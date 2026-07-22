from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_refresh_token,
    hash_password,
    hash_token,
    validate_password_strength,
)
from app.models.auth_session import AuthSession
from app.models.password_reset_token import PasswordResetToken
from app.repositories.users import UserRepository


class PasswordResetError(Exception):
    pass


class InvalidPasswordResetTokenError(PasswordResetError):
    pass


class PasswordResetService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def request(self, email: str) -> str | None:
        user = UserRepository(self.db).get_by_email(email.strip())
        if user is None or not user.active or user.hashed_password is None:
            return None

        now = datetime.now(timezone.utc)
        self.db.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
            )
            .values(used_at=now)
        )
        raw_token = create_refresh_token()
        self.db.add(
            PasswordResetToken(
                id=str(uuid4()),
                user_id=user.id,
                token_hash=hash_token(raw_token),
                expires_at=now + timedelta(minutes=settings.password_reset_expire_minutes),
            )
        )
        self.db.commit()

        if settings.environment.lower() == "development":
            return f"{settings.frontend_url.rstrip('/')}/reset-password?token={raw_token}"
        return None

    def reset(self, *, token: str, password: str, password_confirmation: str) -> None:
        if password != password_confirmation:
            raise PasswordResetError("Las contraseñas no coinciden")
        try:
            validate_password_strength(password)
        except ValueError as error:
            raise PasswordResetError(str(error)) from error

        reset_token = self.db.scalar(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash == hash_token(token)
            )
        )
        now = datetime.now(timezone.utc)
        if (
            reset_token is None
            or reset_token.used_at is not None
            or self._as_utc(reset_token.expires_at) <= now
            or not reset_token.user.active
        ):
            raise InvalidPasswordResetTokenError("Token inválido o expirado")

        reset_token.user.hashed_password = hash_password(password)
        reset_token.user.failed_login_attempts = 0
        reset_token.user.locked_until = None
        reset_token.used_at = now
        self.db.execute(
            update(AuthSession)
            .where(AuthSession.user_id == reset_token.user_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        self.db.commit()

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
