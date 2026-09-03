import datetime
import logging
import uuid

import pytest
from bs4 import BeautifulSoup
from flask import url_for
from flask_login import login_user
from sqlalchemy import select

from app.access_grant_funding.forms import EligibleOrganisationSelectionForm
from app.common.collections.forms import build_question_form
from app.common.data.interfaces.collections import add_component_eligibility
from app.common.data.models import GrantRecipient, Submission
from app.common.data.models_audit import AuditEvent as AuditEventModel
from app.common.data.models_user import Invitation, User, UserRole
from app.common.data.types import (
    AuditEventType,
    AuthMethodEnum,
    CollectionStatusEnum,
    GrantRecipientModeEnum,
    GrantRecipientStatusEnum,
    GrantStatusEnum,
    OrganisationModeEnum,
    QuestionDataType,
    RoleEnum,
    SubmissionEventType,
    SubmissionModeEnum,
)
from app.common.expressions import ExpressionContext
from app.common.expressions.managed import GreaterThan
from app.common.expressions.references import ExpressionReference
from app.common.helpers.collections import get_or_create_unclaimed_submission
from app.common.helpers.feature_flags import FeatureFlags
from tests.utils import get_form_data, get_h1_text, get_h2_text


def enable_access_user_management_flag(client):
    with client.session_transaction() as session:
        session[FeatureFlags.ACCESS_GRANT_FUNDING_USER_MANAGEMENT.name] = "on"


class TestIndex:
    def test_get_index_just_one_grant_recipient_redirects(self, authenticated_grant_recipient_member_client):
        response = authenticated_grant_recipient_member_client.get(url_for("access_grant_funding.index"))
        assert response.status_code == 302
        assert response.location == (
            f"/access/organisation/{authenticated_grant_recipient_member_client.organisation.id}"
            f"/grants/{authenticated_grant_recipient_member_client.grant.id}/forms"
        )

    def test_get_index_two_grant_recipients_same_org_redirects(
        self, authenticated_grant_recipient_member_client, factories
    ):
        user = authenticated_grant_recipient_member_client.user
        grant = factories.grant.create()
        organisation = authenticated_grant_recipient_member_client.organisation

        factories.grant_recipient.create(grant=grant, organisation=organisation)
        factories.user_role.create(
            user=user, organisation=organisation, grant=grant, permissions=[RoleEnum.DATA_PROVIDER]
        )

        response = authenticated_grant_recipient_member_client.get(url_for("access_grant_funding.index"))
        assert response.status_code == 302
        assert (
            response.location
            == f"/access/organisation/{authenticated_grant_recipient_member_client.organisation.id}/grants"
        )

    def test_get_index_two_grant_recipient_orgs_redirects(self, authenticated_grant_recipient_member_client, factories):
        user = authenticated_grant_recipient_member_client.user
        grant = authenticated_grant_recipient_member_client.grant
        organisation = factories.organisation.create()

        factories.grant_recipient.create(grant=grant, organisation=organisation)
        factories.user_role.create(
            user=user, organisation=organisation, grant=grant, permissions=[RoleEnum.DATA_PROVIDER]
        )

        response = authenticated_grant_recipient_member_client.get(url_for("access_grant_funding.index"))
        assert response.status_code == 302
        assert response.location == "/access/organisations"

    def test_get_index_403_if_no_permissions(self, authenticated_no_role_client):
        response = authenticated_no_role_client.get(url_for("access_grant_funding.index"), follow_redirects=True)
        assert response.status_code == 403


class TestListGrants:
    def test_get_list_grants_404(self, authenticated_grant_recipient_member_client, factories, client):
        response = authenticated_grant_recipient_member_client.get(
            url_for("access_grant_funding.list_grants", organisation_id=uuid.uuid4())
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_recipient_member_client", True),
        ),
    )
    def test_get_list_grants(self, factories, client, request, client_fixture, can_access):
        client = request.getfixturevalue(client_fixture)
        organisation = client.organisation or factories.organisation.create(can_manage_grants=False)
        response = client.get(
            url_for(
                "access_grant_funding.list_grants",
                organisation_id=organisation.id,
            )
        )
        if can_access:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert get_h1_text(soup) == "Select a grant"
        else:
            assert response.status_code == 403


class TestListOrganisations:
    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_recipient_member_client", True),
        ),
    )
    def test_get_list_organisations(self, factories, client, request, client_fixture, can_access):
        client = request.getfixturevalue(client_fixture)
        if can_access:
            user = client.user
            grant = client.grant
            second_organisation = factories.organisation.create()
            factories.grant_recipient.create(organisation=second_organisation, grant=grant)
            factories.user_role.create(
                user=user, permissions=[RoleEnum.MEMBER], organisation=second_organisation, grant=grant
            )
        response = client.get(url_for("access_grant_funding.list_organisations"))
        if can_access:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert get_h1_text(soup) == "Select an organisation"
        else:
            assert response.status_code == 403

    def test_get_list_organisations_redirects_when_only_one_org(self, authenticated_grant_recipient_member_client):
        organisation = authenticated_grant_recipient_member_client.organisation
        response = authenticated_grant_recipient_member_client.get(
            url_for("access_grant_funding.list_organisations"), follow_redirects=False
        )
        assert response.status_code == 302
        assert response.location == url_for("access_grant_funding.list_grants", organisation_id=organisation.id)


