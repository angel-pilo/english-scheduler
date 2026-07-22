from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.room import Room


class BranchRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self, organization_id: int, *, include_inactive: bool = False) -> list[Branch]:
        statement = select(Branch).where(Branch.organization_id == organization_id)
        if not include_inactive:
            statement = statement.where(Branch.active.is_(True))
        return list(self.db.scalars(statement.order_by(Branch.name)))

    def get(self, organization_id: int, branch_id: int) -> Branch | None:
        return self.db.scalar(
            select(Branch).where(
                Branch.id == branch_id,
                Branch.organization_id == organization_id,
            )
        )


class RoomRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(
        self,
        organization_id: int,
        *,
        branch_id: int | None = None,
        include_inactive: bool = False,
    ) -> list[Room]:
        statement = select(Room).where(Room.organization_id == organization_id)
        if branch_id is not None:
            statement = statement.where(Room.branch_id == branch_id)
        if not include_inactive:
            statement = statement.where(Room.active.is_(True))
        return list(self.db.scalars(statement.order_by(Room.name)))

    def get(self, organization_id: int, room_id: int) -> Room | None:
        return self.db.scalar(
            select(Room).where(
                Room.id == room_id,
                Room.organization_id == organization_id,
            )
        )
