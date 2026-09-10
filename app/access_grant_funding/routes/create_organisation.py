from collections.abc import Callable
from typing import Any

import sentry_sdk
from flask import abort, redirect, render_template, request, session, url_for
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
    get_sign_up_modes,
    sign_up_as_grant_recipient,
)
from app.access_grant_funding.routes import access_grant_funding_blueprint
from app.access_grant_funding.session_models import (
    CompleteCreateOrganisationSession,
    CreateOrganisationSession,
    NamedCreateOrganisationSession,
    SignUpOrganisationType,
)
from app.common.auth.decorators import has_feature_flag_enabled, requires_passed_eligibility
from app.common.data import interfaces
from app.common.data.interfaces.collections import get_collection_by_slug
from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.interfaces.grants import get_grant_by_slug
from app.common.data.interfaces.organisations import (
    create_organisation,
    organisation_name_exists,
    organisation_typed_id_exists,
)
from app.common.data.types import OrganisationModeEnum, OrganisationType
from app.common.data.utils import generate_organisation_custom_code
from app.common.forms import GenericSubmitForm
from app.common.helpers.feature_flags import FeatureFlags
from app.constants import CHECK_YOUR_ANSWERS, SESSION_CREATE_ORGANISATION
from app.extensions import auto_commit_after_request, companies_house_service
from app.services.companies_house import CompaniesHouseError, CompaniesHouseNotFoundError, CompanySearchResults


def _organisation_already_registered(org_session: CreateOrganisationSession, mode: OrganisationModeEnum) -> bool:
    """Whether the organisation described by the sign up session already exists in the service."""
    assert org_session.name is not None
    if organisation_name_exists(org_session.name, mode=mode):
        return True
    return org_session.is_registered_company and organisation_typed_id_exists(
        OrganisationType.COMPANY, org_session.typed_id, mode=mode
    )


def _search_pagination(results: CompanySearchResults, page_url: Callable[[int], str]) -> dict[str, Any] | None:
    """Parameters for the GOV.UK pagination component: first and last pages, the current page and its neighbours."""
    if results.total_pages <= 1:
        return None

    shown = {1, results.total_pages, results.page - 1, results.page, results.page + 1}
    items: list[dict[str, Any]] = []
    for number in range(1, results.total_pages + 1):
        if number not in shown:
            if not items[-1].get("ellipsis"):
                items.append({"ellipsis": True})
            continue
        items.append({"number": number, "href": page_url(number), "current": number == results.page})

    return {
        "previous": {"href": page_url(results.page - 1)} if results.page > 1 else None,
        "next": {"href": page_url(results.page + 1)} if results.page < results.total_pages else None,
        "items": items,
    }


def _organisation_details_url(
    org_session: CreateOrganisationSession, grant_slug: str, collection_slug: str, source: str | None = None
) -> str:
    """The step that collected the organisation's details, which differs for companies found on Companies House."""
    return url_for(
        "access_grant_funding.create_organisation_company_search"
        if org_session.is_registered_company
        else "access_grant_funding.create_organisation_name",
        grant_slug=grant_slug,
        collection_slug=collection_slug,
        source=source,
    )


