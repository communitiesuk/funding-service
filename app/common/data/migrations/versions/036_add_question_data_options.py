"""Adding data_options column to component table

Revision ID: 036_add_question_data_options
Revises: 035_remove_static_event_data
Create Date: 2026-01-23 12:40:37.386356

"""

import sqlalchemy as sa
from alembic import op

from app.common.data.types import QuestionDataOptionsPostgresType

revision = "036_add_question_data_options"
down_revision = "035_remove_static_event_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "data_options",
                QuestionDataOptionsPostgresType(astext_type=sa.Text()),
                server_default="{}",
                nullable=True,
            )
        )
    op.execute(
        sa.text("""
                UPDATE component
                SET data_options = '{"allow_decimals"\\:false}'
                WHERE data_type = 'INTEGER'
                """)
    )


def downgrade() -> None:
    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.drop_column("data_options")
