import logging
import uuid
from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup
from flask import url_for
from flask_login import login_user
from sqlalchemy import select

from app.access_grant_funding.session_models import (
    CreateOrganisationSession,
    OrganisationIdentification,
    SignUpOrganisationType,
)
from app.common.data.models import GrantRecipient, Organisation
from app.common.data.models_user import UserRole
from app.common.data.types import (
    AuthMethodEnum,
    CollectionStatusEnum,
    GrantRecipientModeEnum,
    GrantRecipientStatusEnum,
    GrantStatusEnum,
    OrganisationModeEnum,
    OrganisationStatus,
    OrganisationType,
    RoleEnum,
    SubmissionModeEnum,
)
from app.common.helpers.collections import get_or_create_unclaimed_submission
from app.common.helpers.feature_flags import FeatureFlags
from app.extensions import companies_house_service
from app.metrics import MetricAttributeName, MetricEventName
from app.services.companies_house import (
    CompaniesHouseDisabledError,
    CompaniesHouseError,
    CompaniesHouseNotFoundError,
    CompanyProfile,
    CompanySearchResults,
)
from tests.utils import (
    AnyStringMatching,
    enable_session_feature_flag,
    get_h1_text,
    get_input_value,
    get_summary_list_value_by_key,
    get_table_row_by_first_column_value,
    page_has_button,
    page_has_error,
    page_has_link,
)


@pytest.fixture()
def sign_up_collection(factories):
    grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug", name="Test grant name")
    return factories.collection.create(
        grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
    )


def _create_organisation_session(
    collection_id, *, needs_user_name: bool = False, can_share_email_domain: bool = True, **answers
) -> CreateOrganisationSession:
    """A session started by a user we already hold a name for, on an email domain they could share."""
    return CreateOrganisationSession(
        collection_id=collection_id,
        needs_user_name=needs_user_name,
        can_share_email_domain=can_share_email_domain,
        **answers,
    )


def _seed_session(client, collection, org_session: CreateOrganisationSession | None = None) -> None:
    with client.session_transaction() as flask_session:
        flask_session["signing_up_for_collection_id"] = collection.id
        if org_session is not None:
            flask_session["create_organisation"] = org_session.to_session_dict()


def _seed_company_session(client, collection, organisation_type=SignUpOrganisationType.COMPANY, **answers) -> None:
    """A session with the lookup on, for a company found through the register unless said otherwise."""
    enable_session_feature_flag(client, FeatureFlags.ACCESS_GRANT_FUNDING_COMPANIES_HOUSE_LOOKUP)
    if organisation_type == SignUpOrganisationType.COMPANY:
        answers.setdefault("identified_by", OrganisationIdentification.COMPANIES_HOUSE)
    _seed_session(
        client,
        collection,
        _create_organisation_session(
            collection.id, organisation_type=organisation_type, companies_house_lookup=True, **answers
        ),
    )


def _company(company_number="00000001", title="TEST COMPANY LIMITED", address_snippet="1 Test Street, Testtown"):
    return {"company_number": company_number, "title": title, "address_snippet": address_snippet}


def _search_results(items, *, total_results=None, start_index=0) -> CompanySearchResults:
    return CompanySearchResults.model_validate(
        {
            "items": items,
            "total_results": len(items) if total_results is None else total_results,
            "items_per_page": companies_house_service.items_per_page,
            "start_index": start_index,
        },
        context={"max_results": companies_house_service.max_search_results},
    )


@pytest.fixture()
def companies_house(mocker):
    search = mocker.patch.object(
        companies_house_service, "search_companies", return_value=_search_results([_company()])
    )
    get_company = mocker.patch.object(
        companies_house_service,
        "get_company",
        return_value=CompanyProfile(company_number="00000001", company_name="TEST COMPANY LIMITED"),
    )
    return search, get_company


def _name_url(collection, **params):
    return url_for(
        "access_grant_funding.create_organisation_name",
        grant_slug=collection.grant.slug,
        collection_slug=collection.slug,
        **params,
    )


def _unavailable_url(collection, **params):
    return url_for(
        "access_grant_funding.create_organisation_company_search_unavailable",
        grant_slug=collection.grant.slug,
        collection_slug=collection.slug,
        **params,
    )


_REGISTER_FAILURES = [
    pytest.param(CompaniesHouseError("upstream", status_code=500), id="server error"),
    pytest.param(CompaniesHouseError("timeout"), id="timeout"),
    pytest.param(CompaniesHouseDisabledError("disabled"), id="disabled"),
]


def _sign_up_router_url(collection):
    return url_for(
        "access_grant_funding.public_sign_up_router",
        grant_slug=collection.grant.slug,
        collection_slug=collection.slug,
    )


