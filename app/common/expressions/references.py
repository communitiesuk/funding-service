import ast
import re
from collections import namedtuple
from functools import cached_property
from typing import TYPE_CHECKING, Any, Callable, Protocol, Self
from uuid import UUID

from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema
from sqlalchemy import String, TypeDecorator
from sqlalchemy.dialects.postgresql import CITEXT
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


class PExpressionReferences(Protocol):
    @property
    def _all_references(self) -> list[ExpressionReference]: ...

    @property
    def references(self) -> list[ExpressionReference]: ...

    def count_references(self, reference: ExpressionReference) -> int: ...


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
    def from_question_id(cls, question_id: UUID) -> ExpressionReference:
        return cls(SafeQidMixin.safe_qid_from_id(question_id))

    @classmethod
    def from_data_source_column(cls, data_source: DataSource, column_name: str) -> ExpressionReference:
        return cls(f"{data_source.safe_did}.{column_name}")

    @classmethod
    def from_data_source_column_id(cls, data_source_id: UUID, column_name: str) -> ExpressionReference:
        return cls(f"{SafeDidMixin.safe_did_from_id(data_source_id)}.{column_name}")

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

    @property
    def references(self) -> list[ExpressionReference]:
        return [self]


class _ReferenceExtractor(ast.NodeVisitor):
    """
    'Expressions' are a strictly limited subset of the Python language used to interpolate messages and evaluate
    statements when running forms to collect information from users.

    An interpolation message is a mixture of plain text and embedded evaluation statements wrapped by double
    parens `(( ... ))`.

    We use the `simpleeval` library to evaluate expression statements. This parses the statement using Python's `ast`
    stdlib. In order to identify all of the references (effectively: names and attributes) present in the expression
    we will similarly parse the statement and keep a record of anything referenced in the statement.

    This is a cleaner and more reliable way to extract any required data that the expression needs than doing string/
    regex matching, which is error-prone and difficult to maintain.

    This class is only responsible for walking the AST and recording which references are made; it does not validate
    that those references are actually resolveable within a given expression context.
    """

    def __init__(self) -> None:
        self._seen: set[str] = set()
        self.references: list[ExpressionReference] = []

    def _record(self, name: str) -> None:
        self._seen.add(name)
        self.references.append(ExpressionReference(name))

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Record visits to attributes of a node

        This tracks nested attribute access such as where we're reaching into a dictionary's values.
        """
        parts: list[str] = [node.attr]
        current = node.value

        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value

        if isinstance(current, ast.Name):
            parts.append(current.id)
            self._record(".".join(reversed(parts)))
            return

        # Chain isn't rooted in a plain Name (eg ``foo()[0].bar``); fall back to
        # visiting children so any nested Names still get picked up.
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        """Record visits to bare names (eg ``foo``)"""
        self._record(node.id)

    def visit_Call(self, node: ast.Call) -> None:
        """Deliberately skip ``node.func`` — function calls are not tracked as "references"

        These could be recorded as `required_functions` to later make sure that an expression has access to the
        functions it needs in order to evaluate correctly. This is left for a future extension.
        """
        for arg in node.args:
            self.visit(arg)
        for keyword in node.keywords:
            self.visit(keyword.value)


class ExpressionStatement(PExpressionReferences, str):
    @property
    def _all_references(self) -> list[ExpressionReference]:
        raise NotImplementedError()

    @property
    def references(self) -> list[ExpressionReference]:
        return list(dict.fromkeys(self._all_references))

    def count_references(self, reference: ExpressionReference) -> int:
        """Returns the number of times the given reference appears in the statement."""
        return sum(1 for ref in self._all_references if ref == reference)

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> CoreSchema:
        def _from_str(value: str) -> ExpressionStatement:
            if isinstance(value, cls):
                return value
            return cls(value)

        return core_schema.no_info_after_validator_function(
            _from_str,
            core_schema.str_schema(),
            serialization=core_schema.plain_serializer_function_ser_schema(str),
        )

    def rewrite_reference(self, old: ExpressionReference, new: ExpressionReference) -> Self:
        """Replace all occurrences of ``old`` with ``new`` in the statement."""
        new_statement = str(self).replace(old.unwrapped, new.unwrapped)

        return type(self)(new_statement)


class EvaluationStatement(ExpressionStatement):
    """A Python-like expression to evaluate, with unwrapped references (e.g. ``q_abc > 100``).

    References are discovered by AST-walking the statement using the above _ReferenceExtractor. Python treats ``((x))``
    identically to ``x``, so legacy wrapped references inside custom expressions are picked up by the same walk
    without a separate regex pass.
    """

    def validate_syntax(self):
        try:
            ast.parse(str(self).strip(), mode="eval")
        except SyntaxError as e:
            from app.common.expressions import DisallowedExpression

            raise DisallowedExpression(message=f"Expression {self=} could not be parsed due to a syntax error.") from e

    @property
    def _all_references(self) -> list[ExpressionReference]:
        """Returns a list of all references found in the statement, including duplicates, in the order they appear."""
        try:
            tree = ast.parse(str(self).strip(), mode="eval")
        except SyntaxError:
            return []

        extractor = _ReferenceExtractor()
        extractor.visit(tree)
        return extractor.references


class InterpolationStatement(ExpressionStatement):
    """Free text with ``((ref))`` references embedded (e.g. ``"Your answer was ((q_abc))"``).

    In theory, each ``((...))`` block *should* be able to be treated as an ``EvaluationStatement`` that could contain
    multiple references or calculations. However, flagging invalid references in this case is more difficult. The
    product currently only allows you to insert single references here, so we specifically limit the code here as well.

    If we ever need to be able to interpolate calculations into message, we'll need to revisit this.
    """

    @property
    def _all_references(self) -> list[ExpressionReference]:
        """Returns a list of all references found in the statement, including duplicates, in the order they appear."""
        from app.common.expressions import INTERPOLATE_REGEX

        out: list[ExpressionReference] = []
        for match in INTERPOLATE_REGEX.finditer(self):
            inner = match.group(1)

            # NOTE: Ideally we would allow multiple references within embedded statements in an interpolation
            #       message, but that complicates accurate detection significantly. For now the product only lets users
            #       enter a single reference to interpolate within message, so we will skip any attempts at parsing
            #       embedded references as EvaluationStatements.

            ref = ExpressionReference(inner)
            out.append(ref)

        return out

    def interpolate(self, interpolation_function: Callable[[re.Match[Any]], str]) -> str:
        from app.common.expressions import INTERPOLATE_REGEX

        return INTERPOLATE_REGEX.sub(
            interpolation_function,
            self,
        )


class InterpolationStatementType(TypeDecorator):
    """SQLAlchemy column type backing an ``InterpolationStatement`` field as ``VARCHAR``."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        return None if value is None else str(value)

    def process_result_value(self, value: Any, dialect: Any) -> InterpolationStatement | None:
        return None if value is None else InterpolationStatement(value)


class CIInterpolationStatementType(InterpolationStatementType):
    """``InterpolationStatement`` backed by Postgres ``CITEXT`` for case-insensitive columns."""

    impl = CITEXT
    cache_ok = True


class EvaluationStatementType(TypeDecorator):
    """SQLAlchemy column type backing an ``EvaluationStatement`` field as ``VARCHAR``."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        return None if value is None else str(value)

    def process_result_value(self, value: Any, dialect: Any) -> EvaluationStatement | None:
        return None if value is None else EvaluationStatement(value)
