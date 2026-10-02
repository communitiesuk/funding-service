import datetime
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, distinct, func, or_, select
from sqlalchemy.orm import selectinload

from app.common.audit import UserInvited, UserPermissionsAdded, UserPermissionsRemoved, parse_audit_event
from app.common.data.base import BaseModel
from app.common.data.models import Collection, Grant, GrantRecipient, Organisation
from app.common.data.models_audit import AuditEvent as AuditEventModel
from app.common.data.models_user import Invitation, User, UserRole
from app.common.data.types import (
    MONITORING_COLLECTIONS,
    PRE_AWARD_COLLECTIONS,
    AuditEventType,
    GrantRecipientModeEnum,
    RoleEnum,
)
from app.extensions import db

USER_MANAGEMENT_EVENTS_CSV_HEADERS = [
    "Timestamp",
    "Event",
    "Source",
    "Grant name",
    "Grant ID",
    "Grant GGIS number",
    "Organisation name",
    "Organisation ID",
    "Organisation external ID",
    "Pre-award or monitoring",
    "Actor email",
    "Permissions",
    "Invite date",
    "Accepted date",
    "Unclaimed invitation",
]


@dataclass(frozen=True)
class UserManagementEventCsvRow:
    timestamp: str
    event: str
    source: str
    grant_name: str
    grant_id: str
    grant_ggis_number: str
    organisation_name: str
    organisation_id: str
    organisation_external_id: str
    pre_award_or_monitoring: str
    actor_email: str
    permissions: str
    invite_date: str
    accepted_date: str
    unclaimed_invitation: int

    def as_csv_row(self) -> list[str | int]:
        return [
            self.timestamp,
            self.event,
            self.source,
            self.grant_name,
            self.grant_id,
            self.grant_ggis_number,
            self.organisation_name,
            self.organisation_id,
            self.organisation_external_id,
            self.pre_award_or_monitoring,
            self.actor_email,
            self.permissions,
            self.invite_date,
            self.accepted_date,
            self.unclaimed_invitation,
        ]


def get_unique_users_count_for_live_grant_recipients(with_permissions: list[RoleEnum] | None = None) -> int:
    """Get the count of unique users associated with live grant recipients.

    This counts users who:
    - Are associated with organisations that are grant recipients (NOT grant managing orgs)
    - Have roles for live grant recipients only (excludes test grant recipients)
    - Have either grant-specific roles or org-wide roles that apply to the grant

    Explicitly excludes:
    - Users in grant managing organisations (e.g., MHCLG staff/grant team members)
    - Users associated with test grant recipients

    Args:
        with_permissions: Optional collection of permissions to filter by.
                         If provided, only users with ALL specified permissions are counted.
                         If None or empty, all users are counted regardless of permissions.

    Returns:
        Count of unique users matching the criteria.
    """
    query = (
        db.session.query(func.count(distinct(UserRole.user_id)))
        .join(
            GrantRecipient,
            and_(
                UserRole.organisation_id == GrantRecipient.organisation_id,
                or_(UserRole.grant_id == GrantRecipient.grant_id, UserRole.grant_id.is_(None)),
            ),
        )
        .join(Organisation, Organisation.id == UserRole.organisation_id)
        .filter(
            GrantRecipient.mode == GrantRecipientModeEnum.LIVE,
            Organisation.can_manage_grants.is_(False),
        )
    )

    if with_permissions:
        query = query.filter(UserRole.permissions.contains(with_permissions))

    return query.scalar() or 0


def _models_by_id[T: BaseModel](model: type[T], ids: set[UUID]) -> dict[UUID, T]:
    if not ids:
        return {}

    return {item.id: item for item in db.session.scalars(select(model).where(model.id.in_(ids))).all()}


def _users_by_id(ids: set[UUID]) -> dict[UUID, User]:
    if not ids:
        return {}

    return {
        user.id: user
        for user in db.session.scalars(select(User).where(User.id.in_(ids)).options(selectinload(User.roles))).all()
    }


def _format_datetime(value: datetime.datetime | None) -> str:
    if value is None:
        return ""

    return value.strftime("%d/%m/%Y %H:%M:%S")


def _format_permissions(permissions: list[RoleEnum]) -> str:
    return ", ".join(permission.value for permission in permissions)


def _source_for_event(
    event: UserInvited | UserPermissionsAdded | UserPermissionsRemoved,
    organisation: Organisation | None,
    actor: User | None,
) -> str:
    if (
        isinstance(event, UserPermissionsAdded)
        and event.invitation_id is None
        and event.target_user_id == event.user_id
    ):
        return "public sign-up"

    if actor and any(
        role.organisation_id is None
        and role.grant_id is None
        and (RoleEnum.ADMIN in role.permissions or RoleEnum.GRANT_LIFECYCLE_MANAGER in role.permissions)
        for role in actor.roles
    ):
        return "platform/admin added"

    if organisation is not None and not organisation.can_manage_grants:
        return "self-serve"

    return "platform/admin added"


