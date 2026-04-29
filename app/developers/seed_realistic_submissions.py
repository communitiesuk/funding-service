"""Seed one valid TEST submission for each grant recipient on a collection.

Generates submission data using `hypothesis.strategies` constrained by each question's
managed validators. Walks `forms[order]` -> `components[order]` to mirror form-runner
ordering. Skips grant recipients that already have a submission.
"""

from __future__ import annotations

import dataclasses
import datetime
import random
import uuid
import warnings
from decimal import Decimal
from typing import Any, cast

from hypothesis.errors import NonInteractiveExampleWarning
from hypothesis.strategies import (
    SearchStrategy,
    booleans,
    characters,
    dates,
    decimals,
    emails,
    from_regex,
    integers,
    just,
    lists,
    sampled_from,
    text,
)

from app.common.collections.types import (
    DateAnswer,
    DecimalAnswer,
    EmailAnswer,
    FileUploadAnswer,
    IntegerAnswer,
    MultipleChoiceFromListAnswer,
    SingleChoiceFromListAnswer,
    TextMultiLineAnswer,
    TextSingleLineAnswer,
    UrlAnswer,
    YesNoAnswer,
)
from app.common.collections.validation import SubmissionValidator
from app.common.data.interfaces.collections import (
    create_submission,
    get_collection,
    get_submissions_by_grant_recipient_collection,
    update_submission_data,
)
from app.common.data.interfaces.grant_recipients import get_grant_recipients
from app.common.data.interfaces.user import add_permissions_to_user, upsert_user_by_email
from app.common.data.models import (
    Component,
    GrantRecipient,
    Group,
    Question,
)
from app.common.data.models_user import User
from app.common.data.submission_data_manager import SubmissionDataAddAnotherIndexInvalid
from app.common.data.types import (
    GrantRecipientModeEnum,
    ManagedExpressionsEnum,
    NumberTypeEnum,
    QuestionDataType,
    RoleEnum,
    SubmissionModeEnum,
)
from app.common.exceptions import SubmissionValidationFailed
from app.common.expressions.managed import (
    Between,
    BetweenDates,
    GreaterThan,
    IsAfter,
    IsBefore,
    LessThan,
)
from app.common.helpers.collections import SubmissionHelper
from app.extensions import db

# A fixed valid file-upload payload. We don't actually upload anything to S3; the validator
# only inspects the answer shape. `key` is stable per submission so the JSON dedupes nicely.
FILE_UPLOAD_STUB_FILENAME = "stub.pdf"
FILE_UPLOAD_STUB_MIME_TYPE = "application/pdf"
FILE_UPLOAD_STUB_SIZE = 1024

_TEXT_ALPHABET = characters(min_codepoint=0x20, max_codepoint=0x7E)


@dataclasses.dataclass
class SeedFailure:
    grant_recipient_id: uuid.UUID
    submission_reference: str | None
    error: str


@dataclasses.dataclass
class SeedReport:
    created: int = 0
    submitted: int = 0
    skipped: int = 0
    failed: int = 0
    failures: list[SeedFailure] = dataclasses.field(default_factory=list)


def seed_realistic_submissions(
    collection_id: uuid.UUID,
    *,
    user: User | None = None,
    new_user_per_submission: bool = False,
    max_submissions: int = 1,
    per_gr_attempts: int = 5,
    submit_percentage: float = 0.0,
    seed: int | None = None,
) -> SeedReport:
    """Create up to `max_submissions` TEST submissions for TEST grant recipients on `collection_id`.

    Each GR is retried up to `per_gr_attempts` times before giving up and moving on to the next GR.

    Pass `user` to record the same user as `created_by` for every submission, or set
    `new_user_per_submission` to create a fresh random user as `created_by` for each one.

    Every section is marked as complete. `submit_percentage` (0-100) is the chance that each
    created submission is also submitted.
    """
    if seed is not None:
        random.seed(seed)

    if not new_user_per_submission and user is None:
        raise ValueError("`user` is required unless `new_user_per_submission` is set")

    collection = get_collection(collection_id, with_full_schema=True)
    grant_recipients = get_grant_recipients(collection.grant, mode=GrantRecipientModeEnum.TEST, with_organisations=True)

    report = SeedReport()
    for gr in grant_recipients:
        if report.created >= max_submissions:
            break

        if get_submissions_by_grant_recipient_collection(gr, collection.id):
            report.skipped += 1
            continue

        submission_user = _create_random_user() if new_user_per_submission else user
        assert submission_user is not None

        add_permissions_to_user(
            user=submission_user,
            permissions=[RoleEnum.DATA_PROVIDER],
            organisation_id=gr.organisation_id,
            grant_id=gr.grant_id,
        )

        should_submit = random.uniform(0, 100) < submit_percentage
        _attempt_submission_for_gr(collection, submission_user, gr, per_gr_attempts, should_submit, report)

    return report


