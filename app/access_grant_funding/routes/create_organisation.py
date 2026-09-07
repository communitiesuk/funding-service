from flask import redirect, render_template, request, session, url_for
from flask.typing import ResponseReturnValue

from app.access_grant_funding.forms import CreateOrganisationNameForm, CreateOrganisationTypeForm
from app.access_grant_funding.routes import access_grant_funding_blueprint
from app.access_grant_funding.session_models import CreateOrganisationSession, SignUpOrganisationType
from app.common.auth.decorators import requires_passed_eligibility
from app.common.data.interfaces.collections import get_collection_by_slug
from app.common.data.interfaces.grants import get_grant_by_slug
from app.common.data.utils import generate_organisation_custom_code
from app.common.forms import GenericSubmitForm
from app.constants import CHECK_YOUR_ANSWERS, SESSION_CREATE_ORGANISATION


@access_grant_funding_blueprint.route(
    "/grant/<string:grant_slug>/<string:collection_slug>/create-organisation/organisation-type", methods=["GET", "POST"]
)
@requires_passed_eligibility
def create_organisation_type(grant_slug: str, collection_slug: str) -> ResponseReturnValue:
    grant = get_grant_by_slug(grant_slug)
    collection = get_collection_by_slug(grant_id=grant.id, slug=collection_slug)

    org_session = CreateOrganisationSession.from_session(
        collection_id=collection.id, session_data=session.get(SESSION_CREATE_ORGANISATION, {})
    )
    if org_session is None:
        return redirect(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant_slug, collection_slug=collection_slug)
        )

    from_check_your_answers = request.args.get("source") == CHECK_YOUR_ANSWERS
    check_your_answers_url = url_for(
        "access_grant_funding.create_organisation_check_your_answers",
        grant_slug=grant_slug,
        collection_slug=collection_slug,
    )

    form = CreateOrganisationTypeForm(obj=org_session)
    if form.validate_on_submit():
        org_session.organisation_type = SignUpOrganisationType(form.organisation_type.data)
        session[SESSION_CREATE_ORGANISATION] = org_session.to_session_dict()
        if from_check_your_answers:
            return redirect(check_your_answers_url)
        return redirect(
            url_for(
                "access_grant_funding.create_organisation_name",
                grant_slug=grant_slug,
                collection_slug=collection_slug,
            )
        )

    back_link_href = (
        check_your_answers_url
        if from_check_your_answers
        else url_for("access_grant_funding.eligible_to_apply", grant_slug=grant_slug, collection_slug=collection_slug)
    )
    return render_template(
        "access_grant_funding/create_organisation/organisation_type.html",
        form=form,
        grant=grant,
        collection=collection,
        back_link_href=back_link_href,
    )


@access_grant_funding_blueprint.route(
    "/grant/<string:grant_slug>/<string:collection_slug>/create-organisation/organisation-name", methods=["GET", "POST"]
)
@requires_passed_eligibility
def create_organisation_name(grant_slug: str, collection_slug: str) -> ResponseReturnValue:
    grant = get_grant_by_slug(grant_slug)
    collection = get_collection_by_slug(grant_id=grant.id, slug=collection_slug)

    org_session = CreateOrganisationSession.from_session(
        collection_id=collection.id, session_data=session.get(SESSION_CREATE_ORGANISATION, {})
    )
    if org_session is None:
        return redirect(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant_slug, collection_slug=collection_slug)
        )

    from_check_your_answers = request.args.get("source") == CHECK_YOUR_ANSWERS
    check_your_answers_url = url_for(
        "access_grant_funding.create_organisation_check_your_answers",
        grant_slug=grant_slug,
        collection_slug=collection_slug,
    )

    form = CreateOrganisationNameForm(obj=org_session)
    if form.validate_on_submit():
        assert form.name.data is not None
        org_session.name = form.name.data
        # for now all organisations are going to be considered to have type "OTHER" which means that
        # we'll generate their identifier, other ways of looking up organisations will have their own
        # methods for finding the name and external ID
        org_session.external_id = generate_organisation_custom_code()
        session[SESSION_CREATE_ORGANISATION] = org_session.to_session_dict()
        return redirect(check_your_answers_url)

    back_link_href = (
        check_your_answers_url
        if from_check_your_answers
        else url_for(
            "access_grant_funding.create_organisation_type",
            grant_slug=grant_slug,
            collection_slug=collection_slug,
        )
    )
    return render_template(
        "access_grant_funding/create_organisation/organisation_name.html",
        form=form,
        grant=grant,
        collection=collection,
        back_link_href=back_link_href,
    )


@access_grant_funding_blueprint.route(
    "/grant/<string:grant_slug>/<string:collection_slug>/create-organisation/check-your-answers",
    methods=["GET", "POST"],
)
@requires_passed_eligibility
def create_organisation_check_your_answers(grant_slug: str, collection_slug: str) -> ResponseReturnValue:
    grant = get_grant_by_slug(grant_slug)
    collection = get_collection_by_slug(grant_id=grant.id, slug=collection_slug)

    org_session = CreateOrganisationSession.from_session(
        collection_id=collection.id, session_data=session.get(SESSION_CREATE_ORGANISATION, {})
    )
    session_complete = org_session is not None and all(
        [bool(i) for i in [org_session.organisation_type, org_session.name, org_session.external_id]]
    )
    if not session_complete:
        return redirect(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant_slug, collection_slug=collection_slug)
        )

    form = GenericSubmitForm()
    if form.validate_on_submit():
        # TODO: create the organisation (type OTHER, map external_id from the session to custom code)
        #       then allow existing code to connect org to grant as-is
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
        org_session=org_session,
        back_link_href=url_for(
            "access_grant_funding.create_organisation_name",
            grant_slug=grant_slug,
            collection_slug=collection_slug,
        ),
    )
