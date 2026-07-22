"""Add curriculum, student level history, and topic progress.

Revision ID: 0011_add_curriculum_progress
Revises: 0010_add_teacher_management
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_add_curriculum_progress"
down_revision = "0010_add_teacher_management"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_student_profiles_id_organization",
        "student_profiles",
        ["id", "organization_id"],
    )
    op.execute(
        "INSERT INTO permissions (code, name, description) VALUES "
        "('student.progress.manage', 'Manage student progress', "
        "'Record individual curriculum progress')"
    )
    op.execute(
        "INSERT INTO role_permissions (role_code, permission_code) VALUES "
        "('SUPER_ADMIN', 'student.progress.manage'), "
        "('ADMIN', 'student.progress.manage'), "
        "('TEACHER', 'student.progress.manage')"
    )
    op.create_table(
        "curriculum_chapters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("level_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["level_id", "organization_id"],
            ["academic_levels.id", "academic_levels.organization_id"],
            name="fk_curriculum_chapters_level_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_curriculum_chapters"),
        sa.UniqueConstraint("id", "organization_id", name="uq_curriculum_chapters_id_org"),
        sa.UniqueConstraint("level_id", "name", name="uq_curriculum_chapters_level_name"),
        sa.UniqueConstraint("level_id", "sort_order", name="uq_curriculum_chapters_level_order"),
    )
    op.create_index("ix_curriculum_chapters_organization_id", "curriculum_chapters", ["organization_id"])
    op.create_index("ix_curriculum_chapters_level_id", "curriculum_chapters", ["level_id"])
    op.create_table(
        "curriculum_topics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("chapter_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["chapter_id", "organization_id"],
            ["curriculum_chapters.id", "curriculum_chapters.organization_id"],
            name="fk_curriculum_topics_chapter_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_curriculum_topics"),
        sa.UniqueConstraint("id", "organization_id", name="uq_curriculum_topics_id_org"),
        sa.UniqueConstraint("chapter_id", "name", name="uq_curriculum_topics_chapter_name"),
        sa.UniqueConstraint("chapter_id", "sort_order", name="uq_curriculum_topics_chapter_order"),
    )
    op.create_index("ix_curriculum_topics_organization_id", "curriculum_topics", ["organization_id"])
    op.create_index("ix_curriculum_topics_chapter_id", "curriculum_topics", ["chapter_id"])
    op.create_index("ix_curriculum_topics_status", "curriculum_topics", ["status"])
    op.create_table(
        "student_level_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("level_id", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "(is_current = true AND end_date IS NULL) OR "
            "(is_current = false AND end_date IS NOT NULL)",
            name="ck_student_level_history_current_end_date_shape",
        ),
        sa.CheckConstraint(
            "end_date IS NULL OR end_date >= start_date",
            name="ck_student_level_history_date_order",
        ),
        sa.ForeignKeyConstraint(
            ["level_id", "organization_id"],
            ["academic_levels.id", "academic_levels.organization_id"],
            name="fk_student_level_history_level_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["student_id", "organization_id"],
            ["student_profiles.id", "student_profiles.organization_id"],
            name="fk_student_level_history_student_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_student_level_history"),
        sa.UniqueConstraint("student_id", "level_id", "start_date", name="uq_student_level_start"),
    )
    op.create_index("ix_student_level_history_organization_id", "student_level_history", ["organization_id"])
    op.create_index("ix_student_level_history_student_id", "student_level_history", ["student_id"])
    op.create_index("ix_student_level_history_level_id", "student_level_history", ["level_id"])
    op.create_index(
        "uq_student_current_level",
        "student_level_history",
        ["student_id"],
        unique=True,
        postgresql_where=sa.text("is_current = true"),
    )
    op.create_table(
        "student_topic_progress",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("topic_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("observations", sa.Text(), nullable=True),
        sa.Column("last_taught_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["student_id", "organization_id"],
            ["student_profiles.id", "student_profiles.organization_id"],
            name="fk_student_topic_progress_student_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id", "organization_id"],
            ["curriculum_topics.id", "curriculum_topics.organization_id"],
            name="fk_student_topic_progress_topic_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_student_topic_progress_updater_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_student_topic_progress"),
        sa.UniqueConstraint("student_id", "topic_id", name="uq_student_topic_progress"),
    )
    op.create_index("ix_student_topic_progress_organization_id", "student_topic_progress", ["organization_id"])
    op.create_index("ix_student_topic_progress_student_id", "student_topic_progress", ["student_id"])
    op.create_index("ix_student_topic_progress_topic_id", "student_topic_progress", ["topic_id"])
    op.create_index("ix_student_topic_progress_status", "student_topic_progress", ["status"])


def downgrade() -> None:
    op.drop_table("student_topic_progress")
    op.drop_table("student_level_history")
    op.drop_table("curriculum_topics")
    op.drop_table("curriculum_chapters")
    op.execute("DELETE FROM role_permissions WHERE permission_code = 'student.progress.manage'")
    op.execute("DELETE FROM permissions WHERE code = 'student.progress.manage'")
    op.drop_constraint(
        "uq_student_profiles_id_organization", "student_profiles", type_="unique"
    )
