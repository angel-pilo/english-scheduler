from datetime import date, time

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.base import Base
from app.models.branch import Branch
from app.models.enums import (
    ClassSessionStatus,
    ScheduleExceptionScope,
    TeacherStatus,
    UserRole,
)
from app.models.level import AcademicLevel
from app.models.org import Organization
from app.models.rbac import Role
from app.models.room import Room
from app.models.schedule import ScheduleTemplate
from app.models.teacher import (
    TeacherAvailabilityBlock,
    TeacherAvailabilityException,
    TeacherBranchAssignment,
    TeacherLevelAssignment,
    TeacherProfile,
)
from app.models.user import User
from app.schemas.sessions import ClassSessionUpdateIn
from app.services.schedules import ScheduleService
from app.services.session_generation import ClassSessionService, SessionGenerationError


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
                    code=UserRole.TEACHER.value,
                    name="Teacher",
                    description="Teacher account",
                ),
            ]
        )
        db.commit()
        yield db


def _tenant(db: Session):
    organization = Organization(name="Academia Uno", slug="academia-uno")
    branch = Branch(name="Matriz", code="MATRIZ", organization=organization)
    admin = User(
        name="Admin",
        email="admin@test.local",
        hashed_password=hash_password("AdminPassword123!"),
        role=UserRole.ADMIN.value,
        organization=organization,
        branch=branch,
    )
    db.add(admin)
    db.flush()
    room_one = Room(
        organization_id=organization.id,
        branch_id=branch.id,
        name="Salón 1",
        code="S1",
        capacity=8,
    )
    room_two = Room(
        organization_id=organization.id,
        branch_id=branch.id,
        name="Salón 2",
        code="S2",
        capacity=12,
    )
    level = AcademicLevel(
        organization_id=organization.id,
        name="A1",
        sort_order=1,
        default_capacity=10,
        active=True,
    )
    db.add_all([room_one, room_two, level])
    db.commit()
    return admin, branch, room_one, room_two, level


def _teacher(
    db: Session,
    admin: User,
    branch: Branch,
    level: AcademicLevel,
    number: int,
) -> TeacherProfile:
    user = User(
        organization_id=admin.organization_id,
        branch_id=branch.id,
        name=f"Teacher {number}",
        email=f"teacher-{number}@test.local",
        hashed_password="hash",
        role=UserRole.TEACHER.value,
        active=True,
    )
    teacher = TeacherProfile(
        organization_id=admin.organization_id,
        user=user,
        employee_number=f"EMP-{number}",
        first_name="Teacher",
        last_name=str(number),
        hire_date=date(2026, 1, 1),
        status=TeacherStatus.ACTIVE.value,
    )
    db.add(teacher)
    db.flush()
    db.add_all(
        [
            TeacherBranchAssignment(
                teacher_id=teacher.id,
                branch_id=branch.id,
                organization_id=admin.organization_id,
            ),
            TeacherLevelAssignment(
                teacher_id=teacher.id,
                level_id=level.id,
                organization_id=admin.organization_id,
            ),
            TeacherAvailabilityBlock(
                teacher_id=teacher.id,
                organization_id=admin.organization_id,
                weekday=0,
                start_time=time(7),
                end_time=time(13),
            ),
        ]
    )
    db.commit()
    return teacher


def _template_data(branch: Branch, room: Room, level: AcademicLevel, name="Lunes A1"):
    return {
        "name": name,
        "branch_id": branch.id,
        "room_id": room.id,
        "level_id": level.id,
        "weekday": 0,
        "start_time": time(7),
        "end_time": time(8),
        "configured_capacity": 10,
        "effective_from": date(2026, 1, 1),
        "effective_until": None,
        "notes": None,
    }


def test_generate_week_assigns_teacher_and_is_idempotent(session: Session) -> None:
    admin, branch, room, _, level = _tenant(session)
    teacher = _teacher(session, admin, branch, level, 1)
    template = ScheduleService(session).create_template(
        admin, _template_data(branch, room, level)
    )

    generated = ClassSessionService(session).generate_week(
        admin, week_start=date(2026, 8, 3)
    )
    assert len(generated.sessions) == 1
    assert generated.sessions[0].teacher_id == teacher.id
    assert generated.sessions[0].source_template_id == template.id
    assert generated.sessions[0].status == ClassSessionStatus.DRAFT.value
    assert generated.sessions[0].effective_capacity == 8

    repeated = ClassSessionService(session).generate_week(
        admin, week_start=date(2026, 8, 3)
    )
    assert repeated.sessions == []
    assert repeated.existing_count == 1


