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
from app.models.enums import ScheduleExceptionScope

if TYPE_CHECKING:
    from app.models.branch import Branch
    from app.models.level import AcademicLevel
    from app.models.room import Room
    from app.models.teacher import TeacherProfile
    from app.models.user import User


class ScheduleTemplate(TimestampMixin, Base):
    __tablename__ = "schedule_templates"
    __table_args__ = (
        ForeignKeyConstraint(
            ["branch_id", "organization_id"],
            ["branches.id", "branches.organization_id"],
            name="fk_schedule_templates_branch_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["room_id", "branch_id", "organization_id"],
            ["rooms.id", "rooms.branch_id", "rooms.organization_id"],
            name="fk_schedule_templates_room_branch_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["level_id", "organization_id"],
            ["academic_levels.id", "academic_levels.organization_id"],
            name="fk_schedule_templates_level_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["created_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_schedule_templates_creator_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["updated_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_schedule_templates_updater_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint("weekday >= 0 AND weekday <= 6", name="weekday_range"),
        CheckConstraint("end_time > start_time", name="time_order"),
        CheckConstraint(
            "configured_capacity IS NULL OR configured_capacity > 0",
            name="configured_capacity_positive",
        ),
        CheckConstraint(
            "effective_until IS NULL OR effective_until >= effective_from",
            name="effective_dates_order",
        ),
        UniqueConstraint("id", "organization_id", name="uq_schedule_templates_id_org"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, index=True)
    branch_id: Mapped[int] = mapped_column(Integer, index=True)
    room_id: Mapped[int] = mapped_column(Integer, index=True)
    level_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(160))
    weekday: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    configured_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int] = mapped_column(Integer)
    updated_by_user_id: Mapped[int] = mapped_column(Integer)

    branch: Mapped["Branch"] = relationship(overlaps="room")
    room: Mapped["Room"] = relationship(overlaps="branch")
    level: Mapped["AcademicLevel"] = relationship(overlaps="branch,room")
    created_by: Mapped["User"] = relationship(
        foreign_keys=[created_by_user_id], overlaps="updated_by"
    )
    updated_by: Mapped["User"] = relationship(
        foreign_keys=[updated_by_user_id], overlaps="created_by"
    )


class ScheduleException(TimestampMixin, Base):
    __tablename__ = "schedule_exceptions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["branch_id", "organization_id"],
            ["branches.id", "branches.organization_id"],
            name="fk_schedule_exceptions_branch_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["room_id", "branch_id", "organization_id"],
            ["rooms.id", "rooms.branch_id", "rooms.organization_id"],
            name="fk_schedule_exceptions_room_branch_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["teacher_id", "organization_id"],
            ["teacher_profiles.id", "teacher_profiles.organization_id"],
            name="fk_schedule_exceptions_teacher_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["created_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_schedule_exceptions_creator_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["updated_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_schedule_exceptions_updater_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(start_time IS NULL AND end_time IS NULL) OR "
            "(start_time IS NOT NULL AND end_time IS NOT NULL AND end_time > start_time)",
            name="time_shape",
        ),
        CheckConstraint(
            "(scope = 'ORGANIZATION' AND branch_id IS NULL AND room_id IS NULL AND teacher_id IS NULL) OR "
            "(scope = 'BRANCH' AND branch_id IS NOT NULL AND room_id IS NULL AND teacher_id IS NULL) OR "
            "(scope = 'ROOM' AND branch_id IS NOT NULL AND room_id IS NOT NULL AND teacher_id IS NULL) OR "
            "(scope = 'TEACHER' AND branch_id IS NULL AND room_id IS NULL AND teacher_id IS NOT NULL)",
            name="scope_shape",
        ),
        UniqueConstraint("id", "organization_id", name="uq_schedule_exceptions_id_org"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, index=True)
    exception_date: Mapped[date] = mapped_column(Date, index=True)
    scope: Mapped[str] = mapped_column(
        String(20), default=ScheduleExceptionScope.ORGANIZATION.value, index=True
    )
    branch_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    room_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    teacher_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    reason: Mapped[str] = mapped_column(String(500))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_by_user_id: Mapped[int] = mapped_column(Integer)
    updated_by_user_id: Mapped[int] = mapped_column(Integer)

    branch: Mapped["Branch | None"] = relationship(overlaps="room")
    room: Mapped["Room | None"] = relationship(overlaps="branch")
    teacher: Mapped["TeacherProfile | None"] = relationship(overlaps="branch,room")
    created_by: Mapped["User"] = relationship(
        foreign_keys=[created_by_user_id], overlaps="updated_by"
    )
    updated_by: Mapped["User"] = relationship(
        foreign_keys=[updated_by_user_id], overlaps="created_by"
    )
