from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovSubmitInput
from wtforms import SubmitField


class SignOffReportForm(FlaskForm):
    submit = SubmitField("Sign off and submit report", widget=GovSubmitInput())
