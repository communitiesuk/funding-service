"""update expressions enum

Revision ID: 011_mentions_grass
Revises: 010_expression_managed_name
Create Date: 2025-06-28 10:47:35.458764

"""

from alembic import op
from sqlalchemy import text

revision = "011_mentions_grass"
down_revision = "010_expression_managed_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # todo: regenerate after merging https://github.com/communitiesuk/funding-service/pull/397
    op.execute(text("ALTER TYPE managed_expression_enum ADD VALUE 'MENTIONS_GRASS'"))


def downgrade() -> None:
    pass
