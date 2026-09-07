"""Track created_by user on Invitations

Revision ID: 084_invitation_created_by
Revises: 083_add_name_to_invitation
Create Date: 2026-09-07 15:37:33.822078

"""

import sqlalchemy as sa
from alembic import op
from flask import current_app

revision = "084_invitation_created_by"
down_revision = "083_add_name_to_invitation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    system_user_email = current_app.config["SYSTEM_USER_EMAIL"]
    system_user_name = current_app.config["SYSTEM_USER_NAME"]

    with op.batch_alter_table("invitation", schema=None) as batch_op:
        batch_op.add_column(sa.Column("created_by_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(batch_op.f("fk_invitation_created_by_id_user"), "user", ["created_by_id"], ["id"])

    # Only create the system user if there are invitations to backfill
    op.execute(
        sa.text(
            """
            INSERT INTO "user" (id, email, name)
            SELECT gen_random_uuid(), :email, :name
            WHERE EXISTS (SELECT 1 FROM invitation WHERE created_by_id IS NULL)
            ON CONFLICT (email) DO NOTHING
            """
        ).bindparams(email=system_user_email, name=system_user_name)
    )
    op.execute(
        sa.text(
            """
            UPDATE invitation
            SET created_by_id = (SELECT id FROM "user" WHERE email = :email)
            WHERE created_by_id IS NULL
            """
        ).bindparams(email=system_user_email)
    )

    with op.batch_alter_table("invitation", schema=None) as batch_op:
        batch_op.alter_column("created_by_id", existing_type=sa.Uuid(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("invitation", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_invitation_created_by_id_user"), type_="foreignkey")
        batch_op.drop_column("created_by_id")
