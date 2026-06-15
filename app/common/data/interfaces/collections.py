import datetime
import uuid
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, List, Literal, Never, Protocol, Unpack, overload
from uuid import UUID

from flask import current_app
from sqlalchemy import and_, delete, func, null, or_, select, text
from sqlalchemy.exc import IntegrityError, NoResultFound
from sqlalchemy.orm import joinedload, selectinload

from app.common.data.interfaces.exceptions import (
    CollectionChronologyError,
    DuplicateValueError,
    GrantMustBeLiveError,
    GrantRecipientUsersRequiredError,
    InvalidReferenceInExpression,
    StateTransitionError,
    flush_and_rollback_on_exceptions,
)
from app.common.data.interfaces.grant_recipients import (
    all_grant_recipients_have_data_providers,
    get_grant_recipients,
)
from app.common.data.models import (
    Collection,
    Component,
    ComponentReference,
    DataSource,
    DataSourceItem,
    Expression,
    Form,
    Grant,
    GrantRecipient,
    Group,
    Organisation,
    Question,
    Submission,
    SubmissionEvent,
)
from app.common.data.models_user import User
from app.common.data.types import (
    CollectionStatusEnum,
    CollectionType,
    ConditionsOperator,
    DataSourceType,
    ExpressionType,
    GrantRecipientModeEnum,
    GrantStatusEnum,
    QuestionDataOptions,
    QuestionDataType,
    QuestionPresentationOptions,
    SubmissionEventType,
    SubmissionModeEnum,
    SubmissionStatusEnum,
)
from app.common.data.utils import generate_submission_reference
from app.common.exceptions import WTFormRenderableException
from app.common.expressions import (
    ALLOWED_INTERPOLATION_REGEX,
    INTERPOLATE_REGEX,
    EvaluatableExpression,
    ExpressionContext,
)
from app.common.expressions.managed import BaseDataSourceManagedExpression
from app.common.expressions.references import DataSourceReference, ExpressionReference
from app.common.forms.helpers import (
    components_in_valid_add_another_combination,
)
from app.common.helpers.submission_events import (
    DeclinedByCertifierKwargs,
    ReopenedKwargs,
    SubmissionEventHelper,
)
from app.common.utils import slugify
from app.extensions import db
from app.metrics import MetricAttributeName, MetricEventName, emit_metric_count
from app.types import NOT_PROVIDED, TNotProvided


@flush_and_rollback_on_exceptions(coerce_exceptions=[(IntegrityError, DuplicateValueError)])
def create_collection(*, name: str, user: User, grant: Grant, type_: CollectionType) -> Collection:
    collection = Collection(
        name=name,
        created_by=user,
        grant=grant,
        slug=slugify(name),
        type=type_,
        requires_certification=True,  # note: this'll need to change when we have more than just monitoring reports
    )
    db.session.add(collection)
    return collection


def get_collection(
    collection_id: UUID,
    grant_id: UUID | None = None,
    type_: CollectionType | None = None,
    with_full_schema: bool = False,
) -> Collection:
    """Get a collection by ID."""
    options = []
    if with_full_schema:
        options.extend(
            [
                # get all flat components to drive single batches of selectin
                # joinedload lets us avoid an exponentially increasing number of queries
                joinedload(Collection.forms).selectinload(Form._all_components).selectinload(Component.components),
                # eagerly populate the forms top level components - this is a redundant query but
                # leaves as much as possible with the ORM
                joinedload(Collection.forms).selectinload(Form.components),
            ]
        )

    filters = [Collection.id == collection_id]
    if grant_id:
        filters.append(Collection.grant_id == grant_id)
    if type_:
        filters.append(Collection.type == type_)

    return db.session.scalars(select(Collection).where(*filters).options(*options)).unique().one()


@flush_and_rollback_on_exceptions(coerce_exceptions=[(IntegrityError, DuplicateValueError)])
def update_collection(  # noqa: C901
    collection: Collection,
    *,
    name: str | TNotProvided = NOT_PROVIDED,
    status: CollectionStatusEnum | TNotProvided = NOT_PROVIDED,
    reporting_period_start_date: datetime.date | None | TNotProvided = NOT_PROVIDED,
    reporting_period_end_date: datetime.date | None | TNotProvided = NOT_PROVIDED,
    submission_period_start_date: datetime.date | None | TNotProvided = NOT_PROVIDED,
    submission_period_end_date: datetime.date | None | TNotProvided = NOT_PROVIDED,
    allow_multiple_submissions: bool | TNotProvided = NOT_PROVIDED,
    allow_public_sign_up: bool | TNotProvided = NOT_PROVIDED,
    submission_name_question_id: uuid.UUID | None | TNotProvided = NOT_PROVIDED,
    submission_guidance: str | None | TNotProvided = NOT_PROVIDED,
) -> Collection:
    """Update the various attributes of a collection.

    NOTE: When transitioning a collection's status, this may need to update the status for all of its submissions, eg
    when closing a report to change any unsubmitted submissions statuses to NOT_SUBMITTED.
    """
    if name is not NOT_PROVIDED:
        collection.name = name
        collection.slug = slugify(name)

    if reporting_period_start_date is not NOT_PROVIDED or reporting_period_end_date is not NOT_PROVIDED:
        if (
            (reporting_period_start_date is NOT_PROVIDED or reporting_period_end_date is NOT_PROVIDED)
            or (
                isinstance(reporting_period_start_date, datetime.date)
                != isinstance(reporting_period_end_date, datetime.date)
            )
            or (reporting_period_start_date is None != reporting_period_end_date is None)
        ):  # could be written more concisely but this satisfies type checking
            raise CollectionChronologyError(
                "reporting_period_start_date and reporting_period_end_date must both be unset or both be set"
            )

        if reporting_period_start_date is not None and reporting_period_end_date is not None:
            if reporting_period_start_date >= reporting_period_end_date:
                raise CollectionChronologyError("reporting_period_start_date must be before reporting_period_end_date")

        collection.reporting_period_start_date = reporting_period_start_date
        collection.reporting_period_end_date = reporting_period_end_date

    if submission_period_start_date is not NOT_PROVIDED or submission_period_end_date is not NOT_PROVIDED:
        if (
            (submission_period_start_date is NOT_PROVIDED or submission_period_end_date is NOT_PROVIDED)
            or (
                isinstance(submission_period_start_date, datetime.date)
                != isinstance(submission_period_end_date, datetime.date)
            )
            or (submission_period_start_date is None != submission_period_end_date is None)
        ):  # could be written more concisely but this satisfies type checking
            raise CollectionChronologyError(
                "submission_period_start_date and submission_period_end_date must both be unset or both be set"
            )

        if submission_period_start_date is not None and submission_period_end_date is not None:
            if submission_period_start_date >= submission_period_end_date:
                raise CollectionChronologyError(
                    "submission_period_start_date must be before submission_period_end_date"
                )

        collection.submission_period_start_date = submission_period_start_date
        collection.submission_period_end_date = submission_period_end_date

    if collection.reporting_period_end_date and collection.submission_period_start_date:
        if collection.reporting_period_end_date >= collection.submission_period_start_date:
            raise CollectionChronologyError("reporting_period_end_date must be before submission_period_start_date")

    if allow_multiple_submissions is not NOT_PROVIDED:
        if (
            not allow_multiple_submissions
            and collection.allow_multiple_submissions
            and collection.submission_name_question_id is not None
            and collection.id is not None
        ):
            if len(collection.live_submissions) > 0 or len(collection.test_submissions) > 0:
                raise ValueError(
                    "Cannot disable multiple submissions: submissions already exist for this "
                    f"{collection.type.constants.singular}"
                )

        collection.allow_multiple_submissions = allow_multiple_submissions
        if not allow_multiple_submissions:
            collection.submission_name_question_id = None

    if allow_public_sign_up is not NOT_PROVIDED:
        collection.allow_public_sign_up = allow_public_sign_up

    if submission_name_question_id is not NOT_PROVIDED:
        if not collection.allow_multiple_submissions:
            raise ValueError("submission_name_question_id cannot be set when allow_multiple_submissions is not enabled")

        try:
            if (
                submission_name_question_id
                and not (submission_name_question := get_question_by_id(submission_name_question_id))
                or not submission_name_question.is_question
            ):
                raise ValueError("submission_name_question_id must be a question ID")
        except NoResultFound as e:
            raise ValueError("submission_name_question_id must be a question ID") from e

        collection.submission_name_question_id = submission_name_question_id

    if submission_guidance is not NOT_PROVIDED:
        stripped = submission_guidance.strip() if submission_guidance else None
        collection.submission_guidance = stripped or None

    if status is not NOT_PROVIDED and collection.status != status:
        match (collection.status, status):
            case (CollectionStatusEnum.DRAFT, CollectionStatusEnum.SCHEDULED) | (
                CollectionStatusEnum.SCHEDULED,
                CollectionStatusEnum.OPEN,
            ):
                actioning = "opening" if collection.status == CollectionStatusEnum.SCHEDULED else "scheduling"

                if collection.grant.status != GrantStatusEnum.LIVE:
                    raise GrantMustBeLiveError(
                        f"{collection.grant.name} must be made live before {actioning} a "
                        f"{collection.type.constants.singular}"
                    )

                try:
                    assert collection.submission_period_start_date
                    assert collection.submission_period_end_date
                except AssertionError as e:
                    raise CollectionChronologyError(
                        f"Cannot change {collection.type.constants.singular} status to {status.value}: "
                        "submission period dates must be set"
                    ) from e

                if (collection.reporting_period_start_date or collection.reporting_period_end_date) and not (
                    collection.reporting_period_start_date and collection.reporting_period_end_date
                ):
                    raise CollectionChronologyError(
                        "reporting_period_start_date and reporting_period_end_date must both be unset or both be set"
                    )

                if (
                    collection.reporting_period_start_date
                    and collection.reporting_period_end_date
                    and not (
                        collection.reporting_period_start_date
                        < collection.reporting_period_end_date
                        < collection.submission_period_start_date
                        < collection.submission_period_end_date
                    )
                ):
                    raise CollectionChronologyError("Reporting dates must be chronological and before submission dates")

                if not get_grant_recipients(collection.grant):
                    raise GrantRecipientUsersRequiredError(
                        f"Grant recipients must be set up before {actioning} a {collection.type.constants.singular}"
                    )

                if not all_grant_recipients_have_data_providers(collection.grant):
                    raise GrantRecipientUsersRequiredError(
                        "All grant recipients must have at least one data "
                        f"provider set up before {actioning} a {collection.type.constants.singular}"
                    )

                if status == CollectionStatusEnum.OPEN:
                    if datetime.datetime.now(datetime.UTC) < datetime.datetime.combine(
                        collection.submission_period_start_date, datetime.time.min, tzinfo=datetime.UTC
                    ):
                        raise CollectionChronologyError(
                            f"You cannot open the {collection.type.constants.singular} for submissions before "
                            f"the submission period start date of {collection.submission_period_start_date}"
                        )

            case (
                CollectionStatusEnum.SCHEDULED,
                CollectionStatusEnum.DRAFT,
            ):
                pass
            case (
                CollectionStatusEnum.OPEN,
                CollectionStatusEnum.CLOSED,
            ):
                assert collection.submission_period_end_date
                if datetime.datetime.now(datetime.UTC) < datetime.datetime.combine(
                    collection.submission_period_end_date, datetime.time.min, tzinfo=datetime.UTC
                ):
                    raise CollectionChronologyError(
                        f"You cannot close the {collection.type.constants.singular} for submissions before "
                        f"the submission period end date of {collection.submission_period_end_date}"
                    )

                from app.common.helpers.collections import SubmissionHelper

                # TODO don't do this here but we need it for _update_submission_status to calculate the new status below
                collection.status = status

                for submission in collection._submissions:
                    # TODO replace this with add_submission_event to record that the colleciton was closed
                    #   But for expediency now, just call _update_submission_status which will calculate the new status
                    #   based on the collection now being closed
                    SubmissionHelper(submission)._update_submission_status()

            case _:
                raise StateTransitionError("Collection", collection.status, status)

        emit_metric_count(
            MetricEventName.COLLECTION_STATUS_CHANGED,
            collection=collection,
            custom_attributes={
                MetricAttributeName.FROM_STATUS: str(collection.status),
                MetricAttributeName.TO_STATUS: str(status),
            },
        )
        collection.status = status

    return collection


