"""Refactor eligibility from a Collection type into an eligibility Form (section)

Revision ID: 075_eligibility_section
Revises: 074_rolling_submissions
Create Date: 2026-07-29 09:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from alembic_postgresql_enum import TableReference

revision = "075_eligibility_section"
down_revision = "074_rolling_submissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Data cleanup, before touching the enum. We delete ELIGIBILITY_CHECK collections and everything hanging off
    # them, rather than migrating the data, so grant teams re-add their eligibility questions as a new eligibility
    # section on the main collection.
    op.execute("UPDATE collection SET depends_on_collection_eligibility_id = NULL")
    op.execute("UPDATE collection SET requires_eligibility_check = false")

    op.execute("""
        DELETE FROM submission_event
        WHERE submission_id IN (
            SELECT id FROM submission
            WHERE collection_id IN (SELECT id FROM collection WHERE type = 'ELIGIBILITY_CHECK')
        )
    """)
    op.execute("""
        DELETE FROM submission
        WHERE collection_id IN (SELECT id FROM collection WHERE type = 'ELIGIBILITY_CHECK')
    """)
    op.execute("""
        DELETE FROM component_reference
        WHERE component_id IN (
            SELECT id FROM component
            WHERE form_id IN (
                SELECT id FROM form
                WHERE collection_id IN (SELECT id FROM collection WHERE type = 'ELIGIBILITY_CHECK')
            )
        )
        OR depends_on_component_id IN (
            SELECT id FROM component
            WHERE form_id IN (
                SELECT id FROM form
                WHERE collection_id IN (SELECT id FROM collection WHERE type = 'ELIGIBILITY_CHECK')
            )
        )
    """)
    op.execute("""
        DELETE FROM expression
        WHERE question_id IN (
            SELECT id FROM component
            WHERE form_id IN (
                SELECT id FROM form
                WHERE collection_id IN (SELECT id FROM collection WHERE type = 'ELIGIBILITY_CHECK')
            )
        )
    """)
    op.execute("""
        DELETE FROM component
        WHERE form_id IN (
            SELECT id FROM form
            WHERE collection_id IN (SELECT id FROM collection WHERE type = 'ELIGIBILITY_CHECK')
        )
    """)
    op.execute("""
        DELETE FROM form
        WHERE collection_id IN (SELECT id FROM collection WHERE type = 'ELIGIBILITY_CHECK')
    """)
    op.execute("DELETE FROM collection WHERE type = 'ELIGIBILITY_CHECK'")

    # 2. Drop the self-referential FK/column that linked a collection to its (now deleted) eligibility collection.
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.drop_constraint("fk_collection_depends_on_collection_eligibility_id_collection", type_="foreignkey")
        batch_op.drop_column("depends_on_collection_eligibility_id")

    # 3. Drop ELIGIBILITY_CHECK from the collection_type enum.
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

    # 4. Eligibility is now a flag on a Form (section) instead of a separate collection.
    with op.batch_alter_table("form", schema=None) as batch_op:
        batch_op.add_column(sa.Column("is_eligibility", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.create_index(
            "uq_form_eligibility_collection",
            ["collection_id"],
            unique=True,
            postgresql_where=sa.text("is_eligibility"),
        )


def downgrade() -> None:
    with op.batch_alter_table("form", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_form_eligibility_collection",
            postgresql_where=sa.text("is_eligibility"),
        )
        batch_op.drop_column("is_eligibility")

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

    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.add_column(sa.Column("depends_on_collection_eligibility_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_collection_depends_on_collection_eligibility_id_collection"),
            "collection",
            ["depends_on_collection_eligibility_id"],
            ["id"],
        )
