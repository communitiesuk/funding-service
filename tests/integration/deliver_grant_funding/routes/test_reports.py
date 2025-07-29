import uuid

import pytest
from _pytest.fixtures import FixtureRequest
from bs4 import BeautifulSoup
from flask import url_for

from app.deliver_grant_funding.forms import SetUpReportForm
from tests.utils import AnyStringMatching, page_has_button, page_has_error, page_has_link


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
            ("Add a monitoring report", AnyStringMatching(r"/grant/[a-z0-9-]{36}/set-up-report")),
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

        expected_links = [
            ("Add another monitoring report", AnyStringMatching(r"/grant/[a-z0-9-]{36}/set-up-report")),
            ("Add tasks", "#"),
            ("Manage", "#"),
        ]
        for expected_link in expected_links:
            link = page_has_link(soup, expected_link[0])
            assert (link is not None) is can_edit

            if can_edit:
                assert link.get("href") == expected_link[1]


class TestSetUpReport:
    def test_404(self, authenticated_grant_member_client):
        response = authenticated_grant_member_client.get(
            url_for("deliver_grant_funding.set_up_report", grant_id=uuid.uuid4())
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get(self, request: FixtureRequest, client_fixture: str, can_access: bool, factories):
        client = request.getfixturevalue(client_fixture)
        factories.collection.create(grant=client.grant)

        response = client.get(url_for("deliver_grant_funding.set_up_report", grant_id=client.grant.id))

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert page_has_button(soup, "Continue and set up report")

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_post(self, request: FixtureRequest, client_fixture: str, can_access: bool, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        assert len(client.grant.reports) == 0

        form = SetUpReportForm(data={"name": "Test monitoring report"})
        response = client.post(
            url_for("deliver_grant_funding.set_up_report", grant_id=client.grant.id),
            data=form.data,
            follow_redirects=False,
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 302
            assert response.location == AnyStringMatching("/grant/[a-z0-9-]{36}/reports")

            assert len(client.grant.reports) == 1
            assert client.grant.reports[0].name == "Test monitoring report"
            assert client.grant.reports[0].created_by == client.user

    def test_post_duplicate_report_name(self, authenticated_grant_admin_client, factories):
        factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Monitoring report")

        form = SetUpReportForm(data={"name": "Monitoring report"})
        response = authenticated_grant_admin_client.post(
            url_for("deliver_grant_funding.set_up_report", grant_id=authenticated_grant_admin_client.grant.id),
            data=form.data,
        )
        soup = BeautifulSoup(response.data, "html.parser")

        assert response.status_code == 200
        assert page_has_error(soup, "A report with this name already exists")
