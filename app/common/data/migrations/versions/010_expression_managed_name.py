"""Surface the managed expression key and consider naming

Revision ID: 010_expression_managed_name
Revises: 009_unique_conditions
Create Date: 2025-06-25 19:00:20.136242

"""

import sqlalchemy as sa
from alembic import op

revision = "010_expression_managed_name"
down_revision = "009_unique_conditions"
branch_labels = None
depends_on = None

managed_name_enum = sa.Enum("GREATER_THAN", "LESS_THAN", "BETWEEN", name="managed_expression_enum")


def upgrade() -> None:
    managed_name_enum.create(op.get_bind())
    with op.batch_alter_table("expression", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "managed_name",
                managed_name_enum,
                nullable=True,
            )
        )
        batch_op.drop_index(
            "uq_type_condition_unique_question", postgresql_where="(type = 'CONDITION'::expression_type_enum)"
        )
        batch_op.create_index(
            "uq_type_condition_unique_question",
            ["type", "question_id", "managed_name", sa.literal_column("(context ->> 'question_id')")],
            unique=True,
            postgresql_where="type = 'CONDITION'::expression_type_enum",
        )
        batch_op.drop_index(
            "uq_type_validation_unique_key", postgresql_where="(type = 'VALIDATION'::expression_type_enum)"
        )
        batch_op.create_index(
            "uq_type_validation_unique_key",
            ["type", "question_id", "managed_name"],
            unique=True,
            postgresql_where="type = 'VALIDATION'::expression_type_enum",
        )

    op.execute(
        sa.text(
            """
                update expression set
                    managed_name = upper(replace((context->>'key'), ' ', '_'))::managed_expression_enum,
                    context = context - 'key'
                where managed_name is null and context ? 'key'
            """
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("expression", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_type_validation_unique_key", postgresql_where="type = 'VALIDATION'::expression_type_enum"
        )
        batch_op.create_index(
            "uq_type_validation_unique_key",
            ["type", "question_id", sa.literal_column("(context ->> 'key'::text)")],
            unique=True,
            postgresql_where="(type = 'VALIDATION'::expression_type_enum)",
        )
        batch_op.drop_index(
            "uq_type_condition_unique_question", postgresql_where="type = 'CONDITION'::expression_type_enum"
        )
        batch_op.create_index(
            "uq_type_condition_unique_question",
            [
                "type",
                "question_id",
                sa.literal_column("(context ->> 'key'::text)"),
                sa.literal_column("(context ->> 'question_id'::text)"),
            ],
            unique=True,
            postgresql_where="(type = 'CONDITION'::expression_type_enum)",
        )
        batch_op.drop_column("managed_name")
        managed_name_enum.drop(op.get_bind())
