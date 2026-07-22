import datetime
import uuid
from collections.abc import Callable, Sequence
from decimal import Decimal
from functools import cached_property
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from flask import current_app, url_for
from sqlalchemy import (
    CheckConstraint,
    ColumnElement,
    Date,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    and_,
    case,
    cast,
    func,
    not_,
    or_,
    select,
    text,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.hybrid import hybrid_method, hybrid_property
from sqlalchemy.ext.orderinglist import OrderingList, ordering_list
from sqlalchemy.orm import Mapped, aliased, column_property, foreign, mapped_column, relationship, remote
from sqlalchemy_json import mutable_json_type

from app.common.collections.types import DataSourceAnswerTypes, DecimalAnswer, IntegerAnswer, TextSingleLineAnswer
from app.common.data.base import BaseModel, CIStr
from app.common.data.models_user import Invitation, User, UserRole
from app.common.data.submission_data_manager import SubmissionDataManager
from app.common.data.types import (
    IN_PROGRESS_STATUSES,
    MONITORING_COLLECTIONS,
    PRE_AWARD_COLLECTIONS,
    SUBMITTED_STATUSES,
    CollectionStatusEnum,
    CollectionType,
    ComponentType,
    ConditionsOperator,
    DataSourceFileMetadata,
    DataSourceSchema,
    DataSourceSchemaColumn,
    DataSourceType,
    ExpressionType,
    FileUploadTypes,
    GrantRecipientModeEnum,
    GrantRecipientStatusEnum,
    GrantStatusEnum,
    ManagedExpressionsEnum,
    MaximumFileSize,
    NumberTypeEnum,
    OrganisationModeEnum,
    OrganisationStatus,
    OrganisationType,
    QuestionDataOptions,
    QuestionDataType,
    QuestionPresentationOptions,
    RoleEnum,
    SubmissionAssessmentStatusEnum,
    SubmissionEventType,
    SubmissionModeEnum,
    SubmissionStatusEnum,
    json_flat_scalars,
    json_scalars,
)
from app.common.expressions import EvaluatableExpression
from app.common.expressions.custom import CustomExpression, get_custom_expression
from app.common.expressions.managed import (
    get_managed_expression,
)
from app.common.expressions.references import (
    CIInterpolationStatementType,
    EvaluationStatement,
    InterpolationStatement,
)
from app.common.safe_ids import SafeDidMixin, SafeQidMixin
from app.common.utils import comma_join_items

if TYPE_CHECKING:
    from app.common.expressions.managed import ManagedExpression


class Grant(BaseModel):
    __tablename__ = "grant"

    ggis_number: Mapped[str]
    name: Mapped[CIStr] = mapped_column(unique=True)
    code: Mapped[CIStr] = mapped_column(unique=True)
    status: Mapped[GrantStatusEnum] = mapped_column(default=GrantStatusEnum.DRAFT)
    description: Mapped[str]
    primary_contact_name: Mapped[str]
    primary_contact_email: Mapped[str]
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisation.id"), nullable=True
    )  # TODO: make non-nullable

    collections: Mapped[list[Collection]] = relationship(
        "Collection",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="Collection.type.desc(), Collection.created_at_utc.desc()",
    )
    organisation: Mapped[Organisation] = relationship("Organisation", back_populates="grants")
    grant_recipients: Mapped[list[GrantRecipient]] = relationship("GrantRecipient", back_populates="grant")
    privacy_policy_markdown: Mapped[str | None]

    allow_pre_award: Mapped[bool] = mapped_column(default=False)

    invitations: Mapped[list[Invitation]] = relationship(
        "Invitation",
        back_populates="grant",
        viewonly=True,
    )

    # This is specifically people granted *explicit* access to this specific grant, not just anyone with more
    # generalised access to the grant (eg org and platform admins)
    grant_team_users: Mapped[list[User]] = relationship(
        "User",
        secondary="user_role",
        primaryjoin="Grant.id==UserRole.grant_id",
        secondaryjoin="and_(User.id==UserRole.user_id, UserRole.organisation_id==foreign(Grant.organisation_id))",
        viewonly=True,
        lazy="select",
    )

    @property
    def reports(self) -> list[Collection]:
        return [collection for collection in self.collections if collection.is_monitoring_collection]

    @property
    def pre_award_forms(self) -> list[Collection]:
        return [collection for collection in self.collections if collection.is_pre_award_collection]

    @property
    def test_grant_recipients(self) -> list[GrantRecipient]:
        return [
            grant_recipient
            for grant_recipient in self.grant_recipients
            if grant_recipient.mode == GrantRecipientModeEnum.TEST
        ]

    @property
    def live_grant_recipients(self) -> list[GrantRecipient]:
        return [
            grant_recipient
            for grant_recipient in self.grant_recipients
            if grant_recipient.mode == GrantRecipientModeEnum.LIVE
        ]

    def get_access_reports_for_user(
        self, user: User | None = None, *, user_organisation: Organisation | None = None
    ) -> list[Collection]:
        """Get reports visible to Access users, with special handling for testing.

        Args:
            user: Current user. If a Deliver user testing Access, returns all reports.
                  If None or regular Access user, returns only OPEN/CLOSED reports.

        Returns:
            List of Collection objects sorted by status and submission end date.
        """
        from app.common.auth.authorisation_helper import AuthorisationHelper

        # Deliver users testing Access see all reports
        if user and AuthorisationHelper.is_deliver_user_testing_access(user, user_organisation=user_organisation):
            return sorted(
                self.reports, key=lambda report: (report.status, report.submission_period_end_date or datetime.date.max)
            )

        # Regular Access users see only OPEN/CLOSED
        access_reports = [
            report
            for report in self.reports
            if report.status in [CollectionStatusEnum.OPEN, CollectionStatusEnum.CLOSED]
        ]
        return sorted(
            access_reports, key=lambda report: (report.status, report.submission_period_end_date or datetime.date.max)
        )

    def get_access_pre_award_forms_for_user(
        self, user: User | None = None, *, user_organisation: Organisation | None = None
    ) -> list[Collection]:
        from app.common.auth.authorisation_helper import AuthorisationHelper

        # Deliver users testing Access see all pre-award forms
        if user and AuthorisationHelper.is_deliver_user_testing_access(user, user_organisation=user_organisation):
            return sorted(
                self.pre_award_forms,
                key=lambda form: (form.status, form.submission_period_end_date or datetime.date.max),
            )

        # Regular Access users see only OPEN/CLOSED pre-award forms
        access_forms = [
            form
            for form in self.pre_award_forms
            if form.status in [CollectionStatusEnum.OPEN, CollectionStatusEnum.CLOSED]
        ]
        return sorted(
            access_forms, key=lambda form: (form.status, form.submission_period_end_date or datetime.date.max)
        )

    @property
    def access_reports(self) -> list[Collection]:
        """Backward compatibility - uses regular Access user filtering."""
        return self.get_access_reports_for_user(user=None)

    @property
    def access_pre_award_forms(self) -> list[Collection]:
        return self.get_access_pre_award_forms_for_user(user=None)

    @property
    def can_go_live(self) -> bool:
        return bool(
            self.privacy_policy_markdown is not None
            and len(self.grant_team_users) >= 2
            and self.ggis_number
            and self.description
        )


