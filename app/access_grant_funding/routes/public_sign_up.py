import re

from flask import abort, make_response, redirect, render_template, session, url_for
from flask.typing import ResponseReturnValue

from app.access_grant_funding.routes import access_grant_funding_blueprint
from app.common.data.interfaces.grants import get_grant_with_open_public_sign_up_collection_by_name
from app.common.data.types import CollectionStatusEnum
from app.common.forms import GenericSubmitForm

SLUG_PATTERN = re.compile(r"^[a-zA-Z0-9]+(?:-[a-zA-Z0-9]+)*$")


@access_grant_funding_blueprint.route("/grants/<grant_slug>", methods=["GET", "POST"])
def public_grant_sign_up(grant_slug: str) -> ResponseReturnValue:
    if not SLUG_PATTERN.match(grant_slug):
        return abort(404)

    grant_name = grant_slug.replace("-", " ")
    grant = get_grant_with_open_public_sign_up_collection_by_name(grant_name)
    if not grant:
        return abort(404)

    open_public_collections = [
        c
        for c in grant.collections
        if c.allow_public_sign_up
        # todo: how should this be tested? we don't want public sign up pages to be available legitimately for
        #       maybe for now its only available to non-open collections if its an already signed in deliver user
        and c.status == CollectionStatusEnum.OPEN
    ]
    earliest_deadline = min(
        (c.submission_period_end_date for c in open_public_collections if c.submission_period_end_date),
        default=None,
    )

    form = GenericSubmitForm()
    if form.validate_on_submit():
        session["signing_up_for_grant_id"] = str(grant.id)
        return redirect(url_for("auth.request_a_link_to_sign_in"))

    response = make_response(
        render_template(
            "access_grant_funding/public_grant_sign_up.html",
            grant=grant,
            submission_deadline=earliest_deadline,
            form=form,
        )
    )
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response
