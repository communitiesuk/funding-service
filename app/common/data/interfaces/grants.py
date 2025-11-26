from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload

from app.common.data.interfaces.exceptions import (
    DuplicateValueError,
    NotEnoughGrantTeamUsersError,
    StateTransitionError,
    flush_and_rollback_on_exceptions,
)
from app.common.data.models import Collection, Grant, Organisation
from app.common.data.models_user import User
from app.common.data.types import GrantStatusEnum
from app.extensions import db
from app.metrics import MetricAttributeName, MetricEventName, emit_metric_count
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


def get_all_deliver_grants_by_user(user: User) -> Sequence[Grant]:
    from app.common.auth.authorisation_helper import AuthorisationHelper

    if AuthorisationHelper.is_platform_admin(user):
        statement = select(Grant).order_by(Grant.name)
        return db.session.scalars(statement).all()

    return user.deliver_grants


def get_all_grants(statuses: list[GrantStatusEnum] | None = None) -> Sequence[Grant]:
    statement = select(Grant)

    if statuses is not None:
        statement = statement.where(Grant.status.in_(statuses))

    statement = statement.order_by(Grant.name)
    return db.session.scalars(statement).all()


@flush_and_rollback_on_exceptions(coerce_exceptions=[(IntegrityError, DuplicateValueError)])
def create_grant(
    *,
    ggis_number: str,
    name: str,
    description: str,
    primary_contact_name: str,
    primary_contact_email: str,
) -> Grant:
    # For now, the platform only supports a single 'grant-owning' organisation. So we can just grab the only one (which
    # will be MHCLG), and use that as the grant-owning org of any new grant we create. This means we don't need to
    # design anything around users "selecting" the org for their grant, for now.
    mhclg = db.session.query(Organisation).filter_by(can_manage_grants=True).one()
    grant: Grant = Grant(
        ggis_number=ggis_number,
        name=name,
        description=description,
        primary_contact_name=primary_contact_name,
        primary_contact_email=primary_contact_email,
        organisation=mhclg,
    )
    db.session.add(grant)
    return grant


@flush_and_rollback_on_exceptions(coerce_exceptions=[(IntegrityError, DuplicateValueError)])
def update_grant(
    grant: Grant,
    *,
    ggis_number: str | TNotProvided = NOT_PROVIDED,
    name: str | TNotProvided = NOT_PROVIDED,
    status: GrantStatusEnum | TNotProvided = NOT_PROVIDED,
    description: str | TNotProvided = NOT_PROVIDED,
    primary_contact_name: str | TNotProvided = NOT_PROVIDED,
    primary_contact_email: str | TNotProvided = NOT_PROVIDED,
) -> Grant:
    if ggis_number is not NOT_PROVIDED:
        grant.ggis_number = ggis_number  # ty: ignore[invalid-assignment]
    if name is not NOT_PROVIDED:
        grant.name = name  # ty: ignore[invalid-assignment]

    # NOTE: as/when we start to have a lot of defined state transitions, we might want to have a better state machine
    #       representation such as sqlalchemy-fsm (but all of the libs for this I've looked at lately seem to be
    #       unmaintained or with limited uptake.
    if status is not NOT_PROVIDED and grant.status != status:
        match grant.status, status:
            case (GrantStatusEnum.DRAFT, GrantStatusEnum.LIVE) | (GrantStatusEnum.ONBOARDING, GrantStatusEnum.LIVE):
                if len(grant.grant_team_users) < 2:
                    raise NotEnoughGrantTeamUsersError()
            case GrantStatusEnum.DRAFT, GrantStatusEnum.ONBOARDING:
                pass
            case GrantStatusEnum.LIVE, GrantStatusEnum.DRAFT:
                pass
            case _:
                raise StateTransitionError(model="grant", from_state=grant.status, to_state=status)

        emit_metric_count(
            MetricEventName.GRANT_STATUS_CHANGED,
            grant=grant,
            custom_attributes={
                MetricAttributeName.FROM_STATUS: str(grant.status),
                MetricAttributeName.TO_STATUS: str(status),
            },
        )
        grant.status = status

    if description is not NOT_PROVIDED:
        grant.description = description  # ty: ignore[invalid-assignment]
    if primary_contact_name is not NOT_PROVIDED:
        grant.primary_contact_name = primary_contact_name  # ty: ignore[invalid-assignment]
    if primary_contact_email is not NOT_PROVIDED:
        grant.primary_contact_email = primary_contact_email  # ty: ignore[invalid-assignment]
    return grant
