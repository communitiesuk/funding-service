from uuid import UUID

from app.common.data.models_user import User
from app.common.data.types import GRANT_ROLES_MAPPING, RoleEnum


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
        return any(
            role.role == RoleEnum.ADMIN and role.organisation_id is None and role.grant_id is None
            for role in user.roles
        )

    @staticmethod
    def is_grant_admin(grant_id: UUID, user: User) -> bool:
        return any(
            role.role == RoleEnum.ADMIN and role.organisation_id is None and role.grant_id == grant_id
            for role in user.roles
        )

    @staticmethod
    def is_grant_member(grant_id: UUID, user: User) -> bool:
        """
        Determines whether a user has permissions to act as a grant member.
        Platform admin overrides anything else.
        """
        if AuthorisationHelper.is_platform_admin(user=user):
            return True

        if isinstance(grant_id, str):
            grant_id = UUID(grant_id)

        return any(
            role.grant_id == grant_id and RoleEnum.MEMBER in GRANT_ROLES_MAPPING.get(role.role, role.role)
            for role in user.roles
        )

    @staticmethod
    def has_grant_role(grant_id: UUID, role: RoleEnum, user: User) -> bool:
        """
        Will return True if the user has the specified role for the grant.
        Platform admin overrides anything else.
        """
        if AuthorisationHelper.is_platform_admin(user=user):
            return True
        match role:
            case RoleEnum.ADMIN:
                return AuthorisationHelper.is_grant_admin(grant_id, user)
            case RoleEnum.MEMBER:
                return AuthorisationHelper.is_grant_member(grant_id, user)
            case _:
                raise ValueError(f"Unknown role {role}")
