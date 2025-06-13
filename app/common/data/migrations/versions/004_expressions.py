"""adds expression table

Revision ID: 004_expressions
Revises: 003_add_mode_to_submission_table
Create Date: 2025-06-13 16:24:06.666801

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "004_expressions"
down_revision = "003_add_mode_to_submission_table"
branch_labels = None
depends_on = None

expression_type_enum = sa.Enum("CONDITION", "VALIDATION", name="expression_type_enum")


def upgrade() -> None:
    op.create_table(
        "expression",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("statement", sa.String(), nullable=False),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("type", expression_type_enum, nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["user.id"], name=op.f("fk_expression_created_by_id_user")),
        sa.ForeignKeyConstraint(["question_id"], ["question.id"], name=op.f("fk_expression_question_id_question")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_expression")),
    )


def downgrade() -> None:
    op.drop_table("expression")
    expression_type_enum.drop(op.get_bind())
