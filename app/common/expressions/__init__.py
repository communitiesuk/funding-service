import ast
import uuid
from typing import TYPE_CHECKING, Any

import simpleeval

if TYPE_CHECKING:
    from app.common.data.models import Expression


class BaseExpressionError(Exception):
    pass


class UndefinedVariableInExpression(BaseExpressionError):
    pass


class DisallowedExpression(BaseExpressionError):
    pass


class InvalidEvaluationResult(BaseExpressionError):
    pass


def _evaluate_expression_with_context(
    expression: "Expression", context: dict[str, str | int | float | bool | None] | None = None
) -> Any:
    """
    The base evaluator to use for handling all expressions.

    This parses arbitrary Python-language text into an Abstract Syntax Tree (AST) and then evaluates the result of
    that expression. Parsing arbitrary Python is extremely dangerous so we heavily restrict the AST nodes that we
    are willing to handle, to (hopefully) close off the attack surface to any malicious behaviour.

    The addition of any new AST nodes should be well-tested and intentional consideration should be given to any
    ways of exploit or misuse.
    """
    expr_context = expression.context or {}
    context = context or {}

    if context_overlap := set(expr_context).intersection(set(context)):
        raise ValueError(
            f"Cannot safely evaluate with overlapping contexts. "
            f"The following keys exist in both the expression.context and additional context: {context_overlap}."
        )

    merged_context = {**expr_context, **context}

    # May want EvalWithCompoundTypes at some point, but for now simple+very limited is OK.
    evaluator = simpleeval.SimpleEval(names=merged_context)  # type: ignore[no-untyped-call]

    # Remove all nodes except those we explicitly allowlist
    evaluator.nodes = {
        ast_expr: ast_fn
        for ast_expr, ast_fn in evaluator.nodes.items()
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
            ast.Index,
            ast.Slice,
            ast.Constant,
            ast.Call,
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
def interpolate(expression: "Expression", context: dict[str, str | int | float | bool | None] | None = None) -> Any: ...


def evaluate(expression: "Expression", context: dict[str, str | int | float | bool | None] | None = None) -> bool:
    result = _evaluate_expression_with_context(expression, context)

    # do we want these to evalaute to non-bool types like int/str ever?
    if not isinstance(result, bool):
        raise InvalidEvaluationResult(f"Result of evaluating {expression=} was {result=}; expected a boolean.")

    return result


def mangle_question_id_for_context(question_id: uuid.UUID) -> str:
    # todo: work out how to refer to questions in an expressions-compatible way without doing this mangling
    #       in all of the places. It's not nice.
    return "q_" + question_id.hex
