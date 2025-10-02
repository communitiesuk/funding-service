import abc
import datetime
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar, Union, cast
from typing import Optional as TOptional

# Define any "managed" expressions that can be applied to common conditions or validations
# that are built through the UI. These will be used alongside custom expressions
from uuid import UUID

from flask import render_template
from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import (
    GovCheckboxesInput,
    GovCheckboxInput,
    GovDateInput,
    GovRadioInput,
    GovSubmitInput,
    GovTextInput,
)
from markupsafe import Markup
from pydantic import BaseModel, TypeAdapter
from wtforms import BooleanField, DateField, IntegerField, SelectField, SelectMultipleField, StringField
from wtforms.fields.core import Field
from wtforms.validators import DataRequired, InputRequired, Optional, ReadOnly, ValidationError

from app.common.data.types import ManagedExpressionsEnum, QuestionDataType
from app.common.expressions.registry import lookup_managed_expression, register_managed_expression
from app.common.filters import format_date_approximate, format_date_short
from app.common.forms.fields import MHCLGApproximateDateInput
from app.common.qid import SafeQidMixin
from app.types import TRadioItem

if TYPE_CHECKING:
    from app.common.data.models import Expression, Question
    from app.common.expressions.forms import _ManagedExpressionForm


class ManagedExpression(BaseModel, SafeQidMixin):
    # Defining this as a ClassVar allows direct access from the class and excludes it from pydantic instance
    name: ClassVar[ManagedExpressionsEnum]
    supported_condition_data_types: ClassVar[set[QuestionDataType]]
    supported_validator_data_types: ClassVar[set[QuestionDataType]]

    _key: ManagedExpressionsEnum
    question_id: UUID

    @property
    @abc.abstractmethod
    def statement(self) -> str:
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def description(self) -> str: ...

    @property
    @abc.abstractmethod
    def message(self) -> str: ...

    @property
    def required_functions(self) -> dict[str, Union[Callable[[Any], Any], type]]:
        """
        Used when we evaluate an expression to add specific functions to the list of what simpleeval will accept
        and parse.
        Provides a default implementation that returns an empty dict (no additional functions).

        If your ManagedExpression needs a specific function to evaluate the statement,
        eg. q_543 < calculate_something_complex(),
        override this function as follows:

            @property
            def required_functions(self) -> dict[str, Union[Callable[[Any], Any], type]]:
                return dict(calculate_something_complex=app.stuff.calculate_something_complex)

        Where the keys of the dict are the function names as they will appear in the expression statement, and the
        values are the function definitions.

        """
        return dict()

    @property
    def referenced_question(self) -> "Question":
        # todo: split up the collections interface to let us sensibly reason about whats importing what
        from app.common.data.interfaces.collections import get_question_by_id

        # todo: this will do a database query per expression on the question - for now we'd anticipate
        #       questions only have one or two managed expressions but in the future we should probably
        #       optimise this to fetch the full schema once and then re-use that throughout these helpers
        return get_question_by_id(self.question_id)

    # implementing these two fields will update the "add/edit condition/validation" pages for any question types
    # that are defined in `question_data_types`.
    @staticmethod
    @abc.abstractmethod
    def get_form_fields(
        referenced_question: "Question", expression: TOptional["Expression"] = None
    ) -> dict[str, "Field"]:
        """
        A hook used by `build_managed_expression_form`. It should return the set of form fields which need to be
        added to the managed expression form. The fields returned should collect the data needed to define an instance
        of the managed expression.

        class GreaterThan(ManagedExpression):
            key: ManagedExpressionsEnum = ManagedExpressionsEnum.GREATER_THAN

        Eg:
            return {
                "greater_than_value": IntegerField(
                    "Minimum value",
                    widget=GovTextInput(),
                    validators=[Optional()],
                    render_kw={"params": {"classes": "govuk-input--width-10"}},
                ),
            }

        Note:   Only add the `Optional()` validator here. If further validation is required (eg. making sure the answer
                is a number) add these validators in `update_validators` instead. This is because if there are multiple
                managed expressions available for a question type they all appear on the same page, and adding
                validation to the fields directly means they are validated even if a different type of expression was
                selected.

        Note: because these are fed into dynamic form generation, and these dynamic forms are rendered automatically,
              we need to specify the parameters tweak rendering here. `render_kw['params']` is of the same format
              and structure as in Jinja2 templates directly, which closely follows the official GOV.UK Frontend
              nunjucks macros that you can find in the Design System, eg at https://design-system.service.gov.uk/components/text-input/.
        """  # noqa: E501
        ...

    @staticmethod
    @abc.abstractmethod
    def update_validators(form: "_ManagedExpressionForm") -> None:
        """
        A hook used by `build_managed_expression_form`. If this managed expression has been selected, then (some or all
        of) the fields are likely to required to correctly define the instance. Mutate the fields on the form to set
        those validators here.

        Set these validators on the form fields that were added in `get_form_fields`. See notes there about why we set
        the validators in a separate function.

        Eg:
            def update_validators(form: "_ManagedExpressionForm") -> None:
                form.greater_than_value.validators = [InputRequired("Enter the minimum value allowed for this question")]
        """  # noqa: E501
        ...

    @classmethod
    def concatenate_all_wtf_fields_html(cls, form: "_ManagedExpressionForm", referenced_question: "Question") -> Markup:
        """
        A hook used by `build_managed_expression_form` to support conditionally-revealed the fields that a user needs
        to complete when they select this managed expression type from the radio list of available managed expressions.

        This does not need to be re-defined on any subclasses; it will work automatically.
        """
        # FIXME: Re-using cls.get_form_fields() is a 🤏 bit wasteful (building form fields that aren't used).
        fields = [
            getattr(form, field_name)()
            for field_name in cls.get_form_fields(referenced_question=referenced_question).keys()
        ]

        return Markup("\n".join(fields))

    @staticmethod
    @abc.abstractmethod
    def build_from_form(form: "_ManagedExpressionForm", question: "Question") -> "ManagedExpression":
        """
        A hook used by `build_managed_expression_form`. If this managed expression type has been selected during form
        submission, this hook will be called. It should pull data from the form and use that to instantiate and return
        the managed expression.

        Eg:
            def build_from_form(form: "_ManagedExpressionForm", question: "Question") -> "GreaterThan":
                return GreaterThan(
                    question_id=question.id,
                    minimum_value=form.greater_than_value.data,
                    inclusive=form.greater_than_inclusive.data,
                )
        """
        ...


