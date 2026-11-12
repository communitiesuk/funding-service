import datetime
from uuid import UUID

from sqlalchemy import select

from app.common.audit import DatabaseModelChange
from app.common.data.interfaces.audit import track_audit_event
from app.common.data.models_audit import AuditEvent
from app.common.data.models_user import User
from app.common.data.types import AuditEventType
from app.extensions import db


def get_completed_dashboard_event_keys() -> set[tuple[UUID, str, datetime.date]]:
    audit_event_data = db.session.scalars(
        select(AuditEvent.data)
        .where(
            AuditEvent.event_type == AuditEventType.PLATFORM_ADMIN_DB_EVENT,
            AuditEvent.data["model_class"].astext == "Collection",
            AuditEvent.data["action"].astext == "update",
        )
        .order_by(AuditEvent.created_at_utc, AuditEvent.id)
    )
    completed: set[tuple[UUID, str, datetime.date]] = set()
    for data in audit_event_data:
        collection_id = UUID(data["model_id"])
        for field, change in data["changes"].items():
            if not field.startswith("dashboard_event:"):
                continue
            _, event_type, event_date = field.split(":", maxsplit=2)
            event_key = (collection_id, event_type, datetime.date.fromisoformat(event_date))
            if change.get("new") == "done":
                completed.add(event_key)
            elif change.get("new") == "pending":
                completed.discard(event_key)
    return completed


def set_dashboard_event_completion(
    *, collection_id: UUID, event_type: str, event_date: datetime.date, is_done: bool, changed_by: User
) -> None:
    event_key = (collection_id, event_type, event_date)
    currently_done = event_key in get_completed_dashboard_event_keys()
    if currently_done == is_done:
        return

    old_status, new_status = ("pending", "done") if is_done else ("done", "pending")
    event = DatabaseModelChange(
        user_id=changed_by.id,
        model_class="Collection",
        model_id=collection_id,
        action="update",
        changes={f"dashboard_event:{event_type}:{event_date.isoformat()}": {"old": old_status, "new": new_status}},
    )
    track_audit_event(event, changed_by)
