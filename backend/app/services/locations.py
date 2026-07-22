from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.room import Room
from app.models.user import User
from app.repositories.locations import BranchRepository, RoomRepository


class LocationError(Exception):
    pass


class LocationNotFoundError(LocationError):
    pass


class LocationConflictError(LocationError):
    pass


class BranchService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.branches = BranchRepository(db)

    def list(self, actor: User, *, include_inactive: bool = False):
        organization_id = self._tenant_id(actor)
        return self.branches.list(organization_id, include_inactive=include_inactive)

    def get(self, actor: User, branch_id: int):
        branch = self.branches.get(self._tenant_id(actor), branch_id)
        if branch is None:
            raise LocationNotFoundError("Sucursal no encontrada")
        return branch

    def create(self, actor: User, *, name: str, code: str, timezone_name: str):
        self._validate_timezone(timezone_name)
        from app.models.branch import Branch

        branch = Branch(
            organization_id=self._tenant_id(actor),
            name=name.strip(),
            code=code.strip().upper(),
            timezone=timezone_name,
            active=True,
        )
        self.db.add(branch)
        self._commit_or_conflict("Ya existe una sucursal con ese nombre o código")
        self.db.refresh(branch)
        return branch

    def update(self, actor: User, branch_id: int, changes: dict[str, object]):
        branch = self.get(actor, branch_id)
        if "timezone" in changes:
            self._validate_timezone(str(changes["timezone"]))
        if "name" in changes:
            changes["name"] = str(changes["name"]).strip()
        if "code" in changes:
            changes["code"] = str(changes["code"]).strip().upper()
        for field, value in changes.items():
            setattr(branch, field, value)
        self._commit_or_conflict("Ya existe una sucursal con ese nombre o código")
        self.db.refresh(branch)
        return branch

    def deactivate(self, actor: User, branch_id: int) -> None:
        branch = self.get(actor, branch_id)
        branch.active = False
        self.db.execute(
            update(Room)
            .where(
                Room.organization_id == branch.organization_id,
                Room.branch_id == branch.id,
            )
            .values(active=False)
        )
        self.db.commit()

    def _commit_or_conflict(self, message: str) -> None:
        try:
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            raise LocationConflictError(message) from error

    @staticmethod
    def _tenant_id(actor: User) -> int:
        if actor.organization_id is None:
            raise LocationError("Esta operación requiere contexto de organización")
        return actor.organization_id

    @staticmethod
    def _validate_timezone(timezone_name: str) -> None:
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as error:
            raise LocationError("Zona horaria inválida") from error


class RoomService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.branches = BranchRepository(db)
        self.rooms = RoomRepository(db)

    def list(
        self,
        actor: User,
        *,
        branch_id: int | None = None,
        include_inactive: bool = False,
    ):
        organization_id = BranchService._tenant_id(actor)
        if branch_id is not None and self.branches.get(organization_id, branch_id) is None:
            raise LocationNotFoundError("Sucursal no encontrada")
        return self.rooms.list(
            organization_id,
            branch_id=branch_id,
            include_inactive=include_inactive,
        )

    def get(self, actor: User, room_id: int):
        room = self.rooms.get(BranchService._tenant_id(actor), room_id)
        if room is None:
            raise LocationNotFoundError("Salón no encontrado")
        return room

    def create(
        self,
        actor: User,
        *,
        branch_id: int,
        name: str,
        code: str,
        capacity: int,
        description: str | None,
    ):
        organization_id = BranchService._tenant_id(actor)
        branch = self.branches.get(organization_id, branch_id)
        if branch is None or not branch.active:
            raise LocationNotFoundError("Sucursal activa no encontrada")
        room = Room(
            organization_id=organization_id,
            branch_id=branch.id,
            name=name.strip(),
            code=code.strip().upper(),
            capacity=capacity,
            description=description.strip() if description else None,
            active=True,
        )
        self.db.add(room)
        self._commit_or_conflict()
        self.db.refresh(room)
        return room

    def update(self, actor: User, room_id: int, changes: dict[str, object]):
        room = self.get(actor, room_id)
        if "branch_id" in changes:
            branch_id = int(changes["branch_id"])
            branch = self.branches.get(room.organization_id, branch_id)
            if branch is None or not branch.active:
                raise LocationNotFoundError("Sucursal activa no encontrada")
        if "name" in changes:
            changes["name"] = str(changes["name"]).strip()
        if "code" in changes:
            changes["code"] = str(changes["code"]).strip().upper()
        if "description" in changes and changes["description"] is not None:
            changes["description"] = str(changes["description"]).strip()
        for field, value in changes.items():
            setattr(room, field, value)
        self._commit_or_conflict()
        self.db.refresh(room)
        return room

    def deactivate(self, actor: User, room_id: int) -> None:
        room = self.get(actor, room_id)
        room.active = False
        self.db.commit()

    def _commit_or_conflict(self) -> None:
        try:
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            raise LocationConflictError("Ya existe un salón con ese nombre o código") from error