class TestCreateOrganisationType:
    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_renders_the_question(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            _create_organisation_session(sign_up_collection.id),
        )

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.create_organisation_type",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "What is your organisation type?" in get_h1_text(soup)
        assert "Create an organisation" in soup.text

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_without_session_redirects(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(authenticated_no_role_client, sign_up_collection)

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.create_organisation_type",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            )
        )

        assert response.status_code == 302
        assert response.location == _sign_up_router_url(sign_up_collection)

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_with_session_for_another_collection_redirects(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            _create_organisation_session(uuid.uuid4()),
        )

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.create_organisation_type",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            )
        )

        assert response.status_code == 302
        assert response.location == _sign_up_router_url(sign_up_collection)

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_saves_choice_and_continues_to_name(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            _create_organisation_session(sign_up_collection.id),
        )

        response = authenticated_no_role_client.post(
            url_for(
                "access_grant_funding.create_organisation_type",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            ),
            data={"organisation_type": SignUpOrganisationType.CHARITY.value, "submit": "y"},
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.create_organisation_name",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )

        with authenticated_no_role_client.session_transaction() as flask_session:
            assert flask_session["create_organisation"]["organisation_type"] == SignUpOrganisationType.CHARITY.value

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_registered_company_with_the_lookup_enabled_goes_to_the_company_search_page(
        self, authenticated_no_role_client, sign_up_collection
    ):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            _create_organisation_session(sign_up_collection.id, companies_house_lookup=True),
        )

        response = authenticated_no_role_client.post(
            url_for(
                "access_grant_funding.create_organisation_type",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            ),
            data={"organisation_type": SignUpOrganisationType.COMPANY.value, "submit": "y"},
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.create_organisation_company_search",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )

        with authenticated_no_role_client.session_transaction() as flask_session:
            assert flask_session["create_organisation"]["organisation_type"] == SignUpOrganisationType.COMPANY.value

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_registered_company_from_check_your_answers_with_the_lookup_enabled_forgets_the_name(
        self, authenticated_no_role_client, sign_up_collection
    ):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            _create_organisation_session(
                sign_up_collection.id,
                organisation_type=SignUpOrganisationType.OTHER,
                name="Test Organisation",
                external_id="000111222",
                allow_team_members=False,
                companies_house_lookup=True,
            ),
        )

        response = authenticated_no_role_client.post(
            url_for(
                "access_grant_funding.create_organisation_type",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
                source="check-your-answers",
            ),
            data={"organisation_type": SignUpOrganisationType.COMPANY.value, "submit": "y"},
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.create_organisation_company_search",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
            source="check-your-answers",
        )

        with authenticated_no_role_client.session_transaction() as flask_session:
            assert flask_session["create_organisation"]["organisation_type"] == SignUpOrganisationType.COMPANY.value
            assert "name" not in flask_session["create_organisation"]
            assert "external_id" not in flask_session["create_organisation"]
            assert flask_session["create_organisation"]["allow_team_members"] is False

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_another_type_from_check_your_answers_for_a_looked_up_company_asks_for_the_name(
        self, authenticated_no_role_client, sign_up_collection
    ):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            _create_organisation_session(
                sign_up_collection.id,
                organisation_type=SignUpOrganisationType.COMPANY,
                identified_by=OrganisationIdentification.COMPANIES_HOUSE,
                companies_house_lookup=True,
                name="Test Company Ltd",
                external_id="AB123456",
                allow_team_members=False,
            ),
        )

        response = authenticated_no_role_client.post(
            url_for(
                "access_grant_funding.create_organisation_type",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
                source="check-your-answers",
            ),
            data={"organisation_type": SignUpOrganisationType.CHARITY.value, "submit": "y"},
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.create_organisation_name",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
            source="check-your-answers",
        )

        with authenticated_no_role_client.session_transaction() as flask_session:
            assert "name" not in flask_session["create_organisation"]
            assert "external_id" not in flask_session["create_organisation"]

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_a_different_type_drops_a_name_taken_from_the_register(
        self, authenticated_no_role_client, sign_up_collection
    ):
        _seed_company_session(
            authenticated_no_role_client,
            sign_up_collection,
            name="TEST COMPANY LIMITED",
            external_id="00000001",
        )

        response = authenticated_no_role_client.post(
            url_for(
                "access_grant_funding.create_organisation_type",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            ),
            data={"organisation_type": SignUpOrganisationType.CHARITY.value, "submit": "y"},
        )

        assert response.status_code == 302
        with authenticated_no_role_client.session_transaction() as flask_session:
            assert flask_session["create_organisation"]["organisation_type"] == SignUpOrganisationType.CHARITY.value
            assert "name" not in flask_session["create_organisation"]
            assert "external_id" not in flask_session["create_organisation"]

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_registered_company_after_falling_back_continues_to_name(
        self, authenticated_no_role_client, sign_up_collection
    ):
        _seed_company_session(
            authenticated_no_role_client, sign_up_collection, organisation_type=None, companies_house_unavailable=True
        )

        response = authenticated_no_role_client.post(
            url_for(
                "access_grant_funding.create_organisation_type",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            ),
            data={"organisation_type": SignUpOrganisationType.COMPANY.value, "submit": "y"},
        )

        assert response.status_code == 302
        assert response.location == _name_url(sign_up_collection)

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_local_authority_goes_to_the_support_desk_page(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            _create_organisation_session(sign_up_collection.id),
        )

        response = authenticated_no_role_client.post(
            url_for(
                "access_grant_funding.create_organisation_type",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            ),
            data={"organisation_type": SignUpOrganisationType.LOCAL_AUTHORITY.value, "submit": "y"},
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.create_organisation_local_authority",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )

        # the choice is still stored so the support desk page can tell it is the right place to be
        with authenticated_no_role_client.session_transaction() as flask_session:
            assert (
                flask_session["create_organisation"]["organisation_type"]
                == SignUpOrganisationType.LOCAL_AUTHORITY.value
            )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_local_authority_from_check_your_answers_keeps_the_source(
        self, authenticated_no_role_client, sign_up_collection
    ):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            _create_organisation_session(sign_up_collection.id, organisation_type=SignUpOrganisationType.OTHER),
        )

        response = authenticated_no_role_client.post(
            url_for(
                "access_grant_funding.create_organisation_type",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
                source="check-your-answers",
            ),
            data={"organisation_type": SignUpOrganisationType.LOCAL_AUTHORITY.value, "submit": "y"},
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.create_organisation_local_authority",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
            source="check-your-answers",
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_post_from_check_your_answers_returns_there(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            _create_organisation_session(
                sign_up_collection.id,
                organisation_type=SignUpOrganisationType.COMPANY,
                name="Test Company",
                external_id="000111222",
                allow_team_members=False,
            ),
        )

        cya_url = url_for(
            "access_grant_funding.create_organisation_check_your_answers",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )
        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.create_organisation_type",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
                source="check-your-answers",
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        back_link = soup.select_one("a.govuk-back-link")
        assert back_link["href"] == cya_url

        response = authenticated_no_role_client.post(
            url_for(
                "access_grant_funding.create_organisation_type",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
                source="check-your-answers",
            ),
            data={"organisation_type": SignUpOrganisationType.COMPANY.value, "submit": "y"},
        )

        assert response.status_code == 302
        assert response.location == cya_url


class TestCreateOrganisationLocalAuthority:
    def _url(self, collection, **kwargs) -> str:
        return url_for(
            "access_grant_funding.create_organisation_local_authority",
            grant_slug=collection.grant.slug,
            collection_slug=collection.slug,
            **kwargs,
        )

    def _organisation_type_url(self, collection, **kwargs) -> str:
        return url_for(
            "access_grant_funding.create_organisation_type",
            grant_slug=collection.grant.slug,
            collection_slug=collection.slug,
            **kwargs,
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_renders_the_page(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            _create_organisation_session(
                sign_up_collection.id, organisation_type=SignUpOrganisationType.LOCAL_AUTHORITY
            ),
        )

        response = authenticated_no_role_client.get(self._url(sign_up_collection))

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Contact our support desk" in get_h1_text(soup)
        assert "Create an organisation" in soup.text
        assert soup.select_one("a.govuk-back-link")["href"] == self._organisation_type_url(sign_up_collection)

        support_desk_link = soup.find("a", string="support desk (opens in new tab)")
        assert support_desk_link is not None

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_without_session_redirects(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(authenticated_no_role_client, sign_up_collection)

        response = authenticated_no_role_client.get(self._url(sign_up_collection))

        assert response.status_code == 302
        assert response.location == _sign_up_router_url(sign_up_collection)

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_with_another_organisation_type_redirects_back_to_the_type_page(
        self, authenticated_no_role_client, sign_up_collection
    ):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            _create_organisation_session(sign_up_collection.id, organisation_type=SignUpOrganisationType.CHARITY),
        )

        response = authenticated_no_role_client.get(self._url(sign_up_collection))

        assert response.status_code == 302
        assert response.location == self._organisation_type_url(sign_up_collection)

    @pytest.mark.authenticate_as("applicant@no-org.com")
    @patch("app.access_grant_funding.helpers.emit_metric_count")
    def test_get_emits_local_authority_support_shown_metric(
        self, mock_count, authenticated_no_role_client, sign_up_collection
    ):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            _create_organisation_session(
                sign_up_collection.id, organisation_type=SignUpOrganisationType.LOCAL_AUTHORITY
            ),
        )

        response = authenticated_no_role_client.get(self._url(sign_up_collection))

        assert response.status_code == 200
        mock_count.assert_called_once_with(
            MetricEventName.PUBLIC_SIGN_UP_LOCAL_AUTHORITY_SUPPORT_SHOWN,
            grant_recipient=None,
            collection=sign_up_collection,
            custom_attributes={MetricAttributeName.SUBMISSION_MODE: str(SubmissionModeEnum.LIVE)},
        )


class TestCreateOrganisationCompanySearch:
    def _url(self, collection, **params) -> str:
        return url_for(
            "access_grant_funding.create_organisation_company_search",
            grant_slug=collection.grant.slug,
            collection_slug=collection.slug,
            **params,
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_without_the_feature_flag_is_not_found(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            _create_organisation_session(sign_up_collection.id, organisation_type=SignUpOrganisationType.COMPANY),
        )

        response = authenticated_no_role_client.get(self._url(sign_up_collection))

        assert response.status_code == 404

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_renders_the_search_form(self, authenticated_no_role_client, sign_up_collection):
        _seed_company_session(authenticated_no_role_client, sign_up_collection)

        response = authenticated_no_role_client.get(self._url(sign_up_collection))

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Search Companies House register"

        assert page_has_button(soup, "Search")
        back_link = page_has_link(soup, "Back")
        assert back_link is not None
        assert back_link.attrs["href"] == url_for(
            "access_grant_funding.create_organisation_type",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_without_session_redirects(self, authenticated_no_role_client, sign_up_collection):
        enable_session_feature_flag(
            authenticated_no_role_client, FeatureFlags.ACCESS_GRANT_FUNDING_COMPANIES_HOUSE_LOOKUP
        )
        _seed_session(authenticated_no_role_client, sign_up_collection)

        response = authenticated_no_role_client.get(self._url(sign_up_collection))

        assert response.status_code == 302
        assert response.location == _sign_up_router_url(sign_up_collection)

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_with_another_organisation_type_redirects_back_to_the_type_page(
        self, authenticated_no_role_client, sign_up_collection
    ):
        _seed_company_session(
            authenticated_no_role_client, sign_up_collection, organisation_type=SignUpOrganisationType.CHARITY
        )

        response = authenticated_no_role_client.get(self._url(sign_up_collection))

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.create_organisation_type",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_with_an_empty_search_term_shows_an_error(
        self, authenticated_no_role_client, sign_up_collection, companies_house
    ):
        _seed_company_session(authenticated_no_role_client, sign_up_collection)

        response = authenticated_no_role_client.get(self._url(sign_up_collection, q=""))

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "Enter a company name or number")
        assert "search result" not in soup.text
        companies_house[0].assert_not_called()

    @pytest.mark.authenticate_as("applicant@no-org.com")
    @pytest.mark.parametrize(
        "search_term, expected_error",
        [
            pytest.param("ab", "Company name or number must be 3 characters or more", id="too short"),
            pytest.param("a" * 161, "Company name or number must be 160 characters or fewer", id="too long"),
        ],
    )
    def test_get_with_a_search_term_outside_the_length_limits_shows_the_error_instead_of_results(
        self, authenticated_no_role_client, sign_up_collection, companies_house, search_term, expected_error
    ):
        _seed_company_session(authenticated_no_role_client, sign_up_collection)

        response = authenticated_no_role_client.get(self._url(sign_up_collection, q=search_term))

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_input_value(soup, "q") == search_term
        assert page_has_error(soup, expected_error)
        assert "search result" not in soup.text
        companies_house[0].assert_not_called()

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_renders_the_results_for_the_search_term_in_the_url(
        self, authenticated_no_role_client, sign_up_collection, companies_house
    ):
        _seed_company_session(authenticated_no_role_client, sign_up_collection)
        companies_house[0].return_value = _search_results(
            [_company(), _company("00000002", "OTHER TEST COMPANY LTD", "2 Test Street, Testtown")]
        )

        response = authenticated_no_role_client.get(self._url(sign_up_collection, q="Test Company"))

        assert response.status_code == 200
        companies_house[0].assert_called_once_with("Test Company", page=1)

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Search results"
        assert get_input_value(soup, "q") == "Test Company"
        assert "2 search results" in soup.text

        row = get_table_row_by_first_column_value(soup, "TEST COMPANY LIMITED")
        assert row is not None
        assert "00000001" in row.text
        assert "1 Test Street, Testtown" in row.text

        select_button = page_has_button(row, "Select")
        assert select_button is not None
        assert select_button.attrs["name"] == "company_number"
        assert select_button.attrs["value"] == "00000001"

        other_row = get_table_row_by_first_column_value(soup, "OTHER TEST COMPANY LTD")
        assert other_row is not None
        assert page_has_button(other_row, "Select").attrs["value"] == "00000002"

        back_link = page_has_link(soup, "Back")
        assert back_link is not None
        assert back_link.attrs["href"] == self._url(sign_up_collection)

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_paginates_the_results(self, authenticated_no_role_client, sign_up_collection, companies_house):
        _seed_company_session(authenticated_no_role_client, sign_up_collection)
        companies_house[0].return_value = _search_results([_company()] * 20, total_results=45, start_index=20)

        response = authenticated_no_role_client.get(self._url(sign_up_collection, q="Test Company", page=2))

        assert response.status_code == 200
        companies_house[0].assert_called_once_with("Test Company", page=2)
        soup = BeautifulSoup(response.data, "html.parser")
        assert "45 search results" in soup.text

        previous_link = page_has_link(soup, "Previous")
        next_link = page_has_link(soup, "Next")
        assert previous_link is not None
        assert next_link is not None
        assert previous_link.attrs["href"] == self._url(sign_up_collection, q="Test Company", page=1)
        assert next_link.attrs["href"] == self._url(sign_up_collection, q="Test Company", page=3)

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_caps_the_number_of_results_shown(
        self, authenticated_no_role_client, sign_up_collection, companies_house
    ):
        _seed_company_session(authenticated_no_role_client, sign_up_collection)
        companies_house[0].return_value = _search_results([_company()] * 20, total_results=5000)

        response = authenticated_no_role_client.get(self._url(sign_up_collection, q="Test Company"))

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "1,000 search results" in soup.text
        assert "Only the first 1,000 results can be shown" in soup.text

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_with_no_matches_shows_no_results(
        self, authenticated_no_role_client, sign_up_collection, companies_house
    ):
        _seed_company_session(authenticated_no_role_client, sign_up_collection)
        companies_house[0].return_value = _search_results([])

        response = authenticated_no_role_client.get(self._url(sign_up_collection, q="Test Company"))

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "0 search results" in soup.text
        assert page_has_button(soup, "Select") is None

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_past_the_last_page_redirects_to_the_last_page(
        self, authenticated_no_role_client, sign_up_collection, companies_house
    ):
        _seed_company_session(authenticated_no_role_client, sign_up_collection)
        companies_house[0].return_value = _search_results([], total_results=100, start_index=580)

        response = authenticated_no_role_client.get(self._url(sign_up_collection, q="Test Company", page=30))

        assert response.status_code == 302
        assert response.location == self._url(sign_up_collection, q="Test Company", page=5)

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_past_the_register_range_redirects_to_the_first_page(
        self, authenticated_no_role_client, sign_up_collection, companies_house
    ):
        _seed_company_session(authenticated_no_role_client, sign_up_collection)
        companies_house[0].side_effect = CompaniesHouseNotFoundError("not_found", status_code=416)

        response = authenticated_no_role_client.get(self._url(sign_up_collection, q="Test Company", page=50))

        assert response.status_code == 302
        assert response.location == self._url(sign_up_collection, q="Test Company")

    @pytest.mark.authenticate_as("applicant@no-org.com")
    @pytest.mark.parametrize("failure", _REGISTER_FAILURES)
    def test_get_when_the_register_is_unavailable_asks_whether_to_add_the_organisation_manually(
        self, authenticated_no_role_client, sign_up_collection, companies_house, mocker, failure
    ):
        capture_exception = mocker.patch(
            "app.access_grant_funding.routes.create_organisation.sentry_sdk.capture_exception"
        )
        _seed_company_session(authenticated_no_role_client, sign_up_collection)
        companies_house[0].side_effect = failure

        response = authenticated_no_role_client.get(self._url(sign_up_collection, q="Test Company"))

        assert response.status_code == 302
        assert response.location == _unavailable_url(sign_up_collection)
        capture_exception.assert_called_once_with(failure)
        with authenticated_no_role_client.session_transaction() as flask_session:
            assert flask_session["create_organisation"]["companies_house_unavailable"] is False
            assert (
                flask_session["create_organisation"]["identified_by"]
                == OrganisationIdentification.COMPANIES_HOUSE.value
            )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_when_the_register_is_unavailable_from_check_your_answers_keeps_the_way_back(
        self, authenticated_no_role_client, sign_up_collection, companies_house
    ):
        _seed_company_session(authenticated_no_role_client, sign_up_collection)
        companies_house[0].side_effect = CompaniesHouseError("upstream", status_code=500)

        response = authenticated_no_role_client.get(
            self._url(sign_up_collection, q="Test Company", source="check-your-answers")
        )

        assert response.status_code == 302
        assert response.location == _unavailable_url(sign_up_collection, source="check-your-answers")

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_after_falling_back_redirects_to_the_name_page(
        self, authenticated_no_role_client, sign_up_collection, companies_house
    ):
        _seed_company_session(
            authenticated_no_role_client,
            sign_up_collection,
            identified_by=OrganisationIdentification.MANUAL,
            companies_house_unavailable=True,
        )

        response = authenticated_no_role_client.get(self._url(sign_up_collection, q="Test Company"))

        assert response.status_code == 302
        assert response.location == _name_url(sign_up_collection)
        companies_house[0].assert_not_called()

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_stores_the_company_and_continues_to_the_team_members_step(
        self, authenticated_no_role_client, sign_up_collection, companies_house
    ):
        _seed_company_session(authenticated_no_role_client, sign_up_collection)

        response = authenticated_no_role_client.post(
            self._url(sign_up_collection, q="Test Company"), data={"company_number": "00000001"}
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.create_organisation_allow_team_members",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )

        companies_house[1].assert_called_once_with("00000001")

        with authenticated_no_role_client.session_transaction() as flask_session:
            assert flask_session["create_organisation"]["name"] == "TEST COMPANY LIMITED"
            assert flask_session["create_organisation"]["external_id"] == "00000001"

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_without_a_company_number_shows_the_results_again(
        self, authenticated_no_role_client, sign_up_collection, companies_house
    ):
        _seed_company_session(authenticated_no_role_client, sign_up_collection)

        response = authenticated_no_role_client.post(self._url(sign_up_collection, q="Test Company"), data={})

        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_button(soup, "Select")

        companies_house[1].assert_not_called()

        with authenticated_no_role_client.session_transaction() as flask_session:
            assert "external_id" not in flask_session["create_organisation"]

    @pytest.mark.authenticate_as("applicant@gmail.com")
    def test_post_can_skip_optional_steps_that_do_not_apply(
        self, authenticated_no_role_client, sign_up_collection, companies_house
    ):
        _seed_company_session(
            authenticated_no_role_client, sign_up_collection, can_share_email_domain=False, needs_user_name=False
        )

        response = authenticated_no_role_client.post(
            self._url(sign_up_collection, q="Test Company"), data={"company_number": "00000001"}
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.create_organisation_check_your_answers",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_from_check_your_answers_returns_there(
        self, authenticated_no_role_client, sign_up_collection, companies_house
    ):
        _seed_company_session(
            authenticated_no_role_client,
            sign_up_collection,
            name="Acme Ltd",
            external_id="000111222",
            allow_team_members=False,
        )

        response = authenticated_no_role_client.post(
            self._url(sign_up_collection, q="Test Company", source="check-your-answers"),
            data={"company_number": "00000001"},
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.create_organisation_check_your_answers",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )
        with authenticated_no_role_client.session_transaction() as flask_session:
            assert flask_session["create_organisation"]["name"] == "TEST COMPANY LIMITED"
            assert flask_session["create_organisation"]["external_id"] == "00000001"

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_a_company_already_registered_by_number_goes_to_the_already_exists_page(
        self, authenticated_no_role_client, sign_up_collection, companies_house, factories, db_session
    ):
        factories.organisation.create(type=OrganisationType.COMPANY, external_id="CH-00000001", name="Other Test Org")
        db_session.commit()
        _seed_company_session(authenticated_no_role_client, sign_up_collection)

        response = authenticated_no_role_client.post(
            self._url(sign_up_collection, q="Test Company"), data={"company_number": "00000001"}
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.create_organisation_already_exists",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_a_company_already_registered_by_name_goes_to_the_already_exists_page(
        self, authenticated_no_role_client, sign_up_collection, companies_house, factories, db_session
    ):
        factories.organisation.create(name="TEST COMPANY LIMITED")
        db_session.commit()
        _seed_company_session(authenticated_no_role_client, sign_up_collection)

        response = authenticated_no_role_client.post(
            self._url(sign_up_collection, q="Test Company"), data={"company_number": "00000001"}
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.create_organisation_already_exists",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_an_unknown_company_asks_whether_to_add_the_organisation_manually(
        self, authenticated_no_role_client, sign_up_collection, companies_house, mocker
    ):
        capture_exception = mocker.patch(
            "app.access_grant_funding.routes.create_organisation.sentry_sdk.capture_exception"
        )
        _seed_company_session(authenticated_no_role_client, sign_up_collection)
        companies_house[1].side_effect = CompaniesHouseNotFoundError("not_found", status_code=404)

        response = authenticated_no_role_client.post(
            self._url(sign_up_collection, q="Test Company"), data={"company_number": "00000001"}
        )

        assert response.status_code == 302
        assert response.location == _unavailable_url(sign_up_collection)
        capture_exception.assert_called_once_with(companies_house[1].side_effect)
        with authenticated_no_role_client.session_transaction() as flask_session:
            assert flask_session["create_organisation"]["companies_house_unavailable"] is False
            assert "name" not in flask_session["create_organisation"]
            assert "external_id" not in flask_session["create_organisation"]

    @pytest.mark.authenticate_as("applicant@no-org.com")
    @pytest.mark.parametrize("failure", _REGISTER_FAILURES)
    def test_post_when_the_register_is_unavailable_asks_whether_to_add_the_organisation_manually(
        self, authenticated_no_role_client, sign_up_collection, companies_house, mocker, failure
    ):
        capture_exception = mocker.patch(
            "app.access_grant_funding.routes.create_organisation.sentry_sdk.capture_exception"
        )
        _seed_company_session(authenticated_no_role_client, sign_up_collection)
        companies_house[1].side_effect = failure

        response = authenticated_no_role_client.post(
            self._url(sign_up_collection, q="Test Company"), data={"company_number": "00000001"}
        )

        assert response.status_code == 302
        assert response.location == _unavailable_url(sign_up_collection)
        capture_exception.assert_called_once_with(failure)
        with authenticated_no_role_client.session_transaction() as flask_session:
            assert flask_session["create_organisation"]["companies_house_unavailable"] is False
            assert (
                flask_session["create_organisation"]["identified_by"]
                == OrganisationIdentification.COMPANIES_HOUSE.value
            )
            assert "name" not in flask_session["create_organisation"]
            assert "external_id" not in flask_session["create_organisation"]

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_with_another_organisation_type_redirects_back_to_the_type_page(
        self, authenticated_no_role_client, sign_up_collection, companies_house
    ):
        _seed_company_session(
            authenticated_no_role_client, sign_up_collection, organisation_type=SignUpOrganisationType.CHARITY
        )

        response = authenticated_no_role_client.post(
            self._url(sign_up_collection, q="Test Company"), data={"company_number": "00000001"}
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.create_organisation_type",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )
        companies_house[1].assert_not_called()

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_results_offer_to_add_the_organisation_manually(
        self, app, authenticated_no_role_client, sign_up_collection, companies_house
    ):
        _seed_company_session(authenticated_no_role_client, sign_up_collection)

        response = authenticated_no_role_client.get(self._url(sign_up_collection, q="Test Company"))

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Organisation not listed" in soup.text
        assert get_input_value(soup, "submit") == "add your organisation manually"
        support_desk = page_has_link(soup, "support desk (opens in new tab)")
        assert support_desk is not None
        assert support_desk.attrs["href"] == app.config["ACCESS_SERVICE_DESK_URL"]

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_the_search_form_does_not_offer_manual_entry_before_searching(
        self, authenticated_no_role_client, sign_up_collection
    ):
        _seed_company_session(authenticated_no_role_client, sign_up_collection)

        response = authenticated_no_role_client.get(self._url(sign_up_collection))

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Organisation not listed" not in soup.text
        assert get_input_value(soup, "submit") is None

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_to_add_the_organisation_manually_continues_to_the_name_page(
        self, authenticated_no_role_client, sign_up_collection, companies_house
    ):
        _seed_company_session(authenticated_no_role_client, sign_up_collection)

        response = authenticated_no_role_client.post(
            self._url(sign_up_collection, q="Test Company"),
            data={"mode": "manual", "submit": "add your organisation manually"},
        )

        assert response.status_code == 302
        assert response.location == _name_url(sign_up_collection)
        companies_house[1].assert_not_called()
        with authenticated_no_role_client.session_transaction() as flask_session:
            assert flask_session["create_organisation"]["identified_by"] == OrganisationIdentification.MANUAL.value
            assert flask_session["create_organisation"]["companies_house_unavailable"] is False
            assert "name" not in flask_session["create_organisation"]
            assert "external_id" not in flask_session["create_organisation"]

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_to_add_the_organisation_manually_from_check_your_answers_asks_for_the_name_on_the_way_back(
        self, authenticated_no_role_client, sign_up_collection, companies_house
    ):
        _seed_company_session(
            authenticated_no_role_client,
            sign_up_collection,
            name="TEST COMPANY LIMITED",
            external_id="00000001",
            allow_team_members=False,
        )

        response = authenticated_no_role_client.post(
            self._url(sign_up_collection, q="Test Company", source="check-your-answers"),
            data={"mode": "manual", "submit": "add your organisation manually"},
        )

        assert response.status_code == 302
        assert response.location == _name_url(sign_up_collection, source="check-your-answers")
        with authenticated_no_role_client.session_transaction() as flask_session:
            assert "name" not in flask_session["create_organisation"]
            assert "external_id" not in flask_session["create_organisation"]


class TestCreateOrganisationCompanySearchUnavailable:
    def _url(self, collection, **params) -> str:
        return _unavailable_url(collection, **params)

    def _journey_url(self, collection, endpoint, **params) -> str:
        return url_for(
            f"access_grant_funding.{endpoint}",
            grant_slug=collection.grant.slug,
            collection_slug=collection.slug,
            **params,
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_without_the_feature_flag_is_not_found(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            _create_organisation_session(sign_up_collection.id, organisation_type=SignUpOrganisationType.COMPANY),
        )

        response = authenticated_no_role_client.get(self._url(sign_up_collection))

        assert response.status_code == 404

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_without_session_redirects(self, authenticated_no_role_client, sign_up_collection):
        enable_session_feature_flag(
            authenticated_no_role_client, FeatureFlags.ACCESS_GRANT_FUNDING_COMPANIES_HOUSE_LOOKUP
        )
        _seed_session(authenticated_no_role_client, sign_up_collection)

        response = authenticated_no_role_client.get(self._url(sign_up_collection))

        assert response.status_code == 302
        assert response.location == _sign_up_router_url(sign_up_collection)

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_renders_the_question(self, authenticated_no_role_client, sign_up_collection):
        _seed_company_session(authenticated_no_role_client, sign_up_collection)

        response = authenticated_no_role_client.get(self._url(sign_up_collection))

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Companies House register search not available"
        assert "Do you want to add your organisation manually?" in soup.text
        assert "We'll ask for the name of your organisation" in soup.text
        assert "No, I'll try again later" in soup.text
        assert page_has_button(soup, "Continue")
        back_link = page_has_link(soup, "Back")
        assert back_link is not None
        assert back_link.attrs["href"] == self._journey_url(sign_up_collection, "create_organisation_company_search")

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_once_adding_manually_redirects_to_the_name_page(
        self, authenticated_no_role_client, sign_up_collection
    ):
        _seed_company_session(
            authenticated_no_role_client,
            sign_up_collection,
            identified_by=OrganisationIdentification.MANUAL,
            companies_house_unavailable=True,
        )

        response = authenticated_no_role_client.get(self._url(sign_up_collection))

        assert response.status_code == 302
        assert response.location == _name_url(sign_up_collection)

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_with_another_organisation_type_redirects_back_to_the_type_page(
        self, authenticated_no_role_client, sign_up_collection
    ):
        _seed_company_session(
            authenticated_no_role_client, sign_up_collection, organisation_type=SignUpOrganisationType.CHARITY
        )

        response = authenticated_no_role_client.get(self._url(sign_up_collection))

        assert response.status_code == 302
        assert response.location == self._journey_url(sign_up_collection, "create_organisation_type")

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_without_an_answer_shows_an_error(self, authenticated_no_role_client, sign_up_collection):
        _seed_company_session(authenticated_no_role_client, sign_up_collection)

        response = authenticated_no_role_client.post(self._url(sign_up_collection), data={"submit": "y"})

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "Select yes if you want to add your organisation manually")

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_yes_names_the_company_by_hand_from_here_on(self, authenticated_no_role_client, sign_up_collection):
        _seed_company_session(authenticated_no_role_client, sign_up_collection)

        response = authenticated_no_role_client.post(
            self._url(sign_up_collection), data={"add_manually": True, "submit": "y"}
        )

        assert response.status_code == 302
        assert response.location == _name_url(sign_up_collection)
        with authenticated_no_role_client.session_transaction() as flask_session:
            assert flask_session["create_organisation"]["identified_by"] == OrganisationIdentification.MANUAL.value
            assert flask_session["create_organisation"]["companies_house_unavailable"] is True
            assert "name" not in flask_session["create_organisation"]
            assert "external_id" not in flask_session["create_organisation"]

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_yes_from_check_your_answers_asks_for_the_name_on_the_way_back(
        self, authenticated_no_role_client, sign_up_collection
    ):
        _seed_company_session(
            authenticated_no_role_client,
            sign_up_collection,
            name="TEST COMPANY LIMITED",
            external_id="00000001",
            allow_team_members=False,
        )

        response = authenticated_no_role_client.post(
            self._url(sign_up_collection, source="check-your-answers"), data={"add_manually": True, "submit": "y"}
        )

        assert response.status_code == 302
        assert response.location == self._journey_url(
            sign_up_collection, "create_organisation_name", source="check-your-answers"
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_no_returns_to_the_start_page_and_keeps_the_sign_up_as_it_was(
        self, authenticated_no_role_client, sign_up_collection
    ):
        _seed_company_session(authenticated_no_role_client, sign_up_collection)
        with authenticated_no_role_client.session_transaction() as flask_session:
            session_before = dict(flask_session["create_organisation"])

        response = authenticated_no_role_client.post(
            self._url(sign_up_collection), data={"add_manually": "False", "submit": "y"}
        )

        assert response.status_code == 302
        assert response.location == self._journey_url(sign_up_collection, "public_sign_up_start_page")
        with authenticated_no_role_client.session_transaction() as flask_session:
            assert flask_session["create_organisation"] == session_before


class TestCreateOrganisationName:
    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_renders_the_question(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            _create_organisation_session(sign_up_collection.id, organisation_type=SignUpOrganisationType.OTHER),
        )

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.create_organisation_name",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "What is the name of your organisation?" in get_h1_text(soup)

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_without_session_redirects(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(authenticated_no_role_client, sign_up_collection)

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.create_organisation_name",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            )
        )

        assert response.status_code == 302
        assert response.location == _sign_up_router_url(sign_up_collection)

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_with_a_local_authority_session_redirects_back_to_the_type_page(
        self, authenticated_no_role_client, sign_up_collection
    ):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            _create_organisation_session(
                sign_up_collection.id, organisation_type=SignUpOrganisationType.LOCAL_AUTHORITY
            ),
        )

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.create_organisation_name",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            )
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.create_organisation_type",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_with_a_looked_up_company_session_redirects_to_the_company_search(
        self, authenticated_no_role_client, sign_up_collection
    ):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            _create_organisation_session(
                sign_up_collection.id,
                organisation_type=SignUpOrganisationType.COMPANY,
                identified_by=OrganisationIdentification.COMPANIES_HOUSE,
                companies_house_lookup=True,
            ),
        )

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.create_organisation_name",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            )
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.create_organisation_company_search",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_with_a_looked_up_company_session_does_not_take_a_name(
        self, authenticated_no_role_client, sign_up_collection
    ):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            _create_organisation_session(
                sign_up_collection.id,
                organisation_type=SignUpOrganisationType.COMPANY,
                identified_by=OrganisationIdentification.COMPANIES_HOUSE,
                companies_house_lookup=True,
            ),
        )

        response = authenticated_no_role_client.post(
            url_for(
                "access_grant_funding.create_organisation_name",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            ),
            data={"name": "Test Company Ltd", "submit": "y"},
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.create_organisation_company_search",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )

        with authenticated_no_role_client.session_transaction() as flask_session:
            assert "name" not in flask_session["create_organisation"]
            assert "external_id" not in flask_session["create_organisation"]

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_persists_name_and_generates_external_id(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            _create_organisation_session(sign_up_collection.id, organisation_type=SignUpOrganisationType.OTHER),
        )

        response = authenticated_no_role_client.post(
            url_for(
                "access_grant_funding.create_organisation_name",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            ),
            data={"name": "  Acme Ltd  ", "submit": "y"},
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.create_organisation_allow_team_members",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )

        with authenticated_no_role_client.session_transaction() as flask_session:
            stored = flask_session["create_organisation"]
        assert stored["name"] == "Acme Ltd"
        assert len(stored["external_id"]) == 9

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_an_existing_organisation_name_goes_to_the_already_exists_page(
        self, authenticated_no_role_client, sign_up_collection, factories
    ):
        factories.organisation.create(name="Acme Ltd")
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            _create_organisation_session(sign_up_collection.id, organisation_type=SignUpOrganisationType.OTHER),
        )

        response = authenticated_no_role_client.post(
            url_for(
                "access_grant_funding.create_organisation_name",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            ),
            data={"name": "acme ltd", "submit": "y"},
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.create_organisation_already_exists",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )

        # the name is still stored so the page can name the organisation and the back link pre-fills what they typed
        with authenticated_no_role_client.session_transaction() as flask_session:
            assert flask_session["create_organisation"]["name"] == "acme ltd"

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_an_existing_organisation_name_from_check_your_answers_keeps_the_source(
        self, authenticated_no_role_client, sign_up_collection, factories
    ):
        factories.organisation.create(name="Acme Ltd")
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            _create_organisation_session(
                sign_up_collection.id,
                organisation_type=SignUpOrganisationType.OTHER,
                name="Some other name",
                external_id="000111222",
            ),
        )

        response = authenticated_no_role_client.post(
            url_for(
                "access_grant_funding.create_organisation_name",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
                source="check-your-answers",
            ),
            data={"name": "Acme Ltd", "submit": "y"},
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.create_organisation_already_exists",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
            source="check-your-answers",
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_a_name_only_taken_in_test_mode_continues(
        self, authenticated_no_role_client, sign_up_collection, factories
    ):
        factories.organisation.create(name="Acme Ltd", mode=OrganisationModeEnum.TEST)
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            _create_organisation_session(sign_up_collection.id, organisation_type=SignUpOrganisationType.OTHER),
        )

        response = authenticated_no_role_client.post(
            url_for(
                "access_grant_funding.create_organisation_name",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            ),
            data={"name": "Acme Ltd", "submit": "y"},
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.create_organisation_allow_team_members",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )

    def test_post_matches_the_test_suffixed_name_for_a_deliver_user_testing_access(
        self, anonymous_client, sign_up_collection, factories, user, db_session
    ):
        # ` (test)` should reliably be matched
        factories.organisation.create(name="Mirrored Org (test)", mode=OrganisationModeEnum.TEST)
        factories.user_role.create(
            user=user,
            organisation=sign_up_collection.grant.organisation,
            grant=sign_up_collection.grant,
            permissions=[RoleEnum.MEMBER],
        )

        # logging in as a deliver user means the session will all be in the test context
        login_user(user)
        with anonymous_client.session_transaction() as flask_session:
            flask_session["auth"] = AuthMethodEnum.SSO
        db_session.commit()

        _seed_session(
            anonymous_client,
            sign_up_collection,
            _create_organisation_session(sign_up_collection.id, organisation_type=SignUpOrganisationType.OTHER),
        )

        response = anonymous_client.post(
            url_for(
                "access_grant_funding.create_organisation_name",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            ),
            data={"name": "Mirrored Org", "submit": "y"},
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.create_organisation_already_exists",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_post_from_check_your_answers_returns_there(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            _create_organisation_session(
                sign_up_collection.id,
                organisation_type=SignUpOrganisationType.OTHER,
                name="Acme Ltd",
                external_id="000111222",
                allow_team_members=False,
            ),
        )

        cya_url = url_for(
            "access_grant_funding.create_organisation_check_your_answers",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )

        get_response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.create_organisation_name",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
                source="check-your-answers",
            )
        )
        soup = BeautifulSoup(get_response.data, "html.parser")
        assert soup.select_one("a.govuk-back-link")["href"] == cya_url

        post_response = authenticated_no_role_client.post(
            url_for(
                "access_grant_funding.create_organisation_name",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
                source="check-your-answers",
            ),
            data={"name": "Acme Ltd", "submit": "y"},
        )
        assert post_response.status_code == 302
        assert post_response.location == cya_url


