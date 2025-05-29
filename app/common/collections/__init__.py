# the goal of this file for now is to both hook some of the init behaviour into the app CLI
# and to start out the helper class that will be able to parse the schema and submission
import json
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, RootModel, TypeAdapter
from wtforms import Form as WTForm

from app.common.data import interfaces
from app.common.data.models import DataType, Form, Question, Submission


class UKAddress(BaseModel):
    street_address: str
    postal_code: str
    city: str
    county: str
    country: str
    latitude: int
    longitute: int

    def human_readable(self):
        return f"{self.street_address}, {self.postal_code}"


class SelectOneOption(BaseModel):
    selection_id: UUID
    selection_key: str
    selection_human_readable: str

    def human_readable(self):
        # or looks this up using the selection ID at context building time - it can always
        # fall back on this preserved version or show it in some contexts or others
        return self.selection_human_readable


# actually extend a class we define that extends root model - defines what you
# need to be able to turn it into i.e a human readable value for summary list, for CSV, for JSON
# (those may all be the same)
class SingleLineOfText(RootModel):
    root: str

    def human_readable(self):
        return self.root

    # write to question
    # already using the type according to the question type, which will line up with the
    # form and form data that was used

    # data = SingleLineOfText.from(question_form.data)
    # data.model_dump_json()

    # read from question stored
    # raw_answer() -> JSON:
    # answer() -> SingleLineOfText:
    # data = TypeAdapter(SingleLineOfText).validate_json(question.raw_answer)

    # this is for a single question so it should assume its just getting the values for that question
    # something before this has gone through and mapped the question answers to a dict?
    @staticmethod
    def from_form(data: dict[str, Any]):
        return SingleLineOfText(data["field"])

    # 1. a method that will build a dynamic form based on a question
    # if the question is a group of questions (and therefore multiple on a single page) it will go through all the questions
    # if will lookup the questions required fields and add them to the form
    # fields are added with the name question-id.type-specific-field-name
    # always has a submit button, add another throws a bit of a spanner in the works though
    # 2. a template which renders based on a question
    # if the question is a group of questions it will go through all the questions
    # for the question it will fish out the question-id.type-specific-field-name and know how to render that
    # (does it organise it into a fieldset, does it just call the form directly, it will know the type, it will use the right gizmo)
    # 3. a method that will extract data from a dynamic form data and turn it into a pydnatic representation
    # based on the type of the question, if its a question group with same page it will do it based on a lot of them
    # if its an add another something will be impacted here but I haven't thought through what
    # 4. the pydantic representation of that answer is then submitted to the submission, based on the question type
    # that's whats then deserialised whenever it is used

    # single line of text - one text field
    # multi line of text - one text field
    # date - one date field
    # uk address ? - multiple text fields

    # i think there is a question here about should you just build custom components for i.e an address field
    # _instead_ of allowing multiple fields to be defined by the dynamic form
    # that would mean that main purpose of the more elaborate dynamic form would be to have multiple questions
    # -- although you do want separate bits of data out of a uk address, you don't want one return value like with a date
    # (as an example look at the date component in gov uk wtf)


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

        self.submission = submission

        # calculate visible questions once - this is doubling as wrapping them in helpers for the time
        # being which wants to be split out later
        self._visible_questions = [
            SubmissionQuestion(self, question, submission) for question in self.form_schema.questions
        ]

        pass

    # TODO: this should be calculated once and stored in the constructor
    @property
    def visible_questions(self) -> list["SubmissionQuestion"]:
        # should run all of the questions through any condition based on the current self.submission
        # works through an ordered list getting the "next question"

        # is it a nice interface to have a "next question" interface on the questions returned from this themselves?
        # that next question method would use this information calculated once here

        # this visible questions should be calculated once so it can be used any number of times
        # done in the constructor

        # if you come across a question group, you step into it (unless its a same page, in which case they're all the next question)
        # return self.form_schema.questions
        return self._visible_questions

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

    @property
    def to_json(self):
        dict = {}
        # also needs to be able to route through and determine if questions or groups are visible
        for question in self.visible_questions:
            if question.answer:
                # maps to a single value for now
                # a model might want to be able to return nested JSON that could just be appended
                dict[question.name] = question.answer.human_readable()

        return json.dumps(dict)

    # @ property
    # def status(self) -> FormStatus:
    # status based on how many of the questions in the form have validated answers
    # alongside what submission events have happened to this form (i.e marked as complete)

    # presumably none only returned when you're finished and have no more valid questions
    def next_question(self, question: Optional["SubmissionQuestion"] = None) -> Optional["SubmissionQuestion"]:
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

    def previous_question(self, question: "SubmissionQuestion") -> Optional["SubmissionQuestion"]:
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


# probably each of these should just have a reference to the collection helper which references the submission
# for now its all passed down I guess
class SubmissionQuestion:
    def __init__(self, form: SubmissionForm, question_schema: Question, submission: Submission):
        self.form = form
        self.question_schema = question_schema
        self.submission = submission

    @property
    def name(self):
        return self.question_schema.name

    @property
    def text(self):
        return self.question_schema.text

    # this will interact with the interface to actually update the JSON on the form
    # I _think_ this will continue to work nicely for things like groups processing multiple
    # questions on the same page and add another but we'll have to see as I come to it

    # will this just reference the collections get answer thing or will we all just have the
    # sumission to look things up? - to be decided
    # the data that this will receive will very likely come from wtforms - the type signature
    # and other intrefaces and logic could probably reflect this

    # I think this should only accept the pydantic model that represents the validated question answer
    # it can then serialise that and store it reliably in the submission
    # this then shouldn't need to know the type
    # come back to this

    # the steps are
    # wtform data submission
    # -> validation based on question type and question validators
    # -> pydantic model based on question type
    # -> model dump to JSON, assuming it will be read back by the same model
    def submit(self, answer: RootModel):
        interfaces.collections._submit_data(self.submission, self.question_schema, answer.model_dump_json())
        # interface.collections.update_data(dict(self.question_schema.id=data.model_dump()))

        # alternatively this could be set in the constructor based on the question type
        # if it extends a standard root model then anything it needs to expose can be called here
        # match self.question_schema.data_type:
        # case DataType.SINGLE_LINE_OF_TEXT:
        # data = SingleLineOfText(value)
        # pass

    # I think this should be serialised according to the question type
    # this returns the pydantic model directly serialised from the submission entry
    # to get human readable should the calling code be pulling this and then calling it on the model
    # - will that human readable value ever use the context or anything else from the form?
    @property
    def answer(self):
        raw_answer = self.submission.data.get(str(self.question_schema.id))
        if not raw_answer:
            return None

        # in _theory_ you could build a dynamic pydantic model that
        # knows to parse optional vars of the key ids and knows what types it should be expecting
        # and it coudld parse it all in one go

        # this might get expensive to be done individually without a bit of optimisation - TBD
        match self.question_schema.data_type:
            case DataType.SINGLE_LINE_OF_TEXT:
                return TypeAdapter(SingleLineOfText).validate_strings(raw_answer)

    # def __repr__(self):
    # return f"Question('{self.question_schema.id}')"

    # @property
    # def human_readable()
