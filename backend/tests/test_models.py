import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.branch import Branch
from app.models.enums import UserRole
from app.models.org import Organization
from app.models.user import User


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


def test_organization_owns_branches_and_users(session: Session) -> None:
    organization = Organization(name="Academia Uno", slug="academia-uno")
    branch = Branch(name="Centro", code="CENTRO", organization=organization)
    user = User(
        name="Admin",
        email="admin@academia.test",
        hashed_password="not-a-real-hash",
        role=UserRole.ADMIN.value,
        organization=organization,
        branch=branch,
    )
    session.add(user)
    session.commit()

    assert user.organization is organization
    assert user.branch is branch
    assert branch in organization.branches
    assert user in organization.users


def test_branch_code_is_unique_within_organization(session: Session) -> None:
    organization = Organization(name="Academia Uno", slug="academia-uno")
    session.add_all(
        [
            Branch(name="Centro", code="CENTRO", organization=organization),
            Branch(name="Norte", code="CENTRO", organization=organization),
        ]
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_super_admin_has_no_tenant(session: Session) -> None:
    super_admin = User(
        name="Platform Owner",
        email="owner@platform.test",
        hashed_password="not-a-real-hash",
        role=UserRole.SUPER_ADMIN.value,
    )
    session.add(super_admin)
    session.commit()

    assert super_admin.organization_id is None
    assert super_admin.branch_id is None
