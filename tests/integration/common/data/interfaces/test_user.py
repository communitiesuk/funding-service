import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.common.data import interfaces
from app.common.data.interfaces.exceptions import InvalidUserRoleError
from app.common.data.models_audit import AuditEvent as AuditEventModel
from app.common.data.models_user import Invitation, User, UserRole
from app.common.data.types import AuditEventType, GrantRecipientModeEnum, OrganisationModeEnum, RoleEnum
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

    def test_create_magic_link_with_collection(self, factories):
        collection = factories.collection.create()

        magic_link = interfaces.magic_link.create_magic_link(
            email="new_user@email.com", user=None, redirect_to_path="/", collection=collection
        )

        assert magic_link.collection == collection


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
        "organisation, grant, permissions",
        [
            (False, False, [RoleEnum.ADMIN, RoleEnum.MEMBER]),
            (True, False, [RoleEnum.MEMBER]),
        ],
    )
    def test_add_user_role(self, db_session, factories, organisation, grant, permissions):
        # This test checks a few happy paths - the tests in test_constraints check against the table's constraints at
        # the DB level and additional tests will be added to check these errors are raised correctly once a custom
        # exception is created for this.
        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 0
        user = factories.user.create(email="test@communities.gov.uk")
        organisation_id = factories.organisation.create().id
        grant_id = factories.grant.create().id

        organisation_id_value = organisation_id if organisation else None
        grant_id_value = grant_id if grant else None

        user_role = interfaces.user._upsert_user_role(
            user=user,
            organisation_id=organisation_id_value,
            grant_id=grant_id_value,
            permissions=permissions,
        )
        assert user_role.user_id == user.id
        assert (user_role.user_id, user_role.organisation_id, user_role.grant_id, user_role.permissions) == (
            user.id,
            organisation_id_value,
            grant_id_value,
            permissions,
        )

        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 1

    def test_multiple_roles_treated_as_distinct_and_dont_overwrite(self, db_session, factories):
        # Make sure that the handling of nulls on the constraint, and the upsert behaviour of `upsert_user_role`
        # will definitely create new roles on any mismatch between user_id/organisation_id/grant_id.
        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 0
        user = factories.user.create(email="test@communities.gov.uk")
        organisation = factories.organisation.create()
        grant = factories.grant.create()

        interfaces.user._upsert_user_role(
            user=user, organisation_id=organisation.id, grant_id=grant.id, permissions=[RoleEnum.ADMIN, RoleEnum.MEMBER]
        )
        interfaces.user._upsert_user_role(
            user=user, organisation_id=organisation.id, grant_id=None, permissions=[RoleEnum.MEMBER]
        )

        user_roles = db_session.query(UserRole).all()
        assert {
            (ur.user_id, ur.organisation_id, ur.grant_id, frozenset(r for r in ur.permissions)) for ur in user_roles
        } == {
            (user.id, organisation.id, grant.id, frozenset((RoleEnum.ADMIN, RoleEnum.MEMBER))),
            (
                user.id,
                organisation.id,
                None,
                frozenset(
                    (RoleEnum.MEMBER,),
                ),
            ),
        }

    def test_add_existing_user_role(self, db_session, factories):
        user = factories.user.create(email="test@communities.gov.uk")
        interfaces.user._upsert_user_role(user=user, permissions=[RoleEnum.ADMIN, RoleEnum.MEMBER])

        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 1

        user_role = interfaces.user._upsert_user_role(user=user, permissions=[RoleEnum.ADMIN, RoleEnum.MEMBER])
        assert user_role.user_id == user.id
        assert (user_role.organisation_id, user_role.grant_id) == (None, None)
        assert RoleEnum.ADMIN in user_role.permissions

        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 1

    def test_upsert_existing_user_role(self, db_session, factories):
        user = factories.user.create(email="test@communities.gov.uk")
        grant = factories.grant.create()
        interfaces.user._upsert_user_role(
            user=user, organisation_id=grant.organisation.id, grant_id=grant.id, permissions=[RoleEnum.MEMBER]
        )

        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 1

        user_role = interfaces.user._upsert_user_role(
            user=user,
            organisation_id=grant.organisation.id,
            grant_id=grant.id,
            permissions=[RoleEnum.ADMIN, RoleEnum.MEMBER],
        )
        assert user_role.user == user
        assert (user_role.organisation_id, user_role.grant_id) == (grant.organisation.id, grant.id)
        assert RoleEnum.ADMIN in user_role.permissions

        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 1

    @pytest.mark.parametrize(
        "organisation, grant, permissions, message",
        [
            (
                False,
                False,
                [RoleEnum.CERTIFIER],
                "The 'member' role must always be present",
            ),
            (
                False,
                False,
                [RoleEnum.MEMBER, RoleEnum.CERTIFIER],
                "Non-'admin' roles must be linked to an organisation or grant.",
            ),
        ],
    )
    def test_add_invalid_user_permissions(self, factories, organisation, grant, permissions, message) -> None:
        user = factories.user.create(email="test@communities.gov.uk")
        organisation_id = factories.organisation.create().id
        grant_id = factories.grant.create().id

        organisation_id_value = organisation_id if organisation else None
        grant_id_value = grant_id if grant else None

        with pytest.raises(InvalidUserRoleError) as error:
            interfaces.user._upsert_user_role(
                user=user,
                organisation_id=organisation_id_value,
                grant_id=grant_id_value,
                permissions=permissions,
            )
        assert isinstance(error.value, InvalidUserRoleError)
        assert error.value.message == message


class TestRemoveUserRoleInterfaces:
    def test_remove_all_roles_from_user(self, db_session, factories) -> None:
        user = factories.user.create(email="test@communities.gov.uk")
        factories.user_role.create(user=user, permissions=[RoleEnum.ADMIN])
        grants = factories.grant.create_batch(2)
        for grant in grants:
            factories.user_role.create(user=user, permissions=[RoleEnum.MEMBER], grant=grant)
        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 3

        interfaces.user.remove_all_roles_from_user(user)
        assert user.roles == []

        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 0


