from datetime import date, time

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.base import Base
from app.models.branch import Branch
from app.models.enums import ScheduleExceptionScope, TeacherStatus, UserRole
from app.models.level import AcademicLevel
from app.models.org import Organization
from app.models.rbac import Role
from app.models.room import Room
from app.models.teacher import TeacherProfile
from app.models.user import User
from app.services.schedules import (
    ScheduleConflictError,
    ScheduleError,
    ScheduleNotFoundError,
    ScheduleService,
)


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


def _tenant(db: Session, suffix: str):
    organization = Organization(
        name=f"Academia {suffix}", slug=f"academia-{suffix.lower()}"
    )
    branch = Branch(name="Matriz", code="MATRIZ", organization=organization)
    second_branch = Branch(name="Norte", code="NORTE", organization=organization)
    admin = User(
        name="Admin",
        email=f"admin-{suffix.lower()}@test.local",
        hashed_password=hash_password("AdminPassword123!"),
        role=UserRole.ADMIN.value,
        organization=organization,
        branch=branch,
    )
    db.add(admin)
    db.flush()
    room = Room(
        name="Salón 1",
        code="S1",
        capacity=6,
        branch_id=branch.id,
        organization_id=organization.id,
    )
    second_room = Room(
        name="Salón 2",
        code="S2",
        capacity=12,
        branch_id=second_branch.id,
        organization_id=organization.id,
    )
    level = AcademicLevel(
        organization_id=organization.id,
        name="A1",
        description=None,
        sort_order=1,
        default_capacity=8,
        active=True,
    )
    db.add_all([room, second_room, level])
    db.commit()
    return admin, branch, room, second_branch, second_room, level


def _template_data(branch: Branch, room: Room, level: AcademicLevel):
    return {
        "name": "Lunes A1",
        "branch_id": branch.id,
        "room_id": room.id,
        "level_id": level.id,
        "weekday": 0,
        "start_time": time(7),
        "end_time": time(8),
        "configured_capacity": 10,
        "effective_from": date(2026, 8, 1),
        "effective_until": None,
        "notes": None,
    }


def test_template_effective_capacity_uses_smallest_limit(session: Session) -> None:
    admin, branch, room, _, _, level = _tenant(session, "Uno")
    template = ScheduleService(session).create_template(
        admin, _template_data(branch, room, level)
    )

    assert ScheduleService.effective_capacity(template) == 6
    assert template.created_by_user_id == admin.id
    assert ScheduleService(session).list_templates(admin)[0].id == template.id


def test_room_overlap_is_rejected_only_when_date_ranges_overlap(session: Session) -> None:
    admin, branch, room, _, _, level = _tenant(session, "Uno")
    service = ScheduleService(session)
    first_data = _template_data(branch, room, level)
    first_data["effective_until"] = date(2026, 12, 31)
    service.create_template(admin, first_data)

    overlapping = _template_data(branch, room, level)
    overlapping["start_time"] = time(7, 30)
    overlapping["end_time"] = time(8, 30)
    with pytest.raises(ScheduleConflictError, match="salón"):
        service.create_template(admin, overlapping)

    future = dict(overlapping)
    future["effective_from"] = date(2027, 1, 1)
    assert service.create_template(admin, future).id is not None


def test_template_rejects_room_from_different_branch_and_tenant(session: Session) -> None:
    admin, branch, room, _, second_room, level = _tenant(session, "Uno")
    other_admin, _, _, _, _, _ = _tenant(session, "Dos")
    invalid = _template_data(branch, second_room, level)
    with pytest.raises(ScheduleError, match="salón"):
        ScheduleService(session).create_template(admin, invalid)

    template = ScheduleService(session).create_template(
        admin, _template_data(branch, room, level)
    )
    with pytest.raises(ScheduleNotFoundError):
        ScheduleService(session).get_template(other_admin, template.id)


