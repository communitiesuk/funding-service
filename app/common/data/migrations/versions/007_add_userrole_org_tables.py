"""Add UserRole table and stub Organisation table

Revision ID: 007_add_userrole_org_tables
Revises: 006_add_collection_schema
Create Date: 2025-05-14 16:38:10.925388

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "007_add_userrole_org_tables"
down_revision = "006_add_collection_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organisation",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("name", postgresql.CITEXT(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organisation")),
        sa.UniqueConstraint("name", name=op.f("uq_organisation_name")),
    )
    op.create_table(
        "user_role",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=True),
        sa.Column("grant_id", sa.Uuid(), nullable=True),
        sa.Column(
            "role", sa.Enum("ADMIN", "MEMBER", "EDITOR", "ASSESSOR", "S151_OFFICER", name="role_enum"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["grant_id"], ["grant.id"], name=op.f("fk_user_role_grant_id_grant"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organisation.id"], name=op.f("fk_user_role_org_id_organisation"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], name=op.f("fk_user_role_user_id_user"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_role")),
        sa.UniqueConstraint("user_id", "org_id", "grant_id", "role", name="uq_user_org_grant_role"),
    )
    with op.batch_alter_table("user_role", schema=None) as batch_op:
        batch_op.create_index("ix_user_roles_grant_id", ["grant_id"], unique=False)
        batch_op.create_index("ix_user_roles_org_id", ["org_id"], unique=False)
        batch_op.create_index("ix_user_roles_user_id", ["user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("user_role", schema=None) as batch_op:
        batch_op.drop_index("ix_user_roles_user_id")
        batch_op.drop_index("ix_user_roles_org_id")
        batch_op.drop_index("ix_user_roles_grant_id")

    op.drop_table("user_role")
    op.drop_table("organisation")
    op.execute("drop type role_enum")
