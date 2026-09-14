from flask import current_app, redirect, render_template
from flask.typing import ResponseReturnValue

from app.access_grant_funding.decorators import requires_create_organisation_session
from app.access_grant_funding.forms import (
    CompaniesHouseSearchForm,
    CreateOrganisationAllowTeamMembersForm,
    CreateOrganisationNameForm,
    CreateOrganisationTypeForm,
    UserNameForm,
)
from app.access_grant_funding.helpers import (
    complete_public_sign_up_session_and_redirect,
    emit_public_sign_up_metric_once,
    get_sign_up_modes,
    sign_up_as_grant_recipient,
)
from app.access_grant_funding.routes import access_grant_funding_blueprint
from app.access_grant_funding.session_models import (
    CompleteCreateOrganisationSession,
    CreateOrganisationPage,
    CreateOrganisationSession,
    NamedCreateOrganisationSession,
    SignUpOrganisationType,
)
from app.common.auth.decorators import has_feature_flag_enabled, requires_passed_eligibility
from app.common.data import interfaces
from app.common.data.interfaces.collections import get_collection_by_slug
from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.interfaces.grants import get_grant_by_slug
from app.common.data.interfaces.organisations import create_organisation, organisation_name_exists
from app.common.data.types import OrganisationType, SubmissionModeEnum
from app.common.forms import GenericSubmitForm
from app.common.helpers.feature_flags import FeatureFlags
from app.extensions import auto_commit_after_request
from app.metrics import MetricAttributeName, MetricEventName


@access_grant_funding_blueprint.route(
    "/grant/<string:grant_slug>/<string:collection_slug>/create-organisation/organisation-type", methods=["GET", "POST"]
)
@requires_passed_eligibility
@requires_create_organisation_session(page=CreateOrganisationPage.TYPE)
def create_organisation_type(
    grant_slug: str, collection_slug: str, org_session: CreateOrganisationSession
) -> ResponseReturnValue:
    grant = get_grant_by_slug(grant_slug)
    collection = get_collection_by_slug(grant_id=grant.id, slug=collection_slug)

    form = CreateOrganisationTypeForm(obj=org_session)
    if form.validate_on_submit():
        org_session.answer_organisation_type(SignUpOrganisationType(form.organisation_type.data))
        return redirect(org_session.next_page)

    return render_template(
        "access_grant_funding/create_organisation/organisation_type.html",
        form=form,
        grant=grant,
        collection=collection,
        back_link_href=org_session.previous_page,
    )


@access_grant_funding_blueprint.route(
    "/grant/<string:grant_slug>/<string:collection_slug>/create-organisation/local-authority", methods=["GET"]
)
@requires_passed_eligibility
@requires_create_organisation_session(page=CreateOrganisationPage.LOCAL_AUTHORITY)
def create_organisation_local_authority(
    grant_slug: str, collection_slug: str, org_session: CreateOrganisationSession
) -> ResponseReturnValue:
    grant = get_grant_by_slug(grant_slug)
    collection = get_collection_by_slug(grant_id=grant.id, slug=collection_slug)

    modes = get_sign_up_modes(interfaces.user.get_current_user())
    if modes.submission == SubmissionModeEnum.LIVE:
        emit_public_sign_up_metric_once(
            MetricEventName.PUBLIC_SIGN_UP_LOCAL_AUTHORITY_SUPPORT_SHOWN,
            collection=collection,
            custom_attributes={MetricAttributeName.SUBMISSION_MODE: str(modes.submission)},
        )

    return render_template(
        "access_grant_funding/create_organisation/local_authority.html",
        grant=grant,
        collection=collection,
        back_link_href=org_session.previous_page,
    )


@access_grant_funding_blueprint.route(
    "/grant/<string:grant_slug>/<string:collection_slug>/create-organisation/company-search", methods=["GET", "POST"]
)
@requires_passed_eligibility
@has_feature_flag_enabled(FeatureFlags.ACCESS_GRANT_FUNDING_COMPANIES_HOUSE_LOOKUP)
@requires_create_organisation_session(page=CreateOrganisationPage.COMPANY_SEARCH)
def create_organisation_company_search(
    grant_slug: str, collection_slug: str, org_session: CreateOrganisationSession
) -> ResponseReturnValue:
    grant = get_grant_by_slug(grant_slug)
    collection = get_collection_by_slug(grant_id=grant.id, slug=collection_slug)

    form = CompaniesHouseSearchForm()
    # TODO: implement search results and selection
    form.validate_on_submit()

    return render_template(
        "access_grant_funding/create_organisation/company_search.html",
        form=form,
        grant=grant,
        collection=collection,
        back_link_href=org_session.previous_page,
    )


@access_grant_funding_blueprint.route(
    "/grant/<string:grant_slug>/<string:collection_slug>/create-organisation/organisation-name", methods=["GET", "POST"]
)
@requires_passed_eligibility
@requires_create_organisation_session(page=CreateOrganisationPage.NAME)
def create_organisation_name(
    grant_slug: str, collection_slug: str, org_session: CreateOrganisationSession
) -> ResponseReturnValue:
    grant = get_grant_by_slug(grant_slug)
    collection = get_collection_by_slug(grant_id=grant.id, slug=collection_slug)

    form = CreateOrganisationNameForm(obj=org_session)
    if form.validate_on_submit():
        assert form.name.data is not None
        org_session.answer_name(form.name.data)

        modes = get_sign_up_modes(interfaces.user.get_current_user())
        if organisation_name_exists(form.name.data, mode=modes.organisation):
            return redirect(org_session.page_url(CreateOrganisationPage.ALREADY_EXISTS))
        return redirect(org_session.next_page)

    return render_template(
        "access_grant_funding/create_organisation/organisation_name.html",
        form=form,
        grant=grant,
        collection=collection,
        back_link_href=org_session.previous_page,
    )


