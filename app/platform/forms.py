from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovSubmitInput, GovTextInput
from wtforms.fields.simple import HiddenField, StringField, SubmitField
from wtforms.validators import DataRequired


class GrantForm(FlaskForm):
    name = StringField(
        "Grant name",
        validators=[DataRequired("Enter a grant name")],
        filters=[lambda x: x.strip() if x else x],
        widget=GovTextInput(),
    )
    submit = SubmitField(widget=GovSubmitInput())


class CollectionForm(FlaskForm):
    name = StringField(
        "Collection name",
        validators=[DataRequired("Enter a collection name")],
        filters=[lambda x: x.strip() if x else x],
        widget=GovTextInput(),
    )
    grant_id = HiddenField()
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