class Organisation(BaseModel):
    __tablename__ = "organisation"

    # The consistent reference used to identify this orgaisation; changing this after creation is a risky endeavour
    # as the external ID is used to associate eg uploaded reference data. Consider this immutable once set.
    external_id: Mapped[str]

    # For Central Government departments, this is an IATI organisation identifier
    # from: https://www.gov.uk/government/publications/iati-organisation-identifiers-for-uk-government-organisations
    iati_id: Mapped[str | None] = mapped_column(nullable=True)

    # For local government, this uses the Local Authority District (December 2024) [LAD24] boundaries dataset:
    # https://geoportal.statistics.gov.uk/datasets/6a05f93297cf4a438d08e972099f54b9_0/explore
    ons_lad_id: Mapped[str | None] = mapped_column(nullable=True)

    companies_house_number: Mapped[str | None] = mapped_column(nullable=True)
    charity_commission_number: Mapped[str | None] = mapped_column(nullable=True)

    # For 'Other' type organisations, we'll generate our own code to identify the organisation.
    # We might later fill in a companies house or charity commission number, but this need to be done carefully -
    # switching the external_id could break dataset references.
    custom_code: Mapped[str | None] = mapped_column(nullable=True)
    name: Mapped[CIStr] = mapped_column(unique=False)

    # TODO: switch this to a computed column?
    status: Mapped[OrganisationStatus] = mapped_column(default=OrganisationStatus.ACTIVE)

    type: Mapped[OrganisationType]
    active_date: Mapped[datetime.date | None] = mapped_column(nullable=True)
    retirement_date: Mapped[datetime.date | None] = mapped_column(nullable=True)
    can_manage_grants: Mapped[bool] = mapped_column(default=False)
    mode: Mapped[OrganisationModeEnum] = mapped_column(default=OrganisationModeEnum.LIVE)

    @property
    def typed_id(self) -> str:
        """Fetch the 'canonical' organisation ID field based on its org type, for example a 'Company' type should store
        its ID in the 'companies_house_number' column.
        """
        return getattr(self, self.type.typed_id_field, "")

    @typed_id.setter
    def typed_id(self, value: str) -> None:
        setattr(self, self.type.typed_id_field, value)

    def make_external_id(self) -> str:
        """Consistently create an external ID for an organisation based on its official ID column.

        For example, add the CC- prefix for Charities so you get something like CC-1234 for charity number 1234.
        """
        prefix = self.type.external_id_prefix
        return f"{prefix}{self.typed_id}" if prefix else self.typed_id

    roles: Mapped[list[UserRole]] = relationship(
        "UserRole", back_populates="organisation", cascade="all, delete-orphan"
    )
    grants: Mapped[list[Grant]] = relationship("Grant", back_populates="organisation")

    matching_test_organisation: Mapped["Organisation | None"] = relationship(
        "Organisation",
        primaryjoin=lambda: and_(
            Organisation.id != remote(Organisation.id),
            foreign(Organisation.external_id) == remote(Organisation.external_id),
            remote(Organisation.mode) == OrganisationModeEnum.TEST,
        ),
        uselist=False,
        viewonly=True,
    )
    matching_live_organisation: Mapped["Organisation | None"] = relationship(
        "Organisation",
        primaryjoin=lambda: and_(
            Organisation.id != remote(Organisation.id),
            foreign(Organisation.external_id) == remote(Organisation.external_id),
            remote(Organisation.mode) == OrganisationModeEnum.LIVE,
        ),
        uselist=False,
        viewonly=True,
    )

    __table_args__ = (
        # NOTE: make it so that only a single organisation can manage grants in the platform at the moment. When we come
        #       to onboard other government departments as grant owners, we'll need to release this constraint and
        #       ensure that Deliver grant funding has appropriate designs to understand and handle multiple grant
        #       owning orgs. For now this lets us keep the idea of org switching out of Deliver grant funding, and our
        #       queries can just find the only organisation with 'can_manage_grants=true'.
        Index(
            "uq_organisation_name_can_manage_grants",
            "can_manage_grants",
            unique=True,
            postgresql_where=can_manage_grants.is_(True),
        ),
        UniqueConstraint("external_id", "mode", name="uq_organisation_external_id_mode"),
        UniqueConstraint("name", "mode", name="uq_organisation_name_mode"),
        CheckConstraint("status = 'retired' OR retirement_date IS NULL", name="ck_retirement"),
        CheckConstraint(
            """
            (type = 'CENTRAL_GOVERNMENT' AND iati_id IS NOT NULL) OR
            (type IN ('UNITARY_AUTHORITY', 'SHIRE_DISTRICT', 'METROPOLITAN_DISTRICT',
                      'LONDON_BOROUGH', 'SHIRE_COUNTY', 'COMBINED_AUTHORITY',
                      'NORTHERN_IRELAND_AUTHORITY', 'SCOTTISH_UNITARY_AUTHORITY',
                      'WELSH_UNITARY_AUTHORITY') AND ons_lad_id IS NOT NULL) OR
            (type = 'CHARITY' AND charity_commission_number IS NOT NULL) OR
            (type = 'COMPANY' AND companies_house_number IS NOT NULL) OR
            (type = 'OTHER' AND custom_code IS NOT NULL)
            """,
            name="ck_typed_external_id",
        ),
    )


class Collection(BaseModel):
    __tablename__ = "collection"

    type: Mapped[CollectionType] = mapped_column(SqlEnum(CollectionType, name="collection_type", validate_strings=True))

    # Name will be superseded by domain specific application contexts but allows us to
    # try out different collections and scenarios
    name: Mapped[str]
    slug: Mapped[str]

    grant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("grant.id"))
    grant: Mapped[Grant] = relationship("Grant", back_populates="collections")

    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    created_by: Mapped[User] = relationship("User")

    # NOTE: Status and dates *may* more properly belong on a separate model, such as a ReportingRound, but have not done
    # that for now because:
    #       1) time constraints - sorry
    #       2) until we have multiple concrete implementations (eg ReportingRound and ApplicationRound), I don't think
    #          there's a compelling reason to sort this out *right now*.
    #       When that time comes we probably will move `name` off of this model and could also drop `type`; but there
    #       are a few threads that need pulling in a coherent way with a suitable amount of time and effort. Such as:
    #       * what do `submissions` link to? their `collection` or the report/application/prospectus
    #       * how do we associate submissions to their users
    #         (grant recipient orgs for reports, plain orgs for applications, grant teams for prospectuses)
    status: Mapped[CollectionStatusEnum] = mapped_column(
        SqlEnum(CollectionStatusEnum, name="collection_status", validate_strings=True),
        default=CollectionStatusEnum.DRAFT,
    )
    reporting_period_start_date: Mapped[datetime.date | None]
    reporting_period_end_date: Mapped[datetime.date | None]
    submission_period_start_date: Mapped[datetime.date | None]
    submission_period_end_date: Mapped[datetime.date | None]
    reminder_email_business_days_before_closing: Mapped[int] = mapped_column(default=5)
    requires_certification: Mapped[bool | None]
    allow_multiple_submissions: Mapped[bool] = mapped_column(default=False)
    allow_public_sign_up: Mapped[bool] = mapped_column(default=False)
    submission_name_question_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("component.id"), nullable=True)
    submission_name_question: Mapped["Question | None"] = relationship(
        "Question", foreign_keys=[submission_name_question_id]
    )
    submission_guidance: Mapped[str | None]

    # Prevents grant recipients from creating their own submissions in a multi-submission collection; where we set this
    # to be true, we need to generate the initial submissions for them.
    multiple_submissions_are_managed_by_service: Mapped[bool] = mapped_column(default=False)

    # NOTE: Don't use this relationship directly; use either `test_submissions` or `live_submissions`.
    _submissions: Mapped[list[Submission]] = relationship(
        "Submission",
        lazy=True,
        order_by="Submission.created_at_utc",
        back_populates="collection",
        cascade="all, delete-orphan",
    )
    forms: Mapped[OrderingList[Form]] = relationship(
        "Form",
        lazy=True,
        order_by="Form.order",
        collection_class=ordering_list("order"),
        # Importantly we don't `delete-orphan` here; when we move forms up/down, we remove them from the collection,
        # which would trigger the delete-orphan rule
        cascade="all",
    )

    data_sources: Mapped[list[DataSource]] = relationship("DataSource", back_populates="collection")

    def s3_key_prefix(self, submission_mode: SubmissionModeEnum) -> str:
        return f"{current_app.config['SUBMISSION_FILES_PREFIX']}/{submission_mode}/{self.id}"

    __table_args__ = (
        UniqueConstraint("name", "grant_id", name="uq_collection_name_grant_id"),
        CheckConstraint(
            "requires_certification IS NOT NULL OR type != 'MONITORING_REPORT'",
            name="ck_monitoring_certification_not_null",
        ),
        CheckConstraint(
            "submission_name_question_id IS NULL OR allow_multiple_submissions = true",
            name="ck_submission_name_question_requires_multiple_submissions",
        ),
        CheckConstraint(
            "multiple_submissions_are_managed_by_service = false OR allow_multiple_submissions = true",
            name="ck_multiple_submissions_are_managed_by_service",
        ),
    )

    @property
    def preview_submissions(self) -> list[Submission]:
        return list(submission for submission in self._submissions if submission.mode == SubmissionModeEnum.PREVIEW)

    @property
    def test_submissions(self) -> list[Submission]:
        return list(submission for submission in self._submissions if submission.mode == SubmissionModeEnum.TEST)

    @property
    def live_submissions(self) -> list[Submission]:
        return list(submission for submission in self._submissions if submission.mode == SubmissionModeEnum.LIVE)

    @property
    def is_editable_for_current_status(self) -> bool:
        return self.status == CollectionStatusEnum.DRAFT

    @property
    def is_open(self) -> bool:
        return self.status == CollectionStatusEnum.OPEN

    @property
    def is_closed(self) -> bool:
        return self.status == CollectionStatusEnum.CLOSED

    @property
    def is_open_for_changes(self) -> bool:
        return self.status in [CollectionStatusEnum.OPEN, CollectionStatusEnum.DRAFT]

    @property
    def is_overdue(self) -> bool:
        if not self.submission_period_end_date:
            return False
        # ensure BST/ GMT to line up with the hybrid property expected boundary
        return self.submission_period_end_date < datetime.datetime.now(ZoneInfo("Europe/London")).date()

    @property
    def is_monitoring_collection(self) -> bool:
        return self.type in MONITORING_COLLECTIONS

    @property
    def is_pre_award_collection(self) -> bool:
        return self.type in PRE_AWARD_COLLECTIONS

    @property
    def public_sign_up(self) -> str:
        # TODO: link to the grants/ collection public sign up page when registered as an endpoint in Access
        # url is just a placeholder for now
        return url_for("auth.request_a_link_to_sign_in", _external=True)

    def get_section_names_from_ids(self, form_ids: list[str]) -> list[str]:
        return [form.title for form in self.forms if str(form.id) in form_ids]


