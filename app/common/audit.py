import datetime
import enum
from collections import ChainMap
from typing import Annotated, Any, ClassVar, Literal
from uuid import UUID

from pydantic import BaseModel, Field, TypeAdapter
from sqlalchemy import inspect
from sqlalchemy.orm import RelationshipDirection

from app.common.data.base import BaseModel as SQLAlchemyBaseModel
from app.common.data.models_user import User
from app.common.data.types import AuditEventType, RoleEnum


class AuditEvent(BaseModel):
    event_type: AuditEventType
    timestamp: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.UTC))
    user_id: UUID
    action: str

    # Fields holding a DB entity's primary key, mapped to the name of that entity's model class so admin rendering can
    # link to it.
    _related_entities: ClassVar[dict[str, str]] = {
        "user_id": "User",
        "created_by_id": "User",
        "grant_id": "Grant",
        "grant_recipient_id": "GrantRecipient",
        "organisation_id": "Organisation",
        "invitation_id": "Invitation",
        "collection_id": "Collection",
        "submission_id": "Submission",
    }
    _extra_related_entities: ClassVar[dict[str, str]] = {}

    @property
    def related_entities(self) -> ChainMap[str, str]:
        return ChainMap(self._extra_related_entities, self._related_entities)


class DatabaseModelChange(AuditEvent):
    event_type: AuditEventType = AuditEventType.PLATFORM_ADMIN_DB_EVENT
    model_class: str
    model_id: UUID
    action: Literal["create", "update", "delete"]
    changes: dict[str, Any]

    @property
    def related_entities(self) -> ChainMap[str, str]:
        return ChainMap({"model_id": self.model_class, "id": self.model_class}, super().related_entities)


class SystemEvent(DatabaseModelChange):
    event_type: AuditEventType = AuditEventType.SYSTEM
    context: dict[str, Any]


class UserPermissionsEvent(AuditEvent):
    """`permissions` are those added to or removed from the target user's role by this action:

    `resulting_permissions` are the role's full set afterwards (empty if it was deleted).
    `organisation_id` is None for platform-wide roles,
    `grant_id` is None for organisation-wide roles, and
    `grant_recipient_id` is only set for Access grant funding roles on a grant.
    `invitation_id` is set when the permissions were granted by the target user claiming an invitation.
    """

    event_type: AuditEventType = AuditEventType.USER_MANAGEMENT
    target_user_id: UUID
    organisation_id: UUID | None
    grant_id: UUID | None
    grant_recipient_id: UUID | None
    invitation_id: UUID | None = None
    permissions: list[RoleEnum]
    resulting_permissions: list[RoleEnum]

    _extra_related_entities: ClassVar[dict[str, str]] = {"target_user_id": "User"}


class UserPermissionsAdded(UserPermissionsEvent):
    action: Literal["permissions_added"] = "permissions_added"


class UserPermissionsRemoved(UserPermissionsEvent):
    action: Literal["permissions_removed"] = "permissions_removed"


class UserInvited(AuditEvent):
    """Tracked when `user_id` invites someone to take on `permissions`; the invitation itself holds their email.

    The UserPermissionsAdded event tracked when they claim the invitation records the same `invitation_id`.
    `organisation_id`, `grant_id` and `grant_recipient_id` follow the same rules as UserPermissionsEvent.
    """

    event_type: AuditEventType = AuditEventType.USER_MANAGEMENT
    action: Literal["user_invited"] = "user_invited"
    invitation_id: UUID
    organisation_id: UUID | None
    grant_id: UUID | None
    grant_recipient_id: UUID | None
    permissions: list[RoleEnum]


_audit_event_adapters: dict[AuditEventType, TypeAdapter[Any]] = {
    AuditEventType.PLATFORM_ADMIN_DB_EVENT: TypeAdapter(DatabaseModelChange),
    AuditEventType.SYSTEM: TypeAdapter(SystemEvent),
    AuditEventType.USER_MANAGEMENT: TypeAdapter(
        Annotated[UserPermissionsAdded | UserPermissionsRemoved | UserInvited, Field(discriminator="action")]
    ),
}


