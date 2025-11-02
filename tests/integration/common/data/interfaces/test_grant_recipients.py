from app.common.data.interfaces.grant_recipients import (
    all_grant_recipients_have_users,
    create_grant_recipients,
    get_grant_recipient_user_roles,
    get_grant_recipient_users_by_organisation,
    get_grant_recipient_users_count,
    get_grant_recipients,
    get_grant_recipients_count,
    revoke_grant_recipient_user_role,
)
from app.common.data.models import GrantRecipient
from app.common.data.types import RoleEnum


class TestGetGrantRecipients:
    def test_returns_grant_recipients_for_grant(self, factories, db_session):
        grant = factories.grant.create()
        org1 = factories.organisation.create(name="Organisation 1")
        org2 = factories.organisation.create(name="Organisation 2")
        org3 = factories.organisation.create(name="Organisation 3")

        factories.grant_recipient.create(grant=grant, organisation=org1)
        factories.grant_recipient.create(grant=grant, organisation=org2)
        factories.grant_recipient.create(grant=grant, organisation=org3)

        result = get_grant_recipients(grant)

        assert len(result) == 3
        assert {gr.organisation_id for gr in result} == {org1.id, org2.id, org3.id}

    def test_returns_only_grant_recipients_for_specified_grant(self, factories, db_session):
        grant1 = factories.grant.create()
        grant2 = factories.grant.create()
        org1 = factories.organisation.create(name="Organisation 1")
        org2 = factories.organisation.create(name="Organisation 2")

        gr1 = factories.grant_recipient.create(grant=grant1, organisation=org1)
        factories.grant_recipient.create(grant=grant2, organisation=org2)

        result = get_grant_recipients(grant1)

        assert len(result) == 1
        assert result[0].id == gr1.id

    def test_returns_empty_list_when_no_grant_recipients(self, factories, db_session):
        grant = factories.grant.create()

        result = get_grant_recipients(grant)

        assert result == []


class TestGetGrantRecipientsCount:
    def test_returns_count_of_grant_recipients(self, factories, db_session):
        grant = factories.grant.create()
        org1 = factories.organisation.create(name="Organisation 1")
        org2 = factories.organisation.create(name="Organisation 2")
        org3 = factories.organisation.create(name="Organisation 3")

        factories.grant_recipient.create(grant=grant, organisation=org1)
        factories.grant_recipient.create(grant=grant, organisation=org2)
        factories.grant_recipient.create(grant=grant, organisation=org3)

        result = get_grant_recipients_count(grant)

        assert result == 3

    def test_returns_zero_when_no_grant_recipients(self, factories, db_session):
        grant = factories.grant.create()

        result = get_grant_recipients_count(grant)

        assert result == 0

    def test_counts_only_grant_recipients_for_specified_grant(self, factories, db_session):
        grant1 = factories.grant.create()
        grant2 = factories.grant.create()
        org1 = factories.organisation.create(name="Organisation 1")
        org2 = factories.organisation.create(name="Organisation 2")
        org3 = factories.organisation.create(name="Organisation 3")

        factories.grant_recipient.create(grant=grant1, organisation=org1)
        factories.grant_recipient.create(grant=grant2, organisation=org2)
        factories.grant_recipient.create(grant=grant2, organisation=org3)

        result = get_grant_recipients_count(grant1)

        assert result == 1


class TestCreateGrantRecipients:
    def test_creates_grant_recipients_for_organisations(self, factories, db_session):
        grant = factories.grant.create()
        org1 = factories.organisation.create(name="Organisation 1")
        org2 = factories.organisation.create(name="Organisation 2")
        org3 = factories.organisation.create(name="Organisation 3")

        create_grant_recipients(grant, [org1.id, org2.id, org3.id])

        db_session.expire_all()
        grant_recipients = db_session.query(GrantRecipient).filter_by(grant_id=grant.id).all()
        assert len(grant_recipients) == 3
        assert {gr.organisation_id for gr in grant_recipients} == {org1.id, org2.id, org3.id}

    def test_creates_single_grant_recipient(self, factories, db_session):
        grant = factories.grant.create()
        org = factories.organisation.create(name="Organisation 1")

        create_grant_recipients(grant, [org.id])

        db_session.expire_all()
        grant_recipients = db_session.query(GrantRecipient).filter_by(grant_id=grant.id).all()
        assert len(grant_recipients) == 1
        assert grant_recipients[0].organisation_id == org.id
        assert grant_recipients[0].grant_id == grant.id

    def test_handles_empty_list(self, factories, db_session):
        grant = factories.grant.create()
        initial_count = db_session.query(GrantRecipient).count()

        create_grant_recipients(grant, [])

        db_session.expire_all()
        final_count = db_session.query(GrantRecipient).count()
        assert final_count == initial_count

    def test_adds_to_existing_grant_recipients(self, factories, db_session):
        grant = factories.grant.create()
        org1 = factories.organisation.create(name="Organisation 1")
        org2 = factories.organisation.create(name="Organisation 2")
        org3 = factories.organisation.create(name="Organisation 3")

        factories.grant_recipient.create(grant=grant, organisation=org1)

        create_grant_recipients(grant, [org2.id, org3.id])

        db_session.expire_all()
        grant_recipients = db_session.query(GrantRecipient).filter_by(grant_id=grant.id).all()
        assert len(grant_recipients) == 3
        assert {gr.organisation_id for gr in grant_recipients} == {org1.id, org2.id, org3.id}


