from typing import TYPE_CHECKING
from uuid import UUID

from flask import request
from flask_login import AnonymousUserMixin

from app.common.data.interfaces.collections import get_collection
from app.common.data.interfaces.grant_recipients import get_grant_recipient
from app.common.data.interfaces.grants import get_grant
from app.common.data.models_user import User
from app.common.data.types import OrganisationModeEnum, RoleEnum

if TYPE_CHECKING:
    from app.common.data.models import Organisation


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
            RoleEnum.ADMIN in role.permissions and role.organisation_id is None and role.grant_id is None
            for role in user.roles
        )

    @staticmethod
    def is_platform_member(user: User | AnonymousUserMixin) -> bool:
        if isinstance(user, AnonymousUserMixin):
            return False
        return any(
            RoleEnum.MEMBER in role.permissions and role.organisation_id is None and role.grant_id is None
            for role in user.roles
        )

    @staticmethod
    def is_deliver_org_admin(user: User | AnonymousUserMixin) -> bool:
        if isinstance(user, AnonymousUserMixin):
            return False
        if AuthorisationHelper.is_platform_admin(user=user):
            return True
        return any(
            RoleEnum.ADMIN in role.permissions
            and role.organisation_id
            and role.grant_id is None
            and role.organisation.can_manage_grants
            for role in user.roles
        )

    @staticmethod
    def is_deliver_org_member(user: User | AnonymousUserMixin) -> bool:
        if isinstance(user, AnonymousUserMixin):
            return False
        if AuthorisationHelper.is_platform_admin(user=user):
            return True
        return any(
            (RoleEnum.MEMBER in role.permissions or RoleEnum.ADMIN in role.permissions)
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
            if RoleEnum.ADMIN in role.permissions:
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
            if RoleEnum.MEMBER in role.permissions or RoleEnum.ADMIN in role.permissions:
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
    def has_access_grant_role(
        grant_id: UUID, organisation_id: UUID, role: RoleEnum, user: User | AnonymousUserMixin
    ) -> bool:
        if isinstance(user, AnonymousUserMixin):
            return False
        match role:
            case RoleEnum.DATA_PROVIDER:
                return AuthorisationHelper.is_access_grant_data_provider(grant_id, organisation_id, user)
            case RoleEnum.CERTIFIER:
                return AuthorisationHelper.is_access_grant_certifier(grant_id, organisation_id, user)
            case RoleEnum.MEMBER:
                return AuthorisationHelper.is_access_grant_member(grant_id, organisation_id, user)
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

    @staticmethod
    def can_edit_collection(user: User | AnonymousUserMixin, collection_id: UUID) -> bool:
        if isinstance(user, AnonymousUserMixin):
            return False

        collection = get_collection(collection_id)
        if collection.is_editable_for_current_status and AuthorisationHelper.is_deliver_grant_admin(
            collection.grant_id, user
        ):
            return True

        if AuthorisationHelper.is_platform_admin(user=user):
            # TODO: Decision point
            return False

        return False

    @staticmethod
    def has_access_org_access(user: User | AnonymousUserMixin, organisation_id: UUID) -> bool:
        if isinstance(user, AnonymousUserMixin):
            return False

        # TODO: agree with product and dev what the policy on access to platform admins should be
        #       assuming they should only have blanket access to test data when that exists
        # TODO: organisations are likely lazy loaded here, we should be careful with that and audit
        #       these before we're done
        return any(
            role.organisation_id == organisation_id and not role.organisation.can_manage_grants for role in user.roles
        )

    @staticmethod
    def is_access_grant_data_provider(grant_id: UUID, organisation_id: UUID, user: User | AnonymousUserMixin) -> bool:
        if isinstance(user, AnonymousUserMixin):
            return False

        # its' a valid grant recipient or raise
        grant_recipient = get_grant_recipient(grant_id, organisation_id)

        for role in user.roles:
            if RoleEnum.DATA_PROVIDER in role.permissions:
                # entire org member
                if role.organisation_id == grant_recipient.organisation_id and role.grant_id is None:
                    return True
                # specific grant member
                if (
                    role.organisation_id == grant_recipient.organisation_id
                    and role.grant_id == grant_recipient.grant_id
                ):
                    return True
        return False

    @staticmethod
    def is_access_grant_member(grant_id: UUID, organisation_id: UUID, user: User | AnonymousUserMixin) -> bool:
        if isinstance(user, AnonymousUserMixin):
            return False

        # its' a valid grant recipient or raise
        grant_recipient = get_grant_recipient(grant_id, organisation_id)

        for role in user.roles:
            if RoleEnum.MEMBER in role.permissions:
                # entire org member
                if role.organisation_id == grant_recipient.organisation_id and role.grant_id is None:
                    return True
                # specific grant member
                if (
                    role.organisation_id == grant_recipient.organisation_id
                    and role.grant_id == grant_recipient.grant_id
                ):
                    return True
        return False

    @staticmethod
    def is_access_grant_certifier(grant_id: UUID, organisation_id: UUID, user: User | AnonymousUserMixin) -> bool:
        if isinstance(user, AnonymousUserMixin):
            return False

        # its' a valid grant recipient or raise
        grant_recipient = get_grant_recipient(grant_id, organisation_id)

        for role in user.roles:
            if RoleEnum.CERTIFIER in role.permissions:
                # entire org member
                if role.organisation_id == grant_recipient.organisation_id and role.grant_id is None:
                    return True
                # specific grant member
                if (
                    role.organisation_id == grant_recipient.organisation_id
                    and role.grant_id == grant_recipient.grant_id
                ):
                    return True
        return False

    @staticmethod
    def has_access_grant_recipient_role(user: User | AnonymousUserMixin) -> bool:
        if isinstance(user, AnonymousUserMixin):
            return False

        if any(role.organisation and not role.organisation.can_manage_grants for role in user.roles):
            return True

        return False

    @staticmethod
    def is_deliver_user_testing_access(
        user: User | AnonymousUserMixin, *, user_organisation: Organisation | None = None
    ) -> bool:
        if not AuthorisationHelper.is_deliver_grant_funding_user(user):
            return False

        # if we've got a grant recipient context we can be specific for the organisation too
        # this is likely only possibly in lower envs as deliver users won't be applying for or reporting on grants
        if user_organisation and user_organisation.mode == OrganisationModeEnum.LIVE:
            return False

        return request.path.startswith("/access/")
