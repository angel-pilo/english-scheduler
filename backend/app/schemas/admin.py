from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: str  # TEACHER o STUDENT
    branch_id: int


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    role: str
    active: bool
    organization_id: int
    branch_id: int
