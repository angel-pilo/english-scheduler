from typing import TYPE_CHECKING

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.auth_session import AuthSession
    from app.models.invitation import Invitation
    from app.models.password_reset_token import PasswordResetToken
    from app.models.branch import Branch
    from app.models.org import Organization
    from app.models.student import StudentProfile


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "(role = 'SUPER_ADMIN' AND organization_id IS NULL AND branch_id IS NULL) "
            "OR (role <> 'SUPER_ADMIN' AND organization_id IS NOT NULL)",
            name="tenant_scope",
        ),
        UniqueConstraint("id", "organization_id", name="uq_users_id_organization"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True, nullable=True
    )
    branch_id: Mapped[int | None] = mapped_column(
        ForeignKey("branches.id", ondelete="RESTRICT"), index=True, nullable=True
    )
    role: Mapped[str] = mapped_column(
        ForeignKey("roles.code", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped["Organization | None"] = relationship(back_populates="users")
    branch: Mapped["Branch | None"] = relationship(back_populates="users")
    auth_sessions: Mapped[list["AuthSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    invitations: Mapped[list["Invitation"]] = relationship(
        back_populates="user",
        foreign_keys="Invitation.user_id",
        cascade="all, delete-orphan",
    )
    password_reset_tokens: Mapped[list["PasswordResetToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    student_profile: Mapped["StudentProfile | None"] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        overlaps="primary_branch,student_profiles",
    )
