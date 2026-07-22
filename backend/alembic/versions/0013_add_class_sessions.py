"""Add generated class sessions.

Revision ID: 0013_add_class_sessions
Revises: 0012_add_schedule_templates
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_add_class_sessions"
down_revision = "0012_add_schedule_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "class_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("source_template_id", sa.Integer(), nullable=False),
        sa.Column("generation_batch_id", sa.String(length=36), nullable=False),
        sa.Column("branch_id", sa.Integer(), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("level_id", sa.Integer(), nullable=False),
        sa.Column("teacher_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("configured_capacity", sa.Integer(), nullable=False),
        sa.Column("effective_capacity", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "configured_capacity > 0",
            name="ck_class_sessions_configured_capacity_positive",
        ),
        sa.CheckConstraint(
            "effective_capacity <= configured_capacity",
            name="ck_class_sessions_effective_capacity_not_above_configured",
        ),
        sa.CheckConstraint(
            "effective_capacity > 0",
            name="ck_class_sessions_effective_capacity_positive",
        ),
        sa.CheckConstraint(
            "status <> 'PUBLISHED' OR teacher_id IS NOT NULL",
            name="ck_class_sessions_published_requires_teacher",
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'PUBLISHED', 'CANCELLED')",
            name="ck_class_sessions_status_valid",
        ),
        sa.CheckConstraint("end_time > start_time", name="ck_class_sessions_time_order"),
        sa.ForeignKeyConstraint(
            ["branch_id", "organization_id"],
            ["branches.id", "branches.organization_id"],
            name="fk_class_sessions_branch_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_class_sessions_creator_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["level_id", "organization_id"],
            ["academic_levels.id", "academic_levels.organization_id"],
            name="fk_class_sessions_level_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["room_id", "branch_id", "organization_id"],
            ["rooms.id", "rooms.branch_id", "rooms.organization_id"],
            name="fk_class_sessions_room_branch_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_template_id", "organization_id"],
            ["schedule_templates.id", "schedule_templates.organization_id"],
            name="fk_class_sessions_template_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["teacher_id", "organization_id"],
            ["teacher_profiles.id", "teacher_profiles.organization_id"],
            name="fk_class_sessions_teacher_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_class_sessions_updater_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_class_sessions"),
        sa.UniqueConstraint("id", "organization_id", name="uq_class_sessions_id_org"),
        sa.UniqueConstraint(
            "source_template_id", "session_date", name="uq_class_sessions_template_date"
        ),
    )
    for column in (
        "organization_id",
        "source_template_id",
        "generation_batch_id",
        "branch_id",
        "room_id",
        "level_id",
        "teacher_id",
        "session_date",
        "status",
    ):
        op.create_index(f"ix_class_sessions_{column}", "class_sessions", [column])


def downgrade() -> None:
    op.drop_table("class_sessions")
