from flask import current_app, redirect, render_template, request, session, url_for
from flask.typing import ResponseReturnValue
from pydantic import ValidationError

from app.access_grant_funding.forms import CreateOrganisationNameForm, CreateOrganisationTypeForm
from app.access_grant_funding.routes import access_grant_funding_blueprint
from app.access_grant_funding.session_models import CreateOrganisationSession, SignUpOrganisationType
from app.common.auth.decorators import requires_passed_eligibility
from app.common.data.interfaces.collections import get_collection_by_slug
from app.common.data.interfaces.grants import get_grant_by_slug
from app.common.data.models import Collection
from app.common.data.utils import generate_organisation_custom_code
from app.common.forms import GenericSubmitForm
from app.constants import CHECK_YOUR_ANSWERS, SESSION_CREATE_ORGANISATION

_CREATE_ORGANISATION_URL_PREFIX = "/grant/<string:grant_slug>/<string:collection_slug>/create-organisation"


def _load_create_organisation_session(collection: Collection) -> CreateOrganisationSession | None:
    try:
        org_session = CreateOrganisationSession.from_session(session.get(SESSION_CREATE_ORGANISATION, {}))
    except ValidationError:
        return None
    # a Deliver user testing Access bypasses the session check in `is_signing_up`, so pin the set up to one collection
    return org_session if org_session.collection_id == collection.id else None


def _save_create_organisation_session(org_session: CreateOrganisationSession) -> None:
    session[SESSION_CREATE_ORGANISATION] = org_session.to_session_dict()


def _eligible_to_apply_redirect(grant_slug: str, collection_slug: str) -> ResponseReturnValue:
    return redirect(
        url_for("access_grant_funding.eligible_to_apply", grant_slug=grant_slug, collection_slug=collection_slug)
    )


@access_grant_funding_blueprint.route(f"{_CREATE_ORGANISATION_URL_PREFIX}/organisation-type", methods=["GET", "POST"])
@requires_passed_eligibility
def create_organisation_type(grant_slug: str, collection_slug: str) -> ResponseReturnValue:
    grant = get_grant_by_slug(grant_slug)
    collection = get_collection_by_slug(grant_id=grant.id, slug=collection_slug)

    org_session = _load_create_organisation_session(collection)
    if org_session is None:
        return _eligible_to_apply_redirect(grant_slug, collection_slug)

    from_check_your_answers = request.args.get("source") == CHECK_YOUR_ANSWERS

    form = CreateOrganisationTypeForm(obj=org_session)
    if form.validate_on_submit():
        org_session.organisation_type = SignUpOrganisationType(form.organisation_type.data)
        _save_create_organisation_session(org_session)
        if from_check_your_answers:
            return redirect(
                url_for(
                    "access_grant_funding.create_organisation_check_your_answers",
                    grant_slug=grant_slug,
                    collection_slug=collection_slug,
                )
            )
        return redirect(
            url_for(
                "access_grant_funding.create_organisation_name",
                grant_slug=grant_slug,
                collection_slug=collection_slug,
            )
        )

    back_link_href = (
        url_for(
            "access_grant_funding.create_organisation_check_your_answers",
            grant_slug=grant_slug,
            collection_slug=collection_slug,
        )
        if from_check_your_answers
        else url_for("access_grant_funding.eligible_to_apply", grant_slug=grant_slug, collection_slug=collection_slug)
    )
    return render_template(
        "access_grant_funding/create_organisation/organisation_type.html",
        form=form,
        grant=grant,
        collection=collection,
        companies_house_url=current_app.config["COMPANIES_HOUSE_URL"],
        back_link_href=back_link_href,
    )


@access_grant_funding_blueprint.route(f"{_CREATE_ORGANISATION_URL_PREFIX}/organisation-name", methods=["GET", "POST"])
@requires_passed_eligibility
def create_organisation_name(grant_slug: str, collection_slug: str) -> ResponseReturnValue:
    grant = get_grant_by_slug(grant_slug)
    collection = get_collection_by_slug(grant_id=grant.id, slug=collection_slug)

    org_session = _load_create_organisation_session(collection)
    if org_session is None:
        return _eligible_to_apply_redirect(grant_slug, collection_slug)

    from_check_your_answers = request.args.get("source") == CHECK_YOUR_ANSWERS

    form = CreateOrganisationNameForm(obj=org_session)
    if form.validate_on_submit():
        assert form.name.data is not None
        org_session.name = form.name.data
        # Generate once so editing the name via a change link keeps the same code
        if not org_session.custom_code:
            org_session.custom_code = generate_organisation_custom_code()
        _save_create_organisation_session(org_session)
        return redirect(
            url_for(
                "access_grant_funding.create_organisation_check_your_answers",
                grant_slug=grant_slug,
                collection_slug=collection_slug,
            )
        )

    back_link_href = url_for(
        "access_grant_funding.create_organisation_check_your_answers"
        if from_check_your_answers
        else "access_grant_funding.create_organisation_type",
        grant_slug=grant_slug,
        collection_slug=collection_slug,
    )
    return render_template(
        "access_grant_funding/create_organisation/organisation_name.html",
        form=form,
        grant=grant,
        collection=collection,
        back_link_href=back_link_href,
    )


@access_grant_funding_blueprint.route(f"{_CREATE_ORGANISATION_URL_PREFIX}/check-your-answers", methods=["GET", "POST"])
@requires_passed_eligibility
def create_organisation_check_your_answers(grant_slug: str, collection_slug: str) -> ResponseReturnValue:
    grant = get_grant_by_slug(grant_slug)
    collection = get_collection_by_slug(grant_id=grant.id, slug=collection_slug)

    org_session = _load_create_organisation_session(collection)
    if org_session is None or org_session.organisation_type is None or not org_session.name:
        return _eligible_to_apply_redirect(grant_slug, collection_slug)

    form = GenericSubmitForm()
    if form.validate_on_submit():
        # TODO: create the organisation (type OTHER, custom_code from the session), the grant recipient and the
        #       user's DATA_PROVIDER permissions, then clear_public_sign_up_session() and redirect to list_collections
        return redirect(
            url_for(
                "access_grant_funding.create_organisation_check_your_answers",
                grant_slug=grant_slug,
                collection_slug=collection_slug,
            )
        )

    return render_template(
        "access_grant_funding/create_organisation/check_your_answers.html",
        form=form,
        grant=grant,
        collection=collection,
        organisation_session=org_session,
        organisation_type_label=org_session.organisation_type.label,
        check_your_answers_source=CHECK_YOUR_ANSWERS,
        service_desk_url=current_app.config["ACCESS_SERVICE_DESK_URL"],
        back_link_href=url_for(
            "access_grant_funding.create_organisation_name",
            grant_slug=grant_slug,
            collection_slug=collection_slug,
        ),
    )
