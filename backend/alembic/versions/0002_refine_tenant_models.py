"""Refine tenant models with metadata and integrity constraints.

Revision ID: 0002_refine_tenant_models
Revises: 0001_initial_schema
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_refine_tenant_models"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("slug", sa.String(length=80), nullable=True))
    op.add_column(
        "organizations",
        sa.Column(
            "timezone",
            sa.String(length=64),
            server_default="America/Mexico_City",
            nullable=False,
        ),
    )
    op.add_column(
        "organizations",
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column(
        "organizations",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column(
        "organizations",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute("UPDATE organizations SET slug = 'organization-' || id WHERE slug IS NULL")
    op.alter_column("organizations", "slug", nullable=False)
    op.alter_column("organizations", "timezone", server_default=None)
    op.alter_column("organizations", "active", server_default=None)
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)

    op.add_column("branches", sa.Column("code", sa.String(length=30), nullable=True))
    op.add_column(
        "branches",
        sa.Column(
            "timezone",
            sa.String(length=64),
            server_default="America/Mexico_City",
            nullable=False,
        ),
    )
    op.add_column(
        "branches", sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False)
    )
    op.add_column(
        "branches",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column(
        "branches",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute("UPDATE branches SET code = 'BR-' || id WHERE code IS NULL")
    op.alter_column("branches", "code", nullable=False)
    op.alter_column("branches", "timezone", server_default=None)
    op.alter_column("branches", "active", server_default=None)
    op.create_unique_constraint(
        "uq_branches_organization_name", "branches", ["organization_id", "name"]
    )
    op.create_unique_constraint(
        "uq_branches_organization_code", "branches", ["organization_id", "code"]
    )
    op.drop_constraint("branches_organization_id_fkey", "branches", type_="foreignkey")
    op.create_foreign_key(
        "fk_branches_organization_id_organizations",
        "branches",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.add_column(
        "users",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.drop_constraint("users_branch_id_fkey", "users", type_="foreignkey")
    op.drop_constraint("users_organization_id_fkey", "users", type_="foreignkey")
    op.alter_column("users", "organization_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("users", "branch_id", existing_type=sa.Integer(), nullable=True)
    op.create_foreign_key(
        "fk_users_organization_id_organizations",
        "users",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_users_branch_id_branches",
        "users",
        "branches",
        ["branch_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_users_tenant_scope",
        "users",
        "(role = 'SUPER_ADMIN' AND organization_id IS NULL AND branch_id IS NULL) "
        "OR (role <> 'SUPER_ADMIN' AND organization_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_tenant_scope", "users", type_="check")
    op.drop_constraint("fk_users_branch_id_branches", "users", type_="foreignkey")
    op.drop_constraint("fk_users_organization_id_organizations", "users", type_="foreignkey")
    op.alter_column("users", "branch_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("users", "organization_id", existing_type=sa.Integer(), nullable=False)
    op.create_foreign_key(
        "users_organization_id_fkey", "users", "organizations", ["organization_id"], ["id"]
    )
    op.create_foreign_key("users_branch_id_fkey", "users", "branches", ["branch_id"], ["id"])
    op.drop_column("users", "updated_at")
    op.drop_column("users", "created_at")

    op.drop_constraint("fk_branches_organization_id_organizations", "branches", type_="foreignkey")
    op.create_foreign_key(
        "branches_organization_id_fkey",
        "branches",
        "organizations",
        ["organization_id"],
        ["id"],
    )
    op.drop_constraint("uq_branches_organization_code", "branches", type_="unique")
    op.drop_constraint("uq_branches_organization_name", "branches", type_="unique")
    op.drop_column("branches", "updated_at")
    op.drop_column("branches", "created_at")
    op.drop_column("branches", "active")
    op.drop_column("branches", "timezone")
    op.drop_column("branches", "code")

    op.drop_index("ix_organizations_slug", table_name="organizations")
    op.drop_column("organizations", "updated_at")
    op.drop_column("organizations", "created_at")
    op.drop_column("organizations", "active")
    op.drop_column("organizations", "timezone")
    op.drop_column("organizations", "slug")