@flush_and_rollback_on_exceptions
def update_submission_data(submission: Submission) -> None:
    """Update the submission data with the data from the helper.

    NOTE: the submission's status probably needs updating after this; SubmissionHelper owns the status of a submission.
    This interface should only be called by the SubmissionHelper, and it must make sure that the status of the
    submission is updated appropriately (after clearing appropriate caches).
    """
    # We make a deepcopy here so that if any changes are made to `submission.data_manager.data` after this is flushed,
    # the changes are not reflected on the submission.
    submission._data = deepcopy(submission.data_manager.data)

    # Bust the DataManager cached property so that it reads the new submission data
    del submission.data_manager


@flush_and_rollback_on_exceptions
def update_submission(submission: Submission, *, status: SubmissionStatusEnum | TNotProvided = NOT_PROVIDED) -> None:
    if status is not NOT_PROVIDED:
        submission.status = status


def get_all_submissions_with_mode_for_collection(
    collection_id: UUID,
    submission_mode: SubmissionModeEnum,
    grant_recipient_ids: Sequence[UUID] | TNotProvided = NOT_PROVIDED,
    *,
    with_full_schema: bool = True,
    with_users: bool = False,
) -> Sequence[Submission]:
    """
    Use this function to get all submission data for a collection - it
    loads all the question/expression/user data at once to optimise
    performance and reduce the number of queries compared to looping
    through them all individually.
    """

    if sum([with_full_schema, with_users]) > 1:
        raise ValueError("Only one of with_full_schema or with_users should be set")

    # todo: this feels redundant because this interface should probably be limited to a single collection and fetch
    #       that through a specific interface which already exists - this can then focus on submissions
    stmt = select(Submission).where(Submission.collection_id == collection_id).where(Submission.mode == submission_mode)
    if with_full_schema:
        stmt = stmt.options(
            # get all flat components to drive single batches of selectin
            # joinedload lets us avoid an exponentially increasing number of queries
            joinedload(Submission.collection)
            .joinedload(Collection.forms)
            .selectinload(Form._all_components)
            .joinedload(Component.expressions),
            # get any nested components in one go
            joinedload(Submission.collection)
            .joinedload(Collection.forms)
            .selectinload(Form._all_components)
            .selectinload(Component.components)
            .joinedload(Component.expressions),
            # eagerly populate the forms top level components - this is a redundant query but
            # leaves as much as possible with the ORM
            joinedload(Submission.collection)
            .joinedload(Collection.forms)
            .selectinload(Form.components)
            .joinedload(Component.expressions),
            joinedload(Submission.collection)
            .joinedload(Collection.forms)
            .selectinload(Form._all_components)
            .selectinload(Component.owned_component_references),
            selectinload(Submission.events).joinedload(SubmissionEvent.created_by),
            selectinload(Submission.data_sources),
            joinedload(Submission.created_by),
        )
    elif with_users:
        stmt = stmt.options(
            joinedload(Submission.created_by),
        )

    if grant_recipient_ids is not NOT_PROVIDED:
        stmt = stmt.where(Submission.grant_recipient_id.in_(grant_recipient_ids))
    return db.session.scalars(stmt).unique().all()


@dataclass(frozen=True)
class ListSubmissionData:
    """Lightweight view of a row in the submissions list.

    Holds only the fields needed to render a row, avoiding the cost of loading full submission rows
    (including the potentially large `data` blob and every related event).

    Every grant recipient produces at least one row. For multiple-submission collections a recipient
    produces one row per submission (plus a single `submission_id=None` row when they have none yet);
    for single-submission collections a recipient produces exactly one row (with `submission_id=None`
    if they have not started one yet).
    """

    organisation_name: str | None
    name: str | None
    submission_id: UUID | None
    status: SubmissionStatusEnum | None
    last_updated_at_utc: datetime.datetime | None
    is_overdue: bool | None


def get_submission_list_for_collection(
    collection: Collection,
    submission_mode: SubmissionModeEnum,
) -> Sequence[ListSubmissionData]:
    """Fetch the rows needed to render a collection's submissions list.

    Both modes are grant-recipient centric: every grant recipient produces at least one row, so the
    listing can show recipients who have not started a submission. For multiple-submission collections
    a recipient with submissions produces one row per submission (and one `submission_id=None` row when
    they have none yet); for single-submission collections a recipient produces exactly one row.

    Selects only the columns needed to render the list, deriving the submission name in SQL (via the
    Submission hybrid property) rather than loading the full `data` blob into Python. The last-updated
    timestamp is derived by left-joining a single pre-aggregated max of event dates per submission,
    rather than the per-row correlated subquery the `last_updated_at_utc` hybrid would emit. This is a further
    optimisation for performance, as the correlated subquery can be expensive for large datasets.

    Rows are ordered by organisation name, then by submission name for multiple-submission collections.
    """
    # An optimisation to avoid the `Submission.last_updated_at_utc` subquery; here we instead join the max event date
    # directly to squeak out a bit more performance/efficiency
    latest_event = (
        select(
            SubmissionEvent.submission_id.label("submission_id"),
            func.max(SubmissionEvent.created_at_utc).label("max_created_at_utc"),
        )
        .join(Submission, Submission.id == SubmissionEvent.submission_id)
        .where(Submission.collection_id == collection.id, Submission.mode == submission_mode)
        .group_by(SubmissionEvent.submission_id)
        .subquery()
    )
    last_updated_at_utc = func.greatest(Submission.updated_at_utc, latest_event.c.max_created_at_utc).label(
        "last_updated_at_utc"
    )

    grant_recipient_mode = GrantRecipientModeEnum.from_similar(submission_mode)
    name_column = Submission.name.label("name") if collection.allow_multiple_submissions else null().label("name")
    order_by: List[Any] = [Organisation.name]
    if collection.allow_multiple_submissions:
        order_by.append(name_column)

    stmt = (
        select(
            Organisation.name.label("organisation_name"),
            name_column,
            Submission.id.label("submission_id"),
            Submission.status,
            last_updated_at_utc,
            Submission.is_overdue.label("is_overdue"),
        )
        .select_from(GrantRecipient)
        .join(Organisation, GrantRecipient.organisation_id == Organisation.id)
        .outerjoin(
            Submission,
            and_(
                Submission.grant_recipient_id == GrantRecipient.id,
                Submission.collection_id == collection.id,
                Submission.mode == submission_mode,
            ),
        )
        .outerjoin(Collection, Collection.id == Submission.collection_id)
        .outerjoin(latest_event, latest_event.c.submission_id == Submission.id)
        .where(GrantRecipient.grant_id == collection.grant_id, GrantRecipient.mode == grant_recipient_mode)
        .order_by(*order_by)
    )
    return [
        ListSubmissionData(
            organisation_name=row.organisation_name,
            name=row.name,
            submission_id=row.submission_id,
            status=row.status,
            last_updated_at_utc=row.last_updated_at_utc,
            is_overdue=row.is_overdue,
        )
        for row in db.session.execute(stmt).all()
    ]


def get_submissions_by_grant_recipient_collection(
    grant_recipient: GrantRecipient, collection_id: UUID
) -> Sequence[Submission]:
    submission_mode = SubmissionModeEnum(grant_recipient.mode.value)

    return db.session.scalars(
        select(Submission).where(
            Submission.grant_recipient_id == grant_recipient.id,
            Submission.collection_id == collection_id,
            Submission.mode == submission_mode,
        )
    ).all()


