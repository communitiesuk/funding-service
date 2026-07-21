import abc
import ast
import enum
import re
from collections import ChainMap
from collections.abc import MutableMapping
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Callable, ClassVar, Literal, cast, overload

import simpleeval
from markupsafe import Markup, escape
from pydantic import BaseModel

from app.common.data.submission_data_manager import SubmissionDataManager
from app.common.data.types import ExpressionType, ManagedExpressionsEnum, QuestionDataType
from app.common.exceptions import WTFormRenderableException
from app.common.expressions.references import (
    EvaluationStatement,
    ExpressionReference,
    ExpressionStatement,
    InterpolationStatement,
)
from app.types import NOT_PROVIDED

if TYPE_CHECKING:
    from app.common.data.models import Collection, Component, Expression, Group, Question
    from app.common.helpers.collections import SubmissionHelper
    from app.deliver_grant_funding.session_models import AddContextToExpressionsModel

# This is tested by `test_find_references_in_expression_shared_fixtures` - look there for test cases
INTERPOLATE_REGEX = re.compile(r"\(\((?!\()((?:[^()]|\([^()]*\))*)\)\)")

# If any interpolation references contain characters other than alphanumeric, full stops or underscores,
# then we'll hard stop that for now. As of this implementation, only single variable references are allowed.
# We expect to want complex expressions in the future, but are hard limiting that for now as a specific
# product/tech edge case restriction.
# This is stricter than we allow for INTERPOLATE_REGEX, which allows anything that the frontend JS regex allows
#    (which works for highlighting human-readable labels which may contain other characters like arrows or parens).
#    Once those are accepted and normalised to ExpressionContext references, everything should only be dot-notated
#    python-variable-like names.
ALLOWED_INTERPOLATION_REGEX = re.compile(r"[^A-Za-z0-9_.]")


class ManagedExpressionError(Exception):
    pass


class UndefinedVariableInExpression(
    WTFormRenderableException,
    ManagedExpressionError,
):
    def __init__(
        self,
        message: str,
        variable_name: str,
    ):
        self.variable_name = variable_name
        super().__init__(message, f"You cannot use {self.variable_name} because it does not exist")


class UndefinedFunctionInExpression(
    WTFormRenderableException,
    ManagedExpressionError,
):
    def __init__(
        self,
        message: str,
        function_name: str,
    ):
        self.function_name = function_name
        super().__init__(message, f"You cannot use {self.function_name} in calculations")


class UndefinedOperatorInExpression(
    WTFormRenderableException,
    ManagedExpressionError,
):
    def __init__(
        self,
        message: str,
        operator: str,
    ):
        self.operator = operator
        super().__init__(
            message,
            "The calculation does not make sense. Check it is a complete calculation that only uses accepted symbols",
        )


class DisallowedExpression(
    WTFormRenderableException,
    ManagedExpressionError,
):
    def __init__(
        self,
        message: str,
        form_error_message: str | None = None,
    ):
        super().__init__(
            message,
            (
                form_error_message
                or "The calculation does not make sense. Check it is a complete calculation that only uses accepted "
                "symbols"
            ),
        )


class InvalidEvaluationResult(
    WTFormRenderableException,
    ManagedExpressionError,
):
    def __init__(
        self,
        statement: str,
        result: str,
        expected_type: type[bool] | type[int],
    ):
        super().__init__(
            f"Result of evaluating {statement} was {result}; expected {expected_type}.",
            f"The expression must evaluate to {'true or false' if expected_type is bool else 'a number'}",
        )


