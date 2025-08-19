from uuid import UUID

from flask import current_app
from flask_login import AnonymousUserMixin

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
    def is_mhclg_user(user: User | AnonymousUserMixin) -> bool:
        if isinstance(user, AnonymousUserMixin):
            return False

        internal_domains = current_app.config["INTERNAL_DOMAINS"]
        if not user.email.endswith(internal_domains):
            return False

        return True

    @staticmethod
    def is_platform_admin(user: User | AnonymousUserMixin) -> bool:
        if isinstance(user, AnonymousUserMixin):
            return False
        return any(
            role.role == RoleEnum.ADMIN and role.organisation_id is None and role.grant_id is None
            for role in user.roles
        )

    @staticmethod
    def is_grant_admin(grant_id: UUID, user: User | AnonymousUserMixin) -> bool:
        if isinstance(user, AnonymousUserMixin):
            return False
        if AuthorisationHelper.is_platform_admin(user=user):
            return True
        return any(
            role.role == RoleEnum.ADMIN and role.organisation_id is None and role.grant_id == grant_id
            for role in user.roles
        )

    @staticmethod
    def is_grant_member(grant_id: UUID, user: User | AnonymousUserMixin) -> bool:
        """
        Determines whether a user has permissions to act as a grant member.
        Platform admin overrides anything else.
        """
        if isinstance(user, AnonymousUserMixin):
            return False
        if AuthorisationHelper.is_platform_admin(user=user):
            return True

        if isinstance(grant_id, str):
            grant_id = UUID(grant_id)

        return any(
            role.grant_id == grant_id and RoleEnum.MEMBER in GRANT_ROLES_MAPPING.get(role.role, role.role)
            for role in user.roles
        )

    @staticmethod
    def has_grant_role(grant_id: UUID, role: RoleEnum, user: User | AnonymousUserMixin) -> bool:
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
                return AuthorisationHelper.is_grant_admin(grant_id, user)
            case RoleEnum.MEMBER:
                return AuthorisationHelper.is_grant_member(grant_id, user)
            case _:
                raise ValueError(f"Unknown role {role}")

    @staticmethod
    def is_deliver_grant_funding_user(user: User | AnonymousUserMixin) -> bool:
        if isinstance(user, AnonymousUserMixin):
            return False

        if AuthorisationHelper.is_platform_admin(user):
            return True

        # This is the current definition of a Grant team member, but will need updating as more Deliver Grant Funding
        # roles are introduced
        if any(role.grant_id is not None and role.organisation_id is None for role in user.roles):
            return True

        return False