class TestInvitations:
    @pytest.mark.freeze_time("2023-10-01 12:00:00")
    def test_create_invitation(self, db_session, factories):
        organisation = factories.organisation.create()
        inviting_user = factories.user.create()
        invitation = interfaces.user.create_invitation(
            email="test@email.com",
            organisation=organisation,
            permissions=[RoleEnum.MEMBER],
            name="Test User",
            by_user=inviting_user,
        )
        invite_from_db = db_session.get(Invitation, invitation.id)
        assert invite_from_db is not None
        assert invite_from_db.email == "test@email.com"
        assert invite_from_db.name == "Test User"
        assert RoleEnum.MEMBER in invite_from_db.permissions
        assert invite_from_db.expires_at_utc == datetime.strptime("2023-10-08 12:00:00", freeze_time_format)
        assert invite_from_db.claimed_at_utc is None
        assert invite_from_db.grant_id is None
        assert invite_from_db.organisation_id == organisation.id
        assert invite_from_db.is_usable is True

        audit_event = db_session.scalars(select(AuditEventModel)).one()
        assert audit_event.event_type == AuditEventType.USER_MANAGEMENT
        assert audit_event.user_id == inviting_user.id
        assert audit_event.data["action"] == "user_invited"
        assert audit_event.data["invitation_id"] == str(invitation.id)
        assert audit_event.data["organisation_id"] == str(organisation.id)
        assert audit_event.data["grant_id"] is None
        assert audit_event.data["grant_recipient_id"] is None
        assert audit_event.data["permissions"] == [RoleEnum.MEMBER.value]

    @pytest.mark.freeze_time("2023-10-01 12:00:00")
    def test_create_invitation_requires_org_if_grant_set(self, db_session, factories) -> None:
        grant = factories.grant.create()
        with pytest.raises(ValueError) as e:
            interfaces.user.create_invitation(
                email="test@communities.gov.uk",
                grant=grant,
                permissions=[RoleEnum.MEMBER],
                by_user=factories.user.build(),
            )
        assert "If specifying grant, must also specify organisation" in str(e.value)

    @pytest.mark.freeze_time("2023-10-01 12:00:00")
    def test_create_invitation_expires_existing_invitations(self, db_session, factories) -> None:
        grant = factories.grant.create()
        factories.invitation.create(
            email="test@communities.gov.uk", organisation=grant.organisation, grant=grant, permissions=[RoleEnum.MEMBER]
        )
        invite_from_db = db_session.scalars(select(Invitation).where(Invitation.is_usable.is_(True))).all()
        assert len(invite_from_db) == 1
        new_invitation = interfaces.user.create_invitation(
            email="test@communities.gov.uk",
            organisation=grant.organisation,
            grant=grant,
            permissions=[RoleEnum.MEMBER],
            by_user=factories.user.create(),
        )
        usable_invite_from_db = db_session.scalars(select(Invitation).where(Invitation.is_usable.is_(True))).all()
        assert len(usable_invite_from_db) == 1
        assert new_invitation.id == usable_invite_from_db[0].id

    @pytest.mark.freeze_time("2025-10-01 12:00:00")
    def test_get_invitation(self, db_session, factories):
        organisation = factories.organisation.create()
        invitation = factories.invitation.create(
            organisation=organisation, permissions=[RoleEnum.MEMBER], email="test@email.com"
        )
        invite_from_db = interfaces.user.get_invitation(invitation.id)
        assert invite_from_db is not None
        assert invite_from_db.is_usable is True
        assert invite_from_db.email == "test@email.com"
        assert RoleEnum.MEMBER in invite_from_db.permissions
        assert invite_from_db.expires_at_utc == datetime.strptime("2025-10-08 12:00:00", freeze_time_format)

    @pytest.mark.freeze_time("2025-10-01 12:00:00")
    def test_claim_invitation(self, db_session, factories):
        user = factories.user.create(email="new_user@email.com")
        organisation = factories.organisation.create()
        invitation = factories.invitation.create(
            organisation=organisation, permissions=[RoleEnum.MEMBER], email="new_user@email.com"
        )
        assert invitation.claimed_at_utc is None
        assert invitation.is_usable is True

        claimed_invitation = interfaces.user.claim_invitation(invitation, user)
        assert claimed_invitation.claimed_at_utc == datetime.strptime("2025-10-01 12:00:00", freeze_time_format)
        assert claimed_invitation.is_usable is False
        assert claimed_invitation.user == user

    @pytest.mark.freeze_time("2025-10-01 12:00:00")
    def test_claim_invitation_adds_test_grant_recipient_roles(self, db_session, factories):
        from tests.models import _get_grant_managing_organisation

        mhclg = _get_grant_managing_organisation()
        grant = factories.grant.create(organisation=mhclg)
        test_recipient_org = factories.organisation.create(can_manage_grants=False, mode=OrganisationModeEnum.TEST)
        test_grant_recipient = factories.grant_recipient.create(
            grant=grant, organisation=test_recipient_org, mode=GrantRecipientModeEnum.TEST
        )

        user = factories.user.create(email="new_user@email.com")
        invitation = factories.invitation.create(
            organisation=mhclg, grant=grant, permissions=[RoleEnum.MEMBER], email="new_user@email.com"
        )

        interfaces.user.claim_invitation(invitation, user)

        test_recipient_role = interfaces.user.get_user_role(user, test_recipient_org.id, test_grant_recipient.grant_id)
        assert test_recipient_role is not None
        assert RoleEnum.DATA_PROVIDER in test_recipient_role.permissions
        assert RoleEnum.CERTIFIER in test_recipient_role.permissions

        audit_event = db_session.scalars(select(AuditEventModel)).one()
        assert audit_event.data["invitation_id"] == str(invitation.id)
        assert audit_event.data["grant_recipient_id"] == str(test_grant_recipient.id)

    @pytest.mark.freeze_time("2025-10-01 12:00:00")
    def test_claim_invitation_skips_test_roles_for_non_grant_managing_org(self, db_session, factories):
        non_managing_org = factories.organisation.create(can_manage_grants=False)
        grant = factories.grant.create(organisation=non_managing_org)
        test_recipient_org = factories.organisation.create(can_manage_grants=False, mode=OrganisationModeEnum.TEST)
        factories.grant_recipient.create(grant=grant, organisation=test_recipient_org, mode=GrantRecipientModeEnum.TEST)

        user = factories.user.create(email="new_user@email.com")
        invitation = factories.invitation.create(
            organisation=non_managing_org, grant=grant, permissions=[RoleEnum.MEMBER], email="new_user@email.com"
        )

        interfaces.user.claim_invitation(invitation, user)

        test_recipient_role = interfaces.user.get_user_role(user, test_recipient_org.id, grant.id)
        assert test_recipient_role is None

    @pytest.mark.freeze_time("2025-10-01 12:00:00")
    def test_claim_invitation_skips_test_roles_when_no_grant(self, db_session, factories):
        from tests.models import _get_grant_managing_organisation

        mhclg = _get_grant_managing_organisation()

        user = factories.user.create(email="new_user@email.com")
        invitation = factories.invitation.create(
            organisation=mhclg, grant=None, permissions=[RoleEnum.MEMBER], email="new_user@email.com"
        )

        interfaces.user.claim_invitation(invitation, user)

        assert len(user.roles) == 0

    @pytest.mark.freeze_time("2025-10-01 12:00:00")
    def test_claim_invitation_skips_test_roles_when_no_test_grant_recipients(self, db_session, factories):
        from tests.models import _get_grant_managing_organisation

        mhclg = _get_grant_managing_organisation()
        grant = factories.grant.create(organisation=mhclg)
        live_recipient_org = factories.organisation.create(can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=live_recipient_org, mode=GrantRecipientModeEnum.LIVE)

        user = factories.user.create(email="new_user@email.com")
        invitation = factories.invitation.create(
            organisation=mhclg, grant=grant, permissions=[RoleEnum.MEMBER], email="new_user@email.com"
        )

        interfaces.user.claim_invitation(invitation, user)

        test_recipient_role = interfaces.user.get_user_role(user, live_recipient_org.id, grant.id)
        assert test_recipient_role is None

    @pytest.mark.freeze_time("2025-10-01 12:00:00")
    def test_get_invitations_by_email(self, db_session, factories) -> None:
        grants = factories.grant.create_batch(5)

        # Create an expired invitation to check it isn't returned
        expired_invitation = factories.invitation.create(
            email="test@communities.gov.uk",
            organisation=grants[-1].organisation,
            grant=grants[-1],
            permissions=[RoleEnum.MEMBER],
            expires_at_utc=datetime(2025, 9, 1, 12, 0, 0),
        )

        # Create an already claimed invitation to check it isn't returned
        claimed_invitation = factories.invitation.create(
            email="test@communities.gov.uk",
            organisation=grants[-2].organisation,
            grant=grants[-2],
            permissions=[RoleEnum.MEMBER],
            expires_at_utc=datetime(2025, 10, 4, 12, 0, 0),
            claimed_at_utc=datetime(2025, 9, 30, 12, 0, 0),
        )

        for grant in grants[:3]:
            factories.invitation.create(
                email="test@communities.gov.uk",
                organisation=grant.organisation,
                grant=grant,
                permissions=[RoleEnum.MEMBER],
            )

        usable_invitations = interfaces.user.get_invitations_by_email(email="test@communities.gov.uk", is_usable=True)
        assert len(usable_invitations) == 3
        assert expired_invitation not in usable_invitations
        assert claimed_invitation not in usable_invitations

        unusable_invitations = interfaces.user.get_invitations_by_email(
            email="test@communities.gov.uk", is_usable=False
        )
        assert len(unusable_invitations) == 2
        assert expired_invitation in unusable_invitations
        assert claimed_invitation in unusable_invitations

        all_invitations = interfaces.user.get_invitations_by_email(
            email="test@communities.gov.uk",
        )
        assert len(all_invitations) == 5

    def test_create_user_and_claim_invitations(self, db_session, factories) -> None:
        grants = factories.grant.create_batch(3)
        invitations = []
        for grant in grants:
            invitation = factories.invitation.create(
                email="test@communities.gov.uk",
                organisation=grant.organisation,
                grant=grant,
                permissions=[RoleEnum.MEMBER],
            )
            invitations.append(invitation)

        # Create an invitation for a different user to make sure it doesn't get claimed
        factories.invitation.create(
            email="different_email@communities.gov.uk",
            organisation=grant.organisation,
            grant=grant,
            permissions=[RoleEnum.MEMBER],
        )

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

    def test_create_user_and_claim_invitations_records_invitation_on_audit_event(self, db_session, factories) -> None:
        grant = factories.grant.create()
        invitation = factories.invitation.create(
            email="test@communities.gov.uk", organisation=grant.organisation, grant=grant, permissions=[RoleEnum.MEMBER]
        )

        user = interfaces.user.create_user_and_claim_invitations(
            azure_ad_subject_id="oih12373", email_address="test@communities.gov.uk", name="Test User"
        )

        audit_event = db_session.scalars(select(AuditEventModel)).one()
        assert audit_event.user_id == user.id
        assert audit_event.data["target_user_id"] == str(user.id)
        assert audit_event.data["invitation_id"] == str(invitation.id)

    def test_grant_member_add_role_or_create_invitation_adds_role(self, db_session, factories) -> None:
        grant = factories.grant.create()
        user = factories.user.create(email="test@communities.gov.uk")
        interfaces.user.add_grant_member_role_or_create_invitation(
            email_address="test@communities.gov.uk", grant=grant, by_user=user
        )

        assert db_session.scalar(select(func.count()).select_from(Invitation)) == 0
        assert (
            len(user.roles) == 1 and user.roles[0].grant_id == grant.id and RoleEnum.MEMBER in user.roles[0].permissions
        )

    def test_grant_member_add_role_or_create_invitation_adds_test_grant_recipient_roles(
        self, db_session, factories
    ) -> None:
        grant = factories.grant.create()
        test_recipient_org = factories.organisation.create(can_manage_grants=False, mode=OrganisationModeEnum.TEST)
        test_grant_recipient = factories.grant_recipient.create(
            grant=grant, organisation=test_recipient_org, mode=GrantRecipientModeEnum.TEST
        )

        user = factories.user.create(email="test@communities.gov.uk")
        interfaces.user.add_grant_member_role_or_create_invitation(
            email_address="test@communities.gov.uk", grant=grant, by_user=user
        )

        grant_team_role = interfaces.user.get_user_role(user, grant.organisation_id, grant.id)
        assert grant_team_role is not None
        assert RoleEnum.MEMBER in grant_team_role.permissions

        test_recipient_role = interfaces.user.get_user_role(user, test_recipient_org.id, test_grant_recipient.grant_id)
        assert test_recipient_role is not None
        assert RoleEnum.DATA_PROVIDER in test_recipient_role.permissions
        assert RoleEnum.CERTIFIER in test_recipient_role.permissions

    def test_grant_member_add_role_or_create_invitation_skips_test_roles_when_no_test_recipients(
        self, db_session, factories
    ) -> None:
        grant = factories.grant.create()
        live_recipient_org = factories.organisation.create(can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=live_recipient_org, mode=GrantRecipientModeEnum.LIVE)

        user = factories.user.create(email="test@communities.gov.uk")
        interfaces.user.add_grant_member_role_or_create_invitation(
            email_address="test@communities.gov.uk", grant=grant, by_user=user
        )

        assert len(user.roles) == 1
        assert user.roles[0].grant_id == grant.id
        assert RoleEnum.MEMBER in user.roles[0].permissions

    def test_grant_member_add_role_or_create_invitation_creates_invitation(self, db_session, factories) -> None:
        grant = factories.grant.create()
        inviting_user = factories.user.create()
        interfaces.user.add_grant_member_role_or_create_invitation(
            email_address="test@communities.gov.uk", grant=grant, by_user=inviting_user
        )
        assert db_session.scalar(select(func.count()).select_from(Invitation)) == 1
        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 0
        assert db_session.scalar(select(User).where(User.email == "test@communities.gov.uk")) is None
        invite_from_db = db_session.scalar(select(Invitation).where(Invitation.is_usable.is_(True)))
        assert invite_from_db.grant_id == grant.id and RoleEnum.MEMBER in invite_from_db.permissions

        audit_event = db_session.scalars(select(AuditEventModel)).one()
        assert audit_event.user_id == inviting_user.id
        assert audit_event.data["action"] == "user_invited"
        assert audit_event.data["invitation_id"] == str(invite_from_db.id)
        assert audit_event.data["grant_id"] == str(grant.id)
        assert audit_event.data["grant_recipient_id"] is None

    def test_upsert_platform_admin_user_and_set_platform_admin_role_claims_invitations(
        self, db_session, factories
    ) -> None:
        grants = factories.grant.create_batch(3)
        for grant in grants:
            factories.invitation.create(
                email="test@communities.gov.uk",
                organisation=grant.organisation,
                grant=grant,
                permissions=[RoleEnum.MEMBER],
            )

        factories.invitation.create(
            email="different_email@communities.gov.uk",
            organisation=grants[0].organisation,
            grant=grants[0],
            permissions=[RoleEnum.MEMBER],
        )

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
        assert RoleEnum.ADMIN in user_from_db_role.permissions
        assert (user_from_db_role.organisation_id, user_from_db_role.grant_id) == (None, None)

        audit_event = db_session.scalars(select(AuditEventModel)).one()
        assert audit_event.event_type == AuditEventType.USER_MANAGEMENT