class EvaluatableExpression(BaseModel):
    # Defining this as a ClassVar allows direct access from the class and excludes it from pydantic instance
    name: ClassVar[ManagedExpressionsEnum | Literal["CUSTOM"]]
    subject_reference: ExpressionReference | None = None

    _key: ManagedExpressionsEnum | None

    @property
    @abc.abstractmethod
    def statement(self) -> EvaluationStatement:
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def description(self) -> str: ...

    @property
    @abc.abstractmethod
    def message(self) -> InterpolationStatement | None: ...

    @property
    def reference_aware_fields(self) -> set[str]:
        """
        Returns a set of field names in the expression that can contain reference data.
        """
        # TODO: we could dynamically detect this for all `ExpressionReference` fields instead of hand-coding the
        #       fields now?
        return set()

    @classmethod
    def prepare_form_data(cls, add_context_data: "AddContextToExpressionsModel") -> dict[str, Any]:
        data = {
            k: v
            for k, v in add_context_data.expression_form_data.items()
            if k != "add_context" and k != "remove_context"
        }

        return data


class ExpressionContext(ChainMap[str, Any]):
    """
    This handles all of the data that we want to be able to pass into an Expression when evaluating it. As of writing,
    this is two things:

    1. the answers provided so far for a submission
    2. the expression's arbitrary `context` field

    When thinking about the answers for a submission in the context of an HTTP request, there are two sources for this:

    1. The current state of the submission from the database.
    2. Any form data in a POST request trying to update the submission.

    When evaluating expressions, we care about the latest view of the world, so form data POST'd in the current request
    should override any data from the database. We do this by starting with a dictionary of answers from the existing
    submission in the DB, and then (assuming the data passes some basic validation checks), we mutate the dictionary
    with answers from the current form submission (DynamicQuestionForm).
    """

    class ContextSources(enum.StrEnum):
        # We actually expose all questions in the collection, but for now we're limited contextual references to
        # just questions in the same section.
        SECTION = "A previous question in this section"
        PREVIOUS_SECTION = "A question in a previous section"
        PREVIOUS_COLLECTION = "A question in a previous collection"
        DATASET = "An uploaded data set"

    def __init__(
        self,
        submission_data: dict[str, Any] | None = None,
        expression_context: dict[str, Any] | None = None,
        add_another_context: dict[str, Any] | None = None,
        data_source_context: dict[str, Any] | None = None,
        question_form_context: dict[str, Any] | None = None,
        default_context: dict[str, Any] | None = None,
    ):
        self._submission_data = submission_data or {}
        self._expression_context = expression_context or {}
        self._add_another_context = add_another_context or {}
        self._data_source_context = data_source_context or {}
        self._question_form_context = question_form_context or {}
        self._default_context = default_context or {}

        super().__init__(*self._ordered_contexts)

    def with_add_another_context(
        self,
        component: Component,
        data_manager: SubmissionDataManager,
        *,
        add_another_index: int,
        mode: Literal["evaluation", "interpolation"] = "evaluation",
    ) -> ExpressionContext:
        """
        Creates a new `ExpressionContext` with `add_another_context` set to the provided `add_another_context`, and the
        other contexts set to the same values as this context
        """
        if not component.add_another_container:
            raise ValueError("add_another_context can only be set for add another components")

        # we're evaluating for a specific entry in a list so we'll set the context for the
        # questions in our container - assume submission context is already set
        questions = (
            cast("Group", component.add_another_container).cached_questions
            if component.add_another_container.is_group
            else [cast("Question", component.add_another_container)]
        )

        add_another_context: dict[str, Any] = {}
        for question in questions:
            answer = data_manager.get(question, add_another_index=add_another_index)
            if answer is not None:
                add_another_context[question.safe_qid] = (
                    answer.get_value_for_evaluation() if mode == "evaluation" else answer.get_value_for_interpolation()
                )

        if self._add_another_context:
            if self._add_another_context != add_another_context:
                raise ValueError(
                    "overriding with different add_another_context where it is already set on this ExpressionContext"
                )

        return ExpressionContext(
            submission_data=self._submission_data,
            add_another_context=add_another_context,
            expression_context=self._expression_context,
            question_form_context=self._question_form_context,
            data_source_context=self._data_source_context,
            default_context=self._default_context,
        )

    @property
    def _ordered_contexts(self) -> list[MutableMapping[str, Any]]:
        return list(
            filter(
                None,
                [
                    self._question_form_context,
                    self._default_context,
                    self._add_another_context,
                    self._submission_data,
                    self._data_source_context,
                    self._expression_context,
                ],
            )
        )

    @property
    def expression_context(self) -> dict[str, Any]:
        return self._expression_context

    @expression_context.setter
    def expression_context(self, expression_context: dict[str, Any]) -> None:
        self._expression_context = expression_context
        self.maps = self._ordered_contexts

    def with_question_form_context(self, submission_answers_from_form: dict[str, Any]) -> ExpressionContext:
        """The default submission data we use for expression context is all of the data from the Submission DB record.
        However, if we're processing things on a POST request when a user is submitting data for a question, then we
        need to override any existing answer in the DB with the latest answer from the current POST request. This
        happens during the question form validation, after we know that the answer the user has submitted is broadly
        valid (ie of the correct data type). This can't happen during the initial instantiation of the
        ExpressionContext, because of the way we use WTForms and the way it validates data.
        """
        return ExpressionContext(
            submission_data=self._submission_data,
            expression_context=self._expression_context,
            add_another_context=self._add_another_context,
            data_source_context=self._data_source_context,
            question_form_context=submission_answers_from_form,
            default_context=self._default_context,
        )

    def with_default_context(self, submission_helper: SubmissionHelper | None) -> ExpressionContext:
        """To accommodate custom expressions that might reference questions that are
        conditionally not required given the current answer state, we set default empty values
        for any question that is not currently visible.

        We won't default answers that should be visible, as anything unhandled here should
        surface logical errors and defaults could lead to unpredictable failures.

        This method is intentionally separated from building the initial expression context
        so that any initial visibility checks and interpolation don't worry about default edge cases,
        this should only be used when evaluating custom validations.

        The scope of this could be expanded to other data sources and other data types
        as required.
        """
        if not submission_helper:
            return self

        default_context: dict[str, Any] = {}

        for form in submission_helper.collection.forms:
            visible_questions = submission_helper.cached_get_ordered_visible_questions(form)
            for question in form.cached_questions:
                if question not in visible_questions:
                    if question.data_type == QuestionDataType.NUMBER:
                        default_context[question.safe_qid] = 0

        return ExpressionContext(
            submission_data=self._submission_data,
            expression_context=self._expression_context,
            add_another_context=self._add_another_context,
            data_source_context=self._data_source_context,
            question_form_context=self._question_form_context,
            default_context=default_context,
        )

    @staticmethod
    def build_expression_context(
        collection: Collection,
        mode: Literal["evaluation", "interpolation"],
        expression_context_end_point: Component | None = None,
        submission_helper: SubmissionHelper | None = None,  # TODO: replace with submission data source manager
        data_manager: SubmissionDataManager | None = None,
        include_children_of_context_end_point: bool | None = None,
    ) -> ExpressionContext:
        """Pulls together all of the context that we want to be able to expose to an expression when evaluating it.

        `include_children_of_context_end_point` should be set only when passing `expression_context_end_point`, which is
        not used when the expression context is built for form running - only for form design/build in deliver. Set
        `include_children_of_context_end_point` to True when creating validations; it should be False everywhere else.
        """

        assert len(ExpressionContext.ContextSources) == 4, (
            "When defining a new source of context for expressions, "
            "update this method and the ContextSourceChoices enum"
        )

        if (include_children_of_context_end_point is not None and expression_context_end_point is None) or (
            include_children_of_context_end_point is None and expression_context_end_point is not None
        ):
            raise ValueError(
                "include_children_of_context_end_point must be set only when expression_context_end_point is set"
            )

        # TODO: Namespace this set of data, eg under a `this_submission` prefix/key
        submission_data = ExpressionContext._build_submission_data(
            mode=mode,
            expression_context_end_point=expression_context_end_point,
            collection=collection,
            data_manager=data_manager,
        )

        data_source_context = ExpressionContext._build_data_source_context(
            mode=mode, submission_helper=submission_helper
        )

        # TODO: FSPT-1142 centralise this iteration/filtering logic; duplicated below
        if mode == "interpolation":
            for form in collection.forms:
                for question in form.cached_questions:
                    # TODO: the component order checks here are broadly duplicative of
                    #  `is_component_dependency_order_valid`; can we refactor that function and reuse it here to have
                    #  logic in one place?
                    if expression_context_end_point and (
                        form.order > expression_context_end_point.form.order
                        or (
                            expression_context_end_point.form == form
                            and form.global_component_index(question)
                            > form.global_component_index(expression_context_end_point)
                        )
                    ):
                        if not include_children_of_context_end_point:
                            continue

                        if not (
                            question == expression_context_end_point
                            or question.is_descendant_of(expression_context_end_point)
                        ):
                            continue

                    # TODO: FSPT-1142: do we show this always or only when different to current context?
                    submission_data.setdefault(question.safe_qid, f"(({question.data_reference_label}))")

            # collection.data_sources is used here (rather than submission_helper.data_sources) as a fallback
            # so that placeholder labels are always available in interpolation mode, eg when:
            # 1. No submission_helper (grant admin editing a question in Deliver — no submission/GR exists)
            # 2. Preview — submission_helper exists but data_sources is empty (no GR on a preview submission)
            # 3. A data source was skipped in _build_data_source_context (no matching org item, no schema)
            for data_source in collection.data_sources:
                if data_source.schema and data_source.schema.root:
                    data_source_context.setdefault(
                        data_source.safe_did,
                        {},
                    )
                    for column_name, column_schema in data_source.schema.ordered_items():
                        data_source_context[data_source.safe_did].setdefault(
                            column_name, f"(({data_source.column_reference_label(column_schema)}))"
                        )

        return ExpressionContext(submission_data=submission_data, data_source_context=data_source_context)

    @staticmethod
    def _build_submission_data(
        mode: Literal["evaluation", "interpolation"],
        expression_context_end_point: Component | None = None,
        collection: Collection | None = None,
        data_manager: SubmissionDataManager | None = None,
    ) -> dict[str, Any]:
        submission_data: dict[str, Any] = {}
        if collection and data_manager:
            for form in collection.forms:
                for question in form.cached_questions:
                    # TODO: FSPT-1142 centralise this iteration/filtering logic; duplicated above
                    if expression_context_end_point and (
                        form.order > expression_context_end_point.form.order
                        or (
                            expression_context_end_point.form == form
                            and form.global_component_index(question)
                            > form.global_component_index(expression_context_end_point)
                        )
                    ):
                        continue

                    # until we do support aggregate methods in expressions we only support add another
                    # question answers through an explicit `with_add_another_context` which sets the context
                    if not question.add_another_container:
                        answer = data_manager.get(question)
                        if answer is not None:
                            submission_data[question.safe_qid] = (
                                answer.get_value_for_evaluation()
                                if mode == "evaluation"
                                else answer.get_value_for_interpolation()
                            )
        return submission_data

    @staticmethod
    def _build_data_source_context(
        mode: Literal["evaluation", "interpolation"],
        submission_helper: SubmissionHelper | None = None,
    ) -> dict[str, Any]:
        # TODO: FSPT-1181: Fix when fixing Preview submissions with data source references
        if not submission_helper or not submission_helper.data_sources:
            return {}

        data_source_context: dict[str, Any] = {}

        for data_source in submission_helper.data_sources:
            # In reality this shouldn't happen, it's more a type guard as data_source.schema is nullable ie. when CUSTOM
            if not data_source.schema:
                continue

            if not data_source.schema.root:
                raise ValueError(f"Data source {data_source.name} {data_source.id} has no schema or schema items")

            org_item = data_source.get_filtered_organisation_item(
                submission_helper.submission.grant_recipient.organisation.external_id
            )

            # TODO: Do we want to set this to None or do we want to raise here when a data source exists for this
            # collection but this GR has no data row
            if org_item is None:
                data_source_context[data_source.safe_did] = {
                    col_name: (
                        None if mode == "evaluation" else f"(({data_source.column_reference_label(col_schema)}))"
                    )
                    for col_name, col_schema in data_source.schema.ordered_items()
                }
                continue

            typed_data = org_item.data

            # Type guard against non-GR level data sources - GR-level org items are always single-row data, if this ever
            # isn't a dict something has gone wrong with the sources we're pulling in or it's a Project-level org item
            if not isinstance(typed_data, dict):
                continue

            data_source_context[data_source.safe_did] = {
                col_name: (
                    value.get_value_for_evaluation() if mode == "evaluation" else value.get_value_for_interpolation()
                )
                for col_name, value in typed_data.items()
                if value is not None
            }

        return data_source_context

    @staticmethod
    def get_context_keys_and_labels(
        collection: Collection,
        expression_context_end_point: Component | None = None,
        expression_type: ExpressionType = ExpressionType.CONDITION,
    ) -> dict[str, str]:
        """A dict mapping the reference variables (eg question safe_qids) to human-readable labels

        TODO: When we have more than just questions here, we'll need to do more complicated mapping, and possibly
        find a way to include labels for eg DB model columns, such as the grant name
        """
        ec = ExpressionContext.build_expression_context(
            collection=collection,
            mode="interpolation",
            expression_context_end_point=expression_context_end_point,
            include_children_of_context_end_point=(
                expression_type == ExpressionType.VALIDATION if expression_context_end_point else None
            ),
        )

        # Now we've got a data_source_context which is not a flat dictionary we need to flatten this out so
        # that this function continue to work and the references can still be interpolated correctly
        def flatten(d, prefix=""):
            result = {}
            for key, value in d.items():
                full_key = f"{prefix}.{key}" if prefix else key
                if isinstance(value, dict):
                    result.update(flatten(value, full_key))
                else:
                    result[full_key] = value
            return result

        return flatten(ec)

    def is_valid_reference(self, reference: str) -> bool:
        """For a given ExpressionContext, work out if this reference resolves to a real value or not.

        Examples of valid references might be:
        - A question's safe_qid (points to a specific question in a collection)

        And, as of writing, in the future:
        - `grant.name` -> A string containing the name of the grant
        - `recipient.funding_allocation` -> The amount of money the grant recipient has been allocated
        """
        layers = reference.split(".")

        context = self
        for layer in layers:
            value = context.get(layer, NOT_PROVIDED)
            if value is NOT_PROVIDED:
                return False
            context = value

        return True

    def __hash__(self) -> int:
        # separate immutable instances are used when a context is extended so the instance id
        # should be sufficient for the lru_cache
        return hash(id(self))


