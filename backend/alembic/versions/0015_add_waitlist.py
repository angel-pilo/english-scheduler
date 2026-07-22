"""Add booking waitlist offers and in-app notifications.

Revision ID: 0015_add_waitlist
Revises: 0014_add_bookings
"""

from alembic import op
import sqlalchemy as sa


revision = "0015_add_waitlist"
down_revision = "0014_add_bookings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "booking_policies",
        sa.Column(
            "waitlist_offer_minutes",
            sa.Integer(),
            server_default="120",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_booking_policies_waitlist_offer_positive",
        "booking_policies",
        "waitlist_offer_minutes > 0",
    )
    op.alter_column("booking_policies", "waitlist_offer_minutes", server_default=None)

    op.create_table(
        "booking_waitlist",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("offer_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("booking_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status <> 'ACCEPTED' OR booking_id IS NOT NULL",
            name="ck_booking_waitlist_accepted_requires_booking",
        ),
        sa.CheckConstraint(
            "status <> 'OFFERED' OR offer_expires_at IS NOT NULL",
            name="ck_booking_waitlist_offered_requires_expiration",
        ),
        sa.CheckConstraint(
            "status IN ('WAITING', 'OFFERED', 'ACCEPTED', 'EXPIRED', 'LEFT')",
            name="ck_booking_waitlist_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["booking_id", "organization_id"],
            ["bookings.id", "bookings.organization_id"],
            name="fk_booking_waitlist_booking_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "organization_id"],
            ["class_sessions.id", "class_sessions.organization_id"],
            name="fk_booking_waitlist_session_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id", "organization_id"],
            ["student_profiles.id", "student_profiles.organization_id"],
            name="fk_booking_waitlist_student_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_booking_waitlist_updater_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_booking_waitlist"),
        sa.UniqueConstraint("booking_id", name="uq_booking_waitlist_booking_id"),
        sa.UniqueConstraint("id", "organization_id", name="uq_booking_waitlist_id_org"),
    )
    for column in (
        "organization_id",
        "session_id",
        "student_id",
        "status",
        "offer_expires_at",
        "booking_id",
    ):
        op.create_index(f"ix_booking_waitlist_{column}", "booking_waitlist", [column])
    op.create_index(
        "uq_booking_waitlist_active_student_session",
        "booking_waitlist",
        ["student_id", "session_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('WAITING', 'OFFERED')"),
        sqlite_where=sa.text("status IN ('WAITING', 'OFFERED')"),
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("notification_type", sa.String(length=48), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "notification_type IN ('WAITLIST_PLACE_AVAILABLE', "
            "'WAITLIST_OFFER_EXPIRED')",
            name="ck_notifications_notification_type_valid",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_notifications_user_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_notifications"),
    )
    for column in ("organization_id", "user_id", "notification_type", "entity_id"):
        op.create_index(f"ix_notifications_{column}", "notifications", [column])


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("booking_waitlist")
    op.drop_constraint(
        "ck_booking_policies_waitlist_offer_positive",
        "booking_policies",
        type_="check",
    )
    op.drop_column("booking_policies", "waitlist_offer_minutes")
