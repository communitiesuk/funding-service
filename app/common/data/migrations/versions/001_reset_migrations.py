"""reset migrations

Revision ID: 001_reset_migrations
Revises: 035_remove_sections
Create Date: 2025-09-02 12:57:53.427819

"""

import sqlalchemy as sa
from alembic import op
from alembic_utils.pg_extension import PGExtension
from sqlalchemy.dialects import postgresql

from app.common.data.types import QuestionOptionsPostgresType

revision = "001_reset_migrations"
down_revision = None
branch_labels = None
depends_on = None

collection_type_enum = postgresql.ENUM("MONITORING_REPORT", name="collection_type", create_type=False)
component_type_enum = postgresql.ENUM("QUESTION", "GROUP", name="component_type_enum", create_type=False)
expression_type_enum = postgresql.ENUM("CONDITION", "VALIDATION", name="expression_type_enum", create_type=False)
managed_expression_enum = postgresql.ENUM(
    "GREATER_THAN",
    "LESS_THAN",
    "BETWEEN",
    "IS_YES",
    "IS_NO",
    "ANY_OF",
    "SPECIFICALLY",
    name="managed_expression_enum",
    create_type=False,
)
question_data_type_enum = postgresql.ENUM(
    "TEXT_SINGLE_LINE",
    "TEXT_MULTI_LINE",
    "EMAIL",
    "URL",
    "INTEGER",
    "YES_NO",
    "RADIOS",
    "CHECKBOXES",
    name="question_data_type_enum",
    create_type=False,
)
role_enum = postgresql.ENUM("ADMIN", "MEMBER", name="role_enum", create_type=False)
submission_event_key_enum = postgresql.ENUM(
    "FORM_RUNNER_FORM_COMPLETED", "SUBMISSION_SUBMITTED", name="submission_event_key_enum", create_type=False
)
submission_mode_enum = postgresql.ENUM("TEST", "LIVE", name="submission_mode_enum", create_type=False)


