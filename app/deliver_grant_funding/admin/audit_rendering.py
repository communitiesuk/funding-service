import datetime
import enum
import json
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from flask import url_for
from markupsafe import Markup, escape

from app.common.audit import AuditEvent, DatabaseModelChange, SystemEvent

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
            (
                (_field_label(field_name), self._render_field(event, field_name))
                for field_name in type(event).model_fields
            ),
            nested=False,
        )

    def _render_field(self, event: AuditEvent, field_name: str) -> Markup:
        if isinstance(event, DatabaseModelChange) and field_name == "changes":
            return self._render_changes(event)
        if isinstance(event, SystemEvent) and field_name == "context":
            return self._render_context(event)

        value = getattr(event, field_name)
        if value is not None and field_name in event.related_entities:
            return self._render_entity_link(event.related_entities[field_name], str(value))
        return _render_value(value)

    def _render_changes(self, event: DatabaseModelChange) -> Markup:
        if not event.changes:
            return _render_value(None)

        return _summary_list(
            (
                (_field_label(column), self._render_change(event, column, value))
                for column, value in event.changes.items()
            ),
            nested=True,
        )

    def _render_change(self, event: DatabaseModelChange, column: str, value: Any) -> Markup:
        if event.action == "update":
            return Markup("{old} → {new}").format(
                old=self._render_column_value(event, column, value["old"]),
                new=self._render_column_value(event, column, value["new"]),
            )
        return self._render_column_value(event, column, value)

    def _render_column_value(self, event: DatabaseModelChange, column: str, value: Any) -> Markup:
        # Column values come straight from the stored JSON, so entity ids are already strings.
        if value is not None and column in event.related_entities:
            return self._render_entity_link(event.related_entities[column], value)
        return _render_value(value)

    def _render_context(self, event: SystemEvent) -> Markup:
        if not event.context:
            return _render_value(None)

        return _summary_list(
            ((_field_label(key), _render_value(value)) for key, value in event.context.items()), nested=True
        )

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


def _summary_list(rows: Iterable[tuple[str, Markup]], *, nested: bool) -> Markup:
    classes = "govuk-summary-list"
    if nested:
        classes += " govuk-summary-list--no-border govuk-!-margin-bottom-0"

    return (
        Markup('<dl class="{classes}">').format(classes=classes)
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
