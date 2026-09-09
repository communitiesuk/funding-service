import base64

import pytest
import requests
import responses
from responses import matchers

from app.extensions import companies_house_service
from app.services.companies_house import (
    CompaniesHouseError,
    CompaniesHouseNotFoundError,
    CompanyProfile,
    CompanySearchResult,
    CompanySearchResults,
    InMemoryCompaniesHouseCache,
)

SEARCH_RESPONSE = {
    "items": [
        {
            "title": "TEST COMPANY LIMITED",
            "company_number": "00000001",
            "address_snippet": "1 Test Street, Testtown, TE1 1ST",
            "company_status": "active",
            "date_of_creation": "2000-01-01",
            "kind": "searchresults#company",
        },
        {
            "title": "TEST COMPANY TWO LTD",
            "company_number": "00000002",
            "address_snippet": "2 Test Street, Testtown, TE1 1ST",
            "company_status": "dissolved",
        },
    ],
    "total_results": 2,
    "items_per_page": 20,
    "start_index": 0,
    "kind": "search#companies",
}

COMPANY_RESPONSE = {
    "company_name": "TEST COMPANY LIMITED",
    "company_number": "00000001",
    "company_status": "active",
    "registered_office_address": {"address_line_1": "1 Test Street", "locality": "Testtown", "postal_code": "TE1 1ST"},
}


@pytest.fixture(autouse=True)
def clear_companies_house_cache(app):
    companies_house_service.cache.clear()


def _search_url(app):
    return app.config["COMPANIES_HOUSE_API_URL"] + "/search/companies"


def _company_url(app, company_number):
    return app.config["COMPANIES_HOUSE_API_URL"] + f"/company/{company_number}"


def _basic_auth_header(app):
    return "Basic " + base64.b64encode(f"{app.config['COMPANIES_HOUSE_API_KEY']}:".encode()).decode()


