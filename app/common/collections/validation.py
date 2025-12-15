from typing import TYPE_CHECKING, cast

from flask import current_app

from app.common.collections.types import NOT_ANSWERED
from app.common.exceptions import SubmissionValidationFailed, ValidationError
from app.common.expressions import UndefinedVariableInExpression, evaluate, interpolate
from app.metrics import MetricEventName, emit_metric_count

if TYPE_CHECKING:
    from app.common.data.models import Component, Form, Group, Question
    from app.common.helpers.collections import SubmissionHelper


class SubmissionValidator:
    def __init__(self, submission_helper: "SubmissionHelper"):
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

    def _validate_form(self, form: "Form") -> list[ValidationError]:
        errors = []
        processed_add_another_containers = []

        for question in form.cached_questions:
            if question.add_another_container:
                if question.add_another_container.id in processed_add_another_containers:
                    continue

                errors.extend(self._validate_add_another_container(question.add_another_container, form))
                processed_add_another_containers.append(question.add_another_container.id)

            else:
                if self.helper.is_component_visible(question, self.helper.cached_evaluation_context):
                    answer = self.helper.cached_get_answer_for_question(question.id)
                    if answer is not None and answer != NOT_ANSWERED:
                        errors.extend(self._validate_question(question, form))

        return errors

    def _validate_question(
        self, question: "Question", form: "Form", add_another_index: int | None = None
    ) -> list[ValidationError]:
        errors: list[ValidationError] = []

        if not question.validations:
            return errors

        context = self.helper.cached_evaluation_context
        if add_another_index is not None and question.add_another_container:
            context = context.with_add_another_context(
                question.add_another_container, submission_helper=self.helper, add_another_index=add_another_index
            )

        for validation_expr in question.validations:
            if not validation_expr.managed:
                raise RuntimeError(f"Unmanaged validation not supported: {validation_expr.id}")

            try:
                if not evaluate(expression=validation_expr, context=context):
                    error_message = interpolate(
                        validation_expr.managed.message, context=self.helper.cached_interpolation_context
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
            except UndefinedVariableInExpression:
                current_app.logger.warning(
                    "Undefined variable in validation for question %(qid)s (form %(fid)s)",
                    dict(qid=question.id, fid=form.id),
                )

        return errors

    def _validate_add_another_container(self, container: "Component", form: "Form") -> list[ValidationError]:
        errors = []
        container = cast("Group | Question", container)

        count = self.helper.get_count_for_add_another(container)
        for index in range(count):
            context = self.helper.cached_evaluation_context.with_add_another_context(
                container, submission_helper=self.helper, add_another_index=index
            )

            questions = (
                cast("Group", container).cached_questions if container.is_group else [cast("Question", container)]
            )

            for q in questions:
                if self.helper.is_component_visible(q, context):
                    answer = self.helper.cached_get_answer_for_question(q.id, add_another_index=index)
                    if answer is not None and answer != NOT_ANSWERED:
                        errors.extend(self._validate_question(q, form, add_another_index=index))

        return errors
