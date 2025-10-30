import ast
import enum
import re
from collections import ChainMap
from typing import TYPE_CHECKING, Any, Literal, MutableMapping, Optional, cast, overload

import simpleeval
from markupsafe import Markup, escape

from app.types import NOT_PROVIDED

if TYPE_CHECKING:
    from app.common.data.models import Collection, Component, Expression, Group, Question
    from app.common.helpers.collections import SubmissionHelper

INTERPOLATE_REGEX = re.compile(r"\(\(([^\(]+?)\)\)")
# If any interpolation references contain characters other than alphanumeric, full stops or underscores,
# then we'll hard stop that for now. As of this implementation, only single variable references are allowed.
# We expect to want complex expressions in the future, but are hard limiting that for now as a specific
# product/tech edge case restriction.
ALLOWED_INTERPOLATION_REGEX = re.compile(r"[^A-Za-z0-9_.]")


class ManagedExpressionError(Exception):
    pass


class UndefinedVariableInExpression(ManagedExpressionError):
    pass


class DisallowedExpression(ManagedExpressionError):
    pass


class InvalidEvaluationResult(ManagedExpressionError):
    pass


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
        # just questions in the same task.
        TASK = "A previous question in this task"

    def __init__(
        self,
        submission_data: dict[str, Any] | None = None,
        expression_context: dict[str, Any] | None = None,
        add_another_context: dict[str, Any] | None = None,
    ):
        self._submission_data = submission_data or {}
        self._expression_context = expression_context or {}
        self._add_another_context = add_another_context or {}

        super().__init__(*self._ordered_contexts)

    def with_add_another_context(
        self,
        component: "Component",
        submission_helper: "SubmissionHelper",
        *,
        add_another_index: int,
        allow_new_index: bool = False,
        mode: Literal["evaluation", "interpolation"] = "evaluation",
    ) -> "ExpressionContext":
        """
        Creates a new `ExpressionContext` with `add_another_context` set to the provided `add_another_context`, and the
        other contexts set to the same values as this context
        """
        if self._add_another_context:
            raise ValueError("add_another_context is already set on this ExpressionContext")

        if not component.add_another_container:
            raise ValueError("add_another_context can only be set for add another components")

        if allow_new_index:
            count = submission_helper.get_count_for_add_another(component.add_another_container)
            if add_another_index == count:
                return self

        # we're evaluating for a specific entry in a list so we'll set the context for the
        # questions in our container - assume submission context is already set
        questions = (
            cast("Group", component.add_another_container).cached_questions
            if component.add_another_container.is_group
            else [cast("Question", component.add_another_container)]
        )

        add_another_context: dict[str, Any] = {}
        for question in questions:
            answer = submission_helper.cached_get_answer_for_question(question.id, add_another_index=add_another_index)
            if answer is not None:
                add_another_context[question.safe_qid] = (
                    answer.get_value_for_evaluation() if mode == "evaluation" else answer.get_value_for_interpolation()
                )

        return ExpressionContext(
            submission_data=self._submission_data,
            add_another_context=add_another_context,
            expression_context=self._expression_context,
        )

    @property
    def _ordered_contexts(self) -> list[MutableMapping[str, Any]]:
        return list(
            filter(
                None,
                [
                    self._add_another_context,
                    self._submission_data,
                    self.expression_context,
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

    def update_submission_answers(self, submission_answers_from_form: dict[str, Any]) -> None:
        """The default submission data we use for expression context is all of the data from the Submission DB record.
        However, if we're processing things on a POST request when a user is submitting data for a question, then we
        need to override any existing answer in the DB with the latest answer from the current POST request. This
        happens during the question form validation, after we know that the answer the user has submitted is broadly
        valid (ie of the correct data type). This can't happen during the initial instantiation of the
        ExpressionContext, because of the way we use WTForms and the way it validates data. So this is the (currently)
        one place where you just have to be aware that state can be mutated mid-request and in a slightly hard-to-trace
        way.
        """
        self._submission_data.update(**submission_answers_from_form)

        # the add another context includes answers from its add another container which
        # could include previously persisted values for answers questions, also override those
        # for this form evaluation context
        if self._add_another_context:
            self._add_another_context.update(**submission_answers_from_form)

    @staticmethod
    def build_expression_context(
        collection: "Collection",
        mode: Literal["evaluation", "interpolation"],
        expression_context_end_point: Optional["Component"] = None,
        submission_helper: Optional["SubmissionHelper"] = None,
    ) -> "ExpressionContext":
        """Pulls together all of the context that we want to be able to expose to an expression when evaluating it."""

        assert len(ExpressionContext.ContextSources) == 1, (
            "When defining a new source of context for expressions, "
            "update this method and the ContextSourceChoices enum"
        )

        if submission_helper and submission_helper.collection.id != collection.id:
            raise ValueError("Mismatch between collection and submission.collection")

        # TODO: Namespace this set of data, eg under a `this_submission` prefix/key
        submission_data = ExpressionContext._build_submission_data(
            mode=mode,
            expression_context_end_point=expression_context_end_point,
            submission_helper=submission_helper,
        )

        if mode == "interpolation":
            for form in collection.forms:
                for question in form.cached_questions:
                    if expression_context_end_point and (
                        expression_context_end_point.form != form
                        or form.global_component_index(expression_context_end_point)
                        <= form.global_component_index(question)
                    ):
                        continue

                    submission_data.setdefault(question.safe_qid, f"(({question.name}))")

        return ExpressionContext(submission_data=submission_data)

    @staticmethod
    def _build_submission_data(
        mode: Literal["evaluation", "interpolation"],
        expression_context_end_point: Optional["Component"] = None,
        submission_helper: Optional["SubmissionHelper"] = None,
    ) -> dict[str, Any]:
        submission_data: dict[str, Any] = {}
        if submission_helper:
            for form in submission_helper.collection.forms:
                for question in form.cached_questions:
                    if expression_context_end_point is None or (
                        expression_context_end_point.form == form
                        and form.global_component_index(expression_context_end_point)
                        >= form.global_component_index(question)
                    ):
                        # until we do support aggregate methods in expressions we only support add another
                        # question answers through an explicit `with_add_another_context` which sets the context
                        if not question.add_another_container:
                            answer = submission_helper.cached_get_answer_for_question(question.id)
                            if answer is not None:
                                submission_data[question.safe_qid] = (
                                    answer.get_value_for_evaluation()
                                    if mode == "evaluation"
                                    else answer.get_value_for_interpolation()
                                )
        return submission_data

    @staticmethod
    def get_context_keys_and_labels(
        collection: "Collection", expression_context_end_point: Optional["Component"] = None
    ) -> dict[str, str]:
        """A dict mapping the reference variables (eg question safe_qids) to human-readable labels

        TODO: When we have more than just questions here, we'll need to do more complicated mapping, and possibly
        find a way to include labels for eg DB model columns, such as the grant name
        """
        ec = ExpressionContext.build_expression_context(
            collection=collection, mode="interpolation", expression_context_end_point=expression_context_end_point
        )
        return {k: v for k, v in ec.items()}

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


def _evaluate_expression_with_context(expression: "Expression", context: ExpressionContext | None = None) -> Any:
    """
    The base evaluator to use for handling all expressions.

    This parses arbitrary Python-language text into an Abstract Syntax Tree (AST) and then evaluates the result of
    that expression. Parsing arbitrary Python is extremely dangerous so we heavily restrict the AST nodes that we
    are willing to handle, to (hopefully) close off the attack surface to any malicious behaviour.

    The addition of any new AST nodes should be well-tested and intentional consideration should be given to any
    ways of exploit or misuse.
    """
    if context is None:
        context = ExpressionContext()
    context.expression_context = expression.context or {}

    evaluator = simpleeval.EvalWithCompoundTypes(names=context, functions=expression.required_functions)  # type: ignore[no-untyped-call]

    # Remove all nodes except those we explicitly allowlist
    evaluator.nodes = {
        ast_expr: ast_fn
        for ast_expr, ast_fn in evaluator.nodes.items()  # ty: ignore[possibly-missing-attribute]
        if ast_expr
        in {
            ast.UnaryOp,
            ast.Expr,
            ast.Name,
            ast.BinOp,
            ast.BoolOp,
            ast.Compare,
            ast.Subscript,
            ast.Attribute,
            ast.Slice,
            ast.Constant,
            ast.Call,
            ast.Set,
        }
    }

    try:
        result = evaluator.eval(expression.statement)  # type: ignore[no-untyped-call]
    except simpleeval.NameNotDefined as e:
        raise UndefinedVariableInExpression(e.message) from e
    except (simpleeval.FeatureNotAvailable, simpleeval.FunctionNotDefined) as e:
        raise DisallowedExpression("Expression is using unsafe/unsupported features") from e

    return result


@overload
def interpolate(
    text: str | None, context: ExpressionContext | None, *, with_interpolation_highlighting: Literal[False] = False
) -> str: ...


@overload
def interpolate(
    text: str | None, context: ExpressionContext | None, *, with_interpolation_highlighting: Literal[True]
) -> Markup: ...


def interpolate(
    text: str | None, context: ExpressionContext | None, *, with_interpolation_highlighting: bool = False
) -> str | Markup:
    from app.common.data.models import Expression

    if text is None:
        return "" if not with_interpolation_highlighting else Markup("")

    def _interpolate(matchobj: re.Match[Any]) -> str:
        expr = Expression(statement=matchobj.group(0))

        try:
            value = _evaluate_expression_with_context(expr, context)
            if with_interpolation_highlighting:
                return f'<span class="app-context-aware-editor--valid-reference">{escape(value)}</span>'
        except (UndefinedVariableInExpression, DisallowedExpression):
            value = matchobj.group(0)

        return str(value)

    result = INTERPOLATE_REGEX.sub(
        _interpolate,
        text,
    )

    if with_interpolation_highlighting:
        return Markup(result)
    return result


def evaluate(expression: "Expression", context: ExpressionContext | None = None) -> bool:
    result = _evaluate_expression_with_context(expression, context)

    # do we want these to evalaute to non-bool types like int/str ever?
    if not isinstance(result, bool):
        raise InvalidEvaluationResult(f"Result of evaluating {expression=} was {result=}; expected a boolean.")

    return result
