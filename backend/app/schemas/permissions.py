from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PermissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    description: str


class PermissionGrantIn(BaseModel):
    permission_code: str
    expires_at: datetime | None = None


class UserPermissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    permission_code: str
    expires_at: datetime | None
    revoked_at: datetime | None
    active: bool
    granted_by_user_id: int


class UserAuthorizationOut(BaseModel):
    user_id: int
    role: str
    effective_permissions: list[str]
    delegations: list[UserPermissionOut]
