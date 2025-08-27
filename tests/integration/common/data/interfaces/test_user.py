from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.common.data import interfaces
from app.common.data.interfaces.exceptions import InvalidUserRoleError
from app.common.data.models_user import Invitation, User, UserRole
from app.common.data.types import RoleEnum
from tests.integration.utils import TimeFreezer

freeze_time_format = TimeFreezer.time_format


class TestCreateMagicLink:
    def test_create_magic_link_existing_user(self, db_session, factories):
        user = factories.user.create(azure_ad_subject_id=None)

        magic_link = interfaces.magic_link.create_magic_link(email=user.email, user=user, redirect_to_path="/")

        assert magic_link.user == user

    def test_create_magic_link_new_user(self, db_session, factories):
        user_email = "new_user@email.com"
        user_from_db = db_session.scalar(select(User).where(User.email == user_email))
        assert user_from_db is None

        magic_link = interfaces.magic_link.create_magic_link(email=user_email, user=None, redirect_to_path="/")

        assert magic_link.user is None

    @pytest.mark.freeze_time("2024-10-01 12:00:00")
    def test_create_magic_link_check_expiry_time(self, db_session, factories):
        user = factories.user.create(azure_ad_subject_id=None)

        magic_link = interfaces.magic_link.create_magic_link(email=user.email, user=user, redirect_to_path="/")

        should_expire_at = datetime.strptime("2024-10-01 12:00:00", freeze_time_format) + timedelta(minutes=15)
        assert magic_link.expires_at_utc == should_expire_at

    @pytest.mark.freeze_time("2024-10-01 10:00:00")
    def test_create_magic_link_expires_other_magic_links_for_the_user(self, db_session, factories, time_freezer):
        old_magic_link = factories.magic_link.create()
        assert old_magic_link.expires_at_utc == datetime.strptime("2024-10-01 10:15:00", freeze_time_format)

        # update now by 5 minutes
        time_freezer.update_frozen_time(timedelta(minutes=5))

        new_magic_link = interfaces.magic_link.create_magic_link(
            email=old_magic_link.email, user=None, redirect_to_path="/"
        )

        assert old_magic_link.expires_at_utc == datetime.strptime("2024-10-01 10:05:00", freeze_time_format)
        assert new_magic_link.expires_at_utc == datetime.strptime("2024-10-01 10:20:00", freeze_time_format)


class TestGetMagicLink:
    def test_get_magic_link_by_id(self, db_session, factories):
        magic_link = factories.magic_link.create()

        retrieved_magic_link = interfaces.magic_link.get_magic_link(id_=magic_link.id)

        assert magic_link is retrieved_magic_link

    def test_get_magic_link_by_code(self, db_session, factories):
        magic_link = factories.magic_link.create()

        retrieved_magic_link = interfaces.magic_link.get_magic_link(code=magic_link.code)

        assert magic_link is retrieved_magic_link


class TestClaimMagicLink:
    @pytest.mark.freeze_time("2024-10-01 10:00:00")
    def test_claim_magic_link_success(self, db_session, factories):
        magic_link = factories.magic_link.create()
        assert magic_link.claimed_at_utc is None
        assert magic_link.user is None
        assert magic_link.is_usable is True

        user = factories.user.create()
        interfaces.magic_link.claim_magic_link(magic_link, user)

        assert magic_link.claimed_at_utc == datetime.strptime("2024-10-01 10:00:00", freeze_time_format)
        assert magic_link.user == user
        assert magic_link.is_usable is False

    def test_claim_magic_link_fail_no_user(self, db_session, factories):
        magic_link = factories.magic_link.create()
        assert magic_link.is_usable is True

        with pytest.raises(ValueError, match="User must be provided"):
            interfaces.magic_link.claim_magic_link(magic_link, user=None)


class TestGetUser:
    def test_get_user_by_id(self, db_session, factories):
        user_id = factories.user.create(email="test@communities.gov.uk").id

        user = interfaces.user.get_user(user_id)
        assert user
        assert user.id == user_id
        assert user.email == "test@communities.gov.uk"


