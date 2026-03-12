from sqlalchemy import and_, distinct, func, or_

from app.common.data.models import GrantRecipient, Organisation
from app.common.data.models_user import UserRole
from app.common.data.types import GrantRecipientModeEnum, RoleEnum
from app.extensions import db


def get_unique_users_count_for_live_grant_recipients(with_permissions: list[RoleEnum] | None = None) -> int:
    """Get the count of unique users associated with live grant recipients.

    This counts users who:
    - Are associated with organisations that are grant recipients (NOT grant managing orgs)
    - Have roles for live grant recipients only (excludes test grant recipients)
    - Have either grant-specific roles or org-wide roles that apply to the grant

    Explicitly excludes:
    - Users in grant managing organisations (e.g., MHCLG staff/grant team members)
    - Users associated with test grant recipients

    Args:
        with_permissions: Optional collection of permissions to filter by.
                         If provided, only users with ALL specified permissions are counted.
                         If None or empty, all users are counted regardless of permissions.

    Returns:
        Count of unique users matching the criteria.
    """
    query = (
        db.session.query(func.count(distinct(UserRole.user_id)))
        .join(
            GrantRecipient,
            and_(
                UserRole.organisation_id == GrantRecipient.organisation_id,
                or_(UserRole.grant_id == GrantRecipient.grant_id, UserRole.grant_id.is_(None)),
            ),
        )
        .join(Organisation, Organisation.id == UserRole.organisation_id)
        .filter(
            GrantRecipient.mode == GrantRecipientModeEnum.LIVE,
            Organisation.can_manage_grants.is_(False),
        )
    )

    if with_permissions:
        query = query.filter(UserRole.permissions.contains(with_permissions))

    return query.scalar() or 0
