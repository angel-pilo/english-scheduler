from pydantic import BaseModel, ConfigDict, EmailStr, Field


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=512)


class ActivateAccountIn(BaseModel):
    token: str = Field(min_length=32, max_length=512)
    password: str = Field(min_length=12, max_length=128)
    password_confirmation: str = Field(min_length=12, max_length=128)


class MessageOut(BaseModel):
    message: str


class PasswordResetRequestIn(BaseModel):
    email: EmailStr


class PasswordResetRequestOut(MessageOut):
    reset_url: str | None = None


class PasswordResetIn(BaseModel):
    token: str = Field(min_length=32, max_length=512)
    password: str = Field(min_length=12, max_length=128)
    password_confirmation: str = Field(min_length=12, max_length=128)


class MeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    role: str
    organization_id: int | None
    branch_id: int | None
