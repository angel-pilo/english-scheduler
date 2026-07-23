from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.enums import AttendanceStatus


class AttendanceItemIn(BaseModel):
    booking_id: int = Field(gt=0)
    status: AttendanceStatus
    minutes_late: int | None = Field(default=None, gt=0, le=600)
    justification: str | None = Field(default=None, max_length=2000)
    observations: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_status_fields(self):
        if self.status == AttendanceStatus.LATE and self.minutes_late is None:
            raise ValueError("Los minutos de retardo son obligatorios")
        if self.status != AttendanceStatus.LATE and self.minutes_late is not None:
            raise ValueError("Los minutos solo aplican al estado LATE")
        if self.status == AttendanceStatus.JUSTIFIED and not (
            self.justification and self.justification.strip()
        ):
            raise ValueError("La justificación es obligatoria")
        return self


class AttendanceBulkIn(BaseModel):
    records: list[AttendanceItemIn] = Field(min_length=1)
    correction_reason: str | None = Field(default=None, max_length=1000)


class AttendanceRecordOut(BaseModel):
    id: int
    booking_id: int
    status: str
    minutes_late: int | None
    justification: str | None
    observations: str | None
    recorded_by_user_id: int
    updated_by_user_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AttendanceRosterItemOut(BaseModel):
    booking_id: int
    student_id: int
    student_number: str
    student_name: str
    booking_status: str
    attendance_status: str
    attendance: AttendanceRecordOut | None


class AttendanceEventOut(BaseModel):
    id: int
    attendance_id: int
    previous_values: dict[str, object] | None
    new_values: dict[str, object]
    reason: str | None
    actor_user_id: int
    created_at: datetime
