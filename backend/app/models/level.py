from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.teacher import TeacherLevelAssignment


class AcademicLevel(TimestampMixin, Base):
    __tablename__ = "academic_levels"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_academic_levels_id_organization"),
        UniqueConstraint("organization_id", "name", name="uq_academic_levels_org_name"),
        UniqueConstraint("organization_id", "sort_order", name="uq_academic_levels_org_order"),
        CheckConstraint(
            "default_capacity IS NULL OR default_capacity > 0",
            name="default_capacity_positive",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer)
    default_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    teacher_assignments: Mapped[list["TeacherLevelAssignment"]] = relationship(
        back_populates="level", cascade="all, delete-orphan"
    )
