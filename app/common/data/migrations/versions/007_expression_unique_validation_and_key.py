"""unique constraint on managed validation expressions to limit to one of each type per question

Revision ID: 007_expression_eq_validation_key
Revises: 006_add_user_azure_ad_id
Create Date: 2025-06-19 21:26:41.167609

"""

import sqlalchemy as sa
from alembic import op

revision = "007_expression_eq_validation_key"
down_revision = "006_add_user_azure_ad_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("expression", schema=None) as batch_op:
        batch_op.create_index(
            "uq_type_validation_unique_key",
            ["type", "question_id", sa.literal_column("(context ->> 'key')")],
            unique=True,
            postgresql_where="type = 'VALIDATION'::expression_type_enum",
        )


def downgrade() -> None:
    with op.batch_alter_table("expression", schema=None) as batch_op:
        batch_op.drop_index("uq_type_validation_unique_key", postgresql_where="type = 'VALIDATION'")
