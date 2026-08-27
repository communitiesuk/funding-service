"""Add eligibility type expression and its corresponding unique index

Revision ID: 082_add_eligibility_type_expr
Revises: 081_rename_user_mgmt_audit_event
Create Date: 2026-08-18 20:59:23.676298

"""

import sqlalchemy as sa
from alembic import op
from alembic_postgresql_enum import TableReference

revision = "082_add_eligibility_type_expr"
down_revision = "081_rename_user_mgmt_audit_event"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # These partial indexes reference expression_type_enum in their WHERE clause, so they must be dropped
    # before the enum type can be altered, and recreated afterwards.
    with op.batch_alter_table("expression", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_type_validation_unique_key",
            postgresql_where="type = 'VALIDATION'::expression_type_enum AND managed_name IS NOT NULL",
        )
        batch_op.drop_index(
            "uq_type_condition_unique_question",
            postgresql_where="type = 'CONDITION'::expression_type_enum AND managed_name IS NOT NULL",
        )

    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="expression_type_enum",
        new_values=["CONDITION", "VALIDATION", "ELIGIBILITY"],
        affected_columns=[TableReference(table_schema="public", table_name="expression", column_name="type")],
        enum_values_to_rename=[],
    )

    with op.batch_alter_table("expression", schema=None) as batch_op:
        batch_op.create_index(
            "uq_type_validation_unique_key",
            ["type", "question_id", "managed_name"],
            unique=True,
            postgresql_where="type = 'VALIDATION'::expression_type_enum AND managed_name IS NOT NULL",
        )
        batch_op.create_index(
            "uq_type_condition_unique_question",
            ["type", "question_id", "managed_name", sa.literal_column("(context ->> 'subject_reference')")],  # ty: ignore[invalid-argument-type]
            unique=True,
            postgresql_where="type = 'CONDITION'::expression_type_enum AND managed_name IS NOT NULL",
        )
        batch_op.create_index(
            "uq_type_eligibility_unique_question",
            ["question_id"],
            unique=True,
            postgresql_where="type = 'ELIGIBILITY'::expression_type_enum",
        )


def downgrade() -> None:
    with op.batch_alter_table("expression", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_type_eligibility_unique_question", postgresql_where="type = 'ELIGIBILITY'::expression_type_enum"
        )
        batch_op.drop_index(
            "uq_type_validation_unique_key",
            postgresql_where="type = 'VALIDATION'::expression_type_enum AND managed_name IS NOT NULL",
        )
        batch_op.drop_index(
            "uq_type_condition_unique_question",
            postgresql_where="type = 'CONDITION'::expression_type_enum AND managed_name IS NOT NULL",
        )

    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="expression_type_enum",
        new_values=["CONDITION", "VALIDATION"],
        affected_columns=[TableReference(table_schema="public", table_name="expression", column_name="type")],
        enum_values_to_rename=[],
    )

    with op.batch_alter_table("expression", schema=None) as batch_op:
        batch_op.create_index(
            "uq_type_validation_unique_key",
            ["type", "question_id", "managed_name"],
            unique=True,
            postgresql_where="type = 'VALIDATION'::expression_type_enum AND managed_name IS NOT NULL",
        )
        batch_op.create_index(
            "uq_type_condition_unique_question",
            ["type", "question_id", "managed_name", sa.literal_column("(context ->> 'subject_reference')")],  # ty: ignore[invalid-argument-type]
            unique=True,
            postgresql_where="type = 'CONDITION'::expression_type_enum AND managed_name IS NOT NULL",
        )
