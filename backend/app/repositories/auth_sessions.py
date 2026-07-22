from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.auth_session import AuthSession


class AuthSessionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, session_id: str) -> AuthSession | None:
        return self.db.get(AuthSession, session_id)

    def get_by_refresh_hash(self, token_hash: str) -> AuthSession | None:
        return self.db.scalar(
            select(AuthSession).where(AuthSession.refresh_token_hash == token_hash)
        )
