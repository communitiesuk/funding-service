from bs4 import BeautifulSoup
from flask_wtf import FlaskForm
from wtforms import RadioField, SelectMultipleField
from wtforms.validators import DataRequired

from app.common.forms.fields import MHCLGCheckboxesInput, MHCLGRadioInput


class TestMHCLGRadioInput:
    def test_standard_radios_are_not_divided(self):
        class TestForm(FlaskForm):
            field = RadioField(
                "test",
                widget=MHCLGRadioInput(),
                choices=[(x, str(x)) for x in range(10)],
            )

        form = TestForm()

        soup = BeautifulSoup(str(form.field), "html.parser")
        assert len(soup.select("input[type=radio]")) == 10
        assert soup.select(".govuk-radios__divider") == []

    def test_divided_radios(self):
        class TestForm(FlaskForm):
            field = RadioField(
                "test",
                widget=MHCLGRadioInput(insert_divider_before_last_item=True),
                choices=[(x, str(x)) for x in range(10)],
            )

        form = TestForm()

        soup = BeautifulSoup(str(form.field), "html.parser")
        assert len(soup.select("input[type=radio]")) == 10
        assert len(soup.select(".govuk-radios__divider")) == 1


class TestMHCLGCheckboxesInput:
    def test_standard_checkboxes_are_not_divided(self):
        class TestForm(FlaskForm):
            field = SelectMultipleField(
                "test",
                widget=MHCLGCheckboxesInput(),
                choices=[(x, str(x)) for x in range(10)],
            )

        form = TestForm()

        soup = BeautifulSoup(str(form.field), "html.parser")
        assert len(soup.select("input[type=checkbox]")) == 10
        assert soup.select(".govuk-radios__divider") == []

    def test_divided_checkboxes(self):
        class TestForm(FlaskForm):
            field = SelectMultipleField(
                "test",
                widget=MHCLGCheckboxesInput(insert_divider_before_last_item=True),
                choices=[(x, str(x)) for x in range(10)],
                validators=[DataRequired()],
            )

        form = TestForm()

        soup = BeautifulSoup(str(form.field), "html.parser")
        assert len(soup.select("input[type=checkbox]")) == 10
        assert len(soup.select(".govuk-checkboxes__divider")) == 1

        last_checkbox = soup.select("input[type=checkbox]")[-1]
        assert last_checkbox["data-behaviour"] == "exclusive"
