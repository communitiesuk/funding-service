import datetime
import enum
from typing import Any, Literal
from uuid import UUID

from flask import current_app
from pydantic import BaseModel, Field
from sqlalchemy import inspect
from sqlalchemy.orm import Session, scoped_session

from app.common.data.base import BaseModel as SQLAlchemyBaseModel
from app.common.data.models_audit import AuditEvent as AuditEventModel
from app.common.data.models_user import User
from app.common.data.types import AuditEventType


class AuditEvent(BaseModel):
    user_id: UUID
    timestamp: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    event_type: AuditEventType


class DatabaseModelChange(AuditEvent):
    event_type: AuditEventType = AuditEventType.PLATFORM_ADMIN_DB_EVENT
    model_class: str
    model_id: UUID
    action: Literal["create", "update", "delete"]
    changes: dict[str, Any]


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


def track_audit_event(session: scoped_session[Session], event: AuditEvent, user: User) -> None:
    audit_record = AuditEventModel(
        event_type=event.event_type,
        user_id=event.user_id,
        data=event.model_dump(mode="json"),
    )
    session.add(audit_record)

    current_app.logger.info(
        "audit_event: %(event_type)s by %(user_email)s",
        {"event_type": event.event_type, "user_email": user.email},
        extra={
            "audit": True,
            "event_type": event.event_type,
            "user_id": str(event.user_id),
            "user_email": user.email,
            "event_data": event.model_dump(mode="json"),
        },
    )
