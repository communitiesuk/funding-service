import datetime
import uuid
from typing import Sequence, cast

from flask_login import current_user
from sqlalchemy import and_, func, update
from sqlalchemy.dialects.postgresql import insert as postgresql_upsert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.expression import delete, select

from app.common.data.interfaces.exceptions import InvalidUserRoleError, flush_and_rollback_on_exceptions
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


@flush_and_rollback_on_exceptions(coerce_exceptions=[(IntegrityError, InvalidUserRoleError)])
def upsert_user_role(
    user: User, permissions: list[RoleEnum], organisation_id: uuid.UUID | None = None, grant_id: uuid.UUID | None = None
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
def set_platform_admin_role_for_user(user: User) -> UserRole:
    # Before making someone a platform admin we should remove any other roles they might have assigned to them, as a
    # platform admin should only ever have that one role
    remove_all_roles_from_user(user)
    platform_admin_role = upsert_user_role(user, permissions=[RoleEnum.ADMIN])
    return platform_admin_role


@flush_and_rollback_on_exceptions
def remove_platform_admin_role_from_user(user: User) -> None:
    statement = delete(UserRole).where(
        and_(
            UserRole.user_id == user.id,
            UserRole.permissions.contains([RoleEnum.ADMIN]),
            UserRole.organisation_id.is_(None),
            UserRole.grant_id.is_(None),
        )
    )
    db.session.execute(statement)
    db.session.flush()  # we still manually flush here so that we can expire the user and force a re-fetch
    db.session.expire(user)


def set_grant_team_role_for_user(user: User, grant: Grant, permissions: list[RoleEnum]) -> UserRole:
    """Used for setting (deliver) grant team membership - NOT grant recipient team membership"""
    grant_team_role = upsert_user_role(
        user=user, organisation_id=grant.organisation_id, grant_id=grant.id, permissions=permissions
    )
    return grant_team_role


@flush_and_rollback_on_exceptions
def remove_grant_team_role_from_user(user: User, grant_id: uuid.UUID) -> None:
    """Used for setting (deliver) grant team membership - NOT grant recipient team membership"""
    statement = delete(UserRole).where(
        and_(
            UserRole.user_id == user.id,
            UserRole.grant_id == grant_id,
        )
    )
    db.session.execute(statement)
    db.session.flush()  # we still manually flush here so that we can expire the user and force a re-fetch
    db.session.expire(user)


@flush_and_rollback_on_exceptions
def create_invitation(
    email: str,
    permissions: list[RoleEnum],
    grant: Grant | None = None,
    organisation: Organisation | None = None,
) -> Invitation:
    if organisation is None and grant is not None:
        raise ValueError("If specifying grant, must also specify organisation")

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


def get_usable_invitations_by_email(email: str) -> Sequence[Invitation]:
    return db.session.scalars(
        select(Invitation).where(and_(Invitation.email == email, Invitation.is_usable.is_(True)))
    ).all()


@flush_and_rollback_on_exceptions
def claim_invitation(invitation: Invitation, user: User) -> Invitation:
    invitation.claimed_at_utc = func.now()
    invitation.user = user
    db.session.add(invitation)
    return invitation


@flush_and_rollback_on_exceptions
def create_user_and_claim_invitations(azure_ad_subject_id: str, email_address: str, name: str) -> User:
    # We do a check that there are invitations that exist for this email address before calling this function, but it's
    # safer to do this check again in here to avoid passing in invitations that don't belong to this user. SQLAlchemy
    # should cache the result of this query from when it was previously called so shouldn't impact performance.
    invitations = get_usable_invitations_by_email(email=email_address)
    user = upsert_user_by_azure_ad_subject_id(
        azure_ad_subject_id=azure_ad_subject_id,
        email_address=email_address,
        name=name,
    )
    for invite in invitations:
        upsert_user_role(
            user=user, organisation_id=invite.organisation_id, grant_id=invite.grant_id, permissions=invite.permissions
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
    invitations = get_usable_invitations_by_email(email=email_address)
    for invite in invitations:
        claim_invitation(invitation=invite, user=user)
    set_platform_admin_role_for_user(user)
    return user


@flush_and_rollback_on_exceptions
def add_grant_member_role_or_create_invitation(email_address: str, grant: Grant) -> None:
    existing_user = get_user_by_email(email_address=email_address)
    if existing_user:
        set_grant_team_role_for_user(user=existing_user, grant=grant, permissions=[RoleEnum.MEMBER])
    else:
        create_invitation(
            email=email_address, organisation=grant.organisation, grant=grant, permissions=[RoleEnum.MEMBER]
        )