class TestUserGrantRelationships:
    def test_deliver_grants_direct_grant_access(self, db_session, factories):
        from tests.models import _get_grant_managing_organisation

        mhclg = _get_grant_managing_organisation()
        grant = factories.grant.create(organisation=mhclg)
        user = factories.user.create(email="test@communities.gov.uk")
        factories.user_role.create(user=user, organisation=mhclg, grant=grant, permissions=[RoleEnum.MEMBER])

        assert len(user.deliver_grants) == 1
        assert user.deliver_grants[0].id == grant.id
        assert len(user.access_grants) == 0

    def test_deliver_grants_organisation_level_access(self, db_session, factories):
        from tests.models import _get_grant_managing_organisation

        mhclg = _get_grant_managing_organisation()
        grant1 = factories.grant.create(organisation=mhclg)
        grant2 = factories.grant.create(organisation=mhclg)
        user = factories.user.create(email="test@communities.gov.uk")
        factories.user_role.create(user=user, organisation=mhclg, grant=None, permissions=[RoleEnum.ADMIN])

        assert len(user.deliver_grants) == 2
        assert {g.id for g in user.deliver_grants} == {grant1.id, grant2.id}
        assert len(user.access_grants) == 0

    def test_access_grants_direct_grant_access(self, db_session, factories):
        from tests.models import _get_grant_managing_organisation

        recipient_org = factories.organisation.create(can_manage_grants=False)
        mhclg = _get_grant_managing_organisation()
        grant = factories.grant.create(organisation=mhclg)
        factories.grant_recipient.create(grant=grant, organisation=recipient_org)
        user = factories.user.create(email="test@communities.gov.uk")
        factories.user_role.create(user=user, organisation=recipient_org, grant=grant, permissions=[RoleEnum.MEMBER])

        assert len(user.access_grants) == 1
        assert user.access_grants[0].id == grant.id
        assert len(user.deliver_grants) == 0

    def test_access_grants_organisation_level_access(self, db_session, factories):
        from tests.models import _get_grant_managing_organisation

        recipient_org = factories.organisation.create(can_manage_grants=False)
        mhclg = _get_grant_managing_organisation()
        grant1 = factories.grant.create(organisation=mhclg)
        grant2 = factories.grant.create(organisation=mhclg)
        factories.grant_recipient.create(grant=grant1, organisation=recipient_org)
        factories.grant_recipient.create(grant=grant2, organisation=recipient_org)
        user = factories.user.create(email="test@communities.gov.uk")
        factories.user_role.create(user=user, organisation=recipient_org, grant=None, permissions=[RoleEnum.ADMIN])

        assert len(user.access_grants) == 2
        assert {g.id for g in user.access_grants} == {grant1.id, grant2.id}
        assert len(user.deliver_grants) == 0

    def test_user_with_both_deliver_and_access_grants(self, db_session, factories):
        from tests.models import _get_grant_managing_organisation

        mhclg = _get_grant_managing_organisation()
        recipient_org = factories.organisation.create(can_manage_grants=False)
        deliver_grant = factories.grant.create(organisation=mhclg)
        access_grant = factories.grant.create(organisation=mhclg)
        factories.grant_recipient.create(grant=access_grant, organisation=recipient_org)
        user = factories.user.create(email="test@communities.gov.uk")
        factories.user_role.create(user=user, organisation=mhclg, grant=deliver_grant, permissions=[RoleEnum.MEMBER])
        factories.user_role.create(
            user=user, organisation=recipient_org, grant=access_grant, permissions=[RoleEnum.MEMBER]
        )

        assert len(user.deliver_grants) == 1
        assert user.deliver_grants[0].id == deliver_grant.id
        assert len(user.access_grants) == 1
        assert user.access_grants[0].id == access_grant.id

    def test_no_grants_for_user_without_roles(self, db_session, factories):
        user = factories.user.create(email="test@communities.gov.uk")

        assert len(user.deliver_grants) == 0
        assert len(user.access_grants) == 0

    def test_platform_admin_does_not_populate_deliver_or_access_grants(self, db_session, factories):
        from tests.models import _get_grant_managing_organisation

        mhclg = _get_grant_managing_organisation()
        recipient_org = factories.organisation.create(can_manage_grants=False)
        factories.grant.create(organisation=mhclg)
        access_grant = factories.grant.create(organisation=mhclg)
        factories.grant_recipient.create(grant=access_grant, organisation=recipient_org)
        user = factories.user.create(email="test@communities.gov.uk")
        factories.user_role.create(user=user, organisation=None, grant=None, permissions=[RoleEnum.ADMIN])

        assert len(user.deliver_grants) == 0
        assert len(user.access_grants) == 0

    def test_grant_recipients_direct_grant_access(self, db_session, factories):
        from tests.models import _get_grant_managing_organisation

        mhclg = _get_grant_managing_organisation()

        recipient_org = factories.organisation.create(can_manage_grants=False)
        grant1 = factories.grant.create(organisation=mhclg)
        grant2 = factories.grant.create(organisation=mhclg)
        factories.grant_recipient.create(grant=grant1, organisation=recipient_org)
        factories.grant_recipient.create(grant=grant2, organisation=recipient_org)
        user = factories.user.create(email="test@communities.gov.uk")
        factories.user_role.create(user=user, organisation=recipient_org, grant=grant1, permissions=[RoleEnum.MEMBER])
        factories.user_role.create(user=user, organisation=recipient_org, grant=grant2, permissions=[RoleEnum.MEMBER])

        assert len(user.get_grant_recipients()) == 2
        assert {g.grant.id for g in user.get_grant_recipients()} == {grant1.id, grant2.id}
        assert {g.organisation.id for g in user.get_grant_recipients()} == {recipient_org.id, recipient_org.id}
        assert len(user.deliver_grants) == 0

    def test_grant_recipients_organisation_level_access(self, db_session, factories):
        from tests.models import _get_grant_managing_organisation

        recipient_org = factories.organisation.create(can_manage_grants=False)
        mhclg = _get_grant_managing_organisation()
        grant1 = factories.grant.create(organisation=mhclg)
        grant2 = factories.grant.create(organisation=mhclg)
        factories.grant_recipient.create(grant=grant1, organisation=recipient_org)
        factories.grant_recipient.create(grant=grant2, organisation=recipient_org)
        user = factories.user.create(email="test@communities.gov.uk")
        factories.user_role.create(user=user, organisation=recipient_org, grant=None, permissions=[RoleEnum.ADMIN])

        assert len(user.get_grant_recipients()) == 2
        assert {g.grant.id for g in user.get_grant_recipients()} == {grant1.id, grant2.id}
        assert {g.organisation.id for g in user.get_grant_recipients()} == {recipient_org.id, recipient_org.id}
        assert len(user.deliver_grants) == 0

    def test_grant_recipients_mixed_grant_access(self, db_session, factories):
        from tests.models import _get_grant_managing_organisation

        recipient_org = factories.organisation.create(can_manage_grants=False)
        recipient_org2 = factories.organisation.create(can_manage_grants=False)
        mhclg = _get_grant_managing_organisation()
        grant1 = factories.grant.create(organisation=mhclg)
        grant2 = factories.grant.create(organisation=mhclg)
        grant3 = factories.grant.create(organisation=mhclg)
        factories.grant_recipient.create(grant=grant1, organisation=recipient_org)
        factories.grant_recipient.create(grant=grant2, organisation=recipient_org)
        factories.grant_recipient.create(grant=grant3, organisation=recipient_org2)
        user = factories.user.create(email="test@communities.gov.uk")
        factories.user_role.create(user=user, organisation=recipient_org, grant=None, permissions=[RoleEnum.MEMBER])
        factories.user_role.create(user=user, organisation=recipient_org2, grant=grant3, permissions=[RoleEnum.MEMBER])

        assert len(user.get_grant_recipients()) == 3
        assert {g.grant.id for g in user.get_grant_recipients()} == {grant1.id, grant2.id, grant3.id}
        assert {g.organisation.id for g in user.get_grant_recipients()} == {
            recipient_org.id,
            recipient_org.id,
            recipient_org2.id,
        }

        assert {g.grant.id for g in user.get_grant_recipients(limit_to_organisation_id=recipient_org.id)} == {
            grant1.id,
            grant2.id,
        }
        assert {g.grant.id for g in user.get_grant_recipients(limit_to_organisation_id=recipient_org2.id)} == {
            grant3.id
        }
        assert len(user.deliver_grants) == 0

    def test_grant_recipients_filters(self, db_session, factories):
        grant_recipient_member_org1 = factories.grant_recipient.create()
        grant_recipient_member_org2 = factories.grant_recipient.create()

        user = factories.user.create(email="test@communities.gov.uk")
        factories.user_role.create(
            user=user,
            organisation=grant_recipient_member_org1.organisation,
            grant=grant_recipient_member_org1.grant,
            permissions=[RoleEnum.MEMBER],
        )
        factories.user_role.create(
            user=user,
            organisation=grant_recipient_member_org2.organisation,
            grant=grant_recipient_member_org2.grant,
            permissions=[RoleEnum.MEMBER],
        )

        assert len(user.get_grant_recipients()) == 2
        assert user.get_grant_recipients(limit_to_organisation_id=grant_recipient_member_org1.organisation.id) == [
            grant_recipient_member_org1
        ]
        assert user.get_grant_recipients(limit_to_organisation_id=grant_recipient_member_org2.organisation.id) == [
            grant_recipient_member_org2
        ]
        assert user.get_grant_recipients(limit_to_organisation_id=uuid.uuid4()) == []

    def test_grant_recipients_sorted_alphabetically_by_organisation_name(self, db_session, factories):
        grant = factories.grant.create()
        org_c = factories.organisation.create(name="CCCC Organisation", can_manage_grants=False)
        org_a = factories.organisation.create(name="AAAA Organisation", can_manage_grants=False)
        org_b = factories.organisation.create(name="BBBB Organisation", can_manage_grants=False)

        grant_recipient_c = factories.grant_recipient.create(grant=grant, organisation=org_c)
        grant_recipient_a = factories.grant_recipient.create(grant=grant, organisation=org_a)
        grant_recipient_b = factories.grant_recipient.create(grant=grant, organisation=org_b)

        user = factories.user.create(email="test@communities.gov.uk")
        for grant_recipient in (grant_recipient_c, grant_recipient_a, grant_recipient_b):
            factories.user_role.create(
                user=user,
                organisation=grant_recipient.organisation,
                grant=grant,
                permissions=[RoleEnum.MEMBER],
            )

        assert user.get_grant_recipients() == [grant_recipient_a, grant_recipient_b, grant_recipient_c]


