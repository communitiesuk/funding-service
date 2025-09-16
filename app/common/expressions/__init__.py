import ast
from collections import ChainMap
from typing import TYPE_CHECKING, Any, MutableMapping

import simpleeval

if TYPE_CHECKING:
    from app.common.data.models import Expression


class ManagedExpressionError(Exception):
    pass


class UndefinedVariableInExpression(ManagedExpressionError):
    pass


class DisallowedExpression(ManagedExpressionError):
    pass


class InvalidEvaluationResult(ManagedExpressionError):
    pass


class SubmissionContext(ChainMap[str, Any]):
    def __init__(self, *, form_data: dict[str, Any] | None = None, submission_data: dict[str, Any] | None = None):
        self.submission_data = submission_data or {}
        self.form_data = form_data or {}
        super().__init__(self.form_data, self.submission_data)

    def set_form_data(self, form_data: dict[str, Any]) -> None:
        self.maps = [form_data, self.submission_data]


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
    should override any data from the database. We do this via SubmissionContext, which overlays the form data on
    top of the submission DB data using a ChainMap.
    """

    def __init__(
        self,
        submission_context: SubmissionContext | None = None,
        expression_context: dict[str, Any] | None = None,
    ):
        self._submission_context: SubmissionContext = submission_context or SubmissionContext()
        self._expression_context = expression_context or {}

        super().__init__(*self._ordered_contexts)

    @property
    def _ordered_contexts(self) -> list[MutableMapping[str, Any]]:
        return list(filter(None, [self._submission_context, self.expression_context]))

    @property
    def expression_context(self) -> dict[str, Any]:
        return self._expression_context

    @expression_context.setter
    def expression_context(self, expression_context: dict[str, Any]) -> None:
        self._expression_context = expression_context
        self.maps = self._ordered_contexts

    def update_submission_context_with_form_context(self, form_context: dict[str, Any]) -> None:
        self._submission_context.set_form_data(form_context)


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
        for ast_expr, ast_fn in evaluator.nodes.items()  # ty: ignore[possibly-unbound-attribute]
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


# todo: interpolate an expression (eg for injecting dynamic data into question text, error messages, etc)
def interpolate(expression: "Expression", context: ExpressionContext | None) -> Any: ...


def evaluate(expression: "Expression", context: ExpressionContext | None = None) -> bool:
    result = _evaluate_expression_with_context(expression, context)

    # do we want these to evalaute to non-bool types like int/str ever?
    if not isinstance(result, bool):
        raise InvalidEvaluationResult(f"Result of evaluating {expression=} was {result=}; expected a boolean.")

    return result
