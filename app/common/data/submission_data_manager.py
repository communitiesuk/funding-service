from copy import deepcopy
from typing import TYPE_CHECKING, Any

from pydantic import TypeAdapter

from app.common.collections.types import (
    AllAnswerTypes,
    DateAnswer,
    DecimalAnswer,
    EmailAnswer,
    FileUploadAnswer,
    IntegerAnswer,
    MultipleChoiceFromListAnswer,
    SingleChoiceFromListAnswer,
    TextMultiLineAnswer,
    TextSingleLineAnswer,
    UrlAnswer,
    YesNoAnswer,
)
from app.common.data.types import NumberTypeEnum, QuestionDataType

if TYPE_CHECKING:
    from app.common.data.models import Component, Question


def _deserialise_question_type(question: Question, serialised_data: str | int | float | bool) -> AllAnswerTypes:
    match question.data_type:
        case QuestionDataType.TEXT_SINGLE_LINE:
            return TypeAdapter(TextSingleLineAnswer).validate_python(serialised_data)
        case QuestionDataType.URL:
            return TypeAdapter(UrlAnswer).validate_python(serialised_data)
        case QuestionDataType.EMAIL:
            return TypeAdapter(EmailAnswer).validate_python(serialised_data)
        case QuestionDataType.TEXT_MULTI_LINE:
            return TypeAdapter(TextMultiLineAnswer).validate_python(serialised_data)
        case QuestionDataType.NUMBER:
            if question.data_options.number_type == NumberTypeEnum.DECIMAL:
                return TypeAdapter(DecimalAnswer).validate_python(serialised_data)
            return TypeAdapter(IntegerAnswer).validate_python(serialised_data)
        case QuestionDataType.YES_NO:
            return TypeAdapter(YesNoAnswer).validate_python(serialised_data)
        case QuestionDataType.RADIOS:
            return TypeAdapter(SingleChoiceFromListAnswer).validate_python(serialised_data)
        case QuestionDataType.CHECKBOXES:
            return TypeAdapter(MultipleChoiceFromListAnswer).validate_python(serialised_data)
        case QuestionDataType.DATE:
            return TypeAdapter(DateAnswer).validate_python(serialised_data)
        case QuestionDataType.FILE_UPLOAD:
            return TypeAdapter(FileUploadAnswer).validate_python(serialised_data)

    raise ValueError(f"Could not deserialise data for question type={question.data_type}")


class SubmissionDataManager:
    """A helper to handle creating/updating/deleting answers in the `data` blob of a submission.

    This makes a deep copy of the submission data so that any changes do not get persisted/synced with SQLAlchemy until
    they are persisted explicitly with a call to `update_submission_data`.

    Q for review - is this good or bad?
    """

    def __init__(self, data: dict[str, Any]) -> None:
        # Make a deep copy of the submission data so that any changes do not get persisted/synced with SQLAlchemy unless
        # done so explicitly.
        self.data = deepcopy(data)

    def get(self, question: Question, *, add_another_index: int | None = None) -> AllAnswerTypes | None:
        if question.add_another_container:
            entries = self.data.get(str(question.add_another_container.id), [])
            if add_another_index is None or add_another_index < 0 or add_another_index >= len(entries):
                return None

            raw_answer = entries[add_another_index].get(str(question.id))

        else:
            raw_answer = self.data.get(str(question.id))

        if raw_answer is None:
            return None

        return _deserialise_question_type(question, raw_answer)

    def set(self, question: Question, answer: AllAnswerTypes, *, add_another_index: int | None = None) -> None:
        # TODO: Make sure type of answer matches the question

        if question.add_another_container:
            if add_another_index is None:
                raise ValueError("add_another_index must be provided for questions within an add another container")

            num_existing_entries = self.get_count_for_add_another(question.add_another_container)
            if add_another_index > num_existing_entries or add_another_index < 0:
                raise ValueError(
                    f"Cannot update answers at index {add_another_index} as there are "
                    f"only {num_existing_entries} existing answers"
                )

            container_key = str(question.add_another_container.id)
            entries = self.data.get(container_key, [])
            if add_another_index is not None and add_another_index == len(entries):
                entries.append({})
            entries[add_another_index][str(question.id)] = answer.get_value_for_submission()
            self.data[container_key] = entries
        else:
            if add_another_index is not None:
                raise ValueError(
                    "add_another_index cannot be provided for questions not within an add another container"
                )

            self.data[str(question.id)] = answer.get_value_for_submission()

    def remove(self, question: Question, *, add_another_index: int | None = None) -> None:
        if question.data_type not in [QuestionDataType.FILE_UPLOAD]:
            raise ValueError(
                "Removing answers is currently only supported for questions where an explicit remove is required"
            )

        if question.add_another_container:
            if add_another_index is None:
                raise ValueError("add_another_index must be provided for questions within an add another container")

            num_existing_entries = self.get_count_for_add_another(question.add_another_container)
            if add_another_index < 0 or num_existing_entries == 0 or add_another_index >= num_existing_entries:
                raise ValueError(
                    f"Cannot clear answers at index {add_another_index} as there are "
                    f"only {num_existing_entries} existing answers"
                )

            entries = self.data.get(str(question.add_another_container.id), [])
            if add_another_index is not None and 0 <= add_another_index < len(entries):
                entries[add_another_index].pop(str(question.id), None)
        else:
            self.data.pop(str(question.id), None)

    def get_count_for_add_another(self, group: Component) -> int:
        entries = self.data.get(str(group.id))
        return len(entries) if entries else 0

    def remove_add_another_entry(self, group: Component, *, add_another_index: int) -> None:
        num_existing_entries = self.get_count_for_add_another(group)
        if add_another_index < 0 or num_existing_entries == 0 or add_another_index >= num_existing_entries:
            raise ValueError(
                f"Cannot remove answers at index {add_another_index} "
                f"as there are only {num_existing_entries} existing answers"
            )

        self.data[str(group.id)].pop(add_another_index)
