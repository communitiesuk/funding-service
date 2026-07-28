import uuid
from typing import Any, cast

from flask import abort, current_app, flash, make_response, redirect, render_template, request, session, url_for
from flask.typing import ResponseReturnValue

from app.access_grant_funding.forms import (
    PublicSignUpConfirmOrganisationForm,
    PublicSignUpEmailForm,
    PublicSignUpNameForm,
    PublicSignUpOrganisationNameForm,
    PublicSignUpOrganisationReferenceForm,
    PublicSignUpOrganisationTypeForm,
)
from app.access_grant_funding.mock_registries import (
    CHARITY_COMMISSION_REFERENCES,
    COMPANIES_HOUSE_REFERENCES,
    lookup_charity,
    lookup_company,
)
from app.access_grant_funding.routes import access_grant_funding_blueprint
from app.access_grant_funding.session_models import PublicSignUpSession, SignUpOrganisationType
from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.collections.forms import build_question_form
from app.common.data import interfaces
from app.common.data.interfaces.collections import (
    create_submission,
    get_collection,
    get_public_sign_up_collection,
    get_submissions_by_user,
)
from app.common.data.interfaces.grant_recipients import (
    create_grant_recipient_with_test_counterpart,
    get_grant_recipient_or_none,
)
from app.common.data.interfaces.organisations import (
    get_or_create_self_registered_organisation,
    get_organisations_by_trusted_domain,
)
from app.common.data.models import Collection, Organisation
from app.common.data.models_user import User
from app.common.data.types import (
    CollectionStatusEnum,
    GrantRecipientStatusEnum,
    GrantStatusEnum,
    RoleEnum,
    SubmissionEventType,
    SubmissionModeEnum,
)
from app.common.expressions import evaluate
from app.common.forms import GenericSubmitForm
from app.common.helpers.collections import SubmissionHelper
from app.common.markdown import convert_text_to_govuk_markup
from app.extensions import auto_commit_after_request, notification_service
from app.types import FlashMessageType

PUBLIC_SIGN_UP_SESSION_KEY = "public_sign_up_registration"


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


def _load_registration_session(collection: Collection) -> PublicSignUpSession | None:
    """Load the in-progress self-registration session for this collection, discarding a stale one for another."""
    session_data = session.get(PUBLIC_SIGN_UP_SESSION_KEY)
    if not session_data:
        return None

    sign_up_session = PublicSignUpSession.from_session(session_data)
    if sign_up_session.collection_id != collection.id:
        session.pop(PUBLIC_SIGN_UP_SESSION_KEY, None)
        return None

    return sign_up_session


def _save_registration_session(sign_up_session: PublicSignUpSession) -> None:
    session[PUBLIC_SIGN_UP_SESSION_KEY] = sign_up_session.to_session_dict()


def _check_registration_journey(collection: Collection) -> ResponseReturnValue | None:
    """Guard for the self-registration sub-journey; returns a redirect if the visitor doesn't belong here."""
    user = interfaces.user.get_current_user()
    if not user.is_authenticated:
        return redirect(url_for("access_grant_funding.public_sign_up_email", collection_id=collection.id))

    if collection.requires_eligibility_check and collection.depends_on_collection_eligibility:
        eligibility_collection = collection.depends_on_collection_eligibility
        mode = SubmissionModeEnum.LIVE if _is_publicly_visible(collection) else SubmissionModeEnum.TEST
        eligibility_submissions = get_submissions_by_user(user, eligibility_collection.id, mode)

        if not any(submission.is_submitted for submission in eligibility_submissions):
            return redirect(url_for("access_grant_funding.public_sign_up_eligible", collection_id=collection.id))

    if _get_organisation_by_email_domain(user.email) is not None:
        return redirect(url_for("access_grant_funding.public_sign_up_eligible", collection_id=collection.id))

    if (
        _load_registration_session(collection) is None
        and request.endpoint != "access_grant_funding.public_sign_up_organisation_type"
    ):
        return redirect(url_for("access_grant_funding.public_sign_up_organisation_type", collection_id=collection.id))

    return None


def _organisation_type_back_url(collection: Collection) -> str:
    if collection.requires_eligibility_check and collection.depends_on_collection_eligibility:
        eligibility_collection = collection.depends_on_collection_eligibility
        last_question = eligibility_collection.forms[0].components[-1]
        return url_for(
            "access_grant_funding.public_sign_up_eligibility_question",
            collection_id=collection.id,
            question_id=last_question.id,
        )
    return url_for("access_grant_funding.public_sign_up_email", collection_id=collection.id)


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

    return _render_sign_up_page("access_grant_funding/public_sign_up/email.html", collection, form=form)


