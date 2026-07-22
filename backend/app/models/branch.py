from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.org import Organization
    from app.models.room import Room
    from app.models.user import User


class Branch(TimestampMixin, Base):
    __tablename__ = "branches"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_branches_organization_name"),
        UniqueConstraint("organization_id", "code", name="uq_branches_organization_code"),
        UniqueConstraint("id", "organization_id", name="uq_branches_id_organization"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    code: Mapped[str] = mapped_column(String(30))
    timezone: Mapped[str] = mapped_column(String(64), default="America/Mexico_City")
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    organization: Mapped["Organization"] = relationship(back_populates="branches")
    users: Mapped[list["User"]] = relationship(back_populates="branch")
    rooms: Mapped[list["Room"]] = relationship(
        back_populates="branch", cascade="all, delete-orphan"
    )