def get_or_create_submission(
    *, collection: Collection, grant_recipient: GrantRecipient, created_by: User, mode: SubmissionModeEnum
) -> Submission:
    # Acquire a transaction-scoped advisory lock keyed on (grant_recipient, collection) BEFORE
    # reading submissions. This prevents the double-click race condition: without the lock, two
    # concurrent requests can both read an empty list and each proceed to create a submission
    # before either commits. The lock serialises them so the second request re-reads after the
    # first commits and finds the existing submission instead. pg_advisory_xact_lock releases
    # automatically when the transaction ends, with no manual cleanup required.
    db.session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"{grant_recipient.id}:{collection.id}"},
    )

    submissions = get_submissions_by_grant_recipient_collection(grant_recipient, collection.id)
    if len(submissions) > 1:
        raise RuntimeError(
            f"Multiple submissions found for collection {collection.id} and grant recipient {grant_recipient.id}"
        )
    if submissions:
        return submissions[0]
    return create_submission(collection=collection, grant_recipient=grant_recipient, created_by=created_by, mode=mode)


def get_submissions_by_user(
    user: User, collection_id: UUID, submission_mode: SubmissionModeEnum
) -> Sequence[Submission]:
    return db.session.scalars(
        select(Submission).where(
            Submission.created_by_id == user.id,
            Submission.collection_id == collection_id,
            Submission.mode == submission_mode,
        )
    ).all()


def get_submission(
    submission_id: UUID, *, with_full_schema: bool = False, grant_recipient_id: UUID | None = None
) -> Submission:
    query = select(Submission).where(Submission.id == submission_id)

    options = []
    if grant_recipient_id:
        query = query.where(Submission.grant_recipient_id == grant_recipient_id)

    if with_full_schema:
        options.extend(
            [
                # get all flat components to drive single batches of selectin
                # joinedload lets us avoid an exponentially increasing number of queries
                joinedload(Submission.collection)
                .joinedload(Collection.forms)
                .options(
                    # eagerly populate the forms top level components - this is a redundant query but
                    # leaves as much as possible with the ORM
                    selectinload(Form.components).joinedload(Component.expressions),
                    selectinload(Form._all_components).options(
                        joinedload(Component.expressions),
                        # get any nested components in one go
                        joinedload(Component.components).joinedload(Component.expressions),
                        selectinload(Component.owned_component_references),
                    ),
                ),
                selectinload(Submission.events),
                selectinload(Submission.data_sources),
            ]
        )

    # We set `populate_existing` here to force a new query to be emitted to the database. The mechanics of `get_one`
    # relies on the session cache and does a lookup in the session memory based on the PK we're trying to retrieve.
    # If the object exists, no query is emitted and the options won't take effect - we would fall back to lazy loading,
    # which is n+1 select. If we don't care about fetching the full nested collection then it's fine to grab whatever is
    # cached in the session alright, but if we do specifically want all of the related objects, we want to force the
    # loading options above. This does mean that if you call this function twice with `with_full_schema=True`, it will
    # do redundant DB trips. We should try to avoid that. =]
    # If we took the principle that all relationships should be declared on the model as `lazy='raiseload'`, and we
    # specify lazy loading explicitly at all points of use, we could potentially remove the `populate_existing`
    # override below.
    return db.session.execute(query.options(*options)).unique().scalar_one()


@flush_and_rollback_on_exceptions
def create_submission(
    *, collection: Collection, created_by: User, mode: SubmissionModeEnum, grant_recipient: GrantRecipient | None = None
) -> Submission:
    existing_grant_submission_references = (
        db.session.execute(
            select(Submission.reference).join(Submission.collection).where(Collection.grant_id == collection.grant_id)
        )
        .scalars()
        .all()
    )
    new_reference = generate_submission_reference(collection, existing_grant_submission_references)

    submission = Submission(
        reference=new_reference,
        collection=collection,
        created_by=created_by,
        mode=mode,
        grant_recipient=grant_recipient,
        status=SubmissionStatusEnum.NOT_STARTED,
    )
    db.session.add(submission)
    emit_metric_count(MetricEventName.SUBMISSION_CREATED, submission=submission)
    return submission


def _swap_elements_in_list_and_flush(containing_list: list[Any], index_a: int, index_b: int) -> list[Any]:
    """Swaps the elements at the specified indices in the supplied list.
    If either index is outside the valid range, returns the list unchanged.

    Args:
        containing_list (list): List containing the elements to swap
        index_a (int): List index (0-based) of the first element to swap
        index_b (int): List index (0-based) of the second element to swap

    Returns:
        list: The updated list
    """
    if 0 <= index_a < len(containing_list) and 0 <= index_b < len(containing_list):
        containing_list[index_a], containing_list[index_b] = containing_list[index_b], containing_list[index_a]
    db.session.execute(text("SET CONSTRAINTS uq_form_order_collection, uq_component_order_form DEFERRED"))
    db.session.flush()
    return containing_list


def get_form_by_id(form_id: UUID, grant_id: UUID | None = None, with_all_questions: bool = False) -> Form:
    query = select(Form).where(Form.id == form_id)

    if grant_id:
        query = (
            query.join(Form.collection)
            .join(Collection.grant)
            .options(joinedload(Form.collection).joinedload(Collection.grant))
            .where(Collection.id == Form.collection_id, Collection.grant_id == grant_id)
        )

    if with_all_questions:
        # todo: this needs to be rationalised with the grant_id behaviour above, having multiple places to
        #       specify joins and options feels risky for them to collide or produce unexpected behaviour
        query = query.options(
            # get all flat components to drive single batches of selectin
            # joinedload lets us avoid an exponentially increasing number of queries
            selectinload(Form._all_components).joinedload(Component.expressions),
            # get any nested components in one go
            selectinload(Form._all_components).selectinload(Component.components).joinedload(Component.expressions),
            # eagerly populate the forms top level components - this is a redundant query but leaves as much as possible
            # with the ORM
            selectinload(Form.components).joinedload(Component.expressions),
        )

    return db.session.execute(query).scalar_one()


@flush_and_rollback_on_exceptions(coerce_exceptions=[(IntegrityError, DuplicateValueError)])
def create_form(*, title: str, collection: Collection) -> Form:
    form = Form(
        title=title,
        collection_id=collection.id,
        slug=slugify(title),
    )
    collection.forms.append(form)
    db.session.add(form)
    return form


@flush_and_rollback_on_exceptions
def move_form_up(form: Form) -> Form:
    swap_form = form.collection.forms[form.order - 1]
    _check_form_order_dependency(form, swap_form)
    _swap_elements_in_list_and_flush(form.collection.forms, form.order, swap_form.order)
    return form


@flush_and_rollback_on_exceptions
def move_form_down(form: Form) -> Form:
    swap_form = form.collection.forms[form.order + 1]
    _check_form_order_dependency(form, swap_form)
    _swap_elements_in_list_and_flush(form.collection.forms, form.order, swap_form.order)
    return form


@flush_and_rollback_on_exceptions(coerce_exceptions=[(IntegrityError, DuplicateValueError)])
def update_form(form: Form, *, title: str) -> Form:
    form.title = title
    form.slug = slugify(title)
    return form


@flush_and_rollback_on_exceptions
def _create_data_source(question: Question, items: list[str]) -> None:
    data_source = DataSource(id=uuid.uuid4())

    if len({slugify(item) for item in items}) != len(items):
        # If this error occurs, it's probably because QuestionForm does not check for duplication between the
        # main options and the 'Other' option. Might need to add that if this has triggered; but avoiding
        # now because I consider it unlikely. This will protect us even if it's not the best UX.
        raise ValueError("No duplicate data source items are allowed")

    data_source_items = []
    for choice in items:
        data_source_items.append(DataSourceItem(data_source_id=data_source.id, key=slugify(choice), label=choice))
    data_source.items = data_source_items
    question.data_source = data_source

    # Now that data_sources can be created without being linked to questions, it seems safer to only add the data_source
    # to the session after the relationship with a question has been set, to avoid orphaned data_sources
    db.session.add(data_source)


@flush_and_rollback_on_exceptions
def _update_data_source(question: Question, items: list[str]) -> None:
    assert question.data_source is not None
    existing_choices_map = {choice.key: choice for choice in question.data_source.items}
    for item in items:
        if slugify(item) in existing_choices_map:
            existing_choices_map[slugify(item)].label = item

    if len({slugify(item) for item in items}) != len(items):
        # If this error occurs, it's probably because QuestionForm does not check for duplication between the
        # main options and the 'Other' option. Might need to add that if this has triggered; but avoiding
        # now because I consider it unlikely. This will protect us even if it's not the best UX.
        raise ValueError("No duplicate data source items are allowed")

    new_choices = [
        existing_choices_map.get(
            slugify(choice),
            DataSourceItem(data_source_id=question.data_source.id, key=slugify(choice), label=choice),
        )
        for choice in items
    ]

    db.session.execute(text("SET CONSTRAINTS uq_data_source_id_order DEFERRED"))

    to_delete = [item for item in question.data_source.items if item not in new_choices]
    raise_if_data_source_item_reference_dependency(question, to_delete)
    for item_to_delete in to_delete:
        db.session.delete(item_to_delete)
    question.data_source.items = new_choices
    question.data_source.items.reorder()  # type: ignore[attr-defined]


@flush_and_rollback_on_exceptions
def create_question(
    form: Form,
    *,
    text: str,
    hint: str,
    name: str,
    data_type: QuestionDataType,
    expression_context: ExpressionContext,
    parent: Group | None = None,
    items: list[str] | None = None,
    presentation_options: QuestionPresentationOptions | None = None,
    data_options: QuestionDataOptions | None = None,
) -> Question:
    question = Question(
        text=text,
        form_id=form.id,
        slug=slugify(text),
        hint=hint,
        name=name,
        data_type=data_type,
        presentation_options=presentation_options,
        data_options=data_options,
        parent_id=parent.id if parent else None,
    )
    owner = parent or form
    owner.components.append(question)
    db.session.add(question)

    try:
        _validate_and_sync_component_references(question, expression_context)
        db.session.flush()
    except IntegrityError as e:
        # todo: check devs view on this, this is because other constraints (like the check constraint introduced here)
        #       are not because of duplicated values - the convention based method doesn't feel ideal but this setup
        #       is already working on a few assumptions of things lining up in different places. This just raises
        #       the ORM error if we're not guessing its a duplicate value error based on it being a unique constraint
        if e.orig.diag and e.orig.diag.constraint_name and e.orig.diag.constraint_name.startswith("uq_"):  # type: ignore[union-attr]
            raise DuplicateValueError(e) from e
        raise e

    if items is not None:
        _create_data_source(question, items)

    return question


