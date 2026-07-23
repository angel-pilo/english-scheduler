import json
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
    AssignBestTeacherIn,
    GenerateWeekIn,
    GenerateWeekOut,
    GenerationIssueOut,
    TeacherAssignmentEventOut,
    TeacherCandidateOut,
    TeacherScoreBreakdownOut,
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


@router.get(
    "/admin/class-sessions/{session_id}/teacher-candidates",
    response_model=list[TeacherCandidateOut],
)
def get_teacher_candidates(
    session_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.SCHEDULE_MANAGE)),
) -> list[TeacherCandidateOut]:
    try:
        result = []
        for item in ClassSessionService(db).teacher_candidates(actor, session_id):
            breakdown = (
                TeacherScoreBreakdownOut(**item.breakdown.as_dict())
                if item.breakdown is not None
                else None
            )
            result.append(
                TeacherCandidateOut(
                    teacher_id=item.teacher.id,
                    teacher_name=f"{item.teacher.first_name} {item.teacher.last_name}".strip(),
                    eligible=item.eligible,
                    ineligibility_reason=item.ineligibility_reason,
                    score=item.score,
                    breakdown=breakdown,
                )
            )
        return result
    except SessionGenerationError as error:
        _raise_session(error)


@router.post(
    "/admin/class-sessions/{session_id}/assign-best-teacher",
    response_model=ClassSessionOut,
)
def assign_best_teacher(
    session_id: int,
    payload: AssignBestTeacherIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.SCHEDULE_MANAGE)),
) -> ClassSessionOut:
    try:
        return ClassSessionOut.model_validate(
            ClassSessionService(db).assign_best_teacher(
                actor, session_id, reason=payload.reason
            )
        )
    except SessionGenerationError as error:
        _raise_session(error)


@router.get(
    "/admin/class-sessions/{session_id}/assignment-history",
    response_model=list[TeacherAssignmentEventOut],
)
def get_assignment_history(
    session_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.SCHEDULE_MANAGE)),
) -> list[TeacherAssignmentEventOut]:
    try:
        return [
            TeacherAssignmentEventOut(
                id=item.id,
                session_id=item.session_id,
                previous_teacher_id=item.previous_teacher_id,
                new_teacher_id=item.new_teacher_id,
                method=item.method,
                score=item.score,
                score_breakdown=(
                    json.loads(item.score_breakdown) if item.score_breakdown else None
                ),
                reason=item.reason,
                actor_user_id=item.actor_user_id,
                created_at=item.created_at,
            )
            for item in ClassSessionService(db).assignment_history(actor, session_id)
        ]
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
