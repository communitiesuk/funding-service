from typing import cast

from psycopg.errors import UniqueViolation
from sqlalchemy.exc import IntegrityError


class DuplicateValueError(Exception):
    model_name: str | None
    field_name: str
    new_value: str

    # I think this should probably just wrap the IntegrityError and rely on its message for diagnosing
    # presumably most things calling this will know what the integrity failure is and if they don't they could
    # inspect the constraint name themselves (in the rare instance there might be multiple)
    constraint_name_map: dict[str, str] = {"uq_grant_name": "name", "uq_schema_name_grant_id": "name"}

    def __init__(self, integrity_error: IntegrityError) -> None:
        diagnostics = cast(UniqueViolation, integrity_error.orig).diag
        self.model_name = diagnostics.table_name
        if not isinstance(diagnostics.constraint_name, str):
            raise ValueError("Diagnostic constraint_name must be a string")
        self.field_name = DuplicateValueError.constraint_name_map[diagnostics.constraint_name]
        if not isinstance(integrity_error.params, dict):
            raise ValueError("IntegrityError params must be a dict")
        self.new_value = integrity_error.params[self.field_name]
