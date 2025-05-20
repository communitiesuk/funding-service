from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovSubmitInput, GovTextInput
from wtforms.fields.simple import StringField, SubmitField
from wtforms.validators import DataRequired


def strip_string_if_not_empty(value: str) -> str | None:
    return value.strip() if value else value


class GrantForm(FlaskForm):
    name = StringField(
        "Grant name",
        validators=[DataRequired("Enter a grant name")],
        filters=[strip_string_if_not_empty],
        widget=GovTextInput(),
    )
    submit = SubmitField(widget=GovSubmitInput())


class CollectionForm(FlaskForm):
    name = StringField(
        "What is the name of the collection?",
        validators=[DataRequired("Enter a collection name")],
        filters=[strip_string_if_not_empty],
        widget=GovTextInput(),
    )
    submit = SubmitField(widget=GovSubmitInput())


class SectionForm(FlaskForm):
    title = StringField(
        "What is the name of the section?",
        validators=[DataRequired("Enter a section title")],
        filters=[strip_string_if_not_empty],
        widget=GovTextInput(),
    )
    submit = SubmitField(widget=GovSubmitInput())


class FormForm(FlaskForm):
    title = StringField(
        "What is the name of the form?",
        validators=[DataRequired("Enter a form name")],
        filters=[strip_string_if_not_empty],
        widget=GovTextInput(),
    )
    submit = SubmitField(widget=GovSubmitInput())


class SectionForm(FlaskForm):
    title = StringField(
        "Section title",
        validators=[DataRequired("Enter a section title")],
        filters=[lambda x: x.strip() if x else x],
        widget=GovTextInput(),
    )
    collection_id = HiddenField()
    submit = SubmitField(widget=GovSubmitInput())


class FormForm(FlaskForm):
    title = StringField(
        "Form title",
        validators=[DataRequired("Enter a form title")],
        filters=[lambda x: x.strip() if x else x],
        widget=GovTextInput(),
    )
    section_id = HiddenField()
    submit = SubmitField(widget=GovSubmitInput())
