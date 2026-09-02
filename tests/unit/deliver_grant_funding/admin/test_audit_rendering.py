import datetime
import re
from unittest.mock import call
from uuid import uuid4

import pytest
from markupsafe import Markup

from app.common.audit import DatabaseModelChange, SystemEvent, UserPermissionsAdded
from app.common.data.types import AuditEventType, RoleEnum
from app.deliver_grant_funding.admin.audit_rendering import AuditEventDetailsRenderer, _field_label, _render_value
from app.deliver_grant_funding.admin.entities import PlatformAdminModelView


class TestFieldLabel:
    @pytest.mark.parametrize(
        "field_name, expected",
        [
            ("user_id", "User"),
            ("model_id", "Model"),
            ("id", "Id"),
            ("_data", "Data"),
            ("resulting_permissions", "Resulting permissions"),
        ],
    )
    def test_humanises_field_name(self, field_name, expected):
        assert _field_label(field_name) == expected


class TestRenderValue:
    def test_renders_none_as_dash(self):
        assert _render_value(None) == "—"

    def test_renders_empty_list_as_dash(self):
        assert _render_value([]) == "—"

    def test_renders_enum_value(self):
        assert _render_value(RoleEnum.DATA_PROVIDER) == "data-provider"

    def test_renders_list_comma_separated(self):
        assert _render_value([RoleEnum.DATA_PROVIDER, RoleEnum.MEMBER]) == "data-provider, member"

    def test_renders_dict_as_escaped_json_in_pre_block(self):
        result = _render_value({"name": {"old": "<b>", "new": "B"}})

        assert result.startswith("<pre class='govuk-!-margin-0'>")
        assert result.endswith("</pre>")
        assert "&#34;old&#34;: &#34;&lt;b&gt;&#34;" in result

    def test_renders_datetime_as_isoformat(self):
        value = datetime.datetime(2026, 8, 27, 10, 30, tzinfo=datetime.UTC)

        assert _render_value(value) == "2026-08-27T10:30:00+00:00"

    def test_escapes_strings(self):
        assert _render_value("<script>") == "&lt;script&gt;"

    def test_renders_newlines_in_strings_as_line_breaks(self):
        assert _render_value("first line\nsecond line") == "first line<br>second line"


