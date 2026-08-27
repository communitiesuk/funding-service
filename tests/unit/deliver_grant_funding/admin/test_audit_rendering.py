import datetime
import re
from uuid import uuid4

import pytest
from markupsafe import Markup

from app.common.audit import UserPermissionsAdded
from app.common.data.types import RoleEnum
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
