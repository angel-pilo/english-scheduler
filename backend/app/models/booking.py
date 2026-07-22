from datetime import datetime, time
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import BookingStatus

if TYPE_CHECKING:
    from app.models.branch import Branch
    from app.models.schedule import ClassSession
    from app.models.student import StudentProfile
    from app.models.user import User


class BookingPolicy(TimestampMixin, Base):
    __tablename__ = "booking_policies"
    __table_args__ = (
        ForeignKeyConstraint(
            ["branch_id", "organization_id"],
            ["branches.id", "branches.organization_id"],
            name="fk_booking_policies_branch_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["created_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_booking_policies_creator_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["updated_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_booking_policies_updater_tenant",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "organization_id", name="uq_booking_policies_id_org"),
        UniqueConstraint(
            "organization_id", "branch_id", name="uq_booking_policies_org_branch"
        ),
        Index(
            "uq_booking_policies_org_default",
            "organization_id",
            unique=True,
            postgresql_where=text("branch_id IS NULL"),
            sqlite_where=text("branch_id IS NULL"),
        ),
        CheckConstraint(
            "minimum_booking_notice_hours >= 0",
            name="minimum_booking_notice_nonnegative",
        ),
        CheckConstraint(
            "minimum_cancellation_notice_hours >= 0",
            name="minimum_cancellation_notice_nonnegative",
        ),
        CheckConstraint(
            "earliest_booking_week_offset >= 0",
            name="earliest_week_offset_nonnegative",
        ),
        CheckConstraint(
            "latest_booking_week_offset >= earliest_booking_week_offset",
            name="booking_week_offsets_order",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, index=True)
    branch_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    minimum_booking_notice_hours: Mapped[int] = mapped_column(Integer, default=24)
    minimum_cancellation_notice_hours: Mapped[int] = mapped_column(Integer, default=24)
    earliest_booking_week_offset: Mapped[int] = mapped_column(Integer, default=1)
    latest_booking_week_offset: Mapped[int] = mapped_column(Integer, default=1)
    created_by_user_id: Mapped[int] = mapped_column(Integer)
    updated_by_user_id: Mapped[int] = mapped_column(Integer)

    branch: Mapped["Branch | None"] = relationship()
    time_blocks: Mapped[list["BookingPolicyTimeBlock"]] = relationship(
        back_populates="policy",
        cascade="all, delete-orphan",
        order_by="BookingPolicyTimeBlock.weekday, BookingPolicyTimeBlock.start_time",
    )
    created_by: Mapped["User"] = relationship(
        foreign_keys=[created_by_user_id], overlaps="updated_by"
    )
    updated_by: Mapped["User"] = relationship(
        foreign_keys=[updated_by_user_id], overlaps="created_by"
    )


class BookingPolicyTimeBlock(Base):
    __tablename__ = "booking_policy_time_blocks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["policy_id", "organization_id"],
            ["booking_policies.id", "booking_policies.organization_id"],
            name="fk_booking_policy_blocks_policy_tenant",
            ondelete="CASCADE",
        ),
        CheckConstraint("weekday >= 0 AND weekday <= 6", name="weekday_range"),
        CheckConstraint("end_time > start_time", name="time_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, index=True)
    policy_id: Mapped[int] = mapped_column(Integer, index=True)
    weekday: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[time]
    end_time: Mapped[time]

    policy: Mapped["BookingPolicy"] = relationship(back_populates="time_blocks")


class Booking(TimestampMixin, Base):
    __tablename__ = "bookings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "organization_id"],
            ["class_sessions.id", "class_sessions.organization_id"],
            name="fk_bookings_session_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["student_id", "organization_id"],
            ["student_profiles.id", "student_profiles.organization_id"],
            name="fk_bookings_student_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["created_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_bookings_creator_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["updated_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_bookings_updater_tenant",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "organization_id", name="uq_bookings_id_org"),
        Index(
            "uq_bookings_active_student_session",
            "student_id",
            "session_id",
            unique=True,
            postgresql_where=text("status IN ('CONFIRMED', 'CANCELLATION_PENDING')"),
            sqlite_where=text("status IN ('CONFIRMED', 'CANCELLATION_PENDING')"),
        ),
        CheckConstraint(
            "status IN ('CONFIRMED', 'CANCELLATION_PENDING', 'CANCELLED')",
            name="status_valid",
        ),
        CheckConstraint("reserved_minutes > 0", name="reserved_minutes_positive"),
        CheckConstraint(
            "(status = 'CANCELLED' AND cancelled_at IS NOT NULL) OR "
            "(status <> 'CANCELLED' AND cancelled_at IS NULL)",
            name="cancelled_at_shape",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, index=True)
    session_id: Mapped[int] = mapped_column(Integer, index=True)
    student_id: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(
        String(32), default=BookingStatus.CONFIRMED.value, index=True
    )
    reserved_minutes: Mapped[int] = mapped_column(Integer)
    quota_released: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by_user_id: Mapped[int] = mapped_column(Integer)
    updated_by_user_id: Mapped[int] = mapped_column(Integer)

    session: Mapped["ClassSession"] = relationship(overlaps="student")
    student: Mapped["StudentProfile"] = relationship(overlaps="session")
    events: Mapped[list["BookingEvent"]] = relationship(
        back_populates="booking",
        cascade="all, delete-orphan",
        order_by="BookingEvent.created_at, BookingEvent.id",
    )
    created_by: Mapped["User"] = relationship(
        foreign_keys=[created_by_user_id], overlaps="updated_by"
    )
    updated_by: Mapped["User"] = relationship(
        foreign_keys=[updated_by_user_id], overlaps="created_by"
    )


class BookingEvent(Base):
    __tablename__ = "booking_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["booking_id", "organization_id"],
            ["bookings.id", "bookings.organization_id"],
            name="fk_booking_events_booking_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["actor_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_booking_events_actor_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "event_type IN ('CREATED', 'CANCELLED', "
            "'LATE_CANCELLATION_REQUESTED', 'LATE_CANCELLATION_APPROVED', "
            "'LATE_CANCELLATION_REJECTED', 'ADMIN_CREATED', 'ADMIN_CANCELLED')",
            name="event_type_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, index=True)
    booking_id: Mapped[int] = mapped_column(Integer, index=True)
    actor_user_id: Mapped[int] = mapped_column(Integer, index=True)
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    previous_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    new_status: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    override_rules: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )

    booking: Mapped["Booking"] = relationship(back_populates="events")
    actor: Mapped["User"] = relationship(overlaps="booking,events")
