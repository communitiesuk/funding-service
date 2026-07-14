import uuid
from typing import Any, cast

from flask import abort, current_app, flash, make_response, redirect, render_template, request, session, url_for
from flask.typing import ResponseReturnValue

from app.access_grant_funding.forms import PublicSignUpEmailForm, PublicSignUpNameForm
from app.access_grant_funding.routes import access_grant_funding_blueprint
from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.data import interfaces
from app.common.data.interfaces.collections import get_collection, get_public_sign_up_collection
from app.common.data.interfaces.grant_recipients import create_grant_recipient, get_grant_recipient_or_none
from app.common.data.interfaces.organisations import get_organisations_by_trusted_domain
from app.common.data.models import Collection, Organisation
from app.common.data.models_user import User
from app.common.data.types import CollectionStatusEnum, GrantRecipientStatusEnum, GrantStatusEnum, RoleEnum
from app.common.forms import GenericSubmitForm
from app.common.markdown import convert_text_to_govuk_markup
from app.extensions import auto_commit_after_request, notification_service
from app.types import FlashMessageType

# Where we stash an email address that didn't match a registered organisation, so that we can send the person back to
# the email page with their address prefilled and an error telling them to contact the service desk.
UNREGISTERED_EMAIL_SESSION_KEY = "public_sign_up_unregistered_email"

UNREGISTERED_EMAIL_ERROR = (
    "We could not match your email address to an organisation that is registered with this service. "
    "Contact us through our support desk if you think this is wrong."
)


def _is_publicly_visible(collection: Collection) -> bool:
    return collection.grant.status == GrantStatusEnum.LIVE and collection.status == CollectionStatusEnum.OPEN


def _check_sign_up_page_available(collection: Collection | None) -> Collection:
    """404s unless the current visitor is allowed to see this collection's public sign up pages.

    Signed in users - eg a grant team checking their sign up page before the grant goes live - can see the pages for a
    collection with public sign up switched on whatever state the grant and collection are in; they get a test data
    banner when the pages aren't live yet. For everyone else the grant must be live and the collection open.
    """
    if collection is None or not collection.allow_public_sign_up:
        abort(404)

    if not interfaces.user.get_current_user().is_authenticated and not _is_publicly_visible(collection):
        abort(404)

    return collection


def _render_sign_up_page(template: str, collection: Collection, **context: Any) -> ResponseReturnValue:
    response = make_response(
        render_template(
            template,
            collection=collection,
            grant=collection.grant,
            show_test_banner=not _is_publicly_visible(collection),
            service_desk_url=current_app.config["ACCESS_SERVICE_DESK_URL"],
            **context,
        )
    )
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


def _get_organisation_by_email_domain(email: str) -> Organisation | None:
    domain = email.rsplit("@", 1)[-1]
    organisations = get_organisations_by_trusted_domain(domain)

    if not organisations:
        current_app.logger.info(
            "Public sign up: no organisation trusts the email domain %(domain)s", {"domain": domain}
        )
        return None

    # TODO: when more than one organisation trusts a domain, ask the person which one they're applying on behalf of
    return organisations[0]


def _start_applying(user: User, collection: Collection, organisation: Organisation) -> ResponseReturnValue:
    """Give a user data provider access to a grant on behalf of their organisation, and send them to their forms."""
    interfaces.user.add_permissions_to_user(
        user=user,
        permissions=[RoleEnum.DATA_PROVIDER],
        organisation_id=organisation.id,
        grant_id=collection.grant_id,
    )
    flash(
        f"You can now start the {collection.name} application on behalf of {organisation.name}",
        FlashMessageType.PUBLIC_SIGN_UP_SUCCESS,
    )
    return redirect(
        url_for(
            "access_grant_funding.list_collections",
            organisation_id=organisation.id,
            grant_id=collection.grant_id,
        )
    )


@access_grant_funding_blueprint.route("/sign-up/<slug:grant_slug>/<slug:collection_slug>", methods=["GET", "POST"])
def public_sign_up_start(grant_slug: str, collection_slug: str) -> ResponseReturnValue:
    collection = _check_sign_up_page_available(get_public_sign_up_collection(grant_slug, collection_slug))

    form = GenericSubmitForm()
    if form.validate_on_submit():
        return redirect(url_for("access_grant_funding.public_sign_up_email", collection_id=collection.id))

    prospectus_html = (
        convert_text_to_govuk_markup(collection.prospectus_markdown) if collection.prospectus_markdown else None
    )
    return _render_sign_up_page(
        "access_grant_funding/public_sign_up/start.html", collection, form=form, prospectus_html=prospectus_html
    )


