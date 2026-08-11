import uuid

import pytest
from _pytest.fixtures import FixtureRequest
from bs4 import BeautifulSoup
from flask import url_for

from app.common.data.types import (
    CollectionStatusEnum,
    CollectionType,
    DataSourceType,
    GrantStatusEnum,
)
from tests.utils import (
    AnyStringMatching,
    page_has_link,
)


class TestListReports:
    def test_404(self, authenticated_grant_member_client):
        response = authenticated_grant_member_client.get(
            url_for("deliver_grant_funding.list_reports", grant_id=uuid.uuid4())
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_edit",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_grant_member_get_no_reports(self, request: FixtureRequest, client_fixture: str, can_edit: bool, factories):
        client = request.getfixturevalue(client_fixture)

        response = client.get(url_for("deliver_grant_funding.list_reports", grant_id=client.grant.id))
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert client.grant.name in soup.text

        expected_links = [
            ("Create a report", AnyStringMatching(r"/deliver/grant/[a-z0-9-]{36}/reports/set-up")),
        ]
        for expected_link in expected_links:
            button = page_has_link(soup, expected_link[0])
            assert (button is not None) is can_edit

            if can_edit:
                assert button.get("href") == expected_link[1]

    @pytest.mark.parametrize(
        "client_fixture, can_edit",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
            ("authenticated_platform_admin_client", True),
        ),
    )
    def test_grant_member_get_with_reports(
        self, request: FixtureRequest, client_fixture: str, can_edit: bool, factories
    ):
        client = request.getfixturevalue(client_fixture)
        grant = client.grant or factories.grant.create()
        factories.collection.create(grant=grant)

        response = client.get(url_for("deliver_grant_funding.list_reports", grant_id=grant.id))
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert grant.name in soup.text

        test_submission_links = page_has_link(soup, "0 test submissions")
        assert test_submission_links is not None
        assert test_submission_links.get("href") == AnyStringMatching(
            r"/deliver/grant/[a-z0-9-]{36}/reports/[a-z0-9-]{36}/submissions/test"
        )

        live_submissions_links = page_has_link(soup, "0 live submissions")
        assert live_submissions_links is not None
        assert live_submissions_links.get("href") == AnyStringMatching(
            r"/deliver/grant/[a-z0-9-]{36}/reports/[a-z0-9-]{36}/submissions/live"
        )

        expected_links = [
            (
                "Create another report",
                AnyStringMatching(r"/deliver/grant/[a-z0-9-]{36}/reports/set-up"),
            ),
            (
                "Add sections",
                AnyStringMatching(r"/deliver/grant/[a-z0-9-]{36}/reports/[a-z0-9-]{36}/add-section"),
            ),
        ]
        for expected_link in expected_links:
            link = page_has_link(soup, expected_link[0])
            assert (link is not None) is can_edit

            if can_edit:
                assert link.get("href") == expected_link[1]

    @pytest.mark.parametrize(
        "client_fixture, can_edit",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_card_shows_settings_link(self, request: FixtureRequest, client_fixture: str, can_edit: bool, factories):
        client = request.getfixturevalue(client_fixture)
        factories.collection.create(grant=client.grant)

        response = client.get(url_for("deliver_grant_funding.list_reports", grant_id=client.grant.id))
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        settings_link = page_has_link(soup, "Manage settings" if can_edit else "View settings")
        assert settings_link is not None
        assert settings_link.get("href") == AnyStringMatching(
            r"/deliver/grant/[a-z0-9-]{36}/reports/[a-z0-9-]{36}/settings"
        )

    def test_get_shows_missing_data_tag_for_data_sets(self, authenticated_platform_admin_client, factories):
        grant = factories.grant.create()
        report = factories.collection.create(grant=grant, name="Test Report")
        report_2 = factories.collection.create(grant=grant, name="Test Report 2")

        factories.grant_recipient.create_batch(3, grant=grant)
        factories.data_source.create(
            name="Allocations Data",
            type=DataSourceType.GRANT_RECIPIENT,
            grant=grant,
            collection=report,
            create_gr_org_items=True,
            create_gr_org_items__data=[111, 222, 333],
        )
        factories.data_source.create(
            name="Organisation Data",
            type=DataSourceType.GRANT_RECIPIENT,
            grant=grant,
            collection=report_2,
            create_gr_org_items=True,
            create_gr_org_items__data=[111, 222, None],
        )

        response = authenticated_platform_admin_client.get(
            url_for(
                "deliver_grant_funding.list_reports",
                grant_id=grant.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        data_missing_tags = soup.select(".govuk-tag")
        tag_texts = [tag.text.strip() for tag in data_missing_tags]
        assert tag_texts.count("Data missing") == 1

    @pytest.mark.parametrize(
        "status, number_of_open_collections, expected",
        (
            (GrantStatusEnum.DRAFT, 0, "Reports cannot be published until the grant is live."),
            (GrantStatusEnum.LIVE, 0, "There are no reports live."),
            (GrantStatusEnum.LIVE, 1, None),
        ),
    )
    def test_get_reports_grant_status_description(
        self,
        factories,
        authenticated_platform_admin_client,
        status: GrantStatusEnum,
        number_of_open_collections: int,
        expected: str,
    ):
        grant = factories.grant.create(status=status)

        factories.collection.create_batch(
            number_of_open_collections,
            grant=grant,
            type=CollectionType.MONITORING_REPORT,
            status=CollectionStatusEnum.OPEN,
        )

        response = authenticated_platform_admin_client.get(
            url_for("deliver_grant_funding.list_reports", grant_id=grant.id)
        )

        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert grant.name in soup.text

        if expected is not None:
            assert soup.find("span", {"data-testid": "grant-status-description"}).text.strip() == expected
        else:
            assert soup.find("span", {"data-testid": "grant-status-description"}) is None