class BottomOfRangeIsLower:
    def __init__(self, message: str | None = None):
        if not message:
            message = "The minimum value must be lower than the maximum value"
        self.message = message

    def __call__(self, form: "FlaskForm", field: "Field") -> None:
        bottom_of_range = form.between_bottom_of_range and form.between_bottom_of_range.data  # ty: ignore[unresolved-attribute]
        top_of_range = form.between_top_of_range and form.between_top_of_range.data  # ty: ignore[unresolved-attribute]
        if bottom_of_range and top_of_range:
            if bottom_of_range >= top_of_range:
                raise ValidationError(self.message)


@register_managed_expression
class GreaterThan(ManagedExpression):
    name: ClassVar[ManagedExpressionsEnum] = ManagedExpressionsEnum.GREATER_THAN
    supported_condition_data_types: ClassVar[set[QuestionDataType]] = {QuestionDataType.INTEGER}
    supported_validator_data_types: ClassVar[set[QuestionDataType]] = {QuestionDataType.INTEGER}

    _key: ManagedExpressionsEnum = name

    question_id: UUID
    minimum_value: int | None
    minimum_expression: str | None = None
    inclusive: bool = False

    @property
    def description(self) -> str:
        return f"Is greater than{' or equal to' if self.inclusive else ''}"

    @property
    def message(self) -> str:
        return (
            f"The answer must be greater than {'or equal to ' if self.inclusive else ''}"
            + f"{self.minimum_expression if self.minimum_expression else self.minimum_value}"
        )

    @property
    def statement(self) -> str:
        return (
            f"{self.safe_qid} >{'=' if self.inclusive else ''} "
            + f"{self.minimum_expression if self.minimum_expression else self.minimum_value}"
        )

    @property
    def referenced_ids(self) -> list[UUID]:
        # This will eventually be used to store any referenced question IDs for context aware conditions
        return []

    @staticmethod
    def get_form_fields(
        referenced_question: "Question", expression: TOptional["Expression"] = None
    ) -> dict[str, "Field"]:
        return {
            "greater_than_value": IntegerField(
                "Minimum value",
                default=cast(int, expression.context.get("minimum_value")) if expression else None,
                widget=GovTextInput(),
                validators=[Optional()],
                render_kw={
                    "params": {"classes": "govuk-input--width-10"},
                },
            ),
            "greater_than_add_context": StringField(
                "Insert data",
                widget=GovSubmitInput(),
            ),
            "greater_than_expression": StringField(
                "Minimum expression",
                default=expression.context.get("minimum_expression", "") or "" if expression else "",  # type: ignore[arg-type]
                widget=GovTextInput(),
                render_kw={"params": {"classes": "govuk-input--width-20", "attributes": {"readonly": ""}}},
            ),
            "greater_than_inclusive": BooleanField(
                "An answer of exactly the minimum value is allowed",
                default=cast(bool, expression.context["inclusive"]) if expression else None,
                widget=GovCheckboxInput(),
            ),
        }

    @staticmethod
    def update_validators(form: "_ManagedExpressionForm") -> None:
        form.greater_than_value.validators = (
            [InputRequired("Enter the minimum value allowed for this question")]
            if not form.greater_than_expression.data
            else [Optional()]
        )  # ty: ignore[unresolved-attribute]
        form.greater_than_expression.validators = [ReadOnly()]  # ty: ignore[unresolved-attribute]

    @staticmethod
    def build_from_form(
        form: "_ManagedExpressionForm", question: "Question", expression: TOptional["Expression"] = None
    ) -> "GreaterThan":
        return GreaterThan(
            question_id=question.id,
            minimum_value=form.greater_than_value.data if not form.greater_than_expression.data else None,
            minimum_expression=form.greater_than_expression.data if form.greater_than_expression.data else None,
            inclusive=form.greater_than_inclusive.data,  # ty: ignore[unresolved-attribute]
        )

    @classmethod
    def concatenate_all_wtf_fields_html(cls, form: "_ManagedExpressionForm", referenced_question: "Question") -> Markup:
        return Markup(render_template("deliver_grant_funding/reports/managed_expressions/greater_than.html", form=form))


