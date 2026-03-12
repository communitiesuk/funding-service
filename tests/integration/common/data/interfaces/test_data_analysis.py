from app.common.data import interfaces
from app.common.data.types import GrantRecipientModeEnum, RoleEnum
from tests.models import _get_grant_managing_organisation


class TestGetUniqueUsersCountForLiveGrantRecipients:
    def test_returns_zero_when_no_live_grant_recipients(self, db_session):
        count = interfaces.data_analysis.get_unique_users_count_for_live_grant_recipients()
        assert count == 0

    def test_basic_counting_without_permission_filter(self, db_session, factories):
        org = factories.organisation.create(can_manage_grants=False)
        grant = factories.grant.create()
        user1 = factories.user.create()
        user2 = factories.user.create()
        user3 = factories.user.create()

        factories.grant_recipient.create(organisation=org, grant=grant, mode=GrantRecipientModeEnum.LIVE)

        # Create users with various permissions
        factories.user_role.create(user=user1, organisation=org, grant=grant, permissions=[RoleEnum.DATA_PROVIDER])
        factories.user_role.create(user=user2, organisation=org, grant=grant, permissions=[RoleEnum.CERTIFIER])
        factories.user_role.create(user=user3, organisation=org, grant=grant, permissions=[RoleEnum.MEMBER])

        count = interfaces.data_analysis.get_unique_users_count_for_live_grant_recipients()
        assert count == 3

    def test_excludes_test_grant_recipients(self, db_session, factories):
        org = factories.organisation.create(can_manage_grants=False)
        grant = factories.grant.create()
        test_user = factories.user.create()
        live_user = factories.user.create()

        # Create both test and live grant recipients
        factories.grant_recipient.create(organisation=org, grant=grant, mode=GrantRecipientModeEnum.TEST)

        # Create another org for live recipient
        live_org = factories.organisation.create(can_manage_grants=False)
        factories.grant_recipient.create(organisation=live_org, grant=grant, mode=GrantRecipientModeEnum.LIVE)

        # User in test grant recipient
        factories.user_role.create(user=test_user, organisation=org, grant=grant, permissions=[RoleEnum.DATA_PROVIDER])

        # User in live grant recipient
        factories.user_role.create(
            user=live_user, organisation=live_org, grant=grant, permissions=[RoleEnum.DATA_PROVIDER]
        )

        # Should only count the live user
        count = interfaces.data_analysis.get_unique_users_count_for_live_grant_recipients()
        assert count == 1

    def test_counts_org_wide_roles(self, db_session, factories):
        org = factories.organisation.create(can_manage_grants=False)
        grant = factories.grant.create()
        user = factories.user.create()

        factories.grant_recipient.create(organisation=org, grant=grant, mode=GrantRecipientModeEnum.LIVE)

        factories.user_role.create(user=user, organisation=org, grant=None, permissions=[RoleEnum.CERTIFIER])

        count = interfaces.data_analysis.get_unique_users_count_for_live_grant_recipients()
        assert count == 1

    def test_deduplicates_users_across_multiple_grants(self, db_session, factories):
        org = factories.organisation.create(can_manage_grants=False)
        grant1 = factories.grant.create()
        grant2 = factories.grant.create()
        user = factories.user.create()

        factories.grant_recipient.create(organisation=org, grant=grant1, mode=GrantRecipientModeEnum.LIVE)
        factories.grant_recipient.create(organisation=org, grant=grant2, mode=GrantRecipientModeEnum.LIVE)

        # Same user has roles for both grants
        factories.user_role.create(user=user, organisation=org, grant=grant1, permissions=[RoleEnum.DATA_PROVIDER])
        factories.user_role.create(user=user, organisation=org, grant=grant2, permissions=[RoleEnum.CERTIFIER])

        count = interfaces.data_analysis.get_unique_users_count_for_live_grant_recipients()
        assert count == 1

    def test_permission_filtering_single_permission(self, db_session, factories):
        org = factories.organisation.create(can_manage_grants=False)
        grant = factories.grant.create()
        certifier_user = factories.user.create()
        data_provider_user = factories.user.create()

        factories.grant_recipient.create(organisation=org, grant=grant, mode=GrantRecipientModeEnum.LIVE)

        factories.user_role.create(user=certifier_user, organisation=org, grant=grant, permissions=[RoleEnum.CERTIFIER])
        factories.user_role.create(
            user=data_provider_user, organisation=org, grant=grant, permissions=[RoleEnum.DATA_PROVIDER]
        )

        # Count only certifiers
        certifier_count = interfaces.data_analysis.get_unique_users_count_for_live_grant_recipients(
            with_permissions=[RoleEnum.CERTIFIER]
        )
        assert certifier_count == 1

        # Count only data providers
        data_provider_count = interfaces.data_analysis.get_unique_users_count_for_live_grant_recipients(
            with_permissions=[RoleEnum.DATA_PROVIDER]
        )
        assert data_provider_count == 1

        # Count all users (no filter)
        all_count = interfaces.data_analysis.get_unique_users_count_for_live_grant_recipients()
        assert all_count == 2

    def test_permission_filtering_multiple_permissions(self, db_session, factories):
        org = factories.organisation.create(can_manage_grants=False)
        grant = factories.grant.create()
        user_with_both = factories.user.create()
        user_with_certifier_only = factories.user.create()
        user_with_data_provider_only = factories.user.create()

        factories.grant_recipient.create(organisation=org, grant=grant, mode=GrantRecipientModeEnum.LIVE)

        # User with both permissions
        factories.user_role.create(
            user=user_with_both, organisation=org, grant=grant, permissions=[RoleEnum.CERTIFIER, RoleEnum.DATA_PROVIDER]
        )

        # User with only certifier permission
        factories.user_role.create(
            user=user_with_certifier_only, organisation=org, grant=grant, permissions=[RoleEnum.CERTIFIER]
        )

        # User with only data provider permission
        factories.user_role.create(
            user=user_with_data_provider_only, organisation=org, grant=grant, permissions=[RoleEnum.DATA_PROVIDER]
        )

        # Count users with BOTH certifier AND data provider permissions
        count = interfaces.data_analysis.get_unique_users_count_for_live_grant_recipients(
            with_permissions=[RoleEnum.CERTIFIER, RoleEnum.DATA_PROVIDER]
        )
        assert count == 1  # Only user_with_both

    def test_empty_permissions_list_counts_all(self, db_session, factories):
        org = factories.organisation.create(can_manage_grants=False)
        grant = factories.grant.create()
        user1 = factories.user.create()
        user2 = factories.user.create()

        factories.grant_recipient.create(organisation=org, grant=grant, mode=GrantRecipientModeEnum.LIVE)

        factories.user_role.create(user=user1, organisation=org, grant=grant, permissions=[RoleEnum.CERTIFIER])
        factories.user_role.create(user=user2, organisation=org, grant=grant, permissions=[RoleEnum.DATA_PROVIDER])

        # Empty list should count all users
        count = interfaces.data_analysis.get_unique_users_count_for_live_grant_recipients(with_permissions=[])
        assert count == 2

    def test_excludes_grant_managing_org_users(self, db_session, factories):
        grant_managing_org = _get_grant_managing_organisation()
        recipient_org = factories.organisation.create(can_manage_grants=False)
        grant = factories.grant.create(organisation=grant_managing_org)

        # Create users in both orgs
        grant_team_member = factories.user.create()
        recipient_user = factories.user.create()

        # Grant team member role
        factories.user_role.create(
            user=grant_team_member, organisation=grant_managing_org, grant=grant, permissions=[RoleEnum.ADMIN]
        )

        # Grant recipient setup
        factories.grant_recipient.create(organisation=recipient_org, grant=grant, mode=GrantRecipientModeEnum.LIVE)
        factories.user_role.create(
            user=recipient_user, organisation=recipient_org, grant=grant, permissions=[RoleEnum.DATA_PROVIDER]
        )

        # Should only count the recipient user
        count = interfaces.data_analysis.get_unique_users_count_for_live_grant_recipients()
        assert count == 1

        # Also with permission filter
        count_with_filter = interfaces.data_analysis.get_unique_users_count_for_live_grant_recipients(
            with_permissions=[RoleEnum.DATA_PROVIDER]
        )
        assert count_with_filter == 1

    def test_user_in_both_managing_and_recipient_org_counted_once(self, db_session, factories):
        grant_managing_org = _get_grant_managing_organisation()
        recipient_org = factories.organisation.create(can_manage_grants=False)
        grant = factories.grant.create(organisation=grant_managing_org)

        shared_user = factories.user.create()

        # User has role in grant managing org
        factories.user_role.create(
            user=shared_user, organisation=grant_managing_org, grant=grant, permissions=[RoleEnum.ADMIN]
        )

        # Same user also has role in recipient org
        factories.grant_recipient.create(organisation=recipient_org, grant=grant, mode=GrantRecipientModeEnum.LIVE)
        factories.user_role.create(
            user=shared_user, organisation=recipient_org, grant=grant, permissions=[RoleEnum.DATA_PROVIDER]
        )

        # User counted once (for recipient org role only)
        count = interfaces.data_analysis.get_unique_users_count_for_live_grant_recipients()
        assert count == 1

    def test_complex_scenario_multiple_orgs_grants_users(self, db_session, factories):
        org1 = factories.organisation.create(can_manage_grants=False)
        org2 = factories.organisation.create(can_manage_grants=False)
        grant1 = factories.grant.create()
        grant2 = factories.grant.create()

        data_provider1 = factories.user.create()
        data_provider2 = factories.user.create()
        certifier = factories.user.create()

        # Create live and test grant recipients
        factories.grant_recipient.create(organisation=org1, grant=grant1, mode=GrantRecipientModeEnum.LIVE)
        factories.grant_recipient.create(organisation=org2, grant=grant2, mode=GrantRecipientModeEnum.TEST)

        # Data provider for live grant recipient
        factories.user_role.create(
            user=data_provider1, organisation=org1, grant=grant1, permissions=[RoleEnum.DATA_PROVIDER]
        )

        # Data provider for test grant recipient (should not be counted)
        factories.user_role.create(
            user=data_provider2, organisation=org2, grant=grant2, permissions=[RoleEnum.DATA_PROVIDER]
        )

        # Certifier for live grant recipient
        factories.user_role.create(user=certifier, organisation=org1, grant=grant1, permissions=[RoleEnum.CERTIFIER])

        # Total count
        total_count = interfaces.data_analysis.get_unique_users_count_for_live_grant_recipients()
        assert total_count == 2  # data_provider1 and certifier

        # Data providers only
        data_provider_count = interfaces.data_analysis.get_unique_users_count_for_live_grant_recipients(
            with_permissions=[RoleEnum.DATA_PROVIDER]
        )
        assert data_provider_count == 1  # Only data_provider1

        # Certifiers only
        certifier_count = interfaces.data_analysis.get_unique_users_count_for_live_grant_recipients(
            with_permissions=[RoleEnum.CERTIFIER]
        )
        assert certifier_count == 1  # Only certifier