def upgrade() -> None:
    public_citext = PGExtension(schema="public", signature="citext")
    op.create_entity(public_citext)  # ty: ignore[unresolved-attribute]

    collection_type_enum.create(op.get_bind())
    component_type_enum.create(op.get_bind())
    expression_type_enum.create(op.get_bind())
    managed_expression_enum.create(op.get_bind())
    question_data_type_enum.create(op.get_bind())
    role_enum.create(op.get_bind())
    submission_event_key_enum.create(op.get_bind())
    submission_mode_enum.create(op.get_bind())

    op.create_table(
        "grant",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("ggis_number", sa.String(), nullable=False),
        sa.Column("name", postgresql.CITEXT(), nullable=False),
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
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("azure_ad_subject_id", sa.String(), nullable=True),
        sa.Column("last_logged_in_at_utc", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user")),
        sa.UniqueConstraint("azure_ad_subject_id", name=op.f("uq_user_azure_ad_subject_id")),
        sa.UniqueConstraint("email", name=op.f("uq_user_email")),
    )
    op.create_table(
        "collection",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("type", collection_type_enum, nullable=False),
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
        "invitation",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("organisation_id", sa.Uuid(), nullable=True),
        sa.Column("grant_id", sa.Uuid(), nullable=True),
        sa.Column("role", role_enum, nullable=False),
        sa.Column("expires_at_utc", sa.DateTime(), nullable=False),
        sa.Column("claimed_at_utc", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["grant_id"], ["grant.id"], name=op.f("fk_invitation_grant_id_grant"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisation.id"],
            name=op.f("fk_invitation_organisation_id_organisation"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], name=op.f("fk_invitation_user_id_user")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invitation")),
    )
    op.create_table(
        "magic_link",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
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
            "role != 'MEMBER' OR NOT (organisation_id IS NULL AND grant_id IS NULL)",
            name=op.f("ck_user_role_member_role_not_platform"),
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
            "user_id", "organisation_id", "grant_id", name="uq_user_org_grant", postgresql_nulls_not_distinct=True
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
        "form",
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
            name=op.f("fk_form_collection_id_collection"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_form")),
        sa.UniqueConstraint(
            "order", "collection_id", "collection_version", deferrable=True, name="uq_form_order_collection"
        ),
        sa.UniqueConstraint("slug", "collection_id", "collection_version", name="uq_form_slug_collection"),
        sa.UniqueConstraint("title", "collection_id", "collection_version", name="uq_form_title_collection"),
    )
    op.create_table(
        "submission",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("mode", submission_mode_enum, nullable=False),
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
        "component",
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
            nullable=True,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("form_id", sa.Uuid(), nullable=False),
        sa.Column(
            "presentation_options",
            QuestionOptionsPostgresType(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("type", component_type_enum, nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("guidance_heading", sa.String(), nullable=True),
        sa.Column("guidance_body", sa.String(), nullable=True),
        sa.CheckConstraint(
            "data_type IS NOT NULL OR type != 'QUESTION'",
            name=op.f("ck_component_ck_component_type_question_requires_data_type"),
        ),
        sa.ForeignKeyConstraint(["form_id"], ["form.id"], name=op.f("fk_component_form_id_form")),
        sa.ForeignKeyConstraint(["parent_id"], ["component.id"], name=op.f("fk_component_parent_id_component")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_component")),
        sa.UniqueConstraint("name", "form_id", name="uq_component_name_form"),
        sa.UniqueConstraint("order", "parent_id", "form_id", deferrable=True, name="uq_component_order_form"),
        sa.UniqueConstraint("slug", "form_id", name="uq_component_slug_form"),
        sa.UniqueConstraint("text", "form_id", name="uq_component_text_form"),
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
    op.create_table(
        "data_source",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["question_id"], ["component.id"], name=op.f("fk_data_source_question_id_component")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_source")),
        sa.UniqueConstraint("question_id", name="uq_question_id"),
    )
    op.create_table(
        "expression",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("statement", sa.String(), nullable=False),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "type",
            expression_type_enum,
            nullable=False,
        ),
        sa.Column(
            "managed_name",
            managed_expression_enum,
            nullable=True,
        ),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["user.id"], name=op.f("fk_expression_created_by_id_user")),
        sa.ForeignKeyConstraint(["question_id"], ["component.id"], name=op.f("fk_expression_question_id_component")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_expression")),
    )
    with op.batch_alter_table("expression", schema=None) as batch_op:
        batch_op.create_index(
            "uq_type_condition_unique_question",
            ["type", "question_id", "managed_name", sa.literal_column("(context ->> 'question_id')")],  # ty: ignore[invalid-argument-type]
            unique=True,
            postgresql_where="type = 'CONDITION'::expression_type_enum",
        )
        batch_op.create_index(
            "uq_type_validation_unique_key",
            ["type", "question_id", "managed_name"],
            unique=True,
            postgresql_where="type = 'VALIDATION'::expression_type_enum",
        )

    op.create_table(
        "data_source_item",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("data_source_id", sa.Uuid(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("key", postgresql.CITEXT(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["data_source_id"], ["data_source.id"], name=op.f("fk_data_source_item_data_source_id_data_source")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_source_item")),
        sa.UniqueConstraint("data_source_id", "key", name="uq_data_source_id_key"),
        sa.UniqueConstraint("data_source_id", "order", deferrable=True, name="uq_data_source_id_order"),
    )
    op.create_table(
        "data_source_item_reference",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("data_source_item_id", sa.Uuid(), nullable=False),
        sa.Column("expression_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["data_source_item_id"],
            ["data_source_item.id"],
            name=op.f("fk_data_source_item_reference_data_source_item_id_data_source_item"),
        ),
        sa.ForeignKeyConstraint(
            ["expression_id"], ["expression.id"], name=op.f("fk_data_source_item_reference_expression_id_expression")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_source_item_reference")),
    )


def downgrade() -> None:
    op.drop_table("data_source_item_reference")
    op.drop_table("data_source_item")
    with op.batch_alter_table("expression", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_type_validation_unique_key", postgresql_where="type = 'VALIDATION'::expression_type_enum"
        )
        batch_op.drop_index(
            "uq_type_condition_unique_question", postgresql_where="type = 'CONDITION'::expression_type_enum"
        )

    op.drop_table("expression")
    op.drop_table("data_source")
    op.drop_table("submission_event")
    op.drop_table("component")
    op.drop_table("submission")
    op.drop_table("form")
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
    op.drop_table("invitation")
    op.drop_table("collection")
    op.drop_table("user")
    op.drop_table("organisation")
    op.drop_table("grant")

    submission_mode_enum.drop(op.get_bind())
    submission_event_key_enum.drop(op.get_bind())
    role_enum.drop(op.get_bind())
    question_data_type_enum.drop(op.get_bind())
    managed_expression_enum.drop(op.get_bind())
    expression_type_enum.drop(op.get_bind())
    component_type_enum.drop(op.get_bind())
    collection_type_enum.drop(op.get_bind())

    public_citext = PGExtension(schema="public", signature="citext")
    op.drop_entity(public_citext)  # ty: ignore[unresolved-attribute]
