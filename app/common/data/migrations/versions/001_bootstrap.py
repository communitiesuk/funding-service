"""bootstrap the database

Revision ID: 001_bootstrap
Revises:
Create Date: 2025-06-09 15:57:45.818064

"""

import sqlalchemy as sa
from alembic import op
from alembic_utils.pg_extension import PGExtension
from sqlalchemy.dialects import postgresql

revision = "001_bootstrap"
down_revision = None
branch_labels = None
depends_on = None


question_data_type_enum = sa.Enum("TEXT_SINGLE_LINE", "TEXT_MULTI_LINE", "INTEGER", name="question_data_type_enum")
role_enum = sa.Enum("ADMIN", "MEMBER", "EDITOR", "ASSESSOR", "S151_OFFICER", name="role_enum")
submission_status_enum = sa.Enum("NOT_STARTED", "IN_PROGRESS", "COMPLETED", name="submission_status_enum")
submission_event_key_enum = sa.Enum(
    "FORM_RUNNER_FORM_COMPLETED", "SUBMISSION_SUBMITTED", name="submission_event_key_enum"
)


def upgrade() -> None:
    public_citext = PGExtension(schema="public", signature="citext")
    op.create_entity(public_citext)
    op.create_table(
        "grant",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("name", postgresql.CITEXT(), nullable=False),
        sa.Column("ggis_number", sa.String(), nullable=True),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("primary_contact_name", sa.String(), nullable=False),
        sa.Column("primary_contact_email", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grant")),
        sa.UniqueConstraint("name", name=op.f("uq_grant_name")),
    )
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
        "user",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user")),
        sa.UniqueConstraint("email", name=op.f("uq_user_email")),
    )
    op.create_table(
        "collection",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("grant_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["user.id"], name=op.f("fk_collection_created_by_id_user")),
        sa.ForeignKeyConstraint(["grant_id"], ["grant.id"], name=op.f("fk_collection_grant_id_grant")),
        sa.PrimaryKeyConstraint("id", "version", name=op.f("pk_collection")),
        sa.UniqueConstraint("name", "grant_id", "version", name="uq_collection_name_version_grant_id"),
    )
    op.create_table(
        "magic_link",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("redirect_to_path", sa.String(), nullable=False),
        sa.Column("expires_at_utc", sa.DateTime(), nullable=False),
        sa.Column("claimed_at_utc", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], name=op.f("fk_magic_link_user_id_user")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_magic_link")),
        sa.UniqueConstraint("code", name=op.f("uq_magic_link_code")),
    )
    with op.batch_alter_table("magic_link", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_magic_link_code"), ["code"], unique=True, postgresql_where="claimed_at_utc IS NOT NULL"
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
        sa.UniqueConstraint(
            "user_id",
            "organisation_id",
            "grant_id",
            "role",
            name="uq_user_org_grant_role",
            postgresql_nulls_not_distinct=True,
        ),
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

    op.create_table(
        "section",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column("collection_version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["collection_id", "collection_version"],
            ["collection.id", "collection.version"],
            name=op.f("fk_section_collection_id_collection"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_section")),
        sa.UniqueConstraint(
            "collection_id", "collection_version", "order", deferrable=True, name="uq_section_order_collection"
        ),
        sa.UniqueConstraint("collection_id", "collection_version", "slug", name="uq_section_slug_collection"),
        sa.UniqueConstraint("collection_id", "collection_version", "title", name="uq_section_title_collection"),
    )
    op.create_table(
        "submission",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", submission_status_enum, nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column("collection_version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["collection_id", "collection_version"],
            ["collection.id", "collection.version"],
            name=op.f("fk_submission_collection_id_collection"),
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["user.id"], name=op.f("fk_submission_created_by_id_user")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_submission")),
    )
    op.create_table(
        "form",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["section_id"], ["section.id"], name=op.f("fk_form_section_id_section")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_form")),
        sa.UniqueConstraint("order", "section_id", deferrable=True, name="uq_form_order_section"),
        sa.UniqueConstraint("slug", "section_id", name="uq_form_slug_section"),
        sa.UniqueConstraint("title", "section_id", name="uq_form_title_section"),
    )
    op.create_table(
        "question",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("hint", sa.String(), nullable=True),
        sa.Column(
            "data_type",
            question_data_type_enum,
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("form_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["form_id"], ["form.id"], name=op.f("fk_question_form_id_form")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question")),
        sa.UniqueConstraint("name", "form_id", name="uq_question_name_form"),
        sa.UniqueConstraint("order", "form_id", deferrable=True, name="uq_question_order_form"),
        sa.UniqueConstraint("slug", "form_id", name="uq_question_slug_form"),
        sa.UniqueConstraint("text", "form_id", name="uq_question_text_form"),
    )
    op.create_table(
        "submission_event",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "key",
            submission_event_key_enum,
            nullable=False,
        ),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("form_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["user.id"], name=op.f("fk_submission_event_created_by_id_user")),
        sa.ForeignKeyConstraint(["form_id"], ["form.id"], name=op.f("fk_submission_event_form_id_form")),
        sa.ForeignKeyConstraint(
            ["submission_id"], ["submission.id"], name=op.f("fk_submission_event_submission_id_submission")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_submission_event")),
    )


def downgrade() -> None:
    op.drop_table("submission_event")
    op.drop_table("question")
    op.drop_table("form")
    op.drop_table("submission")
    op.drop_table("section")
    with op.batch_alter_table("user_role", schema=None) as batch_op:
        batch_op.drop_index("ix_user_roles_user_id_organisation_id")
        batch_op.drop_index("ix_user_roles_user_id_grant_id")
        batch_op.drop_index("ix_user_roles_user_id")
        batch_op.drop_index("ix_user_roles_organisation_id_role_id_grant_id")
        batch_op.drop_index("ix_user_roles_organisation_id")
        batch_op.drop_index("ix_user_roles_grant_id")

    op.drop_table("user_role")
    with op.batch_alter_table("magic_link", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_magic_link_code"), postgresql_where="claimed_at_utc IS NOT NULL")

    op.drop_table("magic_link")
    op.drop_table("collection")
    op.drop_table("user")
    op.drop_table("organisation")
    op.drop_table("grant")

    question_data_type_enum.drop(op.get_bind())
    role_enum.drop(op.get_bind())
    submission_status_enum.drop(op.get_bind())
    submission_event_key_enum.drop(op.get_bind())

    public_citext = PGExtension(schema="public", signature="citext")
    op.drop_entity(public_citext)
