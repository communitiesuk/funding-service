from unittest.mock import patch

import pytest
from flask import Flask
from wtforms import Form, StringField
from wtforms.validators import ValidationError

from app.deliver_grant_funding.forms import GrantGGISForm, UniqueGrantName


def test_unique_grant_name_passes_when_name_does_not_exist():
    validator = UniqueGrantName()

    # Create a simple form for testing
    class TestForm(Form):
        name = StringField()

    form = TestForm()
    form.name.data = "New Grant Name"

    with patch("app.deliver_grant_funding.forms.grant_name_exists", return_value=False):
        # Should not raise any exception
        validator(form, form.name)


def test_unique_grant_name_fails_when_name_exists():
    validator = UniqueGrantName()

    class TestForm(Form):
        name = StringField()

    form = TestForm()
    form.name.data = "Existing Grant"

    with patch("app.deliver_grant_funding.forms.grant_name_exists", return_value=True):
        with pytest.raises(ValidationError, match="Grant name already in use"):
            validator(form, form.name)


def test_grant_ggis_form_validates_when_no_selected(app: Flask):
    app.config["SECRET_KEY"] = "test-key"  # pragma: allowlist secret

    with app.test_request_context():
        form = GrantGGISForm(data={"has_ggis": "no", "ggis_number": ""})

        # Should return True when "no" is selected and GGIS number can be empty
        assert form.validate() is True
        assert len(form.ggis_number.errors) == 0


def test_grant_ggis_form_validates_when_yes_selected_with_ggis_number(app: Flask):
    app.config["SECRET_KEY"] = "test-key"  # pragma: allowlist secret

    with app.test_request_context():
        form = GrantGGISForm(data={"has_ggis": "yes", "ggis_number": "GGIS123456"})

        # Should return True when "yes" is selected and GGIS number is provided
        assert form.validate() is True
        assert len(form.ggis_number.errors) == 0


def test_grant_ggis_form_fails_when_yes_selected_and_empty(app: Flask):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-key"  # pragma: allowlist secret
    app.config["WTF_CSRF_ENABLED"] = False  # Disable CSRF for testing

    with app.test_request_context():
        form = GrantGGISForm(data={"has_ggis": "yes", "ggis_number": ""})

        # Should return False when "yes" is selected but GGIS number is empty
        assert form.validate() is False
        assert "Enter your GGIS reference number" in form.ggis_number.errors