def raise_if_group_cannot_be_add_another(group: Group) -> None:
    if group.contains_add_another_components:
        raise GroupContainsAddAnotherException(
            group=group,
            message="You cannot set a group to be add another if it already contains add another components",
        )
    if group.contains_questions_depended_on_elsewhere:
        raise AddAnotherDependencyException(
            message="You cannot set a group to be add another if questions in the group are depended on "
            "by other components",
            component=group,
            referenced_question=next(
                component for component in group.cached_all_components if len(component.depended_on_by) > 0
            ),
            form_error_message="You cannot set a group to be add another if questions in the group are depended on "
            "by other components",
        )
    if group.parent and group.parent.add_another_container:
        raise AddAnotherNotValidException(
            "You cannot set a group to be add another if it is nested inside an add another group",
            component=group,
            add_another_container=group.parent.add_another_container,
        )


def raise_if_nested_group_creation_not_valid_here(parent: Group | None = None) -> None:
    if parent:
        if not parent.can_have_child_group:
            raise NestedGroupException(
                "You cannot create a nested group at this level",
                parent_group=parent,
                nesting_level=parent.nested_group_levels + 1,
            )
        if parent.same_page:
            raise NestedGroupDisplayTypeSamePageException(
                "You cannot create a nested group if the parent is set to display all questions on the same page",
                parent_group=parent,
            )


@flush_and_rollback_on_exceptions(coerce_exceptions=[(IntegrityError, DuplicateValueError)])
def create_group(
    form: Form,
    *,
    text: str,
    name: str | None = None,
    parent: Group | None = None,
    presentation_options: QuestionPresentationOptions | None = None,
    add_another: bool = False,
) -> Group:
    # If this group is nested, ensure it meets rules for nesting groups
    # This is a safety check as we don't allow users to create nested groups when these rules aren't met
    raise_if_nested_group_creation_not_valid_here(parent=parent)
    group = Group(
        text=text,
        name=name or text,
        slug=slugify(text),
        form_id=form.id,
        parent_id=parent.id if parent else None,
        presentation_options=presentation_options,
        add_another=add_another,
    )
    owner = parent or form
    owner.components.append(group)
    db.session.add(group)
    return group


# todo: rename
def get_question_by_id(question_id: UUID) -> Question:
    return db.session.get_one(
        Question,
        question_id,
        options=[
            joinedload(Question.form).joinedload(Form.collection).joinedload(Collection.grant),
        ],
    )


def get_group_by_id(group_id: UUID) -> Group:
    return db.session.get_one(
        Group,
        group_id,
        options=[
            joinedload(Group.form).joinedload(Form.collection).joinedload(Collection.grant),
        ],
    )


def get_expression_by_id(expression_id: UUID) -> Expression:
    return db.session.get_one(
        Expression,
        expression_id,
        options=[
            joinedload(Expression.question)
            .joinedload(Component.form)
            .joinedload(Form.collection)
            .joinedload(Collection.grant)
        ],
    )


def get_component_by_id(component_id: UUID) -> Component:
    return db.session.get_one(Component, component_id)


class FlashableException(Protocol):
    def as_flash_context(self) -> dict[str, Any]: ...


class DependencyOrderException(WTFormRenderableException, FlashableException):
    def __init__(
        self,
        message: str,
        component: Component,
        depends_on_component: Component,
        form_error_message: str,
        field_name: str | None = None,
    ):
        super().__init__(
            message,
            form_error_message,
            field_name,
        )
        self.message = message
        self.question = component
        self.depends_on_question = depends_on_component

    def as_flash_context(self) -> dict[str, str | bool]:
        return {
            "message": self.form_error_message,
            "grant_id": str(self.question.form.collection.grant_id),  # Required for URL routing
            "question_id": str(self.question.id),
            "question_text": self.question.text,
            "question_is_group": self.question.is_group,
            # currently you can't depend on the outcome to a generic component (like a group)
            # so question continues to make sense here - we should review that naming if that
            # functionality changes
            "depends_on_question_id": str(self.depends_on_question.id),
            "depends_on_question_text": self.depends_on_question.text,
            "depends_on_question_is_group": self.depends_on_question.is_group,
        }


class SectionComponentDependencyException(Exception, FlashableException):
    def __init__(self, message: str, form: Form, component_references: list[ComponentReference]):
        super().__init__(message)
        self.message = message
        self.form = form
        self.component_references = component_references

    def as_flash_context(self) -> dict[str, Any]:
        seen_keys: set[tuple[UUID, str]] = set()
        references: list[dict[str, Any]] = []
        for ref in self.component_references:
            component = ref.component
            if ref.expression is not None:
                reference_type = "validation" if ref.expression.type_ == ExpressionType.VALIDATION else "condition"
            else:
                reference_type = "group" if component.is_group else "question"

            key = (component.id, reference_type)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            references.append(
                {
                    "reference_type": reference_type,
                    "component_id": str(component.id),
                    "component_text": component.text or "",
                    "is_group": component.is_group,
                    "section_id": str(component.form_id),
                    "section_title": component.form.title,
                }
            )

        return {
            "message": self.message,
            "grant_id": str(self.form.collection.grant_id),  # Required for URL routing
            "form_id": str(self.form.id),
            "form_title": self.form.title,
            "references": sorted(
                references, key=lambda r: (r["section_title"], r["component_text"], r["reference_type"])
            ),
        }


class SectionDependencyOrderException(Exception, FlashableException):
    def __init__(self, message: str, form: Form, depends_on_form: Form):
        super().__init__(message)
        self.message = message
        self.form = form
        self.depends_on_form = depends_on_form

    def as_flash_context(self) -> dict[str, str | bool]:
        return {
            "message": self.message,
            "grant_id": str(self.form.collection.grant_id),  # Required for URL routing
            "form_id": str(self.form.id),
            "form_title": self.form.title,
            "depends_on_form_id": str(self.depends_on_form.id),
            "depends_on_form_title": self.depends_on_form.title,
        }


class IncompatibleDataTypeInCalculationException(WTFormRenderableException):
    def __init__(self, e: IncompatibleDataTypeException):
        super().__init__(
            message=e.message,
            form_error_message=f"You cannot reference {e.depends_on_question.name} because only numbers can be "
            "referenced in calculations",
            field_name=e.field_name,
        )


class IncompatibleDataTypeException(WTFormRenderableException):
    def __init__(
        self,
        message: str,
        component: Component,
        depends_on_component: Component,
        form_error_message: str,
        field_name: str | None = None,
    ):
        super().__init__(
            message,
            form_error_message,
            field_name,
        )
        self.message = message
        self.question = component
        self.depends_on_question = depends_on_component

    def as_flash_context(self) -> dict[str, str | bool]:
        return {
            "message": self.form_error_message,
            "grant_id": str(self.question.form.collection.grant_id),  # Required for URL routing
            "question_id": str(self.question.id),
            "question_text": self.question.text,
            "depends_on_question_id": str(self.depends_on_question.id),
            "depends_on_question_text": self.depends_on_question.text,
        }


class DataSourceHasReferencesException(Exception, FlashableException):
    def __init__(
        self,
        message: str,
        data_source_id: uuid.UUID,
        data_source_name: str,
        grant_id: uuid.UUID,
        referenced_columns: set[str],
        references: list[dict[str, Any]],
    ):
        super().__init__(message)
        self.message = message
        self.data_source_id = data_source_id
        self.data_source_name = data_source_name
        self.grant_id = grant_id
        self.referenced_columns = referenced_columns
        self.references = references

    def as_flash_context(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "data_source_name": self.data_source_name,
            "grant_id": str(self.grant_id),
            "referenced_columns": sorted(self.referenced_columns),
            "references": sorted(self.references, key=lambda r: (r["component_text"], r["reference_type"])),
        }


class DataSourceItemReferenceDependencyException(Exception, FlashableException):
    def __init__(
        self,
        message: str,
        question_being_edited: Question,
        data_source_item_dependency_map: dict[Component, set[DataSourceItem]],
    ):
        super().__init__(message)
        self.message = message
        self.question_being_edited = question_being_edited
        self.data_source_item_dependency_map = data_source_item_dependency_map

    def as_flash_context(self) -> dict[str, str | bool]:
        contexts = self.as_flash_contexts()
        return contexts[0] if contexts else {}

    def as_flash_contexts(self) -> list[dict[str, str | bool]]:
        flash_contexts = []
        for dependent_question, data_source_items in self.data_source_item_dependency_map.items():
            flash_context: dict[str, str | bool] = {
                "message": self.message,
                "grant_id": str(self.question_being_edited.form.collection.grant_id),  # Required for URL routing
                "question_id": str(dependent_question.id),
                "question_text": dependent_question.text,
                "question_is_group": dependent_question.is_group,
                "depends_on_question_id": str(self.question_being_edited.id),
                "depends_on_question_text": self.question_being_edited.text,
                "depends_on_question_is_group": self.question_being_edited.is_group,
                "depends_on_items_text": ", ".join(data_source_item.label for data_source_item in data_source_items),
            }
            flash_contexts.append(flash_context)
        return flash_contexts


class NestedGroupException(Exception, FlashableException):
    def __init__(self, message: str, parent_group: Group, nesting_level: int):
        super().__init__(message)
        self.message = message
        self.parent_group = parent_group
        self.nesting_level = nesting_level

    def as_flash_context(self) -> dict[str, str | bool]:
        contexts = self.as_flash_contexts()
        return contexts[0] if contexts else {}

    def as_flash_contexts(self) -> list[dict[str, str | bool]]:
        flash_contexts = []
        flash_context: dict[str, str | bool] = {
            "message": self.message,
            "parent_group_name": self.parent_group.name,
            "parent_group_id": str(self.parent_group.id),
            "nesting_level": str(self.nesting_level),
            "max_nesting_level": str(current_app.config["MAX_NESTED_GROUP_LEVELS"]),
            "grant_id": str(self.parent_group.form.collection.grant_id),
        }
        flash_contexts.append(flash_context)
        return flash_contexts


