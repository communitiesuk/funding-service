from app.access_grant_funding.mock_registries import (
    CHARITY_COMMISSION_REFERENCES,
    COMPANIES_HOUSE_REFERENCES,
    RegisteredOrganisation,
    lookup_charity,
    lookup_company,
)


class TestLookupCompany:
    def test_finds_a_known_reference(self):
        assert lookup_company("01234567") == RegisteredOrganisation(
            "01234567", "Northern Regeneration Partners Limited"
        )

    def test_normalises_whitespace_and_case(self):
        assert lookup_company("  sc456789  ") == RegisteredOrganisation(
            "SC456789", "Clydeside Enterprise Company Limited"
        )

    def test_returns_none_for_an_unknown_reference(self):
        assert lookup_company("00000000") is None

    def test_does_not_find_a_charity_reference(self):
        assert lookup_company("1122334") is None


class TestLookupCharity:
    def test_finds_a_known_reference(self):
        assert lookup_charity("1122334") == RegisteredOrganisation("1122334", "The Riverside Youth Trust")

    def test_normalises_whitespace_and_case(self):
        assert lookup_charity("  209078  ") == RegisteredOrganisation("209078", "Midlands Community Foundation")

    def test_returns_none_for_an_unknown_reference(self):
        assert lookup_charity("0000000") is None

    def test_does_not_find_a_company_reference(self):
        assert lookup_charity("01234567") is None


def test_reference_lists_match_the_lookups():
    assert all(lookup_company(reference) is not None for reference in COMPANIES_HOUSE_REFERENCES)
    assert all(lookup_charity(reference) is not None for reference in CHARITY_COMMISSION_REFERENCES)