def test_calendar_exception_blocks_generation(session: Session) -> None:
    admin, branch, room, _, level = _tenant(session)
    _teacher(session, admin, branch, level, 1)
    ScheduleService(session).create_template(
        admin, _template_data(branch, room, level)
    )
    ScheduleService(session).create_exception(
        admin,
        {
            "exception_date": date(2026, 8, 3),
            "scope": ScheduleExceptionScope.ORGANIZATION,
            "branch_id": None,
            "room_id": None,
            "teacher_id": None,
            "start_time": None,
            "end_time": None,
            "reason": "Día festivo",
        },
    )

    result = ClassSessionService(session).generate_week(
        admin, week_start=date(2026, 8, 3)
    )
    assert result.sessions == []
    assert result.blocked_count == 1
    assert "excepción" in result.issues[0].reason


def test_unassigned_session_requires_teacher_before_publish(session: Session) -> None:
    admin, branch, room, _, level = _tenant(session)
    ScheduleService(session).create_template(
        admin, _template_data(branch, room, level)
    )
    service = ClassSessionService(session)
    generated = service.generate_week(admin, week_start=date(2026, 8, 3))
    item = generated.sessions[0]
    assert item.teacher_id is None
    with pytest.raises(SessionGenerationError, match="requiere profesor"):
        service.update(
            admin, item.id, {"status": ClassSessionStatus.PUBLISHED}
        )

    teacher = _teacher(session, admin, branch, level, 1)
    published = service.update(
        admin,
        item.id,
        {"teacher_id": teacher.id, "status": ClassSessionStatus.PUBLISHED},
    )
    assert published.teacher_id == teacher.id
    assert published.status == ClassSessionStatus.PUBLISHED.value


def test_teacher_exception_overrides_recurring_availability(session: Session) -> None:
    admin, branch, room, _, level = _tenant(session)
    teacher = _teacher(session, admin, branch, level, 1)
    teacher.availability_exceptions.append(
        TeacherAvailabilityException(
            organization_id=admin.organization_id,
            exception_date=date(2026, 8, 3),
            is_available=False,
        )
    )
    session.commit()
    ScheduleService(session).create_template(
        admin, _template_data(branch, room, level)
    )

    result = ClassSessionService(session).generate_week(
        admin, week_start=date(2026, 8, 3)
    )
    assert result.sessions[0].teacher_id is None
    assert result.issues[0].reason == "Sin profesor disponible"


def test_simultaneous_sessions_use_different_teachers(session: Session) -> None:
    admin, branch, room_one, room_two, level = _tenant(session)
    first_teacher = _teacher(session, admin, branch, level, 1)
    second_teacher = _teacher(session, admin, branch, level, 2)
    ScheduleService(session).create_template(
        admin, _template_data(branch, room_one, level, "Grupo 1")
    )
    ScheduleService(session).create_template(
        admin, _template_data(branch, room_two, level, "Grupo 2")
    )

    result = ClassSessionService(session).generate_week(
        admin, week_start=date(2026, 8, 3)
    )
    assert {item.teacher_id for item in result.sessions} == {
        first_teacher.id,
        second_teacher.id,
    }


def test_generation_blocks_room_conflicts(session: Session) -> None:
    admin, branch, room, _, level = _tenant(session)
    _teacher(session, admin, branch, level, 1)
    ScheduleService(session).create_template(
        admin, _template_data(branch, room, level, "Grupo original")
    )
    service = ClassSessionService(session)
    first_result = service.generate_week(admin, week_start=date(2026, 8, 3))
    assert len(first_result.sessions) == 1

    overlapping = ScheduleTemplate(
        organization_id=admin.organization_id,
        branch_id=branch.id,
        room_id=room.id,
        level_id=level.id,
        name="Grupo superpuesto",
        weekday=0,
        start_time=time(7, 30),
        end_time=time(8, 30),
        configured_capacity=8,
        effective_from=date(2026, 1, 1),
        effective_until=None,
        active=True,
        notes=None,
        created_by_user_id=admin.id,
        updated_by_user_id=admin.id,
    )
    session.add(overlapping)
    session.commit()

    repeated = service.generate_week(admin, week_start=date(2026, 8, 3))
    assert repeated.existing_count == 1
    assert repeated.blocked_count == 1
    assert repeated.sessions == []
    assert repeated.issues[0].reason == "Conflicto de salón"


def test_week_must_start_on_monday(session: Session) -> None:
    admin, _, _, _, _ = _tenant(session)
    with pytest.raises(SessionGenerationError, match="lunes"):
        ClassSessionService(session).generate_week(
            admin, week_start=date(2026, 8, 4)
        )


@pytest.mark.parametrize(
    "field",
    ["room_id", "configured_capacity", "title", "status"],
)
def test_update_rejects_null_required_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        ClassSessionUpdateIn.model_validate({field: None})
