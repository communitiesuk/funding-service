import functools
from typing import Callable

from flask import abort, current_app, redirect, request, session, url_for
from flask.typing import ResponseReturnValue
from flask_login import logout_user

from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.data import interfaces
from app.common.data.interfaces.grants import get_grant
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


def is_mhclg_user[**P](
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
            session["next"] = request.full_path
            return redirect(url_for("auth.sso_sign_in"))

        # Guarding against SSO users who somehow login via magic link
        if session_auth != AuthMethodEnum.SSO:
            return abort(403)

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
        # This decorator is itself wrapped by `is_mhclg_user`, so we know that `current_user` exists and is
        # not an anonymous user (ie a user is definitely logged-in) and an MHCLG user if we get here.

        # Guarding against SSO users who somehow login via magic link
        session_auth = session.get("auth")
        if session_auth != AuthMethodEnum.SSO:
            return abort(403)

        if not AuthorisationHelper.is_platform_admin(user=interfaces.user.get_current_user()):
            return abort(403)

        return func(*args, **kwargs)

    return is_mhclg_user(wrapper)


def has_grant_role[**P](
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

            if "grant_id" not in kwargs or (grant_id := kwargs["grant_id"]) is None:
                raise ValueError("Grant ID required.")

            # raises a 404 if the grant doesn't exist; more appropriate than 403 on non-existent entity
            grant = get_grant(grant_id)
            if not AuthorisationHelper.has_grant_role(grant_id=grant.id, role=role, user=user):
                return abort(403, description="Access denied")

            return func(*args, **kwargs)

        return is_mhclg_user(wrapped)

    return decorator
