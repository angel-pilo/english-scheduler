from datetime import date, datetime, time

from pydantic import BaseModel, Field, model_validator


class BookingPolicyTimeBlockIn(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start_time: time
    end_time: time

    @model_validator(mode="after")
    def validate_times(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time debe ser posterior a start_time")
        return self


class BookingPolicyIn(BaseModel):
    minimum_booking_notice_hours: int = Field(default=24, ge=0, le=8760)
    minimum_cancellation_notice_hours: int = Field(default=24, ge=0, le=8760)
    earliest_booking_week_offset: int = Field(default=1, ge=0, le=52)
    latest_booking_week_offset: int = Field(default=1, ge=0, le=52)
    time_blocks: list[BookingPolicyTimeBlockIn] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_offsets(self):
        if self.latest_booking_week_offset < self.earliest_booking_week_offset:
            raise ValueError("La semana final debe ser igual o posterior a la inicial")
        return self


class BookingPolicyTimeBlockOut(BaseModel):
    id: int
    weekday: int
    start_time: time
    end_time: time

    model_config = {"from_attributes": True}


class BookingPolicyOut(BaseModel):
    id: int
    organization_id: int
    branch_id: int | None
    minimum_booking_notice_hours: int
    minimum_cancellation_notice_hours: int
    earliest_booking_week_offset: int
    latest_booking_week_offset: int
    time_blocks: list[BookingPolicyTimeBlockOut]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BookingCreateIn(BaseModel):
    session_id: int = Field(gt=0)


class AdminBookingCreateIn(BookingCreateIn):
    student_id: int = Field(gt=0)
    override_rules: bool = False
    reason: str | None = Field(default=None, max_length=1000)


class BookingCancelIn(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class AdminBookingCancelIn(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)
    release_quota: bool = True


class LateCancellationReviewIn(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)
    release_quota: bool = True


class BookingSessionOut(BaseModel):
    id: int
    branch_id: int
    room_id: int
    level_id: int
    teacher_id: int | None
    title: str
    session_date: date
    start_time: time
    end_time: time
    effective_capacity: int
    status: str

    model_config = {"from_attributes": True}


class BookingOut(BaseModel):
    id: int
    organization_id: int
    session_id: int
    student_id: int
    status: str
    reserved_minutes: int
    quota_released: bool
    cancelled_at: datetime | None
    created_by_user_id: int
    updated_by_user_id: int
    created_at: datetime
    updated_at: datetime
    session: BookingSessionOut

    model_config = {"from_attributes": True}


class BookingEventOut(BaseModel):
    id: int
    booking_id: int
    actor_user_id: int
    event_type: str
    previous_status: str | None
    new_status: str
    reason: str | None
    override_rules: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AvailableSessionOut(BookingSessionOut):
    confirmed_count: int
    available_places: int
    own_booking_id: int | None
    can_book: bool
    unavailable_reason: str | None


class WeeklyUsageOut(BaseModel):
    week_start: date
    week_end: date
    allowed_minutes: int
    reserved_minutes: int
    available_minutes: int
