"""empty message

Revision ID: 013_data_sources
Revises: 012_adding_invitations_table
Create Date: 2025-07-11 15:20:50.618430

"""

import sqlalchemy as sa
from alembic import op

revision = "013_data_sources"
down_revision = "012_adding_invitations_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_source",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["question_id"], ["question.id"], name=op.f("fk_data_source_question_id_question")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_source")),
        sa.UniqueConstraint("question_id", name="uq_question_id"),
    )
    op.create_table(
        "data_source_item",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("data_source_id", sa.Uuid(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["data_source_id"], ["data_source.id"], name=op.f("fk_data_source_item_data_source_id_data_source")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_source_item")),
        sa.UniqueConstraint("data_source_id", "key", name="uq_data_source_id_key"),
        sa.UniqueConstraint("data_source_id", "order", deferrable=True, name="uq_data_source_id_order"),
    )


def downgrade() -> None:
    op.drop_table("data_source_item")
    op.drop_table("data_source")
