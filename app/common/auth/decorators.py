import functools
import uuid
from typing import Callable, cast

import sentry_sdk
from flask import abort, current_app, flash, redirect, request, session, url_for
from flask.typing import ResponseReturnValue
from flask_login import logout_user

from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.data import interfaces
from app.common.data.interfaces.collections import (
    get_collection,
    get_component_by_id,
    get_expression_by_id,
    get_form_by_id,
)
from app.common.data.interfaces.grants import get_grant
from app.common.data.interfaces.organisations import get_organisation
from app.common.data.types import AuthMethodEnum, RoleEnum


def access_grant_funding_login_required[**P](
    func: Callable[P, ResponseReturnValue],
) -> Callable[P, ResponseReturnValue]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> ResponseReturnValue:
        user = interfaces.user.get_current_user()
        if not user.is_authenticated:
            session["next"] = request.full_path
            return redirect(url_for("auth.request_a_link_to_sign_in"))

        session_auth = session.get("auth")
        # This shouldn't be able to happen as we set it in our login routes but if it does somehow happen then we want
        # to make sure we know about it through a Sentry error as it would mean our login flows are broken
        if session_auth is None:
            logout_user()
            sentry_sdk.set_user(None)
            return abort(500)

        return func(*args, **kwargs)

    return wrapper


def deliver_grant_funding_login_required[**P](
    func: Callable[P, ResponseReturnValue],
) -> Callable[P, ResponseReturnValue]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> ResponseReturnValue:
        user = interfaces.user.get_current_user()
        if not user.is_authenticated:
            session["next"] = request.full_path
            return redirect(url_for("auth.sso_sign_in"))

        session_auth = session.get("auth")
        # This shouldn't be able to happen as we set it in our login routes but if it does somehow happen then we want
        # to make sure we know about it through a Sentry error as it would mean our login flows are broken
        if session_auth is None:
            logout_user()
            sentry_sdk.set_user(None)
            return abort(500)

        return func(*args, **kwargs)

    return wrapper


def redirect_if_authenticated[**P](
    func: Callable[P, ResponseReturnValue],
) -> Callable[P, ResponseReturnValue]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> ResponseReturnValue:
        user = interfaces.user.get_current_user()
        # TODO: As we add more roles/users to the platform we will want to extend this to redirect appropriately based
        # on the user's role. For now, this covers internal MHCLG users and will hard error for anyone else so that
        # we get a Sentry notification and can get it fixed.
        if user.is_authenticated:
            internal_domains = current_app.config["INTERNAL_DOMAINS"]
            if user.email.endswith(internal_domains):
                return redirect(url_for("deliver_grant_funding.list_grants"))
            # There's no default 'landing page' yet for Access Grant Funding - on magic link sign-in we fallback to a
            # redirect to this Access Grant Funding grants_list page in lieu of anything else so doing the same here
            # (the issue is that this page is platform admins only, but we need to redirect people _somewhere_)
            return redirect(url_for("developers.access.grants_list"))

        return func(*args, **kwargs)

    return wrapper


def is_deliver_grant_funding_user[**P](
    func: Callable[P, ResponseReturnValue],
) -> Callable[P, ResponseReturnValue]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> ResponseReturnValue:
        # This decorator is itself wrapped by `login_required`, so we know that `current_user` exists and is
        # not an anonymous user (ie a user is definitely logged-in) if we get here.

        user = interfaces.user.get_current_user()
        session_auth = session.get("auth")

        # If Deliver Grant Funding user and has logged in with magic link somehow
        if AuthorisationHelper.is_deliver_grant_funding_user(user) and session_auth != AuthMethodEnum.SSO:
            logout_user()
            sentry_sdk.set_user(None)
            session["next"] = request.full_path
            return redirect(url_for("auth.sso_sign_in"))

        # Guarding against SSO users who somehow login via magic link
        if session_auth != AuthMethodEnum.SSO:
            return abort(403)

        # TODO: remove this when we onboard other Government departments to Deliver grant funding
        internal_domains = current_app.config["INTERNAL_DOMAINS"]
        if not user.email.endswith(internal_domains):
            return abort(403)

        return func(*args, **kwargs)

    return deliver_grant_funding_login_required(wrapper)


def is_platform_admin[**P](
    func: Callable[P, ResponseReturnValue],
) -> Callable[P, ResponseReturnValue]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> ResponseReturnValue:
        # This decorator is itself wrapped by `is_deliver_grant_funding_user`, so we know that `current_user` exists and
        # is not an anonymous user (ie a user is definitely logged-in) and an MHCLG user if we get here.

        # Guarding against SSO users who somehow login via magic link
        session_auth = session.get("auth")
        if session_auth != AuthMethodEnum.SSO:
            return abort(403)

        if not AuthorisationHelper.is_platform_admin(user=interfaces.user.get_current_user()):
            return abort(403)

        return func(*args, **kwargs)

    return is_deliver_grant_funding_user(wrapper)


