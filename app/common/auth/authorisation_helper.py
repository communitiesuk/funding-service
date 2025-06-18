from uuid import UUID

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
    def is_grant_member(grant_id: str | UUID, user: User) -> bool:
        # TODO account for hierarchical roles
        # MEMBER_ROLES = [RoleEnum.MEMBER, RoleEnum.ADMIN]
        # platform admin would have RoleEnum.ADMIN and grant_id would be None so need to change 'any()' call
        # role.role in MEMBER_ROLES
        if isinstance(grant_id, str):
            grant_id = UUID(grant_id)
        is_grant_member = any(
            role.role == RoleEnum.MEMBER and role.organisation_id is None and role.grant_id == grant_id
            for role in user.roles
        )
        return is_grant_member

    @staticmethod
    def has_grant_role(grant_id: str, user: User, role: RoleEnum) -> bool:
        """
        Will return True if the user has the specified role for the grant, (TODO: or a higher role in the hierarchy).
        Does not work for platform admin role, as that is not a grant-specific role.
        :param grant_id:
        :param user:
        :param role:
        :return:
        """
        match role:
            case RoleEnum.ADMIN:
                return AuthorisationHelper.is_grant_admin(grant_id, user)
            case RoleEnum.MEMBER:
                return AuthorisationHelper.is_grant_member(grant_id, user)
            case _:
                # If we get to this point, we've put a bad role in the decorator call.
                raise ValueError(f"Unknown role {role}")