class TestListGrantTeam:
    def test_get_list_grant_team(self, authenticated_grant_recipient_data_provider_client, factories):
        client = authenticated_grant_recipient_data_provider_client
        enable_access_user_management_flag(client)
        organisation = authenticated_grant_recipient_data_provider_client.organisation
        grant = authenticated_grant_recipient_data_provider_client.grant
        other_user = factories.user.create(name="Other User")
        factories.user_role.create(
            user=other_user, organisation=organisation, grant=grant, permissions=[RoleEnum.DATA_PROVIDER]
        )

        response = authenticated_grant_recipient_data_provider_client.get(
            url_for("access_grant_funding.list_grant_team", organisation_id=organisation.id, grant_id=grant.id)
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Team"
        assert any(
            authenticated_grant_recipient_data_provider_client.user.name in td.get_text() for td in soup.find_all("td")
        )
        assert any("Action" in th.get_text() for th in soup.find_all("th"))

        current_user_row = next(
            row
            for row in soup.find_all("tr")
            if authenticated_grant_recipient_data_provider_client.user.name in row.get_text()
        )
        assert "Remove" not in current_user_row.get_text()

        remove_link = next((link for link in soup.find_all("a") if "Remove" in link.get_text()), None)
        assert remove_link is not None
        assert remove_link.get("href") == url_for(
            "access_grant_funding.remove_grant_team_member",
            organisation_id=organisation.id,
            grant_id=grant.id,
            user_id=other_user.id,
        )

    def test_get_list_grant_team_shows_pending_invitations(
        self, authenticated_grant_recipient_data_provider_client, factories
    ):
        client = authenticated_grant_recipient_data_provider_client
        factories.invitation.create(
            email="user@hastings.gov.uk",
            name="My User",
            organisation=client.organisation,
            grant=client.grant,
            permissions=[RoleEnum.DATA_PROVIDER],
        )
        factories.invitation.create(
            email="claimed@hastings.gov.uk",
            name="Claimed Person",
            organisation=client.organisation,
            grant=client.grant,
            permissions=[RoleEnum.DATA_PROVIDER],
            is_claimed=True,
        )

        response = client.get(
            url_for(
                "access_grant_funding.list_grant_team", organisation_id=client.organisation.id, grant_id=client.grant.id
            )
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Invited" in [h2.get_text(strip=True) for h2 in soup.find_all("h2")]
        assert "Team members have 7 days to accept their invitation." in soup.get_text()
        invited_row = next(row for row in soup.find_all("tr") if "user@hastings.gov.uk" in row.get_text())
        assert "My User" in invited_row.get_text()
        assert "Can edit and submit" in invited_row.get_text()
        assert "claimed@hastings.gov.uk" not in response.text

    def test_get_list_grant_team_hides_invited_section_without_pending_invitations(
        self, authenticated_grant_recipient_data_provider_client
    ):
        client = authenticated_grant_recipient_data_provider_client

        response = client.get(
            url_for(
                "access_grant_funding.list_grant_team", organisation_id=client.organisation.id, grant_id=client.grant.id
            )
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Invited" not in [h2.get_text(strip=True) for h2 in soup.find_all("h2")]

    def test_get_list_grant_team_shows_multiple_permissions(
        self, authenticated_grant_recipient_data_provider_client, factories
    ):
        user = authenticated_grant_recipient_data_provider_client.user
        organisation = authenticated_grant_recipient_data_provider_client.organisation
        grant = authenticated_grant_recipient_data_provider_client.grant

        factories.user_role.create(user=user, organisation=organisation, grant=None, permissions=[RoleEnum.CERTIFIER])

        response = authenticated_grant_recipient_data_provider_client.get(
            url_for("access_grant_funding.list_grant_team", organisation_id=organisation.id, grant_id=grant.id)
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Team"
        assert any("Can certify" in td.get_text() for td in soup.find_all("td"))
        assert any("Can edit and submit" in td.get_text() for td in soup.find_all("td"))

    def test_add_team_member_button_shown_for_data_provider_when_flag_enabled(
        self, authenticated_grant_recipient_data_provider_client
    ):
        client = authenticated_grant_recipient_data_provider_client
        enable_access_user_management_flag(client)

        response = client.get(
            url_for(
                "access_grant_funding.list_grant_team", organisation_id=client.organisation.id, grant_id=client.grant.id
            )
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        add_team_member_link = soup.find(
            "a",
            href=url_for(
                "access_grant_funding.add_grant_team_member",
                organisation_id=client.organisation.id,
                grant_id=client.grant.id,
            ),
        )
        assert add_team_member_link is not None
        assert add_team_member_link.get_text(strip=True) == "Add team member"
        h2_texts = [h2.get_text(strip=True) for h2 in soup.find_all("h2")]
        assert "Certifier access" in h2_texts
        assert "Changing access and permissions" not in h2_texts

    def test_add_team_member_button_hidden_when_flag_disabled(self, authenticated_grant_recipient_data_provider_client):
        client = authenticated_grant_recipient_data_provider_client

        response = client.get(
            url_for(
                "access_grant_funding.list_grant_team", organisation_id=client.organisation.id, grant_id=client.grant.id
            )
        )
        assert response.status_code == 200
        assert "Add team member" not in response.text
        soup = BeautifulSoup(response.data, "html.parser")
        h2_texts = [h2.get_text(strip=True) for h2 in soup.find_all("h2")]
        assert "Changing access and permissions" in h2_texts
        assert "Certifier access" not in h2_texts
        assert not any("Action" in th.get_text() for th in soup.find_all("th"))
        assert "Remove" not in response.text

    def test_add_team_member_button_hidden_for_member_when_flag_enabled(
        self, authenticated_grant_recipient_member_client
    ):
        client = authenticated_grant_recipient_member_client
        enable_access_user_management_flag(client)

        response = client.get(
            url_for(
                "access_grant_funding.list_grant_team", organisation_id=client.organisation.id, grant_id=client.grant.id
            )
        )
        assert response.status_code == 200
        assert "Add team member" not in response.text
        soup = BeautifulSoup(response.data, "html.parser")
        assert not any("Action" in th.get_text() for th in soup.find_all("th"))

    def test_remove_link_hidden_for_org_wide_data_provider(
        self, authenticated_grant_recipient_data_provider_client, factories
    ):
        client = authenticated_grant_recipient_data_provider_client
        enable_access_user_management_flag(client)
        other_user = factories.user.create(name="Other User")
        factories.user_role.create(
            user=other_user,
            organisation=client.organisation,
            grant=None,
            permissions=[RoleEnum.DATA_PROVIDER],
        )

        response = client.get(
            url_for(
                "access_grant_funding.list_grant_team",
                organisation_id=client.organisation.id,
                grant_id=client.grant.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        other_user_row = next(row for row in soup.find_all("tr") if other_user.name in row.get_text())
        assert "Remove" not in other_user_row.get_text()

    def test_remove_link_hidden_for_certifier_only_user(
        self, authenticated_grant_recipient_data_provider_client, factories
    ):
        client = authenticated_grant_recipient_data_provider_client
        enable_access_user_management_flag(client)
        certifier = factories.user.create(name="Certifier User")
        factories.user_role.create(
            user=certifier,
            organisation=client.organisation,
            grant=client.grant,
            permissions=[RoleEnum.CERTIFIER],
        )

        response = client.get(
            url_for(
                "access_grant_funding.list_grant_team",
                organisation_id=client.organisation.id,
                grant_id=client.grant.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        certifier_row = next(row for row in soup.find_all("tr") if certifier.name in row.get_text())
        assert "Remove" not in certifier_row.get_text()

    def test_remove_link_shown_for_user_with_edit_and_certify_permissions(
        self, authenticated_grant_recipient_data_provider_client, factories
    ):
        client = authenticated_grant_recipient_data_provider_client
        enable_access_user_management_flag(client)
        user = factories.user.create(name="Edit And Certify User")
        factories.user_role.create(
            user=user,
            organisation=client.organisation,
            grant=client.grant,
            permissions=[RoleEnum.DATA_PROVIDER, RoleEnum.CERTIFIER],
        )

        response = client.get(
            url_for(
                "access_grant_funding.list_grant_team",
                organisation_id=client.organisation.id,
                grant_id=client.grant.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        user_row = next(row for row in soup.find_all("tr") if user.name in row.get_text())
        remove_link = next((link for link in user_row.find_all("a") if "Remove" in link.get_text()), None)
        assert remove_link is not None
        assert remove_link.get("href") == url_for(
            "access_grant_funding.remove_grant_team_member",
            organisation_id=client.organisation.id,
            grant_id=client.grant.id,
            user_id=user.id,
        )


class TestAddGrantTeamMember:
    def test_get_returns_404_when_flag_disabled(self, authenticated_grant_recipient_data_provider_client):
        client = authenticated_grant_recipient_data_provider_client

        response = client.get(
            url_for(
                "access_grant_funding.add_grant_team_member",
                organisation_id=client.organisation.id,
                grant_id=client.grant.id,
            )
        )
        assert response.status_code == 404

    def test_get_forbidden_for_member(self, authenticated_grant_recipient_member_client):
        client = authenticated_grant_recipient_member_client
        enable_access_user_management_flag(client)

        response = client.get(
            url_for(
                "access_grant_funding.add_grant_team_member",
                organisation_id=client.organisation.id,
                grant_id=client.grant.id,
            )
        )
        assert response.status_code == 403

    def test_get_forbidden_for_certifier(self, authenticated_grant_recipient_certifier_client):
        client = authenticated_grant_recipient_certifier_client
        enable_access_user_management_flag(client)

        response = client.get(
            url_for(
                "access_grant_funding.add_grant_team_member",
                organisation_id=client.organisation.id,
                grant_id=client.grant.id,
            )
        )
        assert response.status_code == 403

    def test_get_shows_form(self, authenticated_grant_recipient_data_provider_client):
        client = authenticated_grant_recipient_data_provider_client
        enable_access_user_management_flag(client)

        response = client.get(
            url_for(
                "access_grant_funding.add_grant_team_member",
                organisation_id=client.organisation.id,
                grant_id=client.grant.id,
            )
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Add team member details"
        assert (
            f"This team member will be able to edit and submit reports and forms for {client.grant.name}."
            in soup.get_text()
        )
        assert soup.find("input", id="full_name") is not None
        assert soup.find("input", id="email_address") is not None

    def test_post_adds_existing_user_to_team(
        self, authenticated_grant_recipient_data_provider_client, factories, db_session, mock_notification_service_calls
    ):
        client = authenticated_grant_recipient_data_provider_client
        enable_access_user_management_flag(client)
        existing_user = factories.user.create(name="Local user", email="user@local.gov.uk")
        grant_recipient = client.grant_recipient

        response = client.post(
            url_for(
                "access_grant_funding.add_grant_team_member",
                organisation_id=client.organisation.id,
                grant_id=client.grant.id,
            ),
            data={"full_name": "Local user", "email_address": "user@local.gov.uk"},
        )
        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.list_grant_team", organisation_id=client.organisation.id, grant_id=client.grant.id
        )

        user_role = db_session.scalar(select(UserRole).where(UserRole.user_id == existing_user.id))
        assert user_role.organisation_id == client.organisation.id
        assert user_role.grant_id == client.grant.id
        assert RoleEnum.DATA_PROVIDER in user_role.permissions

        audit_event = db_session.scalars(select(AuditEventModel)).one()
        assert audit_event.event_type == AuditEventType.USER_MANAGEMENT

        assert len(mock_notification_service_calls) == 1
        notification_call = mock_notification_service_calls[0]
        assert notification_call.args == ("user@local.gov.uk", "8741f1bd-08b0-4bf3-a9d4-eff744e12350")
        assert notification_call.kwargs["personalisation"] == {
            "organisation_name": client.organisation.name,
            "grant_name": client.grant.name,
            "is_test_data": "no",
            "grant_submission_url": (
                "http://funding.communities.gov.localhost:8080/access/organisation/"
                f"{grant_recipient.organisation.id}/grants/{grant_recipient.grant.id}/forms"
            ),
            "email_address": "user@local.gov.uk",
        }

        team_page = client.get(response.location)
        soup = BeautifulSoup(team_page.data, "html.parser")
        banner = soup.find(class_="govuk-notification-banner")
        assert banner is not None
        assert "Team member added" in banner.get_text()
        assert f"Local user can now edit and submit for {client.grant.name}." in banner.get_text()

    def test_post_does_not_update_the_name_of_an_existing_user(
        self, authenticated_grant_recipient_data_provider_client, factories, db_session, mock_notification_service_calls
    ):
        client = authenticated_grant_recipient_data_provider_client
        enable_access_user_management_flag(client)
        existing_user = factories.user.create(name="Local user", email="user@local.gov.uk")

        response = client.post(
            url_for(
                "access_grant_funding.add_grant_team_member",
                organisation_id=client.organisation.id,
                grant_id=client.grant.id,
            ),
            data={"full_name": "Local user updated", "email_address": "user@local.gov.uk"},
        )
        assert response.status_code == 302

        db_session.refresh(existing_user)
        assert existing_user.name == "Local user"

        team_page = client.get(response.location)
        banner = BeautifulSoup(team_page.data, "html.parser").find(class_="govuk-notification-banner")
        assert "Local user can now edit and submit" in banner.get_text()
        assert "Local user updated" not in banner.get_text()

    def test_post_returns_500_when_person_is_already_a_team_member(
        self, authenticated_grant_recipient_data_provider_client, db_session
    ):
        client = authenticated_grant_recipient_data_provider_client
        enable_access_user_management_flag(client)

        response = client.post(
            url_for(
                "access_grant_funding.add_grant_team_member",
                organisation_id=client.organisation.id,
                grant_id=client.grant.id,
            ),
            data={"full_name": client.user.name, "email_address": client.user.email},
        )
        assert response.status_code == 500
        assert db_session.scalars(select(AuditEventModel)).all() == []

    @pytest.mark.parametrize("certifier_is_org_wide", [True, False])
    def test_post_returns_500_and_does_not_grant_edit_and_submit_to_a_certifier(
        self, authenticated_grant_recipient_data_provider_client, factories, db_session, certifier_is_org_wide
    ):
        client = authenticated_grant_recipient_data_provider_client
        enable_access_user_management_flag(client)
        certifier = factories.user.create(name="Sarah Certifier", email="scertifier@hastings.gov.uk")
        factories.user_role.create(
            user=certifier,
            permissions=[RoleEnum.MEMBER, RoleEnum.CERTIFIER],
            organisation=client.organisation,
            grant=None if certifier_is_org_wide else client.grant,
        )

        response = client.post(
            url_for(
                "access_grant_funding.add_grant_team_member",
                organisation_id=client.organisation.id,
                grant_id=client.grant.id,
            ),
            data={"full_name": "Sarah Certifier", "email_address": "scertifier@hastings.gov.uk"},
        )
        assert response.status_code == 500

        db_session.refresh(certifier)
        assert all(RoleEnum.DATA_PROVIDER not in role.permissions for role in certifier.roles)
        assert db_session.scalars(select(AuditEventModel)).all() == []

    def test_post_invites_person_without_an_account(
        self, authenticated_grant_recipient_data_provider_client, db_session, mock_notification_service_calls
    ):
        client = authenticated_grant_recipient_data_provider_client
        enable_access_user_management_flag(client)
        grant_recipient = client.grant_recipient

        response = client.post(
            url_for(
                "access_grant_funding.add_grant_team_member",
                organisation_id=client.organisation.id,
                grant_id=client.grant.id,
            ),
            data={"full_name": "My User", "email_address": "user@hastings.gov.uk"},
        )
        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.list_grant_team", organisation_id=client.organisation.id, grant_id=client.grant.id
        )

        assert db_session.scalar(select(User).where(User.email == "user@hastings.gov.uk")) is None
        invitation = db_session.scalars(select(Invitation)).one()
        assert invitation.email == "user@hastings.gov.uk"
        assert invitation.name == "My User"
        assert invitation.organisation_id == client.organisation.id
        assert invitation.grant_id == client.grant.id
        assert set(invitation.permissions) == {RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER}
        assert invitation.is_usable is True

        audit_event = db_session.scalars(select(AuditEventModel)).one()
        assert audit_event.event_type == AuditEventType.USER_MANAGEMENT
        assert audit_event.user_id == client.user.id
        assert audit_event.data["action"] == "user_invited"
        assert audit_event.data["invitation_id"] == str(invitation.id)
        assert audit_event.data["grant_recipient_id"] == str(client.grant_recipient.id)

        assert len(mock_notification_service_calls) == 1
        notification_call = mock_notification_service_calls[0]
        assert notification_call.args == ("user@hastings.gov.uk", "ae3b6d9c-0e20-4510-84fb-d3406cf1e18c")
        assert notification_call.kwargs["personalisation"] == {
            "organisation_name": client.organisation.name,
            "grant_name": client.grant.name,
            "is_test_data": "no",
            "email_address": "user@hastings.gov.uk",
            "grant_submission_url": url_for(
                "access_grant_funding.list_collections",
                organisation_id=grant_recipient.organisation_id,
                grant_id=grant_recipient.grant_id,
                _external=True,
            ),
            "service_desk_url": client.application.config["ACCESS_SERVICE_DESK_URL"],
        }

        team_page = client.get(response.location)
        soup = BeautifulSoup(team_page.data, "html.parser")
        banner = soup.find(class_="govuk-notification-banner")
        assert banner is not None
        assert "Team member invited" in banner.get_text()
        assert (
            f"We’ve emailed My User an invite to {client.organisation.name}’s {client.grant.name}." in banner.get_text()
        )
        invited_row = next(row for row in soup.find_all("tr") if "user@hastings.gov.uk" in row.get_text())
        assert "My User" in invited_row.get_text()
        assert "Can edit and submit" in invited_row.get_text()

    def test_post_reinvites_person_with_a_pending_invitation(
        self, authenticated_grant_recipient_data_provider_client, factories, db_session, mock_notification_service_calls
    ):
        client = authenticated_grant_recipient_data_provider_client
        enable_access_user_management_flag(client)
        earlier_invitation = factories.invitation.create(
            email="user@hastings.gov.uk",
            name="My User",
            organisation=client.organisation,
            grant=client.grant,
            permissions=[RoleEnum.DATA_PROVIDER],
        )

        response = client.post(
            url_for(
                "access_grant_funding.add_grant_team_member",
                organisation_id=client.organisation.id,
                grant_id=client.grant.id,
            ),
            data={"full_name": "My Full User", "email_address": "user@hastings.gov.uk"},
        )
        assert response.status_code == 302

        db_session.refresh(earlier_invitation)
        assert earlier_invitation.is_usable is False
        usable_invitation = db_session.scalars(select(Invitation).where(Invitation.is_usable.is_(True))).one()
        assert usable_invitation.name == "My Full User"
        assert len(mock_notification_service_calls) == 1

    def test_post_with_invalid_email_shows_error(self, authenticated_grant_recipient_data_provider_client):
        client = authenticated_grant_recipient_data_provider_client
        enable_access_user_management_flag(client)

        response = client.post(
            url_for(
                "access_grant_funding.add_grant_team_member",
                organisation_id=client.organisation.id,
                grant_id=client.grant.id,
            ),
            data={"full_name": "Local user", "email_address": "not-an-email"},
        )
        assert response.status_code == 200
        assert "Enter an email address in the correct format, like name@example.com" in response.text

    def test_post_with_missing_fields_shows_errors(self, authenticated_grant_recipient_data_provider_client):
        client = authenticated_grant_recipient_data_provider_client
        enable_access_user_management_flag(client)

        response = client.post(
            url_for(
                "access_grant_funding.add_grant_team_member",
                organisation_id=client.organisation.id,
                grant_id=client.grant.id,
            ),
            data={"full_name": "", "email_address": ""},
        )
        assert response.status_code == 200
        assert "Enter the team member’s full name" in response.text
        assert "Enter the team member’s email address" in response.text


class TestRemoveGrantTeamMember:
    def test_get_returns_404_when_flag_disabled(self, authenticated_grant_recipient_data_provider_client):
        client = authenticated_grant_recipient_data_provider_client
        user = client.user

        response = client.get(
            url_for(
                "access_grant_funding.remove_grant_team_member",
                organisation_id=client.organisation.id,
                grant_id=client.grant.id,
                user_id=user.id,
            )
        )

        assert response.status_code == 404

    def test_get_forbidden_for_member(self, authenticated_grant_recipient_member_client, factories):
        client = authenticated_grant_recipient_member_client
        enable_access_user_management_flag(client)
        user = factories.user.create()
        factories.user_role.create(
            user=user, organisation=client.organisation, grant=client.grant, permissions=[RoleEnum.DATA_PROVIDER]
        )

        response = client.get(
            url_for(
                "access_grant_funding.remove_grant_team_member",
                organisation_id=client.organisation.id,
                grant_id=client.grant.id,
                user_id=user.id,
            )
        )

        assert response.status_code == 403

    def test_get_remove_grant_team_member_page(self, authenticated_grant_recipient_data_provider_client, factories):
        client = authenticated_grant_recipient_data_provider_client
        enable_access_user_management_flag(client)
        organisation = client.organisation
        grant = client.grant
        user = factories.user.create(name="Test User", email="test.user@communities.gov.uk")
        factories.user_role.create(
            user=user, organisation=organisation, grant=grant, permissions=[RoleEnum.DATA_PROVIDER]
        )

        response = client.get(
            url_for(
                "access_grant_funding.remove_grant_team_member",
                organisation_id=organisation.id,
                grant_id=grant.id,
                user_id=user.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == f"Remove {user.name} from {grant.name}?"
        assert f"{user.name} ({user.email}) will lose access to {organisation.name}’s {grant.name}." in soup.get_text()
        assert soup.find("button", string=lambda text: text and "Confirm and remove team member" in text) is not None
        cancel_link = soup.find("a", string="Cancel")
        assert cancel_link is not None
        assert cancel_link.get("href") == url_for(
            "access_grant_funding.list_grant_team",
            organisation_id=organisation.id,
            grant_id=grant.id,
        )

    def test_get_remove_grant_team_member_page_returns_404_for_current_user(
        self, authenticated_grant_recipient_data_provider_client
    ):
        client = authenticated_grant_recipient_data_provider_client
        enable_access_user_management_flag(client)

        response = client.get(
            url_for(
                "access_grant_funding.remove_grant_team_member",
                organisation_id=client.organisation.id,
                grant_id=client.grant.id,
                user_id=client.user.id,
            )
        )

        assert response.status_code == 404

    def test_get_remove_grant_team_member_page_returns_404_for_user_not_on_grant(
        self, authenticated_grant_recipient_data_provider_client, factories
    ):
        client = authenticated_grant_recipient_data_provider_client
        enable_access_user_management_flag(client)
        organisation = client.organisation
        grant = client.grant
        user = factories.user.create()

        response = client.get(
            url_for(
                "access_grant_funding.remove_grant_team_member",
                organisation_id=organisation.id,
                grant_id=grant.id,
                user_id=user.id,
            )
        )

        assert response.status_code == 404

    def test_get_remove_grant_team_member_page_returns_404_for_org_wide_data_provider(
        self, authenticated_grant_recipient_data_provider_client, factories
    ):
        client = authenticated_grant_recipient_data_provider_client
        enable_access_user_management_flag(client)
        user = factories.user.create()
        factories.user_role.create(
            user=user,
            organisation=client.organisation,
            grant=None,
            permissions=[RoleEnum.DATA_PROVIDER],
        )

        response = client.get(
            url_for(
                "access_grant_funding.remove_grant_team_member",
                organisation_id=client.organisation.id,
                grant_id=client.grant.id,
                user_id=user.id,
            )
        )

        assert response.status_code == 404

    def test_get_remove_grant_team_member_page_returns_404_for_certifier_only_user(
        self, authenticated_grant_recipient_data_provider_client, factories
    ):
        client = authenticated_grant_recipient_data_provider_client
        enable_access_user_management_flag(client)
        user = factories.user.create()
        factories.user_role.create(
            user=user,
            organisation=client.organisation,
            grant=client.grant,
            permissions=[RoleEnum.CERTIFIER],
        )

        response = client.get(
            url_for(
                "access_grant_funding.remove_grant_team_member",
                organisation_id=client.organisation.id,
                grant_id=client.grant.id,
                user_id=user.id,
            )
        )

        assert response.status_code == 404

    def test_post_removes_edit_access_but_keeps_certifier_access(
        self, authenticated_grant_recipient_data_provider_client, factories, db_session, mock_notification_service_calls
    ):
        client = authenticated_grant_recipient_data_provider_client
        enable_access_user_management_flag(client)
        organisation = client.organisation
        grant = client.grant
        user = factories.user.create(name="Test User", email="test.user@communities.gov.uk")
        factories.user_role.create(
            user=user,
            organisation=organisation,
            grant=grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER, RoleEnum.CERTIFIER],
        )

        response = client.post(
            url_for(
                "access_grant_funding.remove_grant_team_member",
                organisation_id=organisation.id,
                grant_id=grant.id,
                user_id=user.id,
            )
        )

        assert response.status_code == 302

        user_role = db_session.scalar(
            select(UserRole).where(
                UserRole.user_id == user.id,
                UserRole.organisation_id == organisation.id,
                UserRole.grant_id == grant.id,
            )
        )
        assert user_role is not None
        assert RoleEnum.DATA_PROVIDER not in user_role.permissions
        assert RoleEnum.CERTIFIER in user_role.permissions
        assert RoleEnum.MEMBER in user_role.permissions

        audit_event = db_session.scalars(select(AuditEventModel)).one()
        assert audit_event.event_type == AuditEventType.USER_MANAGEMENT

        assert len(mock_notification_service_calls) == 1
        email = mock_notification_service_calls[0]
        assert email.args == (user.email, "df45b766-9af8-4cde-a336-f84ea2e50542")
        assert email.kwargs["personalisation"] == {
            "email_address": user.email,
            "is_test_data": "no",
            "grant_name": grant.name,
            "organisation_name": organisation.name,
        }

    def test_post_removes_user_access_and_redirects_to_grant_team_page(
        self, authenticated_grant_recipient_data_provider_client, factories, db_session, mock_notification_service_calls
    ):
        client = authenticated_grant_recipient_data_provider_client
        enable_access_user_management_flag(client)
        organisation = client.organisation
        grant = client.grant
        user = factories.user.create(name="Test User", email="test.user@communities.gov.uk")
        factories.user_role.create(
            user=user, organisation=organisation, grant=grant, permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER]
        )

        response = client.post(
            url_for(
                "access_grant_funding.remove_grant_team_member",
                organisation_id=organisation.id,
                grant_id=grant.id,
                user_id=user.id,
            )
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.list_grant_team", organisation_id=organisation.id, grant_id=grant.id
        )

        removed_user_role = db_session.scalar(
            select(UserRole).where(
                UserRole.user_id == user.id,
                UserRole.organisation_id == organisation.id,
                UserRole.grant_id == grant.id,
            )
        )
        assert removed_user_role is None

        audit_event = db_session.scalars(select(AuditEventModel)).one()
        assert audit_event.event_type == AuditEventType.USER_MANAGEMENT

        assert len(mock_notification_service_calls) == 1
        email = mock_notification_service_calls[0]
        assert email.args == (user.email, "df45b766-9af8-4cde-a336-f84ea2e50542")
        assert email.kwargs["personalisation"] == {
            "email_address": user.email,
            "is_test_data": "no",
            "grant_name": grant.name,
            "organisation_name": organisation.name,
        }

        team_page = client.get(response.location)
        soup = BeautifulSoup(team_page.data, "html.parser")
        banner = soup.find(class_="govuk-notification-banner")
        assert banner is not None
        assert "Team member removed" in banner.get_text()
        assert (
            f"{user.name} was removed from {grant.name}. They can no longer edit and submit for this grant on "
            f"behalf of {organisation.name}."
        ) in banner.get_text()
        assert user.name not in [td.get_text(strip=True) for td in soup.find_all("td")]


class TestCookieBanner:
    def test_access_loads_with_invisible_cookie_banner(
        self, authenticated_grant_recipient_data_provider_client, grant_recipient
    ):
        response = authenticated_grant_recipient_data_provider_client.get(
            url_for(
                "access_grant_funding.list_collections",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h2_text(soup) == "Cookies on Access grant funding"

        # as no JS has run, the cookie banner should be hidden
        assert soup.find_all("div", class_="govuk-cookie-banner")[0].attrs.get("hidden", None) is not None


class TestPublicSignUpStartPage:
    def test_404_when_grant_slug_unknown(self, anonymous_client, factories):
        collection = factories.collection.create(
            grant__status=GrantStatusEnum.LIVE,
            status=CollectionStatusEnum.OPEN,
            allow_public_sign_up=True,
            slug="collection-slug",
        )

        response = anonymous_client.get(
            url_for(
                "access_grant_funding.public_sign_up_start_page",
                grant_slug="not-a-real-grant",
                collection_slug=collection.slug,
            )
        )

        assert response.status_code == 404

    def test_404_when_collection_slug_unknown(self, anonymous_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")

        response = anonymous_client.get(
            url_for(
                "access_grant_funding.public_sign_up_start_page",
                grant_slug=grant.slug,
                collection_slug="not-a-real-collection",
            )
        )

        assert response.status_code == 404

    @pytest.mark.parametrize(
        "grant_status, collection_status, allow_public_sign_up, expected_status",
        (
            (GrantStatusEnum.LIVE, CollectionStatusEnum.OPEN, True, 200),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.OPEN, False, 404),
            (GrantStatusEnum.DRAFT, CollectionStatusEnum.OPEN, True, 404),
            (GrantStatusEnum.ONBOARDING, CollectionStatusEnum.OPEN, True, 404),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.DRAFT, True, 404),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.CLOSED, True, 404),
        ),
    )
    def test_anonymous_access_depends_on_status_and_allow_public_sign_up(
        self,
        anonymous_client,
        factories,
        grant_status,
        collection_status,
        allow_public_sign_up,
        expected_status,
    ):
        grant = factories.grant.create(status=grant_status, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant,
            status=collection_status,
            allow_public_sign_up=allow_public_sign_up,
            slug="collection-slug",
        )

        response = anonymous_client.get(
            url_for(
                "access_grant_funding.public_sign_up_start_page",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
            )
        )

        assert response.status_code == expected_status

    @pytest.mark.parametrize(
        "grant_status, collection_status",
        (
            (GrantStatusEnum.DRAFT, CollectionStatusEnum.DRAFT),
            (GrantStatusEnum.DRAFT, CollectionStatusEnum.OPEN),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.DRAFT),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.OPEN),
            (GrantStatusEnum.ONBOARDING, CollectionStatusEnum.OPEN),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.CLOSED),
        ),
    )
    def test_deliver_user_testing_access_allowed_for_any_status(
        self, anonymous_client, factories, user, db_session, grant_status, collection_status
    ):
        grant = factories.grant.create(status=grant_status, slug="grant-slug")
        can_manage_grants_organisation = grant.organisation

        collection = factories.collection.create(
            grant=grant,
            status=collection_status,
            allow_public_sign_up=True,
            slug="collection-slug",
        )
        factories.user_role.create(
            user=user, organisation=can_manage_grants_organisation, grant=grant, permissions=[RoleEnum.MEMBER]
        )

        login_user(user)
        with anonymous_client.session_transaction() as flask_session:
            flask_session["auth"] = AuthMethodEnum.SSO
        db_session.commit()

        response = anonymous_client.get(
            url_for(
                "access_grant_funding.public_sign_up_start_page",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
            )
        )

        assert response.status_code == 200

    def test_page_content_with_prospectus_url(self, anonymous_client, factories):
        grant = factories.grant.create(
            status=GrantStatusEnum.LIVE, name="Test grant name", slug="grant-slug", description="Some grant description"
        )
        collection = factories.collection.create(
            grant=grant,
            status=CollectionStatusEnum.OPEN,
            slug="collection-slug",
            allow_public_sign_up=True,
            prospectus_url="https://example.com/prospectus",
        )

        response = anonymous_client.get(
            url_for(
                "access_grant_funding.public_sign_up_start_page",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
            )
        )

        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == f"Apply for the {grant.name}"
        assert "Some grant description" in soup.get_text()
        assert soup.find("meta", attrs={"name": "robots"})["content"] == "noindex, nofollow"
        assert soup.find("a", href="https://example.com/prospectus") is not None

    def test_page_content_without_prospectus_url(self, anonymous_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant,
            status=CollectionStatusEnum.OPEN,
            slug="collection-slug",
            allow_public_sign_up=True,
            prospectus_url=None,
        )

        response = anonymous_client.get(
            url_for(
                "access_grant_funding.public_sign_up_start_page",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
            )
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "prospectus" not in soup.get_text().lower()

    def test_page_content_with_submission_deadline(self, anonymous_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant,
            status=CollectionStatusEnum.OPEN,
            slug="collection-slug",
            allow_public_sign_up=True,
            submission_period_end_date=datetime.date(2026, 8, 30),
        )

        response = anonymous_client.get(
            url_for(
                "access_grant_funding.public_sign_up_start_page",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
            )
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "Deadline for applications" in soup.get_text()
        assert "30 August 2026" in soup.get_text()

    def test_page_content_without_submission_deadline(self, anonymous_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant,
            status=CollectionStatusEnum.OPEN,
            slug="collection-slug",
            allow_public_sign_up=True,
            submission_period_end_date=None,
        )

        response = anonymous_client.get(
            url_for(
                "access_grant_funding.public_sign_up_start_page",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
            )
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "Deadline for applications" not in soup.get_text()

    def test_page_start_button(self, anonymous_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant,
            status=CollectionStatusEnum.OPEN,
            slug="collection-slug",
            allow_public_sign_up=True,
        )

        response = anonymous_client.get(
            url_for(
                "access_grant_funding.public_sign_up_start_page",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
            )
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        form = soup.find("form")
        assert form is not None
        assert form.get("method", "").lower() == "post"
        start_button = form.find("button", {"class": "govuk-button"})
        assert start_button is not None
        assert "Start now" in start_button.get_text(strip=True)

    def test_post_sets_signing_up_session_flag_and_redirects(self, anonymous_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant,
            status=CollectionStatusEnum.OPEN,
            slug="collection-slug",
            allow_public_sign_up=True,
        )

        response = anonymous_client.post(
            url_for(
                "access_grant_funding.public_sign_up_start_page",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
            )
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "auth.collection_request_a_link_to_public_sign_up", grant_slug=grant.slug, collection_slug=collection.slug
        )

        with anonymous_client.session_transaction() as flask_session:
            assert flask_session["signing_up_for_collection_id"] == collection.id

    def test_post_as_member_deliver_user_skips_magic_link_and_redirects_to_sign_up_router(
        self, authenticated_grant_member_client, factories
    ):
        grant = authenticated_grant_member_client.grant
        collection = factories.collection.create(
            grant=grant,
            status=CollectionStatusEnum.OPEN,
            slug="collection-slug",
            allow_public_sign_up=True,
        )

        response = authenticated_grant_member_client.post(
            url_for(
                "access_grant_funding.public_sign_up_start_page",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
            )
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.public_sign_up_router", grant_slug=grant.slug, collection_slug=collection.slug
        )

        with authenticated_grant_member_client.session_transaction() as flask_session:
            assert "signing_up_for_collection_id" not in flask_session


class TestPublicSignUpRouter:
    def test_get_404s_for_unknown_grant(self, authenticated_no_role_client, factories):
        collection = factories.collection.create(slug="collection-slug")

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.public_sign_up_router",
                grant_slug="not-a-real-grant",
                collection_slug=collection.slug,
            )
        )

        assert response.status_code == 404

    def test_get_404s_for_unknown_collection(self, authenticated_no_role_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.public_sign_up_router",
                grant_slug=grant.slug,
                collection_slug="not-a-real-collection",
            )
        )

        assert response.status_code == 404

    @pytest.mark.parametrize(
        "grant_status, collection_status, allow_public_sign_up, expected_status",
        (
            (GrantStatusEnum.LIVE, CollectionStatusEnum.OPEN, True, 302),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.OPEN, False, 404),
            (GrantStatusEnum.DRAFT, CollectionStatusEnum.OPEN, True, 404),
            (GrantStatusEnum.ONBOARDING, CollectionStatusEnum.OPEN, True, 404),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.DRAFT, True, 404),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.CLOSED, True, 404),
        ),
    )
    def test_anonymous_access_depends_on_status_and_allow_public_sign_up(
        self,
        anonymous_client,
        factories,
        grant_status,
        collection_status,
        allow_public_sign_up,
        expected_status,
    ):
        grant = factories.grant.create(status=grant_status, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant,
            status=collection_status,
            allow_public_sign_up=allow_public_sign_up,
            slug="collection-slug",
        )

        response = anonymous_client.get(
            url_for(
                "access_grant_funding.public_sign_up_router",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
            )
        )

        assert response.status_code == expected_status

    @pytest.mark.parametrize(
        "grant_status, collection_status",
        (
            (GrantStatusEnum.DRAFT, CollectionStatusEnum.DRAFT),
            (GrantStatusEnum.DRAFT, CollectionStatusEnum.OPEN),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.DRAFT),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.OPEN),
            (GrantStatusEnum.ONBOARDING, CollectionStatusEnum.OPEN),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.CLOSED),
        ),
    )
    def test_deliver_user_testing_access_allowed_for_any_status(
        self, anonymous_client, factories, user, db_session, grant_status, collection_status
    ):
        grant = factories.grant.create(status=grant_status, slug="grant-slug")
        can_manage_grants_organisation = grant.organisation

        collection = factories.collection.create(
            grant=grant,
            status=collection_status,
            allow_public_sign_up=True,
            slug="collection-slug",
        )
        factories.user_role.create(
            user=user, organisation=can_manage_grants_organisation, grant=grant, permissions=[RoleEnum.MEMBER]
        )

        login_user(user)
        with anonymous_client.session_transaction() as flask_session:
            flask_session["auth"] = AuthMethodEnum.SSO
        db_session.commit()

        response = anonymous_client.get(
            url_for(
                "access_grant_funding.public_sign_up_router",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
            )
        )

        assert response.status_code == 302

    def test_get_redirects_to_eligible_to_apply_when_no_eligibility_form(
        self, authenticated_grant_member_client, factories
    ):
        grant = authenticated_grant_member_client.grant
        collection = factories.collection.create(
            grant=grant,
            status=CollectionStatusEnum.OPEN,
            slug="collection-slug",
            allow_public_sign_up=True,
        )

        response = authenticated_grant_member_client.get(
            url_for(
                "access_grant_funding.public_sign_up_router",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
            )
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug
        )

    def test_get_redirects_to_eligible_to_apply_when_eligibility_form_has_no_questions(
        self, authenticated_grant_member_client, factories
    ):
        grant = authenticated_grant_member_client.grant
        collection = factories.collection.create(
            grant=grant,
            status=CollectionStatusEnum.OPEN,
            slug="collection-slug",
            allow_public_sign_up=True,
        )
        factories.form.create(collection=collection, is_eligibility_section=True)

        response = authenticated_grant_member_client.get(
            url_for(
                "access_grant_funding.public_sign_up_router",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
            )
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug
        )

    def test_get_returns_400_for_invalid_destination(self, authenticated_grant_member_client, factories):
        grant = authenticated_grant_member_client.grant
        collection = factories.collection.create(
            grant=grant,
            status=CollectionStatusEnum.OPEN,
            slug="collection-slug",
            allow_public_sign_up=True,
        )

        response = authenticated_grant_member_client.get(
            url_for(
                "access_grant_funding.public_sign_up_router",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
                destination="middle",
            )
        )

        assert response.status_code == 400

    def test_get_redirects_to_first_eligibility_question_by_default(self, authenticated_grant_member_client, factories):
        grant = authenticated_grant_member_client.grant
        collection = factories.collection.create(
            grant=grant,
            status=CollectionStatusEnum.OPEN,
            slug="collection-slug",
            allow_public_sign_up=True,
        )
        eligibility_form = factories.form.create(collection=collection, is_eligibility_section=True)
        question = factories.question.create(form=eligibility_form)

        response = authenticated_grant_member_client.get(
            url_for(
                "access_grant_funding.public_sign_up_router",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
            )
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.public_sign_up_eligibility_question",
            grant_slug=grant.slug,
            collection_slug=collection.slug,
            question_id=question.id,
        )

    def test_get_redirects_to_first_eligibility_question_even_when_form_already_completed(
        self, authenticated_grant_member_client, factories
    ):
        grant = authenticated_grant_member_client.grant
        collection = factories.collection.create(
            grant=grant,
            status=CollectionStatusEnum.OPEN,
            slug="collection-slug",
            allow_public_sign_up=True,
        )
        eligibility_form = factories.form.create(collection=collection, is_eligibility_section=True)
        question = factories.question.create(form=eligibility_form)

        unclaimed_submission = get_or_create_unclaimed_submission(
            authenticated_grant_member_client.user, collection, SubmissionModeEnum.TEST
        ).submission
        factories.submission_event.create(
            submission=unclaimed_submission,
            event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED,
            related_entity_id=eligibility_form.id,
        )

        response = authenticated_grant_member_client.get(
            url_for(
                "access_grant_funding.public_sign_up_router",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
            )
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.public_sign_up_eligibility_question",
            grant_slug=grant.slug,
            collection_slug=collection.slug,
            question_id=question.id,
        )

    def test_get_redirects_to_last_eligibility_question_when_destination_is_end(
        self, authenticated_grant_member_client, factories
    ):
        grant = authenticated_grant_member_client.grant
        collection = factories.collection.create(
            grant=grant,
            status=CollectionStatusEnum.OPEN,
            slug="collection-slug",
            allow_public_sign_up=True,
        )
        eligibility_form = factories.form.create(collection=collection, is_eligibility_section=True)
        factories.question.create(form=eligibility_form)
        last_question = factories.question.create(form=eligibility_form)

        response = authenticated_grant_member_client.get(
            url_for(
                "access_grant_funding.public_sign_up_router",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
                destination="end",
            )
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.public_sign_up_eligibility_question",
            grant_slug=grant.slug,
            collection_slug=collection.slug,
            question_id=last_question.id,
        )


class TestEligibleToApplyPage:
    def test_get_redirects_when_not_authenticated(self, anonymous_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )

        response = anonymous_client.get(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug)
        )
        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.public_sign_up_start_page", grant_slug=grant.slug, collection_slug=collection.slug
        )

    def test_get_404s_for_unknown_grant(self, authenticated_no_role_client, factories):
        collection = factories.collection.create(slug="collection-slug")

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.eligible_to_apply",
                grant_slug="not-a-real-grant",
                collection_slug=collection.slug,
            )
        )

        assert response.status_code == 404

    def test_get_404s_for_unknown_collection(self, authenticated_no_role_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.eligible_to_apply",
                grant_slug=grant.slug,
                collection_slug="not-a-real-collection",
            )
        )

        assert response.status_code == 404

    @pytest.mark.parametrize(
        "grant_status, collection_status, allow_public_sign_up",
        (
            (GrantStatusEnum.LIVE, CollectionStatusEnum.OPEN, False),
            (GrantStatusEnum.DRAFT, CollectionStatusEnum.OPEN, True),
            (GrantStatusEnum.ONBOARDING, CollectionStatusEnum.OPEN, True),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.DRAFT, True),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.CLOSED, True),
        ),
    )
    def test_get_depends_on_status_and_allow_public_sign_up(
        self,
        authenticated_no_role_client,
        factories,
        grant_status,
        collection_status,
        allow_public_sign_up,
    ):
        grant = factories.grant.create(status=grant_status, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant,
            status=collection_status,
            allow_public_sign_up=allow_public_sign_up,
            slug="collection-slug",
        )

        with authenticated_no_role_client.session_transaction() as flask_session:
            flask_session["signing_up_for_collection_id"] = collection.id

        response = authenticated_no_role_client.get(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug)
        )

        assert response.status_code == 404

    @pytest.mark.parametrize(
        "grant_status, collection_status",
        (
            (GrantStatusEnum.DRAFT, CollectionStatusEnum.DRAFT),
            (GrantStatusEnum.DRAFT, CollectionStatusEnum.OPEN),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.DRAFT),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.OPEN),
            (GrantStatusEnum.ONBOARDING, CollectionStatusEnum.OPEN),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.CLOSED),
        ),
    )
    def test_deliver_user_testing_access_allowed_for_any_status(
        self, anonymous_client, factories, user, db_session, grant_status, collection_status
    ):
        grant = factories.grant.create(status=grant_status, slug="grant-slug")
        can_manage_grants_organisation = grant.organisation

        collection = factories.collection.create(
            grant=grant,
            status=collection_status,
            allow_public_sign_up=True,
            slug="collection-slug",
        )
        factories.user_role.create(
            user=user, organisation=can_manage_grants_organisation, grant=grant, permissions=[RoleEnum.MEMBER]
        )
        factories.organisation.create(
            name="Test Organisation",
            domains=[user.email.split("@")[-1]],
            mode=OrganisationModeEnum.TEST,
        )

        login_user(user)
        with anonymous_client.session_transaction() as flask_session:
            flask_session["auth"] = AuthMethodEnum.SSO
        db_session.commit()

        response = anonymous_client.get(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug)
        )

        assert response.status_code == 200

    @pytest.mark.authenticate_as("test@example-org.com")
    def test_get_redirects_to_first_eligibility_question_when_not_passed(
        self, authenticated_no_role_client, factories, db_session
    ):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )
        eligibility_form = factories.form.create(collection=collection, is_eligibility_section=True)
        question = factories.question.create(form=eligibility_form, data_type=QuestionDataType.NUMBER)
        add_component_eligibility(
            question,
            authenticated_no_role_client.user,
            GreaterThan(minimum_value=3, subject_reference=ExpressionReference.from_question(question)),
        )
        factories.organisation.create(name="Test Organisation", domains=["example-org.com"])
        db_session.commit()

        with authenticated_no_role_client.session_transaction() as flask_session:
            flask_session["signing_up_for_collection_id"] = collection.id

        response = authenticated_no_role_client.get(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.public_sign_up_eligibility_question",
            grant_slug=grant.slug,
            collection_slug=collection.slug,
            question_id=question.id,
        )

    @pytest.mark.authenticate_as("test@no-matching-org.com")
    def test_get_back_link_goes_to_sign_up_router_when_eligibility_form_exists(
        self, authenticated_no_role_client, factories, db_session
    ):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )
        eligibility_form = factories.form.create(collection=collection, is_eligibility_section=True)
        question = factories.question.create(form=eligibility_form, data_type=QuestionDataType.NUMBER)
        add_component_eligibility(
            question,
            authenticated_no_role_client.user,
            GreaterThan(minimum_value=3, subject_reference=ExpressionReference.from_question(question)),
        )
        db_session.commit()

        with authenticated_no_role_client.session_transaction() as flask_session:
            flask_session["signing_up_for_collection_id"] = collection.id

        FormCls = build_question_form([question], ExpressionContext(), ExpressionContext())
        form = FormCls(data={question.safe_qid: "10"})
        authenticated_no_role_client.post(
            url_for(
                "access_grant_funding.public_sign_up_eligibility_question",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
                question_id=question.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        response = authenticated_no_role_client.get(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug)
        )

        assert response.status_code == 200
        expected_back_url = url_for(
            "access_grant_funding.public_sign_up_router",
            grant_slug=grant.slug,
            collection_slug=collection.slug,
        )
        assert expected_back_url.encode() in response.data

    @pytest.mark.authenticate_as("test@no-matching-org.com")
    def test_get_back_link_goes_to_start_page_when_no_eligibility_form(self, authenticated_no_role_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )

        with authenticated_no_role_client.session_transaction() as flask_session:
            flask_session["signing_up_for_collection_id"] = collection.id

        response = authenticated_no_role_client.get(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug)
        )

        assert response.status_code == 200
        expected_back_url = url_for(
            "access_grant_funding.public_sign_up_start_page", grant_slug=grant.slug, collection_slug=collection.slug
        )
        assert expected_back_url.encode() in response.data

    @pytest.mark.authenticate_as("test@no-matching-org.com")
    def test_get_shows_create_org_button_when_no_organisation_matches_email_domain(
        self, authenticated_no_role_client, factories
    ):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )

        with authenticated_no_role_client.session_transaction() as flask_session:
            flask_session["signing_up_for_collection_id"] = collection.id

        response = authenticated_no_role_client.get(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug)
        )

        assert response.status_code == 200
        assert b"We could not find an organisation with the email address you provided." in response.data
        assert b"Create an organisation" in response.data

    @pytest.mark.authenticate_as("test@shared-domain.com")
    def test_get_shows_organisation_options_when_multiple_organisations_match_email_domain(
        self, authenticated_no_role_client, factories
    ):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )
        factories.organisation.create(name="Org A", domains=["shared-domain.com"])
        factories.organisation.create(name="Org B", domains=["shared-domain.com"])

        with authenticated_no_role_client.session_transaction() as flask_session:
            flask_session["signing_up_for_collection_id"] = collection.id

        response = authenticated_no_role_client.get(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug)
        )

        assert response.status_code == 200
        assert b"Org A" in response.data
        assert b"Org B" in response.data
        assert b"Sign up a new organisation to apply" in response.data

    @pytest.mark.authenticate_as("test@example-org.com")
    def test_get_with_known_grant_and_collection(self, authenticated_no_role_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug", name="Test grant name")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )
        factories.organisation.create(name="Test Organisation", domains=["example-org.com"])

        with authenticated_no_role_client.session_transaction() as flask_session:
            flask_session["signing_up_for_collection_id"] = collection.id

        response = authenticated_no_role_client.get(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug)
        )

        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "You are eligible to apply" in get_h1_text(soup)
        assert "Test grant name" in soup.text
        assert "Test Organisation" in soup.text

    @pytest.mark.authenticate_as("test@example-org.com")
    def test_post_creates_grant_recipient_and_grants_data_provider_role(
        self, authenticated_no_role_client, factories, db_session
    ):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug", name="Test grant name")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )
        organisation = factories.organisation.create(
            name="Test Organisation",
            domains=["example-org.com"],
            external_id="org-1",
            mode=OrganisationModeEnum.LIVE,
        )
        with authenticated_no_role_client.session_transaction() as flask_session:
            flask_session["signing_up_for_collection_id"] = collection.id

        response = authenticated_no_role_client.post(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug),
            data={"organisation": str(organisation.id)},
        )
        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.list_collections",
            organisation_id=organisation.id,
            grant_id=grant.id,
        )

        grant_recipient = db_session.scalars(
            select(GrantRecipient).where(
                GrantRecipient.grant_id == grant.id, GrantRecipient.organisation_id == organisation.id
            )
        ).one()
        assert grant_recipient.status == GrantRecipientStatusEnum.APPLYING
        assert grant_recipient.mode == GrantRecipientModeEnum.LIVE

        user_role = db_session.scalars(
            select(UserRole).where(
                UserRole.user_id == authenticated_no_role_client.user.id,
                UserRole.organisation_id == organisation.id,
                UserRole.grant_id == grant.id,
            )
        ).one()
        assert RoleEnum.DATA_PROVIDER in user_role.permissions

        # We delete the signing_up_for_collection_id session flag
        with authenticated_no_role_client.session_transaction() as flask_session:
            assert "signing_up_for_collection_id" not in flask_session

        # Success banner shows on the forms page
        followed_response = authenticated_no_role_client.get(response.location, follow_redirects=True)
        assert followed_response.status_code == 200
        soup = BeautifulSoup(followed_response.data, "html.parser")
        assert "Success" in soup.text
        assert "Added to organisation" in soup.text
        assert "You've been added to Test Organisation. You can now apply for Test grant name." in soup.text

    @pytest.mark.authenticate_as("test@example-org.com")
    def test_post_rejects_organisation_not_in_matched_list(
        self, authenticated_no_role_client, factories, db_session, mocker, caplog
    ):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )
        # Org with domain that matches the user's email
        factories.organisation.create(
            name="Matched Organisation",
            domains=["example-org.com"],
            external_id="org-1",
            mode=OrganisationModeEnum.LIVE,
        )
        # Org with domain that doesn't match the user's email
        unmatched_organisation = factories.organisation.create(
            name="Unmatched Organisation",
            domains=["other-org.com"],
            external_id="org-2",
            mode=OrganisationModeEnum.LIVE,
        )

        with authenticated_no_role_client.session_transaction() as flask_session:
            flask_session["signing_up_for_collection_id"] = collection.id

        # WTForms would already reject this before our explicit check runs - bypass it here
        # Form would already throw an "Error: Not a valid choice."
        mocker.patch.object(EligibleOrganisationSelectionForm, "validate_on_submit", lambda self: True)

        with caplog.at_level(logging.WARNING):
            response = authenticated_no_role_client.post(
                url_for(
                    "access_grant_funding.eligible_to_apply",
                    grant_slug=grant.slug,
                    collection_slug=collection.slug,
                ),
                data={"organisation": str(unmatched_organisation.id)},
            )

        assert response.status_code == 403
        assert any("submitted an organisation not in their matched list" in r.getMessage() for r in caplog.records)

        grant_recipients = db_session.scalars(
            select(GrantRecipient).where(
                GrantRecipient.grant_id == grant.id,
                GrantRecipient.organisation_id == unmatched_organisation.id,
            )
        ).all()
        assert grant_recipients == []

    @pytest.mark.authenticate_as("test@example-org.com")
    def test_post_reuses_existing_grant_recipient_when_user_already_has_role(
        self, authenticated_no_role_client, factories, db_session
    ):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug", name="Test grant name")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )
        organisation = factories.organisation.create(name="Test Organisation", domains=["example-org.com"])
        existing_grant_recipient = factories.grant_recipient.create(grant=grant, organisation=organisation)
        factories.user_role.create(
            user=authenticated_no_role_client.user,
            organisation=organisation,
            grant=grant,
            permissions=[RoleEnum.DATA_PROVIDER],
        )

        with authenticated_no_role_client.session_transaction() as flask_session:
            flask_session["signing_up_for_collection_id"] = collection.id

        response = authenticated_no_role_client.post(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug),
            data={"organisation": str(organisation.id)},
        )

        assert response.status_code == 302

        grant_recipients = db_session.scalars(
            select(GrantRecipient).where(
                GrantRecipient.grant_id == grant.id, GrantRecipient.organisation_id == organisation.id
            )
        ).all()

        assert len(grant_recipients) == 1
        assert grant_recipients[0].id == existing_grant_recipient.id

        # We delete the signing_up_for_collection_id session flag
        with authenticated_no_role_client.session_transaction() as flask_session:
            assert "signing_up_for_collection_id" not in flask_session

        # "Already have access" banner shown on the forms page, not the "added to organisation" one
        followed_response = authenticated_no_role_client.get(response.location, follow_redirects=True)
        assert followed_response.status_code == 200
        soup = BeautifulSoup(followed_response.data, "html.parser")
        assert "Important" in soup.text
        assert "You already have access to this grant" in soup.text
        assert "In the future you can access this grant directly using this link" in soup.text
        assert "Added to organisation" not in soup.text

    @pytest.mark.authenticate_as("test@example-org.com")
    def test_post_redirects_to_already_applying_when_grant_recipient_exists_and_user_has_no_role(
        self, authenticated_no_role_client, factories, db_session
    ):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )
        organisation = factories.organisation.create(name="Test Organisation", domains=["example-org.com"])
        # A colleague from the same email domain has already applied, but this user has no role on it yet
        factories.grant_recipient.create(grant=grant, organisation=organisation)

        with authenticated_no_role_client.session_transaction() as flask_session:
            flask_session["signing_up_for_collection_id"] = collection.id

        response = authenticated_no_role_client.post(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug),
            data={"organisation": str(organisation.id)},
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.already_applying",
            grant_slug=grant.slug,
            collection_slug=collection.slug,
            organisation_id=organisation.id,
        )

        grant_recipients = db_session.scalars(
            select(GrantRecipient).where(
                GrantRecipient.grant_id == grant.id, GrantRecipient.organisation_id == organisation.id
            )
        ).all()
        assert len(grant_recipients) == 1

        user_role = db_session.scalars(
            select(UserRole).where(
                UserRole.user_id == authenticated_no_role_client.user.id,
                UserRole.organisation_id == organisation.id,
                UserRole.grant_id == grant.id,
            )
        ).one_or_none()
        assert user_role is None

        # The signing_up_for_collection_id session exists because flag is only cleared on successful sign-up
        with authenticated_no_role_client.session_transaction() as flask_session:
            assert flask_session["signing_up_for_collection_id"] == collection.id

        # already-applying page actually renders when followed
        followed_response = authenticated_no_role_client.get(response.location, follow_redirects=True)
        assert followed_response.status_code == 200
        soup = BeautifulSoup(followed_response.data, "html.parser")
        assert "Your organisation is already applying" in get_h1_text(soup)

    @pytest.mark.authenticate_as("test@example-org.com")
    def test_post_as_deliver_user_redirects_to_submission_page(self, authenticated_grant_member_client, factories):
        grant = authenticated_grant_member_client.grant
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )
        factories.question.create(form__collection=collection)
        organisation = factories.organisation.create(
            name="Test Organisation", domains=["example-org.com"], mode=OrganisationModeEnum.TEST
        )
        factories.grant_recipient.create(grant=grant, organisation=organisation, mode=GrantRecipientModeEnum.TEST)
        factories.user_role.create(
            user=authenticated_grant_member_client.user,
            organisation=organisation,
            grant=grant,
            permissions=[RoleEnum.DATA_PROVIDER],
        )

        response = authenticated_grant_member_client.post(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug),
            data={"organisation": str(organisation.id)},
        )

        # Redirects to the forms page
        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.list_collections",
            organisation_id=organisation.id,
            grant_id=grant.id,
        )

        # Checking submission page loads correctly
        followed_response = authenticated_grant_member_client.get(response.location, follow_redirects=True)
        assert followed_response.status_code == 200
        soup = BeautifulSoup(followed_response.data, "html.parser")
        assert "Testing grant recipient journey" in soup.text

    @pytest.mark.authenticate_as("test@example-org.com")
    def test_post_as_deliver_user_without_existing_grant_recipient_creates_one(
        self, authenticated_grant_member_client, factories, db_session
    ):
        grant = authenticated_grant_member_client.grant
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )
        organisation = factories.organisation.create(
            name="Test Organisation", domains=["example-org.com"], mode=OrganisationModeEnum.TEST
        )
        # The user has no role at all on the matched organisation, and no TEST grant recipient exists yet

        response = authenticated_grant_member_client.post(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug),
            data={"organisation": str(organisation.id)},
        )

        # Redirects to the forms page
        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.list_collections",
            organisation_id=organisation.id,
            grant_id=grant.id,
        )

        # A TEST grant recipient is auto-created for the tester, along with the DATA_PROVIDER role
        grant_recipient = db_session.scalars(
            select(GrantRecipient).where(
                GrantRecipient.grant_id == grant.id, GrantRecipient.organisation_id == organisation.id
            )
        ).one()
        assert grant_recipient.status == GrantRecipientStatusEnum.APPLYING
        assert grant_recipient.mode == GrantRecipientModeEnum.TEST

        user_role = db_session.scalars(
            select(UserRole).where(
                UserRole.user_id == authenticated_grant_member_client.user.id,
                UserRole.organisation_id == organisation.id,
                UserRole.grant_id == grant.id,
            )
        ).one()
        assert RoleEnum.DATA_PROVIDER in user_role.permissions

        # Submission page now loads successfully, with the "added to organisation" banner shown
        followed_response = authenticated_grant_member_client.get(response.location, follow_redirects=True)
        assert followed_response.status_code == 200
        soup = BeautifulSoup(followed_response.data, "html.parser")
        assert "Added to organisation" in soup.text
        assert f"You've been added to {organisation.name}. You can now apply for {grant.name}." in soup.text

    @pytest.mark.authenticate_as("test@example-org.com")
    def test_post_as_deliver_user_without_access_to_existing_grant_recipient_redirects_to_already_applying(
        self, authenticated_grant_member_client, factories, db_session
    ):
        grant = authenticated_grant_member_client.grant
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )
        organisation = factories.organisation.create(
            name="Test Organisation", domains=["example-org.com"], mode=OrganisationModeEnum.TEST
        )
        # A TEST grant recipient already exists for this organisation and grant, but the user has no role on it
        factories.grant_recipient.create(grant=grant, organisation=organisation, mode=GrantRecipientModeEnum.TEST)

        response = authenticated_grant_member_client.post(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug),
            data={"organisation": str(organisation.id)},
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.already_applying",
            grant_slug=grant.slug,
            collection_slug=collection.slug,
            organisation_id=organisation.id,
        )

        # No new grant recipient or role was created for the user
        grant_recipients = db_session.scalars(
            select(GrantRecipient).where(
                GrantRecipient.grant_id == grant.id, GrantRecipient.organisation_id == organisation.id
            )
        ).all()
        assert len(grant_recipients) == 1

        user_role = db_session.scalars(
            select(UserRole).where(
                UserRole.user_id == authenticated_grant_member_client.user.id,
                UserRole.organisation_id == organisation.id,
                UserRole.grant_id == grant.id,
            )
        ).one_or_none()
        assert user_role is None

    @pytest.mark.authenticate_as("test@example-org.com")
    def test_post_claims_unclaimed_submission_when_new_grant_recipient_created(
        self, authenticated_no_role_client, factories, db_session
    ):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )
        organisation = factories.organisation.create(name="Test Organisation", domains=["example-org.com"])

        unclaimed_submission = get_or_create_unclaimed_submission(
            authenticated_no_role_client.user, collection, SubmissionModeEnum.LIVE
        ).submission
        db_session.commit()

        with authenticated_no_role_client.session_transaction() as flask_session:
            flask_session["signing_up_for_collection_id"] = collection.id

        response = authenticated_no_role_client.post(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug),
            data={"organisation": str(organisation.id)},
        )

        assert response.status_code == 302

        grant_recipient = db_session.scalars(
            select(GrantRecipient).where(
                GrantRecipient.grant_id == grant.id, GrantRecipient.organisation_id == organisation.id
            )
        ).one()

        db_session.refresh(unclaimed_submission)
        assert unclaimed_submission.grant_recipient_id == grant_recipient.id

    @pytest.mark.authenticate_as("test@example-org.com")
    def test_post_claims_unclaimed_submission_when_reusing_existing_grant_recipient(
        self, authenticated_no_role_client, factories, db_session
    ):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )
        organisation = factories.organisation.create(name="Test Organisation", domains=["example-org.com"])
        existing_grant_recipient = factories.grant_recipient.create(grant=grant, organisation=organisation)
        factories.user_role.create(
            user=authenticated_no_role_client.user,
            organisation=organisation,
            grant=grant,
            permissions=[RoleEnum.DATA_PROVIDER],
        )

        unclaimed_submission = get_or_create_unclaimed_submission(
            authenticated_no_role_client.user, collection, SubmissionModeEnum.LIVE
        ).submission
        db_session.commit()

        with authenticated_no_role_client.session_transaction() as flask_session:
            flask_session["signing_up_for_collection_id"] = collection.id

        response = authenticated_no_role_client.post(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug),
            data={"organisation": str(organisation.id)},
        )

        assert response.status_code == 302

        db_session.refresh(unclaimed_submission)
        assert unclaimed_submission.grant_recipient_id == existing_grant_recipient.id

    @pytest.mark.authenticate_as("test@example-org.com")
    def test_post_discards_unclaimed_submission_when_grant_recipient_already_has_a_submission(
        self, authenticated_no_role_client, factories, db_session
    ):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )
        organisation = factories.organisation.create(name="Test Organisation", domains=["example-org.com"])
        existing_grant_recipient = factories.grant_recipient.create(grant=grant, organisation=organisation)
        # Creates submission for existing user+collection+gr
        factories.submission.create(
            collection=collection, mode=SubmissionModeEnum.LIVE, grant_recipient=existing_grant_recipient
        )
        factories.user_role.create(
            user=authenticated_no_role_client.user,
            organisation=organisation,
            grant=grant,
            permissions=[RoleEnum.DATA_PROVIDER],
        )

        unclaimed_submission = get_or_create_unclaimed_submission(
            authenticated_no_role_client.user, collection, SubmissionModeEnum.LIVE
        ).submission
        unclaimed_submission_id = unclaimed_submission.id
        db_session.commit()

        with authenticated_no_role_client.session_transaction() as flask_session:
            flask_session["signing_up_for_collection_id"] = collection.id

        response = authenticated_no_role_client.post(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug),
            data={"organisation": str(organisation.id)},
        )

        assert response.status_code == 302
        assert db_session.get(Submission, unclaimed_submission_id) is None


