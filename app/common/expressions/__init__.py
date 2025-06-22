import ast
from typing import TYPE_CHECKING, Any, Iterator, cast

import simpleeval
from immutabledict import immutabledict

from app.common.data.types import immutable_json_flat_scalars, json_flat_scalars, scalars

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


class ExpressionContext(immutable_json_flat_scalars):
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
        from_form: immutable_json_flat_scalars | None = None,
        from_submission: immutable_json_flat_scalars | None = None,
        from_expression: immutable_json_flat_scalars | None = None,
        *args: Any,
        **kwargs: Any,
    ):
        # TODO: we will probably end up with some of these dicts having nested data (eg for complex questions like
        #       address; so `scalars` likely won't last forever.
        super().__init__(*args, **kwargs)

        if from_form is None:
            from_form = cast(immutable_json_flat_scalars, immutabledict())
        if from_submission is None:
            from_submission = cast(immutable_json_flat_scalars, immutabledict())
        if from_expression is None:
            from_expression = cast(immutable_json_flat_scalars, immutabledict())

        self._form_context: immutable_json_flat_scalars = from_form
        self._submission_context: immutable_json_flat_scalars = from_submission
        self._expression_context: immutable_json_flat_scalars = from_expression
        self._update_keys()

    @property
    def form_context(self) -> immutable_json_flat_scalars:
        return self._form_context

    @form_context.setter
    def form_context(self, value: immutable_json_flat_scalars) -> None:
        self._form_context = value
        self._update_keys()

    @property
    def submission_context(self) -> immutable_json_flat_scalars:
        return self._submission_context

    @submission_context.setter
    def submission_context(self, value: immutable_json_flat_scalars) -> None:
        self._submission_context = value
        self._update_keys()

    @property
    def expression_context(self) -> immutable_json_flat_scalars:
        return self._expression_context

    @expression_context.setter
    def expression_context(self, value: immutable_json_flat_scalars) -> None:
        self._expression_context = value
        self._update_keys()

    def _update_keys(self) -> None:
        _form_context: json_flat_scalars = cast(json_flat_scalars, self.form_context or {})
        _submission_context: json_flat_scalars = cast(json_flat_scalars, self.submission_context or {})
        _expression_context: json_flat_scalars = cast(json_flat_scalars, self.expression_context or {})

        # note: This feels like it could just be a set, or that a set is a more appropriate data structure. However I've
        # chosen a dict on purpose because: sets in python are unordered; dicts in python are ordered by insertion
        # time. ExpressionContext is meant to look and feel like a plain old dict, so maintaining the ordering has been
        # done semi-intentionally. Of course, there is a slight quirk - ordering is based on both insertion time _and_
        # the layering. All keys from form context will come first, then any new keys from submission context, then any
        # new keys from expression context. It may or may not be useful to try to 'maintain' ordering given this, but
        # maybe it's still "better" than fully-random set ordering.
        _keys: dict[str, None] = dict()

        for _dict in [_form_context, _submission_context, _expression_context]:
            for _key in _dict:
                _keys.setdefault(_key, None)

        self._keys = _keys

    def __getitem__(self, key: str) -> scalars | None:
        if key in self.form_context:
            return self.form_context[key]
        elif key in self.submission_context:
            return self.submission_context[key]
        elif key in self.expression_context:
            return self.expression_context[key]
        else:
            raise KeyError(key)

    def get(self, key: str, default: scalars | None = None) -> scalars | None:  # type: ignore[override]
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key: object) -> bool:
        return key in self._keys

    def __iter__(self) -> Iterator[str]:
        return iter(self._keys)

    def __len__(self) -> int:
        return len(self._keys)

    def __repr__(self) -> str:
        items = {key: self[key] for key in self._keys}
        return f"ExpressionContext({items})"

    def __str__(self) -> str:
        items = {key: self[key] for key in self._keys}
        return str(items)

    def keys(self) -> list[str]:  # type: ignore[override]
        return list(self._keys)

    def values(self) -> list[scalars | None]:  # type: ignore[override]
        return [self[key] for key in self._keys]

    def items(self) -> list[tuple[str, scalars | None]]:  # type: ignore[override]
        return [(key, self[key]) for key in self._keys]


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
    context.expression_context = immutabledict(expression.context or {})

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
def interpolate(expression: "Expression", context: ExpressionContext | None) -> Any: ...


def evaluate(expression: "Expression", context: ExpressionContext | None = None) -> bool:
    result = _evaluate_expression_with_context(expression, context)

    # do we want these to evalaute to non-bool types like int/str ever?
    if not isinstance(result, bool):
        raise InvalidEvaluationResult(f"Result of evaluating {expression=} was {result=}; expected a boolean.")

    return result