def _create_random_user() -> User:
    suffix = "%032x" % random.getrandbits(128)
    return upsert_user_by_email(f"seed-{suffix}@example.com", name=f"Seeded User {suffix[:8]}")


def _attempt_submission_for_gr(
    collection: Any,
    user: User,
    gr: GrantRecipient,
    per_gr_attempts: int,
    should_submit: bool,
    report: SeedReport,
) -> bool:
    """Try to create a valid submission for `gr`, retrying with a fresh submission each attempt.

    On success every section is marked as complete, and the submission is submitted when
    `should_submit` is set. Returns True on success (and increments `report.created`, plus
    `report.submitted` when submitted), False on exhaustion (and appends a `SeedFailure`).
    """
    last_failure: SeedFailure | None = None
    for _ in range(per_gr_attempts):
        submission = create_submission(
            collection=collection,
            created_by=user,
            mode=SubmissionModeEnum.TEST,
            grant_recipient=gr,
        )
        try:
            _populate_submission(submission)
            _retry_until_valid(submission, attempts=4)
            _complete_sections(submission, user)
            if should_submit:
                SubmissionHelper(submission).submit(user)
            db.session.commit()
            report.created += 1
            if should_submit:
                report.submitted += 1
            return True
        except SubmissionValidationFailed as exc:
            db.session.rollback()
            error_messages = "; ".join(f"{e.question_name}: {e.error_message}" for e in exc.errors)
            last_failure = SeedFailure(
                grant_recipient_id=gr.id,
                submission_reference=submission.reference,
                error=error_messages or str(exc),
            )
        except Exception as exc:
            db.session.rollback()
            last_failure = SeedFailure(
                grant_recipient_id=gr.id,
                submission_reference=submission.reference,
                error=f"{type(exc).__name__}: {exc}",
            )

    assert last_failure is not None
    report.failed += 1
    report.failures.append(last_failure)
    return False


def _populate_submission(submission: Any) -> None:
    helper = SubmissionHelper(submission)
    for form in helper.collection.forms:
        for component in form.components:
            _answer_component(component, helper)


def _complete_sections(submission: Any, user: User) -> None:
    """Mark every section (form) on the submission as complete via a FORM_RUNNER_FORM_COMPLETED event."""
    helper = SubmissionHelper(submission)
    for form in helper.collection.forms:
        helper.toggle_form_completed(form, user, is_complete=True)


def _retry_until_valid(submission: Any, *, attempts: int) -> None:
    """Re-draw answers for any questions that fail validation, then re-run the validator. Repeats up to `attempts`.

    Cross-form `*_expression` validators only see the referenced answer once it's been generated. The first
    pass walks form order, so if Q_X depends on Q_Y on a later form, Q_X is drawn unbounded. After the first
    pass every question has an answer, so a re-draw of Q_X resolves its bound against Q_Y's actual value.
    """
    last_exc: SubmissionValidationFailed | None = None
    for _ in range(attempts):
        update_submission_data(submission)
        helper = SubmissionHelper(submission)
        try:
            SubmissionValidator(helper).validate_all_reachable_questions()
            return
        except SubmissionValidationFailed as exc:
            last_exc = exc
            for error in exc.errors:
                question = helper.get_question(error.question_id)
                _set_answer(question, helper, add_another_index=error.add_another_index)
    assert last_exc is not None
    raise last_exc


