"""Add roles, permissions, and tenant-scoped delegations.

Revision ID: 0006_add_rbac
Revises: 0005_add_password_reset_tokens
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_add_rbac"
down_revision = "0005_add_password_reset_tokens"
branch_labels = None
depends_on = None


ROLES = [
    {"code": "SUPER_ADMIN", "name": "Super administrator", "description": "Platform owner"},
    {"code": "ADMIN", "name": "Administrator", "description": "Organization administrator"},
    {"code": "TEACHER", "name": "Teacher", "description": "Academic teacher"},
    {"code": "STUDENT", "name": "Student", "description": "Enrolled student"},
]

PERMISSIONS = [
    ("organizations.manage", "Manage organizations", "Create and configure organizations"),
    ("branches.manage", "Manage branches", "Create and configure branches"),
    ("rooms.manage", "Manage rooms", "Create and configure rooms"),
    ("users.invite", "Invite users", "Invite teachers and students"),
    ("users.permissions.manage", "Manage delegated permissions", "Grant and revoke permissions"),
    ("levels.manage", "Manage levels", "Configure academic levels"),
    ("curriculum.manage", "Manage curriculum", "Configure chapters and topics"),
    ("schedule.manage", "Manage schedules", "Create and modify schedules"),
    ("bookings.manage", "Manage bookings", "Manage student bookings"),
    ("payments.manage", "Manage payments", "Register and update payments"),
    ("reports.view", "View reports", "View organization reports"),
    ("attendance.manage", "Manage attendance", "Register class attendance"),
    ("grades.manage", "Manage grades", "Register and update grades"),
    ("teacher.availability.manage", "Manage own availability", "Manage teacher availability"),
    ("student.bookings.manage", "Manage own bookings", "Book and cancel classes"),
    ("own.schedule.view", "View own schedule", "View the current user's schedule"),
    ("own.profile.view", "View own profile", "View the current user's profile"),
]

ADMIN_PERMISSIONS = [
    "branches.manage",
    "rooms.manage",
    "users.invite",
    "users.permissions.manage",
    "levels.manage",
    "curriculum.manage",
    "schedule.manage",
    "bookings.manage",
    "payments.manage",
    "reports.view",
    "attendance.manage",
    "grades.manage",
    "own.schedule.view",
    "own.profile.view",
]

TEACHER_PERMISSIONS = [
    "attendance.manage",
    "grades.manage",
    "teacher.availability.manage",
    "own.schedule.view",
    "own.profile.view",
]

STUDENT_PERMISSIONS = [
    "student.bookings.manage",
    "own.schedule.view",
    "own.profile.view",
]


def upgrade() -> None:
    roles = op.create_table(
        "roles",
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("code", name="pk_roles"),
        sa.UniqueConstraint("name", name="uq_roles_name"),
    )
    permissions = op.create_table(
        "permissions",
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("code", name="pk_permissions"),
        sa.UniqueConstraint("name", name="uq_permissions_name"),
    )
    role_permissions = op.create_table(
        "role_permissions",
        sa.Column("role_code", sa.String(length=20), nullable=False),
        sa.Column("permission_code", sa.String(length=80), nullable=False),
        sa.ForeignKeyConstraint(
            ["permission_code"],
            ["permissions.code"],
            name="fk_role_permissions_permission_code_permissions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_code"],
            ["roles.code"],
            name="fk_role_permissions_role_code_roles",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("role_code", "permission_code", name="pk_role_permissions"),
    )

    op.bulk_insert(roles, ROLES)
    op.bulk_insert(
        permissions,
        [{"code": code, "name": name, "description": description} for code, name, description in PERMISSIONS],
    )
    assignments = [
        *({"role_code": "SUPER_ADMIN", "permission_code": code} for code, _, _ in PERMISSIONS),
        *({"role_code": "ADMIN", "permission_code": code} for code in ADMIN_PERMISSIONS),
        *({"role_code": "TEACHER", "permission_code": code} for code in TEACHER_PERMISSIONS),
        *({"role_code": "STUDENT", "permission_code": code} for code in STUDENT_PERMISSIONS),
    ]
    op.bulk_insert(role_permissions, assignments)

    op.create_foreign_key(
        "fk_users_role_roles", "users", "roles", ["role"], ["code"], ondelete="RESTRICT"
    )
    op.create_table(
        "user_permissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("permission_code", sa.String(length=80), nullable=False),
        sa.Column("granted_by_user_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_user_permissions_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_user_permissions_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["permission_code"],
            ["permissions.code"],
            name="fk_user_permissions_permission_code_permissions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["granted_by_user_id"],
            ["users.id"],
            name="fk_user_permissions_granted_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_permissions"),
        sa.UniqueConstraint("user_id", "permission_code", name="uq_user_permissions_user_code"),
    )
    op.create_index("ix_user_permissions_organization_id", "user_permissions", ["organization_id"])
    op.create_index("ix_user_permissions_user_id", "user_permissions", ["user_id"])
    op.create_index("ix_user_permissions_permission_code", "user_permissions", ["permission_code"])
    op.create_index("ix_user_permissions_granted_by_user_id", "user_permissions", ["granted_by_user_id"])


def downgrade() -> None:
    op.drop_table("user_permissions")
    op.drop_constraint("fk_users_role_roles", "users", type_="foreignkey")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
