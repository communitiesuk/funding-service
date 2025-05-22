from typing import cast

from flask import current_app
from psycopg.errors import CheckViolation, UniqueViolation
from sqlalchemy.exc import IntegrityError


class DuplicateValueError(Exception):
    model_name: str | None
    field_name: str
    new_value: str

    constraint_name_map: dict[str, str] = {
        "uq_grant_name": "name",
        "uq_schema_name_version_grant_id": "name",
        "uq_section_title_collection_schema": "title",
        "uq_form_title_section": "title",
        "uq_form_slug_section": "title",
        "uq_section_slug_collection_schema": "title",
        "uq_collection_slug_grant_id": "name",
        "uq_question_slug_form": "text",
        "uq_question_text_form": "text",
        "uq_question_name_form": "name",
    }

    def __init__(self, integrity_error: IntegrityError) -> None:
        diagnostics = cast(UniqueViolation, integrity_error.orig).diag
        self.model_name = diagnostics.table_name
        if not isinstance(diagnostics.constraint_name, str):
            raise ValueError("Diagnostic constraint_name must be a string")
        self.field_name = DuplicateValueError.constraint_name_map[diagnostics.constraint_name]
        if not isinstance(integrity_error.params, dict):
            raise ValueError("IntegrityError params must be a dict")
        self.new_value = integrity_error.params[self.field_name]


class InvalidUserRoleError(Exception):
    model_name: str | None
    constraint_name: str | None
    message: str

    constraint_message_map: dict[str, str] = {
        "ck_user_role_member_role_not_platform": "A 'member' role must be linked to an organisation or grant.",
        "ck_user_role_s151_officer_role_org_only": "A 's151_officer' role can only be linked to an organisation.",
        "ck_user_role_assessor_role_grant_only": "An 'assessor' role can only be linked to a grant.",
    }

    def __init__(self, integrity_error: IntegrityError) -> None:
        diagnostics = cast(CheckViolation, integrity_error.orig).diag
        self.model_name = getattr(diagnostics, "table_name", None)
        self.constraint_name = getattr(diagnostics, "constraint_name", None)

        if self.constraint_name and self.constraint_name in self.constraint_message_map:
            self.message = self.constraint_message_map[self.constraint_name]
        else:
            self.message = str(integrity_error)

        current_app.logger.warning(
            "UserRole constraint violation %(constraint)s %(message)s | ",
            dict(
                constraint=self.constraint_name,
                message=self.message,
            ),
        )
        super().__init__(self.message)
