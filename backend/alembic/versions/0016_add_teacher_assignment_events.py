"""Add explainable teacher assignment history.

Revision ID: 0016_teacher_assignments
Revises: 0015_add_waitlist
"""

from alembic import op
import sqlalchemy as sa


revision = "0016_teacher_assignments"
down_revision = "0015_add_waitlist"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "teacher_assignment_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("previous_teacher_id", sa.Integer(), nullable=True),
        sa.Column("new_teacher_id", sa.Integer(), nullable=True),
        sa.Column("method", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("score_breakdown", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "method IN ('AUTO_GENERATION', 'AUTO_RECOMMENDATION', 'MANUAL')",
            name="ck_teacher_assignment_events_method_valid",
        ),
        sa.CheckConstraint(
            "previous_teacher_id IS NOT NULL OR new_teacher_id IS NOT NULL",
            name="ck_teacher_assignment_events_teacher_change_present",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_teacher_assignment_events_actor_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["new_teacher_id", "organization_id"],
            ["teacher_profiles.id", "teacher_profiles.organization_id"],
            name="fk_teacher_assignment_events_new_teacher_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["previous_teacher_id", "organization_id"],
            ["teacher_profiles.id", "teacher_profiles.organization_id"],
            name="fk_teacher_assignment_events_previous_teacher_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "organization_id"],
            ["class_sessions.id", "class_sessions.organization_id"],
            name="fk_teacher_assignment_events_session_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_teacher_assignment_events"),
        sa.UniqueConstraint(
            "id", "organization_id", name="uq_teacher_assignment_events_id_org"
        ),
    )
    for column in ("organization_id", "session_id", "method", "actor_user_id"):
        op.create_index(
            f"ix_teacher_assignment_events_{column}",
            "teacher_assignment_events",
            [column],
        )


def downgrade() -> None:
    op.drop_table("teacher_assignment_events")
