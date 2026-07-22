from datetime import date, time
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import TeacherStatus

if TYPE_CHECKING:
    from app.models.branch import Branch
    from app.models.level import AcademicLevel
    from app.models.user import User


class TeacherProfile(TimestampMixin, Base):
    __tablename__ = "teacher_profiles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_teacher_profiles_user_tenant",
            ondelete="CASCADE",
        ),
        UniqueConstraint("id", "organization_id", name="uq_teacher_profiles_id_organization"),
        UniqueConstraint("user_id", name="uq_teacher_profiles_user_id"),
        UniqueConstraint(
            "organization_id", "employee_number", name="uq_teacher_profiles_org_number"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    employee_number: Mapped[str] = mapped_column(String(40))
    first_name: Mapped[str] = mapped_column(String(80))
    last_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    hire_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        String(20), default=TeacherStatus.ACTIVE.value, index=True
    )
    administrative_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_storage_key: Mapped[str | None] = mapped_column(String(255), nullable=True)

    user: Mapped["User"] = relationship(
        back_populates="teacher_profile",
        overlaps="branch,branch_assignments,teacher_assignments,level",
    )
    branch_assignments: Mapped[list["TeacherBranchAssignment"]] = relationship(
        back_populates="teacher", cascade="all, delete-orphan"
    )
    level_assignments: Mapped[list["TeacherLevelAssignment"]] = relationship(
        back_populates="teacher",
        cascade="all, delete-orphan",
        overlaps="level,teacher_assignments",
    )
    recurring_availability: Mapped[list["TeacherAvailabilityBlock"]] = relationship(
        back_populates="teacher", cascade="all, delete-orphan"
    )
    availability_exceptions: Mapped[list["TeacherAvailabilityException"]] = relationship(
        back_populates="teacher", cascade="all, delete-orphan"
    )


class TeacherBranchAssignment(Base):
    __tablename__ = "teacher_branch_assignments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["teacher_id", "organization_id"],
            ["teacher_profiles.id", "teacher_profiles.organization_id"],
            name="fk_teacher_branches_teacher_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["branch_id", "organization_id"],
            ["branches.id", "branches.organization_id"],
            name="fk_teacher_branches_branch_tenant",
            ondelete="RESTRICT",
        ),
    )

    teacher_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    branch_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, index=True)

    teacher: Mapped["TeacherProfile"] = relationship(
        back_populates="branch_assignments", overlaps="branch"
    )
    branch: Mapped["Branch"] = relationship(overlaps="branch_assignments,teacher")


class TeacherLevelAssignment(Base):
    __tablename__ = "teacher_level_assignments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["teacher_id", "organization_id"],
            ["teacher_profiles.id", "teacher_profiles.organization_id"],
            name="fk_teacher_levels_teacher_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["level_id", "organization_id"],
            ["academic_levels.id", "academic_levels.organization_id"],
            name="fk_teacher_levels_level_tenant",
            ondelete="RESTRICT",
        ),
    )

    teacher_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    level_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, index=True)

    teacher: Mapped["TeacherProfile"] = relationship(
        back_populates="level_assignments", overlaps="level,teacher_assignments"
    )
    level: Mapped["AcademicLevel"] = relationship(
        back_populates="teacher_assignments", overlaps="teacher,level_assignments"
    )


class TeacherAvailabilityBlock(Base):
    __tablename__ = "teacher_availability_blocks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["teacher_id", "organization_id"],
            ["teacher_profiles.id", "teacher_profiles.organization_id"],
            name="fk_teacher_availability_teacher_tenant",
            ondelete="CASCADE",
        ),
        CheckConstraint("weekday >= 0 AND weekday <= 6", name="weekday_range"),
        CheckConstraint("end_time > start_time", name="time_order"),
        UniqueConstraint(
            "teacher_id", "weekday", "start_time", "end_time", name="uq_teacher_availability_block"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, index=True)
    teacher_id: Mapped[int] = mapped_column(Integer, index=True)
    weekday: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)

    teacher: Mapped["TeacherProfile"] = relationship(
        back_populates="recurring_availability"
    )


class TeacherAvailabilityException(Base):
    __tablename__ = "teacher_availability_exceptions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["teacher_id", "organization_id"],
            ["teacher_profiles.id", "teacher_profiles.organization_id"],
            name="fk_teacher_exceptions_teacher_tenant",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "(is_available = false AND start_time IS NULL AND end_time IS NULL) OR "
            "(is_available = true AND start_time IS NOT NULL AND end_time IS NOT NULL "
            "AND end_time > start_time)",
            name="availability_shape",
        ),
        UniqueConstraint("teacher_id", "exception_date", name="uq_teacher_exception_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, index=True)
    teacher_id: Mapped[int] = mapped_column(Integer, index=True)
    exception_date: Mapped[date] = mapped_column(Date)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)

    teacher: Mapped["TeacherProfile"] = relationship(
        back_populates="availability_exceptions"
    )
