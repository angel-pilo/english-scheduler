from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.session import get_db
from app.models.enums import PermissionCode, TeacherStatus
from app.models.teacher import TeacherProfile
from app.models.user import User
from app.schemas.teachers import (
    AcademicLevelCreateIn,
    AcademicLevelOut,
    AcademicLevelUpdateIn,
    AvailabilityBlockOut,
    AvailabilityExceptionOut,
    TeacherAvailabilityIn,
    TeacherAvailabilityOut,
    TeacherCreateIn,
    TeacherCreatedOut,
    TeacherOut,
    TeacherSelfUpdateIn,
    TeacherUpdateIn,
)
from app.services.teachers import (
    LevelService,
    TeacherConflictError,
    TeacherError,
    TeacherNotFoundError,
    TeacherService,
)


router = APIRouter(tags=["teachers"])


@router.get("/admin/levels", response_model=list[AcademicLevelOut])
def list_levels(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.LEVELS_MANAGE)),
):
    return LevelService(db).list(actor, include_inactive=include_inactive)


@router.post("/admin/levels", response_model=AcademicLevelOut, status_code=201)
def create_level(
    payload: AcademicLevelCreateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.LEVELS_MANAGE)),
):
    try:
        return LevelService(db).create(actor, payload.model_dump())
    except TeacherError as error:
        _raise_teacher(error)


@router.patch("/admin/levels/{level_id}", response_model=AcademicLevelOut)
def update_level(
    level_id: int,
    payload: AcademicLevelUpdateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.LEVELS_MANAGE)),
):
    try:
        return LevelService(db).update(
            actor, level_id, payload.model_dump(exclude_unset=True)
        )
    except TeacherError as error:
        _raise_teacher(error)


@router.get("/admin/levels/{level_id}", response_model=AcademicLevelOut)
def get_level(
    level_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.LEVELS_MANAGE)),
):
    try:
        return LevelService(db).get(actor, level_id)
    except TeacherError as error:
        _raise_teacher(error)


@router.delete("/admin/levels/{level_id}", status_code=204)
def deactivate_level(
    level_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.LEVELS_MANAGE)),
) -> Response:
    try:
        LevelService(db).deactivate(actor, level_id)
    except TeacherError as error:
        _raise_teacher(error)
    return Response(status_code=204)


@router.get("/admin/teachers", response_model=list[TeacherOut])
def list_teachers(
    teacher_status: TeacherStatus | None = Query(default=None, alias="status"),
    branch_id: int | None = Query(default=None),
    search: str | None = Query(default=None, max_length=160),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.TEACHERS_MANAGE)),
) -> list[TeacherOut]:
    teachers = TeacherService(db).list(
        actor,
        status=teacher_status.value if teacher_status else None,
        branch_id=branch_id,
        search=search,
    )
    return [_teacher_out(item) for item in teachers]


@router.post("/admin/teachers", response_model=TeacherCreatedOut, status_code=201)
def create_teacher(
    payload: TeacherCreateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.TEACHERS_MANAGE)),
) -> TeacherCreatedOut:
    try:
        teacher, invitation = TeacherService(db).create(actor, payload.model_dump())
    except TeacherError as error:
        _raise_teacher(error)
    return TeacherCreatedOut(
        **_teacher_out(teacher).model_dump(), activation_url=invitation.activation_url
    )


@router.get("/admin/teachers/{teacher_id}", response_model=TeacherOut)
def get_teacher(
    teacher_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.TEACHERS_MANAGE)),
) -> TeacherOut:
    try:
        return _teacher_out(TeacherService(db).get(actor, teacher_id))
    except TeacherError as error:
        _raise_teacher(error)


@router.patch("/admin/teachers/{teacher_id}", response_model=TeacherOut)
def update_teacher(
    teacher_id: int,
    payload: TeacherUpdateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.TEACHERS_MANAGE)),
) -> TeacherOut:
    try:
        return _teacher_out(
            TeacherService(db).update(
                actor, teacher_id, payload.model_dump(exclude_unset=True)
            )
        )
    except TeacherError as error:
        _raise_teacher(error)


@router.delete("/admin/teachers/{teacher_id}", status_code=204)
def deactivate_teacher(
    teacher_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.TEACHERS_MANAGE)),
) -> Response:
    try:
        TeacherService(db).deactivate(actor, teacher_id)
    except TeacherError as error:
        _raise_teacher(error)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/admin/teachers/{teacher_id}/availability",
    response_model=TeacherAvailabilityOut,
)
def get_teacher_availability(
    teacher_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.TEACHERS_MANAGE)),
) -> TeacherAvailabilityOut:
    try:
        return _availability_out(TeacherService(db).get(actor, teacher_id))
    except TeacherError as error:
        _raise_teacher(error)


