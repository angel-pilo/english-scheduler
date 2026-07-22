from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_refresh_token,
    hash_password,
    hash_token,
    validate_password_strength,
)
from app.models.branch import Branch
from app.models.enums import StudentStatus, UserRole
from app.models.invitation import Invitation
from app.models.user import User


class InvitationError(Exception):
    pass


class InvitationConflictError(InvitationError):
    pass


class InvalidInvitationError(InvitationError):
    pass


@dataclass(frozen=True)
class CreatedInvitation:
    invitation: Invitation
    email: str
    activation_url: str | None


class InvitationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        admin: User,
        name: str,
        email: str,
        role: str,
        branch_id: int,
    ) -> CreatedInvitation:
        if role != UserRole.TEACHER.value:
            raise InvitationError("Los alumnos deben darse de alta mediante /admin/students")

        branch = self.db.scalar(
            select(Branch).where(
                Branch.id == branch_id,
                Branch.organization_id == admin.organization_id,
                Branch.active.is_(True),
            )
        )
        if branch is None:
            raise InvitationError("Sucursal inválida para esta organización")

        normalized_email = email.strip().lower()
        existing_user = self.db.scalar(
            select(User).where(func.lower(User.email) == normalized_email)
        )
        if existing_user is not None:
            raise InvitationConflictError("El correo ya está registrado")

        user = User(
            organization_id=admin.organization_id,
            branch_id=branch.id,
            role=role,
            name=name.strip(),
            email=normalized_email,
            hashed_password=None,
            active=False,
        )
        self.db.add(user)
        self.db.flush()

        return self.create_for_existing_user(admin=admin, user=user)

    def create_for_existing_user(self, *, admin: User, user: User) -> CreatedInvitation:
        if user.active or user.hashed_password is not None:
            raise InvitationError("El usuario ya tiene una cuenta activa")
        if (
            admin.role != UserRole.SUPER_ADMIN.value
            and admin.organization_id != user.organization_id
        ):
            raise InvitationError("El usuario no pertenece a esta organización")

        raw_token = create_refresh_token()
        invitation = Invitation(
            id=str(uuid4()),
            user_id=user.id,
            created_by_user_id=admin.id,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(timezone.utc)
            + timedelta(hours=settings.invitation_expire_hours),
        )
        self.db.add(invitation)
        self.db.commit()
        self.db.refresh(invitation)

        activation_url = None
        if settings.environment.lower() == "development":
            activation_url = f"{settings.frontend_url.rstrip('/')}/activate?token={raw_token}"
        return CreatedInvitation(invitation, user.email, activation_url)

    def activate(self, *, token: str, password: str, password_confirmation: str) -> User:
        if password != password_confirmation:
            raise InvitationError("Las contraseñas no coinciden")
        try:
            validate_password_strength(password)
        except ValueError as error:
            raise InvitationError(str(error)) from error

        invitation = self.db.scalar(
            select(Invitation).where(Invitation.token_hash == hash_token(token))
        )
        now = datetime.now(timezone.utc)
        if (
            invitation is None
            or invitation.used_at is not None
            or self._as_utc(invitation.expires_at) <= now
            or invitation.user.active
            or (
                invitation.user.student_profile is not None
                and invitation.user.student_profile.status != StudentStatus.ACTIVE.value
            )
        ):
            raise InvalidInvitationError("Invitación inválida o expirada")

        invitation.user.hashed_password = hash_password(password)
        invitation.user.active = True
        invitation.used_at = now
        self.db.commit()
        return invitation.user

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
