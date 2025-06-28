"""update expressions enum

Revision ID: 012_mentions_word
Revises: 011_mentions_grass
Create Date: 2025-06-28 10:47:35.458764

"""

from alembic import op
from sqlalchemy import text

revision = "012_mentions_word"
down_revision = "011_mentions_grass"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # todo: regenerate after merging https://github.com/communitiesuk/funding-service/pull/397
    op.execute(text("ALTER TYPE managed_expression_enum ADD VALUE 'MENTIONS_SOME_WORD'"))


def downgrade() -> None:
    # TODO: write me
    pass
