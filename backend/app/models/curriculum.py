from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
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
from app.models.enums import TopicProgressStatus, TopicStatus

if TYPE_CHECKING:
    from app.models.level import AcademicLevel
    from app.models.student import StudentProfile
    from app.models.user import User


class CurriculumChapter(TimestampMixin, Base):
    __tablename__ = "curriculum_chapters"
    __table_args__ = (
        ForeignKeyConstraint(
            ["level_id", "organization_id"],
            ["academic_levels.id", "academic_levels.organization_id"],
            name="fk_curriculum_chapters_level_tenant",
            ondelete="CASCADE",
        ),
        UniqueConstraint("id", "organization_id", name="uq_curriculum_chapters_id_org"),
        UniqueConstraint("level_id", "name", name="uq_curriculum_chapters_level_name"),
        UniqueConstraint("level_id", "sort_order", name="uq_curriculum_chapters_level_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, index=True)
    level_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    level: Mapped["AcademicLevel"] = relationship(back_populates="chapters")
    topics: Mapped[list["CurriculumTopic"]] = relationship(
        back_populates="chapter", cascade="all, delete-orphan"
    )


class CurriculumTopic(TimestampMixin, Base):
    __tablename__ = "curriculum_topics"
    __table_args__ = (
        ForeignKeyConstraint(
            ["chapter_id", "organization_id"],
            ["curriculum_chapters.id", "curriculum_chapters.organization_id"],
            name="fk_curriculum_topics_chapter_tenant",
            ondelete="CASCADE",
        ),
        UniqueConstraint("id", "organization_id", name="uq_curriculum_topics_id_org"),
        UniqueConstraint("chapter_id", "name", name="uq_curriculum_topics_chapter_name"),
        UniqueConstraint("chapter_id", "sort_order", name="uq_curriculum_topics_chapter_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, index=True)
    chapter_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(20), default=TopicStatus.ACTIVE.value, index=True
    )

    chapter: Mapped["CurriculumChapter"] = relationship(back_populates="topics")
    student_progress: Mapped[list["StudentTopicProgress"]] = relationship(
        back_populates="topic"
    )


class StudentLevelHistory(TimestampMixin, Base):
    __tablename__ = "student_level_history"
    __table_args__ = (
        ForeignKeyConstraint(
            ["student_id", "organization_id"],
            ["student_profiles.id", "student_profiles.organization_id"],
            name="fk_student_level_history_student_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["level_id", "organization_id"],
            ["academic_levels.id", "academic_levels.organization_id"],
            name="fk_student_level_history_level_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(is_current = true AND end_date IS NULL) OR "
            "(is_current = false AND end_date IS NOT NULL)",
            name="current_end_date_shape",
        ),
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="date_order"),
        UniqueConstraint(
            "student_id", "level_id", "start_date", name="uq_student_level_start"
        ),
        Index(
            "uq_student_current_level",
            "student_id",
            unique=True,
            postgresql_where=text("is_current = true"),
            sqlite_where=text("is_current = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, index=True)
    student_id: Mapped[int] = mapped_column(Integer, index=True)
    level_id: Mapped[int] = mapped_column(Integer, index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    student: Mapped["StudentProfile"] = relationship(
        back_populates="level_history", overlaps="level,student_history"
    )
    level: Mapped["AcademicLevel"] = relationship(
        back_populates="student_history", overlaps="level_history,student"
    )


class StudentTopicProgress(TimestampMixin, Base):
    __tablename__ = "student_topic_progress"
    __table_args__ = (
        ForeignKeyConstraint(
            ["student_id", "organization_id"],
            ["student_profiles.id", "student_profiles.organization_id"],
            name="fk_student_topic_progress_student_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["topic_id", "organization_id"],
            ["curriculum_topics.id", "curriculum_topics.organization_id"],
            name="fk_student_topic_progress_topic_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["updated_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_student_topic_progress_updater_tenant",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("student_id", "topic_id", name="uq_student_topic_progress"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, index=True)
    student_id: Mapped[int] = mapped_column(Integer, index=True)
    topic_id: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(
        String(20), default=TopicProgressStatus.NOT_STARTED.value, index=True
    )
    observations: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_taught_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by_user_id: Mapped[int] = mapped_column(Integer)

    student: Mapped["StudentProfile"] = relationship(
        back_populates="topic_progress", overlaps="topic,student_progress,updated_by"
    )
    topic: Mapped["CurriculumTopic"] = relationship(
        back_populates="student_progress", overlaps="student,topic_progress,updated_by"
    )
    updated_by: Mapped["User"] = relationship(
        overlaps="student,student_progress,topic,topic_progress"
    )
