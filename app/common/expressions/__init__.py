import ast
import uuid
from typing import TYPE_CHECKING, Any

import simpleeval
from flask import current_app
from immutabledict import immutabledict

from app.common.data.types import json_flat_scalars

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


class ExpressionContext(dict):
    """
    A thin wrapper around three immutable dicts, where access to keys is done in priority order:
    - Keys from the `form` come first (data just submitted by the user answering some questions)
    - Keys from the `submission` come next (all data currently held about a submission)
    - Keys from the `expression` come last (DB expression.context)

    The only overlap should be between `form` and `submission`, where `form` holds the latest data and `submission`
    holds the previous answer (until the page is saved).

    The main reason for this is to treat each of these things as immutable, but overlay them. To do this with a standard
    dict would mean creating lots of copies/merges/duplicates and juggling them.
    """

    def __init__(
        self,
        from_form: immutabledict[str, json_flat_scalars] | None = None,
        from_submission: immutabledict[str, json_flat_scalars] | None = None,
        from_expression: immutabledict[str, json_flat_scalars] | None = None,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self._form_context = from_form
        self._submission_context = from_submission
        self._expression_context = from_expression
        self._update_keys()

    @property
    def form_context(self):
        return self._form_context

    @form_context.setter
    def form_context(self, value):
        if self._form_context is not None:
            raise ValueError("`form_context` already set")
        self._form_context = value
        self._update_keys()

    @property
    def submission_context(self):
        return self._submission_context

    @submission_context.setter
    def submission_context(self, value):
        if self._submission_context is not None:
            raise ValueError("`submission_context` already set")
        self._submission_context = value
        self._update_keys()

    @property
    def expression_context(self):
        return self._expression_context

    @expression_context.setter
    def expression_context(self, value):
        # Allow this - will be updated just-in-time for each expression evaluation
        # if self._expression_context is not None:
        #     raise ValueError("`expression_context` already set")
        self._expression_context = value
        self._update_keys()

    def _update_keys(self):
        _expression_context = self.expression_context or {}
        _submission_context = self.submission_context or {}
        _form_context = self.form_context or {}
        self._keys = set(_expression_context.keys()) | set(_submission_context.keys()) | set(_form_context.keys())

    def __getitem__(self, key):
        if self.expression_context is None or self.submission_context is None or self.form_context is None:
            raise ValueError(
                "Cannot use expression context without setting expression_context, submission_context, and form_context"
            )

        if key in self.form_context:
            return self.form_context[key]
        elif key in self.submission_context:
            return self.submission_context[key]
        elif key in self.expression_context:
            return self.expression_context[key]
        else:
            raise KeyError(key)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key):
        return key in self._keys

    def __iter__(self):
        return iter(self._keys)

    def __len__(self):
        return len(self._keys)

    def __repr__(self):
        items = {key: self[key] for key in self._keys}
        return f"ExpressionContext({items})"

    def __str__(self):
        items = {key: self[key] for key in self._keys}
        return str(items)

    def keys(self):
        return self._keys

    def values(self):
        return [self[key] for key in self._keys]

    def items(self):
        return [(key, self[key]) for key in self._keys]


def _evaluate_expression_with_context(expression: "Expression", context: ExpressionContext) -> Any:
    """
    The base evaluator to use for handling all expressions.

    This parses arbitrary Python-language text into an Abstract Syntax Tree (AST) and then evaluates the result of
    that expression. Parsing arbitrary Python is extremely dangerous so we heavily restrict the AST nodes that we
    are willing to handle, to (hopefully) close off the attack surface to any malicious behaviour.

    The addition of any new AST nodes should be well-tested and intentional consideration should be given to any
    ways of exploit or misuse.
    """
    context.expression_context = expression.context

    current_app.logger.debug(
        "Evaluating %(statement)s with %(context)s", dict(statement=expression.statement, context=str(context))
    )
    # May want EvalWithCompoundTypes at some point, but for now simple+very limited is OK.
    evaluator = simpleeval.SimpleEval(names=context)  # type: ignore[no-untyped-call]

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
def interpolate(expression: "Expression", context: ExpressionContext) -> Any: ...


def evaluate(expression: "Expression", context: ExpressionContext) -> bool:
    result = _evaluate_expression_with_context(expression, context)

    # do we want these to evalaute to non-bool types like int/str ever?
    if not isinstance(result, bool):
        raise InvalidEvaluationResult(f"Result of evaluating {expression=} was {result=}; expected a boolean.")

    return result


def mangle_question_id_for_context(question_id: uuid.UUID) -> str:
    # todo: work out how to refer to questions in an expressions-compatible way without doing this mangling
    #       in all of the places. It's not nice.
    return "q_" + question_id.hex