def _answer_component(component: Component, helper: SubmissionHelper, *, add_another_index: int | None = None) -> None:
    if component.add_another:
        # The container's own visibility is judged at the outer scope (no inner index yet).
        if not _is_visible(helper, component, None):
            return
        count = random.randint(1, 3)
        for index in range(count):
            if isinstance(component, Group):
                for child in component.components:
                    _answer_component(child, helper, add_another_index=index)
            else:
                assert isinstance(component, Question)
                _set_answer(component, helper, add_another_index=index)
        return

    if not _is_visible(helper, component, add_another_index):
        return

    if isinstance(component, Group):
        for child in component.components:
            _answer_component(child, helper, add_another_index=add_another_index)
        return

    assert isinstance(component, Question)
    _set_answer(component, helper, add_another_index=add_another_index)


def _set_answer(question: Question, helper: SubmissionHelper, *, add_another_index: int | None) -> None:
    answer = _draw_answer(question, helper, add_another_index=add_another_index)
    helper.submission.data_manager.set(question, answer, add_another_index=add_another_index)
    _invalidate_helper_caches(helper)


def _is_visible(helper: SubmissionHelper, component: Component, add_another_index: int | None) -> bool:
    return helper.is_component_visible(component, helper.cached_evaluation_context, add_another_index=add_another_index)


def _invalidate_helper_caches(helper: SubmissionHelper) -> None:
    helper.cached_get_answer_for_question.cache_clear()
    helper.cached_get_all_questions_are_answered_for_form.cache_clear()
    helper.cached_get_ordered_visible_questions.cache_clear()
    if "cached_evaluation_context" in helper.__dict__:
        del helper.cached_evaluation_context
    if "cached_interpolation_context" in helper.__dict__:
        del helper.cached_interpolation_context


def _draw_answer(question: Question, helper: SubmissionHelper, *, add_another_index: int | None = None) -> Any:
    match question.data_type:
        case QuestionDataType.TEXT_SINGLE_LINE:
            return TextSingleLineAnswer(_draw(_text_single_line_strategy(question)))
        case QuestionDataType.TEXT_MULTI_LINE:
            return TextMultiLineAnswer(_draw(_text_multi_line_strategy(question)))
        case QuestionDataType.EMAIL:
            return EmailAnswer(_draw(emails(domains=just("example.com"))))
        case QuestionDataType.URL:
            return UrlAnswer(_draw(from_regex(r"https://example\.com/[a-z]{3,10}", fullmatch=True)))
        case QuestionDataType.NUMBER:
            return _draw_number_answer(question, helper, add_another_index)
        case QuestionDataType.YES_NO:
            return YesNoAnswer(_draw(booleans()))
        case QuestionDataType.RADIOS:
            assert question.data_source is not None
            item = _draw(sampled_from(question.data_source.items))
            return SingleChoiceFromListAnswer(key=item.key, label=item.label)
        case QuestionDataType.CHECKBOXES:
            assert question.data_source is not None
            items = question.data_source.items
            chosen = _draw(lists(sampled_from(items), min_size=1, max_size=len(items), unique_by=lambda i: i.key))
            return MultipleChoiceFromListAnswer(choices=[{"key": i.key, "label": i.label} for i in chosen])
        case QuestionDataType.DATE:
            return _draw_date_answer(question, helper, add_another_index)
        case QuestionDataType.FILE_UPLOAD:
            stub_key = f"stubs/{uuid.uuid4()}/{FILE_UPLOAD_STUB_FILENAME}"
            return FileUploadAnswer(
                filename=FILE_UPLOAD_STUB_FILENAME,
                key=stub_key,
                size=FILE_UPLOAD_STUB_SIZE,
                mime_type=FILE_UPLOAD_STUB_MIME_TYPE,
                scanned_for_viruses=True,
            )

    raise ValueError(f"No strategy for question data_type={question.data_type}")