class TestCompaniesHouseService:
    """
    Test that the service maps to the expected Companies House HTTP API calls and parses their responses.
    """

    @responses.activate
    def test_search_companies(self, app):
        request_matcher = responses.get(
            url=_search_url(app),
            status=200,
            match=[
                matchers.query_param_matcher({"q": "test company", "items_per_page": "20", "start_index": "0"}),
                matchers.header_matcher({"Authorization": _basic_auth_header(app)}),
            ],
            json=SEARCH_RESPONSE,
        )

        results = companies_house_service.search_companies("test company")

        assert results == CompanySearchResults(
            items=[
                CompanySearchResult(
                    company_number="00000001",
                    title="TEST COMPANY LIMITED",
                    address_snippet="1 Test Street, Testtown, TE1 1ST",
                    company_status="active",
                ),
                CompanySearchResult(
                    company_number="00000002",
                    title="TEST COMPANY TWO LTD",
                    address_snippet="2 Test Street, Testtown, TE1 1ST",
                    company_status="dissolved",
                ),
            ],
            total_results=2,
            start_index=0,
            items_per_page=20,
        )
        assert results.page == 1
        assert results.total_pages == 1
        assert request_matcher.call_count == 1

    @responses.activate
    def test_search_companies_requests_the_start_index_for_a_page(self, app):
        request_matcher = responses.get(
            url=_search_url(app),
            match=[matchers.query_param_matcher({"q": "test company", "items_per_page": "20", "start_index": "40"})],
            json={**SEARCH_RESPONSE, "start_index": 40, "total_results": 45},
        )

        results = companies_house_service.search_companies("test company", page=3)

        assert results.page == 3
        assert results.total_pages == 3
        assert request_matcher.call_count == 1

    @responses.activate
    def test_search_companies_caches_pages_separately(self, app):
        first_page = responses.get(
            url=_search_url(app),
            match=[matchers.query_param_matcher({"q": "test company", "items_per_page": "20", "start_index": "0"})],
            json=SEARCH_RESPONSE,
        )
        second_page = responses.get(
            url=_search_url(app),
            match=[matchers.query_param_matcher({"q": "test company", "items_per_page": "20", "start_index": "20"})],
            json={**SEARCH_RESPONSE, "start_index": 20},
        )

        companies_house_service.search_companies("test company")
        companies_house_service.search_companies("test company", page=2)
        companies_house_service.search_companies("test company", page=2)

        assert first_page.call_count == 1
        assert second_page.call_count == 1

    @responses.activate
    def test_search_companies_returns_cached_result_for_repeated_query(self, app):
        request_matcher = responses.get(url=_search_url(app), json=SEARCH_RESPONSE)

        first_results = companies_house_service.search_companies("test company")
        second_results = companies_house_service.search_companies("test company")

        assert first_results == second_results
        assert request_matcher.call_count == 1

    @responses.activate
    def test_search_companies_raises_when_disabled(self, app, monkeypatch):
        monkeypatch.setitem(app.config, "COMPANIES_HOUSE_DISABLE", True)

        with pytest.raises(CompaniesHouseError):
            companies_house_service.search_companies("test company")

        assert len(responses.calls) == 0

    @responses.activate
    def test_search_companies_raises_on_api_error_and_does_not_cache_it(self, app):
        responses.get(url=_search_url(app), status=500)
        responses.get(url=_search_url(app), json=SEARCH_RESPONSE)

        with pytest.raises(CompaniesHouseError):
            companies_house_service.search_companies("test company")
        results = companies_house_service.search_companies("test company")

        assert results.total_results == 2
        assert len(responses.calls) == 2

    @responses.activate
    def test_search_companies_raises_on_connection_error(self, app):
        responses.get(url=_search_url(app), body=requests.ConnectionError("connection refused"))

        with pytest.raises(CompaniesHouseError):
            companies_house_service.search_companies("test company")

    @responses.activate
    def test_search_companies_raises_on_unexpected_payload(self, app):
        responses.get(url=_search_url(app), json={"items": "not-a-list", "total_results": 1})

        with pytest.raises(CompaniesHouseError):
            companies_house_service.search_companies("test company")

    @responses.activate
    def test_get_company(self, app):
        request_matcher = responses.get(
            url=_company_url(app, "00000001"),
            match=[matchers.header_matcher({"Authorization": _basic_auth_header(app)})],
            json=COMPANY_RESPONSE,
        )

        company = companies_house_service.get_company("00000001")

        assert company == CompanyProfile(
            company_number="00000001", company_name="TEST COMPANY LIMITED", company_status="active"
        )
        assert request_matcher.call_count == 1

    @responses.activate
    def test_get_company_normalises_the_company_number(self, app):
        request_matcher = responses.get(url=_company_url(app, "NI000001"), json=COMPANY_RESPONSE)

        companies_house_service.get_company(" ni000001 ")

        assert request_matcher.call_count == 1

    @responses.activate
    def test_get_company_returns_cached_result_for_repeated_lookup(self, app):
        request_matcher = responses.get(url=_company_url(app, "00000001"), json=COMPANY_RESPONSE)

        companies_house_service.get_company("00000001")
        companies_house_service.get_company("00000001")

        assert request_matcher.call_count == 1

    @responses.activate
    def test_get_company_raises_not_found(self, app):
        responses.get(
            url=_company_url(app, "00000001"), status=404, json={"errors": [{"error": "company-profile-not-found"}]}
        )

        with pytest.raises(CompaniesHouseNotFoundError):
            companies_house_service.get_company("00000001")


class TestInMemoryCompaniesHouseCache:
    def test_expires_entries_after_the_ttl(self):
        clock = {"now": 0.0}
        cache = InMemoryCompaniesHouseCache(maxsize=10, ttl_seconds=60, timer=lambda: clock["now"])

        cache.set("key", {"value": 1})
        assert cache.get("key") == {"value": 1}

        clock["now"] = 61.0
        assert cache.get("key") is None

    def test_clear_empties_the_cache(self):
        cache = InMemoryCompaniesHouseCache(maxsize=10, ttl_seconds=60)
        cache.set("key", {"value": 1})

        cache.clear()

        assert cache.get("key") is None