class TestCreateOrganisationAlreadyExists:
    @pytest.fixture()
    def duplicate_org_session(self, sign_up_collection, factories):
        factories.organisation.create(name="Acme Ltd")
        return _create_organisation_session(
            sign_up_collection.id,
            organisation_type=SignUpOrganisationType.OTHER,
            name="Acme Ltd",
            external_id="000111222",
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_renders_the_page(self, authenticated_no_role_client, sign_up_collection, duplicate_org_session):
        _seed_session(authenticated_no_role_client, sign_up_collection, duplicate_org_session)

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.create_organisation_already_exists",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Your organisation already exists" in get_h1_text(soup)
        assert "Acme Ltd is already an existing organisation on Access grant funding." in soup.text

        assert soup.select_one("a.govuk-back-link")["href"] == url_for(
            "access_grant_funding.create_organisation_name",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_from_check_your_answers_back_link_keeps_the_source(
        self, authenticated_no_role_client, sign_up_collection, duplicate_org_session
    ):
        _seed_session(authenticated_no_role_client, sign_up_collection, duplicate_org_session)

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.create_organisation_already_exists",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
                source="check-your-answers",
            )
        )

        soup = BeautifulSoup(response.data, "html.parser")
        assert soup.select_one("a.govuk-back-link")["href"] == url_for(
            "access_grant_funding.create_organisation_name",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
            source="check-your-answers",
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_without_session_redirects(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(authenticated_no_role_client, sign_up_collection)

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.create_organisation_already_exists",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            )
        )

        assert response.status_code == 302
        assert response.location == _sign_up_router_url(sign_up_collection)

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_for_a_company_from_the_register_links_back_to_the_search(
        self, authenticated_no_role_client, sign_up_collection, factories, db_session
    ):
        factories.organisation.create(type=OrganisationType.COMPANY, external_id="CH-00000001", name="Other Test Org")
        db_session.commit()
        _seed_company_session(
            authenticated_no_role_client,
            sign_up_collection,
            name="TEST COMPANY LIMITED",
            external_id="00000001",
        )

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.create_organisation_already_exists",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "TEST COMPANY LIMITED is already an existing organisation" in soup.text
        back_link = page_has_link(soup, "Back")
        assert back_link is not None
        assert back_link.attrs["href"] == url_for(
            "access_grant_funding.create_organisation_company_search",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_without_a_name_in_the_session_redirects(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            _create_organisation_session(sign_up_collection.id, organisation_type=SignUpOrganisationType.OTHER),
        )

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.create_organisation_already_exists",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            )
        )

        assert response.status_code == 302
        assert response.location == _sign_up_router_url(sign_up_collection)

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_with_a_name_that_is_not_taken_redirects_back_to_the_name_page(
        self, authenticated_no_role_client, sign_up_collection
    ):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            _create_organisation_session(
                sign_up_collection.id,
                organisation_type=SignUpOrganisationType.OTHER,
                name="Nobody Else Ltd",
                external_id="000111222",
            ),
        )

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.create_organisation_already_exists",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            )
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.create_organisation_name",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )


