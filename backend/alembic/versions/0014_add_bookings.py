"""Add booking policies, bookings, and booking history.

Revision ID: 0014_add_bookings
Revises: 0013_add_class_sessions
"""

from alembic import op
import sqlalchemy as sa


revision = "0014_add_bookings"
down_revision = "0013_add_class_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "booking_policies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("branch_id", sa.Integer(), nullable=True),
        sa.Column("minimum_booking_notice_hours", sa.Integer(), nullable=False),
        sa.Column("minimum_cancellation_notice_hours", sa.Integer(), nullable=False),
        sa.Column("earliest_booking_week_offset", sa.Integer(), nullable=False),
        sa.Column("latest_booking_week_offset", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "latest_booking_week_offset >= earliest_booking_week_offset",
            name="ck_booking_policies_booking_week_offsets_order",
        ),
        sa.CheckConstraint(
            "earliest_booking_week_offset >= 0",
            name="ck_booking_policies_earliest_week_offset_nonnegative",
        ),
        sa.CheckConstraint(
            "minimum_booking_notice_hours >= 0",
            name="ck_booking_policies_minimum_booking_notice_nonnegative",
        ),
        sa.CheckConstraint(
            "minimum_cancellation_notice_hours >= 0",
            name="ck_booking_policies_minimum_cancellation_notice_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["branch_id", "organization_id"],
            ["branches.id", "branches.organization_id"],
            name="fk_booking_policies_branch_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_booking_policies_creator_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_booking_policies_updater_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_booking_policies"),
        sa.UniqueConstraint("id", "organization_id", name="uq_booking_policies_id_org"),
        sa.UniqueConstraint(
            "organization_id", "branch_id", name="uq_booking_policies_org_branch"
        ),
    )
    op.create_index(
        "ix_booking_policies_organization_id",
        "booking_policies",
        ["organization_id"],
    )
    op.create_index("ix_booking_policies_branch_id", "booking_policies", ["branch_id"])
    op.create_index(
        "uq_booking_policies_org_default",
        "booking_policies",
        ["organization_id"],
        unique=True,
        postgresql_where=sa.text("branch_id IS NULL"),
        sqlite_where=sa.text("branch_id IS NULL"),
    )
    op.execute(
        sa.text(
            "INSERT INTO booking_policies "
            "(organization_id, branch_id, minimum_booking_notice_hours, "
            "minimum_cancellation_notice_hours, earliest_booking_week_offset, "
            "latest_booking_week_offset, created_by_user_id, updated_by_user_id) "
            "SELECT organizations.id, NULL, 24, 24, 1, 1, MIN(users.id), MIN(users.id) "
            "FROM organizations JOIN users ON users.organization_id = organizations.id "
            "AND users.role = 'ADMIN' "
            "GROUP BY organizations.id"
        )
    )

    op.create_table(
        "booking_policy_time_blocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("policy_id", sa.Integer(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.CheckConstraint(
            "end_time > start_time", name="ck_booking_policy_time_blocks_time_order"
        ),
        sa.CheckConstraint(
            "weekday >= 0 AND weekday <= 6",
            name="ck_booking_policy_time_blocks_weekday_range",
        ),
        sa.ForeignKeyConstraint(
            ["policy_id", "organization_id"],
            ["booking_policies.id", "booking_policies.organization_id"],
            name="fk_booking_policy_blocks_policy_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_booking_policy_time_blocks"),
    )
    op.create_index(
        "ix_booking_policy_time_blocks_organization_id",
        "booking_policy_time_blocks",
        ["organization_id"],
    )
    op.create_index(
        "ix_booking_policy_time_blocks_policy_id",
        "booking_policy_time_blocks",
        ["policy_id"],
    )

    op.create_table(
        "bookings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reserved_minutes", sa.Integer(), nullable=False),
        sa.Column("quota_released", sa.Boolean(), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "(status = 'CANCELLED' AND cancelled_at IS NOT NULL) OR "
            "(status <> 'CANCELLED' AND cancelled_at IS NULL)",
            name="ck_bookings_cancelled_at_shape",
        ),
        sa.CheckConstraint(
            "reserved_minutes > 0", name="ck_bookings_reserved_minutes_positive"
        ),
        sa.CheckConstraint(
            "status IN ('CONFIRMED', 'CANCELLATION_PENDING', 'CANCELLED')",
            name="ck_bookings_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_bookings_creator_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "organization_id"],
            ["class_sessions.id", "class_sessions.organization_id"],
            name="fk_bookings_session_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["student_id", "organization_id"],
            ["student_profiles.id", "student_profiles.organization_id"],
            name="fk_bookings_student_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_bookings_updater_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_bookings"),
        sa.UniqueConstraint("id", "organization_id", name="uq_bookings_id_org"),
    )
    for column in ("organization_id", "session_id", "student_id", "status"):
        op.create_index(f"ix_bookings_{column}", "bookings", [column])
    op.create_index(
        "uq_bookings_active_student_session",
        "bookings",
        ["student_id", "session_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('CONFIRMED', 'CANCELLATION_PENDING')"),
        sqlite_where=sa.text("status IN ('CONFIRMED', 'CANCELLATION_PENDING')"),
    )

    op.create_table(
        "booking_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("booking_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("previous_status", sa.String(length=32), nullable=True),
        sa.Column("new_status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("override_rules", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_type IN ('CREATED', 'CANCELLED', "
            "'LATE_CANCELLATION_REQUESTED', 'LATE_CANCELLATION_APPROVED', "
            "'LATE_CANCELLATION_REJECTED', 'ADMIN_CREATED', 'ADMIN_CANCELLED')",
            name="ck_booking_events_event_type_valid",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_booking_events_actor_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["booking_id", "organization_id"],
            ["bookings.id", "bookings.organization_id"],
            name="fk_booking_events_booking_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_booking_events"),
    )
    for column in ("organization_id", "booking_id", "actor_user_id", "event_type"):
        op.create_index(f"ix_booking_events_{column}", "booking_events", [column])


def downgrade() -> None:
    op.drop_table("booking_events")
    op.drop_table("bookings")
    op.drop_table("booking_policy_time_blocks")
    op.drop_table("booking_policies")