def get_restricted_evaluator(
    names: Any, required_functions: dict[str, Callable[[Any], Any] | type[Any]]
) -> simpleeval.SimpleEval:
    evaluator = simpleeval.EvalWithCompoundTypes(
        names=names,
        functions=required_functions,
    )

    # restrict to a subset of binary operators so eg. & (bitwise and) is not allowed
    allowed_operators = {}
    for op in [ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Eq, ast.GtE, ast.Gt, ast.LtE, ast.Lt, ast.USub, ast.Is, ast.In]:
        allowed_operators[op] = evaluator.operators[op]
    evaluator.operators = allowed_operators
    # Remove all nodes except those we explicitly allowlist
    evaluator.nodes = {
        ast_expr: ast_fn
        for ast_expr, ast_fn in evaluator.nodes.items()  # ty:ignore[unresolved-attribute]
        if ast_expr
        in {
            ast.UnaryOp,
            ast.Expr,
            ast.Name,
            ast.BinOp,
            ast.Compare,
            ast.Subscript,
            ast.Attribute,
            ast.Slice,
            ast.Constant,
            ast.Call,
            ast.Set,
        }
    }

    # We override the handler for inline floats, eg. 1.1 * ((value)), because we store 'value' as a decimal.Decimal
    # and we get an unsupported operand type error if we try and use decimals and floats together
    _original_constant_handler = evaluator.nodes[ast.Constant]

    def _decimal_constant_handler(node: ast.Constant) -> Any:
        value = _original_constant_handler(node)
        if isinstance(value, float):
            return Decimal(str(value))
        return value

    evaluator.nodes[ast.Constant] = _decimal_constant_handler

    return evaluator