@access_grant_funding_blueprint.route("/sign-up/<uuid:collection_id>/eligible", methods=["GET", "POST"])
@auto_commit_after_request
def public_sign_up_eligible(collection_id: uuid.UUID) -> ResponseReturnValue:
    collection = _check_sign_up_page_available(get_collection(collection_id))
    user = interfaces.user.get_current_user()

    # They've not verified an email address yet, so we don't know who they are
    if not user.is_authenticated:
        return redirect(url_for("access_grant_funding.public_sign_up_email", collection_id=collection.id))

    if collection.requires_eligibility_check and collection.depends_on_collection_eligibility:
        eligibility_collection = collection.depends_on_collection_eligibility
        mode = SubmissionModeEnum.LIVE if _is_publicly_visible(collection) else SubmissionModeEnum.TEST
        eligibility_submissions = get_submissions_by_user(user, eligibility_collection.id, mode)

        if not any(submission.is_submitted for submission in eligibility_submissions):
            first_question = eligibility_collection.forms[0].components[0]
            return redirect(
                url_for(
                    "access_grant_funding.public_sign_up_eligibility_question",
                    collection_id=collection.id,
                    question_id=first_question.id,
                )
            )

    organisation = _get_organisation_by_email_domain(user.email)
    if organisation is None:
        return redirect(url_for("access_grant_funding.public_sign_up_organisation_type", collection_id=collection.id))

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
        create_grant_recipient_with_test_counterpart(
            collection.grant, organisation, status=GrantRecipientStatusEnum.APPLYING
        )
        return _start_applying(user, collection, organisation)

    return _render_sign_up_page(
        "access_grant_funding/public_sign_up/eligible.html",
        collection,
        form=form,
        organisation=organisation,
        has_name=bool(user.name),
    )


def _get_or_create_eligibility_submission(
    user: User, eligibility_collection: Collection, mode: SubmissionModeEnum
) -> SubmissionHelper:
    submissions = get_submissions_by_user(user, eligibility_collection.id, mode)
    unsubmitted = next((submission for submission in submissions if not submission.is_submitted), None)
    submission_id = (
        unsubmitted.id
        if unsubmitted
        else create_submission(collection=eligibility_collection, created_by=user, mode=mode, grant_recipient=None).id
    )
    return SubmissionHelper.load(submission_id)


@access_grant_funding_blueprint.route(
    "/sign-up/<uuid:collection_id>/eligibility/<uuid:question_id>", methods=["GET", "POST"]
)
@auto_commit_after_request
def public_sign_up_eligibility_question(collection_id: uuid.UUID, question_id: uuid.UUID) -> ResponseReturnValue:
    collection = _check_sign_up_page_available(get_collection(collection_id))
    user = interfaces.user.get_current_user()

    if not user.is_authenticated:
        return redirect(url_for("access_grant_funding.public_sign_up_email", collection_id=collection.id))

    eligibility_collection = collection.depends_on_collection_eligibility
    if not collection.requires_eligibility_check or eligibility_collection is None:
        abort(404)

    mode = SubmissionModeEnum.LIVE if _is_publicly_visible(collection) else SubmissionModeEnum.TEST
    submission_helper = _get_or_create_eligibility_submission(user, eligibility_collection, mode)
    question = submission_helper.get_question(question_id)

    form_cls = build_question_form(
        [question], submission_helper.cached_evaluation_context, submission_helper.cached_interpolation_context
    )
    form = form_cls(data=submission_helper.form_data())

    if form.validate_on_submit():
        submission_helper.submit_answer_for_question(question.id, form, user)
        submission_helper.clear_caches()

        eligibility_expression = question.eligibility[0] if question.eligibility else None
        if eligibility_expression and not evaluate(eligibility_expression, submission_helper.cached_evaluation_context):
            return redirect(url_for("access_grant_funding.public_sign_up_ineligible", collection_id=collection.id))

        next_question = submission_helper.get_next_question(question.id)
        if next_question:
            return redirect(
                url_for(
                    "access_grant_funding.public_sign_up_eligibility_question",
                    collection_id=collection.id,
                    question_id=next_question.id,
                )
            )

        submission_helper.toggle_form_completed(eligibility_collection.forms[0], user, is_complete=True)
        submission_helper.add_submission_event(
            SubmissionEventType.SUBMISSION_SUBMITTED, user, related_entity_id=submission_helper.submission.id
        )
        return redirect(url_for("access_grant_funding.public_sign_up_eligible", collection_id=collection.id))

    previous_question = submission_helper.get_previous_question(question.id)
    back_url = (
        url_for(
            "access_grant_funding.public_sign_up_eligibility_question",
            collection_id=collection.id,
            question_id=previous_question.id,
        )
        if previous_question
        else None
    )

    return _render_sign_up_page(
        "access_grant_funding/public_sign_up/eligibility_question.html",
        collection,
        form=form,
        question=question,
        back_url=back_url,
        interpolator=SubmissionHelper.get_interpolator(eligibility_collection, submission_helper),
    )


