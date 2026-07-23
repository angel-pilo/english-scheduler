from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import AttendanceStatus


class AttendanceRecord(TimestampMixin, Base):
    __tablename__ = "attendance_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["booking_id", "organization_id"],
            ["bookings.id", "bookings.organization_id"],
            name="fk_attendance_records_booking_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["recorded_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_attendance_records_recorder_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["updated_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_attendance_records_updater_tenant",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("booking_id", name="uq_attendance_records_booking_id"),
        UniqueConstraint("id", "organization_id", name="uq_attendance_records_id_org"),
        CheckConstraint(
            "status IN ('PENDING', 'PRESENT', 'ABSENT', 'LATE', 'JUSTIFIED')",
            name="status_valid",
        ),
        CheckConstraint(
            "(status = 'LATE' AND minutes_late IS NOT NULL AND minutes_late > 0) OR "
            "(status <> 'LATE' AND minutes_late IS NULL)",
            name="late_minutes_shape",
        ),
        CheckConstraint(
            "status <> 'JUSTIFIED' OR justification IS NOT NULL",
            name="justified_requires_text",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, index=True)
    booking_id: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(
        String(20), default=AttendanceStatus.PENDING.value, index=True
    )
    minutes_late: Mapped[int | None] = mapped_column(Integer, nullable=True)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    observations: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by_user_id: Mapped[int] = mapped_column(Integer)
    updated_by_user_id: Mapped[int] = mapped_column(Integer)

    booking = relationship("Booking")
    events = relationship(
        "AttendanceEvent",
        back_populates="attendance",
        cascade="all, delete-orphan",
        order_by="AttendanceEvent.created_at, AttendanceEvent.id",
    )


class AttendanceEvent(Base):
    __tablename__ = "attendance_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["attendance_id", "organization_id"],
            ["attendance_records.id", "attendance_records.organization_id"],
            name="fk_attendance_events_attendance_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["actor_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_attendance_events_actor_tenant",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, index=True)
    attendance_id: Mapped[int] = mapped_column(Integer, index=True)
    previous_values: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_values: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_user_id: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )

    attendance = relationship("AttendanceRecord", back_populates="events")
