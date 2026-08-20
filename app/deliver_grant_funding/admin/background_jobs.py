import datetime
import uuid
from dataclasses import dataclass
from typing import Any, ClassVar

import markupsafe
from flask_sqlalchemy_lite import SQLAlchemy
from sqlalchemy import BigInteger, Integer, LargeBinary, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from xgovuk_flask_admin import XGovukModelView

from app.deliver_grant_funding.admin.mixins import FlaskAdminPlatformAdminAccessibleMixin

# Read-only Flask Admin view over pgqueuer's own tables. This is here because otherwise the PoC is awkward to inspect
# locally, we need further discussions about how we will design the long-term admin view.


class PgQueuerBase(DeclarativeBase):
    pass


@dataclass(frozen=True)
class BackgroundJobAdminView:
    view_class: type["PlatformAdminPgQueuerModelView"]
    name: str
    endpoint: str
    url: str
    category: str = "Developer tools"


class PgQueuerJob(PgQueuerBase):
    __tablename__ = "pgqueuer"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    priority: Mapped[int] = mapped_column(Integer)
    queue_manager_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created: Mapped[datetime.datetime]
    updated: Mapped[datetime.datetime]
    heartbeat: Mapped[datetime.datetime]
    execute_after: Mapped[datetime.datetime]
    status: Mapped[str] = mapped_column(Text)
    entrypoint: Mapped[str] = mapped_column(Text)
    dedupe_key: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[bytes | None] = mapped_column(LargeBinary)
    headers: Mapped[dict[str, str] | None] = mapped_column(JSONB)
    attempts: Mapped[int] = mapped_column(Integer)

    def __str__(self) -> str:
        return f"PgQueuerJob({self.id})"


def _format_bytes_payload(view: Any, context: Any, model: PgQueuerJob, name: str) -> markupsafe.Markup:
    del view, context
    payload = getattr(model, name)
    if payload is None:
        return markupsafe.Markup("—")

    return markupsafe.Markup("<pre>{}</pre>").format(payload.decode(errors="replace"))


class PlatformAdminPgQueuerModelView(FlaskAdminPlatformAdminAccessibleMixin, XGovukModelView):
    _model: ClassVar[type[PgQueuerBase]]

    page_size = 50
    can_set_page_size = True

    can_create = False
    can_view_details = True
    can_edit = False
    can_delete = False
    can_export = False

    def __init__(
        self,
        session: SQLAlchemy,
        name: str | None = None,
        category: str | None = None,
        endpoint: str | None = None,
        url: str | None = None,
        static_folder: str | None = None,
        menu_class_name: str | None = None,
        menu_icon_type: str | None = None,
        menu_icon_value: str | None = None,
    ) -> None:
        super().__init__(
            self._model,
            session,
            name=name,
            category=category,
            endpoint=endpoint,
            url=url,
            static_folder=static_folder,
            menu_class_name=menu_class_name,
            menu_icon_type=menu_icon_type,
            menu_icon_value=menu_icon_value,
        )


class PlatformAdminPgQueuerJobView(PlatformAdminPgQueuerModelView):
    _model = PgQueuerJob

    column_default_sort = ("created", True)
    column_list = ["id", "status", "entrypoint", "attempts", "execute_after"]
    column_details_list = [
        "id",
        "status",
        "entrypoint",
        "dedupe_key",
        "priority",
        "attempts",
        "created",
        "updated",
        "heartbeat",
        "execute_after",
        "queue_manager_id",
        "headers",
        "payload",
    ]
    column_filters = ["status", "entrypoint", "created", "execute_after", "updated"]
    column_searchable_list = ["entrypoint", "dedupe_key"]
    column_formatters_detail = {"payload": _format_bytes_payload}
    column_labels = {
        "dedupe_key": "Dedupe key",
        "execute_after": "Execute after",
        "queue_manager_id": "Queue manager ID",
    }

    def search_placeholder(self) -> str:
        return "Entrypoint, dedupe key"


BACKGROUND_JOB_ADMIN_VIEWS = (
    BackgroundJobAdminView(
        view_class=PlatformAdminPgQueuerJobView,
        name="Background jobs",
        endpoint="background_jobs_admin",
        url="background-jobs",
    ),
)
