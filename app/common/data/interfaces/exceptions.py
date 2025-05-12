from typing import cast

from psycopg.errors import UniqueViolation
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