class TestAlreadyApplyingPage:
    def test_get_404s_for_unknown_grant(self, authenticated_no_role_client, factories):
        collection = factories.collection.create(slug="collection-slug")
        organisation = factories.organisation.create()

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.already_applying",
                grant_slug="not-a-real-grant",
                collection_slug=collection.slug,
                organisation_id=organisation.id,
            )
        )

        assert response.status_code == 404

    def test_get_404s_for_unknown_collection(self, authenticated_no_role_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        organisation = factories.organisation.create()

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.already_applying",
                grant_slug=grant.slug,
                collection_slug="not-a-real-collection",
                organisation_id=organisation.id,
            )
        )

        assert response.status_code == 404

    @pytest.mark.authenticate_as("test@example-org.com")
    def test_get_404s_for_unknown_organisation(self, authenticated_no_role_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )

        with authenticated_no_role_client.session_transaction() as flask_session:
            flask_session["signing_up_for_collection_id"] = collection.id

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.already_applying",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
                organisation_id=uuid.uuid4(),
            )
        )

        assert response.status_code == 404

    @pytest.mark.parametrize(
        "grant_status, collection_status, allow_public_sign_up",
        (
            (GrantStatusEnum.LIVE, CollectionStatusEnum.OPEN, False),
            (GrantStatusEnum.DRAFT, CollectionStatusEnum.OPEN, True),
            (GrantStatusEnum.ONBOARDING, CollectionStatusEnum.OPEN, True),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.DRAFT, True),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.CLOSED, True),
        ),
    )
    def test_get_depends_on_status_and_allow_public_sign_up(
        self,
        authenticated_no_role_client,
        factories,
        grant_status,
        collection_status,
        allow_public_sign_up,
    ):
        grant = factories.grant.create(status=grant_status, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant,
            status=collection_status,
            allow_public_sign_up=allow_public_sign_up,
            slug="collection-slug",
        )
        organisation = factories.organisation.create()

        with authenticated_no_role_client.session_transaction() as flask_session:
            flask_session["signing_up_for_collection_id"] = collection.id

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.already_applying",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
                organisation_id=organisation.id,
            )
        )

        assert response.status_code == 404

    @pytest.mark.parametrize(
        "grant_status, collection_status",
        (
            (GrantStatusEnum.DRAFT, CollectionStatusEnum.DRAFT),
            (GrantStatusEnum.DRAFT, CollectionStatusEnum.OPEN),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.DRAFT),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.OPEN),
            (GrantStatusEnum.ONBOARDING, CollectionStatusEnum.OPEN),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.CLOSED),
        ),
    )
    def test_deliver_user_testing_access_allowed_for_any_status(
        self, anonymous_client, factories, user, db_session, grant_status, collection_status
    ):
        grant = factories.grant.create(status=grant_status, slug="grant-slug")
        can_manage_grants_organisation = grant.organisation

        collection = factories.collection.create(
            grant=grant,
            status=collection_status,
            allow_public_sign_up=True,
            slug="collection-slug",
        )
        factories.user_role.create(
            user=user, organisation=can_manage_grants_organisation, grant=grant, permissions=[RoleEnum.MEMBER]
        )
        organisation = factories.organisation.create(name="Test Organisation")
        factories.grant_recipient.create(grant=grant, organisation=organisation)

        login_user(user)
        with anonymous_client.session_transaction() as flask_session:
            flask_session["auth"] = AuthMethodEnum.SSO
        db_session.commit()

        response = anonymous_client.get(
            url_for(
                "access_grant_funding.already_applying",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
                organisation_id=organisation.id,
            )
        )

        assert response.status_code == 200

    @pytest.mark.authenticate_as("test@example-org.com")
    def test_get_404s_when_no_grant_recipient_exists_for_organisation(self, authenticated_no_role_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )
        # Organisation exists, but has no grant recipient for this grant
        organisation = factories.organisation.create()

        with authenticated_no_role_client.session_transaction() as flask_session:
            flask_session["signing_up_for_collection_id"] = collection.id

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.already_applying",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
                organisation_id=organisation.id,
            )
        )

        assert response.status_code == 404

    @pytest.mark.authenticate_as("test@example-org.com")
    def test_get_renders_already_applying_content(self, authenticated_no_role_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug", name="Test grant name")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )
        organisation = factories.organisation.create(name="Eastbourne Borough Council")
        factories.grant_recipient.create(grant=grant, organisation=organisation)

        with authenticated_no_role_client.session_transaction() as flask_session:
            flask_session["signing_up_for_collection_id"] = collection.id

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.already_applying",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
                organisation_id=organisation.id,
            )
        )

        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "Your organisation is already applying" in get_h1_text(soup)
        assert "Test grant name" in soup.text
        assert "Eastbourne Borough Council" in soup.text

    def test_get_redirects_when_not_authenticated(self, anonymous_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )
        organisation = factories.organisation.create()

        response = anonymous_client.get(
            url_for(
                "access_grant_funding.already_applying",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
                organisation_id=organisation.id,
            )
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.public_sign_up_start_page", grant_slug=grant.slug, collection_slug=collection.slug
        )

    def test_get_redirects_when_no_session_set(self, authenticated_no_role_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )
        organisation = factories.organisation.create()

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.already_applying",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
                organisation_id=organisation.id,
            )
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.public_sign_up_start_page", grant_slug=grant.slug, collection_slug=collection.slug
        )


