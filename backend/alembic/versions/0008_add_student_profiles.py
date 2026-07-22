"""Add tenant-safe student profiles and student management permission.

Revision ID: 0008_add_student_profiles
Revises: 0007_add_rooms
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_add_student_profiles"
down_revision = "0007_add_rooms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_users_id_organization", "users", ["id", "organization_id"]
    )
    op.execute(
        "INSERT INTO permissions (code, name, description) VALUES "
        "('students.manage', 'Manage students', 'Create and manage student profiles')"
    )
    op.execute(
        "INSERT INTO role_permissions (role_code, permission_code) "
        "VALUES ('SUPER_ADMIN', 'students.manage'), ('ADMIN', 'students.manage')"
    )
    op.create_table(
        "student_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("primary_branch_id", sa.Integer(), nullable=False),
        sa.Column("student_number", sa.String(length=40), nullable=False),
        sa.Column("first_name", sa.String(length=80), nullable=False),
        sa.Column("last_name", sa.String(length=120), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("emergency_contact_name", sa.String(length=160), nullable=True),
        sa.Column("emergency_contact_phone", sa.String(length=30), nullable=True),
        sa.Column("admission_date", sa.Date(), nullable=False),
        sa.Column("weekly_hours_limit", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("course_start_date", sa.Date(), nullable=True),
        sa.Column("course_end_date", sa.Date(), nullable=True),
        sa.Column("can_book_other_branches", sa.Boolean(), nullable=False),
        sa.Column("administrative_notes", sa.Text(), nullable=True),
        sa.Column("photo_storage_key", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "course_end_date IS NULL OR course_start_date IS NULL "
            "OR course_end_date >= course_start_date",
            name="ck_student_profiles_course_dates_order",
        ),
        sa.CheckConstraint(
            "weekly_hours_limit > 0", name="ck_student_profiles_weekly_hours_positive"
        ),
        sa.ForeignKeyConstraint(
            ["primary_branch_id", "organization_id"],
            ["branches.id", "branches.organization_id"],
            name="fk_student_profiles_branch_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_student_profiles_user_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_student_profiles"),
        sa.UniqueConstraint(
            "organization_id", "student_number", name="uq_student_profiles_org_number"
        ),
        sa.UniqueConstraint("user_id", name="uq_student_profiles_user_id"),
    )
    op.create_index(
        "ix_student_profiles_organization_id", "student_profiles", ["organization_id"]
    )
    op.create_index("ix_student_profiles_user_id", "student_profiles", ["user_id"])
    op.create_index(
        "ix_student_profiles_primary_branch_id", "student_profiles", ["primary_branch_id"]
    )
    op.create_index("ix_student_profiles_status", "student_profiles", ["status"])


def downgrade() -> None:
    op.drop_table("student_profiles")
    op.execute("DELETE FROM role_permissions WHERE permission_code = 'students.manage'")
    op.execute("DELETE FROM permissions WHERE code = 'students.manage'")
    op.drop_constraint("uq_users_id_organization", "users", type_="unique")
