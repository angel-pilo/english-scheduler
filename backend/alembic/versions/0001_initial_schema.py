"""Represent the initial Organization, Branch, and User schema.

Revision ID: 0001_initial_schema
Revises:
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_organizations_name", "organizations", ["name"], unique=True)

    op.create_table(
        "branches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], name="branches_organization_id_fkey"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_branches_organization_id", "branches", ["organization_id"])

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("branch_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=180), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["branch_id"], ["branches.id"], name="users_branch_id_fkey"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], name="users_organization_id_fkey"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_branch_id", "users", ["branch_id"])
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_organization_id", "users", ["organization_id"])
    op.create_index("ix_users_role", "users", ["role"])


def downgrade() -> None:
    op.drop_table("users")
    op.drop_table("branches")
    op.drop_table("organizations")