class TestPublicSignUpIneligiblePage:
    def test_get_404s_for_unknown_grant(self, authenticated_no_role_client, factories):
        collection = factories.collection.create(slug="collection-slug")

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.public_sign_up_ineligible",
                grant_slug="not-a-real-grant",
                collection_slug=collection.slug,
            )
        )

        assert response.status_code == 404

    def test_get_404s_for_unknown_collection(self, authenticated_no_role_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.public_sign_up_ineligible",
                grant_slug=grant.slug,
                collection_slug="not-a-real-collection",
            )
        )

        assert response.status_code == 404

    @pytest.mark.parametrize(
        "grant_status, collection_status, allow_public_sign_up, expected_status",
        (
            (GrantStatusEnum.LIVE, CollectionStatusEnum.OPEN, True, 302),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.OPEN, False, 404),
            (GrantStatusEnum.DRAFT, CollectionStatusEnum.OPEN, True, 404),
            (GrantStatusEnum.ONBOARDING, CollectionStatusEnum.OPEN, True, 404),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.DRAFT, True, 404),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.CLOSED, True, 404),
        ),
    )
    def test_anonymous_access_depends_on_status_and_allow_public_sign_up(
        self,
        anonymous_client,
        factories,
        grant_status,
        collection_status,
        allow_public_sign_up,
        expected_status,
    ):
        grant = factories.grant.create(status=grant_status, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant,
            status=collection_status,
            allow_public_sign_up=allow_public_sign_up,
            slug="collection-slug",
        )

        response = anonymous_client.get(
            url_for(
                "access_grant_funding.public_sign_up_ineligible",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
            )
        )

        assert response.status_code == expected_status

    @pytest.mark.parametrize(
        "grant_status, collection_status",
        (
            (GrantStatusEnum.DRAFT, CollectionStatusEnum.DRAFT),
            (GrantStatusEnum.DRAFT, CollectionStatusEnum.OPEN),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.DRAFT),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.OPEN),
            (GrantStatusEnum.ONBOARDING, CollectionStatusEnum.OPEN),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.CLOSED),
        ),
    )
    def test_deliver_user_testing_access_allowed_for_any_status(
        self, anonymous_client, factories, user, db_session, grant_status, collection_status
    ):
        grant = factories.grant.create(status=grant_status, slug="grant-slug")
        can_manage_grants_organisation = grant.organisation

        collection = factories.collection.create(
            grant=grant,
            status=collection_status,
            allow_public_sign_up=True,
            slug="collection-slug",
        )
        factories.user_role.create(
            user=user, organisation=can_manage_grants_organisation, grant=grant, permissions=[RoleEnum.MEMBER]
        )

        login_user(user)
        with anonymous_client.session_transaction() as flask_session:
            flask_session["auth"] = AuthMethodEnum.SSO
        db_session.commit()

        response = anonymous_client.get(
            url_for(
                "access_grant_funding.public_sign_up_ineligible",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
            )
        )

        assert response.status_code == 200

    def test_get_redirects_when_not_signed_up(self, authenticated_no_role_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.public_sign_up_ineligible", grant_slug=grant.slug, collection_slug=collection.slug
            )
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.public_sign_up_start_page", grant_slug=grant.slug, collection_slug=collection.slug
        )

    def test_get_with_known_grant_and_collection(self, authenticated_no_role_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug", name="Test grant name")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )

        with authenticated_no_role_client.session_transaction() as flask_session:
            flask_session["signing_up_for_collection_id"] = collection.id

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.public_sign_up_ineligible", grant_slug=grant.slug, collection_slug=collection.slug
            )
        )

        assert response.status_code == 200
        assert "You are not eligible to apply" in response.data.decode()
        assert "Test grant name" in response.data.decode()


