import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.base import Base
from app.models.enums import UserRole
from app.models.user import User
from app.services.auth import AuthService, InvalidCredentialsError
from app.services.platform import PlatformService


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


@pytest.fixture
def super_admin(session: Session) -> User:
    user = User(
        name="Owner",
        email="owner@platform.test",
        hashed_password=hash_password("OwnerPassword123!"),
        role=UserRole.SUPER_ADMIN.value,
        active=True,
    )
    session.add(user)
    session.commit()
    return user


def test_super_admin_creates_tenant_and_primary_admin(
    session: Session, super_admin: User
) -> None:
    created = PlatformService(session).create_organization(
        actor=super_admin,
        name="Academia Uno",
        slug="academia-uno",
        timezone_name="America/Mexico_City",
        branch_name="Centro",
        branch_code="centro",
        admin_name="Tenant Admin",
        admin_email="ADMIN@ACADEMIA.TEST",
    )

    assert created.organization.id is not None
    assert created.branch.organization_id == created.organization.id
    assert created.branch.code == "CENTRO"
    assert created.admin.organization_id == created.organization.id
    assert created.admin.role == UserRole.ADMIN.value
    assert created.admin.active is False
    assert created.activation_url is not None


def test_inactive_organization_cannot_authenticate(
    session: Session, super_admin: User
) -> None:
    created = PlatformService(session).create_organization(
        actor=super_admin,
        name="Academia Uno",
        slug="academia-uno",
        timezone_name="America/Mexico_City",
        branch_name="Centro",
        branch_code="CENTRO",
        admin_name="Tenant Admin",
        admin_email="admin@academia.test",
    )
    created.admin.hashed_password = hash_password("AdminPassword123!")
    created.admin.active = True
    session.commit()
    PlatformService(session).set_organization_active(created.organization.id, False)

    with pytest.raises(InvalidCredentialsError):
        AuthService(session).login(
            email=created.admin.email,
            password="AdminPassword123!",
            user_agent=None,
            ip_address=None,
        )
