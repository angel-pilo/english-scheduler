from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    create_refresh_token,
    hash_token,
    verify_password,
)
from app.models.auth_session import AuthSession
from app.models.user import User
from app.repositories.auth_sessions import AuthSessionRepository
from app.repositories.users import UserRepository


class InvalidCredentialsError(Exception):
    pass


class AccountLockedError(Exception):
    pass


class InvalidRefreshTokenError(Exception):
    pass


@dataclass(frozen=True)
class AuthTokens:
    access_token: str
    refresh_token: str
    expires_in: int


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.sessions = AuthSessionRepository(db)

    def login(
        self,
        *,
        email: str,
        password: str,
        user_agent: str | None,
        ip_address: str | None,
    ) -> AuthTokens:
        now = datetime.now(timezone.utc)
        user = self.users.get_by_email(email.strip())

        if user is None:
            verify_password(password, DUMMY_PASSWORD_HASH)
            raise InvalidCredentialsError

        if user.locked_until is not None and self._as_utc(user.locked_until) > now:
            raise AccountLockedError

        if not user.active or not verify_password(password, user.hashed_password):
            self._record_failed_attempt(user, now)
            raise InvalidCredentialsError

        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = now
        tokens = self._create_session_tokens(
            user=user,
            now=now,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        self.db.commit()
        return tokens

    def refresh(self, refresh_token: str) -> AuthTokens:
        now = datetime.now(timezone.utc)
        auth_session = self.sessions.get_by_refresh_hash(hash_token(refresh_token))
        if (
            auth_session is None
            or auth_session.revoked_at is not None
            or self._as_utc(auth_session.expires_at) <= now
            or not auth_session.user.active
        ):
            raise InvalidRefreshTokenError

        rotated_refresh_token = create_refresh_token()
        auth_session.refresh_token_hash = hash_token(rotated_refresh_token)
        auth_session.last_used_at = now
        access_token, expires_in = self._access_token(auth_session.user, auth_session.id)
        self.db.commit()
        return AuthTokens(access_token, rotated_refresh_token, expires_in)

    def logout(self, auth_session: AuthSession) -> None:
        if auth_session.revoked_at is None:
            auth_session.revoked_at = datetime.now(timezone.utc)
            self.db.commit()

    def _record_failed_attempt(self, user: User, now: datetime) -> None:
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.max_login_attempts:
            user.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
            user.failed_login_attempts = 0
        self.db.commit()

    def _create_session_tokens(
        self,
        *,
        user: User,
        now: datetime,
        user_agent: str | None,
        ip_address: str | None,
    ) -> AuthTokens:
        refresh_token = create_refresh_token()
        auth_session = AuthSession(
            id=str(uuid4()),
            user=user,
            refresh_token_hash=hash_token(refresh_token),
            expires_at=now + timedelta(days=settings.refresh_token_expire_days),
            user_agent=user_agent[:255] if user_agent else None,
            ip_address=ip_address,
        )
        self.db.add(auth_session)
        access_token, expires_in = self._access_token(user, auth_session.id)
        return AuthTokens(access_token, refresh_token, expires_in)

    @staticmethod
    def _access_token(user: User, session_id: str) -> tuple[str, int]:
        return create_access_token(
            user_id=user.id,
            role=user.role,
            org_id=user.organization_id,
            branch_id=user.branch_id,
            session_id=session_id,
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