class GroupContainsAddAnotherException(Exception, FlashableException):
    def __init__(
        self,
        message: str,
        group: Group,
    ):
        super().__init__(message)
        self.message = message
        self.group = group

    def as_flash_context(self) -> dict[str, str | bool]:
        contexts = self.as_flash_contexts()
        return contexts[0] if contexts else {}

    def as_flash_contexts(self) -> list[dict[str, str | bool]]:
        flash_contexts = []
        flash_context: dict[str, str | bool] = {
            "message": self.message,
            "group_name": self.group.name,
            "group_id": str(self.group.id),
            "grant_id": str(self.group.form.collection.grant_id),
        }
        flash_contexts.append(flash_context)
        return flash_contexts


class NestedGroupDisplayTypeSamePageException(Exception, FlashableException):
    def __init__(
        self,
        message: str,
        parent_group: Group,
    ):
        super().__init__(message)
        self.message = message
        self.parent_group = parent_group

    def as_flash_context(self) -> dict[str, str | bool]:
        contexts = self.as_flash_contexts()
        return contexts[0] if contexts else {}

    def as_flash_contexts(self) -> list[dict[str, str | bool]]:
        flash_contexts = []
        flash_context: dict[str, str | bool] = {
            "message": self.message,
            "parent_group_name": self.parent_group.name,
            "parent_group_id": str(self.parent_group.id),
            "grant_id": str(self.parent_group.form.collection.grant_id),
        }
        flash_contexts.append(flash_context)
        return flash_contexts


class GroupHasValidationsCannotBeOnePerPageException(Exception):
    def __init__(self, message: str, group: Group):
        super().__init__(message)
        self.message = message
        self.group = group


def _check_form_order_dependency(form: Form, swap_form: Form) -> None:
    # fetching the entire schema means whatever is calling this doesn't have to worry about
    # guaranteeing lazy loading performance behaviour
    _ = get_form_by_id(form.id, with_all_questions=True)
    _ = get_form_by_id(swap_form.id, with_all_questions=True)

    # we could be comparing to either an individual question or a group of multiple questions so collect those
    # as lists to compare against each other
    child_components = form.cached_all_components
    child_swap_components = swap_form.cached_all_components

    for c in child_components:
        for cr in c.owned_component_references:
            if cr.depends_on_component in child_swap_components:
                raise SectionDependencyOrderException(
                    "You cannot move sections above ones they depend on",
                    form,
                    swap_form,
                )

    for c in child_swap_components:
        for cr in c.owned_component_references:
            if cr.depends_on_component in child_components:
                raise SectionDependencyOrderException(
                    "You cannot move sections below ones that depend on them",
                    swap_form,
                    form,
                )


# todo: we might want something more generalisable that checks all order dependencies across a form
#       but this gives us the specific result we want for the UX for now
def _check_component_order_dependency(component: Component, swap_component: Component) -> None:
    # fetching the entire schema means whatever is calling this doesn't have to worry about
    # guaranteeing lazy loading performance behaviour
    _ = get_form_by_id(component.form_id, with_all_questions=True)

    # we could be comparing to either an individual question or a group of multiple questions so collect those
    # as lists to compare against each other
    child_components = [component] + (
        [c for c in component.cached_all_components] if isinstance(component, Group) else []
    )
    child_swap_components = [swap_component] + (
        [c for c in swap_component.cached_all_components] if isinstance(swap_component, Group) else []
    )

    for c in child_components:
        component_name = "question_groups" if c.is_group else "questions"
        for cr in c.owned_component_references:
            if cr.depends_on_component in child_swap_components:
                raise DependencyOrderException(
                    f"Cannot move {c.id} above {cr.depends_on_component.id} because there is a dependency",
                    component,
                    swap_component,
                    form_error_message=f"You cannot move {component_name} above answers they depend on",
                )

    for c in child_swap_components:
        component_name = "question_groups" if c.is_group else "questions"
        for cr in c.owned_component_references:
            if cr.depends_on_component in child_components:
                raise DependencyOrderException(
                    f"Cannot move {cr.depends_on_component.id} below {c.id} because there is a dependency",
                    swap_component,
                    component,
                    form_error_message=f"You cannot move answers below {component_name} that depend on them",
                )


# todo: persisting global order (depth + order) of components would help short circuit a lot of these checks
def is_component_dependency_order_valid(component: Component, depends_on_component: Component) -> bool:
    # fetching the entire schema means whatever is calling this doesn't have to worry about
    # guaranteeing lazy loading performance behaviour
    form = get_form_by_id(component.form_id, with_all_questions=True)
    depended_upon_form_is_earlier = depends_on_component.form.order < form.order
    if depended_upon_form_is_earlier:
        return True

    dependency_is_same_form = component.form_id == depends_on_component.form_id
    if not dependency_is_same_form:
        return False

    return form.cached_all_components.index(component) > form.cached_all_components.index(depends_on_component)


def raise_if_component_or_section_has_any_dependencies(component_or_form: Question | Group | Form) -> Never | None:
    child_components_ids = [
        c.id
        for c in [component_or_form]
        + (component_or_form.cached_all_components if isinstance(component_or_form, (Group, Form)) else [])
    ]
    # Only consider references whose dependent component is *outside* the subtree being deleted.
    # Internal references (e.g. a group validation that references its own child questions) will be
    # cascaded away alongside the subtree, so they should not block deletion.
    component_reference = (
        db.session.query(ComponentReference)
        .where(ComponentReference.depends_on_component_id.in_(child_components_ids))
        .where(ComponentReference.component_id.notin_(child_components_ids))
        .all()
    )
    if component_reference:
        if isinstance(component_or_form, Form):
            raise SectionComponentDependencyException(
                f"You cannot delete {component_or_form.title} because it is being referenced in another "
                f"section's questions",
                component_or_form,
                component_reference,
            )

        raise DependencyOrderException(
            f"{component_or_form.id} cannot be deleted as it is depended on by {component_reference[0].component.id}",
            component_reference[0].component,
            component_or_form,  # TODO: this could be component_reference[0].depends_on_component?
            form_error_message="You cannot delete an answer that other questions depend on",
        )

    return None


def raise_if_group_questions_depend_on_each_other(group: Group) -> Never | None:
    child_components_ids = [c.id for c in group.cached_questions]
    component_reference = (
        db.session.query(ComponentReference)
        .where(
            and_(
                ComponentReference.component_id.in_(child_components_ids),
                ComponentReference.depends_on_component_id.in_(child_components_ids),
            )
        )
        .all()
    )
    if component_reference:
        assert component_reference[0].depends_on_component
        raise DependencyOrderException(
            f"Group {group.id} cannot be set to same page because {component_reference[0].component.id} "
            f"depends on {component_reference[0].depends_on_component.id}",
            component_reference[0].component,
            component_reference[0].depends_on_component,
            form_error_message="You cannot set a group to be same page if it contains questions that depend on each "
            "other",
        )

    return None


def raise_if_data_source_item_reference_dependency(
    question: Question, items_to_delete: Sequence[DataSourceItem]
) -> Never | None:
    data_source_item_dependency_map: dict[Component, set[DataSourceItem]] = {}
    for data_source_item in items_to_delete:
        for reference in data_source_item.component_references:
            dependent_component = reference.component
            if dependent_component not in data_source_item_dependency_map:
                data_source_item_dependency_map[dependent_component] = set()
            data_source_item_dependency_map[dependent_component].add(data_source_item)

    if data_source_item_dependency_map:
        db.session.rollback()
        raise DataSourceItemReferenceDependencyException(
            "You cannot delete or change an option that other questions depend on.",
            question_being_edited=question,
            data_source_item_dependency_map=data_source_item_dependency_map,
        )
    return None


def raise_if_data_source_has_references(data_source: DataSource) -> Never | None:
    references = list(data_source.depended_on_by_columns)
    if not references:
        return None

    seen_keys: set[tuple[UUID, str]] = set()
    references_for_flash: list[dict[str, Any]] = []
    for ref in references:
        if ref.component is None:
            continue
        if ref.expression is not None:
            reference_type = "Validation" if ref.expression.type_ == ExpressionType.VALIDATION else "Condition"
        else:
            reference_type = "Group" if ref.component.is_group else "Question"

        key = (ref.component.id, reference_type)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        references_for_flash.append(
            {
                "component_id": str(ref.component.id),
                "component_text": ref.component.text or "",
                "is_group": ref.component.is_group,
                "reference_type": reference_type,
            }
        )

    if data_source.grant_id is None:
        # Should not happen for non-CUSTOM data sources (see check constraint on DataSource), so we treat this
        # as a programmer error rather than trying to build a half-broken flash message.
        raise RuntimeError(f"DataSource {data_source.id} has references but no grant_id")

    raise DataSourceHasReferencesException(
        "You cannot delete this data set because it's being referenced in the form. You need to remove references in:",
        data_source_id=data_source.id,
        data_source_name=data_source.name or "",
        grant_id=data_source.grant_id,
        referenced_columns={ref.depends_on_column_name or "" for ref in references},
        references=references_for_flash,
    )


class AddAnotherDependencyException(WTFormRenderableException, FlashableException):
    def __init__(
        self,
        message: str,
        component: Component,
        referenced_question: Component,
        form_error_message: str,
        field_name: str = "",
    ):
        super().__init__(
            message,
            form_error_message,
            field_name,
        )
        self.message = message
        self.component = component
        self.referenced_question = referenced_question

    def as_flash_context(self) -> dict[str, str | bool]:
        return {
            "message": self.form_error_message,
            "grant_id": str(self.component.form.collection.grant_id),  # Required for URL routing
            "component_id": str(self.component.id),
            "component_text": self.component.text,
            "referenced_question_id": str(self.referenced_question.id),
            "referenced_question_text": self.referenced_question.text,
        }


