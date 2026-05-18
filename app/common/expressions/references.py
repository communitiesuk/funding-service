from collections import namedtuple
from functools import cached_property
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema
from sqlalchemy.exc import NoResultFound

from app.common.safe_ids import SafeDidMixin, SafeQidMixin

if TYPE_CHECKING:
    from app.common.data.models import DataSource, Question
    from app.common.data.types import (
        DataSourceSchemaColumn,
        QuestionDataOptions,
        QuestionDataType,
        QuestionPresentationOptions,
    )


def _try_unwrap(text: str) -> str | None:
    """If ``text`` is a single ``((reference))`` token, return the inner reference; else None."""
    from app.common.expressions import INTERPOLATE_REGEX

    match = INTERPOLATE_REGEX.fullmatch(text.strip())
    if not match:
        return None
    return match.group(1).strip()


DataSourceReference = namedtuple("DataSourceReference", ("data_source_id", "column_name"))


class ExpressionReference(str):
    """A reference to a datapoint available within an ExpressionContext.

    Stored form is unwrapped: e.g. ``q_<hex>`` for a question answer, or
    ``d_<hex>.<column_name>`` for a data source column value.

    This class owns the parsing/formatting logic for references so that the
    rest of the codebase can pass a typed value around instead of juggling
    bare strings. Instances inherit from ``str`` so they serialise naturally
    through Pydantic/JSON and compare equal to the underlying unwrapped
    reference string.
    """

    def __new__(cls, value: str) -> ExpressionReference:
        if (unwrapped := _try_unwrap(value)) is not None:
            # Allow passing already-wrapped references for backwards compatibility.
            value = unwrapped
        value = value.strip()
        return super().__new__(cls, value)

    @classmethod
    def from_wrapped(cls, text: str) -> ExpressionReference:
        unwrapped = _try_unwrap(text)
        if unwrapped is None:
            raise ValueError(f"Expected a wrapped reference like ((ref)); got {text!r}")
        # TODO: This should raise InvalidReferenceInExpression if an empty string?
        return cls(unwrapped)

    @classmethod
    def from_question(cls, question: Question) -> ExpressionReference:
        return cls(question.safe_qid)

    @classmethod
    def from_data_source_column(cls, data_source: DataSource, column_name: str) -> ExpressionReference:
        return cls(f"{data_source.safe_did}.{column_name}")

    @property
    def unwrapped(self) -> str:
        return str(self)

    @property
    def wrapped(self) -> str:
        return f"(({self.unwrapped}))"

    @property
    def question_id(self) -> UUID | None:
        """If this reference refers to a question, return the question's UUID; otherwise None.

        This does not check that the referenced question exists in any DB/context —
        it only inspects the shape of the reference string.
        """
        try:
            return SafeQidMixin.safe_qid_to_id(self.unwrapped)
        except ValueError:
            return None

    @property
    def data_source_reference(self) -> DataSourceReference | None:
        """If this reference refers to a data source column, return ``(data_source_id, column_name)``;
        otherwise None.

        As with `question_id`, this only inspects the shape of the reference string.
        """
        try:
            data_source_id, column_name = SafeDidMixin.safe_ds_ref_to_id_and_column_name(self.unwrapped)
        except ValueError:
            return None
        if data_source_id is None or column_name is None:
            return None
        return DataSourceReference(data_source_id, column_name)

    @cached_property
    def question(self) -> Question | None:
        from app.common.data.interfaces.collections import get_question_by_id

        question_id = self.question_id
        if not question_id:
            return None

        try:
            return get_question_by_id(question_id)
        except NoResultFound:
            return None

    @cached_property
    def data_source_column(self) -> DataSourceSchemaColumn | None:
        ds_ref = self.data_source_reference
        if not ds_ref:
            return None

        data_source = self.data_source
        if not data_source:
            return None

        schema = data_source.schema
        if not schema:
            return None

        return schema.root.get(ds_ref.column_name)

    @cached_property
    def data_source(self) -> DataSource | None:
        from app.common.data.interfaces.data_sets import get_data_source

        ds_ref = self.data_source_reference
        if not ds_ref:
            return None

        try:
            data_source = get_data_source(ds_ref.data_source_id) if ds_ref else None
        except NoResultFound:
            data_source = None

        if not data_source:
            return None

        return data_source

    @property
    def label(self) -> str:
        if question := self.question:
            return question.data_reference_label

        if (column := self.data_source_column) and (data_source := self.data_source):
            if label := data_source.column_reference_label(column):
                return label

        raise ValueError(f"Can't resolve ExpressionReference {self!r} to a specific label; unknown reference shape")

    @property
    def data_type(self) -> QuestionDataType:
        """Resolve this reference to the data type of the value it points at.

        Returns the referenced Question's data_type for question refs, or the data source
        column's data_type for column refs.

        Called by `build_managed_expression_form` to pick the set of managed expressions
        applicable to a subject without caring whether that subject is a question or a
        data source column.
        """
        if question := self.question:
            return question.data_type

        if column := self.data_source_column:
            return column.data_type

        raise ValueError(f"Can't resolve ExpressionReference {self!r} to a specific data type; unknown reference shape")

    @property
    def presentation_options(self) -> QuestionPresentationOptions:
        if question := self.question:
            return question.presentation_options

        if column := self.data_source_column:
            return column.presentation_options

        raise ValueError(
            f"Can't resolve ExpressionReference {self!r} to a specific presentation options; unknown reference shape"
        )

    @property
    def data_options(self) -> QuestionDataOptions:
        if question := self.question:
            return question.data_options

        if column := self.data_source_column:
            return column.data_options

        raise ValueError(
            f"Can't resolve ExpressionReference {self!r} to a specific data options; unknown reference shape"
        )

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> CoreSchema:
        def _from_str(value: str) -> ExpressionReference:
            if isinstance(value, cls):
                return value
            # Be lenient about wrapped input from the Pydantic deserialisation path —
            # existing stored JSONB contains wrapped references like "((q_xxx))" and
            # form submissions also arrive wrapped. Canonicalise to unwrapped here.
            return cls(value)

        return core_schema.no_info_after_validator_function(
            _from_str,
            core_schema.str_schema(),
            serialization=core_schema.plain_serializer_function_ser_schema(str),
        )
