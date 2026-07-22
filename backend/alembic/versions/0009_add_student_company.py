"""Add optional company to student profiles.

Revision ID: 0009_add_student_company
Revises: 0008_add_student_profiles
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_add_student_company"
down_revision = "0008_add_student_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "student_profiles", sa.Column("company", sa.String(length=160), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("student_profiles", "company")
