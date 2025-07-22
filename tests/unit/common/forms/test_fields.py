from bs4 import BeautifulSoup
from flask_wtf import FlaskForm
from wtforms import RadioField

from app.common.forms.fields import MHCLGRadioInput


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