@access_grant_funding_blueprint.route("/sign-up/<uuid:collection_id>/ineligible", methods=["GET"])
def public_sign_up_ineligible(collection_id: uuid.UUID) -> ResponseReturnValue:
    collection = _check_sign_up_page_available(get_collection(collection_id))

    prospectus_html = (
        convert_text_to_govuk_markup(collection.prospectus_markdown) if collection.prospectus_markdown else None
    )
    return _render_sign_up_page(
        "access_grant_funding/public_sign_up/ineligible.html", collection, prospectus_html=prospectus_html
    )


def _name_back_url(collection: Collection, registration_session: PublicSignUpSession | None) -> str:
    if registration_session is None:
        return url_for("access_grant_funding.public_sign_up_eligible", collection_id=collection.id)
    if registration_session.organisation_type == SignUpOrganisationType.OTHER:
        return url_for("access_grant_funding.public_sign_up_organisation_name", collection_id=collection.id)
    return url_for("access_grant_funding.public_sign_up_confirm_organisation", collection_id=collection.id)


@access_grant_funding_blueprint.route("/sign-up/<uuid:collection_id>/name", methods=["GET", "POST"])
@auto_commit_after_request
def public_sign_up_name(collection_id: uuid.UUID) -> ResponseReturnValue:
    collection = _check_sign_up_page_available(get_collection(collection_id))
    user = interfaces.user.get_current_user()

    if not user.is_authenticated:
        return redirect(url_for("access_grant_funding.public_sign_up_email", collection_id=collection.id))

    registration_session = _load_registration_session(collection)

    organisation = None
    if registration_session is None:
        organisation = _get_organisation_by_email_domain(user.email)
        if organisation is None:
            return redirect(url_for("access_grant_funding.public_sign_up_eligible", collection_id=collection.id))

    # They already have a name, so there's nothing to ask here - send them back to pick up the rest of the flow
    if user.name:
        if registration_session:
            return redirect(
                url_for("access_grant_funding.public_sign_up_check_your_answers", collection_id=collection.id)
            )
        return redirect(url_for("access_grant_funding.public_sign_up_eligible", collection_id=collection.id))

    submit_text = "Continue" if registration_session else "Continue and start application"

    form = PublicSignUpNameForm()
    if form.validate_on_submit():
        user = interfaces.user.upsert_user_by_email(email_address=user.email, name=form.full_name.data)

        if registration_session:
            return redirect(
                url_for("access_grant_funding.public_sign_up_check_your_answers", collection_id=collection.id)
            )

        assert organisation is not None
        grant_recipient = get_grant_recipient_or_none(collection.grant_id, organisation.id)
        if not grant_recipient:
            create_grant_recipient_with_test_counterpart(
                collection.grant, organisation, status=GrantRecipientStatusEnum.APPLYING
            )

        return _start_applying(user, collection, organisation)

    return _render_sign_up_page(
        "access_grant_funding/public_sign_up/name.html",
        collection,
        form=form,
        submit_text=submit_text,
        back_url=_name_back_url(collection, registration_session),
    )


@access_grant_funding_blueprint.route("/sign-up/<uuid:collection_id>/organisation-type", methods=["GET", "POST"])
@auto_commit_after_request
def public_sign_up_organisation_type(collection_id: uuid.UUID) -> ResponseReturnValue:
    collection = _check_sign_up_page_available(get_collection(collection_id))
    if response := _check_registration_journey(collection):
        return response

    sign_up_session = _load_registration_session(collection) or PublicSignUpSession(collection_id=collection.id)

    form = PublicSignUpOrganisationTypeForm(organisation_type=sign_up_session.organisation_type)
    if form.validate_on_submit():
        sign_up_session.organisation_type = SignUpOrganisationType(form.organisation_type.data)
        _save_registration_session(sign_up_session)

        if sign_up_session.organisation_type == SignUpOrganisationType.LOCAL_AUTHORITY:
            return redirect(url_for("access_grant_funding.public_sign_up_contact_support", collection_id=collection.id))
        if sign_up_session.organisation_type == SignUpOrganisationType.OTHER:
            return redirect(
                url_for("access_grant_funding.public_sign_up_organisation_name", collection_id=collection.id)
            )
        return redirect(
            url_for("access_grant_funding.public_sign_up_organisation_reference", collection_id=collection.id)
        )

    return _render_sign_up_page(
        "access_grant_funding/public_sign_up/organisation_type.html",
        collection,
        form=form,
        back_url=_organisation_type_back_url(collection),
    )


