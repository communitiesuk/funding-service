"""add conditions operator

Revision ID: 028_add_conditions_operator
Revises: 027_requires_certification_flag
Create Date: 2025-11-25 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "028_add_conditions_operator"
down_revision = "027_requires_certification_flag"
branch_labels = None
depends_on = None

conditions_operator_enum = postgresql.ENUM("ALL", "ANY", name="conditions_operator_enum", create_type=False)


def upgrade() -> None:
    conditions_operator_enum.create(op.get_bind())
    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.add_column(sa.Column("conditions_operator", conditions_operator_enum, nullable=True))

    op.execute("""UPDATE "component" SET conditions_operator='ALL'""")

    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.alter_column("conditions_operator", existing_nullable=True, nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.drop_column("conditions_operator")

    conditions_operator_enum.drop(op.get_bind())
