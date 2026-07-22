import sqlite3

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.branch import Branch
from app.models.enums import UserRole
from app.models.org import Organization
from app.models.rbac import Role
from app.models.room import Room
from app.models.user import User
from app.services.locations import (
    BranchService,
    LocationConflictError,
    LocationError,
    LocationNotFoundError,
    RoomService,
)


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection: sqlite3.Connection, _: object) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


def _tenant_admin(db: Session, suffix: str) -> tuple[User, Branch]:
    if db.get(Role, UserRole.ADMIN.value) is None:
        db.add(
            Role(
                code=UserRole.ADMIN.value,
                name="Administrator",
                description="Organization administrator",
            )
        )
        db.flush()
    organization = Organization(name=f"Academia {suffix}", slug=f"academia-{suffix.lower()}")
    branch = Branch(name="Matriz", code="MATRIZ", organization=organization)
    admin = User(
        name="Admin",
        email=f"admin-{suffix}@test.local",
        hashed_password="hash",
        role=UserRole.ADMIN.value,
        organization=organization,
        branch=branch,
    )
    db.add(admin)
    db.commit()
    return admin, branch


def test_branch_crud_is_scoped_to_tenant(session: Session) -> None:
    admin, _ = _tenant_admin(session, "One")
    other_admin, _ = _tenant_admin(session, "Two")

    branch = BranchService(session).create(
        admin,
        name="Norte",
        code="norte",
        timezone_name="America/Mexico_City",
    )
    assert branch.code == "NORTE"
    assert [item.id for item in BranchService(session).list(admin)] == [1, branch.id]
    with pytest.raises(LocationNotFoundError):
        BranchService(session).get(other_admin, branch.id)

    BranchService(session).update(admin, branch.id, {"name": "Norte Renovada"})
    assert branch.name == "Norte Renovada"
    BranchService(session).deactivate(admin, branch.id)
    assert branch not in BranchService(session).list(admin)


def test_branch_validates_timezone_and_duplicates(session: Session) -> None:
    admin, _ = _tenant_admin(session, "One")
    with pytest.raises(LocationError, match="Zona horaria inválida"):
        BranchService(session).create(
            admin,
            name="Norte",
            code="NORTE",
            timezone_name="Invalid/Timezone",
        )
    BranchService(session).create(
        admin,
        name="Norte",
        code="NORTE",
        timezone_name="America/Mexico_City",
    )
    with pytest.raises(LocationConflictError):
        BranchService(session).create(
            admin,
            name="Norte 2",
            code="NORTE",
            timezone_name="America/Mexico_City",
        )


def test_room_crud_and_branch_deactivation(session: Session) -> None:
    admin, branch = _tenant_admin(session, "One")
    room = RoomService(session).create(
        admin,
        branch_id=branch.id,
        name="Aula multimedia",
        code="multi",
        capacity=12,
        description="Proyector",
    )
    assert room.code == "MULTI"
    assert RoomService(session).get(admin, room.id) is room

    RoomService(session).update(admin, room.id, {"capacity": 16})
    assert room.capacity == 16
    BranchService(session).deactivate(admin, branch.id)
    session.refresh(room)
    assert room.active is False


def test_room_cannot_reference_branch_from_another_tenant(session: Session) -> None:
    admin, _ = _tenant_admin(session, "One")
    other_admin, other_branch = _tenant_admin(session, "Two")

    with pytest.raises(LocationNotFoundError):
        RoomService(session).create(
            admin,
            branch_id=other_branch.id,
            name="Aula 1",
            code="A1",
            capacity=10,
            description=None,
        )

    session.add(
        Room(
            organization_id=admin.organization_id,
            branch_id=other_branch.id,
            name="Invalid room",
            code="INVALID",
            capacity=10,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    assert RoomService(session).list(other_admin) == []
