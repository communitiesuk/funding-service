"""add options for multiple submissions on collections

Revision ID: 044_add_multi_submission_sett
Revises: 043_file_upload_question_type
Create Date: 2026-02-19 18:14:15.699447

"""

import sqlalchemy as sa
from alembic import op

revision = "044_add_multi_submission_sett"
down_revision = "043_file_upload_question_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("allow_multiple_submissions", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(sa.Column("submission_name_question_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_collection_submission_name_question_id_component"),
            "component",
            ["submission_name_question_id"],
            ["id"],
        )
        batch_op.create_check_constraint(
            "ck_submission_name_question_requires_multiple_submissions",
            "submission_name_question_id IS NULL OR allow_multiple_submissions = true",
        )


def downgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.drop_constraint("ck_submission_name_question_requires_multiple_submissions", type_="check")
        batch_op.drop_constraint(batch_op.f("fk_collection_submission_name_question_id_component"), type_="foreignkey")
        batch_op.drop_column("submission_name_question_id")
        batch_op.drop_column("allow_multiple_submissions")
