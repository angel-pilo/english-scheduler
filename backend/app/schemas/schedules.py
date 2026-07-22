from datetime import date, datetime, time

from pydantic import BaseModel, Field

from app.models.enums import ScheduleExceptionScope


class ScheduleTemplateCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    branch_id: int
    room_id: int
    level_id: int
    weekday: int = Field(ge=0, le=6)
    start_time: time
    end_time: time
    configured_capacity: int | None = Field(default=None, gt=0)
    effective_from: date
    effective_until: date | None = None
    notes: str | None = Field(default=None, max_length=4000)


class ScheduleTemplateUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    branch_id: int | None = None
    room_id: int | None = None
    level_id: int | None = None
    weekday: int | None = Field(default=None, ge=0, le=6)
    start_time: time | None = None
    end_time: time | None = None
    configured_capacity: int | None = Field(default=None, gt=0)
    effective_from: date | None = None
    effective_until: date | None = None
    notes: str | None = Field(default=None, max_length=4000)
    active: bool | None = None


class ScheduleTemplateOut(BaseModel):
    id: int
    organization_id: int
    name: str
    branch_id: int
    room_id: int
    level_id: int
    weekday: int
    start_time: time
    end_time: time
    configured_capacity: int | None
    level_default_capacity: int | None
    room_capacity: int
    effective_capacity: int
    effective_from: date
    effective_until: date | None
    active: bool
    notes: str | None
    created_by_user_id: int
    updated_by_user_id: int
    created_at: datetime
    updated_at: datetime


class ScheduleExceptionCreateIn(BaseModel):
    exception_date: date
    scope: ScheduleExceptionScope
    branch_id: int | None = None
    room_id: int | None = None
    teacher_id: int | None = None
    start_time: time | None = None
    end_time: time | None = None
    reason: str = Field(min_length=1, max_length=500)


class ScheduleExceptionUpdateIn(BaseModel):
    exception_date: date | None = None
    scope: ScheduleExceptionScope | None = None
    branch_id: int | None = None
    room_id: int | None = None
    teacher_id: int | None = None
    start_time: time | None = None
    end_time: time | None = None
    reason: str | None = Field(default=None, min_length=1, max_length=500)
    active: bool | None = None


class ScheduleExceptionOut(BaseModel):
    id: int
    organization_id: int
    exception_date: date
    scope: str
    branch_id: int | None
    room_id: int | None
    teacher_id: int | None
    start_time: time | None
    end_time: time | None
    reason: str
    active: bool
    created_by_user_id: int
    updated_by_user_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
