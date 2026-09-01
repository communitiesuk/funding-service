"""Helpers for the public sign-up session state.

Kept deliberately small and dependency-light: ``app.common.auth`` is forbidden from importing
``app.common.data.models`` by the import-linter contract, so this module sticks to ``flask``, ``uuid`` and
``app.constants``. It is named ``sign_up_session`` rather than ``session`` to avoid shadowing ``flask.session``,
which is imported by name across this package.
"""

from uuid import UUID

from flask import session

from app.constants import SESSION_CREATE_ORGANISATION, SESSION_SIGNING_UP_FOR_COLLECTION_ID


# TODO: consider moving to access/session_models to keep the logic togther
def start_public_sign_up(collection_id: UUID) -> None:
    """Begin (or restart) a public sign up, discarding any in-progress organisation set up."""
    session.pop(SESSION_CREATE_ORGANISATION, None)
    session[SESSION_SIGNING_UP_FOR_COLLECTION_ID] = collection_id


def clear_public_sign_up_session() -> UUID | None:
    """Clear all public sign up state. Returns the collection being signed up for, if there was one."""
    session.pop(SESSION_CREATE_ORGANISATION, None)
    return session.pop(SESSION_SIGNING_UP_FOR_COLLECTION_ID, None)


def get_signing_up_for_collection_id() -> UUID | None:
    return session.get(SESSION_SIGNING_UP_FOR_COLLECTION_ID)
