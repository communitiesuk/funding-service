"""extends metadata enum

Revision ID: 006_metadata_enum
Revises: 005_collection_metadata
Create Date: 2025-06-04 14:56:07.802724

"""

import sqlalchemy as sa
from alembic import op

revision = "006_metadata_enum"
down_revision = "005_collection_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TYPE metadata_event_key_enum ADD VALUE 'COLLECTION_SUBMITTED'"))


def downgrade() -> None:
    pass