class AddAnotherNotValidException(Exception, FlashableException):
    def __init__(self, message: str, component: Component, add_another_container: Component):
        super().__init__(message)
        self.message = message
        self.component = component
        self.add_another_container = add_another_container

    def as_flash_context(self) -> dict[str, str | bool]:
        return {
            "message": self.message,
            "grant_id": str(self.component.form.collection.grant_id),  # Required for URL routing
            "component_id": str(self.component.id),
            "component_text": self.component.text,
            "add_another_container_id": str(self.add_another_container.id),
            "add_another_container_text": self.add_another_container.text,
        }


def raise_if_add_another_not_valid_here(component: Component) -> None:
    if not component.add_another:
        return
    if component.parent and component.parent.add_another_container:
        raise AddAnotherNotValidException(
            "You cannot create an add another component within an add another group",
            component,
            component.parent.add_another_container,
        )


@flush_and_rollback_on_exceptions
def move_component_up(component: Component) -> Component:
    swap_component = component.container.components[component.order - 1]
    _check_component_order_dependency(component, swap_component)
    _swap_elements_in_list_and_flush(component.container.components, component.order, swap_component.order)
    return component


@flush_and_rollback_on_exceptions
def move_component_down(component: Component) -> Component:
    swap_component = component.container.components[component.order + 1]
    _check_component_order_dependency(component, swap_component)
    _swap_elements_in_list_and_flush(component.container.components, component.order, swap_component.order)
    return component


def group_name_exists(name: str, form_id: UUID) -> bool:
    stmt_components_with_same_name_or_text = select(Component).where(
        or_(Component.name == name, Component.text == name), Component.form_id == form_id
    )
    slug_of_name = slugify(name)
    stmt_components_with_same_slug = select(Component).where(
        Component.slug == slug_of_name, Component.form_id == form_id
    )

    components_with_same_name_or_text = db.session.scalar(stmt_components_with_same_name_or_text)
    components_with_same_slug = db.session.scalar(stmt_components_with_same_slug)

    if components_with_same_slug and not components_with_same_name_or_text:
        current_app.logger.error(
            "Group name blocked by conflicting slug [%(form_id)s], %(name)s", {"name": name, "form_id": form_id}
        )

    return bool(components_with_same_slug or components_with_same_name_or_text)


@flush_and_rollback_on_exceptions(coerce_exceptions=[(IntegrityError, DuplicateValueError)])
def update_group(  # noqa: C901
    group: Group,
    expression_context: ExpressionContext,
    *,
    name: str | TNotProvided = NOT_PROVIDED,
    presentation_options: QuestionPresentationOptions | TNotProvided = NOT_PROVIDED,
    guidance_heading: str | None | TNotProvided = NOT_PROVIDED,
    guidance_body: str | None | TNotProvided = NOT_PROVIDED,
    add_another: bool | TNotProvided = NOT_PROVIDED,
    add_another_guidance_body: str | None | TNotProvided = NOT_PROVIDED,
    conditions_operator: ConditionsOperator | TNotProvided = NOT_PROVIDED,
) -> Group:
    if name is not NOT_PROVIDED:
        group.name = name
        group.text = name
        group.slug = slugify(name)

    if presentation_options is not NOT_PROVIDED:
        if (
            group.presentation_options.show_questions_on_the_same_page is not True
            and presentation_options.show_questions_on_the_same_page is True
        ):
            if group.has_nested_groups:
                raise NestedGroupDisplayTypeSamePageException(
                    "You cannot set a group to display all questions on the same page if it has nested groups",
                    parent_group=group,
                )
            try:
                raise_if_group_questions_depend_on_each_other(group)
            except DependencyOrderException as e:
                db.session.rollback()
                raise e

        if (
            group.presentation_options.show_questions_on_the_same_page is True
            and presentation_options.show_questions_on_the_same_page is False
            and group.validations
        ):
            raise GroupHasValidationsCannotBeOnePerPageException(
                "You cannot display this question group one question per page while it has validation rules attached",
                group=group,
            )

        # presentation options for groups can be spread out across multiple forms/ setting pages
        # override the provided fields without removing the existing settings for now, we might
        # want to switch to mutating the existing object in the future instead
        group.presentation_options = group.presentation_options.model_copy(
            update=presentation_options.model_dump(exclude_unset=True)
        )

    if guidance_heading is not NOT_PROVIDED:
        group.guidance_heading = guidance_heading

    if guidance_body is not NOT_PROVIDED:
        group.guidance_body = guidance_body

    if add_another is not NOT_PROVIDED:
        if group.add_another is not True and add_another is True:
            raise_if_group_cannot_be_add_another(group)

        group.add_another = add_another

    if add_another_guidance_body is not NOT_PROVIDED:
        group.add_another_guidance_body = add_another_guidance_body

    if conditions_operator is not NOT_PROVIDED:
        group.conditions_operator = conditions_operator

    _validate_and_sync_component_references(group, expression_context)

    # This is extreme and reasonably un-optimised, but it does provide a high level of assurance against being able to
    # break references within any child components. We should aim to have suitable checks higher up to provide a better
    # user experience/error handling though.
    for child in group.cached_all_components:
        _validate_and_sync_component_references(child, expression_context)

    return group


@flush_and_rollback_on_exceptions(coerce_exceptions=[(IntegrityError, DuplicateValueError)])
def update_question(
    question: Question,
    expression_context: ExpressionContext,
    *,
    text: str | TNotProvided = NOT_PROVIDED,
    name: str | TNotProvided = NOT_PROVIDED,
    hint: str | None | TNotProvided = NOT_PROVIDED,
    items: list[str] | None | TNotProvided = NOT_PROVIDED,
    presentation_options: QuestionPresentationOptions | TNotProvided = NOT_PROVIDED,
    guidance_heading: str | None | TNotProvided = NOT_PROVIDED,
    guidance_body: str | None | TNotProvided = NOT_PROVIDED,
    conditions_operator: ConditionsOperator | TNotProvided = NOT_PROVIDED,
    data_options: QuestionDataOptions | TNotProvided = NOT_PROVIDED,
) -> Question:
    if text is not NOT_PROVIDED and text is not None:
        question.text = text
        question.slug = slugify(text)

    if hint is not NOT_PROVIDED:
        question.hint = hint

    if name is not NOT_PROVIDED:
        question.name = name

    if presentation_options is not NOT_PROVIDED:
        question.presentation_options = presentation_options or QuestionPresentationOptions()

    if guidance_heading is not NOT_PROVIDED:
        question.guidance_heading = guidance_heading

    if guidance_body is not NOT_PROVIDED:
        question.guidance_body = guidance_body

    if conditions_operator is not NOT_PROVIDED:
        question.conditions_operator = conditions_operator

    if items is not NOT_PROVIDED and items is not None:
        _update_data_source(question, items)

    if data_options is not NOT_PROVIDED:
        question.data_options = data_options

    _validate_and_sync_component_references(question, expression_context)
    return question


@overload
def _add_submission_event(
    submission: Submission,
    *,
    event_type: Literal[SubmissionEventType.SUBMISSION_DECLINED_BY_CERTIFIER],
    user: User,
    related_entity_id: UUID | None = None,
    **kwargs: Unpack[DeclinedByCertifierKwargs],
) -> None: ...


@overload
def _add_submission_event(
    submission: Submission,
    *,
    event_type: Literal[SubmissionEventType.SUBMISSION_REOPENED],
    user: User,
    related_entity_id: UUID | None = None,
    **kwargs: Unpack[ReopenedKwargs],
) -> None: ...


@overload
def _add_submission_event(
    submission: Submission,
    *,
    event_type: SubmissionEventType,
    user: User,
    related_entity_id: UUID | None = None,
) -> None: ...


@flush_and_rollback_on_exceptions
def _add_submission_event(
    submission: Submission,
    *,
    event_type: SubmissionEventType,
    user: User,
    related_entity_id: UUID | None = None,
    **kwargs: Any,
) -> None:
    """Records an immutable submission event.

    NOTE: the submission's status probably needs updating after this; SubmissionHelper owns the status of a submission.
    This interface should only be called by the SubmissionHelper, and it must make sure that the status of the
    submission is updated appropriately (after clearing appropriate caches).

    You almost certainly want to use SubmissionHelper.add_submission_event instead of using this directly.
    """

    submission.events.append(
        SubmissionEvent(
            event_type=event_type,
            created_by=user,
            related_entity_id=related_entity_id or submission.id,
            data=SubmissionEventHelper.event_from(event_type, **kwargs),
        )
    )

    match event_type:
        case SubmissionEventType.SUBMISSION_SENT_FOR_CERTIFICATION:
            emit_metric_count(MetricEventName.SUBMISSION_SENT_FOR_CERTIFICATION, submission=submission)

        case SubmissionEventType.SUBMISSION_SUBMITTED:
            emit_metric_count(MetricEventName.SUBMISSION_SUBMITTED, submission=submission)

        case SubmissionEventType.FORM_RUNNER_FORM_RESET_TO_IN_PROGRESS:
            emit_metric_count(MetricEventName.SECTION_RESET_TO_IN_PROGRESS, submission=submission)

        case SubmissionEventType.FORM_RUNNER_FORM_COMPLETED:
            emit_metric_count(MetricEventName.SECTION_MARKED_COMPLETE, submission=submission)

        case SubmissionEventType.FORM_RUNNER_FORM_RESET_BY_CERTIFIER:
            emit_metric_count(MetricEventName.SECTION_RESET_TO_IN_PROGRESS_BY_CERTIFIER, submission=submission)

        case SubmissionEventType.SUBMISSION_APPROVED_BY_CERTIFIER:
            emit_metric_count(MetricEventName.SUBMISSION_CERTIFIED, submission=submission)

        case SubmissionEventType.SUBMISSION_DECLINED_BY_CERTIFIER:
            emit_metric_count(MetricEventName.SUBMISSION_CERTIFICATION_DECLINED, submission=submission)

        case SubmissionEventType.SUBMISSION_REOPENED:
            emit_metric_count(MetricEventName.SUBMISSION_REOPENED, submission=submission)

        case _:
            current_app.logger.error(
                "No metric configured for submission event %(event_type)s for submission %(submission_id)s",
                {"event_type": event_type, "submission_id": submission.id},
            )