def _text_single_line_strategy(question: Question) -> SearchStrategy[str]:
    if any(_managed_name(v) == ManagedExpressionsEnum.UK_POSTCODE for v in question.validations):
        return from_regex(r"^([A-Z]{1,2}(?:\d[A-Z]|\d{1,2}))\s*(\d[A-Z]{2})$", fullmatch=True)
    return text(alphabet=_TEXT_ALPHABET, min_size=1, max_size=200).filter(lambda s: bool(s.strip()))


def _text_multi_line_strategy(question: Question) -> SearchStrategy[str]:
    word_limit = question.word_limit
    max_chars = word_limit * 6 if word_limit else 1000
    return text(alphabet=_TEXT_ALPHABET, min_size=1, max_size=max(20, min(max_chars, 1000))).filter(
        lambda s: bool(s.strip())
    )


def _draw_number_answer(question: Question, helper: SubmissionHelper, add_another_index: int | None) -> Any:
    minimum, maximum, min_inclusive, max_inclusive = _resolve_number_bounds(question, helper, add_another_index)
    is_decimal = question.data_options.number_type == NumberTypeEnum.DECIMAL

    if is_decimal:
        places = question.data_options.max_decimal_places or 2
        adjusted_min = minimum
        adjusted_max = maximum
        strategy = decimals(
            min_value=adjusted_min,
            max_value=adjusted_max,
            allow_infinity=False,
            allow_nan=False,
            places=places,
        )
        if minimum is not None and not min_inclusive:
            strategy = strategy.filter(lambda v: v > minimum)
        if maximum is not None and not max_inclusive:
            strategy = strategy.filter(lambda v: v < maximum)
        value = _draw(strategy)
        return DecimalAnswer(value=Decimal(value))

    int_min = int(minimum) if minimum is not None else None
    int_max = int(maximum) if maximum is not None else None
    if int_min is not None and not min_inclusive:
        int_min += 1
    if int_max is not None and not max_inclusive:
        int_max -= 1
    if int_min is None:
        int_min = 0
    if int_max is None:
        int_max = max(int_min + 100, 100)
    if int_min > int_max:
        int_min, int_max = int_max, int_min
    value = _draw(integers(min_value=int_min, max_value=int_max))
    return IntegerAnswer(value=value)


def _draw_date_answer(question: Question, helper: SubmissionHelper, add_another_index: int | None) -> Any:
    earliest, latest, earliest_inclusive, latest_inclusive = _resolve_date_bounds(question, helper, add_another_index)
    if earliest is None:
        earliest = datetime.date(2000, 1, 1)
    if latest is None:
        latest = datetime.date(2050, 12, 31)
    if not earliest_inclusive:
        earliest = earliest + datetime.timedelta(days=1)
    if not latest_inclusive:
        latest = latest - datetime.timedelta(days=1)
    if earliest > latest:
        earliest, latest = latest, earliest
    value = _draw(dates(min_value=earliest, max_value=latest))
    return DateAnswer(answer=value, approximate_date=bool(question.approximate_date))


def _resolve_number_bounds(
    question: Question, helper: SubmissionHelper, add_another_index: int | None
) -> tuple[Decimal | None, Decimal | None, bool, bool]:
    min_value: Decimal | None = None
    max_value: Decimal | None = None
    min_inclusive = True
    max_inclusive = True

    for expr in question.validations:
        if not expr.is_managed:
            continue
        managed = expr.managed
        if isinstance(managed, GreaterThan):
            bound = _resolve_bound_value(
                managed.minimum_value, managed.minimum_expression, helper, question, add_another_index
            )
            if bound is not None:
                min_value, min_inclusive = bound, managed.inclusive
        elif isinstance(managed, LessThan):
            bound = _resolve_bound_value(
                managed.maximum_value, managed.maximum_expression, helper, question, add_another_index
            )
            if bound is not None:
                max_value, max_inclusive = bound, managed.inclusive
        elif isinstance(managed, Between):
            low = _resolve_bound_value(
                managed.minimum_value, managed.minimum_expression, helper, question, add_another_index
            )
            high = _resolve_bound_value(
                managed.maximum_value, managed.maximum_expression, helper, question, add_another_index
            )
            if low is not None:
                min_value, min_inclusive = low, managed.minimum_inclusive
            if high is not None:
                max_value, max_inclusive = high, managed.maximum_inclusive

    return min_value, max_value, min_inclusive, max_inclusive


