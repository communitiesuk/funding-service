from flask import redirect, render_template, request, session, url_for
from flask.typing import ResponseReturnValue

from app.access_grant_funding.forms import CreateOrganisationNameForm, CreateOrganisationTypeForm, UserNameForm
from app.access_grant_funding.helpers import (
    complete_public_sign_up_session_and_redirect,
    get_sign_up_modes,
    sign_up_as_grant_recipient,
)
from app.access_grant_funding.routes import access_grant_funding_blueprint
from app.access_grant_funding.session_models import CreateOrganisationSession, SignUpOrganisationType
from app.common.auth.decorators import requires_passed_eligibility
from app.common.data import interfaces
from app.common.data.interfaces.collections import get_collection_by_slug
from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.interfaces.grants import get_grant_by_slug
from app.common.data.interfaces.organisations import create_organisation, organisation_name_exists
from app.common.data.types import OrganisationType
from app.common.data.utils import generate_organisation_custom_code
from app.common.forms import GenericSubmitForm
from app.constants import CHECK_YOUR_ANSWERS, SESSION_CREATE_ORGANISATION
from app.extensions import auto_commit_after_request


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

        # user wasn't matched correctly, steers to support at the moment
        # but will link in with the request access journey to more specific
        if org_session.organisation_type == SignUpOrganisationType.LOCAL_AUTHORITY:
            return redirect(
                url_for(
                    "access_grant_funding.create_organisation_local_authority",
                    grant_slug=grant_slug,
                    collection_slug=collection_slug,
                    source=CHECK_YOUR_ANSWERS if from_check_your_answers else None,
                )
            )
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
    "/grant/<string:grant_slug>/<string:collection_slug>/create-organisation/local-authority", methods=["GET"]
)
@requires_passed_eligibility
def create_organisation_local_authority(grant_slug: str, collection_slug: str) -> ResponseReturnValue:
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
    organisation_type_url = url_for(
        "access_grant_funding.create_organisation_type",
        grant_slug=grant_slug,
        collection_slug=collection_slug,
        source=CHECK_YOUR_ANSWERS if from_check_your_answers else None,
    )

    # double checks the current session type is in this state before presenting it
    # going back and forward will change the state but this screen will be stored in
    # the browser history
    if org_session.organisation_type != SignUpOrganisationType.LOCAL_AUTHORITY:
        return redirect(organisation_type_url)

    return render_template(
        "access_grant_funding/create_organisation/local_authority.html",
        grant=grant,
        collection=collection,
        back_link_href=organisation_type_url,
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

        modes = get_sign_up_modes(interfaces.user.get_current_user())
        if organisation_name_exists(org_session.name, mode=modes.organisation):
            return redirect(
                url_for(
                    "access_grant_funding.create_organisation_already_exists",
                    grant_slug=grant_slug,
                    collection_slug=collection_slug,
                    source=CHECK_YOUR_ANSWERS if from_check_your_answers else None,
                )
            )
        if from_check_your_answers:
            return redirect(check_your_answers_url)
        return redirect(
            url_for(
                "access_grant_funding.create_organisation_user_name",
                grant_slug=grant_slug,
                collection_slug=collection_slug,
            )
        )

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
    "/grant/<string:grant_slug>/<string:collection_slug>/create-organisation/organisation-already-exists",
    methods=["GET"],
)
@requires_passed_eligibility
def create_organisation_already_exists(grant_slug: str, collection_slug: str) -> ResponseReturnValue:
    grant = get_grant_by_slug(grant_slug)
    collection = get_collection_by_slug(grant_id=grant.id, slug=collection_slug)

    org_session = CreateOrganisationSession.from_session(
        collection_id=collection.id, session_data=session.get(SESSION_CREATE_ORGANISATION, {})
    )
    if org_session is None or not all([bool(i) for i in [org_session.name]]):
        return redirect(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant_slug, collection_slug=collection_slug)
        )

    from_check_your_answers = request.args.get("source") == CHECK_YOUR_ANSWERS
    organisation_name_url = url_for(
        "access_grant_funding.create_organisation_name",
        grant_slug=grant_slug,
        collection_slug=collection_slug,
        source=CHECK_YOUR_ANSWERS if from_check_your_answers else None,
    )

    modes = get_sign_up_modes(interfaces.user.get_current_user())

    # double checks the current session name is in this state before presenting it
    # going back and forward will change the state but this screen will be stored in
    # the browser history
    if not organisation_name_exists(org_session.name, mode=modes.organisation):
        return redirect(organisation_name_url)

    return render_template(
        "access_grant_funding/create_organisation/organisation_already_exists.html",
        grant=grant,
        collection=collection,
        organisation_name=org_session.name,
        back_link_href=organisation_name_url,
    )