class Submission(BaseModel):
    __tablename__ = "submission"

    reference: Mapped[CIStr] = mapped_column(unique=True)

    _data: Mapped[json_scalars] = mapped_column("data", default=dict)

    mode: Mapped[SubmissionModeEnum] = mapped_column(
        SqlEnum(SubmissionModeEnum, name="submission_mode_enum", validate_strings=True)
    )

    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    grant_recipient_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("grant_recipient.id"))

    collection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("collection.id"))
    collection: Mapped[Collection] = relationship("Collection")

    events: Mapped[list[SubmissionEvent]] = relationship(
        "SubmissionEvent",
        back_populates="submission",
        cascade="all, delete-orphan",
        order_by="desc(SubmissionEvent.created_at_utc)",
    )
    created_by: Mapped[User] = relationship("User", back_populates="submissions")
    grant_recipient: Mapped[GrantRecipient] = relationship("GrantRecipient", back_populates="submissions")

    data_sources: Mapped[list[DataSource]] = relationship(
        "DataSource",
        primaryjoin=lambda: Submission.collection_id == foreign(DataSource.collection_id),
        viewonly=True,
    )

    status: Mapped[SubmissionStatusEnum] = mapped_column(
        SqlEnum(
            SubmissionStatusEnum,
            name="submission_status_enum",
            validate_strings=True,
        ),
        nullable=False,
    )

    assessment_status: Mapped[SubmissionAssessmentStatusEnum] = mapped_column(
        SqlEnum(
            SubmissionAssessmentStatusEnum,
            name="submission_assessment_status_enum",
            validate_strings=True,
        ),
        nullable=False,
        default=SubmissionAssessmentStatusEnum.NOT_STARTED,
    )

    @hybrid_property
    def last_updated_at_utc(self) -> datetime.datetime:
        from app.common.helpers.submission_events import SubmissionEventHelper

        event_helper = SubmissionEventHelper(self)
        return max(filter(None, [event.created_at_utc for event in event_helper.events] + [self.updated_at_utc]))

    @last_updated_at_utc.inplace.expression
    @classmethod
    def _last_updated_at_utc_expression(cls) -> ColumnElement[datetime.datetime]:
        # Postgres GREATEST ignores NULLs, so this falls back to updated_at_utc when there are no events.
        return func.greatest(
            cls.updated_at_utc,
            select(func.max(SubmissionEvent.created_at_utc))
            .where(SubmissionEvent.submission_id == cls.id)
            .correlate(cls)
            .scalar_subquery(),
        )

    @property
    def s3_key_prefix(self) -> str:
        return f"{current_app.config['SUBMISSION_FILES_PREFIX']}/{self.mode}/{self.collection_id}/{self.id}"

    @cached_property
    def data_manager(self) -> SubmissionDataManager:
        """Copies the existing submission data and wrap it in a helper to update answers.

        Use this to add/edit/remove answers from the submission. Changes must be synced back onto the submission model
        using the `update_submission_data` interface.
        """
        return SubmissionDataManager(self._data)

    @hybrid_property
    def name(self) -> str:
        """
        For submissions in a multi-submission collection, this provides a name for the submission based on a provided
        answer. If the answer hasn't been provided yet, we just use the submission's generated reference.
        """
        question = self.collection.submission_name_question
        if question:
            answer = self.data_manager.get(question)
            if answer is not None:
                return answer.get_value_for_text_export()
        return self.reference

    @name.inplace.expression
    @classmethod
    def _name_expression(cls) -> ColumnElement[str]:
        # Mirrors `get_value_for_text_export()` for the only data types allowed as a submission name question
        # (see QUESTION_DATA_TYPES_ALLOWED_FOR_MULTI_SUBMISSION_NAMES). This hardcodes how each answer type is stored
        # in the `data` blob: TEXT_SINGLE_LINE is the raw value, whereas RADIOS stores a {"key", "label"} object whose
        # display value is the label. Keep this in sync with the answer models in app.common.collections.types if the
        # set of allowed name question types or their stored shape changes.
        name_question = aliased(Component)
        name_question_key = Collection.submission_name_question_id.cast(Text)
        answer_value = case(
            (
                name_question.data_type == QuestionDataType.TEXT_SINGLE_LINE,
                cls._data[name_question_key].astext,
            ),
            (
                name_question.data_type == QuestionDataType.RADIOS,
                cls._data[name_question_key]["label"].astext,
            ),
        )
        # Falls back to the reference when there is no name question (single-submission) or it is unanswered.
        return func.coalesce(
            select(answer_value)
            .select_from(Collection)
            .join(name_question, name_question.id == Collection.submission_name_question_id)
            .where(Collection.id == cls.collection_id)
            .correlate(cls)
            .scalar_subquery(),
            cls.reference,
        )

    @hybrid_property
    def is_assessed(self) -> bool:
        return self.assessment_status != SubmissionAssessmentStatusEnum.NOT_STARTED

    @is_assessed.inplace.expression
    @classmethod
    def _is_assessed_expression(cls) -> ColumnElement[bool]:
        return cls.assessment_status != SubmissionAssessmentStatusEnum.NOT_STARTED

    @hybrid_property
    def is_submitted(self) -> bool:
        return self.status in SUBMITTED_STATUSES

    @is_submitted.inplace.expression
    @classmethod
    def _is_submitted_expression(cls) -> ColumnElement[bool]:
        return cls.status.in_(SUBMITTED_STATUSES)

    @hybrid_property
    def is_in_progress(self) -> bool:
        return self.status in IN_PROGRESS_STATUSES

    @is_in_progress.inplace.expression
    @classmethod
    def _is_in_progress_expression(cls) -> ColumnElement[bool]:
        return cls.status.in_(IN_PROGRESS_STATUSES)

    @hybrid_property
    def is_overdue(self) -> bool:
        # todo: make sure this is resilient to timezones, drift, etc. this is likely something that should
        #       a batch job decision that is then added as a submission event rather than calculated by the server
        return self.collection.is_overdue and not self.is_submitted

    @is_overdue.inplace.expression
    @classmethod
    def _is_overdue_expression(cls) -> ColumnElement[bool]:
        return (
            Collection.submission_period_end_date.isnot(None)
            # ensure both side are dates, when the date side is coerced to date with timestamp it will default
            # to 00:00 which will always be less than the same day resulting in an exclusive comparison
            & (Collection.submission_period_end_date < func.timezone("Europe/London", func.now()).cast(Date))
            & not_(cls.is_submitted)
        )

    __table_args__ = (
        CheckConstraint(
            "mode = 'TEST' OR grant_recipient_id IS NOT NULL",
            name="ck_grant_recipient_if_live",
        ),
    )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(reference={self.reference}, mode={self.mode})"


