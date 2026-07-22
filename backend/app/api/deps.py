from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.auth_session import AuthSession
from app.models.user import User


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: AuthSession


def get_auth_context(
    db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)
) -> AuthContext:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido o expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id = int(str(payload["sub"]))
        session_id = str(payload["sid"])
    except (JWTError, KeyError, TypeError, ValueError):
        raise unauthorized

    auth_session = db.get(AuthSession, session_id)
    user = db.get(User, user_id)
    now = datetime.now(timezone.utc)
    if (
        auth_session is None
        or user is None
        or auth_session.user_id != user.id
        or auth_session.revoked_at is not None
        or _as_utc(auth_session.expires_at) <= now
        or not user.active
    ):
        raise unauthorized
    return AuthContext(user=user, session=auth_session)


def get_current_user(context: AuthContext = Depends(get_auth_context)) -> User:
    return context.user


def require_role(*roles: str):
    def _inner(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No autorizado")
        return user

    return _inner


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
