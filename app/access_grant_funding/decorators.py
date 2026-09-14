import functools
from collections.abc import Callable
from typing import Any, cast

from flask import redirect, request, session, url_for
from flask.typing import ResponseReturnValue

from app.access_grant_funding.session_models import (
    CompleteCreateOrganisationSession,
    CreateOrganisationPage,
    CreateOrganisationSession,
    NamedCreateOrganisationSession,
)
from app.common.data.interfaces.collections import get_collection_by_slug
from app.common.data.interfaces.grants import get_grant_by_slug
from app.common.helpers.feature_flags import FeatureFlags
from app.constants import SESSION_CREATE_ORGANISATION


def requires_create_organisation_session(
    *,
    page: CreateOrganisationPage,
) -> Callable[[Callable[..., ResponseReturnValue]], Callable[..., ResponseReturnValue]]:
    """Load the session for this page and recover missing prerequisites before running the view."""
    session_model = {
        CreateOrganisationPage.ALREADY_EXISTS: NamedCreateOrganisationSession,
        CreateOrganisationPage.TEAM_MEMBERS: NamedCreateOrganisationSession,
        CreateOrganisationPage.USER_NAME: NamedCreateOrganisationSession,
        CreateOrganisationPage.CHECK_YOUR_ANSWERS: CompleteCreateOrganisationSession,
    }.get(page, CreateOrganisationSession)

    def decorator(func: Callable[..., ResponseReturnValue]) -> Callable[..., ResponseReturnValue]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> ResponseReturnValue:
            grant_slug = cast(str, kwargs["grant_slug"])
            collection_slug = cast(str, kwargs["collection_slug"])
            grant = get_grant_by_slug(grant_slug)
            collection = get_collection_by_slug(grant_id=grant.id, slug=collection_slug)

            session_data = session.get(SESSION_CREATE_ORGANISATION, {})
            org_session = session_model.from_session(collection_id=collection.id, session_data=session_data)
            org_session = org_session or CreateOrganisationSession.from_session(
                collection_id=collection.id, session_data=session_data
            )
            if org_session is None:
                session.pop(SESSION_CREATE_ORGANISATION, None)
                return redirect(
                    url_for(
                        "access_grant_funding.public_sign_up_router",
                        grant_slug=grant_slug,
                        collection_slug=collection_slug,
                    )
                )

            try:
                org_session.validate_for_page(
                    page,
                    grant_slug=grant_slug,
                    collection_slug=collection_slug,
                    request_args=request.args,
                    companies_house_lookup=FeatureFlags.ACCESS_GRANT_FUNDING_COMPANIES_HOUSE_LOOKUP.is_enabled,
                )
                response = func(*args, org_session=org_session, **kwargs)
            finally:
                # a view that completes the journey clears the session, which must not be undone here
                if SESSION_CREATE_ORGANISATION in session and org_session.to_session_dict() != session_data:
                    session[SESSION_CREATE_ORGANISATION] = org_session.to_session_dict()

            return response

        return wrapper

    return decorator