@access_grant_funding_blueprint.route("/sign-up/<uuid:collection_id>/organisation-reference", methods=["GET", "POST"])
@auto_commit_after_request
def public_sign_up_organisation_reference(collection_id: uuid.UUID) -> ResponseReturnValue:
    collection = _check_sign_up_page_available(get_collection(collection_id))
    if response := _check_registration_journey(collection):
        return response

    sign_up_session = _load_registration_session(collection)
    if sign_up_session is None or sign_up_session.organisation_type not in (
        SignUpOrganisationType.COMPANY,
        SignUpOrganisationType.CHARITY,
    ):
        return redirect(url_for("access_grant_funding.public_sign_up_organisation_type", collection_id=collection.id))

    is_company = sign_up_session.organisation_type == SignUpOrganisationType.COMPANY
    registry_label = "Companies House" if is_company else "Charity Commission"
    registry_url = (
        "https://find-and-update.company-information.service.gov.uk/"
        if is_company
        else "https://register-of-charities.charitycommission.gov.uk/"
    )
    lookup = lookup_company if is_company else lookup_charity
    valid_references = COMPANIES_HOUSE_REFERENCES if is_company else CHARITY_COMMISSION_REFERENCES

    form = PublicSignUpOrganisationReferenceForm(
        lookup=lookup,
        registry_label=registry_label,
        has_reference_number=sign_up_session.has_reference_number,
        reference_number=sign_up_session.reference_number,
    )
    if form.validate_on_submit():
        sign_up_session.has_reference_number = form.has_reference_number.data

        if form.has_reference_number.data == "no":
            sign_up_session.reference_number = ""
            sign_up_session.organisation_name = ""
            _save_registration_session(sign_up_session)
            return redirect(url_for("access_grant_funding.public_sign_up_contact_support", collection_id=collection.id))

        registered_organisation = lookup(cast(str, form.reference_number.data))
        assert registered_organisation is not None  # already checked by the form's validator
        sign_up_session.reference_number = registered_organisation.reference_number
        sign_up_session.organisation_name = registered_organisation.name
        _save_registration_session(sign_up_session)
        return redirect(
            url_for("access_grant_funding.public_sign_up_confirm_organisation", collection_id=collection.id)
        )

    return _render_sign_up_page(
        "access_grant_funding/public_sign_up/organisation_reference.html",
        collection,
        form=form,
        registry_label=registry_label,
        registry_url=registry_url,
        valid_references=valid_references,
        back_url=url_for("access_grant_funding.public_sign_up_organisation_type", collection_id=collection.id),
    )


@access_grant_funding_blueprint.route("/sign-up/<uuid:collection_id>/organisation-name", methods=["GET", "POST"])
@auto_commit_after_request
def public_sign_up_organisation_name(collection_id: uuid.UUID) -> ResponseReturnValue:
    collection = _check_sign_up_page_available(get_collection(collection_id))
    if response := _check_registration_journey(collection):
        return response

    sign_up_session = _load_registration_session(collection)
    if sign_up_session is None or sign_up_session.organisation_type != SignUpOrganisationType.OTHER:
        return redirect(url_for("access_grant_funding.public_sign_up_organisation_type", collection_id=collection.id))

    form = PublicSignUpOrganisationNameForm(organisation_name=sign_up_session.organisation_name)
    if form.validate_on_submit():
        sign_up_session.organisation_name = cast(str, form.organisation_name.data)
        sign_up_session.reference_number = ""
        _save_registration_session(sign_up_session)
        return redirect(url_for("access_grant_funding.public_sign_up_name", collection_id=collection.id))

    return _render_sign_up_page(
        "access_grant_funding/public_sign_up/organisation_name.html",
        collection,
        form=form,
        back_url=url_for("access_grant_funding.public_sign_up_organisation_type", collection_id=collection.id),
    )


