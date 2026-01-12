"""Central helpers for determining submission mode based on user type."""

from typing import TYPE_CHECKING

from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.data.types import SubmissionModeEnum

if TYPE_CHECKING:
    from app.common.data.models import Organisation
    from app.common.data.models_user import User


def get_submission_mode_for_user(
    user: "User", *, user_organisation: "Organisation | None" = None
) -> SubmissionModeEnum:
    if AuthorisationHelper.is_deliver_user_testing_access(user, user_organisation=user_organisation):
        return SubmissionModeEnum.TEST
    else:
        return SubmissionModeEnum.LIVE
