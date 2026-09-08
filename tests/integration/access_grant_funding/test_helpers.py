import pytest

from app.access_grant_funding.helpers import sign_up_as_grant_recipient
from app.common.data import interfaces
from app.common.data.types import (
    GrantRecipientModeEnum,
    GrantRecipientStatusEnum,
    OrganisationModeEnum,
    RoleEnum,
)


class TestSignUpAsGrantRecipient:
    @pytest.fixture()
    def grant_team_members(self, factories):
        """Two people with explicit access to `grant`, plus one with access to an unrelated grant."""

        def _make(grant):
            members = factories.user.create_batch(2)
            for member in members:
                factories.user_role.create(user=member, grant=grant, permissions=[RoleEnum.MEMBER])

            other_grant_member = factories.user.create()
            factories.user_role.create(
                user=other_grant_member, grant=factories.grant.create(), permissions=[RoleEnum.MEMBER]
            )

            return members, other_grant_member

        return _make

    @pytest.mark.parametrize(
        "mode, organisation_mode",
        [
            (GrantRecipientModeEnum.LIVE, OrganisationModeEnum.LIVE),
            (GrantRecipientModeEnum.TEST, OrganisationModeEnum.TEST),
        ],
    )
    def test_creates_an_applying_grant_recipient(self, factories, user, mode, organisation_mode):
        collection = factories.collection.create()
        organisation = factories.organisation.create(can_manage_grants=False, mode=organisation_mode)

        grant_recipient = sign_up_as_grant_recipient(
            user=user, grant=collection.grant, collection=collection, organisation=organisation, mode=mode
        )

        assert grant_recipient.grant_id == collection.grant.id
        assert grant_recipient.organisation_id == organisation.id
        assert grant_recipient.status == GrantRecipientStatusEnum.APPLYING
        assert grant_recipient.mode == mode

    @pytest.mark.parametrize("requires_certification", [True, False])
    def test_live_sign_up_does_not_set_up_the_grant_team_and_only_makes_the_user_a_data_provider(
        self, factories, user, grant_team_members, requires_certification
    ):
        collection = factories.collection.create(requires_certification=requires_certification)
        members, _ = grant_team_members(collection.grant)
        organisation = factories.organisation.create(can_manage_grants=False, mode=OrganisationModeEnum.LIVE)

        sign_up_as_grant_recipient(
            user=user,
            grant=collection.grant,
            collection=collection,
            organisation=organisation,
            mode=GrantRecipientModeEnum.LIVE,
        )

        for member in members:
            assert interfaces.user.get_user_role(member, organisation.id, collection.grant.id) is None

        assert set(interfaces.user.get_user_role(user, organisation.id, collection.grant.id).permissions) == {
            RoleEnum.DATA_PROVIDER,
            RoleEnum.MEMBER,
        }

    @pytest.mark.parametrize(
        "requires_certification, expected_permissions",
        [
            (True, {RoleEnum.DATA_PROVIDER, RoleEnum.CERTIFIER, RoleEnum.MEMBER}),
            (False, {RoleEnum.DATA_PROVIDER, RoleEnum.MEMBER}),
        ],
    )
    def test_test_sign_up_sets_up_the_grant_team_and_respects_certification_requirement(
        self, factories, user, grant_team_members, requires_certification, expected_permissions
    ):
        collection = factories.collection.create(requires_certification=requires_certification)
        members, other_grant_member = grant_team_members(collection.grant)
        organisation = factories.organisation.create(can_manage_grants=False, mode=OrganisationModeEnum.TEST)

        sign_up_as_grant_recipient(
            user=user,
            grant=collection.grant,
            collection=collection,
            organisation=organisation,
            mode=GrantRecipientModeEnum.TEST,
        )

        for member in members:
            assert (
                set(interfaces.user.get_user_role(member, organisation.id, collection.grant.id).permissions)
                == expected_permissions
            )

        # unrelated grant team members not included in the sign up
        assert interfaces.user.get_user_role(other_grant_member, organisation.id, collection.grant.id) is None
