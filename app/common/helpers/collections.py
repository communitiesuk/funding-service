import csv
import uuid
from datetime import datetime
from io import StringIO
from itertools import chain
from typing import TYPE_CHECKING, Any, List, Optional
from uuid import UUID

from immutabledict import immutabledict
from pydantic import BaseModel as PydanticBaseModel
from pydantic import TypeAdapter

from app.common.collections.forms import DynamicQuestionForm
from app.common.collections.types import (
    NOT_ANSWERED,
    NOT_ASKED,
    AllAnswerTypes,
    EmailAnswer,
    IntegerAnswer,
    SingleChoiceFromListAnswer,
    TextMultiLineAnswer,
    TextSingleLineAnswer,
    UrlAnswer,
    YesNoAnswer,
)
from app.common.data import interfaces
from app.common.data.interfaces.collections import (
    get_all_submissions_with_mode_for_collection_with_full_schema,
    get_submission,
)
from app.common.data.models_user import User
from app.common.data.types import (
    QuestionDataType,
    SubmissionEventKey,
    SubmissionModeEnum,
    SubmissionStatusEnum,
    TasklistTaskStatusEnum,
)
from app.common.expressions import (
    ExpressionContext,
    UndefinedVariableInExpression,
    evaluate,
)

if TYPE_CHECKING:
    from app.common.data.models import Collection, Form, Grant, Question, Section, Submission