class TestGetUserByEmail:
    def test_get_existing_user(self, db_session, factories):
        factories.user.create(email="Test@communities.gov.uk", name="My Name")
        assert db_session.scalar(select(func.count()).select_from(User)) == 1

        user = interfaces.user.get_user_by_email(email_address="test@communities.gov.uk")
        assert user
        assert user.email == "Test@communities.gov.uk"
        assert user.name == "My Name"

        assert db_session.scalar(select(func.count()).select_from(User)) == 1

    def test_get_user_where_none_exists(self, db_session):
        assert db_session.scalar(select(func.count()).select_from(User)) == 0

        user = interfaces.user.get_user_by_email(email_address="test@communities.gov.uk")
        assert user is None

        assert db_session.scalar(select(func.count()).select_from(User)) == 0


class TestGetUserByAzureAdSubjectId:
    def test_get_existing_user(self, db_session, factories):
        user = factories.user.create(email="Test@communities.gov.uk", name="My Name")
        assert db_session.scalar(select(func.count()).select_from(User)) == 1

        user = interfaces.user.get_user_by_azure_ad_subject_id(azure_ad_subject_id=user.azure_ad_subject_id)
        assert user
        assert user.email == "Test@communities.gov.uk"
        assert user.name == "My Name"

        assert db_session.scalar(select(func.count()).select_from(User)) == 1

    def test_get_user_where_none_exists(self, db_session):
        assert db_session.scalar(select(func.count()).select_from(User)) == 0

        user = interfaces.user.get_user_by_azure_ad_subject_id(azure_ad_subject_id="some_string_value")
        assert user is None
        assert db_session.scalar(select(func.count()).select_from(User)) == 0


class TestSetUserLastLoggedInAt:
    def test_set_user_last_logged_in_at_utc(self, db_session, factories) -> None:
        user = factories.user.create(email="test@communites.gov.uk", last_logged_in_at_utc=None)
        interfaces.user.set_user_last_logged_in_at_utc(user)
        assert user.last_logged_in_at_utc is not None


class TestUpsertUserByEmail:
    def test_create_new_user(self, db_session):
        assert db_session.scalar(select(func.count()).select_from(User)) == 0

        user = interfaces.user.upsert_user_by_email(email_address="test@communities.gov.uk")
        assert user.email == "test@communities.gov.uk"
        assert user.name is None and user.azure_ad_subject_id is None

        assert db_session.scalar(select(func.count()).select_from(User)) == 1

    def test_get_existing_user_with_update(self, db_session, factories):
        factories.user.create(email="test@communities.gov.uk", name="My Name", azure_ad_subject_id=None)
        assert db_session.scalar(select(func.count()).select_from(User)) == 1

        user = interfaces.user.upsert_user_by_email(email_address="test@communities.gov.uk", name="My Name updated")
        assert user.email == "test@communities.gov.uk"
        assert user.name == "My Name updated"
        assert user.azure_ad_subject_id is None

        assert db_session.scalar(select(func.count()).select_from(User)) == 1


class TestUpsertUserByAzureAdSubjectId:
    def test_create_new_user(self, db_session):
        assert db_session.scalar(select(func.count()).select_from(User)) == 0

        user = interfaces.user.upsert_user_by_azure_ad_subject_id(
            azure_ad_subject_id="some_example_string", email_address="test@communities.gov.uk"
        )
        assert user.email == "test@communities.gov.uk"
        assert user.azure_ad_subject_id == "some_example_string"
        assert user.name is None

        assert db_session.scalar(select(func.count()).select_from(User)) == 1

    def test_get_existing_user_with_update(self, db_session, factories):
        factory_user = factories.user.create(email="test@communities.gov.uk", name="My Name")
        assert db_session.scalar(select(func.count()).select_from(User)) == 1

        user = interfaces.user.upsert_user_by_azure_ad_subject_id(
            azure_ad_subject_id=factory_user.azure_ad_subject_id,
            email_address="updated@communities.gov.uk",
            name="My Name updated",
        )
        assert user.email == "updated@communities.gov.uk"
        assert user.name == "My Name updated"

        assert db_session.scalar(select(func.count()).select_from(User)) == 1


