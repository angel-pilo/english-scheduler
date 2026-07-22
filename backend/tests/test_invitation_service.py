from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.base import Base
from app.models.branch import Branch
from app.models.enums import UserRole
from app.models.org import Organization
from app.models.user import User
from app.services.auth import AuthService
from app.services.invitations import InvitationError, InvitationService, InvalidInvitationError


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


@pytest.fixture
def admin_and_branch(session: Session) -> tuple[User, Branch]:
    organization = Organization(name="Academia Uno", slug="academia-uno")
    branch = Branch(name="Centro", code="CENTRO", organization=organization)
    admin = User(
        name="Admin",
        email="admin@academia.test",
        hashed_password=hash_password("AdminPassword123!"),
        role=UserRole.ADMIN.value,
        organization=organization,
        branch=branch,
    )
    session.add(admin)
    session.commit()
    return admin, branch


def test_invitation_activates_account_once(
    session: Session, admin_and_branch: tuple[User, Branch]
) -> None:
    admin, branch = admin_and_branch
    created = InvitationService(session).create(
        admin=admin,
        name="Student One",
        email="STUDENT@ACADEMIA.TEST",
        role=UserRole.STUDENT.value,
        branch_id=branch.id,
    )
    assert created.activation_url is not None
    token = parse_qs(urlparse(created.activation_url).query)["token"][0]

    user = InvitationService(session).activate(
        token=token,
        password="StudentPassword123!",
        password_confirmation="StudentPassword123!",
    )

    assert user.active is True
    assert user.email == "student@academia.test"
    AuthService(session).login(
        email=user.email,
        password="StudentPassword123!",
        user_agent=None,
        ip_address=None,
    )
    with pytest.raises(InvalidInvitationError):
        InvitationService(session).activate(
            token=token,
            password="AnotherPassword123!",
            password_confirmation="AnotherPassword123!",
        )


def test_admin_cannot_invite_into_another_tenant(
    session: Session, admin_and_branch: tuple[User, Branch]
) -> None:
    admin, _ = admin_and_branch
    other_organization = Organization(name="Academia Dos", slug="academia-dos")
    other_branch = Branch(name="Norte", code="NORTE", organization=other_organization)
    session.add(other_branch)
    session.commit()

    with pytest.raises(InvitationError, match="Sucursal inválida"):
        InvitationService(session).create(
            admin=admin,
            name="Student Two",
            email="student2@academia.test",
            role=UserRole.STUDENT.value,
            branch_id=other_branch.id,
        )