class TestGetGrantRecipientUsersCount:
    def test_no_grant_recipient_users(self, db_session, factories):
        grant = factories.grant.create()

        count = get_grant_recipient_users_count(grant)

        assert count == 0

    def test_single_grant_recipient_user(self, db_session, factories):
        grant = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant)
        user = factories.user.create()
        factories.user_role.create(
            user=user, organisation=grant_recipient.organisation, grant=grant, role=RoleEnum.MEMBER
        )

        count = get_grant_recipient_users_count(grant)

        assert count == 1

    def test_multiple_grant_recipient_users_same_organisation(self, db_session, factories):
        grant = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant)
        users = factories.user.create_batch(3)
        for user in users:
            factories.user_role.create(
                user=user, organisation=grant_recipient.organisation, grant=grant, role=RoleEnum.MEMBER
            )

        count = get_grant_recipient_users_count(grant)

        assert count == 3

    def test_multiple_grant_recipient_users_different_organisations(self, db_session, factories):
        grant = factories.grant.create()
        grant_recipients = factories.grant_recipient.create_batch(2, grant=grant)

        user1 = factories.user.create()
        factories.user_role.create(
            user=user1, organisation=grant_recipients[0].organisation, grant=grant, role=RoleEnum.MEMBER
        )

        user2 = factories.user.create()
        factories.user_role.create(
            user=user2, organisation=grant_recipients[1].organisation, grant=grant, role=RoleEnum.MEMBER
        )

        count = get_grant_recipient_users_count(grant)

        assert count == 2

    def test_excludes_grant_team_members(self, db_session, factories):
        grant = factories.grant.create()
        factories.grant_recipient.create(grant=grant)

        grant_team_user = factories.user.create()
        factories.user_role.create(
            user=grant_team_user, organisation=grant.organisation, grant=grant, role=RoleEnum.MEMBER
        )

        count = get_grant_recipient_users_count(grant)

        assert count == 0

    def test_excludes_admin_roles(self, db_session, factories):
        grant = factories.grant.create()
        factories.grant_recipient.create(grant=grant)
        user = factories.user.create()
        factories.user_role.create(user=user, role=RoleEnum.ADMIN)

        count = get_grant_recipient_users_count(grant)

        assert count == 0

    def test_excludes_users_from_different_grant(self, db_session, factories):
        grant1 = factories.grant.create()
        grant2 = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant1)
        user = factories.user.create()
        factories.user_role.create(
            user=user, organisation=grant_recipient.organisation, grant=grant2, role=RoleEnum.MEMBER
        )

        count = get_grant_recipient_users_count(grant1)

        assert count == 0


