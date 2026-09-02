from typing import NamedTuple

from flask import flash, redirect, url_for
from flask.typing import ResponseReturnValue

from app.access_grant_funding.session_models import clear_public_sign_up_session
from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.data import interfaces
from app.common.data.interfaces.grant_recipients import create_grant_recipient
from app.common.data.models import Collection, Grant, GrantRecipient, Organisation
from app.common.data.models_user import User
from app.common.data.types import (
    GrantRecipientModeEnum,
    GrantRecipientStatusEnum,
    OrganisationModeEnum,
    RoleEnum,
    SubmissionModeEnum,
)
from app.common.helpers.collections import claim_or_discard_unclaimed_submission
from app.types import FlashMessageType


class SignUpModes(NamedTuple):
    organisation: OrganisationModeEnum
    grant_recipient: GrantRecipientModeEnum
    submission: SubmissionModeEnum


def get_sign_up_modes(user: User) -> SignUpModes:
    """A Deliver user testing Access works against TEST data throughout; everyone else works against LIVE."""
    if AuthorisationHelper.is_deliver_user_testing_access(user):
        return SignUpModes(
            organisation=OrganisationModeEnum.TEST,
            grant_recipient=GrantRecipientModeEnum.TEST,
            submission=SubmissionModeEnum.TEST,
        )
    return SignUpModes(
        organisation=OrganisationModeEnum.LIVE,
        grant_recipient=GrantRecipientModeEnum.LIVE,
        submission=SubmissionModeEnum.LIVE,
    )


def sign_up_as_grant_recipient(
    *, user: User, grant: Grant, organisation: Organisation, mode: GrantRecipientModeEnum
) -> GrantRecipient:
    grant_recipient = create_grant_recipient(
        grant=grant,
        organisation=organisation,
        status=GrantRecipientStatusEnum.APPLYING,
        mode=mode,
    )
    # TODO: in test mode for consistency we could set up each of the
    #       grant team members as users
    # TODO: in test mode if the collection requires certification we
    #       should also give certifier permissions
    interfaces.user.add_permissions_to_user(
        user=user,
        permissions=[RoleEnum.DATA_PROVIDER],
        organisation=organisation,
        grant=grant,
        by_user=user,
    )
    flash(
        {"organisation_name": organisation.name, "grant_name": grant.name},  # ty: ignore[invalid-argument-type]
        FlashMessageType.PUBLIC_SIGN_UP_SUCCESS,
    )
    return grant_recipient


def complete_public_sign_up_session_and_redirect(
    *, user: User, collection: Collection, grant_recipient: GrantRecipient, mode: SubmissionModeEnum
) -> ResponseReturnValue:
    claim_or_discard_unclaimed_submission(user, collection, mode, grant_recipient)
    clear_public_sign_up_session()

    return redirect(
        url_for(
            "access_grant_funding.list_collections",
            organisation_id=grant_recipient.organisation_id,
            grant_id=grant_recipient.grant_id,
        )
    )
