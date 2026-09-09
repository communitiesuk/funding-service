import functools
from collections.abc import Callable
from typing import Any, cast

from flask import redirect, session, url_for
from flask.typing import ResponseReturnValue

from app.access_grant_funding.session_models import CreateOrganisationSession
from app.common.data.interfaces.collections import get_collection_by_slug
from app.common.data.interfaces.grants import get_grant_by_slug
from app.constants import SESSION_CREATE_ORGANISATION


def requires_create_organisation_session(
    session_model: type[CreateOrganisationSession] = CreateOrganisationSession,
) -> Callable[[Callable[..., ResponseReturnValue]], Callable[..., ResponseReturnValue]]:
    """Manages the create organisation session. If the session missing, for a different collection
    or missing required properties at the time in the journey, redirects back to public sign up.
    """

    def decorator(func: Callable[..., ResponseReturnValue]) -> Callable[..., ResponseReturnValue]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> ResponseReturnValue:
            grant_slug = cast(str, kwargs["grant_slug"])
            collection_slug = cast(str, kwargs["collection_slug"])
            grant = get_grant_by_slug(grant_slug)
            collection = get_collection_by_slug(grant_id=grant.id, slug=collection_slug)

            org_session = session_model.from_session(
                collection_id=collection.id, session_data=session.get(SESSION_CREATE_ORGANISATION, {})
            )
            if org_session is None:
                return redirect(
                    url_for(
                        "access_grant_funding.public_sign_up_router",
                        grant_slug=grant_slug,
                        collection_slug=collection_slug,
                    )
                )

            return func(*args, org_session=org_session, **kwargs)

        return wrapper

    return decorator