class TestAllGrantRecipientsHaveUsers:
    def test_returns_false_when_no_grant_recipients(self, db_session, factories):
        grant = factories.grant.create()

        result = all_grant_recipients_have_users(grant)

        assert result is False

    def test_returns_false_when_grant_recipient_has_no_users(self, db_session, factories):
        grant = factories.grant.create()
        factories.grant_recipient.create(grant=grant)

        result = all_grant_recipients_have_users(grant)

        assert result is False

    def test_returns_true_when_single_grant_recipient_has_users(self, db_session, factories):
        grant = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant)
        user = factories.user.create()
        factories.user_role.create(
            user=user, organisation=grant_recipient.organisation, grant=grant, role=RoleEnum.MEMBER
        )

        result = all_grant_recipients_have_users(grant)

        assert result is True

    def test_returns_true_when_all_grant_recipients_have_users(self, db_session, factories):
        grant = factories.grant.create()
        grant_recipients = factories.grant_recipient.create_batch(3, grant=grant)

        for grant_recipient in grant_recipients:
            user = factories.user.create()
            factories.user_role.create(
                user=user, organisation=grant_recipient.organisation, grant=grant, role=RoleEnum.MEMBER
            )

        result = all_grant_recipients_have_users(grant)

        assert result is True

    def test_returns_false_when_some_grant_recipients_have_no_users(self, db_session, factories):
        grant = factories.grant.create()
        grant_recipients = factories.grant_recipient.create_batch(3, grant=grant)

        user = factories.user.create()
        factories.user_role.create(
            user=user, organisation=grant_recipients[0].organisation, grant=grant, role=RoleEnum.MEMBER
        )

        result = all_grant_recipients_have_users(grant)

        assert result is False

    def test_returns_true_when_grant_recipient_has_multiple_users(self, db_session, factories):
        grant = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant)
        users = factories.user.create_batch(3)

        for user in users:
            factories.user_role.create(
                user=user, organisation=grant_recipient.organisation, grant=grant, role=RoleEnum.MEMBER
            )

        result = all_grant_recipients_have_users(grant)

        assert result is True

    def test_excludes_admin_roles(self, db_session, factories):
        grant = factories.grant.create()
        factories.grant_recipient.create(grant=grant)
        user = factories.user.create()
        factories.user_role.create(user=user, role=RoleEnum.ADMIN)

        result = all_grant_recipients_have_users(grant)

        assert result is False

    def test_excludes_users_from_different_grants(self, db_session, factories):
        grant1 = factories.grant.create()
        grant2 = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant1)
        user = factories.user.create()
        factories.user_role.create(
            user=user, organisation=grant_recipient.organisation, grant=grant2, role=RoleEnum.MEMBER
        )

        result = all_grant_recipients_have_users(grant1)

        assert result is False

    def test_excludes_grant_team_members(self, db_session, factories):
        grant = factories.grant.create()
        factories.grant_recipient.create(grant=grant)
        grant_team_user = factories.user.create()
        factories.user_role.create(
            user=grant_team_user, organisation=grant.organisation, grant=grant, role=RoleEnum.MEMBER
        )

        result = all_grant_recipients_have_users(grant)

        assert result is False


class TestGetGrantRecipientUsersByOrganisation:
    def test_returns_empty_dict_when_no_grant_recipients(self, db_session, factories):
        grant = factories.grant.create()

        result = get_grant_recipient_users_by_organisation(grant)

        assert result == {}

    def test_returns_grant_recipients_with_no_users(self, db_session, factories):
        grant = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant)

        result = get_grant_recipient_users_by_organisation(grant)

        assert len(result) == 1
        assert grant_recipient in result
        assert result[grant_recipient] == []

    def test_returns_single_grant_recipient_with_single_user(self, db_session, factories):
        grant = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant)
        user = factories.user.create()
        factories.user_role.create(
            user=user, organisation=grant_recipient.organisation, grant=grant, role=RoleEnum.MEMBER
        )

        result = get_grant_recipient_users_by_organisation(grant)

        assert len(result) == 1
        assert grant_recipient in result
        assert len(result[grant_recipient]) == 1
        assert result[grant_recipient][0].id == user.id

    def test_returns_single_grant_recipient_with_multiple_users(self, db_session, factories):
        grant = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant)
        users = factories.user.create_batch(3)
        for user in users:
            factories.user_role.create(
                user=user, organisation=grant_recipient.organisation, grant=grant, role=RoleEnum.MEMBER
            )

        result = get_grant_recipient_users_by_organisation(grant)

        assert len(result) == 1
        assert grant_recipient in result
        assert len(result[grant_recipient]) == 3
        assert {u.id for u in result[grant_recipient]} == {u.id for u in users}

    def test_returns_multiple_grant_recipients_with_users(self, db_session, factories):
        grant = factories.grant.create()
        grant_recipients = factories.grant_recipient.create_batch(3, grant=grant)

        users_per_recipient = {}
        for grant_recipient in grant_recipients:
            users = factories.user.create_batch(2)
            users_per_recipient[grant_recipient.id] = users
            for user in users:
                factories.user_role.create(
                    user=user, organisation=grant_recipient.organisation, grant=grant, role=RoleEnum.MEMBER
                )

        result = get_grant_recipient_users_by_organisation(grant)

        assert len(result) == 3
        for grant_recipient in grant_recipients:
            assert grant_recipient in result
            expected_user_ids = {u.id for u in users_per_recipient[grant_recipient.id]}
            actual_user_ids = {u.id for u in result[grant_recipient]}
            assert actual_user_ids == expected_user_ids

    def test_excludes_users_from_different_grant(self, db_session, factories):
        grant1 = factories.grant.create()
        grant2 = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant1)
        user1 = factories.user.create()
        user2 = factories.user.create()
        factories.user_role.create(
            user=user1, organisation=grant_recipient.organisation, grant=grant1, role=RoleEnum.MEMBER
        )
        factories.user_role.create(
            user=user2, organisation=grant_recipient.organisation, grant=grant2, role=RoleEnum.MEMBER
        )

        result = get_grant_recipient_users_by_organisation(grant1)

        assert len(result) == 1
        assert grant_recipient in result
        assert len(result[grant_recipient]) == 1
        assert result[grant_recipient][0].id == user1.id

    def test_excludes_non_member_roles(self, db_session, factories):
        grant = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant)
        member_user = factories.user.create()
        admin_user = factories.user.create()
        factories.user_role.create(
            user=member_user, organisation=grant_recipient.organisation, grant=grant, role=RoleEnum.MEMBER
        )
        factories.user_role.create(user=admin_user, role=RoleEnum.ADMIN)

        result = get_grant_recipient_users_by_organisation(grant)

        assert len(result) == 1
        assert grant_recipient in result
        assert len(result[grant_recipient]) == 1
        assert result[grant_recipient][0].id == member_user.id