class TestCreateOrganisationAllowTeamMembers:
    def _org_session(self, collection, **kwargs) -> CreateOrganisationSession:
        return _create_organisation_session(
            collection.id,
            organisation_type=SignUpOrganisationType.OTHER,
            name="Acme Ltd",
            external_id="000111222",
            **kwargs,
        )

    def _url(self, collection, **kwargs) -> str:
        return url_for(
            "access_grant_funding.create_organisation_allow_team_members",
            grant_slug=collection.grant.slug,
            collection_slug=collection.slug,
            **kwargs,
        )

    def _name_url(self, collection) -> str:
        return url_for(
            "access_grant_funding.create_organisation_name",
            grant_slug=collection.grant.slug,
            collection_slug=collection.slug,
        )

    def _user_name_url(self, collection) -> str:
        return url_for(
            "access_grant_funding.create_organisation_user_name",
            grant_slug=collection.grant.slug,
            collection_slug=collection.slug,
        )

    def _cya_url(self, collection) -> str:
        return url_for(
            "access_grant_funding.create_organisation_check_your_answers",
            grant_slug=collection.grant.slug,
            collection_slug=collection.slug,
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_renders_the_question(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(authenticated_no_role_client, sign_up_collection, self._org_session(sign_up_collection))

        response = authenticated_no_role_client.get(self._url(sign_up_collection))

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Do you want to allow team members to apply as Acme Ltd in the future?" in get_h1_text(soup)
        assert "Create an organisation" in soup.text
        assert (
            "Anyone with a @no-org.com email will be able to apply for future grants on behalf of Acme Ltd" in soup.text
        )

        assert soup.select_one("a.govuk-back-link")["href"] == self._name_url(sign_up_collection)

    @pytest.mark.authenticate_as("applicant@gmail.com")
    def test_get_with_both_optional_steps_inapplicable_skips_to_check_your_answers(
        self, authenticated_no_role_client, sign_up_collection
    ):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            self._org_session(sign_up_collection, can_share_email_domain=False),
        )

        response = authenticated_no_role_client.get(self._url(sign_up_collection))

        assert response.status_code == 302
        assert response.location == self._cya_url(sign_up_collection)

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_without_session_redirects(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(authenticated_no_role_client, sign_up_collection)

        response = authenticated_no_role_client.get(self._url(sign_up_collection))

        assert response.status_code == 302
        assert response.location == _sign_up_router_url(sign_up_collection)

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_without_a_name_in_the_session_redirects(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            _create_organisation_session(sign_up_collection.id, organisation_type=SignUpOrganisationType.OTHER),
        )

        response = authenticated_no_role_client.get(self._url(sign_up_collection))

        assert response.status_code == 302
        assert response.location == _sign_up_router_url(sign_up_collection)

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_stores_the_answer_and_continues_to_the_full_name_step(
        self, authenticated_no_role_client, sign_up_collection
    ):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            self._org_session(sign_up_collection, needs_user_name=True),
        )

        response = authenticated_no_role_client.post(
            self._url(sign_up_collection), data={"allow_team_members": True, "submit": "y"}
        )

        assert response.status_code == 302
        assert response.location == self._user_name_url(sign_up_collection)

        with authenticated_no_role_client.session_transaction() as flask_session:
            assert flask_session["create_organisation"]["allow_team_members"] is True

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_source_round_trip_back_to_check_your_answers(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            self._org_session(sign_up_collection, allow_team_members=True),
        )

        get_response = authenticated_no_role_client.get(self._url(sign_up_collection, source="check-your-answers"))
        soup = BeautifulSoup(get_response.data, "html.parser")
        assert soup.select_one("a.govuk-back-link")["href"] == self._cya_url(sign_up_collection)
        assert soup.select_one("input[name=allow_team_members][checked]")["value"] == "True"

        post_response = authenticated_no_role_client.post(
            self._url(sign_up_collection, source="check-your-answers"),
            data={"allow_team_members": "False", "submit": "y"},
        )
        assert post_response.status_code == 302
        assert post_response.location == self._cya_url(sign_up_collection)


class TestCreateOrganisationUserName:
    # this step is only in the journey for users we hold no name for
    def _org_session(self, collection, *, needs_user_name: bool = True, **kwargs) -> CreateOrganisationSession:
        return _create_organisation_session(
            collection.id,
            needs_user_name=needs_user_name,
            organisation_type=SignUpOrganisationType.OTHER,
            name="Acme Ltd",
            external_id="000111222",
            allow_team_members=False,
            **kwargs,
        )

    def _url(self, collection, **kwargs) -> str:
        return url_for(
            "access_grant_funding.create_organisation_user_name",
            grant_slug=collection.grant.slug,
            collection_slug=collection.slug,
            **kwargs,
        )

    def _cya_url(self, collection) -> str:
        return url_for(
            "access_grant_funding.create_organisation_check_your_answers",
            grant_slug=collection.grant.slug,
            collection_slug=collection.slug,
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_renders_the_question(self, authenticated_no_role_client, sign_up_collection, db_session):
        authenticated_no_role_client.user.name = None
        db_session.commit()

        _seed_session(authenticated_no_role_client, sign_up_collection, self._org_session(sign_up_collection))

        response = authenticated_no_role_client.get(self._url(sign_up_collection))

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "What is your full name?" in get_h1_text(soup)
        assert "Create an organisation" in soup.text
        assert soup.select_one("a.govuk-back-link")["href"] == url_for(
            "access_grant_funding.create_organisation_allow_team_members",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_prefills_a_name_already_in_the_session(
        self, authenticated_no_role_client, sign_up_collection, db_session
    ):
        authenticated_no_role_client.user.name = None
        db_session.commit()

        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            self._org_session(sign_up_collection, user_name="Test applicant"),
        )

        response = authenticated_no_role_client.get(self._url(sign_up_collection))

        soup = BeautifulSoup(response.data, "html.parser")
        assert soup.select_one("input[name='user_name']")["value"] == "Test applicant"

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_without_session_redirects(self, authenticated_no_role_client, sign_up_collection, db_session):
        authenticated_no_role_client.user.name = None
        db_session.commit()

        _seed_session(authenticated_no_role_client, sign_up_collection)

        response = authenticated_no_role_client.get(self._url(sign_up_collection))

        assert response.status_code == 302
        assert response.location == _sign_up_router_url(sign_up_collection)

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_skips_the_step_when_we_already_hold_a_name(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            self._org_session(sign_up_collection, needs_user_name=False),
        )

        response = authenticated_no_role_client.get(self._url(sign_up_collection))

        assert authenticated_no_role_client.user.name
        assert response.status_code == 302
        assert response.location == self._cya_url(sign_up_collection)

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_persists_the_name_to_the_session_and_continues(
        self, authenticated_no_role_client, sign_up_collection, db_session
    ):
        authenticated_no_role_client.user.name = None
        db_session.commit()

        _seed_session(authenticated_no_role_client, sign_up_collection, self._org_session(sign_up_collection))

        response = authenticated_no_role_client.post(
            self._url(sign_up_collection), data={"user_name": "  Test applicant  ", "submit": "y"}
        )

        assert response.status_code == 302
        assert response.location == self._cya_url(sign_up_collection)

        with authenticated_no_role_client.session_transaction() as flask_session:
            assert flask_session["create_organisation"]["user_name"] == "Test applicant"

        # the name only reaches the user record when they confirm their answers
        db_session.refresh(authenticated_no_role_client.user)
        assert authenticated_no_role_client.user.name is None

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_source_round_trip_back_to_check_your_answers(
        self, authenticated_no_role_client, sign_up_collection, db_session
    ):
        authenticated_no_role_client.user.name = None
        db_session.commit()

        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            self._org_session(sign_up_collection, user_name="Test applicant"),
        )

        get_response = authenticated_no_role_client.get(self._url(sign_up_collection, source="check-your-answers"))
        soup = BeautifulSoup(get_response.data, "html.parser")
        assert soup.select_one("a.govuk-back-link")["href"] == self._cya_url(sign_up_collection)

        post_response = authenticated_no_role_client.post(
            self._url(sign_up_collection, source="check-your-answers"),
            data={"user_name": "Grace Hopper", "submit": "y"},
        )
        assert post_response.status_code == 302
        assert post_response.location == self._cya_url(sign_up_collection)


class TestCreateOrganisationCheckYourAnswers:
    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_renders_the_answers_with_change_links(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            _create_organisation_session(
                sign_up_collection.id,
                organisation_type=SignUpOrganisationType.CHARITY,
                name="Acme Ltd",
                external_id="000111222",
                allow_team_members=False,
            ),
        )

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.create_organisation_check_your_answers",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Confirm your details are correct" in get_h1_text(soup)
        assert get_summary_list_value_by_key(soup, "Email address").text.strip() == "applicant@no-org.com"
        assert get_summary_list_value_by_key(soup, "Organisation type").text.strip() == "Charity"
        assert get_summary_list_value_by_key(soup, "Organisation name").text.strip() == "Acme Ltd"

        change_type = url_for(
            "access_grant_funding.create_organisation_type",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
            source="check-your-answers",
        )
        change_name = url_for(
            "access_grant_funding.create_organisation_name",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
            source="check-your-answers",
        )
        hrefs = {a["href"] for a in soup.select("a")}
        assert change_type in hrefs
        assert change_name in hrefs

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_changes_a_looked_up_companys_name_through_the_company_search(
        self, authenticated_no_role_client, sign_up_collection
    ):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            _create_organisation_session(
                sign_up_collection.id,
                organisation_type=SignUpOrganisationType.COMPANY,
                identified_by=OrganisationIdentification.COMPANIES_HOUSE,
                companies_house_lookup=True,
                name="Test Company Ltd",
                external_id="AB123456",
                allow_team_members=False,
            ),
        )

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.create_organisation_check_your_answers",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_summary_list_value_by_key(soup, "Organisation name").text.strip() == "Test Company Ltd"
        change_name = page_has_link(soup, "Change organisation name")
        assert change_name
        assert change_name.attrs["href"] == url_for(
            "access_grant_funding.create_organisation_company_search",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
            source="check-your-answers",
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_shows_a_name_we_already_hold_without_a_change_link(
        self, authenticated_no_role_client, sign_up_collection
    ):
        _seed_session(authenticated_no_role_client, sign_up_collection, self._complete_session(sign_up_collection))

        response = authenticated_no_role_client.get(self._cya_url(sign_up_collection))

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_summary_list_value_by_key(soup, "Full name").text.strip() == authenticated_no_role_client.user.name

        change_user_name = url_for(
            "access_grant_funding.create_organisation_user_name",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
            source="check-your-answers",
        )
        assert change_user_name not in {a["href"] for a in soup.select("a")}
        # the full-name step was never shown, so back goes to the allow-team-members step it did show
        assert soup.select_one("a.govuk-back-link")["href"] == url_for(
            "access_grant_funding.create_organisation_allow_team_members",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_shows_the_name_from_the_session_with_a_change_link(
        self, authenticated_no_role_client, sign_up_collection, db_session
    ):
        authenticated_no_role_client.user.name = None
        db_session.commit()

        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            self._complete_session(sign_up_collection, needs_user_name=True, user_name="Test applicant"),
        )

        response = authenticated_no_role_client.get(self._cya_url(sign_up_collection))

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_summary_list_value_by_key(soup, "Full name").text.strip() == "Test applicant"

        change_user_name = url_for(
            "access_grant_funding.create_organisation_user_name",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
            source="check-your-answers",
        )
        assert change_user_name in {a["href"] for a in soup.select("a")}
        assert soup.select_one("a.govuk-back-link")["href"] == url_for(
            "access_grant_funding.create_organisation_user_name",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_without_a_complete_session_redirects(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            _create_organisation_session(sign_up_collection.id, organisation_type=SignUpOrganisationType.OTHER),
        )

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.create_organisation_check_your_answers",
                grant_slug=sign_up_collection.grant.slug,
                collection_slug=sign_up_collection.slug,
            )
        )

        assert response.status_code == 302
        assert response.location == _sign_up_router_url(sign_up_collection)

    def _complete_session(
        self, collection, *, allow_team_members=False, organisation_type=SignUpOrganisationType.OTHER, **kwargs
    ) -> CreateOrganisationSession:
        return _create_organisation_session(
            collection.id,
            organisation_type=organisation_type,
            name="Acme Ltd",
            external_id="000111222",
            allow_team_members=allow_team_members,
            **kwargs,
        )

    def _cya_url(self, collection) -> str:
        return url_for(
            "access_grant_funding.create_organisation_check_your_answers",
            grant_slug=collection.grant.slug,
            collection_slug=collection.slug,
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_with_a_company_from_the_register_creates_a_company_organisation(
        self, authenticated_no_role_client, sign_up_collection, db_session, mock_notification_service_calls
    ):
        _seed_company_session(
            authenticated_no_role_client,
            sign_up_collection,
            name="TEST COMPANY LIMITED",
            external_id="00000001",
            allow_team_members=False,
        )

        response = authenticated_no_role_client.post(self._cya_url(sign_up_collection), data={"submit": "y"})

        assert response.status_code == 302
        organisation = db_session.scalars(select(Organisation).where(Organisation.external_id == "CH-00000001")).one()
        assert organisation.name == "TEST COMPANY LIMITED"
        assert organisation.type == OrganisationType.COMPANY
        assert organisation.companies_house_number == "00000001"
        assert organisation.custom_code is None

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_creates_the_organisation_grant_recipient_and_data_provider_role(
        self, authenticated_no_role_client, sign_up_collection, db_session, mock_notification_service_calls, caplog
    ):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            self._complete_session(sign_up_collection, organisation_type=SignUpOrganisationType.COMPANY),
        )

        with caplog.at_level(logging.INFO):
            response = authenticated_no_role_client.post(self._cya_url(sign_up_collection), data={"submit": "y"})

        organisation = db_session.scalars(select(Organisation).where(Organisation.external_id == "FS-000111222")).one()
        assert any(
            message
            == AnyStringMatching(
                rf"^Organisation {organisation.external_id} created\. Organisation type was ignored: COMPANY$"
            )
            for message in caplog.messages
        )
        assert organisation.name == "Acme Ltd"
        assert organisation.type == OrganisationType.OTHER
        assert organisation.custom_code == "000111222"
        assert organisation.mode == OrganisationModeEnum.LIVE
        assert organisation.status == OrganisationStatus.ACTIVE
        assert organisation.can_manage_grants is False
        assert organisation.domains == []

        grant_recipient = db_session.scalars(
            select(GrantRecipient).where(
                GrantRecipient.grant_id == sign_up_collection.grant.id,
                GrantRecipient.organisation_id == organisation.id,
            )
        ).one()
        assert grant_recipient.status == GrantRecipientStatusEnum.APPLYING
        assert grant_recipient.mode == GrantRecipientModeEnum.LIVE

        user_role = db_session.scalars(
            select(UserRole).where(
                UserRole.user_id == authenticated_no_role_client.user.id,
                UserRole.organisation_id == organisation.id,
                UserRole.grant_id == sign_up_collection.grant.id,
            )
        ).one()
        assert RoleEnum.DATA_PROVIDER in user_role.permissions
        assert RoleEnum.MEMBER in user_role.permissions

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.list_collections",
            organisation_id=organisation.id,
            grant_id=sign_up_collection.grant.id,
        )

        with authenticated_no_role_client.session_transaction() as flask_session:
            assert "create_organisation" not in flask_session
            assert "signing_up_for_collection_id" not in flask_session

        assert len(mock_notification_service_calls) == 1
        notification_call = mock_notification_service_calls[0]
        assert notification_call.args == (
            authenticated_no_role_client.user.email,
            "bede86cd-b956-4dad-8f28-17a797788811",
        )
        assert notification_call.kwargs["personalisation"]["submission_name"] == sign_up_collection.name
        assert notification_call.kwargs["personalisation"]["organisation_name"] == "Acme Ltd"
        assert notification_call.kwargs["personalisation"]["grant_name"] == "Test grant name"

        followed_response = authenticated_no_role_client.get(response.location, follow_redirects=True)
        assert followed_response.status_code == 200
        followed_text = BeautifulSoup(followed_response.data, "html.parser").text
        assert "Organisation created" in followed_text
        assert "Acme Ltd has been created successfully. You can now start applying for Test grant name." in (
            followed_text
        )

    def test_post_creates_a_test_organisation_for_a_deliver_user_testing_access(
        self, anonymous_client, sign_up_collection, factories, user, db_session, mock_notification_service_calls
    ):
        factories.user_role.create(
            user=user,
            organisation=sign_up_collection.grant.organisation,
            grant=sign_up_collection.grant,
            permissions=[RoleEnum.MEMBER],
        )

        login_user(user)
        with anonymous_client.session_transaction() as flask_session:
            flask_session["auth"] = AuthMethodEnum.SSO
        db_session.commit()

        _seed_session(anonymous_client, sign_up_collection, self._complete_session(sign_up_collection))

        response = anonymous_client.post(self._cya_url(sign_up_collection), data={"submit": "y"})

        organisation = db_session.scalars(select(Organisation).where(Organisation.external_id == "FS-000111222")).one()
        assert organisation.name == "Acme Ltd (test)"
        assert organisation.mode == OrganisationModeEnum.TEST

        grant_recipient = db_session.scalars(
            select(GrantRecipient).where(GrantRecipient.organisation_id == organisation.id)
        ).one()
        assert grant_recipient.mode == GrantRecipientModeEnum.TEST

        assert response.status_code == 302

        assert len(mock_notification_service_calls) == 1
        notification_call = mock_notification_service_calls[0]
        assert notification_call.args == (user.email, "bede86cd-b956-4dad-8f28-17a797788811")

    @pytest.mark.authenticate_as("applicant@no-org.com")
    @patch("app.access_grant_funding.helpers.emit_metric_count")
    def test_post_emits_organisation_created_metric_with_organisation_type(
        self, mock_count, authenticated_no_role_client, sign_up_collection, db_session, mock_notification_service_calls
    ):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            _create_organisation_session(
                sign_up_collection.id,
                organisation_type=SignUpOrganisationType.CHARITY,
                name="Acme Ltd",
                external_id="000111222",
                allow_team_members=False,
            ),
        )

        response = authenticated_no_role_client.post(self._cya_url(sign_up_collection), data={"submit": "y"})
        assert response.status_code == 302

        grant_recipient = db_session.scalars(
            select(GrantRecipient).where(GrantRecipient.grant_id == sign_up_collection.grant.id)
        ).one()
        mock_count.assert_called_once_with(
            MetricEventName.PUBLIC_SIGN_UP_ORGANISATION_CREATED,
            grant_recipient=grant_recipient,
            collection=sign_up_collection,
            custom_attributes={
                MetricAttributeName.ORGANISATION_TYPE: "CHARITY",
                MetricAttributeName.SUBMISSION_MODE: str(SubmissionModeEnum.LIVE),
            },
        )

    @patch("app.access_grant_funding.helpers.emit_metric_count")
    def test_post_as_deliver_user_testing_access_does_not_emit_metric(
        self, mock_count, authenticated_platform_admin_client, sign_up_collection, mock_notification_service_calls
    ):
        _seed_session(
            authenticated_platform_admin_client, sign_up_collection, self._complete_session(sign_up_collection)
        )

        response = authenticated_platform_admin_client.post(self._cya_url(sign_up_collection), data={"submit": "y"})

        assert response.status_code == 302
        mock_count.assert_not_called()

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_claims_the_eligibility_submission(
        self, authenticated_no_role_client, sign_up_collection, db_session, mock_notification_service_calls
    ):
        unclaimed_submission = get_or_create_unclaimed_submission(
            authenticated_no_role_client.user, sign_up_collection, SubmissionModeEnum.LIVE
        ).submission
        db_session.commit()

        _seed_session(authenticated_no_role_client, sign_up_collection, self._complete_session(sign_up_collection))

        response = authenticated_no_role_client.post(self._cya_url(sign_up_collection), data={"submit": "y"})
        assert response.status_code == 302

        organisation = db_session.scalars(select(Organisation).where(Organisation.external_id == "FS-000111222")).one()
        grant_recipient = db_session.scalars(
            select(GrantRecipient).where(GrantRecipient.organisation_id == organisation.id)
        ).one()

        db_session.refresh(unclaimed_submission)
        assert unclaimed_submission.grant_recipient_id == grant_recipient.id

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_sets_the_users_name_from_the_session(
        self, authenticated_no_role_client, sign_up_collection, db_session, mock_notification_service_calls
    ):
        authenticated_no_role_client.user.name = None
        db_session.commit()

        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            self._complete_session(sign_up_collection, needs_user_name=True, user_name="Test applicant"),
        )

        response = authenticated_no_role_client.post(self._cya_url(sign_up_collection), data={"submit": "y"})

        assert response.status_code == 302
        db_session.refresh(authenticated_no_role_client.user)
        assert authenticated_no_role_client.user.name == "Test applicant"

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_leaves_a_name_we_already_hold_alone(
        self, authenticated_no_role_client, sign_up_collection, db_session, mock_notification_service_calls
    ):
        existing_name = authenticated_no_role_client.user.name
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            self._complete_session(sign_up_collection, user_name="Test applicant"),
        )

        response = authenticated_no_role_client.post(self._cya_url(sign_up_collection), data={"submit": "y"})

        assert response.status_code == 302
        db_session.refresh(authenticated_no_role_client.user)
        assert authenticated_no_role_client.user.name == existing_name

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_does_not_set_the_users_name_when_the_organisation_name_was_taken(
        self, authenticated_no_role_client, sign_up_collection, factories, db_session, mock_notification_service_calls
    ):
        authenticated_no_role_client.user.name = None
        db_session.commit()

        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            self._complete_session(sign_up_collection, needs_user_name=True, user_name="Test applicant"),
        )
        factories.organisation.create(name="Acme Ltd", mode=OrganisationModeEnum.LIVE)

        response = authenticated_no_role_client.post(self._cya_url(sign_up_collection), data={"submit": "y"})

        assert response.status_code == 302
        db_session.refresh(authenticated_no_role_client.user)
        assert authenticated_no_role_client.user.name is None

        assert mock_notification_service_calls == []

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_redirects_to_already_exists_when_the_name_was_taken_in_the_meantime(
        self, authenticated_no_role_client, sign_up_collection, factories, db_session
    ):
        _seed_session(authenticated_no_role_client, sign_up_collection, self._complete_session(sign_up_collection))
        factories.organisation.create(name="Acme Ltd", mode=OrganisationModeEnum.LIVE)

        response = authenticated_no_role_client.post(self._cya_url(sign_up_collection), data={"submit": "y"})

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.create_organisation_already_exists",
            grant_slug=sign_up_collection.grant.slug,
            collection_slug=sign_up_collection.slug,
            source="check-your-answers",
        )

        assert db_session.scalars(select(GrantRecipient)).all() == []

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_twice_creates_a_single_organisation_and_grant_recipient(
        self, authenticated_no_role_client, sign_up_collection, db_session, mock_notification_service_calls
    ):
        for _ in range(2):
            _seed_session(authenticated_no_role_client, sign_up_collection, self._complete_session(sign_up_collection))
            authenticated_no_role_client.post(self._cya_url(sign_up_collection), data={"submit": "y"})

        assert (
            db_session.scalars(select(Organisation).where(Organisation.external_id == "FS-000111222")).one() is not None
        )
        assert len(db_session.scalars(select(GrantRecipient)).all()) == 1

        assert len(mock_notification_service_calls) == 1

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_without_a_complete_session_redirects(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            _create_organisation_session(sign_up_collection.id, organisation_type=SignUpOrganisationType.OTHER),
        )

        response = authenticated_no_role_client.post(self._cya_url(sign_up_collection), data={"submit": "y"})

        assert response.status_code == 302
        assert response.location == _sign_up_router_url(sign_up_collection)

    def _allow_team_members_change_href(self, collection) -> str:
        return url_for(
            "access_grant_funding.create_organisation_allow_team_members",
            grant_slug=collection.grant.slug,
            collection_slug=collection.slug,
            source="check-your-answers",
        )

    @pytest.mark.authenticate_as("applicant@no-org.com")
    @pytest.mark.parametrize("allow_team_members, expected_value", [(True, "Yes"), (False, "No")])
    def test_get_renders_the_allow_team_members_row_and_change_link(
        self, authenticated_no_role_client, sign_up_collection, allow_team_members, expected_value
    ):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            self._complete_session(sign_up_collection, allow_team_members=allow_team_members),
        )

        response = authenticated_no_role_client.get(self._cya_url(sign_up_collection))

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert (
            get_summary_list_value_by_key(soup, "Allow team members to apply as Acme Ltd").text.strip()
            == expected_value
        )
        assert self._allow_team_members_change_href(sign_up_collection) in {a["href"] for a in soup.select("a")}

    @pytest.mark.authenticate_as("applicant@gmail.com")
    def test_get_omits_the_allow_team_members_row_for_a_shared_email_domain(
        self, authenticated_no_role_client, sign_up_collection
    ):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            self._complete_session(sign_up_collection, can_share_email_domain=False, allow_team_members=None),
        )

        response = authenticated_no_role_client.get(self._cya_url(sign_up_collection))

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_summary_list_value_by_key(soup, "Allow team members to apply as Acme Ltd") is None
        assert self._allow_team_members_change_href(sign_up_collection) not in {a["href"] for a in soup.select("a")}

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_get_with_allow_team_members_unanswered_redirects(self, authenticated_no_role_client, sign_up_collection):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            self._complete_session(sign_up_collection, allow_team_members=None),
        )

        response = authenticated_no_role_client.get(self._cya_url(sign_up_collection))

        assert response.status_code == 302
        assert response.location == _sign_up_router_url(sign_up_collection)

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_with_allow_team_members_writes_the_email_domain_to_the_organisation(
        self, authenticated_no_role_client, sign_up_collection, db_session, mock_notification_service_calls
    ):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            self._complete_session(sign_up_collection, allow_team_members=True),
        )

        response = authenticated_no_role_client.post(self._cya_url(sign_up_collection), data={"submit": "y"})

        assert response.status_code == 302
        organisation = db_session.scalars(select(Organisation).where(Organisation.external_id == "FS-000111222")).one()
        assert organisation.domains == ["no-org.com"]

    @pytest.mark.authenticate_as("applicant@no-org.com")
    def test_post_without_allow_team_members_leaves_the_organisation_domains_empty(
        self, authenticated_no_role_client, sign_up_collection, db_session, mock_notification_service_calls
    ):
        _seed_session(
            authenticated_no_role_client,
            sign_up_collection,
            self._complete_session(sign_up_collection, allow_team_members=False),
        )

        response = authenticated_no_role_client.post(self._cya_url(sign_up_collection), data={"submit": "y"})

        assert response.status_code == 302
        organisation = db_session.scalars(select(Organisation).where(Organisation.external_id == "FS-000111222")).one()
        assert organisation.domains == []
