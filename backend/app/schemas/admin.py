from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class InvitationCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    role: str
    branch_id: int


class InvitationOut(BaseModel):
    id: str
    user_id: int
    email: EmailStr
    expires_at: datetime
    activation_url: str | None = None
