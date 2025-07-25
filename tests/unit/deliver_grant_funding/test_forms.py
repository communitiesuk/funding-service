from unittest import mock
from unittest.mock import patch

import pytest
from flask import Flask, request
from werkzeug.datastructures import MultiDict
from wtforms import ValidationError

from app.common.data.types import QuestionDataType, RoleEnum
from app.deliver_grant_funding.forms import (
    GrantAddUserForm,
    GrantGGISForm,
    GrantNameForm,
    QuestionForm,
    _validate_no_blank_lines,
    _validate_no_duplicates,
    strip_string_if_not_empty,
)


class TestFilters:
    def test_strip_string_if_not_empty(self):
        assert strip_string_if_not_empty("  blah ") == "blah"


class TestValidators:
    def test_validate_no_blank_lines(self):
        _validate_no_blank_lines(mock.Mock(), mock.Mock(data="  blah  "))

        with pytest.raises(ValidationError):
            _validate_no_blank_lines(mock.Mock(), mock.Mock(data="    "))

    def test_validate_no_duplicates(self):
        _validate_no_duplicates(mock.Mock(), mock.Mock(data="a\nb\nc"))

        with pytest.raises(ValidationError):
            _validate_no_duplicates(mock.Mock(), mock.Mock(data="a\na\na"))


def test_grant_name_form_passes_when_name_does_not_exist():
    form = GrantNameForm()
    form.name.data = "New Grant"

    with patch("app.deliver_grant_funding.forms.grant_name_exists", return_value=False):
        assert form.validate() is True
        assert len(form.name.errors) == 0


def test_grant_name_form_fails_when_name_exists():
    form = GrantNameForm()
    form.name.data = "Existing Grant"

    with patch("app.deliver_grant_funding.forms.grant_name_exists", return_value=True):
        assert form.validate() is False
        assert "Grant name already in use" in form.name.errors


def test_grant_ggis_form_validates_when_no_selected(app: Flask):
    print(request)
    form = GrantGGISForm(data={"has_ggis": "no", "ggis_number": ""})

    # Should return True when "no" is selected and GGIS number can be empty
    assert form.validate() is True
    assert len(form.ggis_number.errors) == 0


def test_grant_ggis_form_validates_when_yes_selected_with_ggis_number(app: Flask):
    form = GrantGGISForm(data={"has_ggis": "yes", "ggis_number": "GGIS123456"})

    # Should return True when "yes" is selected and GGIS number is provided
    assert form.validate() is True
    assert len(form.ggis_number.errors) == 0


def test_grant_ggis_form_fails_when_yes_selected_and_empty(app: Flask):
    form = GrantGGISForm(data={"has_ggis": "yes", "ggis_number": ""})

    # Should return False when "yes" is selected but GGIS number is empty
    assert form.validate() is False
    assert "Enter your GGIS reference number" in form.ggis_number.errors


def test_user_already_in_grant_users(app: Flask, factories):
    grant = factories.grant.build(name="Test Grant")
    user = factories.user.build(email="test.user@communities.gov.uk")
    factories.user_role.build(user=user, role=RoleEnum.MEMBER, grant=grant)

    form = GrantAddUserForm(grant=grant)
    form.user_email.data = "test.admin@communities.gov.uk"

    with (
        patch("app.deliver_grant_funding.forms.get_user_by_email", return_value=user),
    ):
        assert form.validate() is False
        assert "already is a member of" in form.user_email.errors[0]


def test_user_already_platform_admin(app: Flask, factories):
    grant = factories.grant.build(name="Test")
    user = factories.user.build(email="test.user@communities.gov.uk")
    factories.user_role.build(user=user, role=RoleEnum.ADMIN)

    form = GrantAddUserForm(grant=grant)
    form.user_email.data = "test.admin@communities.gov.uk"

    with patch("app.deliver_grant_funding.forms.get_user_by_email", return_value=user):
        assert form.validate() is False
        assert "already exists as a Funding Service admin user" in form.user_email.errors[0]


class TestQuestionForm:
    def test_max_data_source_items(self, app):
        max_data_source_items = app.config["MAX_DATA_SOURCE_ITEMS"]
        form = QuestionForm(question_type=QuestionDataType.RADIOS)

        formdata = MultiDict(
            [
                ("text", "question"),
                ("hint", ""),
                ("name", "name"),
                ("data_source_items", "\n".join(str(x) for x in range(max_data_source_items))),
            ]
        )

        form.process(formdata)

        assert form.validate() is True
        assert form.errors == {}

    def test_too_many_data_source_items(self, app):
        max_data_source_items = app.config["MAX_DATA_SOURCE_ITEMS"]
        form = QuestionForm(question_type=QuestionDataType.RADIOS)

        formdata = MultiDict(
            [
                ("text", "question"),
                ("hint", ""),
                ("name", "name"),
                ("data_source_items", "\n".join(str(x) for x in range(max_data_source_items + 1))),
            ]
        )

        form.process(formdata)

        assert form.validate() is False
        assert form.errors == {
            "data_source_items": [f"You have entered too many options. The maximum is {max_data_source_items}"]
        }
