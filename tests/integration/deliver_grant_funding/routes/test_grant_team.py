import pytest
from bs4 import BeautifulSoup
from flask import url_for

from app.common.data.interfaces.user import get_current_user
from app.common.data.models_user import Invitation
from app.common.data.types import RoleEnum
from tests.models import _get_grant_managing_organisation
from tests.utils import get_h2_text, get_soup_text


class TestGrantTeamListUsers:
    def test_list_users_for_grant_with_platform_admin_and_no_member(
        self, authenticated_platform_admin_client, templates_rendered, factories, mock_notification_service_calls
    ):
        grant = factories.grant.create()
        authenticated_platform_admin_client.get(
            url_for("deliver_grant_funding.list_users_for_grant", grant_id=grant.id)
        )
        users = (
            templates_rendered.get("deliver_grant_funding.list_users_for_grant").context.get("grant").grant_team_users
        )
        assert not users

    @pytest.mark.parametrize(
        "client_fixture,can_add_users",
        [
            ("authenticated_platform_admin_client", True),
            ("authenticated_org_admin_client", True),
            ("authenticated_grant_admin_client", True),
            ("authenticated_grant_member_client", True),
        ],
    )
    def test_list_users_for_grant_check_add_member_button(self, client_fixture, can_add_users, factories, request):
        client = request.getfixturevalue(client_fixture)
        organisation = client.organisation or _get_grant_managing_organisation()
        grant = client.grant or factories.grant.create(organisation=organisation)

        response = client.get(url_for("deliver_grant_funding.list_users_for_grant", grant_id=grant.id))
        soup = BeautifulSoup(response.data, "html.parser")
        add_member_button = soup.find("a", string=lambda text: text and "Add grant team member" in text)

        if can_add_users:
            assert add_member_button is not None, "'Add grant team member' button not found"
        else:
            assert add_member_button is None, "'Add grant team member' button should not be visible"

    def test_list_users_for_grant_with_not_logged_in_members(
        self, authenticated_platform_admin_client, factories, templates_rendered
    ):
        grant = factories.grant.create()
        factories.invitation.create(
            email="test@communities.gov.uk", organisation=grant.organisation, grant=grant, permissions=[RoleEnum.MEMBER]
        )

        response = authenticated_platform_admin_client.get(
            url_for("deliver_grant_funding.list_users_for_grant", grant_id=grant.id)
        )
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Not yet signed in" in get_h2_text(soup)
        assert "test@communities.gov.uk" in get_soup_text(soup, "td")

    def test_list_users_for_grant_with_member(self, authenticated_grant_member_client, templates_rendered, factories):
        grant = factories.grant.create()
        user = get_current_user()
        factories.user_role.create(user=user, permissions=[RoleEnum.MEMBER], grant=grant)
        authenticated_grant_member_client.get(url_for("deliver_grant_funding.list_users_for_grant", grant_id=grant.id))
        users = (
            templates_rendered.get("deliver_grant_funding.list_users_for_grant").context.get("grant").grant_team_users
        )
        assert users
        assert len(users) == 1

    def test_does_not_show_grant_recipient_users(
        self, authenticated_grant_member_client, templates_rendered, factories
    ):
        grant = factories.grant.create()
        user = get_current_user()
        grant_recipient = factories.grant_recipient.create(grant=grant)
        factories.user_role.create(user=user, permissions=[RoleEnum.MEMBER], grant=grant)
        gr_user = factories.user_role.create(
            permissions=[RoleEnum.MEMBER], grant=grant, organisation=grant_recipient.organisation
        ).user
        authenticated_grant_member_client.get(url_for("deliver_grant_funding.list_users_for_grant", grant_id=grant.id))
        users = (
            templates_rendered.get("deliver_grant_funding.list_users_for_grant").context.get("grant").grant_team_users
        )
        assert len(users) == 1
        assert gr_user not in users


