from unittest.mock import patch

import pytest
from wtforms import Form, StringField
from wtforms.validators import ValidationError

from app.deliver_grant_funding.forms import UniqueGrantName


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
