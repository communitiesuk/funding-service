"""Add question table

Revision ID: 009_add_question
Revises: 008_add_userrole_org_tables
Create Date: 2025-05-20 14:18:02.989992

"""

import sqlalchemy as sa
from alembic import op

revision = "009_add_question"
down_revision = "008_add_userrole_org_tables"
branch_labels = None
depends_on = None

question_data_type_enum = sa.Enum("TEXT_SINGLE_LINE", "INTEGER", "TEXT_MULTI_LINE", name="question_data_type_enum")


def upgrade() -> None:
    op.create_table(
        "question",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("hint", sa.String(), nullable=True),
        sa.Column(
            "data_type",
            question_data_type_enum,
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("form_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["form_id"], ["form.id"], name=op.f("fk_question_form_id_form")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question")),
        sa.UniqueConstraint("name", "form_id", name="uq_question_name_form"),
        sa.UniqueConstraint("text", "form_id", name="uq_question_text_form"),
        sa.UniqueConstraint("order", "form_id", deferrable=True, name="uq_question_order_form"),
        sa.UniqueConstraint("slug", "form_id", name="uq_question_slug_form"),
    )


def downgrade() -> None:
    op.drop_table("question")
    question_data_type_enum.drop(op.get_bind())
