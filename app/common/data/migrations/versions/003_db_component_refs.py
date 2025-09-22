"""store references to components in the DB so that FKs can prevent deletion of used components

Revision ID: 003_db_component_refs
Revises: 002_add_date_type
Create Date: 2025-09-22 14:43:28.444072

"""

import sqlalchemy as sa
from alembic import op

revision = "003_db_component_refs"
down_revision = "002_add_date_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "component_reference",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("component_id", sa.Uuid(), nullable=False),
        sa.Column("depends_on_component_id", sa.Uuid(), nullable=False),
        sa.Column("expression_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["component_id"], ["component.id"], name=op.f("fk_component_reference_component_id_component")
        ),
        sa.ForeignKeyConstraint(
            ["expression_id"], ["expression.id"], name=op.f("fk_component_reference_expression_id_expression")
        ),
        sa.ForeignKeyConstraint(
            ["depends_on_component_id"],
            ["component.id"],
            name=op.f("fk_component_reference_depends_on_component_id_component"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_component_reference")),
    )


def downgrade() -> None:
    op.drop_table("component_reference")