def is_deliver_org_admin[**P](
    func: Callable[P, ResponseReturnValue],
) -> Callable[P, ResponseReturnValue]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> ResponseReturnValue:
        # This decorator is itself wrapped by `is_deliver_grant_funding_user`, so we know that `current_user` exists and
        # is not an anonymous user (ie a user is definitely logged-in) and an MHCLG user if we get here.

        # Guarding against SSO users who somehow login via magic link
        session_auth = session.get("auth")
        if session_auth != AuthMethodEnum.SSO:
            return abort(403)

        if not AuthorisationHelper.is_deliver_org_admin(user=interfaces.user.get_current_user()):
            return abort(403)

        return func(*args, **kwargs)

    return is_deliver_grant_funding_user(wrapper)


def is_deliver_org_member[**P](
    func: Callable[P, ResponseReturnValue],
) -> Callable[P, ResponseReturnValue]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> ResponseReturnValue:
        # This decorator is itself wrapped by `is_deliver_grant_funding_user`, so we know that `current_user` exists and
        # is not an anonymous user (ie a user is definitely logged-in) and an MHCLG user if we get here.

        # Guarding against SSO users who somehow login via magic link
        session_auth = session.get("auth")
        if session_auth != AuthMethodEnum.SSO:
            return abort(403)

        if not AuthorisationHelper.is_deliver_org_member(user=interfaces.user.get_current_user()):
            return abort(403)

        return func(*args, **kwargs)

    return is_deliver_grant_funding_user(wrapper)


def has_deliver_grant_role[**P](
    role: RoleEnum,
) -> Callable[[Callable[P, ResponseReturnValue]], Callable[P, ResponseReturnValue]]:
    def decorator(func: Callable[P, ResponseReturnValue]) -> Callable[P, ResponseReturnValue]:
        @functools.wraps(func)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> ResponseReturnValue:
            # Guarding against SSO users who somehow login via magic link
            session_auth = session.get("auth")
            if session_auth != AuthMethodEnum.SSO:
                return abort(403)

            user = interfaces.user.get_current_user()
            if AuthorisationHelper.is_platform_admin(user=user):
                return func(*args, **kwargs)

            if "grant_id" not in kwargs or (grant_id := cast(uuid.UUID, kwargs["grant_id"])) is None:
                raise ValueError("Grant ID required.")

            # raises a 404 if the grant doesn't exist; more appropriate than 403 on non-existent entity
            grant = get_grant(grant_id)
            if not AuthorisationHelper.has_deliver_grant_role(grant_id=grant.id, role=role, user=user):
                return abort(403, description="Access denied")

            return func(*args, **kwargs)

        return is_deliver_grant_funding_user(wrapped)

    return decorator


def collection_is_editable[**P]() -> Callable[[Callable[P, ResponseReturnValue]], Callable[P, ResponseReturnValue]]:
    def decorator(func: Callable[P, ResponseReturnValue]) -> Callable[P, ResponseReturnValue]:
        @functools.wraps(func)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> ResponseReturnValue:
            # Guarding against SSO users who somehow login via magic link
            session_auth = session.get("auth")
            if session_auth != AuthMethodEnum.SSO:
                return abort(403)

            entity_lookups = [
                "collection_id",
                "report_id",
                "form_id",
                "component_id",
                "question_id",
                "group_id",
                "expression_id",
            ]
            for entity_lookup in entity_lookups:
                if entity_lookup in kwargs and (entity_id := cast(uuid.UUID, kwargs[entity_lookup])) is not None:
                    break
            else:
                raise ValueError("Collection/Report/Form/Component/Expression ID required.")

            # raises a 404 if the entity doesn't exist; more appropriate than 403 on non-existent thing
            if entity_lookup == "form_id":
                form = get_form_by_id(entity_id)
                collection = form.collection
            elif entity_lookup in {"component_id", "question_id", "group_id"}:
                question = get_component_by_id(entity_id)
                collection = question.form.collection
            elif entity_lookup == "expression_id":
                expression = get_expression_by_id(entity_id)
                collection = expression.question.form.collection
            else:
                collection = get_collection(entity_id)

            user = interfaces.user.get_current_user()
            if not AuthorisationHelper.can_edit_collection(user=user, collection_id=collection.id):
                # TODO: FSPT-549 - Reliably show flash messages everywhere, currently these just ... won't show up
                flash(
                    f"You cannot edit the “{collection.name}” {collection.type} as it is {collection.status}",
                    "error",
                )
                return redirect(url_for("deliver_grant_funding.list_reports", grant_id=collection.grant_id))

            return func(*args, **kwargs)

        return is_deliver_grant_funding_user(wrapped)

    return decorator


def is_access_org_member[**P](
    func: Callable[P, ResponseReturnValue],
) -> Callable[P, ResponseReturnValue]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> ResponseReturnValue:
        # This decorator is itself wrapped by `login_required`, so we know that `current_user` exists and is
        # not an anonymous user (ie a user is definitely logged-in) if we get here.

        if "organisation_id" not in kwargs or (organisation_id := cast(uuid.UUID, kwargs["organisation_id"])) is None:
            raise ValueError("Organisation ID required.")

        # check it exists raising 404 otherwise
        organisation = get_organisation(organisation_id)
        if not AuthorisationHelper.has_access_org_access(
            user=interfaces.user.get_current_user(), organisation_id=organisation.id
        ):
            return abort(403)

        return func(*args, **kwargs)

    # TODO: when magic links work is done make sure this works relative to that
    # return is_deliver_grant_funding_user(wrapper)
    return access_grant_funding_login_required(wrapper)
