from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.session import get_db
from app.models.enums import PermissionCode, StudentStatus
from app.models.student import StudentProfile
from app.models.user import User
from app.schemas.students import (
    StudentCreateIn,
    StudentCreatedOut,
    StudentOut,
    StudentSelfUpdateIn,
    StudentUpdateIn,
)
from app.services.students import (
    StudentConflictError,
    StudentError,
    StudentNotFoundError,
    StudentService,
)


router = APIRouter(tags=["students"])


@router.get("/admin/students", response_model=list[StudentOut])
def list_students(
    student_status: StudentStatus | None = Query(default=None, alias="status"),
    branch_id: int | None = Query(default=None),
    search: str | None = Query(default=None, max_length=160),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.STUDENTS_MANAGE)),
) -> list[StudentOut]:
    students = StudentService(db).list(
        actor,
        status=student_status.value if student_status else None,
        branch_id=branch_id,
        search=search,
    )
    return [_student_out(item) for item in students]


@router.post(
    "/admin/students",
    response_model=StudentCreatedOut,
    status_code=status.HTTP_201_CREATED,
)
def create_student(
    payload: StudentCreateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.STUDENTS_MANAGE)),
) -> StudentCreatedOut:
    try:
        student, invitation = StudentService(db).create(actor, payload.model_dump())
    except StudentError as error:
        _raise_student(error)
    return StudentCreatedOut(
        **_student_out(student).model_dump(), activation_url=invitation.activation_url
    )


@router.get("/admin/students/{student_id}", response_model=StudentOut)
def get_student(
    student_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.STUDENTS_MANAGE)),
) -> StudentOut:
    try:
        return _student_out(StudentService(db).get(actor, student_id))
    except StudentError as error:
        _raise_student(error)


@router.patch("/admin/students/{student_id}", response_model=StudentOut)
def update_student(
    student_id: int,
    payload: StudentUpdateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.STUDENTS_MANAGE)),
) -> StudentOut:
    try:
        student = StudentService(db).update(
            actor, student_id, payload.model_dump(exclude_unset=True)
        )
        return _student_out(student)
    except StudentError as error:
        _raise_student(error)


@router.delete("/admin/students/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
def withdraw_student(
    student_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(PermissionCode.STUDENTS_MANAGE)),
) -> Response:
    try:
        StudentService(db).withdraw(actor, student_id)
    except StudentError as error:
        _raise_student(error)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/students/me", response_model=StudentOut)
def get_my_student_profile(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(PermissionCode.OWN_PROFILE_VIEW)),
) -> StudentOut:
    try:
        return _student_out(StudentService(db).get_self(user))
    except StudentError as error:
        _raise_student(error)


@router.patch("/students/me", response_model=StudentOut)
def update_my_student_profile(
    payload: StudentSelfUpdateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(PermissionCode.OWN_PROFILE_VIEW)),
) -> StudentOut:
    try:
        student = StudentService(db).update_self(
            user, payload.model_dump(exclude_unset=True)
        )
        return _student_out(student)
    except StudentError as error:
        _raise_student(error)


def _student_out(student: StudentProfile) -> StudentOut:
    return StudentOut(
        id=student.id,
        user_id=student.user_id,
        organization_id=student.organization_id,
        primary_branch_id=student.primary_branch_id,
        student_number=student.student_number,
        first_name=student.first_name,
        last_name=student.last_name,
        email=student.user.email,
        phone=student.phone,
        address=student.address,
        company=student.company,
        emergency_contact_name=student.emergency_contact_name,
        emergency_contact_phone=student.emergency_contact_phone,
        admission_date=student.admission_date,
        weekly_hours_limit=student.weekly_hours_limit,
        status=student.status,
        course_start_date=student.course_start_date,
        course_end_date=student.course_end_date,
        can_book_other_branches=student.can_book_other_branches,
        administrative_notes=student.administrative_notes,
        photo_storage_key=student.photo_storage_key,
        account_active=student.user.active,
        created_at=student.created_at,
        updated_at=student.updated_at,
    )


def _raise_student(error: StudentError) -> NoReturn:
    if isinstance(error, StudentNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    if isinstance(error, StudentConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