@register_managed_expression
class LessThan(ManagedExpression):
    name: ClassVar[ManagedExpressionsEnum] = ManagedExpressionsEnum.LESS_THAN
    supported_condition_data_types: ClassVar[set[QuestionDataType]] = {QuestionDataType.INTEGER}
    supported_validator_data_types: ClassVar[set[QuestionDataType]] = {QuestionDataType.INTEGER}

    _key: ManagedExpressionsEnum = name

    question_id: UUID
    maximum_value: int
    inclusive: bool = False

    @property
    def description(self) -> str:
        return f"Is less than{' or equal to' if self.inclusive else ''}"

    @property
    def message(self) -> str:
        return f"The answer must be less than {'or equal to ' if self.inclusive else ''}{self.maximum_value}"

    @property
    def statement(self) -> str:
        return f"{self.safe_qid} <{'=' if self.inclusive else ''} {self.maximum_value}"

    @staticmethod
    def get_form_fields(
        referenced_question: "Question", expression: TOptional["Expression"] = None
    ) -> dict[str, "Field"]:
        return {
            "less_than_value": IntegerField(
                "Maximum value",
                default=cast(int, expression.context["maximum_value"]) if expression else None,
                widget=GovTextInput(),
                validators=[Optional()],
                render_kw={"params": {"classes": "govuk-input--width-10"}},
            ),
            "less_than_inclusive": BooleanField(
                "An answer of exactly the maximum value is allowed",
                default=cast(bool, expression.context["inclusive"]) if expression else None,
                widget=GovCheckboxInput(),
            ),
        }

    @staticmethod
    def update_validators(form: "_ManagedExpressionForm") -> None:
        form.less_than_value.validators = [InputRequired("Enter the maximum value allowed for this question")]  # ty: ignore[unresolved-attribute]

    @staticmethod
    def build_from_form(form: "_ManagedExpressionForm", question: "Question") -> "LessThan":
        return LessThan(
            question_id=question.id,
            maximum_value=form.less_than_value.data,  # ty: ignore[unresolved-attribute]
            inclusive=form.less_than_inclusive.data,  # ty: ignore[unresolved-attribute]
        )


