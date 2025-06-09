import uuid
from typing import Optional, cast

from flask_login import current_user
from sqlalchemy.dialects.postgresql import insert as postgresql_upsert
from sqlalchemy.exc import IntegrityError

from app.common.data.interfaces.exceptions import InvalidUserRoleError
from app.common.data.models_user import User, UserRole
from app.common.data.types import RoleEnum
from app.extensions import db


def get_user(id_: str | uuid.UUID) -> User | None:
    return db.session.get(User, id_)


def get_current_user() -> User:
    user = cast(User, current_user)
    return user


def get_or_create_user(email_address: str, name: Optional[str] = None) -> User:
    # This feels like it should be a `on_conflict_do_nothing`, except in that case the DB won't return any rows
    # So we use `on_conflict_do_update` with a noop change, so that this upsert will always return the User regardless
    # of if its doing an insert or an 'update'.
    user = db.session.scalars(
        postgresql_upsert(User)
        .values(email=email_address, name=name)
        .on_conflict_do_update(index_elements=["email"], set_={"email": email_address, "name": name})
        .returning(User),
        execution_options={"populate_existing": True},
    ).one()

    return user


def add_user_role(
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
                index_elements=["user_id", "organisation_id", "grant_id", "role"],
                set_={
                    "user_id": user_id,
                    "organisation_id": organisation_id,
                    "grant_id": grant_id,
                    "role": role,
                },
            )
            .returning(UserRole),
            execution_options={"populate_existing": True},
        ).one()
    except IntegrityError as e:
        raise InvalidUserRoleError(e) from e

    return user_role
