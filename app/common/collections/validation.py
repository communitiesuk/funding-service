from typing import TYPE_CHECKING, cast

from flask import current_app

from app.common.collections.types import NOT_ANSWERED
from app.common.data.models import Group
from app.common.exceptions import SubmissionValidationFailed, ValidationError
from app.common.expressions import (
    DisallowedExpression,
    UndefinedFunctionInExpression,
    UndefinedOperatorInExpression,
    UndefinedVariableInExpression,
    evaluate,
    interpolate,
)
from app.metrics import MetricEventName, emit_metric_count

if TYPE_CHECKING:
    from app.common.data.models import Component, Form, Question
    from app.common.helpers.collections import SubmissionHelper


class SubmissionValidator:
    def __init__(self, submission_helper: SubmissionHelper):
        self.helper = submission_helper

    def validate_all_reachable_questions(self) -> None:
        errors = []

        for form in self.helper.get_ordered_visible_forms():
            errors.extend(self._validate_form(form))

        if errors:
            emit_metric_count(
                MetricEventName.SUBMISSION_BLOCKED_BY_INVALID_ANSWERS, 1, submission=self.helper.submission
            )
            raise SubmissionValidationFailed(
                f"Could not submit submission id={self.helper.submission.id} because some answers are no longer valid.",
                errors=errors,
            )

    def _validate_form(self, form: Form) -> list[ValidationError]:
        errors = []
        processed_add_another_containers = []
        processed_groups: set = set()

        for component in form.cached_all_components:
            if isinstance(component, Group):
                if (
                    component.validations
                    and component.add_another_container is None
                    and component.id not in processed_groups
                ):
                    processed_groups.add(component.id)
                    errors.extend(self._validate_group(component, form))
                continue

            question = component
            if question.add_another_container:
                if question.add_another_container.id in processed_add_another_containers:
                    continue

                errors.extend(self._validate_add_another_container(question.add_another_container, form))
                processed_add_another_containers.append(question.add_another_container.id)

            else:
                if self.helper.is_component_visible(question, self.helper.cached_evaluation_context):
                    answer = self.helper.cached_get_answer_for_question(question.id)
                    if answer is not None and answer != NOT_ANSWERED:
                        errors.extend(self._validate_question(cast("Question", question), form))

        return errors

    def _validate_group(self, group: Group, form: Form, add_another_index: int | None = None) -> list[ValidationError]:
        errors: list[ValidationError] = []

        if not self.helper.is_component_visible(
            group, self.helper.cached_evaluation_context, add_another_index=add_another_index
        ):
            return errors

        if (add_another_index is not None and not group.add_another_container) or (
            add_another_index is None and group.add_another_container
        ):
            raise ValueError(f"Cannot validate {group.add_another=} {group=} with {add_another_index=}")

        if add_another_index is not None:
            evaluation_context = self.helper.cached_evaluation_context.with_add_another_context(
                group, self.helper.submission.data_manager, add_another_index=add_another_index, mode="evaluation"
            ).with_default_context(self.helper)
            interpolation_context = self.helper.cached_interpolation_context.with_add_another_context(
                group, self.helper.submission.data_manager, add_another_index=add_another_index, mode="interpolation"
            )
        else:
            evaluation_context = self.helper.cached_evaluation_context.with_default_context(self.helper)
            interpolation_context = self.helper.cached_interpolation_context

        for validation_expr in group.validations:
            try:
                if not evaluate(expression=validation_expr, context=evaluation_context):
                    error_message = interpolate(
                        validation_expr.evaluatable_expression.message, context=interpolation_context
                    )
                    errors.append(
                        ValidationError(
                            question_id=group.id,
                            question_name=group.name,
                            form_id=form.id,
                            form_title=form.title,
                            error_message=error_message,
                            answer=None,
                        )
                    )
                    return errors
            except (
                UndefinedVariableInExpression,
                DisallowedExpression,
                UndefinedFunctionInExpression,
                UndefinedOperatorInExpression,
            ) as e:
                current_app.logger.error(
                    "%(exception_name)s in group validation for group %(gid)s (form %(fid)s)",
                    dict(exception_name=e.__class__.__name__, gid=group.id, fid=form.id),
                )

        return errors

    def _validate_question(
        self, question: Question, form: Form, add_another_index: int | None = None
    ) -> list[ValidationError]:
        errors: list[ValidationError] = []

        if not question.validations:
            return errors

        evaluation_context = self.helper.cached_evaluation_context.with_default_context(self.helper)
        if add_another_index is not None and question.add_another_container:
            evaluation_context = evaluation_context.with_add_another_context(
                question.add_another_container,
                data_manager=self.helper.submission.data_manager,
                add_another_index=add_another_index,
                mode="evaluation",
            )

        for validation_expr in question.validations:
            try:
                if not evaluate(expression=validation_expr, context=evaluation_context):
                    error_message = interpolate(
                        validation_expr.evaluatable_expression.message, context=self.helper.cached_interpolation_context
                    )
                    errors.append(
                        ValidationError(
                            question_id=question.id,
                            question_name=question.name,
                            form_id=form.id,
                            form_title=form.title,
                            error_message=error_message,
                            answer=self.helper.cached_get_answer_for_question(
                                question.id, add_another_index=add_another_index
                            ),
                            add_another_index=add_another_index,
                        )
                    )
            except (
                UndefinedVariableInExpression,
                DisallowedExpression,
                UndefinedFunctionInExpression,
                UndefinedOperatorInExpression,
            ) as e:
                current_app.logger.error(
                    "%(exception_name)s in validation for question %(qid)s (form %(fid)s)",
                    dict(exception_name=e.__class__.__name__, qid=question.id, fid=form.id),
                )

        return errors

    def _validate_add_another_container(self, container: Component, form: Form) -> list[ValidationError]:
        errors = []
        container = cast("Group | Question", container)

        count = self.helper.get_count_for_add_another(container)
        for index in range(count):
            questions = (
                cast("Group", container).cached_questions if container.is_group else [cast("Question", container)]
            )

            for q in questions:
                if self.helper.is_component_visible(q, self.helper.cached_evaluation_context, add_another_index=index):
                    answer = self.helper.cached_get_answer_for_question(q.id, add_another_index=index)
                    if answer is not None and answer != NOT_ANSWERED:
                        errors.extend(self._validate_question(q, form, add_another_index=index))

            if container.is_group:
                for group in set(cast(Group, container).cached_all_components).union({container}):
                    if group.is_group:
                        group = cast(Group, group)
                        if group.validations and group.add_another_container is not None:
                            errors.extend(self._validate_group(group, form, add_another_index=index))
                        continue

        return errors
