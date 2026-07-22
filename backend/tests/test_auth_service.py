import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.security import decode_access_token, hash_password
from app.db.base import Base
from app.models.branch import Branch
from app.models.enums import UserRole
from app.models.org import Organization
from app.models.user import User
from app.services.auth import AuthService, InvalidRefreshTokenError


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
        name="Admin",
        email="admin@academia.test",
        hashed_password=hash_password("CorrectPassword123!"),
        role=UserRole.ADMIN.value,
        organization=organization,
        branch=branch,
    )
    session.add(user)
    session.commit()
    return user


def test_login_creates_a_persisted_session(session: Session, active_user: User) -> None:
    tokens = AuthService(session).login(
        email=active_user.email,
        password="CorrectPassword123!",
        user_agent="pytest",
        ip_address="127.0.0.1",
    )
    payload = decode_access_token(tokens.access_token)

    assert payload["sub"] == str(active_user.id)
    assert payload["type"] == "access"
    assert payload["sid"] == active_user.auth_sessions[0].id
    assert active_user.auth_sessions[0].refresh_token_hash != tokens.refresh_token


def test_refresh_token_is_rotated(session: Session, active_user: User) -> None:
    first = AuthService(session).login(
        email=active_user.email,
        password="CorrectPassword123!",
        user_agent=None,
        ip_address=None,
    )
    second = AuthService(session).refresh(first.refresh_token)

    assert second.refresh_token != first.refresh_token
    with pytest.raises(InvalidRefreshTokenError):
        AuthService(session).refresh(first.refresh_token)


def test_logout_revokes_refresh_token(session: Session, active_user: User) -> None:
    tokens = AuthService(session).login(
        email=active_user.email,
        password="CorrectPassword123!",
        user_agent=None,
        ip_address=None,
    )
    auth_session = active_user.auth_sessions[0]

    AuthService(session).logout(auth_session)

    with pytest.raises(InvalidRefreshTokenError):
        AuthService(session).refresh(tokens.refresh_token)