@register_managed_expression
class Between(ManagedExpression):
    name: ClassVar[ManagedExpressionsEnum] = ManagedExpressionsEnum.BETWEEN
    supported_condition_data_types: ClassVar[set[QuestionDataType]] = {QuestionDataType.INTEGER}
    supported_validator_data_types: ClassVar[set[QuestionDataType]] = {QuestionDataType.INTEGER}

    _key: ManagedExpressionsEnum = name

    question_id: UUID
    minimum_value: int
    minimum_inclusive: bool = False
    maximum_value: int
    maximum_inclusive: bool = False

    @property
    def description(self) -> str:
        return "Is between"

    @property
    def message(self) -> str:
        # todo: optionally include the question name in the default message
        # todo: do you allow the form builder to override this if they need to
        #       - does that persist in the context (inherited from ManagedExpression) or as a separate
        #         property on the model
        # todo: make this use expression evaluation/interpolation rather than f-strings
        return (
            f"The answer must be between "
            f"{self.minimum_value}{' (inclusive)' if self.minimum_inclusive else ' (exclusive)'} and "
            f"{self.maximum_value}{' (inclusive)' if self.maximum_inclusive else ' (exclusive)'}"
        )

    @property
    def statement(self) -> str:
        # todo: do you refer to the question by ID or slugs - pros and cons - discuss - by the end of the epic
        return (
            f"{self.minimum_value} "
            f"<{'=' if self.minimum_inclusive else ''} "
            f"{self.safe_qid} "
            f"<{'=' if self.maximum_inclusive else ''} "
            f"{self.maximum_value}"
        )

    @staticmethod
    def get_form_fields(
        referenced_question: "Question", expression: TOptional["Expression"] = None
    ) -> dict[str, "Field"]:
        return {
            "between_bottom_of_range": IntegerField(
                "Minimum value",
                default=cast(int, expression.context["minimum_value"]) if expression else None,
                widget=GovTextInput(),
                validators=[Optional()],
                render_kw={"params": {"classes": "govuk-input--width-10"}},
            ),
            "between_bottom_inclusive": BooleanField(
                "An answer of exactly the minimum value is allowed",
                default=cast(bool, expression.context["minimum_inclusive"]) if expression else None,
                widget=GovCheckboxInput(),
            ),
            "between_top_of_range": IntegerField(
                "Maximum value",
                default=cast(int, expression.context["maximum_value"]) if expression else None,
                widget=GovTextInput(),
                validators=[Optional()],
                render_kw={"params": {"classes": "govuk-input--width-10"}},
            ),
            "between_top_inclusive": BooleanField(
                "An answer of exactly the maximum value is allowed",
                default=cast(bool, expression.context["maximum_inclusive"]) if expression else None,
                widget=GovCheckboxInput(),
            ),
        }

    @staticmethod
    def update_validators(form: "_ManagedExpressionForm") -> None:
        form.between_bottom_of_range.validators = [  # ty: ignore[unresolved-attribute]
            InputRequired("Enter the minimum value allowed for this question"),
            BottomOfRangeIsLower("The minimum value must be lower than the maximum value"),
        ]
        form.between_top_of_range.validators = [  # ty: ignore[unresolved-attribute]
            InputRequired("Enter the maximum value allowed for this question"),
            BottomOfRangeIsLower("The maximum value must be higher than the minimum value"),
        ]

    @staticmethod
    def build_from_form(form: "_ManagedExpressionForm", question: "Question") -> "Between":
        return Between(
            question_id=question.id,
            minimum_value=form.between_bottom_of_range.data,  # ty: ignore[unresolved-attribute]
            minimum_inclusive=form.between_bottom_inclusive.data,  # ty: ignore[unresolved-attribute]
            maximum_value=form.between_top_of_range.data,  # ty: ignore[unresolved-attribute]
            maximum_inclusive=form.between_top_inclusive.data,  # ty: ignore[unresolved-attribute]
        )


class BaseDataSourceManagedExpression(ManagedExpression):
    @property
    @abc.abstractmethod  # todo: decorator does nothing here because ABCMeta cant be used
    def referenced_data_source_items(self) -> list["TRadioItem"]:
        raise NotImplementedError


