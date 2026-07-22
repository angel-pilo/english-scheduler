"""Add one-time account invitations.

Revision ID: 0004_add_invitations
Revises: 0003_add_auth_sessions
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_add_invitations"
down_revision = "0003_add_auth_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "hashed_password", existing_type=sa.String(length=255), nullable=True)
    op.create_table(
        "invitations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_invitations_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_invitations_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_invitations"),
    )
    op.create_index("ix_invitations_user_id", "invitations", ["user_id"])
    op.create_index("ix_invitations_created_by_user_id", "invitations", ["created_by_user_id"])
    op.create_index("ix_invitations_token_hash", "invitations", ["token_hash"], unique=True)
    op.create_index("ix_invitations_expires_at", "invitations", ["expires_at"])


def downgrade() -> None:
    op.drop_table("invitations")
    op.alter_column("users", "hashed_password", existing_type=sa.String(length=255), nullable=False)
