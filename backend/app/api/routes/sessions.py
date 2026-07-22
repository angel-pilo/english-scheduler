from datetime import date
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.session import get_db
from app.models.enums import ClassSessionStatus, PermissionCode
from app.models.user import User
from app.schemas.sessions import (
    ClassSessionOut,
    ClassSessionUpdateIn,
    GenerateWeekIn,
    GenerateWeekOut,
    GenerationIssueOut,
)
from app.services.session_generation import (
    ClassSessionConflictError,
    ClassSessionNotFoundError,
    ClassSessionService,
    SessionGenerationError,
)
from app.services.teachers import TeacherNotFoundError, TeacherService


router = APIRouter(tags=["class-sessions"])


@router.post("/admin/class-sessions/generate-week", response_model=GenerateWeekOut)
def generate_week(
    payload: GenerateWeekIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.SCHEDULE_MANAGE)),
) -> GenerateWeekOut:
    try:
        result = ClassSessionService(db).generate_week(
            actor, week_start=payload.week_start, branch_id=payload.branch_id
        )
        assigned = sum(item.teacher_id is not None for item in result.sessions)
        return GenerateWeekOut(
            batch_id=result.batch_id,
            week_start=result.week_start,
            week_end=result.week_end,
            created_count=len(result.sessions),
            assigned_count=assigned,
            unassigned_count=len(result.sessions) - assigned,
            existing_count=result.existing_count,
            blocked_count=result.blocked_count,
            sessions=[ClassSessionOut.model_validate(item) for item in result.sessions],
            issues=[
                GenerationIssueOut(
                    template_id=item.template_id,
                    session_date=item.session_date,
                    reason=item.reason,
                )
                for item in result.issues
            ],
        )
    except SessionGenerationError as error:
        _raise_session(error)


@router.get("/admin/class-sessions", response_model=list[ClassSessionOut])
def list_class_sessions(
    date_from: date = Query(),
    date_to: date = Query(),
    branch_id: int | None = Query(default=None),
    teacher_id: int | None = Query(default=None),
    session_status: ClassSessionStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.SCHEDULE_MANAGE)),
) -> list[ClassSessionOut]:
    try:
        return [
            ClassSessionOut.model_validate(item)
            for item in ClassSessionService(db).list(
                actor,
                date_from=date_from,
                date_to=date_to,
                branch_id=branch_id,
                teacher_id=teacher_id,
                status=session_status.value if session_status else None,
            )
        ]
    except SessionGenerationError as error:
        _raise_session(error)


@router.get("/admin/class-sessions/{session_id}", response_model=ClassSessionOut)
def get_class_session(
    session_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.SCHEDULE_MANAGE)),
) -> ClassSessionOut:
    try:
        return ClassSessionOut.model_validate(
            ClassSessionService(db).get(actor, session_id)
        )
    except SessionGenerationError as error:
        _raise_session(error)


@router.patch("/admin/class-sessions/{session_id}", response_model=ClassSessionOut)
def update_class_session(
    session_id: int,
    payload: ClassSessionUpdateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.SCHEDULE_MANAGE)),
) -> ClassSessionOut:
    try:
        return ClassSessionOut.model_validate(
            ClassSessionService(db).update(
                actor, session_id, payload.model_dump(exclude_unset=True)
            )
        )
    except SessionGenerationError as error:
        _raise_session(error)


@router.get("/teachers/me/sessions", response_model=list[ClassSessionOut])
def get_my_teacher_sessions(
    date_from: date = Query(),
    date_to: date = Query(),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(PermissionCode.OWN_SCHEDULE_VIEW)),
) -> list[ClassSessionOut]:
    try:
        teacher = TeacherService(db).get_self(user)
        return [
            ClassSessionOut.model_validate(item)
            for item in ClassSessionService(db).list(
                user,
                date_from=date_from,
                date_to=date_to,
                teacher_id=teacher.id,
                status=ClassSessionStatus.PUBLISHED.value,
            )
        ]
    except TeacherNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except SessionGenerationError as error:
        _raise_session(error)


def _raise_session(error: SessionGenerationError) -> NoReturn:
    if isinstance(error, ClassSessionNotFoundError):
        raise HTTPException(status_code=404, detail=str(error))
    if isinstance(error, ClassSessionConflictError):
        raise HTTPException(status_code=409, detail=str(error))
    raise HTTPException(status_code=400, detail=str(error))
