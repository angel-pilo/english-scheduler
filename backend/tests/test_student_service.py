from datetime import date
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.base import Base
from app.models.branch import Branch
from app.models.enums import StudentStatus, UserRole
from app.models.org import Organization
from app.models.rbac import Role
from app.models.user import User
from app.services.invitations import InvitationService, InvalidInvitationError
from app.services.students import (
    StudentConflictError,
    StudentError,
    StudentNotFoundError,
    StudentService,
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
                    code=UserRole.STUDENT.value,
                    name="Student",
                    description="Student account",
                ),
            ]
        )
        db.commit()
        yield db


def _tenant_admin(db: Session, suffix: str) -> tuple[User, Branch]:
    organization = Organization(
        name=f"Academia {suffix}", slug=f"academia-{suffix.lower()}"
    )
    branch = Branch(name="Matriz", code="MATRIZ", organization=organization)
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
    return admin, branch


def _student_data(branch_id: int, suffix: str = "001") -> dict[str, object]:
    return {
        "student_number": f"mat-{suffix}",
        "first_name": "Ana",
        "last_name": "LÃ³pez",
        "email": f"ana-{suffix}@test.local",
        "primary_branch_id": branch_id,
        "phone": " 5551234567 ",
        "address": None,
        "company": "English Partners SA",
        "emergency_contact_name": "MarÃ­a LÃ³pez",
        "emergency_contact_phone": "5559876543",
        "admission_date": date(2026, 7, 21),
        "weekly_hours_limit": Decimal("5.50"),
        "status": StudentStatus.ACTIVE,
        "course_start_date": date(2026, 7, 21),
        "course_end_date": date(2026, 12, 18),
        "can_book_other_branches": False,
        "administrative_notes": "Nivel inicial",
    }


def test_create_student_invites_and_activates_account(session: Session) -> None:
    admin, branch = _tenant_admin(session, "Uno")
    student, invitation = StudentService(session).create(admin, _student_data(branch.id))

    assert student.student_number == "MAT-001"
    assert student.organization_id == admin.organization_id
    assert student.user.role == UserRole.STUDENT.value
    assert student.user.active is False
    assert student.phone == "5551234567"
    assert student.company == "English Partners SA"
    assert invitation.activation_url is not None

    token = parse_qs(urlparse(invitation.activation_url).query)["token"][0]
    activated = InvitationService(session).activate(
        token=token,
        password="StudentPassword123!",
        password_confirmation="StudentPassword123!",
    )
    assert activated.active is True
    assert StudentService(session).get_self(activated).id == student.id


def test_student_number_is_unique_within_tenant(session: Session) -> None:
    admin, branch = _tenant_admin(session, "Uno")
    StudentService(session).create(admin, _student_data(branch.id))
    duplicate = _student_data(branch.id, "002")
    duplicate["student_number"] = "mat-001"
    with pytest.raises(StudentConflictError):
        StudentService(session).create(admin, duplicate)


def test_student_access_is_scoped_to_tenant(session: Session) -> None:
    admin, branch = _tenant_admin(session, "Uno")
    other_admin, other_branch = _tenant_admin(session, "Dos")
    student, _ = StudentService(session).create(admin, _student_data(branch.id))

    with pytest.raises(StudentNotFoundError):
        StudentService(session).get(other_admin, student.id)
    invalid = _student_data(other_branch.id, "002")
    with pytest.raises(StudentError, match="Sucursal activa no encontrada"):
        StudentService(session).create(admin, invalid)


def test_admin_status_changes_account_and_self_update_is_limited(session: Session) -> None:
    admin, branch = _tenant_admin(session, "Uno")
    student, invitation = StudentService(session).create(admin, _student_data(branch.id))
    token = parse_qs(urlparse(invitation.activation_url).query)["token"][0]
    user = InvitationService(session).activate(
        token=token,
        password="StudentPassword123!",
        password_confirmation="StudentPassword123!",
    )

    StudentService(session).update_self(
        user, {"phone": " 5550000000 ", "address": " Nueva direcciÃ³n "}
    )
    assert student.phone == "5550000000"
    assert student.address == "Nueva direcciÃ³n"

    StudentService(session).update(
        admin, student.id, {"status": StudentStatus.SUSPENDED}
    )
    assert student.status == StudentStatus.SUSPENDED.value
    assert student.user.active is False


def test_course_end_cannot_precede_start(session: Session) -> None:
    admin, branch = _tenant_admin(session, "Uno")
    invalid = _student_data(branch.id)
    invalid["course_end_date"] = date(2026, 7, 20)
    with pytest.raises(StudentError, match="fecha final"):
        StudentService(session).create(admin, invalid)


def test_inactive_student_cannot_activate_until_reenabled(session: Session) -> None:
    admin, branch = _tenant_admin(session, "Uno")
    data = _student_data(branch.id)
    data["status"] = StudentStatus.SUSPENDED
    student, invitation = StudentService(session).create(admin, data)
    token = parse_qs(urlparse(invitation.activation_url).query)["token"][0]

    with pytest.raises(InvalidInvitationError):
        InvitationService(session).activate(
            token=token,
            password="StudentPassword123!",
            password_confirmation="StudentPassword123!",
        )

    StudentService(session).update(
        admin, student.id, {"status": StudentStatus.ACTIVE}
    )
    activated = InvitationService(session).activate(
        token=token,
        password="StudentPassword123!",
        password_confirmation="StudentPassword123!",
    )
    assert activated.active is True