class TestGetOrganisations:
    def test_returns_organisations_user_has_a_role_for(self, factories):
        user = factories.user.create()
        org = factories.organisation.create(name="Org 1")
        interfaces.user.add_permissions_to_user(user, permissions=[RoleEnum.MEMBER], organisation=org, by_user=user)

        result = user.get_organisations()

        assert len(result) == 1
        assert result[0].id == org.id

    def test_returns_empty_list_when_user_has_no_organisation_roles(self, factories):
        user = factories.user.create()

        assert user.get_organisations() == []

    def test_does_not_return_organisations_for_other_users(self, factories):
        user = factories.user.create()
        other_user = factories.user.create()
        org = factories.organisation.create(name="Org 1")
        interfaces.user.add_permissions_to_user(
            other_user, permissions=[RoleEnum.MEMBER], organisation=org, by_user=user
        )

        assert user.get_organisations() == []

    def test_respects_mode_filter(self, factories):
        user = factories.user.create()
        live_org = factories.organisation.create(name="Live Org", mode=OrganisationModeEnum.LIVE)
        test_org = factories.organisation.create(name="Test Org", mode=OrganisationModeEnum.TEST)
        interfaces.user.add_permissions_to_user(
            user, permissions=[RoleEnum.MEMBER], organisation=live_org, by_user=user
        )
        interfaces.user.add_permissions_to_user(
            user, permissions=[RoleEnum.MEMBER], organisation=test_org, by_user=user
        )

        result = user.get_organisations(mode=OrganisationModeEnum.TEST)

        assert len(result) == 1
        assert result[0].id == test_org.id

    def test_deduplicates_organisation_with_multiple_roles(self, factories):
        user = factories.user.create()
        org = factories.organisation.create(name="Org 1")
        grant = factories.grant.create(organisation=org)
        interfaces.user.add_permissions_to_user(user, permissions=[RoleEnum.MEMBER], organisation=org, by_user=user)
        interfaces.user.add_permissions_to_user(
            user, permissions=[RoleEnum.MEMBER], organisation=org, grant=grant, by_user=user
        )

        result = user.get_organisations()

        assert len(result) == 1
        assert result[0].id == org.id


