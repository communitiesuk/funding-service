from uuid import UUID

from flask_login import AnonymousUserMixin

from app.common.data.interfaces.grants import get_grant
from app.common.data.models_user import User
from app.common.data.types import GRANT_ROLES_MAPPING, RoleEnum


class AuthorisationHelper:
    @staticmethod
    def is_logged_in(user: User | AnonymousUserMixin) -> bool:
        return user.is_authenticated

    @staticmethod
    def has_logged_in(user: User | AnonymousUserMixin) -> bool:
        if isinstance(user, AnonymousUserMixin):
            return False
        return bool(user.last_logged_in_at_utc)

    @staticmethod
    def is_platform_admin(user: User | AnonymousUserMixin) -> bool:
        if isinstance(user, AnonymousUserMixin):
            return False
        return any(
            role.role == RoleEnum.ADMIN and role.organisation_id is None and role.grant_id is None
            for role in user.roles
        )

    @staticmethod
    def is_deliver_org_admin(user: User | AnonymousUserMixin) -> bool:
        if isinstance(user, AnonymousUserMixin):
            return False
        if AuthorisationHelper.is_platform_admin(user=user):
            return True
        return any(
            role.role == RoleEnum.ADMIN
            and role.organisation_id
            and role.grant_id is None
            and role.organisation.can_manage_grants
            for role in user.roles
        )

    @staticmethod
    def is_deliver_grant_admin(grant_id: UUID, user: User | AnonymousUserMixin) -> bool:
        if isinstance(user, AnonymousUserMixin):
            return False
        if AuthorisationHelper.is_platform_admin(user=user):
            return True

        grant = get_grant(grant_id)

        for role in user.roles:
            if role.role == RoleEnum.ADMIN:
                # entire org admin
                if role.organisation_id == grant.organisation_id and role.grant_id is None:
                    return True
                # specific grant admin
                if role.organisation_id == grant.organisation_id and role.grant_id == grant_id:
                    return True

        return False

    @staticmethod
    def is_deliver_grant_member(grant_id: UUID, user: User | AnonymousUserMixin) -> bool:
        if isinstance(user, AnonymousUserMixin):
            return False
        if AuthorisationHelper.is_platform_admin(user=user):
            return True

        grant = get_grant(grant_id)

        for role in user.roles:
            if RoleEnum.MEMBER in GRANT_ROLES_MAPPING.get(role.role, [role.role]):
                # entire org member
                if role.organisation_id == grant.organisation_id and role.grant_id is None:
                    return True
                # specific grant member
                if role.organisation_id == grant.organisation_id and role.grant_id == grant_id:
                    return True

        return False

    @staticmethod
    def has_deliver_grant_role(grant_id: UUID, role: RoleEnum, user: User | AnonymousUserMixin) -> bool:
        """
        Will return True if the user has the specified role for the grant.
        Platform admin overrides anything else.
        """
        if isinstance(user, AnonymousUserMixin):
            return False
        if AuthorisationHelper.is_platform_admin(user=user):
            return True
        match role:
            case RoleEnum.ADMIN:
                return AuthorisationHelper.is_deliver_grant_admin(grant_id, user)
            case RoleEnum.MEMBER:
                return AuthorisationHelper.is_deliver_grant_member(grant_id, user)
            case _:
                raise ValueError(f"Unknown role {role}")

    @staticmethod
    def is_deliver_grant_funding_user(user: User | AnonymousUserMixin) -> bool:
        if isinstance(user, AnonymousUserMixin):
            return False

        if AuthorisationHelper.is_platform_admin(user):
            return True

        if any(role.organisation and role.organisation.can_manage_grants for role in user.roles):
            return True

        return False
