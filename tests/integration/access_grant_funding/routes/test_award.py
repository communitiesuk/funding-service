from datetime import date

from bs4 import BeautifulSoup
from flask import url_for

from app import CollectionStatusEnum, GrantStatusEnum
from app.common.data.types import CollectionType, SubmissionModeEnum
from tests.utils import get_h1_text


class TestListAwardCollections:
    def test_get_list_award_collections(self, authenticated_grant_recipient_member_client, factories):
        grant = authenticated_grant_recipient_member_client.grant
        organisation = authenticated_grant_recipient_member_client.organisation
        grant.status = GrantStatusEnum.LIVE

        factories.collection.create(
            grant=grant,
            type=CollectionType.APPLICATION,
            status=CollectionStatusEnum.OPEN,
            submission_period_start_date=date(2025, 11, 1),
            submission_period_end_date=date(2026, 2, 28),
        )
        factories.collection.create(
            grant=grant,
            type=CollectionType.BASELINE,
            status=CollectionStatusEnum.OPEN,
            submission_period_start_date=date(2025, 11, 1),
            submission_period_end_date=date(2026, 2, 28),
        )

        response = authenticated_grant_recipient_member_client.get(
            url_for(
                "access_grant_funding.list_award_collections",
                organisation_id=organisation.id,
                grant_id=grant.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == organisation.name
        table_elem = soup.find("table", class_="govuk-table")
        assert table_elem is not None
        assert len(table_elem.find_all("tr")) == 3  # header + 2 data rows

    def test_does_not_show_monitoring_reports(self, authenticated_grant_recipient_member_client, factories):
        grant = authenticated_grant_recipient_member_client.grant
        organisation = authenticated_grant_recipient_member_client.organisation
        grant.status = GrantStatusEnum.LIVE

        factories.collection.create(
            grant=grant,
            type=CollectionType.MONITORING_REPORT,
            status=CollectionStatusEnum.OPEN,
        )
        factories.collection.create(
            grant=grant,
            type=CollectionType.APPLICATION,
            status=CollectionStatusEnum.OPEN,
        )

        response = authenticated_grant_recipient_member_client.get(
            url_for(
                "access_grant_funding.list_award_collections",
                organisation_id=organisation.id,
                grant_id=grant.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        table_elem = soup.find("table", class_="govuk-table")
        assert table_elem is not None
        assert len(table_elem.find_all("tr")) == 2  # header + 1 data row (no monitoring report)

    def test_shows_empty_state_when_no_award_collections(self, authenticated_grant_recipient_member_client, factories):
        grant = authenticated_grant_recipient_member_client.grant
        organisation = authenticated_grant_recipient_member_client.organisation
        grant.status = GrantStatusEnum.LIVE

        response = authenticated_grant_recipient_member_client.get(
            url_for(
                "access_grant_funding.list_award_collections",
                organisation_id=organisation.id,
                grant_id=grant.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "There are no required collections for this grant." in soup.text

    def test_only_shows_open_and_closed_collections_for_regular_users(
        self, authenticated_grant_recipient_member_client, factories
    ):
        grant = authenticated_grant_recipient_member_client.grant
        organisation = authenticated_grant_recipient_member_client.organisation
        grant.status = GrantStatusEnum.LIVE

        factories.collection.create(
            grant=grant,
            type=CollectionType.APPLICATION,
            status=CollectionStatusEnum.OPEN,
        )
        factories.collection.create(
            grant=grant,
            type=CollectionType.APPLICATION,
            status=CollectionStatusEnum.DRAFT,
        )
        factories.collection.create(
            grant=grant,
            type=CollectionType.BASELINE,
            status=CollectionStatusEnum.SCHEDULED,
        )

        response = authenticated_grant_recipient_member_client.get(
            url_for(
                "access_grant_funding.list_award_collections",
                organisation_id=organisation.id,
                grant_id=grant.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        table_elem = soup.find("table", class_="govuk-table")
        assert table_elem is not None
        assert len(table_elem.find_all("tr")) == 2  # header + 1 (only OPEN)

    def test_shows_grant_recipient_status(self, authenticated_grant_recipient_member_client, factories):
        grant = authenticated_grant_recipient_member_client.grant
        organisation = authenticated_grant_recipient_member_client.organisation
        grant.status = GrantStatusEnum.LIVE

        factories.collection.create(
            grant=grant,
            type=CollectionType.APPLICATION,
            status=CollectionStatusEnum.OPEN,
        )

        response = authenticated_grant_recipient_member_client.get(
            url_for(
                "access_grant_funding.list_award_collections",
                organisation_id=organisation.id,
                grant_id=grant.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Allocated" in soup.text

    def test_not_grant_recipient_returns_403(self, authenticated_grant_recipient_member_client, factories):
        organisation = authenticated_grant_recipient_member_client.organisation
        grant = factories.grant.create(organisation=organisation, status=GrantStatusEnum.LIVE)
        factories.grant_recipient.create(grant=grant, organisation=organisation)

        response = authenticated_grant_recipient_member_client.get(
            url_for(
                "access_grant_funding.list_award_collections",
                organisation_id=organisation.id,
                grant_id=grant.id,
            )
        )

        assert response.status_code == 403

    def test_shows_submission_status_for_single_submission_collection(
        self, authenticated_grant_recipient_member_client, factories
    ):
        grant_recipient = authenticated_grant_recipient_member_client.grant_recipient
        grant = authenticated_grant_recipient_member_client.grant
        organisation = authenticated_grant_recipient_member_client.organisation
        grant.status = GrantStatusEnum.LIVE

        collection = factories.collection.create(
            grant=grant,
            type=CollectionType.APPLICATION,
            status=CollectionStatusEnum.OPEN,
        )
        factories.submission.create(
            collection=collection,
            grant_recipient=grant_recipient,
            mode=SubmissionModeEnum.LIVE,
        )

        response = authenticated_grant_recipient_member_client.get(
            url_for(
                "access_grant_funding.list_award_collections",
                organisation_id=organisation.id,
                grant_id=grant.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Ready to submit" in soup.text
