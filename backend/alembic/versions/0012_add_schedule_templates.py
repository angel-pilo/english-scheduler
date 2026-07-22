"""Add recurring schedule templates and calendar exceptions.

Revision ID: 0012_add_schedule_templates
Revises: 0011_add_curriculum_progress
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_add_schedule_templates"
down_revision = "0011_add_curriculum_progress"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_rooms_id_branch_organization",
        "rooms",
        ["id", "branch_id", "organization_id"],
    )
    op.create_table(
        "schedule_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("branch_id", sa.Integer(), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("level_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("configured_capacity", sa.Integer(), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_until", sa.Date(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "configured_capacity IS NULL OR configured_capacity > 0",
            name="ck_schedule_templates_configured_capacity_positive",
        ),
        sa.CheckConstraint(
            "effective_until IS NULL OR effective_until >= effective_from",
            name="ck_schedule_templates_effective_dates_order",
        ),
        sa.CheckConstraint("end_time > start_time", name="ck_schedule_templates_time_order"),
        sa.CheckConstraint("weekday >= 0 AND weekday <= 6", name="ck_schedule_templates_weekday_range"),
        sa.ForeignKeyConstraint(
            ["branch_id", "organization_id"],
            ["branches.id", "branches.organization_id"],
            name="fk_schedule_templates_branch_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_schedule_templates_creator_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["level_id", "organization_id"],
            ["academic_levels.id", "academic_levels.organization_id"],
            name="fk_schedule_templates_level_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["room_id", "branch_id", "organization_id"],
            ["rooms.id", "rooms.branch_id", "rooms.organization_id"],
            name="fk_schedule_templates_room_branch_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_schedule_templates_updater_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_schedule_templates"),
        sa.UniqueConstraint("id", "organization_id", name="uq_schedule_templates_id_org"),
    )
    for column in ("organization_id", "branch_id", "room_id", "level_id", "active"):
        op.create_index(
            f"ix_schedule_templates_{column}", "schedule_templates", [column]
        )
    op.create_table(
        "schedule_exceptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("exception_date", sa.Date(), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("branch_id", sa.Integer(), nullable=True),
        sa.Column("room_id", sa.Integer(), nullable=True),
        sa.Column("teacher_id", sa.Integer(), nullable=True),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "(scope = 'ORGANIZATION' AND branch_id IS NULL AND room_id IS NULL AND teacher_id IS NULL) OR "
            "(scope = 'BRANCH' AND branch_id IS NOT NULL AND room_id IS NULL AND teacher_id IS NULL) OR "
            "(scope = 'ROOM' AND branch_id IS NOT NULL AND room_id IS NOT NULL AND teacher_id IS NULL) OR "
            "(scope = 'TEACHER' AND branch_id IS NULL AND room_id IS NULL AND teacher_id IS NOT NULL)",
            name="ck_schedule_exceptions_scope_shape",
        ),
        sa.CheckConstraint(
            "(start_time IS NULL AND end_time IS NULL) OR "
            "(start_time IS NOT NULL AND end_time IS NOT NULL AND end_time > start_time)",
            name="ck_schedule_exceptions_time_shape",
        ),
        sa.ForeignKeyConstraint(
            ["branch_id", "organization_id"],
            ["branches.id", "branches.organization_id"],
            name="fk_schedule_exceptions_branch_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_schedule_exceptions_creator_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["room_id", "branch_id", "organization_id"],
            ["rooms.id", "rooms.branch_id", "rooms.organization_id"],
            name="fk_schedule_exceptions_room_branch_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["teacher_id", "organization_id"],
            ["teacher_profiles.id", "teacher_profiles.organization_id"],
            name="fk_schedule_exceptions_teacher_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_schedule_exceptions_updater_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_schedule_exceptions"),
        sa.UniqueConstraint("id", "organization_id", name="uq_schedule_exceptions_id_org"),
    )
    for column in (
        "organization_id",
        "exception_date",
        "scope",
        "branch_id",
        "room_id",
        "teacher_id",
        "active",
    ):
        op.create_index(
            f"ix_schedule_exceptions_{column}", "schedule_exceptions", [column]
        )


def downgrade() -> None:
    op.drop_table("schedule_exceptions")
    op.drop_table("schedule_templates")
    op.drop_constraint(
        "uq_rooms_id_branch_organization", "rooms", type_="unique"
    )
