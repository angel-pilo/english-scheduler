from datetime import date, datetime, time

from pydantic import BaseModel, Field

from app.models.enums import ClassSessionStatus


class GenerateWeekIn(BaseModel):
    week_start: date
    branch_id: int | None = None


class ClassSessionUpdateIn(BaseModel):
    teacher_id: int | None = None
    room_id: int = Field(default=None, gt=0)
    configured_capacity: int = Field(default=None, gt=0)
    title: str = Field(default=None, min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=4000)
    status: ClassSessionStatus = None


class ClassSessionOut(BaseModel):
    id: int
    organization_id: int
    source_template_id: int
    generation_batch_id: str
    branch_id: int
    room_id: int
    level_id: int
    teacher_id: int | None
    title: str
    session_date: date
    start_time: time
    end_time: time
    configured_capacity: int
    effective_capacity: int
    status: str
    notes: str | None
    created_by_user_id: int
    updated_by_user_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GenerationIssueOut(BaseModel):
    template_id: int
    session_date: date
    reason: str


class GenerateWeekOut(BaseModel):
    batch_id: str
    week_start: date
    week_end: date
    created_count: int
    assigned_count: int
    unassigned_count: int
    existing_count: int
    blocked_count: int
    sessions: list[ClassSessionOut]
    issues: list[GenerationIssueOut]