class TestGetGrantRecipientUserRoles:
    def test_returns_empty_list_when_no_users(self, db_session, factories):
        grant = factories.grant.create()

        result = get_grant_recipient_user_roles(grant)

        assert result == []

    def test_returns_single_user_role(self, db_session, factories):
        grant = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant)
        user = factories.user.create(name="Test User", email="test@example.com")
        factories.user_role.create(
            user=user, organisation=grant_recipient.organisation, grant=grant, role=RoleEnum.MEMBER
        )

        result = get_grant_recipient_user_roles(grant)

        assert len(result) == 1
        user_id, org_id, user_name, user_email, org_name = result[0]
        assert user_id == user.id
        assert org_id == grant_recipient.organisation_id
        assert user_name == "Test User"
        assert user_email == "test@example.com"
        assert org_name == grant_recipient.organisation.name

    def test_returns_multiple_user_roles_same_organisation(self, db_session, factories):
        grant = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant)
        users = factories.user.create_batch(3)
        for user in users:
            factories.user_role.create(
                user=user, organisation=grant_recipient.organisation, grant=grant, role=RoleEnum.MEMBER
            )

        result = get_grant_recipient_user_roles(grant)

        assert len(result) == 3
        user_ids = {r[0] for r in result}
        assert user_ids == {u.id for u in users}
        for _, org_id, _, _, _ in result:
            assert org_id == grant_recipient.organisation_id

    def test_returns_multiple_user_roles_different_organisations(self, db_session, factories):
        grant = factories.grant.create()
        grant_recipients = factories.grant_recipient.create_batch(2, grant=grant)

        user1 = factories.user.create(name="User 1")
        user2 = factories.user.create(name="User 2")

        factories.user_role.create(
            user=user1, organisation=grant_recipients[0].organisation, grant=grant, role=RoleEnum.MEMBER
        )
        factories.user_role.create(
            user=user2, organisation=grant_recipients[1].organisation, grant=grant, role=RoleEnum.MEMBER
        )

        result = get_grant_recipient_user_roles(grant)

        assert len(result) == 2
        result_dict = {r[0]: (r[1], r[2]) for r in result}
        assert result_dict[user1.id] == (grant_recipients[0].organisation_id, "User 1")
        assert result_dict[user2.id] == (grant_recipients[1].organisation_id, "User 2")

    def test_excludes_users_from_different_grant(self, db_session, factories):
        grant1 = factories.grant.create()
        grant2 = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant1)
        user1 = factories.user.create()
        user2 = factories.user.create()
        factories.user_role.create(
            user=user1, organisation=grant_recipient.organisation, grant=grant1, role=RoleEnum.MEMBER
        )
        factories.user_role.create(
            user=user2, organisation=grant_recipient.organisation, grant=grant2, role=RoleEnum.MEMBER
        )

        result = get_grant_recipient_user_roles(grant1)

        assert len(result) == 1
        assert result[0][0] == user1.id

    def test_excludes_non_member_roles(self, db_session, factories):
        grant = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant)
        member_user = factories.user.create()
        admin_user = factories.user.create()
        factories.user_role.create(
            user=member_user, organisation=grant_recipient.organisation, grant=grant, role=RoleEnum.MEMBER
        )
        factories.user_role.create(user=admin_user, role=RoleEnum.ADMIN)

        result = get_grant_recipient_user_roles(grant)

        assert len(result) == 1
        assert result[0][0] == member_user.id


