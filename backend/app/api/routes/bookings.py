from datetime import date
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.session import get_db
from app.models.enums import BookingStatus, PermissionCode
from app.models.user import User
from app.schemas.bookings import (
    AdminBookingCancelIn,
    AdminBookingCreateIn,
    AvailableSessionOut,
    BookingCancelIn,
    BookingCreateIn,
    BookingEventOut,
    BookingOut,
    BookingPolicyIn,
    BookingPolicyOut,
    BookingSessionOut,
    LateCancellationReviewIn,
    WeeklyUsageOut,
)
from app.services.bookings import (
    BookingConflictError,
    BookingError,
    BookingNotFoundError,
    BookingPolicyService,
    BookingService,
)


router = APIRouter(tags=["bookings"])


@router.get("/admin/booking-policies", response_model=list[BookingPolicyOut])
def list_booking_policies(
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.BOOKINGS_MANAGE)),
) -> list[BookingPolicyOut]:
    return [
        BookingPolicyOut.model_validate(item)
        for item in BookingPolicyService(db).list(actor)
    ]


@router.put("/admin/booking-policies/default", response_model=BookingPolicyOut)
def set_default_booking_policy(
    payload: BookingPolicyIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.BOOKINGS_MANAGE)),
) -> BookingPolicyOut:
    return _save_policy(db, actor, None, payload)


@router.put(
    "/admin/booking-policies/branches/{branch_id}", response_model=BookingPolicyOut
)
def set_branch_booking_policy(
    branch_id: int,
    payload: BookingPolicyIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.BOOKINGS_MANAGE)),
) -> BookingPolicyOut:
    return _save_policy(db, actor, branch_id, payload)


@router.get("/students/me/available-sessions", response_model=list[AvailableSessionOut])
def get_available_sessions(
    date_from: date = Query(),
    date_to: date = Query(),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(PermissionCode.STUDENT_BOOKINGS_MANAGE)),
) -> list[AvailableSessionOut]:
    try:
        result = []
        for item in BookingService(db).available_sessions(
            user, date_from=date_from, date_to=date_to
        ):
            session_data = BookingSessionOut.model_validate(item.session).model_dump()
            result.append(
                AvailableSessionOut(
                    **session_data,
                    confirmed_count=item.confirmed_count,
                    held_waitlist_places=item.held_count,
                    available_places=item.available_places,
                    own_booking_id=item.own_booking_id,
                    can_book=item.unavailable_reason is None,
                    unavailable_reason=item.unavailable_reason,
                )
            )
        return result
    except BookingError as error:
        _raise_booking(error)


@router.post("/students/me/bookings", response_model=BookingOut, status_code=201)
def create_my_booking(
    payload: BookingCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(PermissionCode.STUDENT_BOOKINGS_MANAGE)),
) -> BookingOut:
    try:
        return BookingOut.model_validate(
            BookingService(db).create_for_self(user, payload.session_id)
        )
    except BookingError as error:
        _raise_booking(error)


@router.get("/students/me/bookings", response_model=list[BookingOut])
def list_my_bookings(
    date_from: date = Query(),
    date_to: date = Query(),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(PermissionCode.STUDENT_BOOKINGS_MANAGE)),
) -> list[BookingOut]:
    try:
        return [
            BookingOut.model_validate(item)
            for item in BookingService(db).list_for_self(
                user, date_from=date_from, date_to=date_to
            )
        ]
    except BookingError as error:
        _raise_booking(error)


@router.get("/students/me/bookings/weekly-usage", response_model=WeeklyUsageOut)
def get_my_weekly_usage(
    week_start: date = Query(),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(PermissionCode.STUDENT_BOOKINGS_MANAGE)),
) -> WeeklyUsageOut:
    try:
        usage = BookingService(db).weekly_usage(user, week_start=week_start)
        return WeeklyUsageOut(**usage.__dict__, available_minutes=usage.available_minutes)
    except BookingError as error:
        _raise_booking(error)


@router.post("/students/me/bookings/{booking_id}/cancel", response_model=BookingOut)
def cancel_my_booking(
    booking_id: int,
    payload: BookingCancelIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(PermissionCode.STUDENT_BOOKINGS_MANAGE)),
) -> BookingOut:
    try:
        return BookingOut.model_validate(
            BookingService(db).cancel_for_self(
                user, booking_id, reason=payload.reason
            )
        )
    except BookingError as error:
        _raise_booking(error)


