from datetime import date
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.session import get_db
from app.models.enums import PermissionCode
from app.models.schedule import ScheduleTemplate
from app.models.user import User
from app.schemas.schedules import (
    ScheduleExceptionCreateIn,
    ScheduleExceptionOut,
    ScheduleExceptionUpdateIn,
    ScheduleTemplateCreateIn,
    ScheduleTemplateOut,
    ScheduleTemplateUpdateIn,
)
from app.services.schedules import (
    ScheduleConflictError,
    ScheduleError,
    ScheduleNotFoundError,
    ScheduleService,
)


router = APIRouter(prefix="/admin", tags=["schedules"])


@router.get("/schedule-templates", response_model=list[ScheduleTemplateOut])
def list_schedule_templates(
    branch_id: int | None = Query(default=None),
    level_id: int | None = Query(default=None),
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.SCHEDULE_MANAGE)),
) -> list[ScheduleTemplateOut]:
    templates = ScheduleService(db).list_templates(
        actor,
        branch_id=branch_id,
        level_id=level_id,
        include_inactive=include_inactive,
    )
    return [_template_out(item) for item in templates]


@router.post(
    "/schedule-templates",
    response_model=ScheduleTemplateOut,
    status_code=status.HTTP_201_CREATED,
)
def create_schedule_template(
    payload: ScheduleTemplateCreateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.SCHEDULE_MANAGE)),
) -> ScheduleTemplateOut:
    try:
        return _template_out(
            ScheduleService(db).create_template(actor, payload.model_dump())
        )
    except ScheduleError as error:
        _raise_schedule(error)


@router.get("/schedule-templates/{template_id}", response_model=ScheduleTemplateOut)
def get_schedule_template(
    template_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.SCHEDULE_MANAGE)),
) -> ScheduleTemplateOut:
    try:
        return _template_out(ScheduleService(db).get_template(actor, template_id))
    except ScheduleError as error:
        _raise_schedule(error)


@router.patch("/schedule-templates/{template_id}", response_model=ScheduleTemplateOut)
def update_schedule_template(
    template_id: int,
    payload: ScheduleTemplateUpdateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.SCHEDULE_MANAGE)),
) -> ScheduleTemplateOut:
    try:
        return _template_out(
            ScheduleService(db).update_template(
                actor, template_id, payload.model_dump(exclude_unset=True)
            )
        )
    except ScheduleError as error:
        _raise_schedule(error)


@router.delete("/schedule-templates/{template_id}", status_code=204)
def deactivate_schedule_template(
    template_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.SCHEDULE_MANAGE)),
) -> Response:
    try:
        ScheduleService(db).deactivate_template(actor, template_id)
    except ScheduleError as error:
        _raise_schedule(error)
    return Response(status_code=204)


@router.get("/schedule-exceptions", response_model=list[ScheduleExceptionOut])
def list_schedule_exceptions(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.SCHEDULE_MANAGE)),
) -> list[ScheduleExceptionOut]:
    try:
        return [
            ScheduleExceptionOut.model_validate(item)
            for item in ScheduleService(db).list_exceptions(
                actor,
                date_from=date_from,
                date_to=date_to,
                include_inactive=include_inactive,
            )
        ]
    except ScheduleError as error:
        _raise_schedule(error)


@router.post(
    "/schedule-exceptions",
    response_model=ScheduleExceptionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_schedule_exception(
    payload: ScheduleExceptionCreateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.SCHEDULE_MANAGE)),
) -> ScheduleExceptionOut:
    try:
        return ScheduleExceptionOut.model_validate(
            ScheduleService(db).create_exception(actor, payload.model_dump())
        )
    except ScheduleError as error:
        _raise_schedule(error)


@router.patch("/schedule-exceptions/{exception_id}", response_model=ScheduleExceptionOut)
def update_schedule_exception(
    exception_id: int,
    payload: ScheduleExceptionUpdateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.SCHEDULE_MANAGE)),
) -> ScheduleExceptionOut:
    try:
        return ScheduleExceptionOut.model_validate(
            ScheduleService(db).update_exception(
                actor, exception_id, payload.model_dump(exclude_unset=True)
            )
        )
    except ScheduleError as error:
        _raise_schedule(error)


@router.delete("/schedule-exceptions/{exception_id}", status_code=204)
def deactivate_schedule_exception(
    exception_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.SCHEDULE_MANAGE)),
) -> Response:
    try:
        ScheduleService(db).deactivate_exception(actor, exception_id)
    except ScheduleError as error:
        _raise_schedule(error)
    return Response(status_code=204)


def _template_out(item: ScheduleTemplate) -> ScheduleTemplateOut:
    return ScheduleTemplateOut(
        id=item.id,
        organization_id=item.organization_id,
        name=item.name,
        branch_id=item.branch_id,
        room_id=item.room_id,
        level_id=item.level_id,
        weekday=item.weekday,
        start_time=item.start_time,
        end_time=item.end_time,
        configured_capacity=item.configured_capacity,
        level_default_capacity=item.level.default_capacity,
        room_capacity=item.room.capacity,
        effective_capacity=ScheduleService.effective_capacity(item),
        effective_from=item.effective_from,
        effective_until=item.effective_until,
        active=item.active,
        notes=item.notes,
        created_by_user_id=item.created_by_user_id,
        updated_by_user_id=item.updated_by_user_id,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _raise_schedule(error: ScheduleError) -> NoReturn:
    if isinstance(error, ScheduleNotFoundError):
        raise HTTPException(status_code=404, detail=str(error))
    if isinstance(error, ScheduleConflictError):
        raise HTTPException(status_code=409, detail=str(error))
    raise HTTPException(status_code=400, detail=str(error))
