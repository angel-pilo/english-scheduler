"""Add attendance records and correction history.

Revision ID: 0017_attendance
Revises: 0016_teacher_assignments
"""

from alembic import op
import sqlalchemy as sa


revision = "0017_attendance"
down_revision = "0016_teacher_assignments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attendance_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("booking_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("minutes_late", sa.Integer(), nullable=True),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column("observations", sa.Text(), nullable=True),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status <> 'JUSTIFIED' OR justification IS NOT NULL",
            name="ck_attendance_records_justified_requires_text",
        ),
        sa.CheckConstraint(
            "(status = 'LATE' AND minutes_late IS NOT NULL AND minutes_late > 0) OR "
            "(status <> 'LATE' AND minutes_late IS NULL)",
            name="ck_attendance_records_late_minutes_shape",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PRESENT', 'ABSENT', 'LATE', 'JUSTIFIED')",
            name="ck_attendance_records_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["booking_id", "organization_id"],
            ["bookings.id", "bookings.organization_id"],
            name="fk_attendance_records_booking_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_attendance_records_recorder_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_attendance_records_updater_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_attendance_records"),
        sa.UniqueConstraint("booking_id", name="uq_attendance_records_booking_id"),
        sa.UniqueConstraint("id", "organization_id", name="uq_attendance_records_id_org"),
    )
    for column in ("organization_id", "booking_id", "status"):
        op.create_index(f"ix_attendance_records_{column}", "attendance_records", [column])

    op.create_table(
        "attendance_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("attendance_id", sa.Integer(), nullable=False),
        sa.Column("previous_values", sa.Text(), nullable=True),
        sa.Column("new_values", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_attendance_events_actor_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["attendance_id", "organization_id"],
            ["attendance_records.id", "attendance_records.organization_id"],
            name="fk_attendance_events_attendance_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_attendance_events"),
    )
    for column in ("organization_id", "attendance_id", "actor_user_id"):
        op.create_index(f"ix_attendance_events_{column}", "attendance_events", [column])


def downgrade() -> None:
    op.drop_table("attendance_events")
    op.drop_table("attendance_records")
