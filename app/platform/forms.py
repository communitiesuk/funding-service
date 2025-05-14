from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovRadioInput, GovSubmitInput, GovTextArea, GovTextInput
from wtforms.fields.choices import RadioField
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


class QuestionTypeForm(FlaskForm):
    data_type = RadioField(
        "Question type",
        choices=[
            ("text", "Text"),
            # ("number", "Number"),
            # ("person-contact-details", "A person's contact details"),
            # TODO put these back in when we have an enum for these types in the data model
        ],
        validators=[DataRequired("Select a question type")],
        widget=GovRadioInput(),
    )
    submit = SubmitField(widget=GovSubmitInput())


class QuestionForm(FlaskForm):
    text = StringField(
        "What is the question?",
        validators=[DataRequired("Enter the question text")],
        filters=[lambda x: x.strip() if x else x],
        widget=GovTextInput(),
    )
    hint = StringField(
        "Question hint",
        filters=[lambda x: x.strip() if x else x],
        widget=GovTextArea(),
        description="The question hint will be shown to users when they are answering the question.",
    )
    name = StringField(
        "Question name",
        validators=[DataRequired("Enter the question name")],
        description="The question name will be shown when exporting submissions from your users.",
        filters=[lambda x: x.strip() if x else x],
        widget=GovTextInput(),
    )
    data_type = HiddenField()
    form_id = HiddenField()
    submit = SubmitField(widget=GovSubmitInput())
