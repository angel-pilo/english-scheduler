from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_refresh_token, hash_token
from app.models.branch import Branch
from app.models.booking import BookingPolicy
from app.models.enums import UserRole
from app.models.invitation import Invitation
from app.models.org import Organization
from app.models.user import User


class PlatformError(Exception):
    pass


class PlatformConflictError(PlatformError):
    pass


@dataclass(frozen=True)
class CreatedOrganization:
    organization: Organization
    branch: Branch
    admin: User
    activation_url: str | None


class PlatformService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_organizations(self) -> list[Organization]:
        return list(self.db.scalars(select(Organization).order_by(Organization.name)))

    def create_organization(
        self,
        *,
        actor: User,
        name: str,
        slug: str,
        timezone_name: str,
        branch_name: str,
        branch_code: str,
        admin_name: str,
        admin_email: str,
    ) -> CreatedOrganization:
        if actor.role != UserRole.SUPER_ADMIN.value:
            raise PlatformError("Operación exclusiva de SUPER_ADMIN")

        duplicate = self.db.scalar(
            select(Organization).where(
                or_(Organization.name == name.strip(), Organization.slug == slug.strip())
            )
        )
        if duplicate is not None:
            raise PlatformConflictError("La organización o slug ya existe")
        normalized_email = admin_email.strip().lower()
        if self.db.scalar(select(User).where(User.email == normalized_email)) is not None:
            raise PlatformConflictError("El correo del administrador ya está registrado")

        organization = Organization(
            name=name.strip(),
            slug=slug.strip(),
            timezone=timezone_name,
            active=True,
        )
        branch = Branch(
            organization=organization,
            name=branch_name.strip(),
            code=branch_code.strip().upper(),
            timezone=timezone_name,
            active=True,
        )
        admin = User(
            organization=organization,
            branch=branch,
            role=UserRole.ADMIN.value,
            name=admin_name.strip(),
            email=normalized_email,
            hashed_password=None,
            active=False,
        )
        self.db.add_all([organization, branch, admin])
        self.db.flush()
        self.db.add(
            BookingPolicy(
                organization_id=organization.id,
                branch_id=None,
                minimum_booking_notice_hours=24,
                minimum_cancellation_notice_hours=24,
                earliest_booking_week_offset=1,
                latest_booking_week_offset=1,
                waitlist_offer_minutes=120,
                created_by_user_id=admin.id,
                updated_by_user_id=admin.id,
            )
        )

        raw_token = create_refresh_token()
        invitation = Invitation(
            id=str(uuid4()),
            user_id=admin.id,
            created_by_user_id=actor.id,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(timezone.utc)
            + timedelta(hours=settings.invitation_expire_hours),
        )
        self.db.add(invitation)
        self.db.commit()

        activation_url = None
        if settings.environment.lower() == "development":
            activation_url = f"{settings.frontend_url.rstrip('/')}/activate?token={raw_token}"
        return CreatedOrganization(organization, branch, admin, activation_url)

    def set_organization_active(self, organization_id: int, active: bool) -> Organization:
        organization = self.db.get(Organization, organization_id)
        if organization is None:
            raise PlatformError("Organización no encontrada")
        organization.active = active
        self.db.commit()
        self.db.refresh(organization)
        return organization
