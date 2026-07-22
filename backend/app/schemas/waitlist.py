from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.bookings import BookingOut, BookingSessionOut


class WaitlistJoinIn(BaseModel):
    session_id: int = Field(gt=0)


class WaitlistOut(BaseModel):
    id: int
    organization_id: int
    session_id: int
    student_id: int
    status: str
    offer_expires_at: datetime | None
    booking_id: int | None
    queue_position: int | None = None
    created_at: datetime
    updated_at: datetime
    session: BookingSessionOut

    model_config = {"from_attributes": True}


class WaitlistAcceptOut(BaseModel):
    entry: WaitlistOut
    booking: BookingOut


class NotificationOut(BaseModel):
    id: int
    notification_type: str
    title: str
    message: str
    entity_type: str
    entity_id: int
    read_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
