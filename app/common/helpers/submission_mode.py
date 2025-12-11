"""Central helpers for determining submission mode based on user type."""

from typing import TYPE_CHECKING

from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.data.interfaces.grant_recipients import get_grant_recipient
from app.common.data.types import GrantRecipientModeEnum, SubmissionModeEnum

if TYPE_CHECKING:
    from app.common.data.models import GrantRecipient
    from app.common.data.models_user import User


def get_submission_mode_for_user(user: "User") -> SubmissionModeEnum:
    """Get the submission mode for the current user.

    Args:
        user: Current user

    Returns:
        SubmissionModeEnum.TEST if Deliver user testing Access
        SubmissionModeEnum.LIVE if regular Access user
    """
    if AuthorisationHelper.is_deliver_user_testing_access(user):
        return SubmissionModeEnum.TEST
    else:
        return SubmissionModeEnum.LIVE


def get_submission_mode_and_grant_recipient(
    user: "User", grant_recipient: "GrantRecipient"
) -> tuple[SubmissionModeEnum, "GrantRecipient"]:
    """Determine submission mode and grant recipient based on user type.

    Args:
        user: Current user
        grant_recipient: The grant recipient context

    Returns:
        Tuple of (SubmissionModeEnum, GrantRecipient):
        - (TEST, test_grant_recipient) if Deliver user testing Access
        - (LIVE, live_grant_recipient) if regular Access user

    Note:
        TEST submissions always have a TEST grant recipient.
        LIVE submissions always have a LIVE grant recipient.
    """
    if AuthorisationHelper.is_deliver_user_testing_access(user):
        # Find or ensure we have a TEST grant recipient
        # If current grant_recipient is LIVE, we need to find/use the TEST version
        if grant_recipient.mode == GrantRecipientModeEnum.LIVE:
            # Need to get TEST grant recipient for same org/grant combo
            # get_grant_recipient now automatically determines mode from organisation
            test_grant_recipient = get_grant_recipient(
                grant_id=grant_recipient.grant_id,
                organisation_id=grant_recipient.organisation_id,
            )
            return (SubmissionModeEnum.TEST, test_grant_recipient)
        else:
            # Already a TEST grant recipient
            return (SubmissionModeEnum.TEST, grant_recipient)
    else:
        # Regular Access user - use LIVE mode and ensure LIVE grant recipient
        return (SubmissionModeEnum.LIVE, grant_recipient)
