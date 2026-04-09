"""delete self component refs

Revision ID: 055_delete_self_component_refs
Revises: 054_allow_public_sign_up
Create Date: 2026-04-09 14:06:37.697095

"""

from alembic import op

revision = "055_delete_self_component_refs"
down_revision = "054_allow_public_sign_up"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM component_reference WHERE component_id = depends_on_component_id")


def downgrade() -> None:
    pass