@router.get(
    "/students/me/bookings/{booking_id}/history", response_model=list[BookingEventOut]
)
def get_my_booking_history(
    booking_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(PermissionCode.STUDENT_BOOKINGS_MANAGE)),
) -> list[BookingEventOut]:
    try:
        return [
            BookingEventOut.model_validate(item)
            for item in BookingService(db).history(user, booking_id, own=True)
        ]
    except BookingError as error:
        _raise_booking(error)


@router.post("/admin/bookings", response_model=BookingOut, status_code=201)
def create_admin_booking(
    payload: AdminBookingCreateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.BOOKINGS_MANAGE)),
) -> BookingOut:
    try:
        return BookingOut.model_validate(
            BookingService(db).create_for_admin(
                actor,
                student_id=payload.student_id,
                session_id=payload.session_id,
                override_rules=payload.override_rules,
                reason=payload.reason,
            )
        )
    except BookingError as error:
        _raise_booking(error)


@router.get("/admin/bookings", response_model=list[BookingOut])
def list_admin_bookings(
    date_from: date = Query(),
    date_to: date = Query(),
    student_id: int | None = Query(default=None),
    session_id: int | None = Query(default=None),
    booking_status: BookingStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.BOOKINGS_MANAGE)),
) -> list[BookingOut]:
    try:
        return [
            BookingOut.model_validate(item)
            for item in BookingService(db).list_for_admin(
                actor,
                date_from=date_from,
                date_to=date_to,
                student_id=student_id,
                session_id=session_id,
                status=booking_status.value if booking_status else None,
            )
        ]
    except BookingError as error:
        _raise_booking(error)


@router.post("/admin/bookings/{booking_id}/cancel", response_model=BookingOut)
def cancel_admin_booking(
    booking_id: int,
    payload: AdminBookingCancelIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.BOOKINGS_MANAGE)),
) -> BookingOut:
    try:
        return BookingOut.model_validate(
            BookingService(db).cancel_for_admin(
                actor,
                booking_id,
                reason=payload.reason,
                release_quota=payload.release_quota,
            )
        )
    except BookingError as error:
        _raise_booking(error)


@router.post(
    "/admin/bookings/{booking_id}/late-cancellation/approve",
    response_model=BookingOut,
)
def approve_late_cancellation(
    booking_id: int,
    payload: LateCancellationReviewIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.BOOKINGS_MANAGE)),
) -> BookingOut:
    return _review_late_cancellation(db, actor, booking_id, payload, approve=True)


@router.post(
    "/admin/bookings/{booking_id}/late-cancellation/reject",
    response_model=BookingOut,
)
def reject_late_cancellation(
    booking_id: int,
    payload: LateCancellationReviewIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.BOOKINGS_MANAGE)),
) -> BookingOut:
    return _review_late_cancellation(db, actor, booking_id, payload, approve=False)


@router.get("/admin/bookings/{booking_id}/history", response_model=list[BookingEventOut])
def get_admin_booking_history(
    booking_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.BOOKINGS_MANAGE)),
) -> list[BookingEventOut]:
    try:
        return [
            BookingEventOut.model_validate(item)
            for item in BookingService(db).history(actor, booking_id)
        ]
    except BookingError as error:
        _raise_booking(error)


def _save_policy(
    db: Session, actor: User, branch_id: int | None, payload: BookingPolicyIn
) -> BookingPolicyOut:
    try:
        item = BookingPolicyService(db).upsert(
            actor,
            branch_id=branch_id,
            data=payload.model_dump(),
        )
        return BookingPolicyOut.model_validate(item)
    except BookingError as error:
        _raise_booking(error)


def _review_late_cancellation(
    db: Session,
    actor: User,
    booking_id: int,
    payload: LateCancellationReviewIn,
    *,
    approve: bool,
) -> BookingOut:
    try:
        return BookingOut.model_validate(
            BookingService(db).review_late_cancellation(
                actor,
                booking_id,
                approve=approve,
                reason=payload.reason,
                release_quota=payload.release_quota,
            )
        )
    except BookingError as error:
        _raise_booking(error)


def _raise_booking(error: BookingError) -> NoReturn:
    if isinstance(error, BookingNotFoundError):
        raise HTTPException(status_code=404, detail=str(error))
    if isinstance(error, BookingConflictError):
        raise HTTPException(status_code=409, detail=str(error))
    raise HTTPException(status_code=400, detail=str(error))
