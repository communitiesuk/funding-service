"""Make managed condition unique per question and key

Revision ID: 009_unique_conditions
Revises: 008_make_ggis_number_required
Create Date: 2025-06-25 17:41:03.706069

"""

import sqlalchemy as sa
from alembic import op

revision = "009_unique_conditions"
down_revision = "008_make_ggis_number_required"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("expression", schema=None) as batch_op:
        batch_op.create_index(
            "uq_type_condition_unique_question",
            [
                "type",
                "question_id",
                sa.literal_column("(context ->> 'key')"),
                sa.literal_column("(context ->> 'question_id')"),
            ],
            unique=True,
            postgresql_where="type = 'CONDITION'::expression_type_enum",
        )


def downgrade() -> None:
    with op.batch_alter_table("expression", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_type_condition_unique_question", postgresql_where="type = 'CONDITION'::expression_type_enum"
        )