class Form(BaseModel):
    __tablename__ = "form"

    title: Mapped[str]
    order: Mapped[int]
    slug: Mapped[str]

    collection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("collection.id"))
    collection: Mapped[Collection] = relationship("Collection", back_populates="forms")

    __table_args__ = (
        UniqueConstraint("order", "collection_id", name="uq_form_order_collection", deferrable=True),
        UniqueConstraint("title", "collection_id", name="uq_form_title_collection"),
        UniqueConstraint("slug", "collection_id", name="uq_form_slug_collection"),
    )

    # support fetching all of a forms components so that the selectin loading strategy can make one
    # round trip to the database to optimise this further only load components flat like this and
    # manage nesting through properties rather than subsequent declarative queries
    _all_components: Mapped[OrderingList[Component]] = relationship(
        "Component",
        viewonly=True,
        order_by="Component.order",
        collection_class=ordering_list("order"),
        cascade="all, save-update, merge",
    )

    components: Mapped[OrderingList[Component]] = relationship(
        "Component",
        order_by="Component.order",
        collection_class=ordering_list("order"),
        primaryjoin="and_(Component.form_id==Form.id, Component.parent_id.is_(None))",
        cascade="all, save-update, merge",
    )

    def clear_caches(self):
        for attr, value in self.__class__.__dict__.items():
            if isinstance(value, cached_property):
                if attr in self.__dict__:
                    del self.__dict__[attr]

    @cached_property
    def cached_questions(self) -> list[Question]:
        """Consistently returns all questions in the form, respecting order and any level of nesting."""
        return [q for q in get_ordered_nested_components(self.components) if isinstance(q, Question)]

    @cached_property
    def cached_all_components(self) -> list[Component]:
        return get_ordered_nested_components(self.components)

    def global_component_index(self, component: Component) -> int:
        return self.cached_all_components.index(component)

    @property
    def earlier_forms(self) -> list[Form]:
        return [f for f in self.collection.forms if f.order < self.order]


def get_ordered_nested_components(components: list[Component]) -> list[Component]:
    """Recursively collects all components from a list of components, including nested components."""
    flat_components = []
    ordered_components = sorted(components, key=lambda c: c.order)
    for component in ordered_components:
        flat_components.append(component)
        if isinstance(component, Group):
            flat_components.extend(get_ordered_nested_components(component.components))
    return flat_components


class Component(BaseModel):
    __tablename__ = "component"

    text: Mapped[InterpolationStatement] = mapped_column(CIInterpolationStatementType())
    slug: Mapped[str]
    order: Mapped[int]
    hint: Mapped[InterpolationStatement | None]
    data_type: Mapped[QuestionDataType | None] = mapped_column(
        SqlEnum(
            QuestionDataType,
            name="question_data_type_enum",
            validate_strings=True,
        )
    )
    name: Mapped[CIStr]
    form_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("form.id"))
    presentation_options: Mapped[QuestionPresentationOptions] = mapped_column(
        default=QuestionPresentationOptions, server_default="{}"
    )
    data_options: Mapped[QuestionDataOptions] = mapped_column(
        default=QuestionDataOptions,
        server_default="{}",
        # TODO make this nullable=False in future migration - setting to True to allow zero downtime deployment
        nullable=True,
    )
    type: Mapped[ComponentType] = mapped_column(
        SqlEnum(ComponentType, name="component_type_enum", validate_strings=True), default=ComponentType.QUESTION
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("component.id"))
    data_source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("data_source.id"))
    guidance_heading: Mapped[str | None]
    guidance_body: Mapped[InterpolationStatement | None]
    add_another_guidance_body: Mapped[InterpolationStatement | None]
    add_another: Mapped[bool] = mapped_column(default=False)
    conditions_operator: Mapped[ConditionsOperator] = mapped_column(
        SqlEnum(ConditionsOperator, name="conditions_operator_enum", validate_strings=True),
        default=ConditionsOperator.ALL,
    )

    # Relationships
    # todo: reason about if this should actually back populate _all_components as they might not
    #       back populate the join condition
    form: Mapped[Form] = relationship("Form", back_populates="components")

    # todo: decide if these should be lazy loaded, eagerly joined or eagerly selectin
    expressions: Mapped[list[Expression]] = relationship(
        "Expression", back_populates="question", cascade="all, delete-orphan", order_by="Expression.created_at_utc"
    )
    data_source: Mapped[DataSource | None] = relationship(
        "DataSource",
        back_populates="questions",
        foreign_keys=[data_source_id],
    )
    parent: Mapped[Group] = relationship("Component", remote_side="Component.id", back_populates="components")
    components: Mapped[OrderingList[Component]] = relationship(
        "Component",
        back_populates="parent",
        cascade="all, save-update, merge",
        order_by="Component.order",
        collection_class=ordering_list("order"),
    )

    owned_component_references: Mapped[list[ComponentReference]] = relationship(
        "ComponentReference",
        back_populates="component",
        cascade="all, delete-orphan",
        foreign_keys="ComponentReference.component_id",
        order_by=lambda: (
            ComponentReference._sort_form_id,
            ComponentReference._sort_parent_id,
            ComponentReference._sort_order,
        ),
    )
    depended_on_by: Mapped[list[ComponentReference]] = relationship(
        "ComponentReference",
        back_populates="depends_on_component",
        # explicitly disable cascading deletes so that ComponentReference can protect the Component
        passive_deletes="all",
        foreign_keys="ComponentReference.depends_on_component_id",
        order_by=lambda: (
            ComponentReference._sort_form_id,
            ComponentReference._sort_parent_id,
            ComponentReference._sort_order,
        ),
    )

    @property
    def conditions(self) -> list[Expression]:
        return [expression for expression in self.expressions if expression.type_ == ExpressionType.CONDITION]

    def get_full_condition_chain(
        self, ignore_parents: bool = False
    ) -> list[tuple[ConditionsOperator, list[Expression]]]:
        """Returns a list of all of the conditions that this question depends on, eg:

        Q1 has no conditions (always asked)
        Q2 depends on Q1
        Group 1 (conditional on Q2):
            Q3
            Q4 depends on Q3

        Q4.get_full_condition_chain() == [Q4.condition, G1.condition, Q2.condition]
        Q4.get_full_condition_chain(ignore_parents=True) == [Q4.condition, Q2.condition]
        """
        conditions = []

        def _fetch_dependent_conditions(component: Component, visited: set[Component]) -> None:
            visited.add(component)

            if component.conditions:
                conditions.append((component.conditions_operator, component.conditions))

            for ocr in component.owned_component_references:
                if (
                    ocr.depends_on_component
                    and ocr.depends_on_component != component
                    and ocr.depends_on_component not in visited
                ):
                    _fetch_dependent_conditions(ocr.depends_on_component, visited)

        target_component: Component | None = self
        while target_component:
            _fetch_dependent_conditions(target_component, set())
            target_component = target_component.parent if not ignore_parents else None

        return list(reversed(conditions))  # starts with farthest parent, ends with this component

    @property
    def full_condition_chain(self) -> list[tuple[ConditionsOperator, list[Expression]]]:
        """
        Returns a list of all explicit groups of conditions that need to be evaluated in order to work out whether
        this component should be shown or not. This traverses component references as well, so if this component
        references a conditional component C2, C2's conditions will be included here.
        """
        return self.get_full_condition_chain(ignore_parents=False)

    @property
    def all_conditional_depended_on_components(self) -> set[Component]:
        """
        Returns a set of all components that this question depends on, walking up the full condition chain.

        This relies on component references, which means that it includes both explicitly-configured conditions (eg
        managed conditions) and implicit conditions (eg where a question interpolates the answer from another question
        into its text).
        """
        all_conditional_depended_on_components = {
            expr.component_references[0].component
            for _operator, _exprs in self.full_condition_chain
            for expr in _exprs
            if expr.component_references
        }
        return all_conditional_depended_on_components

    @property
    def is_self_conditional(self) -> bool:
        """
        Returns True if this component only has conditional requirements, either from self-owned
        conditions or from direct component references on components that are conditional.

        It does *not* check conditions on its parent chain. This is used to show the 'Conditional' tag on the
        `list questions` page; if we checked parents then every single question inside a conditional group would show
        the tag, which is not useful.
        """
        return len(self.get_full_condition_chain(ignore_parents=True)) > 0

    @property
    def validations(self) -> list[Expression]:
        return [expression for expression in self.expressions if expression.type_ == ExpressionType.VALIDATION]

    def get_expression(self, id: uuid.UUID) -> Expression:
        try:
            return next(expression for expression in self.expressions if expression.id == id)
        except StopIteration as e:
            raise ValueError(f"Could not find an expression with id={id} in question={self.id}") from e

    @property
    def container(self) -> Group | Form:
        return self.parent or self.form

    @property
    def is_group(self) -> bool:
        return isinstance(self, Group)

    @property
    def is_question(self) -> bool:
        return isinstance(self, Question)

    __table_args__ = (
        UniqueConstraint("order", "parent_id", "form_id", name="uq_component_order_form", deferrable=True),
        UniqueConstraint("slug", "form_id", name="uq_component_slug_form"),
        UniqueConstraint("text", "form_id", name="uq_component_text_form"),
        UniqueConstraint("name", "form_id", name="uq_component_name_form"),
        CheckConstraint(
            f"data_type IS NOT NULL OR type != '{ComponentType.QUESTION.value}'",
            name="ck_component_type_question_requires_data_type",
        ),
    )

    __mapper_args__ = {"polymorphic_on": type}

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(text={self.text}, is_group={self.is_group}, add_another={self.add_another})"

    # todo: this returns a question or a group or none and the types should reflect that
    #       the cleanest way to do this is probably to implement it on question and group models separately
    @property
    def add_another_container(self) -> Component | None:
        if self.add_another:
            return self

        add_another_parent = self.parent
        while add_another_parent and not add_another_parent.add_another:
            add_another_parent = add_another_parent.parent

        if add_another_parent and add_another_parent.add_another:
            return add_another_parent

        return None

    @property
    def data_reference_label(self) -> str:
        return f"{self.form.collection.name} → {self.form.title} → {self.name}"

    def is_descendant_of(self, component: Component) -> bool:
        # NOTE: This might want to live on something like a CollectionDependencyGraph in the near future
        #       eg in 577a7f75c049e9e3795111b34bd4350609d3f4b7
        parent = self.parent

        while parent:
            if parent == component:
                return True
            parent = parent.parent

        return False


