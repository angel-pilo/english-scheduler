from datetime import date, datetime, time

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import TeacherStatus


class AcademicLevelCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    sort_order: int = Field(ge=0)
    default_capacity: int | None = Field(default=None, gt=0)


class AcademicLevelUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    sort_order: int | None = Field(default=None, ge=0)
    default_capacity: int | None = Field(default=None, gt=0)
    active: bool | None = None


class AcademicLevelOut(BaseModel):
    id: int
    organization_id: int
    name: str
    description: str | None
    sort_order: int
    default_capacity: int | None
    active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TeacherCreateIn(BaseModel):
    employee_number: str = Field(min_length=1, max_length=40)
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=30)
    hire_date: date
    status: TeacherStatus = TeacherStatus.ACTIVE
    administrative_notes: str | None = Field(default=None, max_length=4000)
    branch_ids: list[int] = Field(min_length=1)
    level_ids: list[int] = Field(default_factory=list)


class TeacherUpdateIn(BaseModel):
    employee_number: str | None = Field(default=None, min_length=1, max_length=40)
    first_name: str | None = Field(default=None, min_length=1, max_length=80)
    last_name: str | None = Field(default=None, min_length=1, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    hire_date: date | None = None
    status: TeacherStatus | None = None
    administrative_notes: str | None = Field(default=None, max_length=4000)
    branch_ids: list[int] | None = Field(default=None, min_length=1)
    level_ids: list[int] | None = None


class TeacherSelfUpdateIn(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=80)
    last_name: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=30)


class TeacherOut(BaseModel):
    id: int
    user_id: int
    organization_id: int
    employee_number: str
    first_name: str
    last_name: str
    email: EmailStr
    phone: str | None
    hire_date: date
    status: str
    administrative_notes: str | None
    photo_storage_key: str | None
    branch_ids: list[int]
    level_ids: list[int]
    account_active: bool
    created_at: datetime
    updated_at: datetime


class TeacherCreatedOut(TeacherOut):
    activation_url: str | None = None


class AvailabilityBlockIn(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start_time: time
    end_time: time


class AvailabilityBlockOut(AvailabilityBlockIn):
    id: int


class AvailabilityExceptionIn(BaseModel):
    exception_date: date
    is_available: bool
    start_time: time | None = None
    end_time: time | None = None


class AvailabilityExceptionOut(AvailabilityExceptionIn):
    id: int


class TeacherAvailabilityIn(BaseModel):
    recurring_blocks: list[AvailabilityBlockIn] = Field(default_factory=list)
    exceptions: list[AvailabilityExceptionIn] = Field(default_factory=list)


class TeacherAvailabilityOut(BaseModel):
    recurring_blocks: list[AvailabilityBlockOut]
    exceptions: list[AvailabilityExceptionOut]
