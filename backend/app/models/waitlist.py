from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
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
from app.models.enums import WaitlistStatus

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.schedule import ClassSession
    from app.models.student import StudentProfile
    from app.models.user import User


class BookingWaitlist(TimestampMixin, Base):
    __tablename__ = "booking_waitlist"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "organization_id"],
            ["class_sessions.id", "class_sessions.organization_id"],
            name="fk_booking_waitlist_session_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["student_id", "organization_id"],
            ["student_profiles.id", "student_profiles.organization_id"],
            name="fk_booking_waitlist_student_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["booking_id", "organization_id"],
            ["bookings.id", "bookings.organization_id"],
            name="fk_booking_waitlist_booking_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["updated_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_booking_waitlist_updater_tenant",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "organization_id", name="uq_booking_waitlist_id_org"),
        UniqueConstraint("booking_id", name="uq_booking_waitlist_booking_id"),
        Index(
            "uq_booking_waitlist_active_student_session",
            "student_id",
            "session_id",
            unique=True,
            postgresql_where=text("status IN ('WAITING', 'OFFERED')"),
            sqlite_where=text("status IN ('WAITING', 'OFFERED')"),
        ),
        CheckConstraint(
            "status IN ('WAITING', 'OFFERED', 'ACCEPTED', 'EXPIRED', 'LEFT')",
            name="status_valid",
        ),
        CheckConstraint(
            "status <> 'OFFERED' OR offer_expires_at IS NOT NULL",
            name="offered_requires_expiration",
        ),
        CheckConstraint(
            "status <> 'ACCEPTED' OR booking_id IS NOT NULL",
            name="accepted_requires_booking",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, index=True)
    session_id: Mapped[int] = mapped_column(Integer, index=True)
    student_id: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(
        String(20), default=WaitlistStatus.WAITING.value, index=True
    )
    offer_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    booking_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    updated_by_user_id: Mapped[int] = mapped_column(Integer)

    session: Mapped["ClassSession"] = relationship(overlaps="booking,student")
    student: Mapped["StudentProfile"] = relationship(overlaps="booking,session")
    booking: Mapped["Booking | None"] = relationship(overlaps="session,student")
    updated_by: Mapped["User"] = relationship(overlaps="booking,session,student")


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_notifications_user_tenant",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "notification_type IN ('WAITLIST_PLACE_AVAILABLE', 'WAITLIST_OFFER_EXPIRED')",
            name="notification_type_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    notification_type: Mapped[str] = mapped_column(String(48), index=True)
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )

    user: Mapped["User"] = relationship()
