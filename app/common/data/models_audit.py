import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.data.base import BaseModel
from app.common.data.types import AuditEventType, json_scalars

if TYPE_CHECKING:
    from app.common.data.models_user import User


class AuditEvent(BaseModel):
    __tablename__ = "audit_event"

    event_type: Mapped[AuditEventType]
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    data: Mapped[json_scalars] = mapped_column(JSONB)

    user: Mapped["User"] = relationship("User")

    __table_args__ = (
        Index("ix_audit_event_event_type", "event_type"),
        Index("ix_audit_event_created_at_utc", "created_at_utc"),
        Index("ix_audit_event_user_id", "user_id"),
        Index("ix_audit_event_data_model_class", text("(data->>'model_class')")),
        Index("ix_audit_event_data_action", text("(data->>'action')")),
    )
