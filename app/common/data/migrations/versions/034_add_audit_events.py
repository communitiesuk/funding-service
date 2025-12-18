"""add audit events

Revision ID: 034_add_audit_events
Revises: 033_grant_privacy_policies
Create Date: 2025-12-19 09:38:37.764854

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "034_add_audit_events"
down_revision = "033_grant_privacy_policies"
branch_labels = None
depends_on = None

audit_event_enum = postgresql.ENUM("PLATFORM_ADMIN_DB_EVENT", name="auditeventtype", create_type=False)


def upgrade() -> None:
    sa.Enum("PLATFORM_ADMIN_DB_EVENT", name="auditeventtype").create(op.get_bind())
    op.create_table(
        "audit_event",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "event_type",
            audit_event_enum,
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], name=op.f("fk_audit_event_user_id_user")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_event")),
    )
    with op.batch_alter_table("audit_event", schema=None) as batch_op:
        batch_op.create_index("ix_audit_event_created_at_utc", ["created_at_utc"], unique=False)
        batch_op.create_index("ix_audit_event_data_action", [sa.literal_column("(data->>'action')")], unique=False)
        batch_op.create_index(
            "ix_audit_event_data_model_class", [sa.literal_column("(data->>'model_class')")], unique=False
        )
        batch_op.create_index("ix_audit_event_event_type", ["event_type"], unique=False)
        batch_op.create_index("ix_audit_event_user_id", ["user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("audit_event", schema=None) as batch_op:
        batch_op.drop_index("ix_audit_event_user_id")
        batch_op.drop_index("ix_audit_event_event_type")
        batch_op.drop_index("ix_audit_event_data_model_class")
        batch_op.drop_index("ix_audit_event_data_action")
        batch_op.drop_index("ix_audit_event_created_at_utc")

    op.drop_table("audit_event")
    audit_event_enum.drop(op.get_bind())
