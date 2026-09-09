"""Rename check constraints to match naming convention, add missing org retirement check

Revision ID: 084_alembic_check_constraints
Revises: 083_add_name_to_invitation
Create Date: 2026-09-09 09:00:14.200876

"""

from alembic import op

revision = "084_alembic_check_constraints"
down_revision = "083_add_name_to_invitation"
branch_labels = None
depends_on = None

# Alembic v1.19 added autogenerate support for check constraints, which surfaced a number of constraint names in the
# database that don't match our naming convention. The SQL condition on each of these is unchanged, so we rename in
# place rather than dropping and recreating (which would make postgres re-validate the constraint against every existing
# row). Model names were also normalised to drop the redundant "ck_"/table-name prefixes baked into some of the raw
# `name=` values, which our naming convention was doubling up on (and, for a handful of long ones, pushing past
# Postgres's 63-character identifier limit.

RENAMES = [
    (
        "collection",
        "ck_collection_ck_submission_name_question_requires_mult_f3c7",
        "ck_collection_submission_name_question_requires_multiple",
    ),
    (
        "collection",
        "ck_multiple_submissions_are_managed_by_service",
        "ck_collection_multiple_submissions_are_managed_by_service",
    ),
    (
        "component",
        "ck_component_ck_component_type_question_requires_data_type",
        "ck_component_type_question_requires_data_type",
    ),
    (
        "component_reference",
        "ck_component_reference_ck_component_reference_component_efcd",
        "ck_component_reference_component_xor_data_source",
    ),
    (
        "component_reference",
        "ck_component_reference_ck_component_reference_data_sour_c80d",
        "ck_component_reference_data_source_requires_column",
    ),
    (
        "component_reference",
        "ck_component_reference_ck_component_reference_item_requ_8ab4",
        "ck_component_reference_item_requires_component",
    ),
    (
        "data_source",
        "ck_data_source_ck_data_source_collection_requires_grant",
        "ck_data_source_collection_requires_grant",
    ),
    (
        "data_source",
        "ck_data_source_ck_data_source_non_custom_requires_name__7beb",
        "ck_data_source_non_custom_requires_core_fields",
    ),
    (
        "invitation",
        "ck_platform_admin_permission_scope",
        "ck_invitation_platform_admin_permission_scope",
    ),
    (
        "organisation",
        "ck_organisation_ck_typed_external_id",
        "ck_organisation_typed_external_id",
    ),
    (
        "user_role",
        "ck_platform_admin_permission_scope",
        "ck_user_role_platform_admin_permission_scope",
    ),
]


def upgrade() -> None:
    for table, old_name, new_name in RENAMES:
        op.execute(f"ALTER TABLE {table} RENAME CONSTRAINT {old_name} TO {new_name}")

    op.create_check_constraint(
        op.f("ck_organisation_retirement"),
        "organisation",
        "status = 'RETIRED' OR retirement_date IS NULL",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_organisation_retirement"), "organisation", type_="check")

    for table, old_name, new_name in RENAMES:
        op.execute(f"ALTER TABLE {table} RENAME CONSTRAINT {new_name} TO {old_name}")