def run_evaluation(evaluator: simpleeval.SimpleEval, statement: str) -> Any:
    try:
        return evaluator.eval(statement)

    except simpleeval.NameNotDefined as e:
        raise UndefinedVariableInExpression(e.message, e.name) from e
    except simpleeval.FunctionNotDefined as e:
        raise UndefinedFunctionInExpression(e.message, e.func_name) from e  # ty:ignore[unresolved-attribute]
    except (SyntaxError, simpleeval.FeatureNotAvailable, KeyError) as e:
        raise DisallowedExpression("Expression is using unsafe/unsupported features") from e
    except simpleeval.OperatorNotDefined as e:
        raise UndefinedOperatorInExpression(e.message, e.attr) from e


def _evaluate_expression_with_context(
    statement: ExpressionStatement,
    context: ExpressionContext | None = None,
    required_functions: dict[str, Callable] | None = None,
) -> Any:
    """
    The base evaluator to use for handling all expressions.

    This parses arbitrary Python-language text into an Abstract Syntax Tree (AST) and then evaluates the result of
    that expression. Parsing arbitrary Python is extremely dangerous so we heavily restrict the AST nodes that we
    are willing to handle, to (hopefully) close off the attack surface to any malicious behaviour.

    The addition of any new AST nodes should be well-tested and intentional consideration should be given to any
    ways of exploit or misuse.
    """
    evaluator = get_restricted_evaluator(names=context, required_functions=required_functions or {})

    result = run_evaluation(evaluator, statement)

    return result


