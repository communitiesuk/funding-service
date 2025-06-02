from unittest.mock import patch

import pytest
from wtforms import Form, RadioField, StringField
from wtforms.validators import ValidationError

from app.deliver_grant_funding.forms import ConditionalGGISRequired, UniqueGrantName


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


def test_conditional_ggis_required_passes_when_no_selected():
    validator = ConditionalGGISRequired()

    class TestForm(Form):
        has_ggis = RadioField()
        ggis_number = StringField()

    form = TestForm()
    form.has_ggis.data = "no"
    form.ggis_number.data = ""

    # Should not raise any exception when "no" is selected
    validator(form, form.ggis_number)


def test_conditional_ggis_required_fails_when_yes_selected_and_empty():
    validator = ConditionalGGISRequired()

    class TestForm(Form):
        has_ggis = RadioField()
        ggis_number = StringField()

    form = TestForm()
    form.has_ggis.data = "yes"
    form.ggis_number.data = ""

    with pytest.raises(ValidationError, match="Enter your GGIS reference number"):
        validator(form, form.ggis_number)
