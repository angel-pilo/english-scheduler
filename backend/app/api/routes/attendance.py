import json
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.session import get_db
from app.models.enums import PermissionCode
from app.models.user import User
from app.schemas.attendance import (
    AttendanceBulkIn,
    AttendanceEventOut,
    AttendanceRecordOut,
    AttendanceRosterItemOut,
)
from app.services.attendance import (
    AttendanceAccessError,
    AttendanceConflictError,
    AttendanceError,
    AttendanceNotFoundError,
    AttendanceRosterItem,
    AttendanceService,
)


router = APIRouter(tags=["attendance"])


@router.get(
    "/teachers/me/sessions/{session_id}/attendance",
    response_model=list[AttendanceRosterItemOut],
)
def get_teacher_attendance(
    session_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.ATTENDANCE_MANAGE)),
) -> list[AttendanceRosterItemOut]:
    return _get_roster(db, actor, session_id)


@router.put(
    "/teachers/me/sessions/{session_id}/attendance",
    response_model=list[AttendanceRosterItemOut],
)
def save_teacher_attendance(
    session_id: int,
    payload: AttendanceBulkIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.ATTENDANCE_MANAGE)),
) -> list[AttendanceRosterItemOut]:
    return _save_roster(db, actor, session_id, payload)


@router.get(
    "/admin/class-sessions/{session_id}/attendance",
    response_model=list[AttendanceRosterItemOut],
)
def get_admin_attendance(
    session_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.ATTENDANCE_MANAGE)),
) -> list[AttendanceRosterItemOut]:
    return _get_roster(db, actor, session_id)


@router.put(
    "/admin/class-sessions/{session_id}/attendance",
    response_model=list[AttendanceRosterItemOut],
)
def save_admin_attendance(
    session_id: int,
    payload: AttendanceBulkIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.ATTENDANCE_MANAGE)),
) -> list[AttendanceRosterItemOut]:
    return _save_roster(db, actor, session_id, payload)


@router.get(
    "/admin/class-sessions/{session_id}/attendance/history",
    response_model=list[AttendanceEventOut],
)
def get_attendance_history(
    session_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.ATTENDANCE_MANAGE)),
) -> list[AttendanceEventOut]:
    try:
        return [
            AttendanceEventOut(
                id=item.id,
                attendance_id=item.attendance_id,
                previous_values=(
                    json.loads(item.previous_values) if item.previous_values else None
                ),
                new_values=json.loads(item.new_values),
                reason=item.reason,
                actor_user_id=item.actor_user_id,
                created_at=item.created_at,
            )
            for item in AttendanceService(db).history(actor, session_id)
        ]
    except AttendanceError as error:
        _raise_attendance(error)


def _get_roster(
    db: Session, actor: User, session_id: int
) -> list[AttendanceRosterItemOut]:
    try:
        return [
            _roster_item(item)
            for item in AttendanceService(db).roster(actor, session_id)
        ]
    except AttendanceError as error:
        _raise_attendance(error)


def _save_roster(
    db: Session,
    actor: User,
    session_id: int,
    payload: AttendanceBulkIn,
) -> list[AttendanceRosterItemOut]:
    try:
        items = AttendanceService(db).save(
            actor,
            session_id,
            [item.model_dump() for item in payload.records],
            correction_reason=payload.correction_reason,
        )
        return [_roster_item(item) for item in items]
    except AttendanceError as error:
        _raise_attendance(error)


def _roster_item(item: AttendanceRosterItem) -> AttendanceRosterItemOut:
    student = item.booking.student
    return AttendanceRosterItemOut(
        booking_id=item.booking.id,
        student_id=student.id,
        student_number=student.student_number,
        student_name=f"{student.first_name} {student.last_name}".strip(),
        booking_status=item.booking.status,
        attendance_status=(item.attendance.status if item.attendance else "PENDING"),
        attendance=(
            AttendanceRecordOut.model_validate(item.attendance)
            if item.attendance is not None
            else None
        ),
    )


def _raise_attendance(error: AttendanceError) -> NoReturn:
    if isinstance(error, AttendanceNotFoundError):
        raise HTTPException(status_code=404, detail=str(error))
    if isinstance(error, AttendanceAccessError):
        raise HTTPException(status_code=403, detail=str(error))
    if isinstance(error, AttendanceConflictError):
        raise HTTPException(status_code=409, detail=str(error))
    raise HTTPException(status_code=400, detail=str(error))