class SubmissionHelper:
    """
    This offensively-named class is a helper for the `app.common.data.models.Submission` and associated sub-models.

    It wraps a Submission instance from the DB and encapsulates the business logic that will make it easy to deal with
    conditionals, routing, storing+retrieving data, etc in one place, consistently.
    """

    def __init__(self, submission: "Submission"):
        """
        Initialise the SubmissionHelper; the `submission` instance passed in should have been retrieved from the DB
        with the collection and related tables (eg section, form, question) eagerly loaded to prevent this helper from
        making any further DB queries. Use `get_submission` with the `with_full_schema=True` option.
        :param submission:
        """
        self.submission = submission
        self.collection = self.submission.collection

    @classmethod
    def load(cls, submission_id: uuid.UUID) -> "SubmissionHelper":
        return cls(get_submission(submission_id, with_full_schema=True))

    @property
    def grant(self) -> "Grant":
        return self.collection.grant

    @property
    def sections(self) -> list["Section"]:
        return self.collection.sections

    @property
    def name(self) -> str:
        return self.collection.name

    @property
    def reference(self) -> str:
        return self.submission.reference

    @property
    def form_data(self) -> dict[str, Any]:
        def get_all_questions(ql: list["Question"]) -> list["Question"]:
                questions = []
                for question in ql:
                    if question.is_group:

                        # fixme: get question includes groups for now, this should all be managed consistently from helpers
                        questions.extend([question, *get_all_questions(question.questions)])
                    else:
                        questions.append(question)
                return questions
        form_data = {
            question.safe_qid: answer.get_value_for_form()
            for section in self.submission.collection.sections
            for form in section.forms
            for question in get_all_questions(form.questions)
            if (answer := self.get_answer_for_question(question.id)) is not None
        }
        return form_data

    @property
    def expression_context(self) -> ExpressionContext:
        # fixme: when calculating the answers to populate the expression context we should check if its a group or not
        #        and treat it appropriately
        def get_all_questions(ql: list["Question"]) -> list["Question"]:
                questions = []
                for question in ql:
                    if question.is_group:

                        # fixme: get question includes groups for now, this should all be managed consistently from helpers
                        questions.extend([question, *get_all_questions(question.questions)])
                    else:
                        questions.append(question)
                return questions
        
        submission_data = {
            question.safe_qid: answer.get_value_for_expression()
            for section in self.submission.collection.sections
            for form in section.forms
            for question in get_all_questions(form.questions)
            if (answer := self.get_answer_for_question(question.id)) is not None
        }
        return ExpressionContext(from_submission=immutabledict(submission_data))

    @property
    def all_visible_questions(self) -> dict[UUID, "Question"]:
        return {
            question.id: question
            for section in self.get_ordered_visible_sections()
            for form in self.get_ordered_visible_forms_for_section(section)
            for question in self.get_ordered_visible_questions_for_form(form)
        }

    @property
    def status(self) -> str:
        submitted = SubmissionEventKey.SUBMISSION_SUBMITTED in [x.key for x in self.submission.events]

        form_statuses = set(
            [
                self.get_status_for_form(form)
                for form in chain.from_iterable(section.forms for section in self.collection.sections)
            ]
        )
        if {SubmissionStatusEnum.COMPLETED} == form_statuses and submitted:
            return SubmissionStatusEnum.COMPLETED
        elif {SubmissionStatusEnum.NOT_STARTED} == form_statuses:
            return SubmissionStatusEnum.NOT_STARTED
        else:
            return SubmissionStatusEnum.IN_PROGRESS

    @property
    def is_completed(self) -> bool:
        return self.status == SubmissionStatusEnum.COMPLETED

    @property
    def is_test(self) -> bool:
        return self.submission.mode == SubmissionModeEnum.TEST

    @property
    def is_live(self) -> bool:
        return self.submission.mode == SubmissionModeEnum.LIVE

    @property
    def created_by_email(self) -> str:
        return self.submission.created_by.email

    @property
    def created_at_utc(self) -> datetime:
        return self.submission.created_at_utc

    @property
    def id(self) -> UUID:
        return self.submission.id

    @property
    def collection_id(self) -> UUID:
        return self.collection.id

    def get_section(self, section_id: uuid.UUID) -> "Section":
        try:
            return next(filter(lambda s: s.id == section_id, self.collection.sections))
        except StopIteration as e:
            raise ValueError(f"Could not find a section with id={section_id} in collection={self.collection.id}") from e

    def get_form(self, form_id: uuid.UUID) -> "Form":
        try:
            return next(
                filter(
                    lambda f: f.id == form_id,
                    chain.from_iterable(section.forms for section in self.collection.sections),
                )
            )
        except StopIteration as e:
            raise ValueError(f"Could not find a form with id={form_id} in collection={self.collection.id}") from e

    # todo: this should calculate an index once on initialisation and then reference that
    def get_question(self, question_id: uuid.UUID) -> "Question":
        try:
            # todo: obvious duplication with above
            def get_all_questions(ql: list["Question"]) -> list["Question"]:
                questions = []
                for question in ql:
                    if question.is_group:

                        # fixme: get question includes groups for now, this should all be managed consistently from helpers
                        questions.extend([question, *get_all_questions(question.questions)])
                    else:
                        questions.append(question)
                return questions

            return next(
                filter(
                    lambda q: q.id == question_id,
                    chain.from_iterable(
                        get_all_questions(form.questions) for section in self.collection.sections for form in section.forms
                    ),
                )
            )

            # all_questions = []
            # for section in self.collection.sections:
            #     for form in section.forms:
            #         form_questions = get_all_questions(form.questions)
            #         all_questions.extend(form_questions)
            #         for question in form_questions:
            #             if question.id == question_id:
            #                 return question
            
            # raise ValueError(
            #     f"Could not find a question with id={question_id} in collection={self.collection.id}"
            # )
        except StopIteration as e:
            raise ValueError(
                f"Could not find a question with id={question_id} in collection={self.collection.id}"
            ) from e

    def get_ordered_visible_sections(self) -> list["Section"]:
        """Returns the visible, ordered sections based upon the current state of this submission."""
        return sorted(self.sections, key=lambda s: s.order)

    def get_all_questions_are_answered_for_form(self, form: "Form") -> tuple[bool, list[AllAnswerTypes]]:
        visible_questions = self.get_ordered_visible_questions_for_form(form)
        answers = [answer for q in visible_questions if (answer := self.get_answer_for_question(q.id)) is not None]
        return len(visible_questions) == len(answers), answers

    @property
    def all_forms_are_completed(self) -> bool:
        form_statuses = set(
            [
                self.get_status_for_form(form)
                for form in chain.from_iterable(section.forms for section in self.collection.sections)
            ]
        )
        return {SubmissionStatusEnum.COMPLETED} == form_statuses

    def get_tasklist_status_for_form(self, form: "Form") -> TasklistTaskStatusEnum:
        if len(form.questions) == 0:
            return TasklistTaskStatusEnum.NO_QUESTIONS

        return TasklistTaskStatusEnum(self.get_status_for_form(form))

    def get_status_for_form(self, form: "Form") -> str:
        all_questions_answered, answers = self.get_all_questions_are_answered_for_form(form)
        marked_as_complete = SubmissionEventKey.FORM_RUNNER_FORM_COMPLETED in [
            x.key for x in self.submission.events if x.form and x.form.id == form.id
        ]
        if form.questions and all_questions_answered and marked_as_complete:
            return SubmissionStatusEnum.COMPLETED
        elif answers:
            return SubmissionStatusEnum.IN_PROGRESS
        else:
            return SubmissionStatusEnum.NOT_STARTED

    def get_ordered_visible_forms_for_section(self, section: "Section") -> list["Form"]:
        """Returns the visible, ordered forms for a given section based upon the current state of this collection."""
        return sorted(section.forms, key=lambda f: f.order)

    def is_question_visible(self, question: "Question", context: "ExpressionContext") -> bool:
        try:
            return all(evaluate(condition, context) for condition in question.conditions)
        except UndefinedVariableInExpression:
            # todo: fail open for now - this method should accept an optional bool that allows this condition to fail
            #       or not- checking visibility on the question page itself should never fail - the summary page could
            # todo: check dependency chain for conditions when undefined variables are encountered to avoid
            #       always suppressing errors and not surfacing issues on misconfigured forms
            return False
        
    def get_ordered_visible_questions(self, questions: list["Question"]) -> list["Question"]:
        ordered_questions = sorted(questions, key=lambda q: q.order)
        questions = []
        for question in ordered_questions:
            if self.is_question_visible(question, self.expression_context):
                if question.is_group:
                    # checking if the group should be visible at all should probably be more robust than this but I think
                    # this should do for now
                    # todo: _probably_ the question visibility check in itself should check up its groups chain, as well as only
                    #       checking the questions in the group in the first place here

                    # thinking through showing the questions for a group on the same page
                    # - the group will need to be included in the visible questions so the ask a question page can decide what to do with it
                    # - the ask a question page will also need to check if the question is in a group when routed to and see if it should
                    # - show the whole group or just the question
                    questions.extend(self.get_ordered_visible_questions(question.questions))
                else:
                    # if self.is_question_visible(question, self.expression_context):
                    questions.append(question)
        return questions
        # return [question for question in ordered_questions if self.is_question_visible(question, self.expression_context)] 

    def get_ordered_visible_questions_for_form(self, form: "Form") -> list["Question"]:
        """Returns the visible, ordered questions for a given form based upon the current state of this collection."""
        # ordered_questions = sorted(form.questions, key=lambda q: q.order)

        # todo: not yet factoring in questions that should show on the same page
        # todo: revise moving away from list comprehension syntax
        # return [
        #     question for question in ordered_questions if self.is_question_visible(question, self.expression_context)
        # ]
        return self.get_ordered_visible_questions(form.questions)

    def get_first_question_for_form(self, form: "Form") -> Optional["Question"]:
        questions = self.get_ordered_visible_questions_for_form(form)
        if questions:
            return questions[0]
        return None

    def get_last_question_for_form(self, form: "Form") -> Optional["Question"]:
        questions = self.get_ordered_visible_questions_for_form(form)
        if questions:
            return questions[-1]
        return None

    def get_form_for_question(self, question_id: UUID) -> "Form":
        # todo: copied from somewhere else
        def get_all_questions(ql: list["Question"]) -> list["Question"]:
            questions = []
            for question in ql:
                if question.is_group:

                    # fixme: get question includes groups for now, this should all be managed consistently from helpers
                    questions.extend([question, *get_all_questions(question.questions)])
                else:
                    questions.append(question)
            return questions

        for section in self.collection.sections:
            for form in section.forms:
                if any(q.id == question_id for q in get_all_questions(form.questions)):
                    return form

        raise ValueError(f"Could not find form for question_id={question_id} in collection={self.collection.id}")

    # todo: factor in if we're on a question that shouldn't be answered (i.e group or page)
    def get_answer_for_question(self, question_id: UUID) -> AllAnswerTypes | None:
        question = self.get_question(question_id)
        serialised_data = self.submission.data.get(str(question_id))
        return _deserialise_question_type(question, serialised_data) if serialised_data is not None else None

    def submit_answer_for_question(self, question_id: UUID, form: DynamicQuestionForm) -> None:
        if self.is_completed:
            raise ValueError(
                f"Could not submit answer for question_id={question_id} "
                f"because submission id={self.id} is already submitted."
            )
                
        question = self.get_question(question_id)
        data = _form_data_to_question_type(question, form)
        interfaces.collections.update_submission_data(self.submission, question, data)

    def submit(self, user: "User") -> None:
        if self.is_completed:
            return

        if self.all_forms_are_completed:
            interfaces.collections.add_submission_event(self.submission, SubmissionEventKey.SUBMISSION_SUBMITTED, user)
        else:
            raise ValueError(f"Could not submit submission id={self.id} because not all forms are complete.")

    def toggle_form_completed(self, form: "Form", user: "User", is_complete: bool) -> None:
        form_complete = self.get_status_for_form(form) == SubmissionStatusEnum.COMPLETED
        if is_complete == form_complete:
            return

        if is_complete:
            all_questions_answered, _ = self.get_all_questions_are_answered_for_form(form)
            if not all_questions_answered:
                raise ValueError(
                    f"Could not mark form id={form.id} as complete because not all questions have been answered."
                )

            interfaces.collections.add_submission_event(
                self.submission, SubmissionEventKey.FORM_RUNNER_FORM_COMPLETED, user, form
            )
        else:
            interfaces.collections.clear_submission_events(
                self.submission, SubmissionEventKey.FORM_RUNNER_FORM_COMPLETED, form
            )

    def get_next_question(self, current_question_id: UUID) -> Optional["Question"]:
        """
        Retrieve the next question that should be shown to the user, or None if this was the last relevant question.
        """
        form = self.get_form_for_question(current_question_id)
        questions = self.get_ordered_visible_questions_for_form(form)

        question_iterator = iter(questions)
        for question in question_iterator:
            if question.id == current_question_id:
                return next(question_iterator, None)

        raise ValueError(f"Could not find a question with id={current_question_id} in collection={self.collection}")

    def get_previous_question(self, current_question_id: UUID) -> Optional["Question"]:
        """
        Retrieve the question that was asked before this one, or None if this was the first relevant question.
        """
        form = self.get_form_for_question(current_question_id)
        questions = self.get_ordered_visible_questions_for_form(form)

        # Reverse the list of questions so that we're working from the end to the start.
        question_iterator = iter(reversed(questions))
        for question in question_iterator:
            if question.id == current_question_id:
                return next(question_iterator, None)

        raise ValueError(f"Could not find a question with id={current_question_id} in collection={self.collection}")