@router.put(
    "/admin/teachers/{teacher_id}/availability",
    response_model=TeacherAvailabilityOut,
)
def replace_teacher_availability(
    teacher_id: int,
    payload: TeacherAvailabilityIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.TEACHERS_MANAGE)),
) -> TeacherAvailabilityOut:
    service = TeacherService(db)
    try:
        teacher = service.get(actor, teacher_id)
        updated = service.replace_availability(
            teacher,
            [item.model_dump() for item in payload.recurring_blocks],
            [item.model_dump() for item in payload.exceptions],
        )
        return _availability_out(updated)
    except TeacherError as error:
        _raise_teacher(error)


@router.get("/teachers/me", response_model=TeacherOut)
def get_my_teacher_profile(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(PermissionCode.OWN_PROFILE_VIEW)),
) -> TeacherOut:
    try:
        return _teacher_out(TeacherService(db).get_self(user))
    except TeacherError as error:
        _raise_teacher(error)


@router.patch("/teachers/me", response_model=TeacherOut)
def update_my_teacher_profile(
    payload: TeacherSelfUpdateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(PermissionCode.OWN_PROFILE_VIEW)),
) -> TeacherOut:
    try:
        return _teacher_out(
            TeacherService(db).update_self(
                user, payload.model_dump(exclude_unset=True)
            )
        )
    except TeacherError as error:
        _raise_teacher(error)


@router.get("/teachers/me/availability", response_model=TeacherAvailabilityOut)
def get_my_availability(
    db: Session = Depends(get_db),
    user: User = Depends(
        require_permission(PermissionCode.TEACHER_AVAILABILITY_MANAGE)
    ),
) -> TeacherAvailabilityOut:
    try:
        return _availability_out(TeacherService(db).get_self(user))
    except TeacherError as error:
        _raise_teacher(error)


@router.put("/teachers/me/availability", response_model=TeacherAvailabilityOut)
def replace_my_availability(
    payload: TeacherAvailabilityIn,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_permission(PermissionCode.TEACHER_AVAILABILITY_MANAGE)
    ),
) -> TeacherAvailabilityOut:
    service = TeacherService(db)
    try:
        teacher = service.get_self(user)
        updated = service.replace_availability(
            teacher,
            [item.model_dump() for item in payload.recurring_blocks],
            [item.model_dump() for item in payload.exceptions],
        )
        return _availability_out(updated)
    except TeacherError as error:
        _raise_teacher(error)


def _teacher_out(teacher: TeacherProfile) -> TeacherOut:
    return TeacherOut(
        id=teacher.id,
        user_id=teacher.user_id,
        organization_id=teacher.organization_id,
        employee_number=teacher.employee_number,
        first_name=teacher.first_name,
        last_name=teacher.last_name,
        email=teacher.user.email,
        phone=teacher.phone,
        hire_date=teacher.hire_date,
        status=teacher.status,
        administrative_notes=teacher.administrative_notes,
        photo_storage_key=teacher.photo_storage_key,
        branch_ids=sorted(item.branch_id for item in teacher.branch_assignments),
        level_ids=sorted(item.level_id for item in teacher.level_assignments),
        account_active=teacher.user.active,
        created_at=teacher.created_at,
        updated_at=teacher.updated_at,
    )


def _availability_out(teacher: TeacherProfile) -> TeacherAvailabilityOut:
    return TeacherAvailabilityOut(
        recurring_blocks=[
            AvailabilityBlockOut(
                id=item.id,
                weekday=item.weekday,
                start_time=item.start_time,
                end_time=item.end_time,
            )
            for item in sorted(
                teacher.recurring_availability,
                key=lambda value: (value.weekday, value.start_time),
            )
        ],
        exceptions=[
            AvailabilityExceptionOut(
                id=item.id,
                exception_date=item.exception_date,
                is_available=item.is_available,
                start_time=item.start_time,
                end_time=item.end_time,
            )
            for item in sorted(
                teacher.availability_exceptions,
                key=lambda value: value.exception_date,
            )
        ],
    )


def _raise_teacher(error: TeacherError) -> NoReturn:
    if isinstance(error, TeacherNotFoundError):
        raise HTTPException(status_code=404, detail=str(error))
    if isinstance(error, TeacherConflictError):
        raise HTTPException(status_code=409, detail=str(error))
    raise HTTPException(status_code=400, detail=str(error))
