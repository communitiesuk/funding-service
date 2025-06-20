import uuid
from typing import cast

from flask_login import current_user
from sqlalchemy.dialects.postgresql import insert as postgresql_upsert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.expression import select

from app.common.data.interfaces.exceptions import InvalidUserRoleError
from app.common.data.models_user import User, UserRole
from app.common.data.types import RoleEnum
from app.extensions import db
from app.types import NOT_PROVIDED, TNotProvided


def get_user(id_: str | uuid.UUID) -> User | None:
    return db.session.get(User, id_)


def get_current_user() -> User:
    user = cast(User, current_user)
    return user


def get_user_by_email(email_address: str) -> User | None:
    return db.session.execute(select(User).where(User.email == email_address)).scalar_one_or_none()


def get_user_by_azure_ad_subject_id(azure_ad_subject_id: str) -> User | None:
    return db.session.execute(select(User).where(User.azure_ad_subject_id == azure_ad_subject_id)).scalar_one_or_none()


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
    user_id: uuid.UUID, role: RoleEnum, organisation_id: uuid.UUID | None = None, grant_id: uuid.UUID | None = None
) -> UserRole:
    # As with the `get_or_create_user` function, this feels like it should be a `on_conflict_do_nothing`,
    # except in that case the DB won't return any rows. So we use the same behaviour as above to ensure we always get a
    # result back regardless of if its doing an insert or an 'update'.

    try:
        user_role = db.session.scalars(
            postgresql_upsert(UserRole)
            .values(
                user_id=user_id,
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

    return user_role
