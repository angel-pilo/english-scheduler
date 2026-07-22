from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.db.session import get_db
from app.models.enums import PermissionCode, WaitlistStatus
from app.models.user import User
from app.models.waitlist import BookingWaitlist
from app.schemas.bookings import BookingOut, BookingSessionOut
from app.schemas.waitlist import (
    NotificationOut,
    WaitlistAcceptOut,
    WaitlistJoinIn,
    WaitlistOut,
)
from app.services.bookings import BookingConflictError, BookingError, BookingNotFoundError
from app.services.waitlists import (
    NotificationService,
    WaitlistConflictError,
    WaitlistNotFoundError,
    WaitlistService,
)


router = APIRouter(tags=["waitlist"])


@router.post("/students/me/waitlist", response_model=WaitlistOut, status_code=201)
def join_waitlist(
    payload: WaitlistJoinIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(PermissionCode.STUDENT_BOOKINGS_MANAGE)),
) -> WaitlistOut:
    try:
        service = WaitlistService(db)
        return _waitlist_out(service, service.join(user, payload.session_id))
    except BookingError as error:
        _raise_waitlist(error)


@router.get("/students/me/waitlist", response_model=list[WaitlistOut])
def list_my_waitlist(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(PermissionCode.STUDENT_BOOKINGS_MANAGE)),
) -> list[WaitlistOut]:
    try:
        service = WaitlistService(db)
        return [_waitlist_out(service, item) for item in service.list_for_self(user)]
    except BookingError as error:
        _raise_waitlist(error)


@router.delete("/students/me/waitlist/{entry_id}", response_model=WaitlistOut)
def leave_waitlist(
    entry_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(PermissionCode.STUDENT_BOOKINGS_MANAGE)),
) -> WaitlistOut:
    try:
        service = WaitlistService(db)
        return _waitlist_out(service, service.leave(user, entry_id))
    except BookingError as error:
        _raise_waitlist(error)


@router.post(
    "/students/me/waitlist/{entry_id}/accept", response_model=WaitlistAcceptOut
)
def accept_waitlist_offer(
    entry_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(PermissionCode.STUDENT_BOOKINGS_MANAGE)),
) -> WaitlistAcceptOut:
    try:
        service = WaitlistService(db)
        entry, booking = service.accept(user, entry_id)
        return WaitlistAcceptOut(
            entry=_waitlist_out(service, entry),
            booking=BookingOut.model_validate(booking),
        )
    except BookingError as error:
        _raise_waitlist(error)


@router.get("/admin/waitlist", response_model=list[WaitlistOut])
def list_admin_waitlist(
    session_id: int | None = Query(default=None),
    waitlist_status: WaitlistStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.BOOKINGS_MANAGE)),
) -> list[WaitlistOut]:
    try:
        service = WaitlistService(db)
        entries = service.list_for_admin(
            actor,
            session_id=session_id,
            status=waitlist_status.value if waitlist_status else None,
        )
        return [_waitlist_out(service, item) for item in entries]
    except BookingError as error:
        _raise_waitlist(error)


@router.post("/admin/waitlist/process-expired")
def process_expired_waitlist_offers(
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.BOOKINGS_MANAGE)),
) -> dict[str, int]:
    try:
        return {"processed_sessions": WaitlistService(db).process_expired(actor)}
    except BookingError as error:
        _raise_waitlist(error)


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(
    unread_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[NotificationOut]:
    try:
        return [
            NotificationOut.model_validate(item)
            for item in NotificationService(db).list(user, unread_only=unread_only)
        ]
    except BookingError as error:
        _raise_waitlist(error)


@router.patch("/notifications/{notification_id}/read", response_model=NotificationOut)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NotificationOut:
    try:
        return NotificationOut.model_validate(
            NotificationService(db).mark_read(user, notification_id)
        )
    except BookingError as error:
        _raise_waitlist(error)


def _waitlist_out(service: WaitlistService, item: BookingWaitlist) -> WaitlistOut:
    session_data = BookingSessionOut.model_validate(item.session)
    return WaitlistOut(
        id=item.id,
        organization_id=item.organization_id,
        session_id=item.session_id,
        student_id=item.student_id,
        status=item.status,
        offer_expires_at=item.offer_expires_at,
        booking_id=item.booking_id,
        queue_position=service.position(item),
        created_at=item.created_at,
        updated_at=item.updated_at,
        session=session_data,
    )


def _raise_waitlist(error: BookingError) -> None:
    if isinstance(error, (WaitlistNotFoundError, BookingNotFoundError)):
        raise HTTPException(status_code=404, detail=str(error))
    if isinstance(error, (WaitlistConflictError, BookingConflictError)):
        raise HTTPException(status_code=409, detail=str(error))
    raise HTTPException(status_code=400, detail=str(error))
