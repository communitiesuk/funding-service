import datetime
import uuid
from collections.abc import Sequence
from itertools import groupby
from typing import cast

from flask_login import current_user
from sqlalchemy import and_, func, update
from sqlalchemy.dialects.postgresql import insert as postgresql_upsert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.expression import delete, select

from app.common.data.interfaces.exceptions import InvalidUserRoleError, flush_and_rollback_on_exceptions
from app.common.data.interfaces.grant_recipients import get_grant_recipients
from app.common.data.interfaces.grants import get_grant
from app.common.data.interfaces.organisations import get_organisations
from app.common.data.models import Grant, Organisation
from app.common.data.models_user import Invitation, User, UserRole
from app.common.data.types import RoleEnum
from app.extensions import db
from app.types import NOT_PROVIDED, TNotProvided


# todo: move this thing somewhere else
def get_current_user() -> User:
    user = cast(User, current_user)
    return user


def get_user(id_: str | uuid.UUID) -> User | None:
    return db.session.get(User, id_)


def get_user_by_email(email_address: str) -> User | None:
    return db.session.execute(select(User).where(User.email == email_address)).scalar_one_or_none()


def get_user_by_azure_ad_subject_id(azure_ad_subject_id: str) -> User | None:
    return db.session.execute(select(User).where(User.azure_ad_subject_id == azure_ad_subject_id)).scalar_one_or_none()


def get_users_with_permission(
    permission: RoleEnum,
    organisation_id: uuid.UUID | None | TNotProvided = NOT_PROVIDED,
    grant_id: uuid.UUID | None | TNotProvided = NOT_PROVIDED,
) -> Sequence[User]:
    """Finds all users in the system with the given permission and matching organisation and/or grant.

    NOTE: If you pass a grant but don't pass an organisation, this will only return users with the permission
          *specifically* for that grant. It will not return users who have that permission in the grant through an
          org-level permission (ie UserRole.grant_id IS NULL)
    """
    stmt = select(User).join(UserRole).where(UserRole.permissions.contains([permission]))

    if organisation_id is not NOT_PROVIDED:
        stmt = stmt.where(UserRole.organisation_id == organisation_id)

    if grant_id is not NOT_PROVIDED:
        stmt = stmt.where(UserRole.grant_id == grant_id)

    return db.session.scalars(stmt).all()


@flush_and_rollback_on_exceptions
def set_user_last_logged_in_at_utc(user: User) -> User:
    user.last_logged_in_at_utc = func.now()
    return user


@flush_and_rollback_on_exceptions
def upsert_user_by_email(
    email_address: str,
    *,
    name: str | TNotProvided = NOT_PROVIDED,
    azure_ad_subject_id: str | TNotProvided = NOT_PROVIDED,
) -> User:
    # This feels like it should be a `on_conflict_do_nothing`, except in that case the DB won't return any rows
    # So we use `on_conflict_do_update` with a noop change, so that this upsert will always return the User regardless
    # of if its doing an insert or an 'update'.
    on_conflict_set = {"email": email_address}

    # doesn't let us remove the name or azure_ad_subject_id, but that doesn't feel like a super valid usecase,
    # so ignoring for now.
    if name is not NOT_PROVIDED:
        on_conflict_set["name"] = name
    # TODO: FSPT-515 - remove the azure_ad_subject_id field from this upsert, this is only added to cover the current
    # behaviour of grant team members being added directly to the database but not yet having signed in
    if azure_ad_subject_id is not NOT_PROVIDED:
        on_conflict_set["azure_ad_subject_id"] = azure_ad_subject_id

    user = db.session.scalars(
        postgresql_upsert(User)
        .values(**on_conflict_set)
        .on_conflict_do_update(index_elements=["email"], set_=on_conflict_set)
        .returning(User),
        execution_options={"populate_existing": True},
    ).one()

    return user


@flush_and_rollback_on_exceptions
def upsert_user_by_azure_ad_subject_id(
    azure_ad_subject_id: str,
    *,
    email_address: str | TNotProvided = NOT_PROVIDED,
    name: str | TNotProvided = NOT_PROVIDED,
) -> User:
    # This feels like it should be a `on_conflict_do_nothing`, except in that case the DB won't return any rows
    # So we use `on_conflict_do_update` with a noop change, so that this upsert will always return the User regardless
    # of if its doing an insert or an 'update'.
    on_conflict_set = {"azure_ad_subject_id": azure_ad_subject_id}

    # doesn't let us remove the name or email, but that doesn't feel like a super valid usecase, so ignoring for now.
    if email_address is not NOT_PROVIDED:
        on_conflict_set["email"] = email_address

    if name is not NOT_PROVIDED:
        on_conflict_set["name"] = name

    user = db.session.scalars(
        postgresql_upsert(User)
        .values(**on_conflict_set)
        .on_conflict_do_update(index_elements=["azure_ad_subject_id"], set_=on_conflict_set)
        .returning(User),
        execution_options={"populate_existing": True},
    ).one()

    return user


