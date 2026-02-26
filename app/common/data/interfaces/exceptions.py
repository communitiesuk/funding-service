from collections.abc import Callable, Sequence
from functools import wraps
from typing import Any, Optional, Protocol, cast, overload

from flask import current_app
from psycopg.errors import CheckViolation, UniqueViolation
from sqlalchemy.exc import IntegrityError

from app.common.data.models import Component
from app.extensions import db
from app.types import NOT_PROVIDED, TNotProvided


class DuplicateValueError(Exception):
    model_name: str | None
    field_name: str
    new_value: str

    constraint_name_map: dict[str, str] = {
        "uq_grant_name": "name",
        "uq_collection_name_version_grant_id": "name",
        "uq_collection_name_grant_id": "name",
        "uq_form_title_collection": "title",
        "uq_form_slug_collection": "title",
        "uq_collection_slug_grant_id": "name",
        "uq_component_slug_form": "text",
        "uq_component_text_form": "text",
        "uq_component_name_form": "name",
        "uq_type_validation_unique_key": "question_id",
        "uq_type_condition_unique_question": "question_id",
    }

    def __init__(self, integrity_error: IntegrityError) -> None:
        diagnostics = cast(UniqueViolation, integrity_error.orig).diag

        # if we can't map the integrity error, re-raise it (has better info in it than any custom exception we'd throw)
        if not isinstance(diagnostics.constraint_name, str):
            raise integrity_error
        if not isinstance(integrity_error.params, dict):
            raise integrity_error

        self.model_name = diagnostics.table_name
        self.field_name = DuplicateValueError.constraint_name_map[diagnostics.constraint_name]
        self.new_value = integrity_error.params.get(self.field_name, "unknown")  # ty: ignore[no-matching-overload]


class InvalidUserRoleError(Exception):
    model_name: str | None
    constraint_name: str | None
    message: str

    constraint_message_map: dict[str, str] = {
        "ck_user_role_non_admin_permissions_require_org": (
            "Non-'admin' roles must be linked to an organisation or grant."
        ),
        "ck_invitation_non_admin_permissions_require_org": (
            "Non-'admin' roles must be linked to an organisation or grant."
        ),
        "ck_user_role_member_permission_required": "The 'member' role must always be present",
        "ck_invitation_member_permission_required": "The 'member' role must always be present",
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


class InvalidReferenceInExpression(Exception):
    def __init__(self, message: str, field_name: str, bad_reference: str):
        super().__init__(message)
        self.message = message
        self.field_name = field_name
        self.bad_reference = bad_reference


class InvalidReferencedDataTypeInExpression(Exception):
    def __init__(self, message: str, field_name: str, component: Component, depends_on_component: Component):
        super().__init__(message)
        self.message = message
        self.field_name = field_name
        self.question = component
        self.depends_on_question = depends_on_component


class FlashableException(Protocol):
    def as_flash_context(self) -> dict[str, str | bool]: ...


class DependencyOrderException(Exception, FlashableException):
    def __init__(
        self, message: str, component: Component, depends_on_component: Component, field_name: Optional[str] = None
    ):
        super().__init__(message)
        self.message = message
        self.question = component
        self.depends_on_question = depends_on_component
        self.field_name = field_name

    def as_flash_context(self) -> dict[str, str | bool]:
        return {
            "message": self.message,
            "grant_id": str(self.question.form.collection.grant_id),  # Required for URL routing
            "question_id": str(self.question.id),
            "question_text": self.question.text,
            "question_is_group": self.question.is_group,
            # currently you can't depend on the outcome to a generic component (like a group)
            # so question continues to make sense here - we should review that naming if that
            # functionality changes
            "depends_on_question_id": str(self.depends_on_question.id),
            "depends_on_question_text": self.depends_on_question.text,
            "depends_on_question_is_group": self.depends_on_question.is_group,
        }


@overload
def flush_and_rollback_on_exceptions[T](
    func: Callable[..., T],
    *,
    coerce_exceptions: Sequence[tuple[type[Exception], type[Exception]]] | None | TNotProvided = NOT_PROVIDED,
) -> Callable[..., T]: ...


@overload
def flush_and_rollback_on_exceptions[T](
    func: None = None,
    *,
    coerce_exceptions: Sequence[tuple[type[Exception], type[Exception]]] | None | TNotProvided = NOT_PROVIDED,
) -> Callable[[Callable[..., T]], Callable[..., T]]: ...


def flush_and_rollback_on_exceptions[T](
    func: Callable[..., T] | None = None,
    *,
    coerce_exceptions: Sequence[tuple[type[Exception], type[Exception]]] | None | TNotProvided = NOT_PROVIDED,
) -> Callable[..., T] | Callable[[Callable[..., T]], Callable[..., T]]:
    def decorator(f: Callable[..., T]) -> Callable[..., T]:
        @wraps(f)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            try:
                retval = f(*args, **kwargs)
                db.session.flush()
                return retval
            except Exception as e:
                db.session.rollback()

                if coerce_exceptions is not None and coerce_exceptions is not NOT_PROVIDED:
                    for from_exception, to_exception in coerce_exceptions:
                        if isinstance(e, from_exception):
                            raise to_exception(e) from e

                raise e

        return wrapper

    if func is not None:
        return decorator(func)

    return decorator


class StateTransitionError(Exception):
    def __init__(self, model: str, from_state: str, to_state: str) -> None:
        self.from_state = from_state
        self.to_state = to_state
        self.model = model
        super().__init__(f"Unsupported state transition for {model} from {from_state} to {to_state}")


class NotEnoughGrantTeamUsersError(Exception):
    pass


class GrantPrivacyPolicyRequiredError(Exception):
    pass


class CollectionChronologyError(Exception):
    pass


class GrantRecipientsRequiredToScheduleReportError(Exception):
    pass


class GrantRecipientUsersRequiredError(Exception):
    pass


class GrantMustBeLiveError(Exception):
    pass
