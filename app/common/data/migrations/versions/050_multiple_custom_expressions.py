"""Adjust the index on validation expressions to allow multiple custom validations per question.

Revision ID: 050_multiple_custom_expressions
Revises: 049_uploaded_datasource
Create Date: 2026-02-09 12:47:40.332189

"""

import sqlalchemy as sa
from alembic import op

revision = "050_multiple_custom_expressions"
down_revision = "049_uploaded_datasource"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("uq_type_validation_unique_key", table_name="expression")
    op.drop_index("uq_type_condition_unique_question", table_name="expression")
    op.create_index(
        "uq_type_validation_unique_key",
        "expression",
        ["type", "question_id", "managed_name"],
        unique=True,
        postgresql_where=("type = 'VALIDATION'::expression_type_enum AND managed_name IS NOT NULL "),
    )

    op.create_index(
        "uq_type_condition_unique_question",
        "expression",
        ["type", "question_id", "managed_name", sa.literal_column("(context ->> 'question_id')")],
        unique=True,
        postgresql_where=("type = 'CONDITION'::expression_type_enum AND managed_name IS NOT NULL "),
    )


def downgrade() -> None:
    op.drop_index("uq_type_validation_unique_key", table_name="expression")
    op.drop_index("uq_type_condition_unique_question", table_name="expression")
    op.create_index(
        "uq_type_validation_unique_key",
        "expression",
        ["type", "question_id", "managed_name"],
        unique=True,
        postgresql_where="type = 'VALIDATION'::expression_type_enum",
    )
    op.create_index(
        "uq_type_condition_unique_question",
        "expression",
        ["type", "question_id", "managed_name", sa.literal_column("(context ->> 'question_id')")],
        unique=True,
        postgresql_where="type = 'CONDITION'::expression_type_enum",
    )