@access_grant_funding_blueprint.route("/sign-up/<uuid:collection_id>/confirm-organisation", methods=["GET", "POST"])
@auto_commit_after_request
def public_sign_up_confirm_organisation(collection_id: uuid.UUID) -> ResponseReturnValue:
    collection = _check_sign_up_page_available(get_collection(collection_id))
    if response := _check_registration_journey(collection):
        return response

    sign_up_session = _load_registration_session(collection)
    if (
        sign_up_session is None
        or not sign_up_session.organisation_name
        or sign_up_session.organisation_type not in (SignUpOrganisationType.COMPANY, SignUpOrganisationType.CHARITY)
    ):
        return redirect(url_for("access_grant_funding.public_sign_up_organisation_type", collection_id=collection.id))

    is_company = sign_up_session.organisation_type == SignUpOrganisationType.COMPANY
    registry_label = "Companies House" if is_company else "Charity Commission"

    form = PublicSignUpConfirmOrganisationForm()
    if form.validate_on_submit():
        if form.is_correct_organisation.data == "no":
            return redirect(url_for("access_grant_funding.public_sign_up_contact_support", collection_id=collection.id))
        return redirect(url_for("access_grant_funding.public_sign_up_name", collection_id=collection.id))

    return _render_sign_up_page(
        "access_grant_funding/public_sign_up/confirm_organisation.html",
        collection,
        form=form,
        registry_label=registry_label,
        organisation_name=sign_up_session.organisation_name,
        reference_number=sign_up_session.reference_number,
        back_url=url_for("access_grant_funding.public_sign_up_organisation_reference", collection_id=collection.id),
    )


@access_grant_funding_blueprint.route("/sign-up/<uuid:collection_id>/check-your-answers", methods=["GET", "POST"])
@auto_commit_after_request
def public_sign_up_check_your_answers(collection_id: uuid.UUID) -> ResponseReturnValue:
    collection = _check_sign_up_page_available(get_collection(collection_id))
    if response := _check_registration_journey(collection):
        return response

    user = interfaces.user.get_current_user()
    sign_up_session = _load_registration_session(collection)
    if sign_up_session is None or sign_up_session.organisation_type is None or not user.name:
        return redirect(url_for("access_grant_funding.public_sign_up_organisation_type", collection_id=collection.id))

    organisation_type = sign_up_session.organisation_type.organisation_type
    if organisation_type is None:
        return redirect(url_for("access_grant_funding.public_sign_up_contact_support", collection_id=collection.id))

    match sign_up_session.organisation_type:
        case SignUpOrganisationType.COMPANY:
            organisation_label, registry_label = "Company", "Companies House"
        case SignUpOrganisationType.CHARITY:
            organisation_label, registry_label = "Charity", "Charity Commission"
        case _:
            organisation_label, registry_label = "Organisation", None

    form = GenericSubmitForm()
    if form.validate_on_submit():
        organisation = get_or_create_self_registered_organisation(
            name=sign_up_session.organisation_name,
            type_=organisation_type,
            typed_id=sign_up_session.reference_number or None,
        )

        if get_grant_recipient_or_none(collection.grant_id, organisation.id):
            current_app.logger.warning(
                "Public sign up: %(email)s tried to register %(external_id)s, already a grant recipient for "
                "grant %(grant_id)s",
                {"email": user.email, "external_id": organisation.external_id, "grant_id": collection.grant_id},
            )
            return redirect(url_for("access_grant_funding.public_sign_up_contact_support", collection_id=collection.id))

        create_grant_recipient_with_test_counterpart(
            collection.grant, organisation, status=GrantRecipientStatusEnum.APPLYING
        )
        session.pop(PUBLIC_SIGN_UP_SESSION_KEY, None)
        return _start_applying(user, collection, organisation)

    return _render_sign_up_page(
        "access_grant_funding/public_sign_up/check_your_answers.html",
        collection,
        form=form,
        sign_up_session=sign_up_session,
        organisation_label=organisation_label,
        registry_label=registry_label,
        user=user,
        back_url=url_for("access_grant_funding.public_sign_up_name", collection_id=collection.id),
    )


@access_grant_funding_blueprint.route("/sign-up/<uuid:collection_id>/contact-support", methods=["GET"])
def public_sign_up_contact_support(collection_id: uuid.UUID) -> ResponseReturnValue:
    collection = _check_sign_up_page_available(get_collection(collection_id))
    return _render_sign_up_page("access_grant_funding/public_sign_up/contact_support.html", collection)