@access_grant_funding_blueprint.route(
    "/grant/<string:grant_slug>/<string:collection_slug>/create-organisation/organisation-type", methods=["GET", "POST"]
)
@requires_passed_eligibility
@requires_create_organisation_session()
def create_organisation_type(
    grant_slug: str, collection_slug: str, org_session: CreateOrganisationSession
) -> ResponseReturnValue:
    grant = get_grant_by_slug(grant_slug)
    collection = get_collection_by_slug(grant_id=grant.id, slug=collection_slug)

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
        # registered companies are found on Companies House, unless one has already been selected and the user is
        # just confirming the type from check your answers
        if (
            org_session.organisation_type == SignUpOrganisationType.COMPANY
            and FeatureFlags.ACCESS_GRANT_FUNDING_COMPANIES_HOUSE_LOOKUP.is_enabled
            and not (from_check_your_answers and org_session.is_registered_company)
        ):
            return redirect(
                url_for(
                    "access_grant_funding.create_organisation_company_search",
                    grant_slug=grant_slug,
                    collection_slug=collection_slug,
                    source=CHECK_YOUR_ANSWERS if from_check_your_answers else None,
                )
            )
        # changing type away from a company found on Companies House leaves nothing to identify the organisation by,
        # so the name is asked for before returning to check your answers
        if from_check_your_answers and org_session.typed_id:
            return redirect(check_your_answers_url)
        return redirect(
            url_for(
                "access_grant_funding.create_organisation_name",
                grant_slug=grant_slug,
                collection_slug=collection_slug,
                source=CHECK_YOUR_ANSWERS if from_check_your_answers else None,
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
@requires_create_organisation_session()
def create_organisation_local_authority(
    grant_slug: str, collection_slug: str, org_session: CreateOrganisationSession
) -> ResponseReturnValue:
    grant = get_grant_by_slug(grant_slug)
    collection = get_collection_by_slug(grant_id=grant.id, slug=collection_slug)

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
@requires_create_organisation_session()
def create_organisation_name(
    grant_slug: str, collection_slug: str, org_session: CreateOrganisationSession
) -> ResponseReturnValue:
    grant = get_grant_by_slug(grant_slug)
    collection = get_collection_by_slug(grant_id=grant.id, slug=collection_slug)

    from_check_your_answers = request.args.get("source") == CHECK_YOUR_ANSWERS
    check_your_answers_url = url_for(
        "access_grant_funding.create_organisation_check_your_answers",
        grant_slug=grant_slug,
        collection_slug=collection_slug,
    )

    # registered companies take their name from Companies House rather than this screen, unless a search failed and
    # the user is entering the company's details by hand instead
    company_search_url = url_for(
        "access_grant_funding.create_organisation_company_search",
        grant_slug=grant_slug,
        collection_slug=collection_slug,
        source=CHECK_YOUR_ANSWERS if from_check_your_answers else None,
    )
    uses_company_search = (
        org_session.organisation_type == SignUpOrganisationType.COMPANY
        and FeatureFlags.ACCESS_GRANT_FUNDING_COMPANIES_HOUSE_LOOKUP.is_enabled
    )
    if uses_company_search and not org_session.companies_house_unavailable:
        return redirect(company_search_url)

    form = CreateOrganisationNameForm(obj=org_session)
    if form.validate_on_submit():
        assert form.name.data is not None
        org_session.name = form.name.data
        # organisations named here are considered to have type "OTHER" and are given a generated identifier;
        # a company previously selected from Companies House is superseded by the name given here
        org_session.external_id = generate_organisation_custom_code()
        org_session.companies_house_number = None
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
                "access_grant_funding.create_organisation_allow_team_members",
                grant_slug=grant_slug,
                collection_slug=collection_slug,
            )
        )

    back_link_href = (
        check_your_answers_url
        if from_check_your_answers
        else company_search_url
        if uses_company_search
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
@requires_create_organisation_session(NamedCreateOrganisationSession)
def create_organisation_already_exists(
    grant_slug: str, collection_slug: str, org_session: NamedCreateOrganisationSession
) -> ResponseReturnValue:
    grant = get_grant_by_slug(grant_slug)
    collection = get_collection_by_slug(grant_id=grant.id, slug=collection_slug)

    from_check_your_answers = request.args.get("source") == CHECK_YOUR_ANSWERS
    organisation_details_url = _organisation_details_url(
        org_session, grant_slug, collection_slug, source=CHECK_YOUR_ANSWERS if from_check_your_answers else None
    )

    modes = get_sign_up_modes(interfaces.user.get_current_user())

    # double checks the current session organisation is in this state before presenting it
    # going back and forward will change the state but this screen will be stored in
    # the browser history
    if not _organisation_already_registered(org_session, modes.organisation):
        return redirect(organisation_details_url)

    return render_template(
        "access_grant_funding/create_organisation/organisation_already_exists.html",
        grant=grant,
        collection=collection,
        organisation_name=org_session.name,
        back_link_href=organisation_details_url,
    )


@access_grant_funding_blueprint.route(
    "/grant/<string:grant_slug>/<string:collection_slug>/create-organisation/allow-team-members",
    methods=["GET", "POST"],
)
@requires_passed_eligibility
@requires_create_organisation_session(NamedCreateOrganisationSession)
def create_organisation_allow_team_members(
    grant_slug: str, collection_slug: str, org_session: NamedCreateOrganisationSession
) -> ResponseReturnValue:
    grant = get_grant_by_slug(grant_slug)
    collection = get_collection_by_slug(grant_id=grant.id, slug=collection_slug)

    user = interfaces.user.get_current_user()
    user_name_url = url_for(
        "access_grant_funding.create_organisation_user_name",
        grant_slug=grant_slug,
        collection_slug=collection_slug,
    )

    # this page isn't needed for shared emails
    if not org_session.can_share_email_domain:
        return redirect(user_name_url)

    from_check_your_answers = request.args.get("source") == CHECK_YOUR_ANSWERS
    check_your_answers_url = url_for(
        "access_grant_funding.create_organisation_check_your_answers",
        grant_slug=grant_slug,
        collection_slug=collection_slug,
    )

    form = CreateOrganisationAllowTeamMembersForm(obj=org_session, organisation_name=org_session.name)
    if form.validate_on_submit():
        org_session.allow_team_members = form.allow_team_members.data == "True"
        session[SESSION_CREATE_ORGANISATION] = org_session.to_session_dict()
        if from_check_your_answers:
            return redirect(check_your_answers_url)
        return redirect(user_name_url)

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
        "access_grant_funding/create_organisation/allow_team_members.html",
        form=form,
        grant=grant,
        collection=collection,
        organisation_name=org_session.name,
        email_domain=user.email_domain,
        back_link_href=back_link_href,
    )


