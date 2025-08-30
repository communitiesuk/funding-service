from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload

from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.models import Collection, Grant
from app.common.data.models_user import User
from app.extensions import db
from app.types import NOT_PROVIDED, TNotProvided


def get_grant(grant_id: UUID, with_all_collections: bool = False) -> Grant:
    options = []
    if with_all_collections:
        options.append(
            selectinload(Grant.collections).options(
                joinedload(Collection.created_by),
                selectinload(Collection.forms),
            )
        )

    return db.session.get_one(
        Grant,
        grant_id,
        options=options,
    )


def grant_name_exists(name: str, exclude_grant_id: UUID | None = None) -> bool:
    statement = select(Grant).where(Grant.name == name)
    if exclude_grant_id:
        statement = statement.where(Grant.id != exclude_grant_id)
    grant = db.session.scalar(statement)
    return grant is not None


def get_all_grants_by_user(user: User) -> Sequence[Grant]:
    from app.common.auth.authorisation_helper import AuthorisationHelper

    if AuthorisationHelper.is_platform_admin(user):
        statement = select(Grant).order_by(Grant.name)
        return db.session.scalars(statement).all()
    else:
        grant_ids = [role.grant_id for role in user.roles]
        if not grant_ids:
            return []
        statement = select(Grant).where(Grant.id.in_(grant_ids)).order_by(Grant.name)
        return db.session.scalars(statement).all()


def get_all_grants() -> Sequence[Grant]:
    statement = select(Grant).order_by(Grant.name)
    return db.session.scalars(statement).all()


def create_grant(
    *,
    ggis_number: str,
    name: str,
    description: str,
    primary_contact_name: str,
    primary_contact_email: str,
) -> Grant:
    grant: Grant = Grant(
        ggis_number=ggis_number,
        name=name,
        description=description,
        primary_contact_name=primary_contact_name,
        primary_contact_email=primary_contact_email,
    )
    db.session.add(grant)

    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return grant


def update_grant(
    grant: Grant,
    *,
    ggis_number: str | TNotProvided = NOT_PROVIDED,
    name: str | TNotProvided = NOT_PROVIDED,
    description: str | TNotProvided = NOT_PROVIDED,
    primary_contact_name: str | TNotProvided = NOT_PROVIDED,
    primary_contact_email: str | TNotProvided = NOT_PROVIDED,
) -> Grant:
    if ggis_number is not NOT_PROVIDED:
        grant.ggis_number = ggis_number  # ty: ignore[invalid-assignment]
    if name is not NOT_PROVIDED:
        grant.name = name  # ty: ignore[invalid-assignment]
    if description is not NOT_PROVIDED:
        grant.description = description  # ty: ignore[invalid-assignment]
    if primary_contact_name is not NOT_PROVIDED:
        grant.primary_contact_name = primary_contact_name  # ty: ignore[invalid-assignment]
    if primary_contact_email is not NOT_PROVIDED:
        grant.primary_contact_email = primary_contact_email  # ty: ignore[invalid-assignment]
    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return grant