class TestAuditEventDetailsRenderer:
    @pytest.fixture
    def render_entity_link(self, mocker):
        return mocker.patch.object(
            AuditEventDetailsRenderer,
            "_render_entity_link",
            side_effect=lambda model_name, entity_id: Markup(f"<a>{model_name}:{entity_id}</a>"),
        )

    @pytest.fixture
    def renderer(self, app, render_entity_link):
        admin = app.extensions["admin"][0]
        return AuditEventDetailsRenderer(view for view in admin._views if isinstance(view, PlatformAdminModelView))

    def test_renders_common_fields_first(self, renderer):
        event = UserPermissionsAdded(
            user_id=uuid4(),
            target_user_id=uuid4(),
            organisation_id=None,
            grant_id=None,
            grant_recipient_id=None,
            permissions=[RoleEnum.MEMBER],
            resulting_permissions=[RoleEnum.MEMBER],
        )

        html = renderer.render(event)

        labels = re.findall(r'<dt class="govuk-summary-list__key">([^<]*)</dt>', html)
        assert labels[:4] == ["Event type", "Timestamp", "User", "Action"]

    def test_update_renders_old_and_new_values_with_entity_links(self, renderer, render_entity_link):
        old_organisation_id, new_organisation_id = uuid4(), uuid4()
        event = DatabaseModelChange(
            user_id=uuid4(),
            model_class="Grant",
            model_id=uuid4(),
            action="update",
            changes={
                "name": {"old": "A", "new": "B"},
                "organisation_id": {"old": str(old_organisation_id), "new": str(new_organisation_id)},
            },
        )

        html = renderer.render(event)

        assert "A → B" in html
        assert f"<a>Organisation:{old_organisation_id}</a> → <a>Organisation:{new_organisation_id}</a>" in html
        assert call("Grant", str(event.model_id)) in render_entity_link.call_args_list

    def test_snapshot_links_id_via_model_class(self, renderer, render_entity_link):
        model_id = uuid4()
        event = DatabaseModelChange(
            user_id=uuid4(),
            model_class="Grant",
            model_id=model_id,
            action="create",
            changes={"id": str(model_id), "name": "Test Grant"},
        )

        html = renderer.render(event)

        assert render_entity_link.call_args_list.count(call("Grant", str(model_id))) == 2
        assert "Test Grant" in html

    def test_unknown_model_class_renders_bare_ids(self):
        model_id = uuid4()
        event = DatabaseModelChange(
            user_id=uuid4(), model_class="Widget", model_id=model_id, action="create", changes={"id": str(model_id)}
        )

        html = AuditEventDetailsRenderer([]).render(event)

        assert html.count(str(model_id)) == 2
        assert "<a" not in html

    def test_null_related_column_renders_dash(self, renderer, render_entity_link):
        event = DatabaseModelChange(
            user_id=uuid4(), model_class="Widget", model_id=uuid4(), action="create", changes={"grant_id": None}
        )

        html = renderer.render(event)

        assert '<dt class="govuk-summary-list__key">Grant</dt><dd class="govuk-summary-list__value">—</dd>' in html
        assert render_entity_link.call_args_list == [
            call("User", str(event.user_id)),
            call("Widget", str(event.model_id)),
        ]

    def test_empty_changes_renders_dash(self, renderer):
        event = DatabaseModelChange(user_id=uuid4(), model_class="Grant", model_id=uuid4(), action="delete", changes={})

        html = renderer.render(event)

        assert '<dt class="govuk-summary-list__key">Changes</dt><dd class="govuk-summary-list__value">—</dd>' in html

    def test_system_event_renders_context_rows(self, renderer):
        notification_id = uuid4()
        event = SystemEvent(
            user_id=uuid4(),
            model_class="UserRole",
            model_id=uuid4(),
            action="delete",
            changes={},
            context={"notification_id": str(notification_id), "reason": "Permanent delivery failure"},
        )

        html = renderer.render(event)

        expected_row = (
            '<dt class="govuk-summary-list__key">Notification</dt>'
            f'<dd class="govuk-summary-list__value">{notification_id}</dd>'
        )
        assert expected_row in html
        assert "Permanent delivery failure" in html
        assert "<pre" not in html

    def test_only_nested_lists_are_borderless(self, renderer):
        event = DatabaseModelChange(
            user_id=uuid4(),
            model_class="Grant",
            model_id=uuid4(),
            action="update",
            changes={"name": {"old": "A", "new": "B"}},
        )

        html = renderer.render(event)

        assert html.startswith('<dl class="govuk-summary-list">')
        assert html.count('<dl class="govuk-summary-list govuk-summary-list--no-border govuk-!-margin-bottom-0">') == 1

    def test_renders_unparsed_event_from_row_columns_and_raw_payload(self, renderer, render_entity_link, factories):
        model = factories.audit_event.build(
            event_type=AuditEventType.USER_MANAGEMENT,
            created_at_utc=datetime.datetime(2026, 8, 27, 10, 30, tzinfo=datetime.UTC),
            data={"action": "team_member_added"},
        )

        html = renderer.render_unparsed(model)

        labels = re.findall(r'<dt class="govuk-summary-list__key">([^<]*)</dt>', html)
        assert labels == ["Event type", "User", "Created at UTC", "Data"]
        assert "user-management" in html
        assert f"<a>User:{model.user_id}</a>" in html
        assert "2026-08-27T10:30:00+00:00" in html
        assert "&#34;action&#34;: &#34;team_member_added&#34;" in html
