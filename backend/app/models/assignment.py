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
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TeacherAssignmentEvent(Base):
    __tablename__ = "teacher_assignment_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "organization_id"],
            ["class_sessions.id", "class_sessions.organization_id"],
            name="fk_teacher_assignment_events_session_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["previous_teacher_id", "organization_id"],
            ["teacher_profiles.id", "teacher_profiles.organization_id"],
            name="fk_teacher_assignment_events_previous_teacher_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["new_teacher_id", "organization_id"],
            ["teacher_profiles.id", "teacher_profiles.organization_id"],
            name="fk_teacher_assignment_events_new_teacher_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["actor_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_teacher_assignment_events_actor_tenant",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "id", "organization_id", name="uq_teacher_assignment_events_id_org"
        ),
        CheckConstraint(
            "method IN ('AUTO_GENERATION', 'AUTO_RECOMMENDATION', 'MANUAL')",
            name="method_valid",
        ),
        CheckConstraint(
            "previous_teacher_id IS NOT NULL OR new_teacher_id IS NOT NULL",
            name="teacher_change_present",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, index=True)
    session_id: Mapped[int] = mapped_column(Integer, index=True)
    previous_teacher_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_teacher_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    method: Mapped[str] = mapped_column(String(32), index=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_breakdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_user_id: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )
