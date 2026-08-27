import datetime
import enum
import json
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from flask import url_for
from markupsafe import Markup, escape

from app.common.audit import AuditEvent

if TYPE_CHECKING:
    from app.deliver_grant_funding.admin.entities import PlatformAdminModelView

_ROW = Markup(
    '<div class="govuk-summary-list__row">'
    '<dt class="govuk-summary-list__key">{label}</dt>'
    '<dd class="govuk-summary-list__value">{value}</dd>'
    "</div>"
)


def render_json_pre(data: Any) -> Markup:
    return Markup("<pre class='govuk-!-margin-0'>{}</pre>").format(json.dumps(data, indent=2))


class AuditEventDetailsRenderer:
    """Renders a parsed audit event as nested GOV.UK summary lists, linking entity ids to their admin details pages."""

    def __init__(self, views: Iterable["PlatformAdminModelView"]) -> None:
        self._views_by_model_name = {view.model.__name__: view for view in views}

    def render(self, event: AuditEvent) -> Markup:
        return _summary_list(
            (_field_label(field_name), self._render_field(event, field_name)) for field_name in type(event).model_fields
        )

    def _render_field(self, event: AuditEvent, field_name: str) -> Markup:
        value = getattr(event, field_name)
        if value is not None and field_name in event.related_entities:
            return self._render_entity_link(event.related_entities[field_name], str(value))
        return _render_value(value)

    def _render_entity_link(self, model_name: str, entity_id: str) -> Markup:
        view = self._views_by_model_name.get(model_name)
        if view is None:
            return escape(entity_id)

        entity = view.get_one(entity_id)
        if entity is None:
            return escape(f"{entity_id} (deleted)")

        href = url_for(f"{view.endpoint}.details_view", id=entity_id)
        return Markup('<a class="govuk-link" href="{href}">{label}</a>').format(
            href=href, label=view.entity_label(entity)
        )


def _field_label(field_name: str) -> str:
    return field_name.removesuffix("_id").strip("_").replace("_", " ").capitalize()


def _summary_list(rows: Iterable[tuple[str, Markup]]) -> Markup:
    return (
        Markup('<dl class="govuk-summary-list">')
        + Markup("").join(_ROW.format(label=label, value=value) for label, value in rows)
        + Markup("</dl>")
    )


def _render_value(value: Any) -> Markup:
    if value is None or value == []:
        return Markup("—")
    if isinstance(value, enum.Enum):
        return escape(value.value)
    if isinstance(value, list):
        return Markup(", ").join(_render_value(v) for v in value)
    if isinstance(value, dict):
        return render_json_pre(value)
    if isinstance(value, datetime.datetime):
        return escape(value.isoformat())
    return escape(str(value)).replace("\n", Markup("<br>"))