@register_managed_expression
class AnyOf(BaseDataSourceManagedExpression):
    name: ClassVar[ManagedExpressionsEnum] = ManagedExpressionsEnum.ANY_OF
    supported_condition_data_types: ClassVar[set[QuestionDataType]] = {QuestionDataType.RADIOS}
    supported_validator_data_types: ClassVar[set[QuestionDataType]] = {}  # type: ignore[assignment]

    _key: ManagedExpressionsEnum = name

    question_id: UUID
    items: list["TRadioItem"]

    @property
    def description(self) -> str:
        return "any of"

    @property
    def message(self) -> str:
        if len(self.items) == 1:
            return f"The answer is “{self.items[0]['label']}”"

        return f"The answer is one of “{'”, “'.join(c['label'] for c in self.items)}”"

    @property
    def statement(self) -> str:
        item_keys = {str(item["key"]) for item in self.items}
        return f"{self.safe_qid} in {item_keys}"

    @staticmethod
    def get_form_fields(
        referenced_question: "Question", expression: TOptional["Expression"] = None
    ) -> dict[str, "Field"]:
        if referenced_question is None or referenced_question.data_source is None:
            raise ValueError("The question for the AnyOf expression must have a data source")

        return {
            "any_of": SelectMultipleField(
                "Choose from the list of options",
                default=[item["key"] for item in expression.context["items"]] if expression else None,  # type: ignore[index, union-attr]
                widget=GovCheckboxesInput(),
                choices=[(item.key, item.label) for item in referenced_question.data_source.items],
                validators=[Optional()],
                render_kw={"params": {"fieldset": {"legend": {"classes": "govuk-visually-hidden"}}}},
            ),
        }

    @staticmethod
    def update_validators(form: "_ManagedExpressionForm") -> None:
        form.any_of.validators = [  # ty: ignore[unresolved-attribute]
            DataRequired("Choose at least one option"),
        ]

    @staticmethod
    def build_from_form(form: "_ManagedExpressionForm", question: "Question") -> "AnyOf":
        item_labels = {choice.key: choice.label for choice in question.data_source.items}

        items: list[TRadioItem] = [{"key": key, "label": item_labels[key]} for key in form.any_of.data]  # ty: ignore[unresolved-attribute]
        return AnyOf(
            question_id=question.id,
            items=items,  # ty: ignore[unresolved-attribute]
        )

    @property
    def referenced_data_source_items(self) -> list["TRadioItem"]:
        return self.items


@register_managed_expression
class IsYes(ManagedExpression):
    name: ClassVar[ManagedExpressionsEnum] = ManagedExpressionsEnum.IS_YES
    supported_condition_data_types: ClassVar[set[QuestionDataType]] = {QuestionDataType.YES_NO}
    supported_validator_data_types: ClassVar[set[QuestionDataType]] = {}  # type: ignore[assignment]

    _key: ManagedExpressionsEnum = name

    question_id: UUID

    @property
    def description(self) -> str:
        return "is yes"

    @property
    def message(self) -> str:
        return "The answer is “yes”"

    @property
    def statement(self) -> str:
        return f"{self.safe_qid} is True"

    @staticmethod
    def get_form_fields(
        referenced_question: "Question", expression: TOptional["Expression"] = None
    ) -> dict[str, "Field"]:
        return {}

    @staticmethod
    def update_validators(form: "_ManagedExpressionForm") -> None:
        pass

    @staticmethod
    def build_from_form(form: "_ManagedExpressionForm", question: "Question") -> "IsYes":
        return IsYes(question_id=question.id)


@register_managed_expression
class IsNo(ManagedExpression):
    name: ClassVar[ManagedExpressionsEnum] = ManagedExpressionsEnum.IS_NO
    supported_condition_data_types: ClassVar[set[QuestionDataType]] = {QuestionDataType.YES_NO}
    supported_validator_data_types: ClassVar[set[QuestionDataType]] = {}  # type: ignore[assignment]

    _key: ManagedExpressionsEnum = name

    question_id: UUID

    @property
    def description(self) -> str:
        return "is no"

    @property
    def message(self) -> str:
        return "The answer is “no”"

    @property
    def statement(self) -> str:
        return f"{self.safe_qid} is False"

    @staticmethod
    def get_form_fields(
        referenced_question: "Question", expression: TOptional["Expression"] = None
    ) -> dict[str, "Field"]:
        return {}

    @staticmethod
    def update_validators(form: "_ManagedExpressionForm") -> None:
        pass

    @staticmethod
    def build_from_form(form: "_ManagedExpressionForm", question: "Question") -> "IsNo":
        return IsNo(question_id=question.id)


