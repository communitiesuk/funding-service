from typing import NamedTuple

from flask import flash, redirect, session, url_for
from flask.typing import ResponseReturnValue
from free_email_domains import whitelist as SHARED_EMAIL_DOMAINS

from app.access_grant_funding.session_models import MatchedOrganisationSession, clear_public_sign_up_session
from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.data import interfaces
from app.common.data.interfaces.grant_recipients import create_grant_recipient, get_grant_recipient_or_none
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
from app.constants import SESSION_MATCHED_ORGANISATION
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


def can_share_email_domain(user: User) -> bool:
    """Exclude commonly used and shared emails to avoid accidentally sharing more widely
    than the user would expect. Intended to avoid mistakes but will need monitoring.
    """
    return user.email_domain.casefold() not in SHARED_EMAIL_DOMAINS


def sign_up_as_grant_recipient(
    *, user: User, grant: Grant, collection: Collection, organisation: Organisation, mode: GrantRecipientModeEnum
) -> GrantRecipient:
    grant_recipient = create_grant_recipient(
        grant=grant,
        organisation=organisation,
        status=GrantRecipientStatusEnum.APPLYING,
        mode=mode,
    )

    permissions = [RoleEnum.DATA_PROVIDER]
    users_to_set_up = [user]

    if mode == GrantRecipientModeEnum.TEST:
        if collection.requires_certification:
            permissions.append(RoleEnum.CERTIFIER)

        # Test grant recipients are shared by the whole grant team, so keep the one we've just created
        # consistent with those set up elsewhere:
        #   * `set_up_grant_recipients` (app/deliver_grant_funding/admin/views.py) gives every existing grant
        #     team member access when a platform admin creates test grant recipients for a grant
        #   * `claim_invitation` and `add_grant_member_role_or_create_invitation`
        #     (app/common/data/interfaces/user.py) give each new grant team member access to the grant's
        #     existing test grant recipients
        users_to_set_up += [
            grant_team_member for grant_team_member in grant.grant_team_users if grant_team_member != user
        ]

    for user_to_set_up in users_to_set_up:
        interfaces.user.add_permissions_to_user(
            user=user_to_set_up,
            permissions=permissions,
            organisation=organisation,
            grant=grant,
            by_user=user,
        )

    flash(
        {"organisation_name": organisation.name, "grant_name": grant.name},  # ty: ignore[invalid-argument-type]
        FlashMessageType.PUBLIC_SIGN_UP_SUCCESS,
    )
    return grant_recipient


def sign_up_with_matched_organisation(
    *, user: User, grant: Grant, collection: Collection, organisation: Organisation, modes: SignUpModes
) -> ResponseReturnValue:
    """Separated out sign up when matching an existing org gives us consistent behaviour even
    if needing to request more information like the users name.
    """
    grant_recipient = get_grant_recipient_or_none(grant.id, organisation.id)

    # No grant recipient exists, create one and sign the user up as a data provider
    if grant_recipient is None:
        # We hold no name for this user, so collect one before signing them up
        # Note we should only match this route if grant recipient isn't already applying
        if not user.name:
            session[SESSION_MATCHED_ORGANISATION] = MatchedOrganisationSession(
                collection_id=collection.id, organisation_id=organisation.id
            ).to_session_dict()
            return redirect(
                url_for(
                    "access_grant_funding.eligible_to_apply_user_name",
                    grant_slug=grant.slug,
                    collection_slug=collection.slug,
                )
            )

        grant_recipient = sign_up_as_grant_recipient(
            user=user, grant=grant, collection=collection, organisation=organisation, mode=modes.grant_recipient
        )
    # A grant recipient exists, and user does not have access to it
    elif not AuthorisationHelper.has_access_grant_role(grant_recipient, RoleEnum.MEMBER, user):
        return redirect(
            url_for(
                "access_grant_funding.already_applying",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
                organisation_id=organisation.id,
            )
        )
    # A grant recipient exists, and user already has access to it
    else:
        flash(
            {"grant_name": grant.name},  # ty: ignore[invalid-argument-type]
            FlashMessageType.PUBLIC_SIGN_UP_ALREADY_HAS_ACCESS,
        )

    return complete_public_sign_up_session_and_redirect(
        user=user, collection=collection, grant_recipient=grant_recipient, mode=modes.submission
    )


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