def _resolve_date_bounds(
    question: Question, helper: SubmissionHelper, add_another_index: int | None
) -> tuple[datetime.date | None, datetime.date | None, bool, bool]:
    earliest: datetime.date | None = None
    latest: datetime.date | None = None
    earliest_inclusive = True
    latest_inclusive = True

    for expr in question.validations:
        if not expr.is_managed:
            continue
        managed = expr.managed
        if isinstance(managed, IsAfter):
            bound = _resolve_date_bound(
                managed.earliest_value, managed.earliest_expression, helper, question, add_another_index
            )
            if bound is not None:
                earliest, earliest_inclusive = bound, managed.inclusive
        elif isinstance(managed, IsBefore):
            bound = _resolve_date_bound(
                managed.latest_value, managed.latest_expression, helper, question, add_another_index
            )
            if bound is not None:
                latest, latest_inclusive = bound, managed.inclusive
        elif isinstance(managed, BetweenDates):
            low = _resolve_date_bound(
                managed.earliest_value, managed.earliest_expression, helper, question, add_another_index
            )
            high = _resolve_date_bound(
                managed.latest_value, managed.latest_expression, helper, question, add_another_index
            )
            if low is not None:
                earliest, earliest_inclusive = low, managed.earliest_inclusive
            if high is not None:
                latest, latest_inclusive = high, managed.latest_inclusive

    return earliest, latest, earliest_inclusive, latest_inclusive


def _resolve_bound_value(
    literal: Any,
    ref: Any,
    helper: SubmissionHelper,
    subject: Question,
    subject_add_another_index: int | None,
) -> Decimal | None:
    answer = _resolve_referenced_answer(literal, ref, helper, subject, subject_add_another_index)
    if answer is None:
        return _decimal_or_none(literal)
    return Decimal(str(answer.get_value_for_evaluation()))


def _resolve_date_bound(
    literal: Any,
    ref: Any,
    helper: SubmissionHelper,
    subject: Question,
    subject_add_another_index: int | None,
) -> datetime.date | None:
    answer = _resolve_referenced_answer(literal, ref, helper, subject, subject_add_another_index)
    if answer is None:
        return literal if isinstance(literal, datetime.date) else None
    return cast(datetime.date, answer.get_value_for_evaluation())


def _resolve_referenced_answer(
    literal: Any,
    ref: Any,
    helper: SubmissionHelper,
    subject: Question,
    subject_add_another_index: int | None,
) -> Any:
    """Mirror the validator's resolution rules for a managed expression's `*_expression` reference.

    Returns the referenced question's `Answer` (or None), so callers can apply a per-type cast.
    Returns None if the reference can't be resolved against the current submission state.
    """
    if literal is not None:
        return None
    if ref is None or ref.question_id is None:
        return None

    referenced = helper.get_question(ref.question_id)
    referenced_container = referenced.add_another_container
    subject_container = subject.add_another_container

    if referenced_container is None:
        # Plain question -> just look it up.
        try:
            return helper.cached_get_answer_for_question(ref.question_id)
        except SubmissionDataAddAnotherIndexInvalid:
            return None

    if referenced_container == subject_container and subject_add_another_index is not None:
        # Same add-another container as the subject -> per-index lookup, matching `with_add_another_context`.
        try:
            return helper.submission.data_manager.get(referenced, add_another_index=subject_add_another_index)
        except SubmissionDataAddAnotherIndexInvalid:
            return None

    # Cross-container reference: the validator can't resolve this at evaluation time either
    # (see _build_submission_data note about aggregate methods being unsupported), so we don't try.
    return None


def _decimal_or_none(literal: Any) -> Decimal | None:
    if literal is None:
        return None
    return Decimal(str(literal))


def _managed_name(expr: Any) -> ManagedExpressionsEnum | None:
    return expr.managed_name if expr.is_managed else None


def _draw(strategy: SearchStrategy[Any]) -> Any:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NonInteractiveExampleWarning)
        return strategy.example()