class Question(Component, SafeQidMixin):
    __mapper_args__ = {"polymorphic_identity": ComponentType.QUESTION}

    if TYPE_CHECKING:
        # database constraints ensure the question component will have a data_type
        # we reflect that its required on the question component but don't hook in a competing migration
        data_type: QuestionDataType

    @property
    def question_id(self) -> uuid.UUID:
        """A small proxy to support SafeQidMixin so that logic can be centralised."""
        return self.id

    # START: Helper properties for populating `QuestionForm` instances
    @property
    def data_source_items(self) -> str | None:
        if self.data_type not in [QuestionDataType.RADIOS, QuestionDataType.CHECKBOXES]:
            return None

        assert self.data_source is not None

        if (
            self.presentation_options is not None
            and self.presentation_options.last_data_source_item_is_distinct_from_others
        ):
            return "\n".join(item.label for item in self.data_source.items[:-1])

        return "\n".join([item.label for item in self.data_source.items])

    @property
    def separate_option_if_no_items_match(self) -> bool | None:
        if self.data_type not in [QuestionDataType.RADIOS, QuestionDataType.CHECKBOXES]:
            return None

        return (
            self.presentation_options.last_data_source_item_is_distinct_from_others
            if self.presentation_options is not None
            else None
        )

    @property
    def none_of_the_above_item_text(self) -> str | None:
        if self.data_type not in [QuestionDataType.RADIOS, QuestionDataType.CHECKBOXES]:
            return None

        assert self.data_source is not None

        if (
            self.presentation_options is not None
            and self.presentation_options.last_data_source_item_is_distinct_from_others
        ):
            return self.data_source.items[-1].label

        return "Other"

    @property
    def rows(self) -> int | None:
        return (
            self.presentation_options.rows.value
            if self.data_type == QuestionDataType.TEXT_MULTI_LINE and self.presentation_options.rows
            else None
        )

    @property
    def word_limit(self) -> int | None:
        return self.presentation_options.word_limit if self.data_type == QuestionDataType.TEXT_MULTI_LINE else None

    @property
    def prefix(self) -> str | None:
        return self.presentation_options.prefix if self.data_type == QuestionDataType.NUMBER else None

    @property
    def suffix(self) -> str | None:
        return self.presentation_options.suffix if self.data_type == QuestionDataType.NUMBER else None

    @property
    def width(self) -> str | None:
        return (
            self.presentation_options.width.value
            if self.data_type == QuestionDataType.NUMBER and self.presentation_options.width
            else None
        )

    @property
    def number_type(self) -> NumberTypeEnum | None:
        return self.data_options.number_type if self.data_type == QuestionDataType.NUMBER else None

    @property
    def max_decimal_places(self) -> int | None:
        return (
            self.data_options.max_decimal_places
            if self.data_type == QuestionDataType.NUMBER and self.data_options.number_type == NumberTypeEnum.DECIMAL
            else None
        )

    @property
    def approximate_date(self) -> bool | None:
        return self.presentation_options.approximate_date if self.data_type == QuestionDataType.DATE else None

    @property
    def file_types_supported(self) -> list[FileUploadTypes] | None:
        return (
            (self.data_options.file_types_supported or [t for t in FileUploadTypes])
            if self.data_type == QuestionDataType.FILE_UPLOAD
            else None
        )

    @property
    def maximum_file_size(self) -> MaximumFileSize | None:
        return (
            (self.data_options.maximum_file_size or MaximumFileSize.SMALL)
            if self.data_type == QuestionDataType.FILE_UPLOAD
            else None
        )

    # END: Helper properties for populating `QuestionForm` instances


class Group(Component):
    __mapper_args__ = {"polymorphic_identity": ComponentType.GROUP}

    if TYPE_CHECKING:
        # reflect that groups will never have a data type but don't hook in a competing migration
        data_type: None

    def clear_caches(self):
        for attr, value in self.__class__.__dict__.items():
            if isinstance(value, cached_property):
                if attr in self.__dict__:
                    del self.__dict__[attr]

    # todo: rename to something that makes it clear this is processed, something like all_nested_questions
    @cached_property
    def cached_questions(self) -> list[Question]:
        return [q for q in get_ordered_nested_components(self.components) if isinstance(q, Question)]

    @cached_property
    def cached_all_components(self) -> list[Component]:
        return get_ordered_nested_components(self.components)

    @property
    def same_page(self) -> bool:
        return bool(self.presentation_options.show_questions_on_the_same_page) if self.presentation_options else False

    @cached_property
    def has_nested_groups(self) -> bool:
        return any([q for q in self.components if q.is_group])

    @classmethod
    def _count_nested_group_levels(cls, group: Group) -> int:
        if not group.parent:
            return 0
        return 1 + group._count_nested_group_levels(group=group.parent)

    @cached_property
    def nested_group_levels(self) -> int:
        return Group._count_nested_group_levels(group=self)

    @cached_property
    def can_have_child_group(self) -> bool:
        """Whether or not this groups is allowed to have a child group,
        based on the maximum number of levels of nested groups"""
        return bool(self.nested_group_levels < current_app.config["MAX_NESTED_GROUP_LEVELS"])

    @property
    def contains_add_another_components(self) -> bool:
        """Whether or not this group contains any components that have add_another set to True"""
        for component in self.cached_all_components:
            if component.add_another:
                return True
        return False

    @property
    def contains_questions_depended_on_elsewhere(self) -> bool:
        """Whether or not any questions in this group (or nested groups) are depended on elsewhere"""
        depended_on_outside_of_group_context = [
            component
            for component in self.cached_all_components
            # todo: sense check the lazy loading implications of this property
            for depends_on in component.depended_on_by
            if depends_on.component not in (set(self.cached_all_components).union({self}))
        ]
        return bool(depended_on_outside_of_group_context)

    @property
    def questions_in_add_another_summary(self) -> list[Question]:
        if not self.add_another:
            return []
        if self.presentation_options.add_another_summary_line_question_ids:
            return [
                question
                for question in self.cached_questions
                if question.id in self.presentation_options.add_another_summary_line_question_ids
            ] or self.cached_questions
        return self.cached_questions


