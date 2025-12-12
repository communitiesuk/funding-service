"""add live/test modes to org, grant recipient, and preview to submission

Revision ID: 032_entity_modes
Revises: 031_submission_references
Create Date: 2025-12-11 14:43:46.497947

"""

import sqlalchemy as sa
from alembic import op
from alembic_postgresql_enum import TableReference

revision = "032_entity_modes"
down_revision = "031_submission_references"
branch_labels = None
depends_on = None


grant_recipient_mode_enum = sa.Enum("LIVE", "TEST", name="grantrecipientmodeenum")
organisation_mode_enum = sa.Enum("LIVE", "TEST", name="organisationmodeenum")


def upgrade() -> None:
    grant_recipient_mode_enum.create(op.get_bind())
    organisation_mode_enum.create(op.get_bind())

    with op.batch_alter_table("grant_recipient", schema=None) as batch_op:
        batch_op.add_column(sa.Column("mode", grant_recipient_mode_enum, nullable=False, server_default="LIVE"))

    with op.batch_alter_table("organisation", schema=None) as batch_op:
        batch_op.add_column(sa.Column("mode", organisation_mode_enum, nullable=False, server_default="LIVE"))

    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="submission_mode_enum",
        new_values=["TEST", "PREVIEW", "LIVE"],
        affected_columns=[TableReference(table_schema="public", table_name="submission", column_name="mode")],
        enum_values_to_rename=[],
    )

    op.execute("UPDATE submission SET mode = 'PREVIEW' WHERE mode = 'TEST'")

    op.create_check_constraint(
        "ck_grant_recipient_if_live", "submission", "mode = 'PREVIEW' OR grant_recipient_id IS NOT NULL"
    )


def downgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="submission_mode_enum",
        new_values=["TEST", "LIVE"],
        affected_columns=[TableReference(table_schema="public", table_name="submission", column_name="mode")],
        enum_values_to_rename=[],
    )

    op.execute("DELETE FROM submission WHERE mode = 'PREVIEW' OR mode = 'TEST'")

    with op.batch_alter_table("organisation", schema=None) as batch_op:
        batch_op.drop_column("mode")

    with op.batch_alter_table("grant_recipient", schema=None) as batch_op:
        batch_op.drop_column("mode")

    organisation_mode_enum.drop(op.get_bind())
    grant_recipient_mode_enum.drop(op.get_bind())

    op.create_check_constraint(
        "ck_grant_recipient_if_live", "submission", "mode = 'TEST' OR grant_recipient_id IS NOT NULL"
    )
