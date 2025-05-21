"""Add UserRole table and stub Organisation table

Revision ID: 008_add_userrole_org_tables
Revises: 007_add_section_form
Create Date: 2025-05-20 10:32:50.241292

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "008_add_userrole_org_tables"
down_revision = "007_add_section_form"
branch_labels = None
depends_on = None

role_enum = sa.Enum("ADMIN", "MEMBER", "EDITOR", "ASSESSOR", "S151_OFFICER", name="role_enum")


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
        sa.Column("organisation_id", sa.Uuid(), nullable=True),
        sa.Column("grant_id", sa.Uuid(), nullable=True),
        sa.Column("role", role_enum, nullable=False),
        sa.CheckConstraint(
            "role != 'ASSESSOR' OR (organisation_id IS NULL AND grant_id IS NOT NULL)",
            name=op.f("ck_user_role_assessor_role_grant_only"),
        ),
        sa.CheckConstraint(
            "role != 'MEMBER' OR NOT (organisation_id IS NULL AND grant_id IS NULL)",
            name=op.f("ck_user_role_member_role_not_platform"),
        ),
        sa.CheckConstraint(
            "role != 'S151_OFFICER' OR (organisation_id IS NOT NULL AND grant_id IS NULL)",
            name=op.f("ck_user_role_s151_officer_role_org_only"),
        ),
        sa.ForeignKeyConstraint(
            ["grant_id"], ["grant.id"], name=op.f("fk_user_role_grant_id_grant"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisation.id"],
            name=op.f("fk_user_role_organisation_id_organisation"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], name=op.f("fk_user_role_user_id_user"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_role")),
        sa.UniqueConstraint("user_id", "organisation_id", "grant_id", "role", name="uq_user_org_grant_role"),
    )
    with op.batch_alter_table("user_role", schema=None) as batch_op:
        batch_op.create_index("ix_user_roles_grant_id", ["grant_id"], unique=False)
        batch_op.create_index("ix_user_roles_organisation_id", ["organisation_id"], unique=False)
        batch_op.create_index(
            "ix_user_roles_organisation_id_role_id_grant_id", ["user_id", "organisation_id", "grant_id"], unique=False
        )
        batch_op.create_index("ix_user_roles_user_id", ["user_id"], unique=False)
        batch_op.create_index("ix_user_roles_user_id_grant_id", ["user_id", "grant_id"], unique=False)
        batch_op.create_index("ix_user_roles_user_id_organisation_id", ["user_id", "organisation_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("user_role", schema=None) as batch_op:
        batch_op.drop_index("ix_user_roles_user_id_organisation_id")
        batch_op.drop_index("ix_user_roles_user_id_grant_id")
        batch_op.drop_index("ix_user_roles_user_id")
        batch_op.drop_index("ix_user_roles_organisation_id_role_id_grant_id")
        batch_op.drop_index("ix_user_roles_organisation_id")
        batch_op.drop_index("ix_user_roles_grant_id")

    op.drop_table("user_role")
    op.drop_table("organisation")
    op.execute(sa.text("DROP TYPE IF EXISTS role_enum"))