class CollectionHelper:
    collection: "Collection"
    submission_mode: SubmissionModeEnum
    submissions: List["Submission"]
    submission_helpers: dict[UUID, SubmissionHelper]

    def __init__(self, collection: "Collection", submission_mode: SubmissionModeEnum):
        self.collection = collection
        self.submission_mode = submission_mode
        self.submissions = [
            s for s in (get_all_submissions_with_mode_for_collection_with_full_schema(collection.id, submission_mode))
        ]
        self.submission_helpers = {s.id: SubmissionHelper(s) for s in self.submissions}

    def get_submission_helper_by_id(self, submission_id: UUID) -> SubmissionHelper | None:
        return self.submission_helpers.get(submission_id, None)

    def get_submission_helper_by_reference(self, submission_reference: str) -> SubmissionHelper | None:
        for _, submission in self.submission_helpers.items():
            if submission.reference == submission_reference:
                return submission

        return None

    def get_all_possible_questions_for_collection(self) -> list["Question"]:
        """
        Returns a list of all questions that are part of the collection, across all sections and forms.
        """
        return [
            question
            for section in sorted(self.collection.sections, key=lambda s: s.order)
            for form in sorted(section.forms, key=lambda f: f.order)
            for question in sorted(form.questions, key=lambda q: q.order)
        ]

    def generate_csv_content_for_all_submissions(self) -> str:
        metadata_headers = ["Submission reference", "Created by", "Created time UTC"]
        question_headers = {
            question.id: f"[{question.form.title}] {question.name}"
            for question in self.get_all_possible_questions_for_collection()
        }
        all_headers = metadata_headers + [header_string for _, header_string in question_headers.items()]

        csv_output = StringIO()
        csv_writer = csv.DictWriter(csv_output, fieldnames=all_headers)
        csv_writer.writeheader()
        for submission in [value for key, value in self.submission_helpers.items()]:
            submission_csv_data = {
                "Submission reference": submission.reference,
                "Created by": submission.created_by_email,
                "Created time UTC": submission.created_at_utc.isoformat(),
            }
            visible_questions = submission.all_visible_questions
            for question_id, header_string in question_headers.items():
                if question_id not in visible_questions.keys():
                    submission_csv_data[header_string] = NOT_ASKED
                else:
                    answer = submission.get_answer_for_question(question_id)
                    submission_csv_data[header_string] = answer.get_value_for_text_export() if answer else NOT_ANSWERED

            csv_writer.writerow(submission_csv_data)

        return csv_output.getvalue()