@register_managed_expression
class Specifically(BaseDataSourceManagedExpression):
    name: ClassVar[ManagedExpressionsEnum] = ManagedExpressionsEnum.SPECIFICALLY
    supported_condition_data_types: ClassVar[set[QuestionDataType]] = {QuestionDataType.CHECKBOXES}
    supported_validator_data_types: ClassVar[set[QuestionDataType]] = {}  # type: ignore[assignment]

    _key: ManagedExpressionsEnum = name

    question_id: UUID
    item: "TRadioItem"

    @property
    def description(self) -> str:
        return "specifically"

    @property
    def message(self) -> str:
        return f"The answer is “{self.item['label']}”"

    @property
    def statement(self) -> str:
        # TODO: This a bit fragile - another reason for referencing a data source item?
        return f"{self.item['key']!r} in {self.safe_qid}"

    @staticmethod
    def get_form_fields(
        referenced_question: "Question", expression: TOptional["Expression"] = None
    ) -> dict[str, "Field"]:
        if referenced_question is None or referenced_question.data_source is None:
            raise ValueError("The question for the Specifically expression must have a data source")

        return {
            "specifically": SelectField(
                "Choose from the list of options",
                default=expression.context["item"]["key"] if expression else None,  # type: ignore[index]
                widget=GovRadioInput(),
                choices=[(item.key, item.label) for item in referenced_question.data_source.items],
                validators=[DataRequired("Choose one option")],
                render_kw={"params": {"fieldset": {"legend": {"classes": "govuk-visually-hidden"}}}},
            ),
        }

    @staticmethod
    def update_validators(form: "_ManagedExpressionForm") -> None:
        pass

    @staticmethod
    def build_from_form(form: "_ManagedExpressionForm", question: "Question") -> "Specifically":
        item_labels = {item.key: item.label for item in question.data_source.items}
        selected_key = form.specifically.data  # ty: ignore[unresolved-attribute]
        item: TRadioItem = {"key": selected_key, "label": item_labels[selected_key]}
        return Specifically(question_id=question.id, item=item)

    @property
    def referenced_data_source_items(self) -> list["TRadioItem"]:
        return [self.item]


@register_managed_expression
class IsBefore(ManagedExpression):
    name: ClassVar[ManagedExpressionsEnum] = ManagedExpressionsEnum.IS_BEFORE
    supported_condition_data_types: ClassVar[set[QuestionDataType]] = {QuestionDataType.DATE}
    supported_validator_data_types: ClassVar[set[QuestionDataType]] = {QuestionDataType.DATE}

    _key: ManagedExpressionsEnum = name

    question_id: UUID
    latest_value: datetime.date
    inclusive: bool = False

    @property
    def description(self) -> str:
        return f"Is {'on or ' if self.inclusive else ''}before"

    @property
    def message(self) -> str:
        return (
            f"The answer must be {'on or ' if self.inclusive else ''}before "
            + f"{format_date_short(self.latest_value) if not self.referenced_question.approximate_date else format_date_approximate(self.latest_value)}"  # noqa: E501
        )

    @property
    def statement(self) -> str:
        return (
            f"{self.safe_qid} <{'=' if self.inclusive else ''} date({self.latest_value.year}, "
            f"{self.latest_value.month}, {self.latest_value.day})"
        )

    @staticmethod
    def get_form_fields(
        referenced_question: "Question", expression: TOptional["Expression"] = None
    ) -> dict[str, "Field"]:
        return {
            "latest_value": DateField(
                "Enter the date which this answer must come before",
                default=datetime.datetime.strptime(cast(str, expression.context["latest_value"]), "%Y-%m-%d").date()
                if expression
                else None,
                widget=GovDateInput() if not referenced_question.approximate_date else MHCLGApproximateDateInput(),
                validators=[Optional()],
                format=["%d %m %Y", "%d %b %Y", "%d %B %Y"]
                if not referenced_question.approximate_date
                else ["%m %Y", "%b %Y", "%B %Y"],  # multiple formats to help user input
            ),
            "latest_value_inclusive": BooleanField(
                "An answer of exactly the latest date is allowed",
                default=cast(bool, expression.context["inclusive"]) if expression else None,
                widget=GovCheckboxInput(),
            ),
        }

    @staticmethod
    def update_validators(form: "_ManagedExpressionForm") -> None:
        form.latest_value.validators = [DataRequired("Enter the date which this answer must come before")]  # ty: ignore[unresolved-attribute]

    @staticmethod
    def build_from_form(form: "_ManagedExpressionForm", question: "Question") -> "IsBefore":
        return IsBefore(
            question_id=question.id,
            latest_value=form.latest_value.data,  # ty: ignore[unresolved-attribute]
            inclusive=form.latest_value_inclusive.data,  # ty: ignore[unresolved-attribute]
        )

    @property
    def required_functions(self) -> dict[str, Union[Callable[[Any], Any], type[Any]]]:
        return {"date": datetime.date}


