from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import StudentStatus

if TYPE_CHECKING:
    from app.models.branch import Branch
    from app.models.user import User


class StudentProfile(TimestampMixin, Base):
    __tablename__ = "student_profiles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_student_profiles_user_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["primary_branch_id", "organization_id"],
            ["branches.id", "branches.organization_id"],
            name="fk_student_profiles_branch_tenant",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("user_id", name="uq_student_profiles_user_id"),
        UniqueConstraint(
            "organization_id", "student_number", name="uq_student_profiles_org_number"
        ),
        CheckConstraint("weekly_hours_limit > 0", name="weekly_hours_positive"),
        CheckConstraint(
            "course_end_date IS NULL OR course_start_date IS NULL "
            "OR course_end_date >= course_start_date",
            name="course_dates_order",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    primary_branch_id: Mapped[int] = mapped_column(Integer, index=True)
    student_number: Mapped[str] = mapped_column(String(40))
    first_name: Mapped[str] = mapped_column(String(80))
    last_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    company: Mapped[str | None] = mapped_column(String(160), nullable=True)
    emergency_contact_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    admission_date: Mapped[date] = mapped_column(Date)
    weekly_hours_limit: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    status: Mapped[str] = mapped_column(String(20), default=StudentStatus.ACTIVE.value, index=True)
    course_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    course_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    can_book_other_branches: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    administrative_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_storage_key: Mapped[str | None] = mapped_column(String(255), nullable=True)

    user: Mapped["User"] = relationship(
        back_populates="student_profile", overlaps="primary_branch,student_profiles"
    )
    primary_branch: Mapped["Branch"] = relationship(
        back_populates="student_profiles", overlaps="student_profile,user"
    )
