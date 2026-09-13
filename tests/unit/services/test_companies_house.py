import base64

import pytest
import requests
import responses
from pydantic import ValidationError
from responses import matchers

from app.extensions import companies_house_service
from app.services.companies_house import (
    CompaniesHouseDisabledError,
    CompaniesHouseError,
    CompaniesHouseNotFoundError,
    CompanyProfile,
    CompanySearchResult,
    CompanySearchResults,
)


def _company(company_number="00000001", title="TEST COMPANY LIMITED", **fields):
    return {"company_number": company_number, "title": title, **fields}


def _profile(company_number="00000001", company_name="TEST COMPANY LIMITED", **fields):
    return {"company_number": company_number, "company_name": company_name, **fields}


def _search_payload(items, *, total_results=None, start_index=0, items_per_page=20):
    return {
        "items": items,
        "total_results": len(items) if total_results is None else total_results,
        "items_per_page": items_per_page,
        "start_index": start_index,
    }


def _validate_results(payload, max_results=1000) -> CompanySearchResults:
    return CompanySearchResults.model_validate(payload, context={"max_results": max_results})


def _results(total_results, *, start_index=0, items_per_page=20) -> CompanySearchResults:
    items_on_page = min(items_per_page, max(0, total_results - start_index))
    return _validate_results(
        _search_payload(
            [_company() for _ in range(items_on_page)],
            total_results=total_results,
            start_index=start_index,
            items_per_page=items_per_page,
        )
    )


def _assert_error(exc_info, reason, *, status_code=None, cause=None):
    assert exc_info.value.reason == reason
    assert exc_info.value.status_code == status_code
    if cause is not None:
        assert isinstance(exc_info.value.__cause__, cause)


@pytest.fixture(scope="module")
def api_url(app):
    return companies_house_service.api_url


@pytest.fixture(scope="module")
def search_url(api_url):
    return f"{api_url}/search/companies"


@pytest.fixture(scope="module")
def auth_header(app):
    credentials = base64.b64encode(f"{companies_house_service.api_key}:".encode()).decode()
    return {"Authorization": f"Basic {credentials}"}


class TestCompanySearchResults:
    @pytest.mark.parametrize(
        "total_results, start_index, page, total_pages, is_truncated",
        [
            (0, 0, 1, 1, False),
            (21, 20, 2, 2, False),
            (999, 0, 1, 50, False),
            (1000, 0, 1, 50, False),
            (1001, 0, 1, 50, True),
            (5000, 980, 50, 50, True),
            (100, 580, 30, 5, False),
        ],
    )
    def test_page_and_total_pages_follow_the_paging_metadata(
        self, total_results, start_index, page, total_pages, is_truncated
    ):
        results = _results(total_results, start_index=start_index)

        assert results.page == page
        assert results.total_pages == total_pages
        assert results.is_truncated is is_truncated

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param(_search_payload([_company()], total_results=11, start_index=10), id="partial page"),
            pytest.param(_search_payload([_company() for _ in range(21)], total_results=21), id="too many items"),
            pytest.param(_search_payload([_company()], total_results=5, start_index=20), id="items past the end"),
            pytest.param(_search_payload([], total_results=5), id="no items when results remain"),
        ],
    )
    def test_rejects_paging_metadata_that_does_not_match_the_items(self, payload):
        with pytest.raises(ValidationError):
            _validate_results(payload)


