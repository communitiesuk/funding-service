from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovSubmitInput
from wtforms import StringField
from wtforms.fields.simple import SubmitField
from wtforms.validators import InputRequired

import app.common.forms.validators as validators

__all__ = ["validators"]


class GenericSubmitForm(FlaskForm):
    submit = SubmitField(widget=GovSubmitInput())


class GenericConfirmDeletionForm(FlaskForm):
    confirm_deletion = SubmitField(widget=GovSubmitInput(), validators=[InputRequired()])


class MarkdownToHtmlForm(FlaskForm):
    markdown = StringField()