class TestGrantTeamAddUser:
    def test_add_user_to_grant_with_platform_admin_add_another_platform_admin(
        self, authenticated_platform_admin_client, templates_rendered, factories, mock_notification_service_calls
    ):
        grant = factories.grant.create()
        current_user = get_current_user()
        authenticated_platform_admin_client.post(
            url_for("deliver_grant_funding.add_user_to_grant", grant_id=grant.id),
            json={"user_email": current_user.email.upper()},
            follow_redirects=True,
        )
        form_errors = templates_rendered.get("deliver_grant_funding.add_user_to_grant").context.get("form").errors
        assert form_errors
        assert "user_email" in form_errors
        assert form_errors["user_email"][0] == f'This user already is an admin of "{grant.name}" so you cannot add them'

    @pytest.mark.parametrize(
        "client_fixture",
        [
            "authenticated_platform_admin_client",
            "authenticated_org_admin_client",
            "authenticated_grant_admin_client",
            "authenticated_grant_member_client",
        ],
    )
    def test_add_user_to_grant_add_member(
        self, client_fixture, templates_rendered, factories, mock_notification_service_calls, request
    ):
        client = request.getfixturevalue(client_fixture)
        grant = client.grant or factories.grant.create()

        client.post(
            url_for("deliver_grant_funding.add_user_to_grant", grant_id=grant.id),
            json={"user_email": "test1@communities.gov.uk"},
            follow_redirects=True,
        )
        invitations = (
            templates_rendered.get("deliver_grant_funding.list_users_for_grant").context.get("grant").invitations
        )
        assert invitations
        assert len(invitations) == 1

    @pytest.mark.parametrize(
        "client_fixture",
        [
            "authenticated_platform_admin_client",
            "authenticated_org_admin_client",
            "authenticated_grant_admin_client",
        ],
    )
    def test_add_user_to_grant_add_same_member_again(
        self, client_fixture, templates_rendered, factories, mock_notification_service_calls, request
    ):
        client = request.getfixturevalue(client_fixture)
        grant = client.grant or factories.grant.create()

        user = factories.user.create(email="test1.member@communities.gov.uk")
        factories.user_role.create(user=user, grant=grant, permissions=[RoleEnum.MEMBER])
        client.post(
            url_for("deliver_grant_funding.add_user_to_grant", grant_id=grant.id),
            json={"user_email": "Test1.Member@Communities.gov.uk"},
            follow_redirects=True,
        )
        form_errors = templates_rendered.get("deliver_grant_funding.add_user_to_grant").context.get("form").errors
        assert form_errors
        assert "user_email" in form_errors
        assert form_errors["user_email"][0] == f'This user already is a member of "{grant.name}" so you cannot add them'

    def test_add_user_to_grant_creates_invitation_for_new_user(
        self, authenticated_grant_admin_client, db_session, factories, mock_notification_service_calls
    ):
        grant = authenticated_grant_admin_client.grant

        authenticated_grant_admin_client.post(
            url_for("deliver_grant_funding.add_user_to_grant", grant_id=grant.id),
            json={"user_email": "test1@communities.gov.uk"},
            follow_redirects=True,
        )

        usable_invites_from_db = db_session.query(Invitation).where(Invitation.is_usable.is_(True)).all()
        assert len(usable_invites_from_db) == 1
        assert (
            usable_invites_from_db[0].email == "test1@communities.gov.uk"
            and usable_invites_from_db[0].grant_id == grant.id
            and RoleEnum.MEMBER in usable_invites_from_db[0].permissions
        )

    def test_add_user_to_grant_adds_existing_user_no_invitation(
        self, authenticated_grant_admin_client, db_session, factories, mock_notification_service_calls
    ):
        grant = authenticated_grant_admin_client.grant

        user = factories.user.create(email="test1@communities.gov.uk")
        authenticated_grant_admin_client.post(
            url_for("deliver_grant_funding.add_user_to_grant", grant_id=grant.id),
            json={"user_email": "test1@communities.gov.uk"},
            follow_redirects=True,
        )
        usable_invites_from_db = db_session.query(Invitation).where(Invitation.is_usable.is_(True)).all()
        assert not usable_invites_from_db
        assert len(user.roles) == 1
        assert user.roles[0].grant_id == grant.id and RoleEnum.MEMBER in user.roles[0].permissions