@access_grant_funding_blueprint.route(
    "/grant/<string:grant_slug>/<string:collection_slug>/create-organisation/your-full-name", methods=["GET", "POST"]
)
@requires_passed_eligibility
def create_organisation_user_name(grant_slug: str, collection_slug: str) -> ResponseReturnValue:
    grant = get_grant_by_slug(grant_slug)
    collection = get_collection_by_slug(grant_id=grant.id, slug=collection_slug)

    org_session = CreateOrganisationSession.from_session(
        collection_id=collection.id, session_data=session.get(SESSION_CREATE_ORGANISATION, {})
    )
    if org_session is None:
        return redirect(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant_slug, collection_slug=collection_slug)
        )

    check_your_answers_url = url_for(
        "access_grant_funding.create_organisation_check_your_answers",
        grant_slug=grant_slug,
        collection_slug=collection_slug,
    )

    # we already hold a name for this user, so there is nothing to ask them and this step drops out of the journey
    if interfaces.user.get_current_user().name:
        return redirect(check_your_answers_url)

    from_check_your_answers = request.args.get("source") == CHECK_YOUR_ANSWERS

    form = UserNameForm(obj=org_session)
    if form.validate_on_submit():
        assert form.user_name.data is not None
        org_session.user_name = form.user_name.data
        session[SESSION_CREATE_ORGANISATION] = org_session.to_session_dict()
        return redirect(check_your_answers_url)

    back_link_href = (
        check_your_answers_url
        if from_check_your_answers
        else url_for(
            "access_grant_funding.create_organisation_name",
            grant_slug=grant_slug,
            collection_slug=collection_slug,
        )
    )
    return render_template(
        "access_grant_funding/user_name.html",
        form=form,
        grant=grant,
        collection=collection,
        is_setting_up_organisation=True,
        back_link_href=back_link_href,
    )


@access_grant_funding_blueprint.route(
    "/grant/<string:grant_slug>/<string:collection_slug>/create-organisation/check-your-answers",
    methods=["GET", "POST"],
)
@requires_passed_eligibility
@auto_commit_after_request
def create_organisation_check_your_answers(grant_slug: str, collection_slug: str) -> ResponseReturnValue:
    grant = get_grant_by_slug(grant_slug)
    collection = get_collection_by_slug(grant_id=grant.id, slug=collection_slug)
    user = interfaces.user.get_current_user()

    org_session = CreateOrganisationSession.from_session(
        collection_id=collection.id, session_data=session.get(SESSION_CREATE_ORGANISATION, {})
    )
    if org_session is None or not all(
        [
            bool(i)
            for i in [
                org_session.organisation_type,
                org_session.name,
                org_session.external_id,
                (org_session.user_name or user.name),
            ]
        ]
    ):
        return redirect(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant_slug, collection_slug=collection_slug)
        )

    form = GenericSubmitForm()
    if form.validate_on_submit():
        modes = get_sign_up_modes(user)
        try:
            organisation = create_organisation(
                name=org_session.name,
                # TODO: for now all organisations are considered OTHER but when the different
                #       mechanisms for fetching the required identifiers for companies and charities
                #       are implemented this should match their appropriate type
                type_=OrganisationType.OTHER,
                typed_id=org_session.external_id,
                mode=modes.organisation,
            )
        except DuplicateValueError:
            return redirect(
                url_for(
                    "access_grant_funding.create_organisation_already_exists",
                    grant_slug=grant_slug,
                    collection_slug=collection_slug,
                    source=CHECK_YOUR_ANSWERS,
                )
            )

        if not user.name:
            interfaces.user.set_user_name(user, org_session.user_name)

        grant_recipient = sign_up_as_grant_recipient(
            user=user, grant=grant, organisation=organisation, mode=modes.grant_recipient
        )
        return complete_public_sign_up_session_and_redirect(
            user=user, collection=collection, grant_recipient=grant_recipient, mode=modes.submission
        )

    return render_template(
        "access_grant_funding/create_organisation/check_your_answers.html",
        form=form,
        grant=grant,
        collection=collection,
        org_session=org_session,
        back_link_href=url_for(
            "access_grant_funding.create_organisation_name"
            if user.name
            else "access_grant_funding.create_organisation_user_name",
            grant_slug=grant_slug,
            collection_slug=collection_slug,
        ),
    )
