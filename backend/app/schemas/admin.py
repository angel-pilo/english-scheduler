from pydantic import BaseModel, EmailStr, Field

class UserCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: str  # TEACHER o STUDENT
    branch_id: int

class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: str
    active: bool
    organization_id: int
    branch_id: int