def _form_data_to_question_type(question: "Question", form: DynamicQuestionForm) -> AllAnswerTypes:
    _QuestionModel: type[PydanticBaseModel]

    answer = form.get_answer_to_question(question)

    match question.data_type:
        case QuestionDataType.TEXT_SINGLE_LINE | QuestionDataType.EMAIL | QuestionDataType.URL:
            return TextSingleLineAnswer(answer)  # ty: ignore[missing-argument]
        case QuestionDataType.TEXT_MULTI_LINE:
            return TextMultiLineAnswer(answer)  # ty: ignore[missing-argument]
        case QuestionDataType.INTEGER:
            return IntegerAnswer(answer)  # ty: ignore[missing-argument]
        case QuestionDataType.YES_NO:
            return YesNoAnswer(answer)  # ty: ignore[missing-argument]
        case QuestionDataType.RADIOS:
            label = next(item.label for item in question.data_source.items if item.key == answer)
            return SingleChoiceFromListAnswer(key=answer, label=label)

    raise ValueError(f"Could not parse data for question type={question.data_type}")


def _deserialise_question_type(question: "Question", serialised_data: str | int | float | bool) -> AllAnswerTypes:
    match question.data_type:
        case QuestionDataType.TEXT_SINGLE_LINE:
            return TypeAdapter(TextSingleLineAnswer).validate_python(serialised_data)
        case QuestionDataType.URL:
            return TypeAdapter(UrlAnswer).validate_python(serialised_data)
        case QuestionDataType.EMAIL:
            return TypeAdapter(EmailAnswer).validate_python(serialised_data)
        case QuestionDataType.TEXT_MULTI_LINE:
            return TypeAdapter(TextMultiLineAnswer).validate_python(serialised_data)
        case QuestionDataType.INTEGER:
            return TypeAdapter(IntegerAnswer).validate_python(serialised_data)
        case QuestionDataType.YES_NO:
            return TypeAdapter(YesNoAnswer).validate_python(serialised_data)
        case QuestionDataType.RADIOS:
            return TypeAdapter(SingleChoiceFromListAnswer).validate_python(serialised_data)

    raise ValueError(f"Could not deserialise data for question type={question.data_type}")