def parse_audit_event(event_type: AuditEventType, data: dict[str, Any]) -> AuditEvent:
    return _audit_event_adapters[event_type].validate_python(data)


def _serialize_value(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, enum.Enum):
        return value.name
    if isinstance(value, (list, tuple)):
        return [_serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    return value


def _get_model_changes(model: SQLAlchemyBaseModel) -> dict[str, dict[str, Any]]:
    insp = inspect(model)
    changes: dict[str, dict[str, Any]] = {}

    for column in insp.mapper.column_attrs:
        if column.key in ("created_at_utc", "updated_at_utc"):
            continue

        history = insp.attrs[column.key].history
        if history.has_changes():
            old_val = history.deleted[0] if history.deleted else None
            new_val = history.added[0] if history.added else None

            old_serialized = _serialize_value(old_val)
            new_serialized = _serialize_value(new_val)

            if old_serialized != new_serialized:
                changes[column.key] = {
                    "old": old_serialized,
                    "new": new_serialized,
                }

    # Admin edit forms set relationship attributes, and the FK columns above only sync with them at flush time —
    # after this snapshot is taken — so record relationship changes under their FK column's key too.
    for relationship in insp.mapper.relationships:
        if relationship.direction is not RelationshipDirection.MANYTOONE:
            continue

        fk_column_key = insp.mapper.get_property_by_column(relationship.local_remote_pairs[0][0]).key
        if fk_column_key in changes:
            continue

        history = insp.attrs[relationship.key].history
        if history.has_changes():
            old_entity = history.deleted[0] if history.deleted else None
            new_entity = history.added[0] if history.added else None

            old_serialized = _serialize_value(old_entity.id if old_entity else None)
            new_serialized = _serialize_value(new_entity.id if new_entity else None)

            if old_serialized != new_serialized:
                changes[fk_column_key] = {
                    "old": old_serialized,
                    "new": new_serialized,
                }

    return changes


def _get_model_snapshot(model: SQLAlchemyBaseModel) -> dict[str, Any]:
    insp = inspect(model)
    snapshot: dict[str, Any] = {}

    for column in insp.mapper.column_attrs:
        if column.key in ("created_at_utc", "updated_at_utc"):
            continue

        value = getattr(model, column.key, None)
        snapshot[column.key] = _serialize_value(value)

    return snapshot


def create_database_model_change_for_update(
    model: SQLAlchemyBaseModel,
    user: User,
) -> DatabaseModelChange | None:
    changes = _get_model_changes(model)
    if not changes:
        return None

    return DatabaseModelChange(
        user_id=user.id,
        model_class=model.__class__.__name__,
        model_id=model.id,
        action="update",
        changes=changes,
    )


def create_database_model_change_for_create(
    model: SQLAlchemyBaseModel,
    user: User,
) -> DatabaseModelChange:
    snapshot = _get_model_snapshot(model)

    return DatabaseModelChange(
        user_id=user.id,
        model_class=model.__class__.__name__,
        model_id=model.id,
        action="create",
        changes=snapshot,
    )


def create_database_model_change_for_delete(
    model: SQLAlchemyBaseModel,
    user: User,
) -> DatabaseModelChange:
    snapshot = _get_model_snapshot(model)

    return DatabaseModelChange(
        user_id=user.id,
        model_class=model.__class__.__name__,
        model_id=model.id,
        action="delete",
        changes=snapshot,
    )


def create_system_event_for_delete(
    model: SQLAlchemyBaseModel,
    user: User,
    context: dict[str, Any],
) -> SystemEvent:
    snapshot = _get_model_snapshot(model)

    return SystemEvent(
        user_id=user.id,
        model_class=model.__class__.__name__,
        model_id=model.id,
        action="delete",
        changes=snapshot,
        context=context,
    )
