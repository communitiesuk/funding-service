import uuid
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


def _is_entry_envelope(entry: dict[str, Any]) -> bool:
    return "id" in entry and "answers" in entry


def _normalise_entries(entries: list[Any]) -> list[dict[str, Any]]:
    """Wrap legacy bare-answers-dict entries (`{question_id: value}`) in an envelope
    (`{"id": ..., "answers": {question_id: value}}`), minting a stable id for each. Entries already in
    envelope shape are left untouched. Submission events store historic snapshots of this data that
    predate the envelope shape, so this normalisation has to run whenever a blob is loaded, not just once
    in a database migration.
    """
    normalised: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            return entries
        normalised.append(entry if _is_entry_envelope(entry) else {"id": str(uuid.uuid4()), "answers": entry})
    return normalised


class SubmissionDataAddAnotherIndexInvalid(ValueError):
    def __init__(self, message: str):
        super().__init__(message)


class SubmissionDataManager:
    """A helper to handle creating/updating/deleting answers in the `data` blob of a submission.

    This makes a deep copy of the submission data so that any changes do not get persisted/synced with SQLAlchemy until
    they are persisted explicitly with a call to `update_submission_data`.

    This is *only* concerned with managing the structure of the `submission.data` blob, not any higher-level concerns
    such as 'how complete is this submission' or 'what is the current state of the submission'.

    An add-another entry is stored as an envelope, not a bare answers dict:

        "<group_id>": [ { "id": "<entry uuid>", "source_entry_id": "<source entry uuid>", "answers": {...} } ]

    `source_entry_id` is only present for entries belonging to a group that repeats over another. The entry
    id is a stable identity for the entry, independent of its position in the list; `add_another_index`
    remains the addressing scheme used in URLs and S3 keys.

    NOTE: If the data structure changes, we may also need to sync/update the following places:
    - Submission.name (for multi-submissions)
    """

    def __init__(self, data: dict[str, Any]) -> None:
        # Make a deep copy of the submission data so that any changes do not get persisted/synced with SQLAlchemy unless
        # done so explicitly.
        self.data = deepcopy(data)

        for key, value in self.data.items():
            if isinstance(value, list):
                self.data[key] = _normalise_entries(value)

    def get(self, question: Question, *, add_another_index: int | None = None) -> AllAnswerTypes | None:
        if question.add_another_container:
            entries = self.data.get(str(question.add_another_container.id), [])
            if add_another_index is None:
                raise SubmissionDataAddAnotherIndexInvalid(
                    "add_another_index must be provided for questions within an add another container"
                )

            if add_another_index < 0 or add_another_index > len(entries):
                raise SubmissionDataAddAnotherIndexInvalid("no add another entry exists at this index")

            if add_another_index == len(entries):
                # Always allow looking at the 'next' add another group - so that you can add more sets of answers.
                raw_answer = None
            else:
                raw_answer = entries[add_another_index]["answers"].get(str(question.id))

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
                entries.append({"id": str(uuid.uuid4()), "answers": {}})
            entries[add_another_index]["answers"][str(question.id)] = answer.get_value_for_submission()
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
                entries[add_another_index]["answers"].pop(str(question.id), None)
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

    def get_entries(self, group: Component) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = self.data.get(str(group.id), [])
        return entries

    def get_entry_id(self, group: Component, *, add_another_index: int) -> str:
        entry_id: str = self.get_entries(group)[add_another_index]["id"]
        return entry_id

    def index_for_source_entry_id(self, group: Component, source_entry_id: str) -> int | None:
        for index, entry in enumerate(self.get_entries(group)):
            if entry.get("source_entry_id") == source_entry_id:
                return index
        return None

    def append_entry(self, group: Component, *, source_entry_id: str | None = None) -> int:
        entries = self.data.setdefault(str(group.id), [])
        entry: dict[str, Any] = {"id": str(uuid.uuid4()), "answers": {}}
        if source_entry_id is not None:
            entry["source_entry_id"] = source_entry_id
        entries.append(entry)
        return len(entries) - 1

    def clear_entry_answers(self, group: Component, *, add_another_index: int) -> None:
        """Empty an entry's answers in place, keeping its id/source_entry_id and its position in the list."""
        entries = self.get_entries(group)
        if add_another_index < 0 or add_another_index >= len(entries):
            raise ValueError(
                f"Cannot clear answers at index {add_another_index} as there are only {len(entries)} existing answers"
            )
        entries[add_another_index]["answers"] = {}
