"""empty message

Revision ID: 014_do_it
Revises: 013_do_it
Create Date: 2025-07-08 11:20:02.190825

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "014_do_it"
down_revision = "013_do_it"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_source",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["question_id"], ["question.id"], name=op.f("fk_data_source_question_id_question")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_source")),
    )


def downgrade() -> None:
    op.drop_table("data_source")
