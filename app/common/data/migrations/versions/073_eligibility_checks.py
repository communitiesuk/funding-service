"""Add eligibility check collections

Revision ID: 073_eligibility_checks
Revises: 072_validate_submission
Create Date: 2026-07-15 09:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from alembic_postgresql_enum import TableReference

revision = "073_eligibility_checks"
down_revision = "072_validate_submission"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.drop_constraint("ck_monitoring_certification_not_null")

    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="collection_type",
        new_values=["MONITORING_REPORT", "APPLICATION", "ELIGIBILITY_CHECK"],
        affected_columns=[TableReference(table_schema="public", table_name="collection", column_name="type")],
        enum_values_to_rename=[],
    )

    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.create_check_constraint(
            op.f("ck_monitoring_certification_not_null"),
            "requires_certification IS NOT NULL OR type != 'MONITORING_REPORT'",
        )

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

    op.drop_constraint("ck_grant_recipient_if_live", "submission", type_="check")

    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("requires_eligibility_check", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(sa.Column("depends_on_collection_eligibility_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_collection_depends_on_collection_eligibility_id_collection"),
            "collection",
            ["depends_on_collection_eligibility_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_collection_depends_on_collection_eligibility_id_collection"), type_="foreignkey"
        )
        batch_op.drop_column("depends_on_collection_eligibility_id")
        batch_op.drop_column("requires_eligibility_check")

    op.create_check_constraint(
        "ck_grant_recipient_if_live", "submission", "mode = 'TEST' OR grant_recipient_id IS NOT NULL"
    )

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

    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.drop_constraint("ck_monitoring_certification_not_null")

    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="collection_type",
        new_values=["MONITORING_REPORT", "APPLICATION"],
        affected_columns=[TableReference(table_schema="public", table_name="collection", column_name="type")],
        enum_values_to_rename=[],
    )

    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.create_check_constraint(
            op.f("ck_monitoring_certification_not_null"),
            "requires_certification IS NOT NULL OR type != 'MONITORING_REPORT'",
        )