class TestCompaniesHouseService:
    def test_client_does_not_retry(self):
        assert companies_house_service.client.get_adapter("http://").max_retries.total == 0
        assert companies_house_service.client.get_adapter("https://").max_retries.total == 0

    @responses.activate
    def test_requests_uses_the_configured_timeout(self, search_url, mocker):
        responses.get(search_url, json=_search_payload([]))
        get = mocker.spy(companies_house_service.client, "get")

        companies_house_service.search_companies("Test Company")

        assert get.call_args.kwargs["timeout"] == companies_house_service.request_timeout

    @responses.activate
    @pytest.mark.parametrize(
        "attribute, value, error_type, reason",
        [
            ("disabled", True, CompaniesHouseDisabledError, "disabled"),
            ("api_key", "", CompaniesHouseError, "configuration"),
            ("api_key", "   ", CompaniesHouseError, "configuration"),
        ],
    )
    def test_fails_before_making_a_request_when_disabled_or_unconfigured(
        self, monkeypatch, attribute, value, error_type, reason
    ):
        monkeypatch.setattr(companies_house_service, attribute, value)

        with pytest.raises(error_type) as exc_info:
            companies_house_service.search_companies("Test Company")

        _assert_error(exc_info, reason)
        assert len(responses.calls) == 0

    @responses.activate
    @pytest.mark.parametrize("status", [404, 416])
    def test_not_found_and_range_statuses_raise_not_found(self, search_url, status):
        responses.get(search_url, status=status)

        with pytest.raises(CompaniesHouseNotFoundError) as exc_info:
            companies_house_service.search_companies("Test Company")

        _assert_error(exc_info, "not_found", status_code=status)

    @responses.activate
    @pytest.mark.parametrize("status", [302, 401, 429, 500])
    def test_other_error_statuses_and_redirects_raise_upstream_errors(self, search_url, status):
        responses.get(search_url, status=status)

        with pytest.raises(CompaniesHouseError) as exc_info:
            companies_house_service.search_companies("Test Company")

        _assert_error(exc_info, "upstream", status_code=status)

    @responses.activate
    @pytest.mark.parametrize(
        "failure, reason",
        [
            (requests.ConnectTimeout(), "timeout"),
            (requests.ReadTimeout(), "timeout"),
            (requests.ConnectionError(), "upstream"),
        ],
    )
    def test_timeouts_and_connection_failures_raise_errors_without_retrying(self, search_url, failure, reason):
        responses.get(search_url, body=failure)

        with pytest.raises(CompaniesHouseError) as exc_info:
            companies_house_service.search_companies("Test Company")

        _assert_error(exc_info, reason, cause=type(failure))
        assert len(responses.calls) == 1

    @responses.activate
    def test_invalid_json_raises_an_error_from_the_decoding_failure(self, search_url):
        responses.get(search_url, body="not json")

        with pytest.raises(CompaniesHouseError) as exc_info:
            companies_house_service.search_companies("Test Company")

        _assert_error(exc_info, "invalid_json", status_code=200, cause=requests.exceptions.JSONDecodeError)

    class TestSearchCompanies:
        @responses.activate
        def test_returns_typed_results_and_sends_the_expected_request(self, search_url, auth_header):
            request = responses.get(
                search_url,
                json=_search_payload(
                    [
                        _company("00000001", address_snippet="1 Test Street, Testtown", company_status="active"),
                        _company("00000002"),
                    ]
                ),
                match=[
                    matchers.query_param_matcher(
                        {
                            "q": "Test Company",
                            "items_per_page": companies_house_service.items_per_page,
                            "start_index": 0,
                        }
                    ),
                    matchers.header_matcher(auth_header),
                ],
            )

            results = companies_house_service.search_companies("Test Company")

            assert results.items == [
                CompanySearchResult(
                    company_number="00000001",
                    title="TEST COMPANY LIMITED",
                    address_snippet="1 Test Street, Testtown",
                    company_status="active",
                ),
                CompanySearchResult(company_number="00000002", title="TEST COMPANY LIMITED"),
            ]
            assert results.total_results == 2
            assert request.call_count == 1

        @responses.activate
        @pytest.mark.parametrize("query, sent", [("  abc  ", "abc"), ("x" * 3, "x" * 3), ("x" * 160, "x" * 160)])
        def test_strips_the_query_and_accepts_the_length_boundaries(self, search_url, query, sent):
            request = responses.get(
                search_url,
                json=_search_payload([]),
                match=[matchers.query_param_matcher({"q": sent}, strict_match=False)],
            )

            companies_house_service.search_companies(query)

            assert request.call_count == 1

        @responses.activate
        @pytest.mark.parametrize("query", ["ab", "x" * 161, "   ", ""])
        def test_rejects_invalid_queries_before_making_a_request(self, query):
            with pytest.raises(ValueError):
                companies_house_service.search_companies(query)

            assert len(responses.calls) == 0

        @responses.activate
        @pytest.mark.parametrize("page, start_index", [(1, 0), (2, 20), (50, 980), (0, 0), (-1, 0), (51, 0)])
        def test_sends_the_start_index_for_the_requested_page(self, search_url, page, start_index):
            request = responses.get(
                search_url,
                json=_search_payload([], start_index=start_index),
                match=[matchers.query_param_matcher({"start_index": start_index}, strict_match=False)],
            )

            companies_house_service.search_companies("Test Company", page=page)

            assert request.call_count == 1

        @responses.activate
        @pytest.mark.parametrize(
            "payload",
            [
                pytest.param(_search_payload([_company()], items_per_page=10), id="items per page"),
                pytest.param(_search_payload([_company()], total_results=21, start_index=20), id="start index"),
            ],
        )
        def test_rejects_paging_metadata_that_does_not_echo_the_request(self, search_url, payload):
            responses.get(search_url, json=payload)

            with pytest.raises(CompaniesHouseError) as exc_info:
                companies_house_service.search_companies("Test Company")

            _assert_error(exc_info, "invalid_payload", status_code=200)

        @responses.activate
        @pytest.mark.parametrize(
            "payload",
            [
                pytest.param(_search_payload([{"company_number": "00000001"}]), id="missing title"),
                pytest.param(_search_payload([_company(company_number=1)]), id="mistyped company number"),
                pytest.param(_search_payload([_company("1234567")]), id="malformed company number"),
                pytest.param(_search_payload([_company()], total_results=-1), id="negative total"),
            ],
        )
        def test_rejects_payloads_missing_or_mistyped_required_fields(self, search_url, payload):
            responses.get(search_url, json=payload)

            with pytest.raises(CompaniesHouseError) as exc_info:
                companies_house_service.search_companies("Test Company")

            _assert_error(exc_info, "invalid_payload", status_code=200, cause=ValidationError)

    class TestGetCompany:
        @responses.activate
        @pytest.mark.parametrize("requested, path_number", [(" ni000001 ", "NI000001"), ("00000001", "00000001")])
        def test_returns_a_typed_profile_and_normalises_the_company_number(
            self, api_url, auth_header, requested, path_number
        ):
            request = responses.get(
                f"{api_url}/company/{path_number}",
                json=_profile(path_number),
                match=[matchers.header_matcher(auth_header)],
            )

            profile = companies_house_service.get_company(requested)

            assert profile == CompanyProfile(company_number=path_number, company_name="TEST COMPANY LIMITED")
            assert profile.company_status is None
            assert request.call_count == 1

        @responses.activate
        @pytest.mark.parametrize("company_number", ["1234567", "123456789", "0000-001", ""])
        def test_rejects_invalid_company_numbers_before_making_a_request(self, company_number):
            with pytest.raises(ValueError):
                companies_house_service.get_company(company_number)

            assert len(responses.calls) == 0

        @responses.activate
        def test_unknown_company_raises_not_found(self, api_url):
            responses.get(f"{api_url}/company/00000001", status=404)

            with pytest.raises(CompaniesHouseNotFoundError) as exc_info:
                companies_house_service.get_company("00000001")

            _assert_error(exc_info, "not_found", status_code=404)

        @responses.activate
        def test_rejects_a_profile_for_a_different_company(self, api_url):
            responses.get(f"{api_url}/company/00000001", json=_profile("00000002"))

            with pytest.raises(CompaniesHouseError) as exc_info:
                companies_house_service.get_company("00000001")

            _assert_error(exc_info, "invalid_payload", status_code=200)

        @responses.activate
        @pytest.mark.parametrize(
            "payload",
            [
                pytest.param({"company_number": "00000001"}, id="missing name"),
                pytest.param(_profile(company_name="   "), id="blank name"),
            ],
        )
        def test_rejects_payloads_missing_required_fields(self, api_url, payload):
            responses.get(f"{api_url}/company/00000001", json=payload)

            with pytest.raises(CompaniesHouseError) as exc_info:
                companies_house_service.get_company("00000001")

            _assert_error(exc_info, "invalid_payload", status_code=200, cause=ValidationError)
