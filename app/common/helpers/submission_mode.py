"""Central helpers for determining submission mode based on user type."""

from typing import TYPE_CHECKING

from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.data.types import SubmissionModeEnum

if TYPE_CHECKING:
    from app.common.data.models import GrantRecipient
    from app.common.data.models_user import User


def get_submission_mode_for_user(
    user: "User", *, grant_recipient: "GrantRecipient | None" = None
) -> SubmissionModeEnum:
    """Get the submission mode for the current user.

    Args:
        user: Current user
        grant_recipient: Optional grant recipient context

    Returns:
        SubmissionModeEnum.TEST if Deliver user testing Access
        SubmissionModeEnum.LIVE if regular Access user
    """
    if AuthorisationHelper.is_deliver_user_testing_access(user, grant_recipient=grant_recipient):
        return SubmissionModeEnum.TEST
    else:
        return SubmissionModeEnum.LIVE