def get_user_role(user: User, organisation_id: uuid.UUID | None, grant_id: uuid.UUID | None) -> UserRole | None:
    return db.session.scalar(
        select(UserRole).where(
            UserRole.user_id == user.id, UserRole.organisation_id == organisation_id, UserRole.grant_id == grant_id
        )
    )


@flush_and_rollback_on_exceptions(coerce_exceptions=[(IntegrityError, InvalidUserRoleError)])
def _upsert_user_role(
    user: User,
    permissions: list[RoleEnum],
    organisation_id: uuid.UUID | None = None,
    grant_id: uuid.UUID | None = None,
) -> UserRole:
    # As with the `get_or_create_user` function, this feels like it should be a `on_conflict_do_nothing`,
    # except in that case the DB won't return any rows. So we use the same behaviour as above to ensure we always get a
    # result back regardless of if its doing an insert or an 'update'.

    if organisation_id is None and grant_id is not None:
        raise ValueError("If specifying grant_id, must also specify organisation_id")

    user_role = db.session.scalars(
        postgresql_upsert(UserRole)
        .values(
            user_id=user.id,
            organisation_id=organisation_id,
            grant_id=grant_id,
            permissions=permissions,
        )
        .on_conflict_do_update(
            index_elements=["user_id", "organisation_id", "grant_id"],
            set_={
                "permissions": permissions,
            },
        )
        .returning(UserRole),
        execution_options={"populate_existing": True},
    ).one()
    db.session.flush()
    db.session.expire(user)
    return user_role


@flush_and_rollback_on_exceptions
def add_permissions_to_user(
    user: User,
    permissions: list[RoleEnum],
    organisation_id: uuid.UUID | None = None,
    grant_id: uuid.UUID | None = None,
) -> UserRole:
    # We're make sure that the MEMBER role is always explicitly included (this is effectively the 'view' permission)
    # NOTE: we could infer view access from the presence of a UserRole at all, so MEMBER could be considered redundant
    #       and is up for removal in the future.
    if RoleEnum.MEMBER not in permissions:
        permissions.append(RoleEnum.MEMBER)

    user_role = get_user_role(user, organisation_id, grant_id)
    existing_permissions = user_role.permissions if user_role else []
    combined_permissions = list(set(existing_permissions + permissions))

    return _upsert_user_role(user, combined_permissions, organisation_id, grant_id)


@flush_and_rollback_on_exceptions
def remove_permissions_from_user(
    user: User,
    permissions: list[RoleEnum],
    organisation_id: uuid.UUID | None = None,
    grant_id: uuid.UUID | None = None,
) -> UserRole | None:
    user_role = get_user_role(user, organisation_id, grant_id)
    if not user_role:
        return None

    existing_permissions = user_role.permissions
    combined_permissions = list(set(existing_permissions) - set(permissions))

    if not combined_permissions:
        db.session.delete(user_role)
        db.session.expire(user)
        return None
    else:
        # We're make sure that the MEMBER role is always explicitly included (this is effectively the 'view' permission)
        # NOTE: we could infer view access from the presence of a UserRole at all, so MEMBER could be considered
        # redundant and is up for removal in the future.
        if RoleEnum.MEMBER not in combined_permissions:
            combined_permissions.append(RoleEnum.MEMBER)

        return _upsert_user_role(user, combined_permissions, organisation_id, grant_id)


@flush_and_rollback_on_exceptions
def create_invitation(
    email: str,
    permissions: list[RoleEnum],
    grant: Grant | None = None,
    organisation: Organisation | None = None,
) -> Invitation:
    if organisation is None and grant is not None:
        raise ValueError("If specifying grant, must also specify organisation")

    if RoleEnum.MEMBER not in permissions:
        permissions.append(RoleEnum.MEMBER)

    # Expire any existing invitations for the same email, organisation, and grant,
    # filtering on NULL if org/grant not passed
    stmt = update(Invitation).where(
        and_(
            Invitation.email == email,
            Invitation.is_usable.is_(True),
            (Invitation.grant_id == grant.id) if grant else Invitation.grant_id.is_(None),
            (Invitation.organisation_id == organisation.id) if organisation else Invitation.organisation_id.is_(None),
        )
    )

    db.session.execute(stmt.values(expires_at_utc=func.now()))

    # Create a new invitation
    invitation = Invitation(
        email=email,
        organisation_id=organisation.id if organisation else None,
        grant_id=grant.id if grant else None,
        permissions=permissions,
        expires_at_utc=func.now() + datetime.timedelta(days=7),
    )
    db.session.add(invitation)
    return invitation


@flush_and_rollback_on_exceptions
def remove_all_roles_from_user(user: User) -> None:
    statement = delete(UserRole).where(UserRole.user_id == user.id)
    db.session.execute(statement)
    db.session.flush()  # we still manually flush here so that we can expire the user and force a re-fetch
    db.session.expire(user)


def get_invitation(invitation_id: uuid.UUID) -> Invitation | None:
    return db.session.get(Invitation, invitation_id)


