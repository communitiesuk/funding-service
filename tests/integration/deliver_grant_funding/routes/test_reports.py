import uuid

import pytest
from _pytest.fixtures import FixtureRequest
from bs4 import BeautifulSoup
from flask import url_for

from app.common.data.models import (
    Collection,
)
from app.common.data.types import (
    CollectionStatusEnum,
    CollectionType,
    DataSourceType,
    GrantStatusEnum,
    SubmissionModeEnum,
)
from app.common.forms import GenericConfirmDeletionForm
from tests.utils import AnyStringMatching, get_form_data, page_has_button, page_has_link


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
            ("Add a monitoring report", AnyStringMatching(r"/deliver/grant/[a-z0-9-]{36}/reports/set-up")),
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
                "Add another monitoring report",
                AnyStringMatching(r"/deliver/grant/[a-z0-9-]{36}/reports/set-up"),
            ),
            (
                "Add sections",
                AnyStringMatching(r"/deliver/grant/[a-z0-9-]{36}/reports/[a-z0-9-]{36}/add-section"),
            ),
            (
                "Change name",
                AnyStringMatching(r"/deliver/grant/[a-z0-9-]{36}/reports/[a-z0-9-]{36}/change-name"),
            ),
            ("Delete", AnyStringMatching(r"/deliver/grant/[a-z0-9-]{36}/reports\?delete")),
        ]
        for expected_link in expected_links:
            link = page_has_link(soup, expected_link[0])
            assert (link is not None) is can_edit

            if can_edit:
                assert link.get("href") == expected_link[1]

    def test_get_hides_delete_link_with_submissions(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        factories.submission.create(collection=collection, mode=SubmissionModeEnum.LIVE)

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.change_collection_name",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert not page_has_link(soup, "Delete")

    def test_get_with_delete_parameter_no_submissions(self, authenticated_grant_admin_client, factories):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.list_reports",
                grant_id=authenticated_grant_admin_client.grant.id,
                delete=report.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_button(soup, "Yes, delete this report")

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
        "client_fixture, can_delete",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_post_delete(self, request: FixtureRequest, client_fixture: str, can_delete: bool, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        report = factories.collection.create(grant=client.grant, name="Test Report")

        form = GenericConfirmDeletionForm(data={"confirm_deletion": True})
        response = client.post(
            url_for("deliver_grant_funding.list_reports", grant_id=client.grant.id, delete=report.id),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/reports$")

        deleted_report = db_session.get(Collection, report.id)
        assert (deleted_report is None) == can_delete

    @pytest.mark.parametrize(
        "collection_status", [status for status in CollectionStatusEnum if status != CollectionStatusEnum.DRAFT]
    )
    @pytest.mark.parametrize(
        "client_fixture", ("authenticated_grant_admin_client", "authenticated_platform_admin_client")
    )
    def test_get_no_change_or_delete_links_when_report_not_draft(
        self, factories, collection_status, client_fixture, request
    ):
        client = request.getfixturevalue(client_fixture)
        grant = client.grant if client.grant else factories.grant.create()
        factories.collection.create(grant=grant, name="Test Report", status=collection_status)

        response = client.get(url_for("deliver_grant_funding.list_reports", grant_id=grant.id))

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")

        change_name_link = page_has_link(soup, "Change name")
        delete_link = page_has_link(soup, "Delete")

        assert change_name_link is None
        assert delete_link is None

    @pytest.mark.parametrize(
        "status, expected",
        (
            (GrantStatusEnum.DRAFT, "Reports cannot be published until the grant is live."),
            (GrantStatusEnum.LIVE, "There are no reports live."),
        ),
    )
    def test_get_reports_grant_status_description(
        self,
        factories,
        authenticated_platform_admin_client,
        status: GrantStatusEnum,
        expected: str,
    ):
        grant = factories.grant.create(status=status)

        response = authenticated_platform_admin_client.get(
            url_for("deliver_grant_funding.list_reports", grant_id=grant.id)
        )

        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert grant.name in soup.text

        assert expected in " ".join(soup.text.split())
