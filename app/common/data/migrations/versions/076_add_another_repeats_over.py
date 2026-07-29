"""Add Component.add_another_repeats_over_component_id, and backfill add-another entries into an envelope shape

Revision ID: 076_add_another_repeats_over
Revises: 075_eligibility_section
Create Date: 2026-07-29 16:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "076_add_another_repeats_over"
down_revision = "075_eligibility_section"
branch_labels = None
depends_on = None

# Only the top-level `submission.data` keys that belong to an add-another container are transformed - a
# top-level list value could in principle be something else (eg a CHECKBOXES answer), so we look up
# container ids from the schema rather than shape-sniffing the JSON.
_CONTAINER_IDS_SUBQUERY = "(SELECT array_agg(id::text) FROM component WHERE add_another = true)"

_WRAP_ENTRIES_SQL = f"""
    UPDATE submission
    SET data = (
        SELECT COALESCE(
            jsonb_object_agg(
                kv.key,
                CASE
                    WHEN kv.key IN (SELECT id::text FROM component WHERE add_another = true)
                         AND jsonb_typeof(kv.value) = 'array'
                    THEN (
                        SELECT COALESCE(
                            jsonb_agg(
                                CASE
                                    WHEN jsonb_typeof(entry) = 'object' AND entry ? 'id' AND entry ? 'answers'
                                        THEN entry
                                    ELSE jsonb_build_object('id', gen_random_uuid()::text, 'answers', entry)
                                END
                            ),
                            '[]'::jsonb
                        )
                        FROM jsonb_array_elements(kv.value) AS entry
                    )
                    ELSE kv.value
                END
            ),
            '{{}}'::jsonb
        )
        FROM jsonb_each(submission.data) AS kv
    )
    WHERE data ?| {_CONTAINER_IDS_SUBQUERY}
"""

_UNWRAP_ENTRIES_SQL = f"""
    UPDATE submission
    SET data = (
        SELECT COALESCE(
            jsonb_object_agg(
                kv.key,
                CASE
                    WHEN kv.key IN (SELECT id::text FROM component WHERE add_another = true)
                         AND jsonb_typeof(kv.value) = 'array'
                    THEN (
                        SELECT COALESCE(
                            jsonb_agg(
                                CASE
                                    WHEN jsonb_typeof(entry) = 'object' AND entry ? 'id' AND entry ? 'answers'
                                        THEN entry -> 'answers'
                                    ELSE entry
                                END
                            ),
                            '[]'::jsonb
                        )
                        FROM jsonb_array_elements(kv.value) AS entry
                    )
                    ELSE kv.value
                END
            ),
            '{{}}'::jsonb
        )
        FROM jsonb_each(submission.data) AS kv
    )
    WHERE data ?| {_CONTAINER_IDS_SUBQUERY}
"""


def upgrade() -> None:
    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.add_column(sa.Column("add_another_repeats_over_component_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_component_add_another_repeats_over_component_id_component"),
            "component",
            ["add_another_repeats_over_component_id"],
            ["id"],
        )

    op.execute(_WRAP_ENTRIES_SQL)


def downgrade() -> None:
    op.execute(_UNWRAP_ENTRIES_SQL)

    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.drop_constraint("fk_component_add_another_repeats_over_component_id_component", type_="foreignkey")
        batch_op.drop_column("add_another_repeats_over_component_id")
