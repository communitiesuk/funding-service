import uuid

from flask import current_app

from app.common.audit import AuditEvent
from app.common.data.interfaces.exceptions import flush_and_rollback_on_exceptions
from app.common.data.models_audit import AuditEvent as AuditEventModel
from app.common.data.models_user import User
from app.extensions import db


@flush_and_rollback_on_exceptions
def track_audit_event(event: AuditEvent, user: User) -> None:
    audit_record = AuditEventModel(
        # set up front rather than on flush, so the log line can point at the row
        id=uuid.uuid4(),
        event_type=event.event_type,
        user_id=event.user_id,
        data=event.model_dump(mode="json"),
    )
    db.session.add(audit_record)

    current_app.logger.info(
        "audit_event: %(event_type)s",
        {"event_type": event.event_type},
        extra={
            "audit_event_type": event.event_type,
            "audit_event_id": str(audit_record.id),
            "audit_user_id": str(event.user_id),
        },
    )
