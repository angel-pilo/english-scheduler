from pydantic import BaseModel, EmailStr, Field


class OrganizationCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    timezone: str = Field(default="America/Mexico_City", min_length=3, max_length=64)
    branch_name: str = Field(min_length=2, max_length=120)
    branch_code: str = Field(min_length=2, max_length=30)
    admin_name: str = Field(min_length=2, max_length=120)
    admin_email: EmailStr


class OrganizationStatusIn(BaseModel):
    active: bool


class OrganizationOut(BaseModel):
    id: int
    name: str
    slug: str
    timezone: str
    active: bool


class OrganizationCreatedOut(OrganizationOut):
    branch_id: int
    admin_user_id: int
    admin_activation_url: str | None = None