def test_calendar_exception_shapes_and_overlap(session: Session) -> None:
    admin, branch, room, _, _, _ = _tenant(session, "Uno")
    service = ScheduleService(session)
    full_day = service.create_exception(
        admin,
        {
            "exception_date": date(2026, 12, 25),
            "scope": ScheduleExceptionScope.ORGANIZATION,
            "branch_id": branch.id,
            "room_id": room.id,
            "teacher_id": None,
            "start_time": None,
            "end_time": None,
            "reason": "Sucursal cerrada",
        },
    )
    assert full_day.branch_id is None
    with pytest.raises(ScheduleConflictError):
        service.create_exception(
            admin,
            {
                "exception_date": date(2026, 12, 25),
                "scope": ScheduleExceptionScope.ORGANIZATION,
                "branch_id": None,
                "room_id": None,
                "teacher_id": None,
                "start_time": time(8),
                "end_time": time(10),
                "reason": "Otro bloqueo",
            },
        )
    branch_exception = service.create_exception(
        admin,
        {
            "exception_date": date(2026, 12, 25),
            "scope": ScheduleExceptionScope.BRANCH,
            "branch_id": branch.id,
            "room_id": None,
            "teacher_id": None,
            "start_time": time(8),
            "end_time": time(10),
            "reason": "Mantenimiento",
        },
    )
    assert branch_exception.id is not None


def test_room_and_teacher_exceptions_are_tenant_safe(session: Session) -> None:
    admin, branch, room, second_branch, _, _ = _tenant(session, "Uno")
    teacher_user = User(
        name="Teacher",
        email="teacher@test.local",
        role=UserRole.TEACHER.value,
        organization_id=admin.organization_id,
        branch_id=branch.id,
        hashed_password="hash",
        active=True,
    )
    teacher = TeacherProfile(
        organization_id=admin.organization_id,
        user=teacher_user,
        employee_number="EMP-1",
        first_name="Juan",
        last_name="Pérez",
        hire_date=date(2026, 1, 1),
        status=TeacherStatus.ACTIVE.value,
    )
    session.add(teacher)
    session.commit()

    with pytest.raises(ScheduleError, match="Salón"):
        ScheduleService(session).create_exception(
            admin,
            {
                "exception_date": date(2026, 9, 1),
                "scope": ScheduleExceptionScope.ROOM,
                "branch_id": second_branch.id,
                "room_id": room.id,
                "teacher_id": None,
                "start_time": None,
                "end_time": None,
                "reason": "Cierre",
            },
        )
    teacher_exception = ScheduleService(session).create_exception(
        admin,
        {
            "exception_date": date(2026, 9, 1),
            "scope": ScheduleExceptionScope.TEACHER,
            "branch_id": branch.id,
            "room_id": room.id,
            "teacher_id": teacher.id,
            "start_time": time(7),
            "end_time": time(9),
            "reason": "Permiso",
        },
    )
    assert teacher_exception.branch_id is None
    assert teacher_exception.room_id is None
    assert teacher_exception.teacher_id == teacher.id


def test_deactivation_is_logical_and_audited(session: Session) -> None:
    admin, branch, room, _, _, level = _tenant(session, "Uno")
    service = ScheduleService(session)
    template = service.create_template(admin, _template_data(branch, room, level))
    service.deactivate_template(admin, template.id)
    assert service.get_template(admin, template.id).active is False
    assert service.list_templates(admin) == []
    assert service.list_templates(admin, include_inactive=True)[0].id == template.id


def test_matching_exceptions_take_scope_and_time_into_account(session: Session) -> None:
    admin, branch, room, second_branch, _, _ = _tenant(session, "Uno")
    service = ScheduleService(session)
    service.create_exception(
        admin,
        {
            "exception_date": date(2026, 12, 25),
            "scope": ScheduleExceptionScope.BRANCH,
            "branch_id": branch.id,
            "room_id": None,
            "teacher_id": None,
            "start_time": time(7),
            "end_time": time(10),
            "reason": "Cierre matutino",
        },
    )
    matches = service.matching_exceptions(
        admin,
        target_date=date(2026, 12, 25),
        branch_id=branch.id,
        room_id=room.id,
        teacher_id=None,
        start_time=time(8),
        end_time=time(9),
    )
    assert len(matches) == 1
    assert service.matching_exceptions(
        admin,
        target_date=date(2026, 12, 25),
        branch_id=second_branch.id,
        room_id=room.id,
        teacher_id=None,
        start_time=time(8),
        end_time=time(9),
    ) == []