class TestGetUsersWithPermission:
    def test_returns_users_with_specific_permission(self, factories, db_session):
        user1 = factories.user.create(email="certifier@test.com")
        user2 = factories.user.create(email="member@test.com")
        organisation = factories.organisation.create()
        factories.user_role.create(user=user1, organisation=organisation, permissions=[RoleEnum.CERTIFIER])
        factories.user_role.create(user=user2, organisation=organisation, permissions=[RoleEnum.MEMBER])

        result = list(interfaces.user.get_users_with_permission(RoleEnum.CERTIFIER))

        assert len(result) == 1
        assert result[0].id == user1.id

    def test_filters_by_organisation_id(self, factories, db_session):
        user1 = factories.user.create(email="user1@test.com")
        user2 = factories.user.create(email="user2@test.com")
        org1 = factories.organisation.create()
        org2 = factories.organisation.create()
        factories.user_role.create(user=user1, organisation=org1, permissions=[RoleEnum.MEMBER])
        factories.user_role.create(user=user2, organisation=org2, permissions=[RoleEnum.MEMBER])

        result = list(interfaces.user.get_users_with_permission(RoleEnum.MEMBER, organisation_id=org1.id))

        assert len(result) == 1
        assert result[0].id == user1.id

    def test_filters_by_organisation_id_and_grant_id(self, factories, db_session):
        user1 = factories.user.create(email="user1@test.com")
        user2 = factories.user.create(email="user2@test.com")
        grant = factories.grant.create()
        factories.user_role.create(
            user=user1, organisation=grant.organisation, grant=grant, permissions=[RoleEnum.MEMBER]
        )
        factories.user_role.create(user=user2, organisation=grant.organisation, permissions=[RoleEnum.MEMBER])

        result = list(
            interfaces.user.get_users_with_permission(
                RoleEnum.MEMBER, organisation_id=grant.organisation.id, grant_id=grant.id
            )
        )

        assert len(result) == 1
        assert result[0].id == user1.id

    def test_handles_not_provided_vs_explicit_none(self, factories, db_session):
        user1 = factories.user.create(email="user1@test.com")
        user2 = factories.user.create(email="user2@test.com")
        org = factories.organisation.create()
        factories.user_role.create(user=user1, organisation=org, permissions=[RoleEnum.ADMIN])
        factories.user_role.create(user=user2, permissions=[RoleEnum.ADMIN])

        result_not_provided = list(interfaces.user.get_users_with_permission(RoleEnum.ADMIN))
        result_explicit_none = list(interfaces.user.get_users_with_permission(RoleEnum.ADMIN, organisation_id=None))

        assert len(result_not_provided) == 2
        assert len(result_explicit_none) == 1
        assert result_explicit_none[0].id == user2.id

    def test_filters_by_organisation_mode(self, factories, db_session):
        live_org = factories.organisation.create(with_matching_test_org=True)
        test_org = live_org.matching_test_organisation
        live_user = factories.user.create(email="live@test.com")
        test_user = factories.user.create(email="test@test.com")
        factories.user_role.create(user=live_user, organisation=live_org, permissions=[RoleEnum.CERTIFIER])
        factories.user_role.create(user=test_user, organisation=test_org, permissions=[RoleEnum.CERTIFIER])

        result = list(
            interfaces.user.get_users_with_permission(RoleEnum.CERTIFIER, organisation_mode=OrganisationModeEnum.LIVE)
        )

        assert len(result) == 1
        assert result[0].id == live_user.id

    def test_organisation_mode_not_provided_returns_all(self, factories, db_session):
        live_org = factories.organisation.create(with_matching_test_org=True)
        test_org = live_org.matching_test_organisation
        live_user = factories.user.create(email="live@test.com")
        test_user = factories.user.create(email="test@test.com")
        factories.user_role.create(user=live_user, organisation=live_org, permissions=[RoleEnum.CERTIFIER])
        factories.user_role.create(user=test_user, organisation=test_org, permissions=[RoleEnum.CERTIFIER])

        result = list(interfaces.user.get_users_with_permission(RoleEnum.CERTIFIER))

        assert len(result) == 2