@access_grant_funding_blueprint.route("/sign-up/<uuid:collection_id>/email", methods=["GET", "POST"])
@auto_commit_after_request
def public_sign_up_email(collection_id: uuid.UUID) -> ResponseReturnValue:
    collection = _check_sign_up_page_available(get_collection(collection_id))
    user = interfaces.user.get_current_user()

    form = PublicSignUpEmailForm()
    if form.validate_on_submit():
        email = cast(str, form.email_address.data)

        # TODO: when a collection has an eligibility check configured, send people there to answer it instead
        redirect_to_path = url_for("access_grant_funding.public_sign_up_eligible", collection_id=collection.id)

        # They're already signed in as the person they say they are, so there's nothing to verify
        if user.is_authenticated and user.email.lower() == email.lower():
            return redirect(redirect_to_path)

        magic_link = interfaces.magic_link.create_magic_link(
            user=interfaces.user.get_user_by_email(email_address=email),
            email=email,
            redirect_to_path=redirect_to_path,
        )
        notification = notification_service.send_magic_link(
            email,
            magic_link_url=url_for("auth.claim_magic_link", magic_link_code=magic_link.code, _external=True),
            magic_link_expires_at_utc=magic_link.expires_at_utc,
            request_new_magic_link_url=url_for(
                "access_grant_funding.public_sign_up_email", collection_id=collection.id, _external=True
            ),
        )
        session["magic_link_email_notification_id"] = notification.id
        session["magic_link_requested"] = True

        return redirect(url_for("auth.check_email", magic_link_id=magic_link.id))

    # They've verified an email address we can't match to a registered organisation, so they're back here to try another
    if request.method == "GET" and (unregistered_email := session.pop(UNREGISTERED_EMAIL_SESSION_KEY, None)):
        form.email_address.data = unregistered_email
        form.email_address.errors = [UNREGISTERED_EMAIL_ERROR]

    return _render_sign_up_page("access_grant_funding/public_sign_up/email.html", collection, form=form)


@access_grant_funding_blueprint.route("/sign-up/<uuid:collection_id>/eligible", methods=["GET", "POST"])
@auto_commit_after_request
def public_sign_up_eligible(collection_id: uuid.UUID) -> ResponseReturnValue:
    collection = _check_sign_up_page_available(get_collection(collection_id))
    user = interfaces.user.get_current_user()

    # They've not verified an email address yet, so we don't know who they are
    if not user.is_authenticated:
        return redirect(url_for("access_grant_funding.public_sign_up_email", collection_id=collection.id))

    # TODO: for now only people from a registered organisation can sign up; in the future they'll be able to register
    #       their organisation themselves from here
    organisation = _get_organisation_by_email_domain(user.email)
    if organisation is None:
        session[UNREGISTERED_EMAIL_SESSION_KEY] = user.email
        return redirect(url_for("access_grant_funding.public_sign_up_email", collection_id=collection.id))

    grant_recipient = get_grant_recipient_or_none(collection.grant_id, organisation.id)

    if grant_recipient:
        # They already have access through this organisation, so let them straight through
        if AuthorisationHelper.has_access_grant_role(
            grant_id=collection.grant_id, organisation_id=organisation.id, role=RoleEnum.MEMBER, user=user
        ):
            return redirect(
                url_for(
                    "access_grant_funding.list_collections",
                    organisation_id=organisation.id,
                    grant_id=collection.grant_id,
                )
            )

        # Their organisation is already applying but they aren't part of it yet, so add them to it - we need their
        # name first if we don't already have it
        if not user.name:
            return redirect(url_for("access_grant_funding.public_sign_up_name", collection_id=collection.id))
        return _start_applying(user, collection, organisation)

    form = GenericSubmitForm()
    if form.validate_on_submit():
        if not user.name:
            return redirect(url_for("access_grant_funding.public_sign_up_name", collection_id=collection.id))
        create_grant_recipient(collection.grant, organisation, status=GrantRecipientStatusEnum.APPLYING)
        return _start_applying(user, collection, organisation)

    return _render_sign_up_page(
        "access_grant_funding/public_sign_up/eligible.html",
        collection,
        form=form,
        organisation=organisation,
        has_name=bool(user.name),
    )


@access_grant_funding_blueprint.route("/sign-up/<uuid:collection_id>/name", methods=["GET", "POST"])
@auto_commit_after_request
def public_sign_up_name(collection_id: uuid.UUID) -> ResponseReturnValue:
    collection = _check_sign_up_page_available(get_collection(collection_id))
    user = interfaces.user.get_current_user()

    if not user.is_authenticated:
        return redirect(url_for("access_grant_funding.public_sign_up_email", collection_id=collection.id))

    organisation = _get_organisation_by_email_domain(user.email)
    if organisation is None:
        session[UNREGISTERED_EMAIL_SESSION_KEY] = user.email
        return redirect(url_for("access_grant_funding.public_sign_up_email", collection_id=collection.id))

    # They already have a name, so there's nothing to ask here - send them back to pick up the rest of the flow
    if user.name:
        return redirect(url_for("access_grant_funding.public_sign_up_eligible", collection_id=collection.id))

    form = PublicSignUpNameForm()
    if form.validate_on_submit():
        user = interfaces.user.upsert_user_by_email(email_address=user.email, name=form.full_name.data)

        grant_recipient = get_grant_recipient_or_none(collection.grant_id, organisation.id)
        if not grant_recipient:
            create_grant_recipient(collection.grant, organisation, status=GrantRecipientStatusEnum.APPLYING)

        return _start_applying(user, collection, organisation)

    return _render_sign_up_page("access_grant_funding/public_sign_up/name.html", collection, form=form)