@register_managed_expression
class IsAfter(ManagedExpression):
    name: ClassVar[ManagedExpressionsEnum] = ManagedExpressionsEnum.IS_AFTER
    supported_condition_data_types: ClassVar[set[QuestionDataType]] = {QuestionDataType.DATE}
    supported_validator_data_types: ClassVar[set[QuestionDataType]] = {QuestionDataType.DATE}

    _key: ManagedExpressionsEnum = name

    question_id: UUID
    earliest_value: datetime.date
    inclusive: bool = False

    @property
    def description(self) -> str:
        return f"Is {'on or ' if self.inclusive else ''}after"

    @property
    def message(self) -> str:
        return (
            f"The answer must be {'on or ' if self.inclusive else ''}after "
            + f"{format_date_short(self.earliest_value) if not self.referenced_question.approximate_date else format_date_approximate(self.earliest_value)}"  # noqa: E501
        )

    @property
    def statement(self) -> str:
        return (
            f"{self.safe_qid} >{'=' if self.inclusive else ''} date({self.earliest_value.year}, "
            f"{self.earliest_value.month}, {self.earliest_value.day})"
        )

    @staticmethod
    def get_form_fields(
        referenced_question: "Question", expression: TOptional["Expression"] = None
    ) -> dict[str, "Field"]:
        return {
            "earliest_value": DateField(
                "Enter the date which this answer must come after",
                default=datetime.datetime.strptime(cast(str, expression.context["earliest_value"]), "%Y-%m-%d").date()  # noqa: E501
                if expression
                else None,
                widget=GovDateInput() if not referenced_question.approximate_date else MHCLGApproximateDateInput(),
                validators=[Optional()],
                format=["%d %m %Y", "%d %b %Y", "%d %B %Y"]
                if not referenced_question.approximate_date
                else ["%m %Y", "%b %Y", "%B %Y"],  # multiple formats to help user input
            ),
            "earliest_value_inclusive": BooleanField(
                "An answer of exactly the earliest date is allowed",
                default=cast(bool, expression.context["inclusive"]) if expression else None,
                widget=GovCheckboxInput(),
            ),
        }

    @staticmethod
    def update_validators(form: "_ManagedExpressionForm") -> None:
        form.earliest_value.validators = [InputRequired("Enter the date which this answer must come after")]  # ty: ignore[unresolved-attribute]

    @staticmethod
    def build_from_form(form: "_ManagedExpressionForm", question: "Question") -> "IsAfter":
        return IsAfter(
            question_id=question.id,
            earliest_value=form.earliest_value.data,  # ty: ignore[unresolved-attribute]
            inclusive=form.earliest_value_inclusive.data,  # ty: ignore[unresolved-attribute]
        )

    @property
    def required_functions(self) -> dict[str, Union[Callable[[Any], Any], type[Any]]]:
        return {"date": datetime.date}


