"""Add teacher profiles, assignments, levels, and availability.

Revision ID: 0010_add_teacher_management
Revises: 0009_add_student_company
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_add_teacher_management"
down_revision = "0009_add_student_company"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO permissions (code, name, description) VALUES "
        "('teachers.manage', 'Manage teachers', 'Create and manage teacher profiles')"
    )
    op.execute(
        "INSERT INTO role_permissions (role_code, permission_code) "
        "VALUES ('SUPER_ADMIN', 'teachers.manage'), ('ADMIN', 'teachers.manage')"
    )
    op.create_table(
        "academic_levels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("default_capacity", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "default_capacity IS NULL OR default_capacity > 0",
            name="ck_academic_levels_default_capacity_positive",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_academic_levels_organization_id_organizations", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_academic_levels"),
        sa.UniqueConstraint("id", "organization_id", name="uq_academic_levels_id_organization"),
        sa.UniqueConstraint("organization_id", "name", name="uq_academic_levels_org_name"),
        sa.UniqueConstraint("organization_id", "sort_order", name="uq_academic_levels_org_order"),
    )
    op.create_index("ix_academic_levels_organization_id", "academic_levels", ["organization_id"])
    op.create_table(
        "teacher_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("employee_number", sa.String(length=40), nullable=False),
        sa.Column("first_name", sa.String(length=80), nullable=False),
        sa.Column("last_name", sa.String(length=120), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("hire_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("administrative_notes", sa.Text(), nullable=True),
        sa.Column("photo_storage_key", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id", "organization_id"], ["users.id", "users.organization_id"],
            name="fk_teacher_profiles_user_tenant", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_teacher_profiles"),
        sa.UniqueConstraint("id", "organization_id", name="uq_teacher_profiles_id_organization"),
        sa.UniqueConstraint("user_id", name="uq_teacher_profiles_user_id"),
        sa.UniqueConstraint("organization_id", "employee_number", name="uq_teacher_profiles_org_number"),
    )
    op.create_index("ix_teacher_profiles_organization_id", "teacher_profiles", ["organization_id"])
    op.create_index("ix_teacher_profiles_user_id", "teacher_profiles", ["user_id"])
    op.create_index("ix_teacher_profiles_status", "teacher_profiles", ["status"])
    op.create_table(
        "teacher_branch_assignments",
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.Column("branch_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["branch_id", "organization_id"], ["branches.id", "branches.organization_id"],
            name="fk_teacher_branches_branch_tenant", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["teacher_id", "organization_id"], ["teacher_profiles.id", "teacher_profiles.organization_id"],
            name="fk_teacher_branches_teacher_tenant", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("teacher_id", "branch_id", name="pk_teacher_branch_assignments"),
    )
    op.create_index(
        "ix_teacher_branch_assignments_organization_id",
        "teacher_branch_assignments", ["organization_id"]
    )
    op.create_table(
        "teacher_level_assignments",
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.Column("level_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["level_id", "organization_id"], ["academic_levels.id", "academic_levels.organization_id"],
            name="fk_teacher_levels_level_tenant", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["teacher_id", "organization_id"], ["teacher_profiles.id", "teacher_profiles.organization_id"],
            name="fk_teacher_levels_teacher_tenant", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("teacher_id", "level_id", name="pk_teacher_level_assignments"),
    )
    op.create_index(
        "ix_teacher_level_assignments_organization_id",
        "teacher_level_assignments", ["organization_id"]
    )
    op.create_table(
        "teacher_availability_blocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.CheckConstraint("end_time > start_time", name="ck_teacher_availability_blocks_time_order"),
        sa.CheckConstraint("weekday >= 0 AND weekday <= 6", name="ck_teacher_availability_blocks_weekday_range"),
        sa.ForeignKeyConstraint(
            ["teacher_id", "organization_id"], ["teacher_profiles.id", "teacher_profiles.organization_id"],
            name="fk_teacher_availability_teacher_tenant", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_teacher_availability_blocks"),
        sa.UniqueConstraint(
            "teacher_id", "weekday", "start_time", "end_time", name="uq_teacher_availability_block"
        ),
    )
    op.create_index(
        "ix_teacher_availability_blocks_organization_id",
        "teacher_availability_blocks", ["organization_id"]
    )
    op.create_index(
        "ix_teacher_availability_blocks_teacher_id",
        "teacher_availability_blocks", ["teacher_id"]
    )
    op.create_table(
        "teacher_availability_exceptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.Column("exception_date", sa.Date(), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.CheckConstraint(
            "(is_available = false AND start_time IS NULL AND end_time IS NULL) OR "
            "(is_available = true AND start_time IS NOT NULL AND end_time IS NOT NULL AND end_time > start_time)",
            name="ck_teacher_availability_exceptions_availability_shape",
        ),
        sa.ForeignKeyConstraint(
            ["teacher_id", "organization_id"], ["teacher_profiles.id", "teacher_profiles.organization_id"],
            name="fk_teacher_exceptions_teacher_tenant", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_teacher_availability_exceptions"),
        sa.UniqueConstraint("teacher_id", "exception_date", name="uq_teacher_exception_date"),
    )
    op.create_index(
        "ix_teacher_availability_exceptions_organization_id",
        "teacher_availability_exceptions", ["organization_id"]
    )
    op.create_index(
        "ix_teacher_availability_exceptions_teacher_id",
        "teacher_availability_exceptions", ["teacher_id"]
    )


def downgrade() -> None:
    op.drop_table("teacher_availability_exceptions")
    op.drop_table("teacher_availability_blocks")
    op.drop_table("teacher_level_assignments")
    op.drop_table("teacher_branch_assignments")
    op.drop_table("teacher_profiles")
    op.drop_table("academic_levels")
    op.execute("DELETE FROM role_permissions WHERE permission_code = 'teachers.manage'")
    op.execute("DELETE FROM permissions WHERE code = 'teachers.manage'")