def get_referenced_data_source_items_by_managed_expression(
    managed_expression: BaseDataSourceManagedExpression,
) -> Sequence[DataSourceItem]:
    # TODO[FSPT-1284]: handle not a `referenced_question` here explicitly? Probably just throw an error because
    #                  data source managed expressions might legitimately only ever be able to reference other questions
    #                  rather than anything in expression context (eg uplaoded data sets)?
    referenced_data_source_items = db.session.scalars(
        select(DataSourceItem).where(
            DataSourceItem.data_source == managed_expression.referenced_question.data_source,
            DataSourceItem.key.in_([item["key"] for item in managed_expression.referenced_data_source_items]),
        )
    ).all()
    return referenced_data_source_items


def _find_all_references_in_expression(
    value: str,
) -> list[ExpressionReference]:
    references: list[ExpressionReference] = []
    for match in INTERPOLATE_REGEX.finditer(value):
        references.append(ExpressionReference.from_wrapped(match.group(0)))
    return references


def components_in_same_group_and_on_same_page(component1: Component, component2: Component) -> bool:
    # got parents
    if not component1.parent or not component2.parent:
        return False
    # parents are groups
    if not component1.parent.is_group or not component2.parent.is_group:
        return False
    # parents are the same
    if component1.parent.id != component2.parent.id:
        return False
    return component1.parent.same_page is True


# TODO separate out more checks into little functions
def _validate_reference(  # noqa:C901
    reference: ExpressionReference,
    attached_to_component: Component | None,
    expression_context: ExpressionContext,
    expression_type: ExpressionType | None,  # None if it's not an expression, eg. guidance text
    field_name_for_error_message: str,
    question_to_test: Question | None,
) -> ExpressionReference:
    wrapped_reference = reference.wrapped
    unwrapped_reference = reference.unwrapped
    is_calculation: bool = field_name_for_error_message == "custom_expression"

    if not unwrapped_reference:
        raise InvalidReferenceInExpression(
            f"You cannot use {wrapped_reference} because it does not exist",
            field_name=field_name_for_error_message,
            bad_reference=wrapped_reference,
            form_error_message=f"You cannot use {wrapped_reference} because it does not exist",
        )
    if ALLOWED_INTERPOLATION_REGEX.search(unwrapped_reference) is not None:
        raise InvalidReferenceInExpression(
            f"Reference is not valid: {wrapped_reference}",
            field_name=field_name_for_error_message,
            bad_reference=wrapped_reference,
            form_error_message=f"You cannot use {wrapped_reference} because it does not exist",
        )
    if not attached_to_component:
        # TODO change this once we can create expressions to reuse, before they are attached to a component
        raise NotImplementedError("Cannot handle un-attached references yet")

    # Check the reference is valid in this expression context
    if not expression_context.is_valid_reference(unwrapped_reference):
        raise InvalidReferenceInExpression(
            f"You cannot use {wrapped_reference} because it does not exist",
            field_name=field_name_for_error_message,
            bad_reference=wrapped_reference,
            form_error_message=f"You cannot use {wrapped_reference} because it does not exist",
        )

    if referenced_question := reference.question:
        # For calculations, the reference must of type number
        if is_calculation and referenced_question.data_type != QuestionDataType.NUMBER:
            raise IncompatibleDataTypeException(
                f"Incompatible data type: {referenced_question.id} ({referenced_question.data_type}). "
                "Only numbers can be referenced in custom_expression",
                component=attached_to_component,
                depends_on_component=referenced_question,
                field_name=field_name_for_error_message,
                form_error_message=f"Reference is not valid due to incompatible data types: {wrapped_reference}",
            )
        # for validation, the question being validated (ie attached to) needs to have the same data type as the question
        # being referenced. Groups have no data_type so this check is skipped for group-level validations.
        if (
            expression_type == ExpressionType.VALIDATION
            and not attached_to_component.is_group
            and not attached_to_component.data_type == referenced_question.data_type
        ):
            raise IncompatibleDataTypeException(
                f"Incompatible data types: {attached_to_component.id} ({attached_to_component.data_type}) and "
                f"{referenced_question.id} ({referenced_question.data_type})",
                component=attached_to_component,
                depends_on_component=referenced_question,
                field_name=field_name_for_error_message,
                form_error_message=f"Reference is not valid due to incompatible data types: {wrapped_reference}",
            )

        # for conditions, the question being tested (could be any prior question) needs to have the same data type as
        # the question being referenced.
        if expression_type == ExpressionType.CONDITION:
            if question_to_test and not question_to_test.data_type == referenced_question.data_type:
                raise IncompatibleDataTypeException(
                    f"Incompatible data types: {attached_to_component.id} ({attached_to_component.data_type}) and "
                    f"{referenced_question.id} ({referenced_question.data_type})",
                    component=attached_to_component,
                    depends_on_component=referenced_question,
                    field_name=field_name_for_error_message,
                    form_error_message=f"Reference is not valid due to incompatible data types: {wrapped_reference}",
                )

        if not is_component_dependency_order_valid(attached_to_component, referenced_question):
            # Can't think of a better way right now for a custom validation expression to reference itself
            # TODO: ideally this would check a pre-configured ExpressionContext that uses an
            #       expression_context_end_point; if the reference is the expression context then we know it's valid and
            #       don't need to have this logic in multiple places.
            references_self_in_custom_validation = (
                expression_type == ExpressionType.VALIDATION
                and is_calculation
                and referenced_question == attached_to_component
            )
            # A validation attached to a group is allowed to reference any question nested within that group:
            # the group only "resolves" once all its questions have been answered, so the dependency order is
            # logically inverted compared to a normal question→question reference. This relaxation deliberately
            # does NOT apply to conditions, where the expression is evaluated *before* the group is shown.
            group_validation_references_own_descendant = (
                expression_type == ExpressionType.VALIDATION
                and attached_to_component.is_group
                and referenced_question.is_descendant_of(attached_to_component)
            )
            if not (references_self_in_custom_validation or group_validation_references_own_descendant):
                raise DependencyOrderException(
                    f"Cannot reference {referenced_question.id} because it comes after {attached_to_component.id}",
                    attached_to_component,
                    referenced_question,
                    field_name=field_name_for_error_message,
                    form_error_message=f"You cannot use {referenced_question.name} because it comes after this question"
                    f"{' group' if attached_to_component.is_group else ''}",
                )

        # For a non-custom condition, the question_to_test is the answer we are checking. eg. The answer that must
        # be GREATER_THAN something else, in order for attached_to_component to display
        if (
            question_to_test is not None
            and expression_type == ExpressionType.CONDITION
            and not is_component_dependency_order_valid(attached_to_component, question_to_test)
        ):
            raise DependencyOrderException(
                "Cannot reference a later question",
                attached_to_component,
                question_to_test,
                field_name=field_name_for_error_message,
                form_error_message=f"You cannot use {question_to_test.name} because it comes after this question",
            )

        if attached_to_component.id != referenced_question.id and components_in_same_group_and_on_same_page(
            attached_to_component, referenced_question
        ):
            raise InvalidReferenceInExpression(
                f"Reference is not valid: {referenced_question.name}",
                field_name=field_name_for_error_message,
                bad_reference=wrapped_reference,
                form_error_message=f"You cannot use {referenced_question.name} because it is in the same group as "
                f"{attached_to_component.name}",
            )

        if not components_in_valid_add_another_combination(
            attached_to_component, [referenced_question, question_to_test]
        ):
            raise AddAnotherDependencyException(
                f"Invalid add another combination: [{attached_to_component.id}, {referenced_question.id}, "
                f"{question_to_test.id if question_to_test else ''}]",
                attached_to_component,
                referenced_question,
                field_name=field_name_for_error_message,
                form_error_message=f"You cannot reference {referenced_question.name} because it can be answered more "
                "than once",
            )
    elif data_source_reference := reference.data_source_reference:
        data_source_column = reference.data_source_column
        if not data_source_column:
            raise InvalidReferenceInExpression(
                (
                    f"Column {data_source_reference.column_name} does not exist "
                    f"on data source {data_source_reference.data_source_id}"
                ),
                field_name=field_name_for_error_message,
                bad_reference=wrapped_reference,
                form_error_message=f"You cannot use {wrapped_reference} because it does not exist",
            )

    else:
        # TODO implement this once we can reference other things, eg. data uploads
        raise NotImplementedError(
            f"Reference is not a valid question ID: {wrapped_reference}",
        )
    return reference