class TestGetUserRole:
    def test_returns_matching_organisation_level_role(self, factories, db_session):
        user = factories.user.create()
        organisation = factories.organisation.create()
        role = factories.user_role.create(user=user, organisation=organisation, permissions=[RoleEnum.MEMBER])

        result = interfaces.user.get_user_role(user, organisation.id, None)

        assert result.id == role.id

    def test_returns_matching_grant_level_role(self, factories, db_session):
        user = factories.user.create()
        grant = factories.grant.create()
        role = factories.user_role.create(
            user=user, organisation=grant.organisation, grant=grant, permissions=[RoleEnum.MEMBER]
        )

        result = interfaces.user.get_user_role(user, grant.organisation.id, grant.id)

        assert result.id == role.id

    def test_returns_none_when_no_matching_role(self, factories, db_session):
        user = factories.user.create()
        organisation = factories.organisation.create()

        result = interfaces.user.get_user_role(user, organisation.id, None)

        assert result is None


class TestAddPermissionsToUser:
    def test_adds_permissions_to_existing_role(self, factories, db_session):
        user = factories.user.create()
        organisation = factories.organisation.create()
        factories.user_role.create(user=user, organisation=organisation, permissions=[RoleEnum.MEMBER])

        role = interfaces.user.add_permissions_to_user(user, [RoleEnum.CERTIFIER], organisation, by_user=user)

        assert set(role.permissions) == {RoleEnum.MEMBER, RoleEnum.CERTIFIER}

    def test_creates_role_when_none_exists(self, factories, db_session):
        user = factories.user.create()
        organisation = factories.organisation.create()

        role = interfaces.user.add_permissions_to_user(user, [RoleEnum.MEMBER], organisation, by_user=user)

        assert role.permissions == [RoleEnum.MEMBER]

    def test_handles_duplicate_permissions(self, factories, db_session):
        user = factories.user.create()
        organisation = factories.organisation.create()
        factories.user_role.create(
            user=user, organisation=organisation, permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER]
        )

        role = interfaces.user.add_permissions_to_user(user, [RoleEnum.DATA_PROVIDER], organisation, by_user=user)

        assert set(role.permissions) == {RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER}

    def test_always_adds_member_role(self, factories, db_session):
        user = factories.user.create()
        organisation = factories.organisation.create()
        factories.user_role.create(user=user, organisation=organisation, permissions=[RoleEnum.DATA_PROVIDER])

        role = interfaces.user.add_permissions_to_user(user, [RoleEnum.ADMIN], organisation, by_user=user)

        assert set(role.permissions) == {RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER, RoleEnum.ADMIN}

    def test_tracks_audit_event_for_access_grant_recipient_user(self, factories, db_session):
        grant_recipient = factories.grant_recipient.create()
        user = factories.user.create()
        admin = factories.user.create()

        interfaces.user.add_permissions_to_user(
            user, [RoleEnum.DATA_PROVIDER], grant_recipient.organisation, grant_recipient.grant, by_user=admin
        )

        audit_event = db_session.scalars(select(AuditEventModel)).one()
        assert audit_event.event_type == AuditEventType.USER_MANAGEMENT

    def test_audit_event_records_only_newly_added_permissions(self, factories, db_session):
        grant_recipient = factories.grant_recipient.create()
        user = factories.user.create()
        factories.user_role.create(
            user=user,
            organisation=grant_recipient.organisation,
            grant=grant_recipient.grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.CERTIFIER],
        )

        interfaces.user.add_permissions_to_user(
            user,
            [RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
            grant_recipient.organisation,
            grant_recipient.grant,
            by_user=user,
        )

        audit_event = db_session.scalars(select(AuditEventModel)).one()
        assert audit_event.data["permissions"] == ["data-provider"]
        assert set(audit_event.data["resulting_permissions"]) == {"certifier", "data-provider", "member"}

    def test_audit_event_records_member_permission_when_role_is_created(self, factories, db_session):
        grant = factories.grant.create()
        user = factories.user.create()

        interfaces.user.add_permissions_to_user(user, [RoleEnum.MEMBER], grant.organisation, grant, by_user=user)

        audit_event = db_session.scalars(select(AuditEventModel)).one()
        assert audit_event.data["permissions"] == ["member"]
        assert audit_event.data["resulting_permissions"] == ["member"]

    def test_does_not_track_audit_event_when_permissions_are_unchanged(self, factories, db_session):
        grant_recipient = factories.grant_recipient.create()
        user = factories.user.create()
        factories.user_role.create(
            user=user,
            organisation=grant_recipient.organisation,
            grant=grant_recipient.grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )

        interfaces.user.add_permissions_to_user(
            user, [RoleEnum.DATA_PROVIDER], grant_recipient.organisation, grant_recipient.grant, by_user=user
        )

        assert db_session.scalars(select(AuditEventModel)).all() == []

    def test_tracks_organisation_wide_audit_event_without_a_grant(self, factories, db_session):
        organisation = factories.organisation.create(can_manage_grants=False)
        user = factories.user.create()

        interfaces.user.add_permissions_to_user(user, [RoleEnum.CERTIFIER], organisation, by_user=user)

        audit_event = db_session.scalars(select(AuditEventModel)).one()
        assert audit_event.data["organisation_id"] == str(organisation.id)
        assert audit_event.data["grant_id"] is None
        assert audit_event.data["grant_recipient_id"] is None
        assert set(audit_event.data["permissions"]) == {"certifier", "member"}
        assert set(audit_event.data["resulting_permissions"]) == {"certifier", "member"}

    def test_tracks_deliver_grant_team_audit_event_without_a_grant_recipient(self, factories, db_session):
        grant = factories.grant.create()
        user = factories.user.create()

        interfaces.user.add_permissions_to_user(user, [RoleEnum.ADMIN], grant.organisation, grant, by_user=user)

        audit_event = db_session.scalars(select(AuditEventModel)).one()
        assert audit_event.data["organisation_id"] == str(grant.organisation.id)
        assert audit_event.data["grant_id"] == str(grant.id)
        assert audit_event.data["grant_recipient_id"] is None
        assert set(audit_event.data["permissions"]) == {"admin", "member"}
        assert set(audit_event.data["resulting_permissions"]) == {"admin", "member"}

    def test_tracks_platform_wide_audit_event_without_an_organisation(self, factories, db_session):
        user = factories.user.create()

        interfaces.user.add_permissions_to_user(user, [RoleEnum.ADMIN], by_user=user)

        audit_event = db_session.scalars(select(AuditEventModel)).one()
        assert audit_event.data["organisation_id"] is None
        assert audit_event.data["grant_id"] is None
        assert audit_event.data["grant_recipient_id"] is None
        assert audit_event.data["invitation_id"] is None
        assert set(audit_event.data["permissions"]) == {"admin", "member"}
        assert set(audit_event.data["resulting_permissions"]) == {"admin", "member"}


class TestRemovePermissionsFromUser:
    def test_removes_permissions_from_existing_role(self, factories, db_session):
        user = factories.user.create()
        organisation = factories.organisation.create()
        factories.user_role.create(
            user=user, organisation=organisation, permissions=[RoleEnum.MEMBER, RoleEnum.CERTIFIER]
        )

        role = interfaces.user.remove_permissions_from_user(user, [RoleEnum.CERTIFIER], organisation, by_user=user)

        assert role.permissions == [RoleEnum.MEMBER]

    def test_handles_removing_nonexistent_permission(self, factories, db_session):
        user = factories.user.create()
        organisation = factories.organisation.create()
        factories.user_role.create(user=user, organisation=organisation, permissions=[RoleEnum.MEMBER])

        role = interfaces.user.remove_permissions_from_user(user, [RoleEnum.CERTIFIER], organisation, by_user=user)

        assert role.permissions == [RoleEnum.MEMBER]

    def test_leaves_other_permissions_intact(self, factories, db_session):
        user = factories.user.create()
        organisation = factories.organisation.create()
        factories.user_role.create(
            user=user,
            organisation=organisation,
            permissions=[RoleEnum.MEMBER, RoleEnum.CERTIFIER, RoleEnum.DATA_PROVIDER],
        )

        role = interfaces.user.remove_permissions_from_user(user, [RoleEnum.CERTIFIER], organisation, by_user=user)

        assert set(role.permissions) == {RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER}

    def test_removing_last_permission_deletes_role(self, factories, db_session):
        user = factories.user.create()
        organisation = factories.organisation.create()
        original_role = factories.user_role.create(
            user=user,
            organisation=organisation,
            permissions=[RoleEnum.MEMBER],
        )

        role = interfaces.user.remove_permissions_from_user(user, [RoleEnum.MEMBER], organisation, by_user=user)
        assert role is None

        db_session.expire_all()
        assert original_role not in db_session

    def test_tracks_audit_event_when_permission_is_removed(self, factories, db_session):
        grant_recipient = factories.grant_recipient.create()
        user = factories.user.create()
        admin = factories.user.create()
        factories.user_role.create(
            user=user,
            organisation=grant_recipient.organisation,
            grant=grant_recipient.grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.CERTIFIER, RoleEnum.DATA_PROVIDER],
        )

        interfaces.user.remove_permissions_from_user(
            user, [RoleEnum.CERTIFIER], grant_recipient.organisation, grant_recipient.grant, by_user=admin
        )

        audit_event = db_session.scalars(select(AuditEventModel)).one()
        assert audit_event.event_type == AuditEventType.USER_MANAGEMENT
        assert audit_event.user_id == admin.id
        assert audit_event.data["action"] == "permissions_removed"
        assert audit_event.data["target_user_id"] == str(user.id)
        assert audit_event.data["grant_recipient_id"] == str(grant_recipient.id)
        assert audit_event.data["organisation_id"] == str(grant_recipient.organisation.id)
        assert audit_event.data["grant_id"] == str(grant_recipient.grant.id)
        assert audit_event.data["permissions"] == ["certifier"]
        assert set(audit_event.data["resulting_permissions"]) == {"data-provider", "member"}

    def test_tracks_audit_event_when_role_is_deleted(self, factories, db_session):
        grant_recipient = factories.grant_recipient.create()
        user = factories.user.create()
        factories.user_role.create(
            user=user,
            organisation=grant_recipient.organisation,
            grant=grant_recipient.grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )

        interfaces.user.remove_permissions_from_user(
            user,
            [RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
            grant_recipient.organisation,
            grant_recipient.grant,
            by_user=user,
        )

        audit_event = db_session.scalars(select(AuditEventModel)).one()
        assert audit_event.data["action"] == "permissions_removed"
        assert set(audit_event.data["permissions"]) == {"data-provider", "member"}
        assert audit_event.data["resulting_permissions"] == []

    def test_does_not_track_audit_event_when_nothing_is_removed(self, factories, db_session):
        organisation = factories.organisation.create(can_manage_grants=False)
        user = factories.user.create()
        factories.user_role.create(
            user=user, organisation=organisation, permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER]
        )

        interfaces.user.remove_permissions_from_user(user, [RoleEnum.CERTIFIER], organisation, by_user=user)
        interfaces.user.remove_permissions_from_user(user, [RoleEnum.MEMBER], organisation, by_user=user)

        assert db_session.scalars(select(AuditEventModel)).all() == []


