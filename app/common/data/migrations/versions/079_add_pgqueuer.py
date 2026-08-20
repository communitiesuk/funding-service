"""Add pgqueuer

Revision ID: 079_add_pgqueuer
Revises: 078_add_collection_id_magic_link
Create Date: 2026-08-12 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "079_add_pgqueuer"
down_revision = "078_add_collection_id_magic_link"
branch_labels = None
depends_on = None

pgqueuer_status = sa.Enum(
    "queued",
    "picked",
    "successful",
    "exception",
    "canceled",
    "deleted",
    "failed",
    name="pgqueuer_status",
)


def upgrade() -> None:
    # This is pgqueuer's schema translated into our Alembic migration flow. These tables should stay close to what
    # pgqueuer expects, app-specific job state belongs on our own models instead.
    pgqueuer_status.create(op.get_bind())

    op.create_table(
        "pgqueuer",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("queue_manager_id", sa.Uuid(), nullable=True),
        sa.Column("created", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("heartbeat", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("execute_after", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="pgqueuer_status", create_type=False),
            nullable=False,
        ),
        sa.Column("entrypoint", sa.Text(), nullable=False),
        sa.Column("dedupe_key", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.BYTEA(), nullable=True),
        sa.Column("headers", postgresql.JSONB(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
    )

    op.execute(
        """
        CREATE INDEX pgqueuer_priority_id_id1_idx
        ON pgqueuer (priority ASC, id DESC)
        INCLUDE (id)
        WHERE status = 'queued'
        """
    )
    op.execute(
        """
        CREATE INDEX pgqueuer_updated_id_id1_idx
        ON pgqueuer (updated ASC, id DESC)
        INCLUDE (id)
        WHERE status = 'picked'
        """
    )
    op.create_index(
        "pgqueuer_queue_manager_id_idx",
        "pgqueuer",
        ["queue_manager_id"],
        postgresql_where=sa.text("queue_manager_id IS NOT NULL"),
    )
    op.execute(
        """
        CREATE INDEX pgqueuer_ep_prio_id_idx
        ON pgqueuer (entrypoint, priority DESC, id ASC)
        WHERE status = 'queued'
        """
    )
    op.create_index(
        "pgqueuer_ep_ea_idx",
        "pgqueuer",
        ["entrypoint", "execute_after"],
        postgresql_where=sa.text("status = 'queued'"),
    )
    op.create_index(
        "pgqueuer_unique_dedupe_key",
        "pgqueuer",
        ["dedupe_key"],
        unique=True,
        postgresql_where=sa.text("((status IN ('queued', 'picked') AND dedupe_key IS NOT NULL))"),
    )

    op.create_table(
        "pgqueuer_log",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("created", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("job_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="pgqueuer_status", create_type=False),
            nullable=False,
        ),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("entrypoint", sa.Text(), nullable=False),
        sa.Column("traceback", postgresql.JSONB(), nullable=True),
        sa.Column("aggregated", sa.Boolean(), server_default=sa.false(), nullable=True),
    )

    op.create_index(
        "pgqueuer_log_not_aggregated",
        "pgqueuer_log",
        ["entrypoint", "priority", "status", "created"],
        postgresql_where=sa.text("not aggregated"),
    )
    op.create_index("pgqueuer_log_created", "pgqueuer_log", ["created"])
    op.create_index("pgqueuer_log_status", "pgqueuer_log", ["status"])
    op.execute("CREATE INDEX pgqueuer_log_job_id_status ON pgqueuer_log (job_id, created DESC)")

    op.create_table(
        "pgqueuer_statistics",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "created",
            sa.DateTime(timezone=True),
            server_default=sa.text("DATE_TRUNC('sec', NOW() at time zone 'UTC')"),
            nullable=False,
        ),
        sa.Column("count", sa.BigInteger(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="pgqueuer_status", create_type=False),
            nullable=False,
        ),
        sa.Column("entrypoint", sa.Text(), nullable=False),
    )
    op.execute(
        """
        CREATE UNIQUE INDEX pgqueuer_statistics_unique_count
        ON pgqueuer_statistics (
            priority,
            DATE_TRUNC('sec', created at time zone 'UTC'),
            status,
            entrypoint
        )
        """
    )

    op.create_table(
        "pgqueuer_schedules",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("expression", sa.Text(), nullable=False),
        sa.Column("entrypoint", sa.Text(), nullable=False),
        sa.Column("heartbeat", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("next_run", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_run", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(name="pgqueuer_status", create_type=False),
            server_default="queued",
            nullable=True,
        ),
        sa.UniqueConstraint("expression", "entrypoint", name="uq_pgqueuer_schedules_expression_entrypoint"),
    )

    op.execute(
        """
        CREATE FUNCTION fn_pgqueuer_changed() RETURNS TRIGGER AS $$
        BEGIN
            PERFORM pg_notify(
                'ch_pgqueuer',
                json_build_object(
                    'channel', 'ch_pgqueuer',
                    'operation', lower(TG_OP),
                    'sent_at', NOW(),
                    'table', TG_TABLE_NAME,
                    'type', 'table_changed_event'
                )::text
            );

            IF TG_OP IN ('INSERT', 'UPDATE') THEN
                RETURN NEW;
            ELSIF TG_OP = 'DELETE' THEN
                RETURN OLD;
            ELSE
                RETURN NULL;
            END IF;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER tg_pgqueuer_changed
        AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE ON pgqueuer
        EXECUTE FUNCTION fn_pgqueuer_changed()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS tg_pgqueuer_changed ON pgqueuer")
    op.execute("DROP FUNCTION IF EXISTS fn_pgqueuer_changed")
    op.drop_table("pgqueuer_schedules")
    op.drop_table("pgqueuer_statistics")
    op.drop_table("pgqueuer_log")
    op.drop_table("pgqueuer")
    pgqueuer_status.drop(op.get_bind())