class TestUpsertUserRole:
    @pytest.mark.parametrize(
        "organisation, grant, role",
        [
            (False, False, RoleEnum.ADMIN),
            (True, False, RoleEnum.MEMBER),
        ],
    )
    def test_add_user_role(self, db_session, factories, organisation, grant, role):
        # This test checks a few happy paths - the tests in test_constraints check against the table's constraints at
        # the DB level and additional tests will be added to check these errors are raised correctly once a custom
        # exception is created for this.
        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 0
        user = factories.user.create(email="test@communities.gov.uk")
        organisation_id = factories.organisation.create().id
        grant_id = factories.grant.create().id

        organisation_id_value = organisation_id if organisation else None
        grant_id_value = grant_id if grant else None

        user_role = interfaces.user.upsert_user_role(
            user=user, organisation_id=organisation_id_value, grant_id=grant_id_value, role=role
        )
        assert user_role.user_id == user.id
        assert (user_role.user_id, user_role.organisation_id, user_role.grant_id, user_role.role) == (
            user.id,
            organisation_id_value,
            grant_id_value,
            role,
        )

        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 1

    def test_multiple_roles_treated_as_distinct_and_dont_overwrite(self, db_session, factories):
        # Make sure that the handling of nulls on the constraint, and the upsert behaviour of `upsert_user_role`
        # will definitely create new roles on any mismatch between user_id/organisation_id/grant_id.
        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 0
        user = factories.user.create(email="test@communities.gov.uk")
        organisation = factories.organisation.create()
        grant = factories.grant.create()

        interfaces.user.upsert_user_role(
            user=user, organisation_id=organisation.id, grant_id=grant.id, role=RoleEnum.MEMBER
        )
        interfaces.user.upsert_user_role(
            user=user, organisation_id=organisation.id, grant_id=None, role=RoleEnum.MEMBER
        )
        interfaces.user.upsert_user_role(user=user, organisation_id=None, grant_id=grant.id, role=RoleEnum.ADMIN)
        interfaces.user.upsert_user_role(user=user, organisation_id=None, grant_id=None, role=RoleEnum.ADMIN)

        user_roles = db_session.query(UserRole).all()
        assert {(ur.user_id, ur.organisation_id, ur.grant_id, ur.role) for ur in user_roles} == {
            (user.id, organisation.id, grant.id, RoleEnum.MEMBER),
            (user.id, organisation.id, None, RoleEnum.MEMBER),
            (user.id, None, grant.id, RoleEnum.ADMIN),
            (user.id, None, None, RoleEnum.ADMIN),
        }

    def test_add_existing_user_role(self, db_session, factories):
        user = factories.user.create(email="test@communities.gov.uk")
        interfaces.user.upsert_user_role(user=user, role=RoleEnum.ADMIN)

        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 1

        user_role = interfaces.user.upsert_user_role(user=user, role=RoleEnum.ADMIN)
        assert user_role.user_id == user.id
        assert (user_role.organisation_id, user_role.grant_id) == (None, None)
        assert user_role.role == RoleEnum.ADMIN

        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 1

    def test_upsert_existing_user_role(self, db_session, factories):
        user = factories.user.create(email="test@communities.gov.uk")
        grant = factories.grant.create()
        interfaces.user.upsert_user_role(user=user, grant_id=grant.id, role=RoleEnum.MEMBER)

        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 1

        user_role = interfaces.user.upsert_user_role(user=user, grant_id=grant.id, role=RoleEnum.ADMIN)
        assert user_role.user == user
        assert (user_role.organisation_id, user_role.grant_id) == (None, grant.id)
        assert user_role.role == RoleEnum.ADMIN

        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 1

    @pytest.mark.parametrize(
        "organisation, grant, role, message",
        [
            (False, False, RoleEnum.MEMBER, "A 'member' role must be linked to an organisation or grant."),
        ],
    )
    def test_add_invalid_user_role(self, factories, organisation, grant, role, message) -> None:
        user = factories.user.create(email="test@communities.gov.uk")
        organisation_id = factories.organisation.create().id
        grant_id = factories.grant.create().id

        organisation_id_value = organisation_id if organisation else None
        grant_id_value = grant_id if grant else None

        with pytest.raises(InvalidUserRoleError) as error:
            interfaces.user.upsert_user_role(
                user=user,
                organisation_id=organisation_id_value,
                grant_id=grant_id_value,
                role=role,
            )
        assert isinstance(error.value, InvalidUserRoleError)
        assert error.value.message == message


