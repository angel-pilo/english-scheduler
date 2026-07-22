from datetime import date, time
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.base import Base
from app.models.branch import Branch
from app.models.enums import TeacherStatus, UserRole
from app.models.org import Organization
from app.models.rbac import Role
from app.models.user import User
from app.services.invitations import InvitationService, InvalidInvitationError
from app.services.teachers import (
    LevelService,
    TeacherConflictError,
    TeacherError,
    TeacherNotFoundError,
    TeacherService,
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


def _tenant(session: Session, suffix: str) -> tuple[User, Branch, Branch]:
    organization = Organization(
        name=f"Academia {suffix}", slug=f"academia-{suffix.lower()}"
    )
    branch = Branch(name="Matriz", code="MATRIZ", organization=organization)
    second = Branch(name="Norte", code="NORTE", organization=organization)
    admin = User(
        name="Admin",
        email=f"admin-{suffix.lower()}@test.local",
        hashed_password=hash_password("AdminPassword123!"),
        role=UserRole.ADMIN.value,
        organization=organization,
        branch=branch,
    )
    session.add(admin)
    session.commit()
    return admin, branch, second


def _teacher_data(branch_ids: list[int], level_ids: list[int]) -> dict[str, object]:
    return {
        "employee_number": "emp-001",
        "first_name": "Juan",
        "last_name": "PÃ©rez",
        "email": "juan@test.local",
        "phone": " 5551234567 ",
        "hire_date": date(2026, 7, 22),
        "status": TeacherStatus.ACTIVE,
        "administrative_notes": "Profesor titular",
        "branch_ids": branch_ids,
        "level_ids": level_ids,
    }


def test_create_teacher_assigns_branches_levels_and_invitation(session: Session) -> None:
    admin, branch, second = _tenant(session, "Uno")
    level = LevelService(session).create(
        admin,
        {"name": "BÃ¡sico 1", "description": None, "sort_order": 1, "default_capacity": 8},
    )

    teacher, invitation = TeacherService(session).create(
        admin, _teacher_data([branch.id, second.id], [level.id])
    )

    assert teacher.employee_number == "EMP-001"
    assert {item.branch_id for item in teacher.branch_assignments} == {branch.id, second.id}
    assert [item.level_id for item in teacher.level_assignments] == [level.id]
    assert teacher.user.active is False
    token = parse_qs(urlparse(invitation.activation_url).query)["token"][0]
    activated = InvitationService(session).activate(
        token=token,
        password="TeacherPassword123!",
        password_confirmation="TeacherPassword123!",
    )
    assert activated.active is True
    assert TeacherService(session).get_self(activated).id == teacher.id


def test_teacher_assignments_are_tenant_scoped(session: Session) -> None:
    admin, branch, _ = _tenant(session, "Uno")
    other_admin, other_branch, _ = _tenant(session, "Dos")
    other_level = LevelService(session).create(
        other_admin,
        {"name": "A1", "description": None, "sort_order": 1, "default_capacity": None},
    )

    with pytest.raises(TeacherError, match="sucursales"):
        TeacherService(session).create(
            admin, _teacher_data([branch.id, other_branch.id], [])
        )
    with pytest.raises(TeacherError, match="niveles"):
        TeacherService(session).create(
            admin, _teacher_data([branch.id], [other_level.id])
        )


def test_teacher_is_hidden_from_other_tenant(session: Session) -> None:
    admin, branch, _ = _tenant(session, "Uno")
    other_admin, _, _ = _tenant(session, "Dos")
    teacher, _ = TeacherService(session).create(
        admin, _teacher_data([branch.id], [])
    )
    with pytest.raises(TeacherNotFoundError):
        TeacherService(session).get(other_admin, teacher.id)


def test_availability_supports_multiple_blocks_and_exceptions(session: Session) -> None:
    admin, branch, _ = _tenant(session, "Uno")
    teacher, _ = TeacherService(session).create(
        admin, _teacher_data([branch.id], [])
    )
    updated = TeacherService(session).replace_availability(
        teacher,
        [
            {"weekday": 0, "start_time": time(7), "end_time": time(13)},
            {"weekday": 0, "start_time": time(16), "end_time": time(20)},
            {"weekday": 2, "start_time": time(7), "end_time": time(15)},
        ],
        [
            {
                "exception_date": date(2026, 8, 15),
                "is_available": False,
                "start_time": None,
                "end_time": None,
            }
        ],
    )
    assert len(updated.recurring_availability) == 3
    assert updated.availability_exceptions[0].is_available is False

    with pytest.raises(TeacherConflictError, match="traslaparse"):
        TeacherService(session).replace_availability(
            updated,
            [
                {"weekday": 1, "start_time": time(8), "end_time": time(12)},
                {"weekday": 1, "start_time": time(11), "end_time": time(14)},
            ],
            [],
        )


def test_suspended_teacher_cannot_activate_until_reenabled(session: Session) -> None:
    admin, branch, _ = _tenant(session, "Uno")
    data = _teacher_data([branch.id], [])
    data["status"] = TeacherStatus.SUSPENDED
    teacher, invitation = TeacherService(session).create(admin, data)
    token = parse_qs(urlparse(invitation.activation_url).query)["token"][0]

    with pytest.raises(InvalidInvitationError):
        InvitationService(session).activate(
            token=token,
            password="TeacherPassword123!",
            password_confirmation="TeacherPassword123!",
        )
    TeacherService(session).update(
        admin, teacher.id, {"status": TeacherStatus.ACTIVE}
    )
    activated = InvitationService(session).activate(
        token=token,
        password="TeacherPassword123!",
        password_confirmation="TeacherPassword123!",
    )
    assert activated.active is True


def test_employee_number_and_level_order_are_unique_per_tenant(session: Session) -> None:
    admin, branch, _ = _tenant(session, "Uno")
    LevelService(session).create(
        admin,
        {"name": "A1", "description": None, "sort_order": 1, "default_capacity": None},
    )
    with pytest.raises(TeacherConflictError):
        LevelService(session).create(
            admin,
            {"name": "A2", "description": None, "sort_order": 1, "default_capacity": None},
        )

    TeacherService(session).create(admin, _teacher_data([branch.id], []))
    duplicate = _teacher_data([branch.id], [])
    duplicate["email"] = "other@test.local"
    with pytest.raises(TeacherConflictError):
        TeacherService(session).create(admin, duplicate)