class TestRevokeGrantRecipientUserRole:
    def test_revokes_user_role_successfully(self, db_session, factories):
        grant = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant)
        user = factories.user.create()
        factories.user_role.create(
            user=user, organisation=grant_recipient.organisation, grant=grant, role=RoleEnum.MEMBER
        )

        result = revoke_grant_recipient_user_role(user.id, grant_recipient.organisation_id, grant.id)

        assert result is True
        db_session.expire_all()
        remaining_roles = get_grant_recipient_user_roles(grant)
        assert len(remaining_roles) == 0

    def test_returns_false_when_no_matching_role(self, db_session, factories):
        grant = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant)
        user = factories.user.create()

        result = revoke_grant_recipient_user_role(user.id, grant_recipient.organisation_id, grant.id)

        assert result is False

    def test_revokes_only_specified_user_role(self, db_session, factories):
        grant = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant)
        user1 = factories.user.create()
        user2 = factories.user.create()
        factories.user_role.create(
            user=user1, organisation=grant_recipient.organisation, grant=grant, role=RoleEnum.MEMBER
        )
        factories.user_role.create(
            user=user2, organisation=grant_recipient.organisation, grant=grant, role=RoleEnum.MEMBER
        )

        result = revoke_grant_recipient_user_role(user1.id, grant_recipient.organisation_id, grant.id)

        assert result is True
        db_session.expire_all()
        remaining_roles = get_grant_recipient_user_roles(grant)
        assert len(remaining_roles) == 1
        assert remaining_roles[0][0] == user2.id

    def test_does_not_revoke_role_for_different_grant(self, db_session, factories):
        grant1 = factories.grant.create()
        grant2 = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant1)
        user = factories.user.create()
        factories.user_role.create(
            user=user, organisation=grant_recipient.organisation, grant=grant1, role=RoleEnum.MEMBER
        )

        result = revoke_grant_recipient_user_role(user.id, grant_recipient.organisation_id, grant2.id)

        assert result is False
        db_session.expire_all()
        remaining_roles = get_grant_recipient_user_roles(grant1)
        assert len(remaining_roles) == 1

    def test_does_not_revoke_role_for_different_organisation(self, db_session, factories):
        grant = factories.grant.create()
        grant_recipient1 = factories.grant_recipient.create(grant=grant)
        grant_recipient2 = factories.grant_recipient.create(grant=grant)
        user = factories.user.create()
        factories.user_role.create(
            user=user, organisation=grant_recipient1.organisation, grant=grant, role=RoleEnum.MEMBER
        )

        result = revoke_grant_recipient_user_role(user.id, grant_recipient2.organisation_id, grant.id)

        assert result is False
        db_session.expire_all()
        remaining_roles = get_grant_recipient_user_roles(grant)
        assert len(remaining_roles) == 1

    def test_does_not_revoke_non_member_roles(self, db_session, factories):
        grant = factories.grant.create()
        user = factories.user.create()
        admin_role = factories.user_role.create(user=user, role=RoleEnum.ADMIN)

        result = revoke_grant_recipient_user_role(user.id, admin_role.organisation_id, grant.id)

        assert result is False

    def test_expires_user_cache_after_revoke(self, db_session, factories):
        grant = factories.grant.create()
        grant_recipient = factories.grant_recipient.create(grant=grant)
        user = factories.user.create()
        factories.user_role.create(
            user=user, organisation=grant_recipient.organisation, grant=grant, role=RoleEnum.MEMBER
        )

        initial_roles_count = len(user.roles)
        assert initial_roles_count > 0

        revoke_grant_recipient_user_role(user.id, grant_recipient.organisation_id, grant.id)

        db_session.expire_all()
        refreshed_user = db_session.get(user.__class__, user.id)
        assert len(refreshed_user.roles) == 0

    def test_will_not_revoke_grant_managing_org_role(self, db_session, factories):
        grant = factories.grant.create()
        user_role = factories.user_role.create(grant=grant, organisation=grant.organisation, role=RoleEnum.MEMBER)

        assert revoke_grant_recipient_user_role(user_role.user_id, grant.organisation_id, grant.id) == 0
