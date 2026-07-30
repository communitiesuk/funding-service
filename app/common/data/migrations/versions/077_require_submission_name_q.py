"""Require a submission name question when multiple submissions are enabled

Revision ID: 077_require_submission_name_q
Revises: 076_add_prospector_url_col
Create Date: 2026-07-30 11:00:00.000000

"""

from alembic import op

revision = "077_require_submission_name_q"
down_revision = "076_add_prospector_url_col"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_multiple_submissions_requires_name_question",
            "allow_multiple_submissions = false OR submission_name_question_id IS NOT NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.drop_constraint("ck_multiple_submissions_requires_name_question", type_="check")
