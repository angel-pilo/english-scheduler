from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BranchCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    code: str = Field(min_length=2, max_length=30)
    timezone: str = Field(default="America/Mexico_City", min_length=3, max_length=64)


class BranchUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    code: str | None = Field(default=None, min_length=2, max_length=30)
    timezone: str | None = Field(default=None, min_length=3, max_length=64)
    active: bool | None = None


class BranchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    name: str
    code: str
    timezone: str
    active: bool
    created_at: datetime
    updated_at: datetime


class RoomCreateIn(BaseModel):
    branch_id: int
    name: str = Field(min_length=1, max_length=120)
    code: str = Field(min_length=1, max_length=30)
    capacity: int = Field(gt=0, le=10000)
    description: str | None = Field(default=None, max_length=2000)


class RoomUpdateIn(BaseModel):
    branch_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    code: str | None = Field(default=None, min_length=1, max_length=30)
    capacity: int | None = Field(default=None, gt=0, le=10000)
    description: str | None = Field(default=None, max_length=2000)
    active: bool | None = None


class RoomOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    branch_id: int
    name: str
    code: str
    capacity: int
    description: str | None
    active: bool
    created_at: datetime
    updated_at: datetime