class SubmissionEvent(BaseModel):
    __tablename__ = "submission_event"

    event_type: Mapped[SubmissionEventType] = mapped_column(
        SqlEnum(SubmissionEventType, name="submission_event_type_enum", validate_strings=True)
    )

    related_entity_id: Mapped[uuid.UUID]

    # properties are immutable and will be mapped to known pydantic models next
    data: Mapped[json_scalars] = mapped_column(server_default="{}")

    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submission.id"))
    submission: Mapped[Submission] = relationship("Submission", back_populates="events")

    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    created_by: Mapped[User] = relationship("User")


class Expression(BaseModel):
    __tablename__ = "expression"

    statement: Mapped[EvaluationStatement]

    context: Mapped[json_flat_scalars] = mapped_column(mutable_json_type(dbtype=JSONB, nested=True))

    type_: Mapped[ExpressionType] = mapped_column(
        "type", SqlEnum(ExpressionType, name="expression_type_enum", validate_strings=True)
    )

    managed_name: Mapped[ManagedExpressionsEnum | None] = mapped_column(
        SqlEnum(ManagedExpressionsEnum, name="managed_expression_enum", validate_strings=True, nullable=True)
    )

    # TODO: Rename this to `component_id` as expressions can be attached to groups as well now.
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("component.id"))
    question: Mapped[Component] = relationship("Component", back_populates="expressions")

    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    created_by: Mapped[User] = relationship("User")

    component_references: Mapped[list[ComponentReference]] = relationship(
        "ComponentReference",
        back_populates="expression",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index(
            "uq_type_validation_unique_key",
            "type",
            "question_id",
            "managed_name",
            postgresql_where=(
                f"type = '{ExpressionType.VALIDATION.value}'::expression_type_enum AND managed_name IS NOT NULL"
            ),
            unique=True,
        ),
        Index(
            "uq_type_condition_unique_question",
            "type",
            "question_id",
            "managed_name",
            text("(context ->> 'subject_reference')"),
            postgresql_where=(
                f"type = '{ExpressionType.CONDITION.value}'::expression_type_enum AND managed_name IS NOT NULL"
            ),
            unique=True,
        ),
    )

    @property
    def is_managed(self) -> bool:
        return bool(self.managed_name)

    @property
    def managed(self) -> ManagedExpression:
        if self.is_managed:
            return get_managed_expression(self)
        raise ValueError("This expression is not a managed expression and does not have a managed definition")

    @property
    def custom(self) -> CustomExpression:
        if self.is_custom:
            return get_custom_expression(self)
        raise ValueError("This expression is not a custom expression and does not have a custom definition")

    @property
    def evaluatable_expression(self) -> EvaluatableExpression:
        if self.is_custom:
            return self.custom
        else:
            return self.managed

    @property
    def is_custom(self) -> bool:
        return not self.is_managed

    @classmethod
    def from_evaluatable_expression(
        cls, evaluatable_expression: "EvaluatableExpression", expression_type: ExpressionType, created_by: "User"
    ) -> "Expression":
        return Expression(
            statement=evaluatable_expression.statement,
            context=evaluatable_expression.model_dump(mode="json"),
            created_by=created_by,
            type_=expression_type,
            managed_name=evaluatable_expression._key,
        )

    @property
    def required_functions(self) -> dict[str, Callable[[Any], Any] | type[Any]]:
        if self.managed_name:
            return self.managed.required_functions

        # In future, make this return a default list of functions for non-managed expressions
        return {}