@access_grant_funding_blueprint.route(
    "/grant/<string:grant_slug>/<string:collection_slug>/create-organisation/your-full-name", methods=["GET", "POST"]
)
@requires_passed_eligibility
@requires_create_organisation_session()
def create_organisation_user_name(
    grant_slug: str, collection_slug: str, org_session: CreateOrganisationSession
) -> ResponseReturnValue:
    grant = get_grant_by_slug(grant_slug)
    collection = get_collection_by_slug(grant_id=grant.id, slug=collection_slug)

    check_your_answers_url = url_for(
        "access_grant_funding.create_organisation_check_your_answers",
        grant_slug=grant_slug,
        collection_slug=collection_slug,
    )

    # we already hold a name for this user, so there is nothing to ask them and this step drops out of the journey
    if not org_session.needs_user_name:
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
            "access_grant_funding.create_organisation_allow_team_members",
            grant_slug=grant_slug,
            collection_slug=collection_slug,
        )
        if org_session.can_share_email_domain
        else _organisation_details_url(org_session, grant_slug, collection_slug)
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
@requires_create_organisation_session(CompleteCreateOrganisationSession)
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
                # TODO: charities are considered OTHER until there is a way to look up their Charity Commission
                #       number, as there is for companies through Companies House
                type_=OrganisationType.COMPANY if org_session.is_registered_company else OrganisationType.OTHER,
                typed_id=org_session.typed_id,
                mode=modes.organisation,
                domains=[user.email_domain] if org_session.allow_team_members else None,
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

        if org_session.needs_user_name:
            interfaces.user.set_user_name(user, org_session.user_name)

        grant_recipient = sign_up_as_grant_recipient(
            user=user, grant=grant, collection=collection, organisation=organisation, mode=modes.grant_recipient
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
        # avoids optionally skipped steps based on
        # how we've arrived here
        back_link_href=url_for(
            "access_grant_funding.create_organisation_user_name",
            grant_slug=grant_slug,
            collection_slug=collection_slug,
        )
        if org_session.needs_user_name
        else url_for(
            "access_grant_funding.create_organisation_allow_team_members",
            grant_slug=grant_slug,
            collection_slug=collection_slug,
        )
        if org_session.can_share_email_domain
        else _organisation_details_url(org_session, grant_slug, collection_slug),
    )


