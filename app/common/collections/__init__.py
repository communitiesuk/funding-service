# the goal of this file for now is to both hook some of the init behaviour into the app CLI
# and to start out the helper class that will be able to parse the schema and submission
from typing import Any, Optional
from uuid import UUID

from pydantic import RootModel
from wtforms import Form as WTForm

from app.common.data.models import DataType, Form, Question, Submission

# thinking through some of the writing
# a group with the same page property should still be recorded as separate data with each of the question IDs
# a single question with add another should be stored as list against that questions ID
# a group with add another should be stored as a list against that groups ID
# - the question ID of each question should be stored

# a pydantic model should be used to read and write the answer JSON
# a question page can know how to use each of the consituent parts of that model for existing values
# each pydantic model should have properties that turn it into a single text value for summary pages, csv export, json export


# rename all of this - represents the current state of a form schema given submission data
class SubmissionForm:
    # this should probably bring in a question context down from the top
    # should the data passed in here be from the submission or just accept the whole submission
    def __init__(self, form_schema: Form, submission: Submission):
        self.form_schema = form_schema
        pass

    # TODO: this should be calculated once and stored in the constructor
    @property
    def visible_questions(self) -> list[Question]:
        # should run all of the questions through any condition based on the current self.submission
        # works through an ordered list getting the "next question"

        # is it a nice interface to have a "next question" interface on the questions returned from this themselves?
        # that next question method would use this information calculated once here

        # this visible questions should be calculated once so it can be used any number of times
        # done in the constructor

        # if you come across a question group, you step into it (unless its a same page, in which case they're all the next question)
        return self.form_schema.questions

    @property
    def id(self) -> UUID:
        return self.form_schema.id

    @property
    def title(self) -> str:
        return self.form_schema.title

    # I think exposing the schema should be consistent - some guaranteed properties could be included for
    # convenience but I think a lot of code will want to access this directly
    @property
    def schema(self) -> Form:
        return self.form_schema

    # @ property
    # def status(self) -> FormStatus:
    # status based on how many of the questions in the form have validated answers
    # alongside what submission events have happened to this form (i.e marked as complete)

    # presumably none only returned when you're finished and have no more valid questions
    def next_question(self, question: Optional[Question] = None) -> Question | None:
        # if there's a question we'll be stepping through or picking it out of this form
        # otherwise we'll return the first
        # I'll probably want to wrap questions in a helper here - I think each wrapper
        # should have the model exposed through a `schema` property
        if not question:
            return self.visible_questions[0]

        # check for things like out of bounds
        # this will need to check if we're in a group context (i.e we have parent)
        # - if so we'll first route according to our parents questions, otherwise we'll return next question _for_ the
        #   parent group itself
        #   otherwise we're routing according to the forms visible questions (top level)
        return self.visible_questions[self.visible_questions.index(question) + 1]

    def previous_question(self, question: Question) -> Question | None:
        return self.visible_questions[self.visible_questions.index(question) - 1]


class Collection:
    def __init__(self, submission: Submission):
        self.submission = submission
        self.schema = submission.collection

        # TODO: use list comprehension - not sure how to flat map from sections -> forms but
        # .     won't be needed after the db change
        # self.forms = [ SubmissionForm(x) for x in self.schema.sections[0].forms ]
        self.forms: list[SubmissionForm] = []
        for section in self.schema.sections:
            # TODO: make sure these are ordered as they come out of the ORM
            for form in section.forms:
                submission_form = SubmissionForm(form, self.submission)
                self.forms.append(submission_form)

    # ordered, visible forms based on this schema and importantly the submission events
    # the submission events should tell you if a form has been marked as complete, checking
    # the submission data and visible questions should tell you if there is sufficient data
    # if for some reason there isn't sufficient data and its for some reason been marked as complete
    # the former should be prioritised over the latter
    @property
    def visible_forms(self):
        return self.forms

    # once you've got one of these forms you should be able to act on it directly
    def form(self, id: UUID) -> SubmissionForm:
        return next(form for form in self.forms if form.id == id)


# from flask_wtf import FlaskForm
# from govuk_frontend_wtf.wtforms_widgets import GovSubmitInput, GovTextInput
# from wtforms.fields.simple import HiddenField, StringField, SubmitField
# from wtforms.validators import DataRequired

# class SingleLineOfTextForm(FlaskForm):
# question = StringField()
# submit = SubmitField(widget=GovSubmitInput())


# actually extend a class we define that extends root model - defines what you
# need to be able to turn it into i.e a human readable value for summary list, for CSV, for JSON
# (those may all be the same)
class SingleLineOfText(RootModel):
    root: str

    def human_readable(self):
        return self.value

    # write to question
    # already using the type according to the question type, which will line up with the
    # form and form data that was used

    # data = SingleLineOfText.from(question_form.data)
    # data.model_dump_json()

    # read from question stored
    # raw_answer() -> JSON:
    # answer() -> SingleLineOfText:
    # data = TypeAdapter(SingleLineOfText).validate_json(question.raw_answer)

    # def from_form(self, data)


class SubmissionQuestion:
    def __init__(self, form: SubmissionForm, question_schema: Question):
        self.form = form
        self.question_schema = question_schema

    # this will interact with the interface to actually update the JSON on the form
    # I _think_ this will continue to work nicely for things like groups processing multiple
    # questions on the same page and add another but we'll have to see as I come to it

    # will this just reference the collections get answer thing or will we all just have the
    # sumission to look things up? - to be decided
    # the data that this will receive will very likely come from wtforms - the type signature
    # and other intrefaces and logic could probably reflect this
    def submit_answer(self, value: Any):
        # alternatively this could be set in the constructor based on the question type
        # if it extends a standard root model then anything it needs to expose can be called here
        match self.question_schema.data_type:
            case DataType.SINGLE_LINE_OF_TEXT:
                # data = SingleLineOfText(value)
                # interface.collections.update_data(dict(self.question_schema.id=data.model_dump()))
                pass

    # I think this should be serialised according to the question type
    # this returns the pydantic model directly serialised from the submission entry
    # to get human readable should the calling code be pulling this and then calling it on the model
    # - will that human readable value ever use the context or anything else from the form?
    @property
    def answer():
        pass

    # @property
    # def human_readable()
