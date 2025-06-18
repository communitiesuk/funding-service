from app.common.data.models_user import User
from app.common.data.types import RoleEnum


class AuthorisationHelper:
    @staticmethod
    def has_logged_in(user: User) -> bool:
        # FIXME: We should have some actual tracking of whether the user has logged in. This could either be a
        #        field on the model called `last_logged_in_at` or similar, or we could only create entries in the user
        #        table when the user actually logs in, rather than at invitation-time. Then we could simply trust that
        #        if a user entry exists, they have definitely logged in.
        return bool(user.name)

    @staticmethod
    def is_platform_admin(user: User) -> bool:
        is_platform_admin = any(
            role.role == RoleEnum.ADMIN and role.organisation_id is None and role.grant_id is None
            for role in user.roles
        )
        return is_platform_admin

    @staticmethod
    def is_grant_admin(grant_id: str, user: User) -> bool:
        is_grant_admin = any(
            role.role == RoleEnum.ADMIN and role.organisation_id is None and role.grant_id == grant_id
            for role in user.roles
        )
        return is_grant_admin

    @staticmethod
    def is_grant_member(grant_id: str, user: User) -> bool:
        is_grant_admin = any(
            role.role == RoleEnum.MEMBER and role.organisation_id is None and role.grant_id == grant_id
            for role in user.roles
        )
        return is_grant_admin

    @staticmethod
    def has_grant_role(grant_id: str, user: User, role: RoleEnum) -> bool:
        return bool(
            next(
                (
                    user_role
                    for user_role in user.roles
                    if str(user_role.grant_id) == grant_id and user_role.role == role
                ),
                None,
            )
        )
