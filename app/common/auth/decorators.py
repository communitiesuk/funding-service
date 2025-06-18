import functools
from typing import Callable

from flask import abort, current_app, redirect, request, session, url_for
from flask.typing import ResponseReturnValue

from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.data import interfaces
from app.common.data.types import RoleEnum


def login_required[**P](
    func: Callable[P, ResponseReturnValue],
) -> Callable[P, ResponseReturnValue]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> ResponseReturnValue:
        user = interfaces.user.get_current_user()
        if not user.is_authenticated:
            session["next"] = request.full_path
            return redirect(url_for("auth.sso_sign_in"))

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

            abort(500)

        return func(*args, **kwargs)

    return wrapper


def mhclg_login_required[**P](
    func: Callable[P, ResponseReturnValue],
) -> Callable[P, ResponseReturnValue]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> ResponseReturnValue:
        user = interfaces.user.get_current_user()
        # This decorator is itself wrapped by `login_required`, so we know that `current_user` exists and is
        # not an anonymous user (ie a user is definitely logged-in) if we get here.
        internal_domains = current_app.config["INTERNAL_DOMAINS"]
        if not user.email.endswith(internal_domains):
            abort(403)

        return func(*args, **kwargs)

    return login_required(wrapper)


def platform_admin_role_required[**P](
    func: Callable[P, ResponseReturnValue],
) -> Callable[P, ResponseReturnValue]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> ResponseReturnValue:
        # This decorator is itself wrapped by `mhclg_login_required`, so we know that `current_user` exists and is
        # not an anonymous user (ie a user is definitely logged-in) and an MHCLG user if we get here.
        user = interfaces.user.get_current_user()

        if not AuthorisationHelper.is_platform_admin(user):
            abort(403)

        return func(*args, **kwargs)

    return mhclg_login_required(wrapper)


def has_grant_role[**P](
    role: RoleEnum,
) -> Callable[[Callable[P, ResponseReturnValue]], Callable[P, ResponseReturnValue]]:
    def decorator(func: Callable[P, ResponseReturnValue]) -> Callable[P, ResponseReturnValue]:
        @functools.wraps(func)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> ResponseReturnValue:
            current_user = interfaces.user.get_current_user()

            if AuthorisationHelper.is_platform_admin(user=current_user):
                return func(*args, **kwargs)

            if "grant_id" in kwargs:
                if not AuthorisationHelper.has_grant_role(
                    grant_id=str(kwargs["grant_id"]), user=current_user, role=role
                ):
                    abort(403, description="Access denied")

            return func(*args, **kwargs)

        return mhclg_login_required(wrapped)

    return decorator