def _pre_award_or_monitoring(
    grant_recipient: GrantRecipient | None,
    audit_event_timestamp: datetime.datetime,
    collections_by_grant_id: dict[UUID, list[Collection]],
) -> str:
    if grant_recipient is None:
        return "unknown"

    audit_event_date = audit_event_timestamp.date()
    relevant_collection_types = {
        collection.type
        for collection in collections_by_grant_id.get(grant_recipient.grant_id, [])
        if collection.created_at_utc <= audit_event_timestamp
        and collection.submission_period_start_date is not None
        and collection.submission_period_start_date <= audit_event_date
    }

    if relevant_collection_types and relevant_collection_types.issubset(PRE_AWARD_COLLECTIONS):
        return "pre-award"

    if relevant_collection_types and relevant_collection_types.issubset(MONITORING_COLLECTIONS):
        return "monitoring"

    return "unknown"


def get_user_management_event_csv_rows() -> list[UserManagementEventCsvRow]:
    audit_records = db.session.scalars(
        select(AuditEventModel)
        .where(
            AuditEventModel.event_type == AuditEventType.USER_MANAGEMENT,
            AuditEventModel.data["action"].astext.in_(["user_invited", "permissions_added", "permissions_removed"]),
        )
        .order_by(AuditEventModel.created_at_utc, AuditEventModel.id)
    ).all()

    events = [
        parse_audit_event(audit_record.event_type, audit_record.data)
        for audit_record in audit_records
        if audit_record.event_type == AuditEventType.USER_MANAGEMENT
    ]
    user_management_events = [
        event for event in events if isinstance(event, UserInvited | UserPermissionsAdded | UserPermissionsRemoved)
    ]

    user_ids = {event.user_id for event in user_management_events}
    invitation_ids = {event.invitation_id for event in user_management_events if event.invitation_id is not None}
    grant_ids = {event.grant_id for event in user_management_events if event.grant_id is not None}
    organisation_ids = {event.organisation_id for event in user_management_events if event.organisation_id is not None}
    grant_recipient_ids = {
        event.grant_recipient_id for event in user_management_events if event.grant_recipient_id is not None
    }

    users_by_id = _users_by_id(user_ids)
    invitations_by_id = _models_by_id(Invitation, invitation_ids)
    grants_by_id = _models_by_id(Grant, grant_ids)
    organisations_by_id = _models_by_id(Organisation, organisation_ids)
    grant_recipients_by_id = _models_by_id(GrantRecipient, grant_recipient_ids)
    collections_by_grant_id: dict[UUID, list[Collection]] = {grant_id: [] for grant_id in grant_ids}
    if grant_ids:
        for collection in db.session.scalars(select(Collection).where(Collection.grant_id.in_(grant_ids))).all():
            collections_by_grant_id.setdefault(collection.grant_id, []).append(collection)

    rows: list[UserManagementEventCsvRow] = []
    for audit_record, event in zip(audit_records, user_management_events, strict=True):
        invitation = invitations_by_id.get(event.invitation_id) if event.invitation_id else None
        grant = grants_by_id.get(event.grant_id) if event.grant_id else None
        organisation = organisations_by_id.get(event.organisation_id) if event.organisation_id else None
        grant_recipient = grant_recipients_by_id.get(event.grant_recipient_id) if event.grant_recipient_id else None
        actor = users_by_id.get(event.user_id)
        source = _source_for_event(event, organisation, actor)

        rows.append(
            UserManagementEventCsvRow(
                timestamp=_format_datetime(audit_record.created_at_utc),
                event=event.action,
                source=source,
                grant_name=grant.name if grant else "",
                grant_id=str(grant.id) if grant else "",
                grant_ggis_number=grant.ggis_number if grant else "",
                organisation_name=organisation.name if organisation else "",
                organisation_id=str(organisation.id) if organisation else "",
                organisation_external_id=organisation.external_id if organisation else "",
                pre_award_or_monitoring=_pre_award_or_monitoring(
                    grant_recipient,
                    audit_record.created_at_utc,
                    collections_by_grant_id,
                ),
                actor_email=actor.email if actor and source == "platform/admin added" else "",
                permissions=_format_permissions(event.permissions),
                invite_date=_format_datetime(invitation.created_at_utc if invitation else None),
                accepted_date=_format_datetime(invitation.claimed_at_utc if invitation else None),
                unclaimed_invitation=1
                if isinstance(event, UserInvited) and invitation and not invitation.claimed_at_utc
                else 0,
            )
        )

    return rows
