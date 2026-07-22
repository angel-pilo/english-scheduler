from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models.branch import Branch
from app.models.booking import BookingPolicy
from app.models.enums import UserRole
from app.models.org import Organization
from app.models.user import User


def bootstrap_initial_data(db: Session) -> None:
    organization = db.scalar(
        select(Organization).where(Organization.slug == settings.bootstrap_org_slug)
    )
    if organization is None:
        organization = db.scalar(
            select(Organization).where(Organization.name == settings.bootstrap_org_name)
        )
        if organization is not None:
            organization.slug = settings.bootstrap_org_slug

    if organization is None:
        organization = Organization(
            name=settings.bootstrap_org_name,
            slug=settings.bootstrap_org_slug,
        )
        db.add(organization)
        db.flush()

    branch = db.scalar(
        select(Branch).where(
            Branch.organization_id == organization.id,
            Branch.code == settings.bootstrap_branch_code,
        )
    )
    if branch is None:
        branch = db.scalar(
            select(Branch).where(
                Branch.organization_id == organization.id,
                Branch.name == settings.bootstrap_branch_name,
            )
        )
        if branch is not None:
            branch.code = settings.bootstrap_branch_code

    if branch is None:
        branch = Branch(
            organization_id=organization.id,
            name=settings.bootstrap_branch_name,
            code=settings.bootstrap_branch_code,
        )
        db.add(branch)
        db.flush()

    admin = db.scalar(select(User).where(User.email == settings.bootstrap_admin_email))
    if admin is None:
        admin = User(
            organization_id=organization.id,
            branch_id=branch.id,
            role=UserRole.ADMIN.value,
            name="Admin",
            email=settings.bootstrap_admin_email,
            hashed_password=hash_password(settings.bootstrap_admin_password),
            active=True,
        )
        db.add(admin)
        db.flush()

    policy = db.scalar(
        select(BookingPolicy).where(
            BookingPolicy.organization_id == organization.id,
            BookingPolicy.branch_id.is_(None),
        )
    )
    if policy is None:
        db.add(
            BookingPolicy(
                organization_id=organization.id,
                branch_id=None,
                minimum_booking_notice_hours=24,
                minimum_cancellation_notice_hours=24,
                earliest_booking_week_offset=1,
                latest_booking_week_offset=1,
                created_by_user_id=admin.id,
                updated_by_user_id=admin.id,
            )
        )

    db.commit()