class TestSetUserRoleInterfaces:
    def test_set_platform_admin_role_for_user(self, db_session, factories) -> None:
        user = factories.user.create(email="test@communities.gov.uk")
        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 0

        platform_admin_role = interfaces.user.set_platform_admin_role_for_user(user=user)
        assert platform_admin_role.user_id == user.id
        assert len(user.roles) == 1

        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 1

    def test_set_platform_admin_role_already_exists(self, db_session, factories) -> None:
        user = factories.user.create(email="test@communities.gov.uk")
        factories.user_role.create(user=user, role=RoleEnum.ADMIN)
        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 1

        platform_admin_role = interfaces.user.set_platform_admin_role_for_user(user=user)
        assert platform_admin_role.user_id == user.id

        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 1

    def test_set_platform_admin_multiple_roles_already_exists(self, db_session, factories) -> None:
        user = factories.user.create(email="test@communities.gov.uk")
        factories.user_role.create(user=user, role=RoleEnum.ADMIN)
        grant = factories.grant.create()
        factories.user_role.create(user=user, grant=grant, role=RoleEnum.MEMBER)
        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 2

        platform_admin_role = interfaces.user.set_platform_admin_role_for_user(user=user)
        assert platform_admin_role.user_id == user.id

        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 1

    def test_set_grant_team_role_for_user(self, db_session, factories) -> None:
        user = factories.user.create(email="test@communities.gov.uk")
        grant = factories.grant.create()
        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 0

        grant_team_role = interfaces.user.set_grant_team_role_for_user(user=user, grant=grant, role=RoleEnum.MEMBER)
        assert grant_team_role.grant_id == grant.id and grant_team_role.user_id == user.id
        assert len(user.roles) == 1

        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 1

    def test_set_grant_team_role_already_exists(self, db_session, factories) -> None:
        user = factories.user.create(email="test@communities.gov.uk")
        grant = factories.grant.create()
        factories.user_role.create(user=user, grant=grant, role=RoleEnum.MEMBER)
        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 1

        grant_team_role = interfaces.user.set_grant_team_role_for_user(user=user, grant=grant, role=RoleEnum.MEMBER)
        assert grant_team_role.user_id == user.id and grant_team_role.grant_id == grant.id

        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 1


class TestRemoveUserRoleInterfaces:
    def test_remove_platform_admin_role_from_user(self, db_session, factories) -> None:
        user = factories.user.create(email="test@communities.gov.uk")
        factories.user_role.create(user=user, role=RoleEnum.ADMIN)
        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 1

        interfaces.user.remove_platform_admin_role_from_user(user)
        assert user.roles == []

        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 0

    def test_remove_platform_admin_role_when_only_other_roles_exist(self, db_session, factories) -> None:
        user = factories.user.create(email="test@communities.gov.uk")
        grant = factories.grant.create()
        factories.user_role.create(user=user, grant=grant, role=RoleEnum.MEMBER)
        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 1

        interfaces.user.remove_platform_admin_role_from_user(user)
        assert len(user.roles) == 1
        assert user.roles[0].role == RoleEnum.MEMBER and user.roles[0].grant_id == grant.id

        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 1

    def test_remove_grant_team_role_from_user(self, db_session, factories) -> None:
        user = factories.user.create(email="test@communities.gov.uk")
        grant = factories.grant.create()
        factories.user_role.create(user=user, grant=grant, role=RoleEnum.MEMBER)
        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 1

        interfaces.user.remove_grant_team_role_from_user(user, grant_id=grant.id)
        assert user.roles == []

        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 0

    def test_remove_grant_team_role_from_user_with_multiple_roles(self, db_session, factories) -> None:
        user = factories.user.create(email="test@communities.gov.uk")
        grants = factories.grant.create_batch(2)
        for grant in grants:
            factories.user_role.create(user=user, role=RoleEnum.MEMBER, grant=grant)
        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 2

        interfaces.user.remove_grant_team_role_from_user(user, grant_id=grants[0].id)
        assert len(user.roles) == 1
        assert user.roles[0].role == RoleEnum.MEMBER and user.roles[0].grant_id == grants[1].id

        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 1

    def test_remove_all_roles_from_user(self, db_session, factories) -> None:
        user = factories.user.create(email="test@communities.gov.uk")
        factories.user_role.create(user=user, role=RoleEnum.ADMIN)
        grants = factories.grant.create_batch(2)
        for grant in grants:
            factories.user_role.create(user=user, role=RoleEnum.MEMBER, grant=grant)
        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 3

        interfaces.user.remove_all_roles_from_user(user)
        assert user.roles == []

        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 0


