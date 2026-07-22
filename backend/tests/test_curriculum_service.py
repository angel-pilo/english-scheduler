from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.base import Base
from app.models.branch import Branch
from app.models.enums import TeacherStatus, TopicProgressStatus, UserRole
from app.models.org import Organization
from app.models.rbac import Role
from app.models.user import User
from app.services.curriculum import (
    AcademicProgressService,
    CurriculumAccessError,
    CurriculumConflictError,
    CurriculumNotFoundError,
    CurriculumService,
)
from app.services.students import StudentService
from app.services.teachers import LevelService, TeacherService


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all(
            [
                Role(
                    code=UserRole.ADMIN.value,
                    name="Administrator",
                    description="Organization administrator",
                ),
                Role(
                    code=UserRole.STUDENT.value,
                    name="Student",
                    description="Student account",
                ),
                Role(
                    code=UserRole.TEACHER.value,
                    name="Teacher",
                    description="Teacher account",
                ),
            ]
        )
        db.commit()
        yield db


def _tenant(db: Session, suffix: str) -> tuple[User, Branch, Branch]:
    organization = Organization(
        name=f"Academia {suffix}", slug=f"academia-{suffix.lower()}"
    )
    branch = Branch(name="Matriz", code="MATRIZ", organization=organization)
    other_branch = Branch(name="Norte", code="NORTE", organization=organization)
    admin = User(
        name="Admin",
        email=f"admin-{suffix.lower()}@test.local",
        hashed_password=hash_password("AdminPassword123!"),
        role=UserRole.ADMIN.value,
        organization=organization,
        branch=branch,
    )
    db.add(admin)
    db.commit()
    return admin, branch, other_branch


def _student(db: Session, admin: User, branch: Branch, suffix: str = "001"):
    student, _ = StudentService(db).create(
        admin,
        {
            "student_number": f"MAT-{suffix}",
            "first_name": "Ana",
            "last_name": "López",
            "email": f"ana-{suffix}@test.local",
            "primary_branch_id": branch.id,
            "phone": None,
            "address": None,
            "company": None,
            "emergency_contact_name": None,
            "emergency_contact_phone": None,
            "admission_date": date(2026, 1, 1),
            "weekly_hours_limit": Decimal("5.00"),
            "course_start_date": None,
            "course_end_date": None,
            "can_book_other_branches": False,
            "administrative_notes": None,
        },
    )
    return student


def _level(db: Session, admin: User, name: str, order: int):
    return LevelService(db).create(
        admin,
        {
            "name": name,
            "description": None,
            "sort_order": order,
            "default_capacity": 10,
        },
    )


def _curriculum(db: Session, admin: User, level_id: int):
    chapter = CurriculumService(db).create_chapter(
        admin,
        level_id,
        {"name": "Unidad 1", "description": "Inicio", "sort_order": 1},
    )
    topic = CurriculumService(db).create_topic(
        admin,
        chapter.id,
        {"name": "Presentaciones", "description": None, "sort_order": 1},
    )
    return chapter, topic


def test_curriculum_is_ordered_and_tenant_scoped(session: Session) -> None:
    admin, _, _ = _tenant(session, "Uno")
    other_admin, _, _ = _tenant(session, "Dos")
    level = _level(session, admin, "A1", 1)
    chapter, topic = _curriculum(session, admin, level.id)

    levels = CurriculumService(session).list_curriculum(admin)
    assert levels[0].chapters[0].id == chapter.id
    assert levels[0].chapters[0].topics[0].id == topic.id
    with pytest.raises(CurriculumNotFoundError):
        CurriculumService(session).get_chapter(other_admin, chapter.id)


def test_duplicate_chapter_order_is_rejected(session: Session) -> None:
    admin, _, _ = _tenant(session, "Uno")
    level = _level(session, admin, "A1", 1)
    _curriculum(session, admin, level.id)
    with pytest.raises(CurriculumConflictError):
        CurriculumService(session).create_chapter(
            admin,
            level.id,
            {"name": "Unidad diferente", "description": None, "sort_order": 1},
        )