@access_grant_funding_blueprint.route(
    "/grant/<string:grant_slug>/<string:collection_slug>/create-organisation/company-search", methods=["GET", "POST"]
)
@requires_passed_eligibility
@has_feature_flag_enabled(FeatureFlags.ACCESS_GRANT_FUNDING_COMPANIES_HOUSE_LOOKUP)
@requires_create_organisation_session()
def create_organisation_company_search(
    grant_slug: str, collection_slug: str, org_session: CreateOrganisationSession
) -> ResponseReturnValue:
    grant = get_grant_by_slug(grant_slug)
    collection = get_collection_by_slug(grant_id=grant.id, slug=collection_slug)

    from_check_your_answers = request.args.get("source") == CHECK_YOUR_ANSWERS
    source = CHECK_YOUR_ANSWERS if from_check_your_answers else None
    organisation_type_url = url_for(
        "access_grant_funding.create_organisation_type",
        grant_slug=grant_slug,
        collection_slug=collection_slug,
        source=source,
    )

    # double checks the current session type is in this state before presenting it
    # going back and forward will change the state but this screen will be stored in
    # the browser history
    if org_session.organisation_type != SignUpOrganisationType.COMPANY:
        return redirect(organisation_type_url)

    # a search is a GET with the query in the URL so that the results can be revisited with the back button;
    # submitting the form validates the query and redirects to that URL
    query = request.args.get("q", "").strip() if request.method == "GET" else ""
    form = CompaniesHouseSearchForm(query=query)
    if form.validate_on_submit():
        return redirect(
            url_for(
                "access_grant_funding.create_organisation_company_search",
                grant_slug=grant_slug,
                collection_slug=collection_slug,
                q=form.query.data,
                source=source,
            )
        )

    page = max(request.args.get("page", 1, type=int) or 1, 1)
    results = None
    pagination = None
    search_unavailable = False
    if query:
        try:
            results = companies_house_service.search_companies(query, page=page)
        except CompaniesHouseError as e:
            # the register has no page of results this far in; start from the first page
            if isinstance(e, CompaniesHouseNotFoundError) and page > 1:
                return redirect(
                    url_for(
                        "access_grant_funding.create_organisation_company_search",
                        grant_slug=grant_slug,
                        collection_slug=collection_slug,
                        q=query,
                        source=source,
                    )
                )
            # a developer should look into why the register couldn't be searched, and in the meantime the user can
            # enter the company's details by hand rather than being stuck
            sentry_sdk.capture_exception(e)
            org_session.companies_house_unavailable = True
            session[SESSION_CREATE_ORGANISATION] = org_session.to_session_dict()
            search_unavailable = True
        else:
            pagination = _search_pagination(
                results,
                lambda number: url_for(
                    "access_grant_funding.create_organisation_company_search",
                    grant_slug=grant_slug,
                    collection_slug=collection_slug,
                    q=query,
                    page=number if number > 1 else None,
                    source=source,
                ),
            )

    back_link_href = (
        url_for(
            "access_grant_funding.create_organisation_company_search",
            grant_slug=grant_slug,
            collection_slug=collection_slug,
            source=source,
        )
        if query
        else organisation_type_url
    )
    return render_template(
        "access_grant_funding/create_organisation/company_search.html",
        form=form,
        grant=grant,
        collection=collection,
        query=query,
        results=results,
        pagination=pagination,
        search_unavailable=search_unavailable,
        organisation_name_url=url_for(
            "access_grant_funding.create_organisation_name",
            grant_slug=grant_slug,
            collection_slug=collection_slug,
            source=source,
        ),
        from_check_your_answers=from_check_your_answers,
        back_link_href=back_link_href,
    )


@access_grant_funding_blueprint.route(
    "/grant/<string:grant_slug>/<string:collection_slug>/create-organisation/select-company/<string:company_number>",
    methods=["GET"],
)
@requires_passed_eligibility
@has_feature_flag_enabled(FeatureFlags.ACCESS_GRANT_FUNDING_COMPANIES_HOUSE_LOOKUP)
@requires_create_organisation_session()
def create_organisation_company_select(
    grant_slug: str, collection_slug: str, company_number: str, org_session: CreateOrganisationSession
) -> ResponseReturnValue:
    from_check_your_answers = request.args.get("source") == CHECK_YOUR_ANSWERS
    source = CHECK_YOUR_ANSWERS if from_check_your_answers else None

    if org_session.organisation_type != SignUpOrganisationType.COMPANY:
        return redirect(
            url_for(
                "access_grant_funding.create_organisation_type",
                grant_slug=grant_slug,
                collection_slug=collection_slug,
                source=source,
            )
        )

    try:
        company = companies_house_service.get_company(company_number)
    except CompaniesHouseNotFoundError:
        return abort(404)
    except CompaniesHouseError as e:
        # the search page explains that Companies House is unavailable, or shows the results again if it recovered
        sentry_sdk.capture_exception(e)
        return redirect(
            url_for(
                "access_grant_funding.create_organisation_company_search",
                grant_slug=grant_slug,
                collection_slug=collection_slug,
                q=company_number,
                source=source,
            )
        )

    org_session.name = company.company_name
    org_session.companies_house_number = company.company_number
    org_session.external_id = None
    session[SESSION_CREATE_ORGANISATION] = org_session.to_session_dict()

    modes = get_sign_up_modes(interfaces.user.get_current_user())
    if _organisation_already_registered(org_session, modes.organisation):
        return redirect(
            url_for(
                "access_grant_funding.create_organisation_already_exists",
                grant_slug=grant_slug,
                collection_slug=collection_slug,
                source=source,
            )
        )

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
            "access_grant_funding.create_organisation_allow_team_members",
            grant_slug=grant_slug,
            collection_slug=collection_slug,
        )
    )