class TestInvitations:
    @pytest.mark.freeze_time("2023-10-01 12:00:00")
    def test_create_invitation(self, db_session, factories):
        invitation = interfaces.user.create_invitation(email="test@email.com", role=RoleEnum.MEMBER)
        invite_from_db = db_session.get(Invitation, invitation.id)
        assert invite_from_db is not None
        assert invite_from_db.email == "test@email.com"
        assert invite_from_db.role == RoleEnum.MEMBER
        assert invite_from_db.expires_at_utc == datetime.strptime("2023-10-08 12:00:00", freeze_time_format)
        assert invite_from_db.claimed_at_utc is None
        assert invite_from_db.grant_id is None
        assert invite_from_db.organisation_id is None
        assert invite_from_db.is_usable is True

    @pytest.mark.freeze_time("2023-10-01 12:00:00")
    def test_create_invitation_expires_existing_invitations(self, db_session, factories) -> None:
        grant = factories.grant.create()
        factories.invitation.create(email="test@communities.gov.uk", grant=grant, role=RoleEnum.MEMBER)
        invite_from_db = db_session.scalars(select(Invitation).where(Invitation.is_usable.is_(True))).all()
        assert len(invite_from_db) == 1
        new_invitation = interfaces.user.create_invitation(
            email="test@communities.gov.uk", grant=grant, role=RoleEnum.MEMBER
        )
        usable_invite_from_db = db_session.scalars(select(Invitation).where(Invitation.is_usable.is_(True))).all()
        assert len(usable_invite_from_db) == 1
        assert new_invitation.id == usable_invite_from_db[0].id

    def test_create_invitation_expires_existing_invitations_when_org_grant_null(self, db_session, factories) -> None:
        grant = factories.grant.create()
        organisation = factories.organisation.create()
        grant_only_invitation = factories.invitation.create(
            email="test@communities.gov.uk", grant=grant, role=RoleEnum.MEMBER
        )
        organisation_only_invitation = factories.invitation.create(
            email="test@communities.gov.uk", organisation=organisation, role=RoleEnum.MEMBER
        )

        invite_from_db = db_session.scalars(select(Invitation).where(Invitation.is_usable.is_(True))).all()
        assert len(invite_from_db) == 2

        new_grant_invitation = interfaces.user.create_invitation(
            email="test@communities.gov.uk", grant=grant, role=RoleEnum.MEMBER
        )

        new_organisation_invitation = interfaces.user.create_invitation(
            email="test@communities.gov.uk", organisation=organisation, role=RoleEnum.MEMBER
        )

        usable_invites_from_db = db_session.scalars(select(Invitation).where(Invitation.is_usable.is_(True))).all()
        assert len(usable_invites_from_db) == 2
        assert new_grant_invitation and new_organisation_invitation in usable_invites_from_db
        assert grant_only_invitation and organisation_only_invitation not in usable_invites_from_db

    @pytest.mark.freeze_time("2025-10-01 12:00:00")
    def test_get_invitation(self, db_session, factories):
        invitation = factories.invitation.create(role=RoleEnum.MEMBER, email="test@email.com")
        invite_from_db = interfaces.user.get_invitation(invitation.id)
        assert invite_from_db is not None
        assert invite_from_db.is_usable is True
        assert invite_from_db.email == "test@email.com"
        assert invite_from_db.role == RoleEnum.MEMBER
        assert invite_from_db.expires_at_utc == datetime.strptime("2025-10-08 12:00:00", freeze_time_format)

    @pytest.mark.freeze_time("2025-10-01 12:00:00")
    def test_claim_invitation(self, db_session, factories):
        user = factories.user.create(email="new_user@email.com")
        invitation = factories.invitation.create(role=RoleEnum.MEMBER, email="new_user@email.com")
        assert invitation.claimed_at_utc is None
        assert invitation.is_usable is True

        claimed_invitation = interfaces.user.claim_invitation(invitation, user)
        assert claimed_invitation.claimed_at_utc == datetime.strptime("2025-10-01 12:00:00", freeze_time_format)
        assert claimed_invitation.is_usable is False
        assert claimed_invitation.user == user

    @pytest.mark.freeze_time("2025-10-01 12:00:00")
    def test_get_usable_invitations_by_email(self, db_session, factories) -> None:
        grants = factories.grant.create_batch(5)

        # Create an expired invitation to check it isn't returned
        expired_invitation = factories.invitation.create(
            email="test@communities.gov.uk",
            grant=grants[-1],
            role=RoleEnum.MEMBER,
            expires_at_utc=datetime(2025, 9, 1, 12, 0, 0),
        )

        # Create an already claimed invitation to check it isn't returned
        claimed_invitation = factories.invitation.create(
            email="test@communities.gov.uk",
            grant=grants[-2],
            role=RoleEnum.MEMBER,
            expires_at_utc=datetime(2025, 10, 4, 12, 0, 0),
            claimed_at_utc=datetime(2025, 9, 30, 12, 0, 0),
        )

        for grant in grants[:3]:
            factories.invitation.create(email="test@communities.gov.uk", grant=grant, role=RoleEnum.MEMBER)

        usable_invitations = interfaces.user.get_usable_invitations_by_email(email="test@communities.gov.uk")
        assert len(usable_invitations) == 3
        assert expired_invitation and claimed_invitation not in usable_invitations

    def test_create_user_and_claim_invitations(self, db_session, factories) -> None:
        grants = factories.grant.create_batch(3)
        invitations = []
        for grant in grants:
            invitation = factories.invitation.create(email="test@communities.gov.uk", grant=grant, role=RoleEnum.MEMBER)
            invitations.append(invitation)

        # Create an invitation for a different user to make sure it doesn't get claimed
        factories.invitation.create(email="different_email@communities.gov.uk", grant=grant, role=RoleEnum.MEMBER)

        interfaces.user.create_user_and_claim_invitations(
            azure_ad_subject_id="oih12373",
            email_address="test@communities.gov.uk",
            name="Test User",
        )

        usable_invites_from_db = db_session.scalars(select(Invitation).where(Invitation.is_usable.is_(True))).all()
        assert (
            len(usable_invites_from_db) == 1 and usable_invites_from_db[0].email == "different_email@communities.gov.uk"
        )

        user_from_db = db_session.scalar(select(User).where(User.azure_ad_subject_id == "oih12373"))
        assert len(user_from_db.roles) == 3

    def test_grant_member_add_role_or_create_invitation_adds_role(self, db_session, factories) -> None:
        grant = factories.grant.create()
        user = factories.user.create(email="test@communities.gov.uk")
        interfaces.user.add_grant_member_role_or_create_invitation(email_address="test@communities.gov.uk", grant=grant)

        assert db_session.scalar(select(func.count()).select_from(Invitation)) == 0
        assert len(user.roles) == 1 and user.roles[0].grant_id == grant.id and user.roles[0].role == RoleEnum.MEMBER

    def test_grant_member_add_role_or_create_invitation_creates_invitation(self, db_session, factories) -> None:
        grant = factories.grant.create()
        interfaces.user.add_grant_member_role_or_create_invitation(email_address="test@communities.gov.uk", grant=grant)
        assert db_session.scalar(select(func.count()).select_from(Invitation)) == 1
        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 0
        assert db_session.scalar(select(func.count()).select_from(User)) == 0
        invite_from_db = db_session.scalar(select(Invitation).where(Invitation.is_usable.is_(True)))
        assert invite_from_db.grant_id == grant.id and invite_from_db.role == RoleEnum.MEMBER

    def test_upsert_platform_admin_user_and_set_platform_admin_role_claims_invitations(
        self, db_session, factories
    ) -> None:
        grants = factories.grant.create_batch(3)
        for grant in grants:
            factories.invitation.create(email="test@communities.gov.uk", grant=grant, role=RoleEnum.MEMBER)

        factories.invitation.create(email="different_email@communities.gov.uk", grant=grants[0], role=RoleEnum.MEMBER)

        interfaces.user.upsert_user_and_set_platform_admin_role(
            azure_ad_subject_id="oih12373", email_address="test@communities.gov.uk", name="User Name"
        )

        usable_invites_from_db = db_session.scalars(select(Invitation).where(Invitation.is_usable.is_(True))).all()
        assert (
            len(usable_invites_from_db) == 1 and usable_invites_from_db[0].email == "different_email@communities.gov.uk"
        )

        user_from_db = db_session.scalar(select(User).where(User.azure_ad_subject_id == "oih12373"))
        assert len(user_from_db.roles) == 1
        user_from_db_role = user_from_db.roles[0]
        assert user_from_db_role.role == RoleEnum.ADMIN
        assert (user_from_db_role.organisation_id, user_from_db_role.grant_id) == (None, None)