@register_managed_expression
class BetweenDates(ManagedExpression):
    name: ClassVar[ManagedExpressionsEnum] = ManagedExpressionsEnum.BETWEEN_DATES
    supported_condition_data_types: ClassVar[set[QuestionDataType]] = {QuestionDataType.DATE}
    supported_validator_data_types: ClassVar[set[QuestionDataType]] = {QuestionDataType.DATE}

    _key: ManagedExpressionsEnum = name

    question_id: UUID
    earliest_value: datetime.date
    earliest_inclusive: bool = False
    latest_value: datetime.date
    latest_inclusive: bool = False

    @property
    def description(self) -> str:
        return "Is between"

    @property
    def message(self) -> str:
        # todo: optionally include the question name in the default message
        # todo: do you allow the form builder to override this if they need to
        #       - does that persist in the context (inherited from ManagedExpression) or as a separate
        #         property on the model
        # todo: make this use expression evaluation/interpolation rather than f-strings
        return (
            "The answer must be between "
            f"{format_date_short(self.earliest_value) if not self.referenced_question.approximate_date else format_date_approximate(self.earliest_value)}"  # noqa: E501
            f"{' (inclusive)' if self.earliest_inclusive else ' (exclusive)'}"
            f" and {format_date_short(self.latest_value) if not self.referenced_question.approximate_date else format_date_approximate(self.latest_value)}"  # noqa: E501
            f"{' (inclusive)' if self.latest_inclusive else ' (exclusive)'}"
        )

    @property
    def statement(self) -> str:
        # todo: do you refer to the question by ID or slugs - pros and cons - discuss - by the end of the epic
        return (
            f"date({self.earliest_value.year}, {self.earliest_value.month}, {self.earliest_value.day}) "
            f"<{'=' if self.earliest_inclusive else ''} "
            f"{self.safe_qid} "
            f"<{'=' if self.latest_inclusive else ''} "
            f"date({self.latest_value.year}, {self.latest_value.month}, {self.latest_value.day})"
        )

    @staticmethod
    def get_form_fields(
        referenced_question: "Question", expression: TOptional["Expression"] = None
    ) -> dict[str, "Field"]:
        return {
            "between_bottom_of_range": DateField(
                "Earliest date",
                default=datetime.datetime.strptime(cast(str, expression.context["earliest_value"]), "%Y-%m-%d").date()  # noqa: E501
                if expression
                else None,
                widget=GovDateInput() if not referenced_question.approximate_date else MHCLGApproximateDateInput(),
                validators=[Optional()],
                format=["%d %m %Y", "%d %b %Y", "%d %B %Y"]
                if not referenced_question.approximate_date
                else ["%m %Y", "%b %Y", "%B %Y"],  # multiple formats to help user input
            ),
            "between_bottom_inclusive": BooleanField(
                "An answer of exactly the earliest date is allowed",
                default=cast(bool, expression.context["earliest_inclusive"]) if expression else None,
                widget=GovCheckboxInput(),
            ),
            "between_top_of_range": DateField(
                "Latest date",
                default=datetime.datetime.strptime(cast(str, expression.context["latest_value"]), "%Y-%m-%d").date()
                if expression
                else None,
                widget=GovDateInput() if not referenced_question.approximate_date else MHCLGApproximateDateInput(),
                validators=[Optional()],
                format=["%d %m %Y", "%d %b %Y", "%d %B %Y"]
                if not referenced_question.approximate_date
                else ["%m %Y", "%b %Y", "%B %Y"],  # multiple formats to help user input
            ),
            "between_top_inclusive": BooleanField(
                "An answer of exactly the latest date is allowed",
                default=cast(bool, expression.context["latest_inclusive"]) if expression else None,
                widget=GovCheckboxInput(),
            ),
        }

    @staticmethod
    def update_validators(form: "_ManagedExpressionForm") -> None:
        form.between_bottom_of_range.validators = [  # ty: ignore[unresolved-attribute]
            InputRequired("Enter the earliest date allowed for this question"),
            BottomOfRangeIsLower("The earliest date must be before the latest date"),
        ]
        form.between_top_of_range.validators = [  # ty: ignore[unresolved-attribute]
            InputRequired("Enter the latest date allowed for this question"),
            BottomOfRangeIsLower("The latest date must be after the earliest date"),
        ]

    @staticmethod
    def build_from_form(form: "_ManagedExpressionForm", question: "Question") -> "BetweenDates":
        return BetweenDates(
            question_id=question.id,
            earliest_value=form.between_bottom_of_range.data,  # ty: ignore[unresolved-attribute]
            earliest_inclusive=form.between_bottom_inclusive.data,  # ty: ignore[unresolved-attribute]
            latest_value=form.between_top_of_range.data,  # ty: ignore[unresolved-attribute]
            latest_inclusive=form.between_top_inclusive.data,  # ty: ignore[unresolved-attribute]
        )

    @property
    def required_functions(self) -> dict[str, Union[Callable[[Any], Any], type[Any]]]:
        return {"date": datetime.date}


def get_managed_expression(expression: "Expression") -> ManagedExpression:
    if not expression.managed_name:
        raise ValueError(f"Expression {expression.id} is not a managed expression.")

    ExpressionType = TypeAdapter(lookup_managed_expression(expression.managed_name))

    # TODO: for AnyOf, do we want to pull the list of items from the DB rather than denormalising into the `context`
    #       blob? We need to have hardlink references between expressions and the radio items they rely on first (this
    #       would be done in FSPT-673).
    return ExpressionType.validate_python(expression.context)
