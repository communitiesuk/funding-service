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
    @pytest.mark.parametrize(
        "mode, organisation_mode, requires_certification, expected_permissions",
        [
            (GrantRecipientModeEnum.LIVE, OrganisationModeEnum.LIVE, True, {RoleEnum.DATA_PROVIDER, RoleEnum.MEMBER}),
            (GrantRecipientModeEnum.LIVE, OrganisationModeEnum.LIVE, False, {RoleEnum.DATA_PROVIDER, RoleEnum.MEMBER}),
            (
                GrantRecipientModeEnum.TEST,
                OrganisationModeEnum.TEST,
                True,
                {RoleEnum.DATA_PROVIDER, RoleEnum.CERTIFIER, RoleEnum.MEMBER},
            ),
            (GrantRecipientModeEnum.TEST, OrganisationModeEnum.TEST, False, {RoleEnum.DATA_PROVIDER, RoleEnum.MEMBER}),
        ],
    )
    def test_creates_an_applying_grant_recipient_and_sets_up_the_user(
        self,
        factories,
        user,
        mock_notification_service_calls,
        mode,
        organisation_mode,
        requires_certification,
        expected_permissions,
    ):
        collection = factories.collection.create(requires_certification=requires_certification)
        organisation = factories.organisation.create(can_manage_grants=False, mode=organisation_mode)

        grant_recipient = sign_up_as_grant_recipient(
            user=user,
            grant=collection.grant,
            collection=collection,
            organisation=organisation,
            mode=mode,
            organisation_created=False,
        )

        assert grant_recipient.grant_id == collection.grant.id
        assert grant_recipient.organisation_id == organisation.id
        assert grant_recipient.status == GrantRecipientStatusEnum.APPLYING
        assert grant_recipient.mode == mode
        assert (
            set(interfaces.user.get_user_role(user, organisation.id, collection.grant.id).permissions)
            == expected_permissions
        )
