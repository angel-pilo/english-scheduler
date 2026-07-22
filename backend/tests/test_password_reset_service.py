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
from app.services.auth import AuthService, InvalidCredentialsError, InvalidRefreshTokenError
from app.services.password_resets import InvalidPasswordResetTokenError, PasswordResetService


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


@pytest.fixture
def active_user(session: Session) -> User:
    organization = Organization(name="Academia Uno", slug="academia-uno")
    branch = Branch(name="Centro", code="CENTRO", organization=organization)
    user = User(
        name="Student",
        email="student@academia.test",
        hashed_password=hash_password("OldPassword123!"),
        role=UserRole.STUDENT.value,
        organization=organization,
        branch=branch,
    )
    session.add(user)
    session.commit()
    return user


def test_reset_changes_password_and_revokes_sessions(session: Session, active_user: User) -> None:
    old_session = AuthService(session).login(
        email=active_user.email,
        password="OldPassword123!",
        user_agent=None,
        ip_address=None,
    )
    reset_url = PasswordResetService(session).request(active_user.email)
    assert reset_url is not None
    token = parse_qs(urlparse(reset_url).query)["token"][0]

    PasswordResetService(session).reset(
        token=token,
        password="NewPassword123!",
        password_confirmation="NewPassword123!",
    )

    with pytest.raises(InvalidRefreshTokenError):
        AuthService(session).refresh(old_session.refresh_token)
    with pytest.raises(InvalidCredentialsError):
        AuthService(session).login(
            email=active_user.email,
            password="OldPassword123!",
            user_agent=None,
            ip_address=None,
        )
    AuthService(session).login(
        email=active_user.email,
        password="NewPassword123!",
        user_agent=None,
        ip_address=None,
    )
    with pytest.raises(InvalidPasswordResetTokenError):
        PasswordResetService(session).reset(
            token=token,
            password="OtherPassword123!",
            password_confirmation="OtherPassword123!",
        )


def test_unknown_email_does_not_reveal_account_status(session: Session) -> None:
    assert PasswordResetService(session).request("unknown@academia.test") is None