class DataSource(BaseModel, SafeDidMixin):
    __tablename__ = "data_source"

    type: Mapped[DataSourceType] = mapped_column(
        SqlEnum(DataSourceType, name="data_source_type_enum", validate_strings=True), default=DataSourceType.CUSTOM
    )
    name: Mapped[CIStr | None]
    grant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("grant.id"))
    collection_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("collection.id"))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id"))
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id"))
    schema: Mapped[DataSourceSchema | None] = mapped_column(
        default=None,
        server_default=None,
    )
    file_metadata: Mapped[DataSourceFileMetadata | None] = mapped_column(
        default=None,
        server_default=None,
    )

    questions: Mapped[list[Question]] = relationship(
        "Question",
        back_populates="data_source",
        foreign_keys="Component.data_source_id",
    )
    grant: Mapped[Grant | None] = relationship("Grant")
    collection: Mapped[Collection | None] = relationship("Collection", back_populates="data_sources")
    created_by: Mapped[User | None] = relationship("User", foreign_keys=[created_by_id])
    updated_by: Mapped[User | None] = relationship("User", foreign_keys=[updated_by_id])

    items: Mapped[list[DataSourceItem]] = relationship(
        "DataSourceItem",
        back_populates="data_source",
        order_by="DataSourceItem.order",
        collection_class=ordering_list("order"),
        lazy="selectin",
        # Importantly we don't `delete-orphan` here; when we move choices around, we remove them from the collection,
        # which would trigger the delete-orphan rule
        cascade="all, save-update, merge",
    )

    # NOTE: This is a list of *all* organisation items for the data source and must be filtered down using the method
    # below to retrieve just the organisation item for a specific grant recipient when using this in the context of
    # a submission.
    organisation_items: Mapped[list[DataSourceOrganisationItem]] = relationship(
        "DataSourceOrganisationItem",
        back_populates="data_source",
        cascade="all, delete-orphan",
    )

    depended_on_by_columns: Mapped[list[ComponentReference]] = relationship(
        "ComponentReference",
        back_populates="depends_on_data_source",
        # explicitly disable cascading deletes so that ComponentReference can protect the DataSource
        passive_deletes="all",
        foreign_keys="ComponentReference.depends_on_data_source_id",
    )

    def get_filtered_organisation_item(self, organisation_external_id: str) -> DataSourceOrganisationItem | None:
        if not self.organisation_items:
            return None

        return next(
            filter(lambda org_item: org_item.external_id == organisation_external_id, self.organisation_items), None
        )

    def get_organisation_items_by_external_id(self) -> dict[str, DataSourceOrganisationItem]:
        return {item.external_id: item for item in self.organisation_items}

    def get_missing_data_organisations(self, grant_recipients: Sequence[GrantRecipient]) -> list[Organisation]:
        """
        Organisations, from the given grant recipients, that are missing from this data source's organisation items or
        have incomplete data in their organisation item.

        `grant_recipients` must already be loaded with their organisations (eg via
        `get_grant_recipients(grant, with_organisations=True)`) to avoid N+1 issues.
        """
        if self.type != DataSourceType.GRANT_RECIPIENT:
            return []

        assert self.schema, f"DataSource {self.id} has type {self.type} but no schema"

        schema_columns = set(self.schema.root.keys())
        items_by_external_id = self.get_organisation_items_by_external_id()
        missing_organisations = []
        for grant_recipient in grant_recipients:
            item = items_by_external_id.get(grant_recipient.organisation.external_id)
            if item is None or any(item._data.get(col) is None for col in schema_columns):
                missing_organisations.append(grant_recipient.organisation)
        return missing_organisations

    def get_referenced_column_names(self) -> set[str]:
        """
        Gets column names from this data source's schema that are referenced anywhere in the collection, either in
        component text/hint/preview or in a condition/validation expression.

        `depended_on_by_columns` should already be loaded (eg via `get_submission(..., with_full_schema=True)`)
        to avoid N+1 issues.
        """
        return {
            reference.depends_on_column_name
            for reference in self.depended_on_by_columns
            if reference.depends_on_column_name is not None
        }

    def has_missing_referenced_data_for_organisation(self, organisation_external_id: str) -> bool:
        """
        Returns bool for if this grant recipient organisation's item for this data source is missing any of the columns
        that are referenced elsewhere in the collection.

        Referenced-but-missing data means the report can't be safely rendered for this grant recipient organisation.

        `depended_on_by_columns` and `organisation_items` should already be loaded (eg via
        `get_submission(..., with_full_schema=True)`) to avoid N+1 issues.
        """
        referenced_columns = self.get_referenced_column_names()
        if not referenced_columns:
            return False

        item = self.get_filtered_organisation_item(organisation_external_id)
        return item is None or any(item._data.get(col) is None for col in referenced_columns)

    def get_removed_organisation_external_ids(self, grant_recipients: Sequence[GrantRecipient]) -> list[str]:
        """
        External IDs of organisation items on this data source that no longer belong to a live grant recipient.

        `grant_recipients` must already be loaded with their organisations (eg via
        `get_grant_recipients(grant, with_organisations=True)`) to avoid N+1 issues.
        """
        current_external_ids = {gr.organisation.external_id for gr in grant_recipients}
        return [item.external_id for item in self.organisation_items if item.external_id not in current_external_ids]

    __table_args__ = (
        CheckConstraint(
            (
                "type = 'CUSTOM' OR "
                "(name IS NOT NULL AND grant_id IS NOT NULL AND collection_id IS NOT NULL AND schema IS NOT NULL "
                "AND file_metadata IS NOT NULL)"
            ),
            name="ck_data_source_non_custom_requires_name_grant_collection_and_schema_and_file_metadata",
        ),
        CheckConstraint(
            "collection_id IS NULL OR grant_id IS NOT NULL",
            name="ck_data_source_collection_requires_grant",
        ),
        Index("ix_data_source_grant_id", "grant_id"),
        Index("ix_data_source_collection_id", "collection_id"),
        Index(
            "uq_data_source_name_collection",
            "name",
            "collection_id",
            postgresql_where="collection_id IS NOT NULL",
            unique=True,
        ),
    )

    @property
    def data_source_id(self) -> uuid.UUID:
        """A small proxy to support SafeDidMixin so that logic can be centralised."""
        return self.id

    def build_typed_org_item_data(
        self,
        data: dict[str, str | int | float | None],
    ) -> dict[str, DataSourceAnswerTypes | None]:
        """
        Transform raw DataSourceOrganisationItem data into typed answer models.

        2D (GRANT_RECIPIENT): dict -> dict[str, DataSourceAnswerTypes]

        The typed answers carry the presentation & data options (prefix, suffix etc.) so that we can call all the usual
        answer methods eg. get_value_for_interpolation().
        """
        if not self.schema:
            return {}

        return self._build_typed_data(data)

    def _build_typed_data(self, row: dict[str, str | int | float | None]) -> dict[str, DataSourceAnswerTypes | None]:
        """
        Build a dict of typed answer models from a single flat row.
        """
        if not self.schema or not self.schema.root:
            return {}
        return {
            column_name: self._build_answer_for_column(row.get(column_name), column_schema)
            for column_name, column_schema in self.schema.ordered_items()
        }

    def _build_answer_for_column(
        self,
        value: str | int | float | None,
        column_schema: DataSourceSchemaColumn,
    ) -> DataSourceAnswerTypes | None:
        """
        Build the appropriate typed answer for a single column value.
        """

        if value is None or (isinstance(value, str) and not value.strip()):
            return None

        match column_schema.data_type:
            case QuestionDataType.NUMBER:
                match column_schema.data_options.number_type:
                    case NumberTypeEnum.DECIMAL:
                        return DecimalAnswer(
                            value=Decimal(str(value)),
                            prefix=column_schema.presentation_options.prefix or None,
                            suffix=column_schema.presentation_options.suffix or None,
                        )
                    case NumberTypeEnum.INTEGER:
                        return IntegerAnswer(
                            value=int(value),
                            prefix=column_schema.presentation_options.prefix or None,
                            suffix=column_schema.presentation_options.suffix or None,
                        )
                    case _:
                        current_app.logger.error(
                            "Unsupported number_type [%(number_type)s] in column %(column_name)s",
                            {
                                "number_type": column_schema.data_options.number_type,
                                "column_name": column_schema.original_column_name,
                            },
                        )
                        raise ValueError(
                            f"Unsupported number_type {column_schema.data_options.number_type} "
                            f"for column {column_schema.original_column_name}"
                        )
            case QuestionDataType.TEXT_SINGLE_LINE:
                return TextSingleLineAnswer(str(value))
            case _:
                current_app.logger.error(
                    "Unsupported data_type [%(data_type)s] in column %(column_name)s",
                    {
                        "data_type": column_schema.data_type,
                        "column_name": column_schema.original_column_name,
                    },
                )
                raise ValueError(
                    f"Unsupported data_type {column_schema.data_type} for column {column_schema.original_column_name}"
                )

    def column_reference_label(self, column: DataSourceSchemaColumn) -> str | None:
        if self.type == DataSourceType.CUSTOM:
            return None
        return f"{column.original_column_name} from {self.name} data set"

    @hybrid_method
    def has_missing_data(self, grant_recipients: Sequence[GrantRecipient] | None = None) -> bool:
        """
        Whether any of the given grant recipients are missing from this data source, or have incomplete data.

        `grant_recipients` must already be the grant's current live grant recipients, loaded with their
        organisations (eg via `get_grant_recipients(grant, with_organisations=True)`), and is required when called
        in Python to avoid N+1 issues. See `get_missing_data_organisations` for the underlying list of organisations
        rather than just a bool.

        The SQL expression below checks the same two conditions (an empty column value, or a live grant
        recipient with no matching organisation item) directly, for use in interface queries eg.
        `select(DataSource).where(DataSource.has_missing_data())` - it ignores `grant_recipients`, which
        only exists here so this method's Python and SQL forms share a signature.
        """
        if grant_recipients is None:
            raise TypeError("has_missing_data() requires grant_recipients when called in Python")
        return bool(self.get_missing_data_organisations(grant_recipients))

    @has_missing_data.inplace.expression
    @classmethod
    def _has_missing_data_expression(
        cls, grant_recipients: Sequence[GrantRecipient] | None = None
    ) -> ColumnElement[bool]:
        has_null_or_empty_value = (
            select(DataSourceOrganisationItem.data_source_id)
            .where(
                DataSourceOrganisationItem.data_source_id == cls.id,
                or_(
                    # Check if _data is an empty object (eg. copied data set org items with no data)
                    DataSourceOrganisationItem._data == cast(text("'{}'"), JSONB),
                    func.jsonb_path_exists(
                        DataSourceOrganisationItem._data,
                        # JSONPath expression to check if any top-level value in the org item JSONB object is null
                        # $.* iterates all top-level values, ? (@ == null) filters to nulls
                        # ::jsonpath casts the string to Postgres jsonpath type
                        text("'$.* ? (@ == null)'::jsonpath"),
                    ),
                ),
            )
            .correlate(cls)
            .exists()
        )

        has_missing_grant_recipient = (
            select(GrantRecipient.id)
            .join(Organisation, GrantRecipient.organisation_id == Organisation.id)
            .outerjoin(
                DataSourceOrganisationItem,
                and_(
                    DataSourceOrganisationItem.data_source_id == cls.id,
                    DataSourceOrganisationItem.external_id == Organisation.external_id,
                ),
            )
            .where(
                GrantRecipient.grant_id == cls.grant_id,
                GrantRecipient.mode == GrantRecipientModeEnum.LIVE,
                Organisation.mode == OrganisationModeEnum.LIVE,
                DataSourceOrganisationItem.id.is_(None),
            )
            .correlate(cls)
            .exists()
        )

        return and_(
            cls.type != DataSourceType.CUSTOM,
            has_null_or_empty_value | has_missing_grant_recipient,
        )


class DataSourceItem(BaseModel):
    __tablename__ = "data_source_item"

    data_source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_source.id"))
    order: Mapped[int]
    key: Mapped[CIStr]
    label: Mapped[str]

    data_source: Mapped[DataSource] = relationship("DataSource", back_populates="items", uselist=False)
    component_references: Mapped[list[ComponentReference]] = relationship(
        "ComponentReference",
        back_populates="depends_on_data_source_item",
        # explicitly disable cascading deletes so that ComponentReference can protect the DataSourceItems
        passive_deletes="all",
    )

    __table_args__ = (
        UniqueConstraint("data_source_id", "order", name="uq_data_source_id_order", deferrable=True),
        UniqueConstraint("data_source_id", "key", name="uq_data_source_id_key"),
    )