def _validate_and_sync_expression_references(expression: Expression) -> None:  # noqa:C901
    if expression.is_managed:
        expr_impl = expression.managed
    else:
        expr_impl = expression.custom

    referenced_questions = set()
    component_references: list[ComponentReference] = []
    data_source_references: set[DataSourceReference] = set()

    if isinstance(expr_impl, BaseDataSourceManagedExpression):
        referenced_data_source_items = get_referenced_data_source_items_by_managed_expression(
            managed_expression=expr_impl
        )

        # TODO: Support data sources that are independent of components(questions), eg when we have platform-level
        #       data sources.
        for referenced_data_source_item in referenced_data_source_items:
            cr = ComponentReference(
                component=expression.question,
                expression=expression,
                # TODO: This will only work with the current 'CUSTOM' datasources - once we actually implement others
                # and a datasource can be used by multiple questions, this will need a refactor
                depends_on_component=referenced_data_source_item.data_source.questions[0],
                depends_on_data_source_item=referenced_data_source_item,
            )
            db.session.add(cr)
            component_references.append(cr)
    elif expression.is_managed:
        if expression.type_ == ExpressionType.CONDITION:
            assert expr_impl.subject_reference is not None
            # validate the referenced question - the one that is compared against the expression
            _validate_reference(
                reference=expr_impl.subject_reference,
                attached_to_component=expression.question,
                expression_context=ExpressionContext.build_expression_context(
                    expression.question.form.collection, "interpolation", None, None
                ),
                expression_type=expression.type_,
                field_name_for_error_message="depends_on_the_answer_to",
                question_to_test=None,
            )

        # For a managed validation attached to a question, expr_impl.subject_reference.question *is* the
        # question the expression is attached to (the answer being validated). Don't record a
        # self-reference — it would create a bogus ComponentReference row that falsely blocks
        # deletion and same-page grouping.

        referenced_question = expr_impl.subject_reference.question  # ty:ignore[unresolved-attribute]
        referenced_data_set_ref = expr_impl.subject_reference.data_source_reference  # ty:ignore[unresolved-attribute]

        if referenced_question and referenced_question != expression.question:
            referenced_questions.add(referenced_question)
        elif referenced_data_set_ref:
            data_source_references.add(referenced_data_set_ref)

    for field in expr_impl.reference_aware_fields:
        field_value = getattr(expr_impl, field)
        if not field_value:
            continue
        # An ExpressionReference-typed field is itself a single reference; a plain str field is
        # free text that may contain zero or more ((…)) references to scan out.
        references = (
            [field_value]
            if isinstance(field_value, ExpressionReference)
            else list(set(_find_all_references_in_expression(field_value)))
        )
        for reference in references:
            valid_reference = _validate_reference(
                reference=reference,
                attached_to_component=expression.question,
                expression_context=ExpressionContext.build_expression_context(
                    expression.question.form.collection, "interpolation", None, None
                ),
                expression_type=expression.type_,
                field_name_for_error_message=field,
                question_to_test=expr_impl.subject_reference.question if expression.is_managed else None,  # ty:ignore[unresolved-attribute]
            )

            if referenced_question := valid_reference.question:
                referenced_questions.add(referenced_question)
                continue

            if data_source_reference := valid_reference.data_source_reference:
                data_source_references.add(data_source_reference)
                continue

            raise ValueError(f"Unhandled reference '{valid_reference}' in component '{expression.question_id}'")

    for referenced_question in referenced_questions:
        if referenced_question == expression.question:
            continue
        cr = ComponentReference(
            component=expression.question,
            expression=expression,
            depends_on_component=referenced_question,
        )
        db.session.add(cr)
        component_references.append(cr)

    for data_source_reference in data_source_references:
        cr = ComponentReference(
            component=expression.question,
            expression=expression,
            depends_on_data_source_id=data_source_reference.data_source_id,
            depends_on_column_name=data_source_reference.column_name,
        )
        db.session.add(cr)
        component_references.append(cr)

    expression.component_references = component_references


def _validate_and_sync_component_references(component: Component, expression_context: ExpressionContext) -> None:  # noqa: C901
    """Scan the given component for references to another component in its text, hint, and guidance.

    Enforce our current feature scope constraint: any expression for interpolation currently must be a 'simple'
    statement. By that we mean: use a single value and do nothing else to it.

    This is a product constraint rather than a strict technical constraint right now as it simplifies
    implementation and removes a number of edge cases/concerns. We may remove this scope limiter in the future
    but recognise that doing so will need further product+design+technical thinking, which we're avoiding
    for now.
    """
    # Remove any references that are coming *from* `component`; we'll regenerate them all below
    db.session.execute(delete(ComponentReference).where(ComponentReference.component == component))

    for expression in component.expressions:
        _validate_and_sync_expression_references(expression)

    component_refs_to_set_up: set[tuple[UUID, UUID]] = set()
    data_source_refs_to_set_up: set[DataSourceReference] = set()
    field_names = ["text", "hint", "guidance_body", "add_another_guidance_body"]
    for field_name in field_names:
        value = getattr(component, field_name)
        if value is None:
            continue

        unvalidated_references = set(_find_all_references_in_expression(value))
        for unvalidated_reference in unvalidated_references:
            validated_reference = _validate_reference(
                reference=unvalidated_reference,
                attached_to_component=component,
                expression_context=expression_context,
                expression_type=None,
                field_name_for_error_message=field_name,
                question_to_test=None,
            )

            # TODO: make a match statement for clearer unhandled case
            if question_id := validated_reference.question_id:
                question = db.session.get_one(Question, question_id)
                component_refs_to_set_up.add((component.id, question.id))
                continue

            if data_source_reference := validated_reference.data_source_reference:
                data_source_refs_to_set_up.add(data_source_reference)
                continue

            raise ValueError(f"Unhandled reference '{validated_reference}' in component '{component.id}'")

    for component_id, depends_on_component_id in component_refs_to_set_up:
        if component_id == depends_on_component_id:
            continue
        db.session.add(ComponentReference(component_id=component_id, depends_on_component_id=depends_on_component_id))

    for data_source_reference in data_source_refs_to_set_up:
        db.session.add(
            ComponentReference(
                component_id=component.id,
                depends_on_data_source_id=data_source_reference.data_source_id,
                depends_on_column_name=data_source_reference.column_name,
            )
        )


@flush_and_rollback_on_exceptions(coerce_exceptions=[(IntegrityError, DuplicateValueError)])
def add_component_condition(
    component: Component, user: User, evaluatable_expression: EvaluatableExpression
) -> Component:
    expression = Expression.from_evaluatable_expression(evaluatable_expression, ExpressionType.CONDITION, user)
    component.expressions.append(expression)

    _validate_and_sync_expression_references(expression)

    if component.parent and component.parent.same_page:
        raise_if_group_questions_depend_on_each_other(component.parent)

    return component


@flush_and_rollback_on_exceptions(coerce_exceptions=[(IntegrityError, DuplicateValueError)])
def add_component_validation(
    component: Component, user: User, evaluatable_expression: "EvaluatableExpression"
) -> Component:
    expression = Expression.from_evaluatable_expression(evaluatable_expression, ExpressionType.VALIDATION, user)
    component.expressions.append(expression)
    _validate_and_sync_expression_references(expression)
    emit_metric_count(
        MetricEventName.VALIDATION_CREATED_MANAGED
        if expression.is_managed
        else MetricEventName.VALIDATION_CREATED_CUSTOM,
        1,
        evaluatable_expression=evaluatable_expression,
    )
    return component


def get_expression(expression_id: UUID) -> Expression:
    return db.session.get_one(Expression, expression_id)


@flush_and_rollback_on_exceptions
def remove_question_expression(question: Component, expression: Expression) -> Component:
    question.expressions.remove(expression)
    return question


@flush_and_rollback_on_exceptions(coerce_exceptions=[(IntegrityError, DuplicateValueError)])
def update_question_expression(expression: Expression, evaluatable_expression: EvaluatableExpression) -> Expression:
    expression.statement = evaluatable_expression.statement
    expression.context = evaluatable_expression.model_dump(mode="json")
    expression.managed_name = evaluatable_expression._key

    _validate_and_sync_expression_references(expression)
    return expression


@flush_and_rollback_on_exceptions
def delete_collection(collection: Collection) -> None:
    if collection.live_submissions:
        db.session.rollback()
        raise ValueError("Cannot delete collection with live submissions")

    data_sources_to_delete = [
        c.data_source for form in collection.forms for c in form._all_components if c.data_source
    ] + collection.data_sources

    db.session.delete(collection)

    for ds in data_sources_to_delete:
        db.session.delete(ds)


@flush_and_rollback_on_exceptions
def delete_form(form: Form) -> None:
    data_sources_to_delete = [
        c.data_source for c in form._all_components if c.data_source and c.data_source.type == DataSourceType.CUSTOM
    ]
    db.session.delete(form)
    for ds in data_sources_to_delete:
        db.session.delete(ds)
    form.collection.forms = [f for f in form.collection.forms if f.id != form.id]  # type: ignore[invalid-assignment]
    form.collection.forms.reorder()  # Force all other forms to update their `order` attribute
    db.session.execute(text("SET CONSTRAINTS uq_form_order_collection DEFERRED"))


@flush_and_rollback_on_exceptions
def delete_question(question: Question | Group) -> None:
    raise_if_component_or_section_has_any_dependencies(question)
    if question.data_source and question.data_source.type == DataSourceType.CUSTOM:
        db.session.delete(question.data_source)
    db.session.delete(question)
    if question in question.container.components:
        question.container.components.remove(question)
    question.container.components.reorder()
    db.session.execute(text("SET CONSTRAINTS uq_component_order_form DEFERRED"))


@flush_and_rollback_on_exceptions
def reset_test_submission(submission: Submission) -> None:
    if not submission.mode == SubmissionModeEnum.TEST:
        raise ValueError("Can only reset submissions in TEST mode")

    db.session.execute(delete(SubmissionEvent).where(SubmissionEvent.submission_id == submission.id))
    db.session.execute(delete(Submission).where(Submission.id == submission.id))


@flush_and_rollback_on_exceptions
def reset_all_test_submissions(collection: Collection) -> None:
    submission_ids = db.session.scalars(
        select(Submission.id).where(
            Submission.collection_id == collection.id,
            Submission.mode == SubmissionModeEnum.TEST,
        )
    ).all()

    if submission_ids:
        db.session.execute(delete(SubmissionEvent).where(SubmissionEvent.submission_id.in_(submission_ids)))
        db.session.execute(delete(Submission).where(Submission.id.in_(submission_ids)))


@flush_and_rollback_on_exceptions
def delete_collection_preview_submissions_created_by_user(collection: Collection, created_by_user: User) -> None:
    # We're trying to rely less on ORM relationships and cascades in delete queries so here we explicitly delete all
    # SubmissionEvents related to the `created_by_user`'s test submissions for that collection, and then
    # subsequently delete the submissions.

    submission_ids = db.session.scalars(
        select(Submission.id).where(
            Submission.collection_id == collection.id,
            Submission.created_by_id == created_by_user.id,
            Submission.mode == SubmissionModeEnum.PREVIEW,
        )
    ).all()

    db.session.execute(delete(SubmissionEvent).where(SubmissionEvent.submission_id.in_(submission_ids)))

    db.session.execute(
        delete(Submission).where(
            Submission.id.in_(submission_ids),
        )
    )
