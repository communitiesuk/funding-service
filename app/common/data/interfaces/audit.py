from flask import current_app

from app.common.audit import AuditEvent
from app.common.data.interfaces.exceptions import flush_and_rollback_on_exceptions
from app.common.data.models_audit import AuditEvent as AuditEventModel
from app.common.data.models_user import User
from app.extensions import db


@flush_and_rollback_on_exceptions
def track_audit_event(event: AuditEvent, user: User) -> None:
    audit_record = AuditEventModel(
        event_type=event.event_type,
        user_id=event.user_id,
        data=event.model_dump(mode="json"),
    )
    db.session.add(audit_record)

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