def test_level_changes_preserve_history(session: Session) -> None:
    admin, branch, _ = _tenant(session, "Uno")
    student = _student(session, admin, branch)
    first = _level(session, admin, "A1", 1)
    second = _level(session, admin, "A2", 2)
    service = AcademicProgressService(session)

    service.assign_level(
        admin, student.id, level_id=first.id, start_date=date(2026, 1, 1)
    )
    service.assign_level(
        admin, student.id, level_id=second.id, start_date=date(2026, 4, 1)
    )
    history = service.get_history(admin, student.id)

    assert len(history) == 2
    assert history[0].level_id == first.id
    assert history[0].end_date == date(2026, 3, 31)
    assert history[0].is_current is False
    assert history[1].level_id == second.id
    assert history[1].is_current is True


def test_admin_records_individual_topic_progress(session: Session) -> None:
    admin, branch, _ = _tenant(session, "Uno")
    student = _student(session, admin, branch)
    level = _level(session, admin, "A1", 1)
    _, topic = _curriculum(session, admin, level.id)
    service = AcademicProgressService(session)
    service.assign_level(
        admin, student.id, level_id=level.id, start_date=date(2026, 1, 1)
    )

    progress = service.update_topic_progress(
        admin,
        student.id,
        topic.id,
        status=TopicProgressStatus.COMPLETED,
        observations="Dominio satisfactorio",
    )

    assert progress.status == TopicProgressStatus.COMPLETED.value
    assert progress.completed_at is not None
    assert progress.updated_by_user_id == admin.id
    _, history, records = service.get_own_academic_progress(student.user)
    assert history[0].level_id == level.id
    assert records[0].topic_id == topic.id


def test_teacher_requires_matching_level_and_branch(session: Session) -> None:
    admin, branch, other_branch = _tenant(session, "Uno")
    student = _student(session, admin, branch)
    level = _level(session, admin, "A1", 1)
    _, topic = _curriculum(session, admin, level.id)
    progress_service = AcademicProgressService(session)
    progress_service.assign_level(
        admin, student.id, level_id=level.id, start_date=date(2026, 1, 1)
    )
    teacher, _ = TeacherService(session).create(
        admin,
        {
            "employee_number": "EMP-001",
            "first_name": "Juan",
            "last_name": "Pérez",
            "email": "juan@test.local",
            "phone": None,
            "hire_date": date(2026, 1, 1),
            "status": TeacherStatus.ACTIVE,
            "administrative_notes": None,
            "branch_ids": [other_branch.id],
            "level_ids": [level.id],
        },
    )

    with pytest.raises(CurriculumAccessError, match="sucursal y nivel"):
        progress_service.update_topic_progress(
            teacher.user,
            student.id,
            topic.id,
            status=TopicProgressStatus.IN_PROGRESS,
            observations=None,
        )

    TeacherService(session).update(
        admin, teacher.id, {"branch_ids": [branch.id]}
    )
    result = progress_service.update_topic_progress(
        teacher.user,
        student.id,
        topic.id,
        status=TopicProgressStatus.NEEDS_REVIEW,
        observations="Repasar vocabulario",
    )
    assert result.status == TopicProgressStatus.NEEDS_REVIEW.value


def test_topic_from_another_level_cannot_update_progress(session: Session) -> None:
    admin, branch, _ = _tenant(session, "Uno")
    student = _student(session, admin, branch)
    current = _level(session, admin, "A1", 1)
    other = _level(session, admin, "A2", 2)
    _, other_topic = _curriculum(session, admin, other.id)
    service = AcademicProgressService(session)
    service.assign_level(
        admin, student.id, level_id=current.id, start_date=date(2026, 1, 1)
    )

    with pytest.raises(CurriculumAccessError, match="nivel actual"):
        service.update_topic_progress(
            admin,
            student.id,
            other_topic.id,
            status=TopicProgressStatus.IN_PROGRESS,
            observations=None,
        )
