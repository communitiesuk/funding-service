import functools
from typing import Callable, cast

from flask import abort, redirect, request, session, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user

from app.common.data.models import User


def login_required[**P](
    func: Callable[P, ResponseReturnValue],
) -> Callable[P, ResponseReturnValue]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> ResponseReturnValue:
        if not current_user.is_authenticated:
            session["next"] = request.full_path
            return redirect(url_for("auth.request_a_link_to_sign_in"))

        return func(*args, **kwargs)

    return wrapper


def mhclg_login_required[**P](
    func: Callable[P, ResponseReturnValue],
) -> Callable[P, ResponseReturnValue]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> ResponseReturnValue:
        # This decorator is itself wrapped by `login_required`, so we know that `current_user` exists and is
        # not an anonymous user (ie a user is definitely logged-in) if we get here.
        if not cast(User, current_user).email.endswith("@communities.gov.uk"):
            abort(403)

        return func(*args, **kwargs)

    return login_required(wrapper)