class TestPublicSignUpEligibilityQuestion:
    def test_get_redirects_when_not_authenticated(self, anonymous_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )
        eligibility_form = factories.form.create(collection=collection, is_eligibility_section=True)
        question = factories.question.create(form=eligibility_form, data_type=QuestionDataType.NUMBER)

        response = anonymous_client.get(
            url_for(
                "access_grant_funding.public_sign_up_eligibility_question",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
                question_id=question.id,
            )
        )
        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.public_sign_up_start_page", grant_slug=grant.slug, collection_slug=collection.slug
        )

    def test_get_404s_for_unknown_grant(self, authenticated_no_role_client, factories):
        collection = factories.collection.create(slug="collection-slug")

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.public_sign_up_eligibility_question",
                grant_slug="not-a-real-grant",
                collection_slug=collection.slug,
                question_id=uuid.uuid4(),
            )
        )

        assert response.status_code == 404

    def test_get_404s_for_unknown_collection(self, authenticated_no_role_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.public_sign_up_eligibility_question",
                grant_slug=grant.slug,
                collection_slug="not-a-real-collection",
                question_id=uuid.uuid4(),
            )
        )

        assert response.status_code == 404

    @pytest.mark.parametrize(
        "grant_status, collection_status, allow_public_sign_up",
        (
            (GrantStatusEnum.LIVE, CollectionStatusEnum.OPEN, False),
            (GrantStatusEnum.DRAFT, CollectionStatusEnum.OPEN, True),
            (GrantStatusEnum.ONBOARDING, CollectionStatusEnum.OPEN, True),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.DRAFT, True),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.CLOSED, True),
        ),
    )
    def test_get_depends_on_status_and_allow_public_sign_up(
        self,
        authenticated_no_role_client,
        factories,
        grant_status,
        collection_status,
        allow_public_sign_up,
    ):
        grant = factories.grant.create(status=grant_status, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant,
            status=collection_status,
            allow_public_sign_up=allow_public_sign_up,
            slug="collection-slug",
        )
        eligibility_form = factories.form.create(collection=collection, is_eligibility_section=True)
        question = factories.question.create(form=eligibility_form, data_type=QuestionDataType.NUMBER)

        with authenticated_no_role_client.session_transaction() as flask_session:
            flask_session["signing_up_for_collection_id"] = collection.id

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.public_sign_up_eligibility_question",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
                question_id=question.id,
            )
        )

        assert response.status_code == 404

    @pytest.mark.parametrize(
        "grant_status, collection_status",
        (
            (GrantStatusEnum.DRAFT, CollectionStatusEnum.DRAFT),
            (GrantStatusEnum.DRAFT, CollectionStatusEnum.OPEN),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.DRAFT),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.OPEN),
            (GrantStatusEnum.ONBOARDING, CollectionStatusEnum.OPEN),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.CLOSED),
        ),
    )
    def test_deliver_user_testing_access_allowed_for_any_status(
        self, anonymous_client, factories, user, db_session, grant_status, collection_status
    ):
        grant = factories.grant.create(status=grant_status, slug="grant-slug")
        can_manage_grants_organisation = grant.organisation

        collection = factories.collection.create(
            grant=grant,
            status=collection_status,
            allow_public_sign_up=True,
            slug="collection-slug",
        )
        eligibility_form = factories.form.create(collection=collection, is_eligibility_section=True)
        question = factories.question.create(form=eligibility_form, data_type=QuestionDataType.NUMBER)
        factories.user_role.create(
            user=user, organisation=can_manage_grants_organisation, grant=grant, permissions=[RoleEnum.MEMBER]
        )
        factories.organisation.create(
            name="Test Organisation",
            domains=[user.email.split("@")[-1]],
            mode=OrganisationModeEnum.TEST,
        )

        login_user(user)
        with anonymous_client.session_transaction() as flask_session:
            flask_session["auth"] = AuthMethodEnum.SSO
        db_session.commit()

        response = anonymous_client.get(
            url_for(
                "access_grant_funding.public_sign_up_eligibility_question",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
                question_id=question.id,
            )
        )

        assert response.status_code == 200

    def test_get_redirects_when_no_session_set(self, authenticated_no_role_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )
        eligibility_form = factories.form.create(collection=collection, is_eligibility_section=True)
        question = factories.question.create(form=eligibility_form, data_type=QuestionDataType.NUMBER)

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.public_sign_up_eligibility_question",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
                question_id=question.id,
            )
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.public_sign_up_start_page", grant_slug=grant.slug, collection_slug=collection.slug
        )

    def test_404_when_collection_has_no_eligibility_form(self, authenticated_no_role_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )

        with authenticated_no_role_client.session_transaction() as flask_session:
            flask_session["signing_up_for_collection_id"] = collection.id

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.public_sign_up_eligibility_question",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
                question_id=uuid.uuid4(),
            )
        )

        assert response.status_code == 404

    def test_get_renders_question(self, authenticated_no_role_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug", name="Test grant name")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )
        eligibility_form = factories.form.create(collection=collection, is_eligibility_section=True)
        question = factories.question.create(
            form=eligibility_form, data_type=QuestionDataType.NUMBER, text="How many years experience do you have?"
        )

        with authenticated_no_role_client.session_transaction() as flask_session:
            flask_session["signing_up_for_collection_id"] = collection.id

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.public_sign_up_eligibility_question",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
                question_id=question.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "How many years experience do you have?" in soup.text

    def test_get_renders_question_with_reference_to_previous_answer(
        self, authenticated_no_role_client, factories, db_session
    ):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )
        eligibility_form = factories.form.create(collection=collection, is_eligibility_section=True)
        first_question = factories.question.create(
            form=eligibility_form, data_type=QuestionDataType.NUMBER, text="How many years experience do you have?"
        )
        factories.question.create(
            form=eligibility_form,
            text="Confirm your experience",
            guidance_body=(
                f"You told us you have {ExpressionReference.from_question(first_question).wrapped} years experience."
            ),
        )

        with authenticated_no_role_client.session_transaction() as flask_session:
            flask_session["signing_up_for_collection_id"] = collection.id

        FormCls = build_question_form([first_question], ExpressionContext(), ExpressionContext())
        form = FormCls(data={first_question.safe_qid: "5"})

        response = authenticated_no_role_client.post(
            url_for(
                "access_grant_funding.public_sign_up_eligibility_question",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
                question_id=first_question.id,
            ),
            data=get_form_data(form),
            follow_redirects=True,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "You told us you have 5 years experience." in soup.text

    def test_post_fails_eligibility_redirects_to_ineligible(self, authenticated_no_role_client, factories, db_session):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )
        eligibility_form = factories.form.create(collection=collection, is_eligibility_section=True)
        question = factories.question.create(form=eligibility_form, data_type=QuestionDataType.NUMBER)
        add_component_eligibility(
            question,
            authenticated_no_role_client.user,
            GreaterThan(minimum_value=3, subject_reference=ExpressionReference.from_question(question)),
        )

        with authenticated_no_role_client.session_transaction() as flask_session:
            flask_session["signing_up_for_collection_id"] = collection.id

        FormCls = build_question_form([question], ExpressionContext(), ExpressionContext())
        form = FormCls(data={question.safe_qid: "1"})

        response = authenticated_no_role_client.post(
            url_for(
                "access_grant_funding.public_sign_up_eligibility_question",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
                question_id=question.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.public_sign_up_ineligible", grant_slug=grant.slug, collection_slug=collection.slug
        )

    def test_post_passes_eligibility_redirects_to_eligible_to_apply(self, authenticated_no_role_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )
        eligibility_form = factories.form.create(collection=collection, is_eligibility_section=True)
        question = factories.question.create(form=eligibility_form, data_type=QuestionDataType.NUMBER)
        add_component_eligibility(
            question,
            authenticated_no_role_client.user,
            GreaterThan(minimum_value=3, subject_reference=ExpressionReference.from_question(question)),
        )

        with authenticated_no_role_client.session_transaction() as flask_session:
            flask_session["signing_up_for_collection_id"] = collection.id

        FormCls = build_question_form([question], ExpressionContext(), ExpressionContext())
        form = FormCls(data={question.safe_qid: "10"})

        response = authenticated_no_role_client.post(
            url_for(
                "access_grant_funding.public_sign_up_eligibility_question",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
                question_id=question.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug
        )

        # The eligibility form is not marked complete here - only once the submission is claimed
        unclaimed_submission = get_or_create_unclaimed_submission(
            authenticated_no_role_client.user, collection, SubmissionModeEnum.LIVE
        )
        assert unclaimed_submission.events.form_state(eligibility_form.id).is_completed is False