class TestGetCertifiersByOrganisation:
    def test_returns_certifiers_grouped_by_organisation(self, factories, db_session):
        org1 = factories.organisation.create(can_manage_grants=False)
        org2 = factories.organisation.create(can_manage_grants=False)
        user1 = factories.user.create(email="certifier1@test.com")
        user2 = factories.user.create(email="certifier2@test.com")
        factories.user_role.create(user=user1, organisation=org1, permissions=[RoleEnum.CERTIFIER])
        factories.user_role.create(user=user2, organisation=org2, permissions=[RoleEnum.CERTIFIER])

        result = interfaces.user.get_certifiers_by_organisation()

        assert len(result) == 2
        assert result[org1][0].id == user1.id
        assert result[org2][0].id == user2.id

    def test_only_includes_organisation_level_certifiers(self, factories, db_session):
        organisation = factories.organisation.create(can_manage_grants=False)
        grant = factories.grant.create(organisation=organisation)
        user1 = factories.user.create(email="org_certifier@test.com")
        user2 = factories.user.create(email="grant_certifier@test.com")
        factories.user_role.create(user=user1, organisation=organisation, permissions=[RoleEnum.CERTIFIER])
        factories.user_role.create(user=user2, organisation=organisation, grant=grant, permissions=[RoleEnum.CERTIFIER])

        result = interfaces.user.get_certifiers_by_organisation()

        assert len(result) == 1
        assert len(result[organisation]) == 1
        assert result[organisation][0].id == user1.id

    def test_excludes_users_without_certifier_permission(self, factories, db_session):
        organisation = factories.organisation.create(can_manage_grants=False)
        user1 = factories.user.create(email="certifier@test.com")
        user2 = factories.user.create(email="member@test.com")
        factories.user_role.create(user=user1, organisation=organisation, permissions=[RoleEnum.CERTIFIER])
        factories.user_role.create(user=user2, organisation=organisation, permissions=[RoleEnum.MEMBER])

        result = interfaces.user.get_certifiers_by_organisation()

        assert len(result) == 1
        assert len(result[organisation]) == 1
        assert result[organisation][0].id == user1.id

    def test_handles_organisations_with_no_certifiers(self, factories, db_session):
        org_with_certifiers = factories.organisation.create(can_manage_grants=False)
        org_without_certifiers = factories.organisation.create(can_manage_grants=False)
        user = factories.user.create(email="certifier@test.com")
        factories.user_role.create(user=user, organisation=org_with_certifiers, permissions=[RoleEnum.CERTIFIER])

        result = interfaces.user.get_certifiers_by_organisation()

        assert len(result) == 2
        assert len(result[org_with_certifiers]) == 1
        assert len(result[org_without_certifiers]) == 0

    def test_handles_out_of_order_certifiers(self, factories, db_session):
        org1 = factories.organisation.create(can_manage_grants=False)
        org2 = factories.organisation.create(can_manage_grants=False)
        user1 = factories.user.create(email="certifier1@test.com")
        user2 = factories.user.create(email="certifier2@test.com")
        user3 = factories.user.create(email="certifier3@test.com")
        factories.user_role.create(user=user1, organisation=org1, permissions=[RoleEnum.CERTIFIER])
        factories.user_role.create(user=user2, organisation=org2, permissions=[RoleEnum.CERTIFIER])
        factories.user_role.create(user=user3, organisation=org1, permissions=[RoleEnum.CERTIFIER])

        result = interfaces.user.get_certifiers_by_organisation()

        assert len(result) == 2
        assert set(result[org1]) == {user1, user3}
        assert set(result[org2]) == {user2}


