from datetime import date, datetime, time

from pydantic import BaseModel, Field, model_validator

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
    assignment_reason: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def require_assignment_reason(self):
        if "teacher_id" in self.model_fields_set and not self.assignment_reason:
            raise ValueError("El motivo de reasignación es obligatorio")
        return self


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


class TeacherScoreBreakdownOut(BaseModel):
    weekly_load_minutes: int
    weekly_load_penalty: int
    recent_total_sessions: int
    recent_total_penalty: int
    recent_same_level_sessions: int
    recent_same_level_penalty: int
    recent_same_template_sessions: int
    recent_same_template_penalty: int
    recent_same_slot_sessions: int
    recent_same_slot_penalty: int
    total_penalty: int


class TeacherCandidateOut(BaseModel):
    teacher_id: int
    teacher_name: str
    eligible: bool
    ineligibility_reason: str | None
    score: int | None
    breakdown: TeacherScoreBreakdownOut | None


class AssignBestTeacherIn(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class TeacherAssignmentEventOut(BaseModel):
    id: int
    session_id: int
    previous_teacher_id: int | None
    new_teacher_id: int | None
    method: str
    score: int | None
    score_breakdown: dict[str, int] | None
    reason: str | None
    actor_user_id: int
    created_at: datetime