@access_grant_funding_blueprint.route(
    "/grant/<string:grant_slug>/<string:collection_slug>/create-organisation/organisation-already-exists",
    methods=["GET"],
)
@requires_passed_eligibility
@requires_create_organisation_session(page=CreateOrganisationPage.ALREADY_EXISTS)
def create_organisation_already_exists(
    grant_slug: str, collection_slug: str, org_session: NamedCreateOrganisationSession
) -> ResponseReturnValue:
    grant = get_grant_by_slug(grant_slug)
    collection = get_collection_by_slug(grant_id=grant.id, slug=collection_slug)

    modes = get_sign_up_modes(interfaces.user.get_current_user())

    # double checks the current session name is in this state before presenting it
    # going back and forward will change the state but this screen will be stored in
    # the browser history
    if not organisation_name_exists(org_session.name, mode=modes.organisation):
        return redirect(org_session.previous_page)

    return render_template(
        "access_grant_funding/create_organisation/organisation_already_exists.html",
        grant=grant,
        collection=collection,
        organisation_name=org_session.name,
        back_link_href=org_session.previous_page,
    )


@access_grant_funding_blueprint.route(
    "/grant/<string:grant_slug>/<string:collection_slug>/create-organisation/allow-team-members",
    methods=["GET", "POST"],
)
@requires_passed_eligibility
@requires_create_organisation_session(page=CreateOrganisationPage.TEAM_MEMBERS)
def create_organisation_allow_team_members(
    grant_slug: str, collection_slug: str, org_session: NamedCreateOrganisationSession
) -> ResponseReturnValue:
    grant = get_grant_by_slug(grant_slug)
    collection = get_collection_by_slug(grant_id=grant.id, slug=collection_slug)

    user = interfaces.user.get_current_user()
    form = CreateOrganisationAllowTeamMembersForm(obj=org_session, organisation_name=org_session.name)
    if form.validate_on_submit():
        org_session.answer_allow_team_members(form.allow_team_members.data == "True")
        return redirect(org_session.next_page)

    return render_template(
        "access_grant_funding/create_organisation/allow_team_members.html",
        form=form,
        grant=grant,
        collection=collection,
        organisation_name=org_session.name,
        email_domain=user.email_domain,
        back_link_href=org_session.previous_page,
    )


@access_grant_funding_blueprint.route(
    "/grant/<string:grant_slug>/<string:collection_slug>/create-organisation/your-full-name", methods=["GET", "POST"]
)
@requires_passed_eligibility
@requires_create_organisation_session(page=CreateOrganisationPage.USER_NAME)
def create_organisation_user_name(
    grant_slug: str, collection_slug: str, org_session: NamedCreateOrganisationSession
) -> ResponseReturnValue:
    grant = get_grant_by_slug(grant_slug)
    collection = get_collection_by_slug(grant_id=grant.id, slug=collection_slug)

    form = UserNameForm(obj=org_session)
    if form.validate_on_submit():
        assert form.user_name.data is not None
        org_session.answer_user_name(form.user_name.data)
        return redirect(org_session.next_page)

    return render_template(
        "access_grant_funding/user_name.html",
        form=form,
        grant=grant,
        collection=collection,
        is_setting_up_organisation=True,
        back_link_href=org_session.previous_page,
    )


@access_grant_funding_blueprint.route(
    "/grant/<string:grant_slug>/<string:collection_slug>/create-organisation/check-your-answers",
    methods=["GET", "POST"],
)
@requires_passed_eligibility
@auto_commit_after_request
@requires_create_organisation_session(page=CreateOrganisationPage.CHECK_YOUR_ANSWERS)
def create_organisation_check_your_answers(
    grant_slug: str, collection_slug: str, org_session: CompleteCreateOrganisationSession
) -> ResponseReturnValue:
    grant = get_grant_by_slug(grant_slug)
    collection = get_collection_by_slug(grant_id=grant.id, slug=collection_slug)
    user = interfaces.user.get_current_user()

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
                domains=[user.email_domain] if org_session.allow_team_members else None,
            )
            current_app.logger.info(
                "Organisation %(organisation_id)s created. Organisation type was ignored: %(organisation_type)s",
                dict(organisation_id=organisation.external_id, organisation_type=org_session.organisation_type.value),
            )
        except DuplicateValueError:
            return redirect(org_session.page_url(CreateOrganisationPage.ALREADY_EXISTS, from_check_your_answers=True))

        if org_session.needs_user_name:
            interfaces.user.set_user_name(user, org_session.user_name)

        grant_recipient = sign_up_as_grant_recipient(
            user=user,
            grant=grant,
            collection=collection,
            organisation=organisation,
            mode=modes.grant_recipient,
            organisation_created=True,
        )

        if modes.submission == SubmissionModeEnum.LIVE:
            emit_public_sign_up_metric_once(
                MetricEventName.PUBLIC_SIGN_UP_ORGANISATION_CREATED,
                collection=collection,
                grant_recipient=grant_recipient,
                custom_attributes={
                    MetricAttributeName.ORGANISATION_TYPE: str(org_session.organisation_type),
                    MetricAttributeName.SUBMISSION_MODE: str(modes.submission),
                },
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
        pages=CreateOrganisationPage,
        back_link_href=org_session.previous_page,
    )
