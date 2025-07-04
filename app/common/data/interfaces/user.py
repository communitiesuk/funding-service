import datetime
import uuid
from typing import cast

from flask_login import current_user
from sqlalchemy import and_, func, update
from sqlalchemy.dialects.postgresql import insert as postgresql_upsert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.expression import delete, select

from app.common.data.interfaces.exceptions import InvalidUserRoleError
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


def set_user_last_logged_in_at_utc(user: User) -> User:
    user.last_logged_in_at_utc = func.now()
    return user


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


def upsert_user_role(
    user: User, role: RoleEnum, organisation_id: uuid.UUID | None = None, grant_id: uuid.UUID | None = None
) -> UserRole:
    # As with the `get_or_create_user` function, this feels like it should be a `on_conflict_do_nothing`,
    # except in that case the DB won't return any rows. So we use the same behaviour as above to ensure we always get a
    # result back regardless of if its doing an insert or an 'update'.

    try:
        user_role = db.session.scalars(
            postgresql_upsert(UserRole)
            .values(
                user_id=user.id,
                organisation_id=organisation_id,
                grant_id=grant_id,
                role=role,
            )
            .on_conflict_do_update(
                index_elements=["user_id", "organisation_id", "grant_id"],
                set_={
                    "role": role,
                },
            )
            .returning(UserRole),
            execution_options={"populate_existing": True},
        ).one()
    except IntegrityError as e:
        raise InvalidUserRoleError(e) from e
    db.session.expire(user)
    return user_role


def set_platform_admin_role_for_user(user: User) -> UserRole:
    # Before making someone a platform admin we should remove any other roles they might have assigned to them, as a
    # platform admin should only ever have that one role
    remove_all_roles_from_user(user)
    platform_admin_role = upsert_user_role(user, role=RoleEnum.ADMIN)
    return platform_admin_role


def remove_platform_admin_role_from_user(user: User) -> None:
    statement = delete(UserRole).where(
        and_(
            UserRole.user_id == user.id,
            UserRole.role == RoleEnum.ADMIN,
            UserRole.organisation_id.is_(None),
            UserRole.grant_id.is_(None),
        )
    )
    db.session.execute(statement)
    db.session.flush()
    db.session.expire(user)


def set_grant_team_role_for_user(user: User, grant_id: uuid.UUID, role: RoleEnum) -> UserRole:
    grant_team_role = upsert_user_role(user=user, grant_id=grant_id, role=role)
    return grant_team_role


def remove_grant_team_role_from_user(user: User, grant_id: uuid.UUID) -> None:
    statement = delete(UserRole).where(
        and_(
            UserRole.user_id == user.id,
            UserRole.grant_id == grant_id,
        )
    )
    db.session.execute(statement)
    db.session.flush()
    db.session.expire(user)


def create_invitation(
    email: str,
    grant: Grant | None = None,
    organisation: Organisation | None = None,
    role: RoleEnum | None = None,
) -> Invitation:
    # Expire any existing invitations for the same email, organisation, and grant
    stmt = update(Invitation).where(
        and_(
            Invitation.email == email,
            Invitation.is_usable.is_(True),
        )
    )
    if grant:
        stmt = stmt.where(Invitation.grant_id == grant.id)
    if organisation:
        stmt = stmt.where(Invitation.organisation_id == organisation.id)

    db.session.execute(stmt.values(expires_at_utc=func.now()))

    # Create a new invitation
    invitation = Invitation(
        email=email,
        organisation_id=organisation.id if organisation else None,
        grant_id=grant.id if grant else None,
        role=role,
        expires_at_utc=func.now() + datetime.timedelta(days=7),
    )
    db.session.add(invitation)
    db.session.flush()
    return invitation


def remove_all_roles_from_user(user: User) -> None:
    statement = delete(UserRole).where(UserRole.user_id == user.id)
    db.session.execute(statement)
    db.session.flush()
    db.session.expire(user)


def get_invitation(invitation_id: uuid.UUID) -> Invitation | None:
    return db.session.get(Invitation, invitation_id)


def claim_invitation(invitation: Invitation, user: User) -> Invitation:
    invitation.claimed_at_utc = func.now()
    invitation.user = user
    db.session.add(invitation)
    db.session.flush()
    return invitation