class TestGetGrantOverrideCertifiersByOrganisation:
    def test_returns_certifiers_grouped_by_grant_recipient_organisation(self, factories, db_session):
        grant = factories.grant.create()
        org1 = factories.organisation.create(can_manage_grants=False)
        org2 = factories.organisation.create(can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org1)
        factories.grant_recipient.create(grant=grant, organisation=org2)
        user1 = factories.user.create(email="certifier1@test.com")
        user2 = factories.user.create(email="certifier2@test.com")
        factories.user_role.create(user=user1, organisation=org1, grant=grant, permissions=[RoleEnum.CERTIFIER])
        factories.user_role.create(user=user2, organisation=org2, grant=grant, permissions=[RoleEnum.CERTIFIER])

        result = interfaces.user.get_grant_override_certifiers_by_organisation(grant_id=grant.id)

        assert len(result[org1]) == 1
        assert result[org1][0].id == user1.id
        assert len(result[org2]) == 1
        assert result[org2][0].id == user2.id

    def test_excludes_organisation_level_certifiers(self, factories, db_session):
        grant = factories.grant.create()
        org = factories.organisation.create(can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)
        org_level_user = factories.user.create(email="org_certifier@test.com")
        factories.user_role.create(user=org_level_user, organisation=org, grant=None, permissions=[RoleEnum.CERTIFIER])

        result = interfaces.user.get_grant_override_certifiers_by_organisation(grant_id=grant.id)

        assert len(result[org]) == 0

    def test_filters_by_organisation_mode(self, factories, db_session):
        grant = factories.grant.create()
        live_org = factories.organisation.create(can_manage_grants=False, with_matching_test_org=True)
        factories.grant_recipient.create(grant=grant, organisation=live_org)
        factories.grant_recipient.create(
            grant=grant, organisation=(live_org.matching_test_organisation), mode=GrantRecipientModeEnum.TEST
        )
        live_user = factories.user.create(email="live_certifier@test.com")
        test_user = factories.user.create(email="test_certifier@test.com")
        factories.user_role.create(user=live_user, organisation=live_org, grant=grant, permissions=[RoleEnum.CERTIFIER])
        factories.user_role.create(
            user=test_user,
            organisation=(live_org.matching_test_organisation),
            grant=grant,
            permissions=[RoleEnum.CERTIFIER],
        )

        result = interfaces.user.get_grant_override_certifiers_by_organisation(
            grant_id=grant.id, organisation_mode=OrganisationModeEnum.LIVE
        )

        assert len(result[live_org]) == 1
        assert result[live_org][0].id == live_user.id

        result = interfaces.user.get_grant_override_certifiers_by_organisation(
            grant_id=grant.id, organisation_mode=OrganisationModeEnum.TEST
        )

        assert len(result[live_org.matching_test_organisation]) == 1
        assert result[live_org.matching_test_organisation][0].id == test_user.id

    def test_organisation_mode_none_returns_all(self, factories, db_session):
        grant = factories.grant.create()
        live_org = factories.organisation.create(can_manage_grants=False, with_matching_test_org=True)
        test_org = live_org.matching_test_organisation
        factories.grant_recipient.create(grant=grant, organisation=live_org)
        factories.grant_recipient.create(grant=grant, organisation=test_org, mode=GrantRecipientModeEnum.TEST)
        live_user = factories.user.create(email="live_certifier@test.com")
        test_user = factories.user.create(email="test_certifier@test.com")
        factories.user_role.create(user=live_user, organisation=live_org, grant=grant, permissions=[RoleEnum.CERTIFIER])
        factories.user_role.create(user=test_user, organisation=test_org, grant=grant, permissions=[RoleEnum.CERTIFIER])

        result = interfaces.user.get_grant_override_certifiers_by_organisation(grant_id=grant.id)

        assert len(result[live_org]) == 1
        assert len(result[test_org]) == 1


class TestGetOrCreateSystemUser:
    def test_creates_system_user_when_missing(self, app, db_session):
        system_user = interfaces.user.get_or_create_system_user()

        assert system_user.email == app.config["SYSTEM_USER_EMAIL"]
        assert system_user.name == app.config["SYSTEM_USER_NAME"]

    def test_returns_existing_system_user_without_updating_it(self, app, db_session, factories):
        existing_user = factories.user.create(email=app.config["SYSTEM_USER_EMAIL"], name="Original name")

        system_user = interfaces.user.get_or_create_system_user()

        assert system_user is existing_user
        assert system_user.name == "Original name"