@overload
def interpolate(
    text: InterpolationStatement | str | None,
    context: ExpressionContext | None,
    *,
    with_interpolation_highlighting: Literal[False] = False,
) -> str: ...


@overload
def interpolate(
    text: InterpolationStatement | str | None,
    context: ExpressionContext | None,
    *,
    with_interpolation_highlighting: Literal[True],
) -> Markup: ...


def interpolate(
    text: InterpolationStatement | str | None,
    context: ExpressionContext | None,
    *,
    with_interpolation_highlighting: bool = False,
) -> str | Markup:
    if text is None:
        return "" if not with_interpolation_highlighting else Markup("")

    # We allow `interpolate` to take raw strings here as we'll otherwise be fighting a lot of Jinja2 template behaviour;
    # concating anything in a Jinja template returns `str` and loses our InterpolationStatement subclass. It also means
    # anywhere that interpolates something that's been round-tripped (eg a flash message into the session) would need
    # to be woven back into an InterpolationStatement; this overhead is unnecessary when we can just deal with plain
    # strings here.
    if isinstance(text, str):
        text = InterpolationStatement(text)

    def _interpolate(matchobj: re.Match[Any]) -> str:
        try:
            value = _evaluate_expression_with_context(matchobj.group(0), context)
            if with_interpolation_highlighting:
                return f'<span class="app-context-aware-editor--valid-reference">{escape(value)}</span>'
        except (
            UndefinedVariableInExpression,
            DisallowedExpression,
            UndefinedFunctionInExpression,
            UndefinedOperatorInExpression,
        ):
            value = matchobj.group(0)

        return str(value)

    result = text.interpolate(_interpolate)

    if with_interpolation_highlighting:
        return Markup(result)
    return result


def evaluate(expression: Expression, context: ExpressionContext | None = None) -> bool:
    result = _evaluate_expression_with_context(expression.statement, context, expression.required_functions)

    # do we want these to evalaute to non-bool types like int/str ever?
    if not isinstance(result, bool):
        raise InvalidEvaluationResult(expression.statement, result, bool)

    return result
