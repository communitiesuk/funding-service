"""Add background jobs

Revision ID: 079_add_background_jobs
Revises: 078_add_collection_id_magic_link
Create Date: 2026-08-11 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "079_add_background_jobs"
down_revision = "078_add_collection_id_magic_link"
branch_labels = None
depends_on = None

background_job_type_enum = sa.Enum("OPEN_COLLECTION_FOR_SUBMISSIONS", name="background_job_type")
background_job_status_enum = sa.Enum("PENDING", "RUNNING", "COMPLETED", "FAILED", name="background_job_status")


def upgrade() -> None:
    background_job_type_enum.create(op.get_bind())
    background_job_status_enum.create(op.get_bind())

    op.create_table(
        "background_job",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "job_type",
            postgresql.ENUM("OPEN_COLLECTION_FOR_SUBMISSIONS", name="background_job_type", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "PENDING", "RUNNING", "COMPLETED", "FAILED", name="background_job_status", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("run_after_utc", sa.DateTime(), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_at_utc", sa.DateTime(), nullable=True),
        sa.Column("completed_at_utc", sa.DateTime(), nullable=True),
        sa.Column("failed_at_utc", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("collection_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["collection_id"], ["collection.id"], name=op.f("fk_background_job_collection_id_collection")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_background_job")),
        sa.UniqueConstraint("idempotency_key", name="uq_background_job_idempotency_key"),
    )
    op.create_index("ix_background_job_pending", "background_job", ["status", "run_after_utc"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_background_job_pending", table_name="background_job")
    op.drop_table("background_job")
    background_job_status_enum.drop(op.get_bind())
    background_job_type_enum.drop(op.get_bind())
