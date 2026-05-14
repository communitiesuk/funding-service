"""empty message

Revision ID: 061_pre_award_collections
Revises: 060_notify_cleanup_audit_event
Create Date: 2026-05-14 10:22:50.502015

"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "061_pre_award_collections"
down_revision = "060_notify_cleanup_audit_event"
branch_labels = None
depends_on = None


def upgrade() -> None:
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


def downgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="collection_type",
        new_values=["MONITORING_REPORT"],
        affected_columns=[TableReference(table_schema="public", table_name="collection", column_name="type")],
        enum_values_to_rename=[],
    )
