from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from uuid import uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
DUMMY_PASSWORD_HASH = "$2b$12$C6UzMDM.H6dfI/f/IKcEe.ou7Nf7MSdDshz7qvLG.CeGVzHRIK8tW"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(
    *,
    user_id: int,
    role: str,
    org_id: int | None,
    branch_id: int | None,
    session_id: str,
) -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    expires_in = settings.access_token_expire_minutes * 60
    payload = {
        "sub": str(user_id),
        "type": "access",
        "sid": session_id,
        "jti": str(uuid4()),
        "role": role,
        "org_id": org_id,
        "branch_id": branch_id,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_in


def decode_access_token(token: str) -> dict[str, object]:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != "access":
        raise JWTError("Invalid token type")
    return payload


def create_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def validate_password_strength(password: str) -> None:
    if len(password) < 12:
        raise ValueError("La contraseña debe tener al menos 12 caracteres")
    if not any(character.islower() for character in password):
        raise ValueError("La contraseña debe incluir una minúscula")
    if not any(character.isupper() for character in password):
        raise ValueError("La contraseña debe incluir una mayúscula")
    if not any(character.isdigit() for character in password):
        raise ValueError("La contraseña debe incluir un número")
    if password.isalnum():
        raise ValueError("La contraseña debe incluir un símbolo")