class DataSourceOrganisationItem(BaseModel):
    __tablename__ = "data_source_organisation_item"

    data_source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_source.id", ondelete="CASCADE"))
    external_id: Mapped[str]

    _data: Mapped[json_flat_scalars] = mapped_column("data", mutable_json_type(dbtype=JSONB, nested=True), default=dict)

    data_source: Mapped[DataSource] = relationship("DataSource", back_populates="organisation_items")

    __table_args__ = (
        UniqueConstraint("data_source_id", "external_id", name="uq_data_source_external_id"),
        Index("ix_data_source_organisation_item_data_source_id", "data_source_id"),
        Index("ix_data_source_organisation_item_external_id", "external_id"),
    )

    @property
    def data(self) -> dict[str, DataSourceAnswerTypes | None]:
        """
        Returns raw data as typed answer models via the parent DataSource schema.

        2D (GRANT_RECIPIENT): dict[str, DataSourceAnswerTypes]
        """
        return self.data_source.build_typed_org_item_data(self._data)


class ComponentReference(BaseModel):
    """A table to track when components (and their expressions) create a dependency upon another component
    or an uploaded reference-dataset column.

    As of creating this table, the common examples are:

    q2 has a condition (c) that checks the answer to q1 to decide if q2 should be shown:
      => ComponentReference(component_id=q2.id, expression_id=c.id, depends_on_component_id=q1.id)

    q2 has text that shows the answer to q1:
      => ComponentReference(component_id=q2.id, expression_id=None, depends_on_component_id=q1.id)

    q2 has text that shows a column value from an uploaded reference dataset d1:
      => ComponentReference(component_id=q2.id, expression_id=None,
                            depends_on_data_source_id=d1.id, depends_on_column_name="c_allocation")
    """

    __tablename__ = "component_reference"

    component_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("component.id"))
    component: Mapped[Component] = relationship(
        "Component", foreign_keys=[component_id], back_populates="owned_component_references"
    )

    expression_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("expression.id"))
    expression: Mapped[Expression | None] = relationship("Expression")

    depends_on_component_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("component.id"))
    depends_on_component: Mapped[Component | None] = relationship(
        "Component", foreign_keys=[depends_on_component_id], back_populates="depended_on_by"
    )

    # NOTE: When pointing at a CUSTOM data source item, we also store `depends_on_component_id` - maybe we shouldn't?
    #       When we add STATIC data sources, it would be nice for CUSTOM+STATIC to be treated the same in terms of
    #       component references?
    depends_on_data_source_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("data_source_item.id"))
    depends_on_data_source_item: Mapped[DataSourceItem | None] = relationship("DataSourceItem")

    depends_on_data_source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("data_source.id", ondelete="RESTRICT")
    )
    depends_on_data_source: Mapped[DataSource | None] = relationship(
        "DataSource", back_populates="depended_on_by_columns"
    )
    # NOTE: should we store dataset columns in a separate table so we can link to specific FKs here for more in-depth
    #       integrity checks?
    depends_on_column_name: Mapped[str | None]

    __table_args__ = (
        # A reference points at exactly one target kind: either a component (optionally paired with a
        # specific data-source item for CUSTOM radio choices), or a data-source column.
        CheckConstraint(
            "(depends_on_component_id IS NOT NULL) != (depends_on_data_source_id IS NOT NULL)",
            name="ck_component_reference_component_xor_data_source",
        ),
        CheckConstraint(
            "depends_on_data_source_item_id IS NULL OR depends_on_component_id IS NOT NULL",
            name="ck_component_reference_item_requires_component",
        ),
        CheckConstraint(
            "(depends_on_data_source_id IS NULL) = (depends_on_column_name IS NULL)",
            name="ck_component_reference_data_source_requires_column",
        ),
    )

    # Mirror columns from the referenced component for ordering the Component.component_references relationship.
    # Column-level references (depends_on_data_source_id set) leave these NULL — they don't participate in
    # form ordering.
    _sort_form_id: Mapped[uuid.UUID | None] = column_property(
        select(Component.form_id).where(Component.id == foreign(depends_on_component_id)).scalar_subquery()
    )
    _sort_parent_id: Mapped[uuid.UUID | None] = column_property(
        select(Component.parent_id).where(Component.id == foreign(depends_on_component_id)).scalar_subquery()
    )
    _sort_order: Mapped[int | None] = column_property(
        select(Component.order).where(Component.id == foreign(depends_on_component_id)).scalar_subquery()
    )


class GrantRecipient(BaseModel):
    __tablename__ = "grant_recipient"

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisation.id"))
    grant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("grant.id"))
    mode: Mapped[GrantRecipientModeEnum] = mapped_column(default=GrantRecipientModeEnum.LIVE)
    status: Mapped[GrantRecipientStatusEnum]

    organisation: Mapped[Organisation] = relationship("Organisation")
    grant: Mapped[Grant] = relationship("Grant", back_populates="grant_recipients")

    submissions: Mapped[list[Submission]] = relationship("Submission", back_populates="grant_recipient")

    users: Mapped[list[User]] = relationship(
        "User",
        secondary="user_role",
        primaryjoin=lambda: GrantRecipient.organisation_id == UserRole.organisation_id,
        secondaryjoin=lambda: and_(User.id == UserRole.user_id, UserRole.grant_id == foreign(GrantRecipient.grant_id)),
        viewonly=True,
        lazy="select",  # TODO: FSPT-977 raiseload, decide joining method explicitly?
    )

    data_providers: Mapped[list[User]] = relationship(
        "User",
        secondary="user_role",
        primaryjoin=lambda: and_(
            GrantRecipient.organisation_id == UserRole.organisation_id,
            or_(UserRole.grant_id.is_(None), UserRole.grant_id == GrantRecipient.grant_id),
            UserRole.permissions.contains([RoleEnum.DATA_PROVIDER]),
        ),
        secondaryjoin=lambda: UserRole.user_id == User.id,
        viewonly=True,
        lazy="select",  # TODO: FSPT-977 raiseload, decide joining method explicitly?
    )

    _all_certifiers: Mapped[list[User]] = relationship(
        "User",
        secondary="user_role",
        primaryjoin=lambda: and_(
            GrantRecipient.organisation_id == UserRole.organisation_id,
            or_(UserRole.grant_id.is_(None), UserRole.grant_id == GrantRecipient.grant_id),
            UserRole.permissions.contains([RoleEnum.CERTIFIER]),
        ),
        secondaryjoin=lambda: UserRole.user_id == User.id,
        viewonly=True,
        lazy="select",  # TODO: FSPT-977 raiseload, decide joining method explicitly?
    )

    @property
    def certifiers(self) -> Sequence[User]:
        """Filters down to the preferred certifiers for this grant recipient.

        Preferred certifiers have specific certifier permissions for this grant, rather than at the organisation-level.
        """
        preferred_certifiers = []
        for certifier in self._all_certifiers:
            for role in certifier.roles:
                if (
                    role.organisation_id == self.organisation_id
                    and role.grant_id == self.grant_id
                    and RoleEnum.CERTIFIER in role.permissions
                ):
                    preferred_certifiers.append(role.user)
                    break

        return preferred_certifiers or self._all_certifiers

    @property
    def unique_data_providers_and_certifiers(self) -> set[User]:
        return set(self.data_providers + list(self.certifiers))

    @property
    def certifier_names(self) -> str:
        names = [certifier.name for certifier in self.certifiers]
        if not names:
            return "Your certifier"

        return comma_join_items(names, join_word="or")

    @property
    def submission_mode(self) -> SubmissionModeEnum:
        return SubmissionModeEnum(self.mode.value)


class ReleaseNote(BaseModel):
    __tablename__ = "release_note"

    title: Mapped[str]
    content: Mapped[str]
    release_date: Mapped[datetime.date]
    is_published: Mapped[bool] = mapped_column(default=False)