def get_invitations_by_email(email: str, is_usable: bool | None = None) -> Sequence[Invitation]:
    stmt = select(Invitation).where(Invitation.email == email)
    if is_usable is not None:
        stmt = stmt.where(Invitation.is_usable.is_(is_usable))
    return db.session.scalars(stmt).all()


@flush_and_rollback_on_exceptions
def claim_invitation(invitation: Invitation, user: User) -> Invitation:
    invitation.claimed_at_utc = func.now()
    invitation.user = user

    # Set new grant team members up as test users for each of the grant's grant recipients
    if invitation.organisation.can_manage_grants and invitation.grant is not None:
        if invitation.grant.test_grant_recipients:
            for test_grant_recipient in invitation.grant.test_grant_recipients:
                add_permissions_to_user(
                    user=user,
                    permissions=[RoleEnum.DATA_PROVIDER, RoleEnum.CERTIFIER],
                    organisation_id=test_grant_recipient.organisation_id,
                    grant_id=test_grant_recipient.grant_id,
                )

    db.session.add(invitation)
    return invitation


@flush_and_rollback_on_exceptions
def create_user_and_claim_invitations(azure_ad_subject_id: str, email_address: str, name: str) -> User:
    # We do a check that there are invitations that exist for this email address before calling this function, but it's
    # safer to do this check again in here to avoid passing in invitations that don't belong to this user. SQLAlchemy
    # should cache the result of this query from when it was previously called so shouldn't impact performance.
    invitations = get_invitations_by_email(email=email_address, is_usable=True)
    user = upsert_user_by_azure_ad_subject_id(
        azure_ad_subject_id=azure_ad_subject_id,
        email_address=email_address,
        name=name,
    )
    for invite in invitations:
        add_permissions_to_user(
            user=user,
            permissions=invite.permissions,
            organisation_id=invite.organisation_id,
            grant_id=invite.grant_id,
        )
        claim_invitation(invitation=invite, user=user)
    return user


@flush_and_rollback_on_exceptions
def upsert_user_and_set_platform_admin_role(azure_ad_subject_id: str, email_address: str, name: str) -> User:
    user = upsert_user_by_azure_ad_subject_id(
        azure_ad_subject_id=azure_ad_subject_id,
        email_address=email_address,
        name=name,
    )
    # Claiming invitations here is an edge case but avoids pre-invited grant team members who might sign in for the
    # first time as a platform admin from having pending invitations in the database and Grant Team views
    invitations = get_invitations_by_email(email=email_address, is_usable=True)
    for invite in invitations:
        claim_invitation(invitation=invite, user=user)
    add_permissions_to_user(user, permissions=[RoleEnum.ADMIN], organisation_id=None, grant_id=None)
    return user


@flush_and_rollback_on_exceptions
def add_grant_member_role_or_create_invitation(email_address: str, grant: Grant) -> None:
    existing_user = get_user_by_email(email_address=email_address)
    if existing_user:
        add_permissions_to_user(
            user=existing_user, permissions=[RoleEnum.MEMBER], organisation_id=grant.organisation_id, grant_id=grant.id
        )

        if grant.test_grant_recipients:
            for test_grant_recipient in grant.test_grant_recipients:
                add_permissions_to_user(
                    user=existing_user,
                    permissions=[RoleEnum.DATA_PROVIDER, RoleEnum.CERTIFIER],
                    organisation_id=test_grant_recipient.organisation_id,
                    grant_id=grant.id,
                )

    else:
        create_invitation(
            email=email_address, organisation=grant.organisation, grant=grant, permissions=[RoleEnum.MEMBER]
        )


def get_certifiers_by_organisation() -> dict[Organisation, Sequence[User]]:
    certifiers_by_organisation: dict[Organisation, Sequence[User]] = {
        organisation: [] for organisation in get_organisations(can_manage_grants=False)
    }

    roles = db.session.scalars(
        select(UserRole).where(
            UserRole.organisation_id.isnot(None),
            UserRole.grant_id.is_(None),
            UserRole.permissions.contains([RoleEnum.CERTIFIER]),
        )
    ).all()

    for org, user_roles in groupby(roles, lambda role: role.organisation):
        certifiers_by_organisation[org] = list({ur.user for ur in user_roles})

    return certifiers_by_organisation


def get_grant_override_certifiers_by_organisation(grant_id: uuid.UUID) -> dict[Organisation, Sequence[User]]:
    grant = get_grant(grant_id)
    grant_recipients = get_grant_recipients(grant=grant)

    certifiers_by_organisation: dict[Organisation, Sequence[User]] = {gr.organisation: [] for gr in grant_recipients}

    roles = db.session.scalars(
        select(UserRole).where(
            UserRole.grant_id == grant_id,
            UserRole.permissions.contains([RoleEnum.CERTIFIER]),
        )
    ).all()

    sorted_roles = sorted(roles, key=lambda r: str(r.organisation_id or ""))
    for org, user_roles in groupby(sorted_roles, lambda role: role.organisation):
        certifiers_by_organisation[org] = list({ur.user for ur in user_roles})

    return certifiers_by_organisation
