"""Add rooms with tenant-safe branch relationships.

Revision ID: 0007_add_rooms
Revises: 0006_add_rbac
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_add_rooms"
down_revision = "0006_add_rbac"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_branches_id_organization", "branches", ["id", "organization_id"]
    )
    op.create_table(
        "rooms",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("branch_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("capacity > 0", name="ck_rooms_capacity_positive"),
        sa.ForeignKeyConstraint(
            ["branch_id", "organization_id"],
            ["branches.id", "branches.organization_id"],
            name="fk_rooms_branch_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rooms"),
        sa.UniqueConstraint("branch_id", "code", name="uq_rooms_branch_code"),
        sa.UniqueConstraint("branch_id", "name", name="uq_rooms_branch_name"),
    )
    op.create_index("ix_rooms_organization_id", "rooms", ["organization_id"])
    op.create_index("ix_rooms_branch_id", "rooms", ["branch_id"])


def downgrade() -> None:
    op.drop_table("rooms")
    op.drop_constraint("uq_branches_id_organization", "branches", type_="unique")
