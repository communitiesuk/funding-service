import uuid
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import mapped_column, Mapped


class Grant:
    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        default=func.now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now,
    )
    name: Mapped[str]
