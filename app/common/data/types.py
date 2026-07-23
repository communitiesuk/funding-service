import datetime
import enum
import typing
from collections.abc import Callable
from enum import IntEnum
from typing import TYPE_CHECKING, Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, RootModel
from sqlalchemy import TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB

if TYPE_CHECKING:
    from app.common.collections.runner import FormRunner
    from app.common.data.models import Form, Question
    from app.deliver_grant_funding.forms import GroupDisplayOptionsForm, QuestionForm

scalars = str | int | float | bool | None
json_scalars = dict[str, Any]
json_flat_scalars = dict[str, scalars]


class GrantStatusEnum(enum.StrEnum):
    DRAFT = "draft"
    ONBOARDING = "onboarding"
    LIVE = "live"


class OrganisationStatus(enum.StrEnum):
    ACTIVE = "active"
    RETIRED = "retired"


class OrganisationType(enum.StrEnum):
    CENTRAL_GOVERNMENT = "Central Government"
    UNITARY_AUTHORITY = "Unitary Authority"
    SHIRE_DISTRICT = "Shire District"
    METROPOLITAN_DISTRICT = "Metropolitan District"
    LONDON_BOROUGH = "London Borough"
    SHIRE_COUNTY = "Shire County"
    COMBINED_AUTHORITY = "Combined Authority"
    NORTHERN_IRELAND_AUTHORITY = "Northern Ireland District"
    SCOTTISH_UNITARY_AUTHORITY = "Scottish Unitary Authority"
    WELSH_UNITARY_AUTHORITY = "Welsh Unitary Authority"
    CHARITY = "Charity"
    COMPANY = "Company"
    OTHER = "Other"

    @property
    def typed_id_field(self) -> str:
        """The Organisation column that stores this type's canonical identifier."""
        if self == OrganisationType.CENTRAL_GOVERNMENT:
            return "iati_id"
        if self in _LOCAL_AUTHORITY_TYPES:
            return "ons_lad_id"
        if self == OrganisationType.CHARITY:
            return "charity_commission_number"
        if self == OrganisationType.COMPANY:
            return "companies_house_number"
        return "custom_code"

    @property
    def external_id_prefix(self) -> str | None:
        """Prefix prepended to the typed ID to form external_id, or None if external_id == typed_id."""
        return _EXTERNAL_ID_PREFIXES.get(self)


_LOCAL_AUTHORITY_TYPES = frozenset(
    [
        OrganisationType.UNITARY_AUTHORITY,
        OrganisationType.SHIRE_DISTRICT,
        OrganisationType.METROPOLITAN_DISTRICT,
        OrganisationType.LONDON_BOROUGH,
        OrganisationType.SHIRE_COUNTY,
        OrganisationType.COMBINED_AUTHORITY,
        OrganisationType.NORTHERN_IRELAND_AUTHORITY,
        OrganisationType.SCOTTISH_UNITARY_AUTHORITY,
        OrganisationType.WELSH_UNITARY_AUTHORITY,
    ]
)

_EXTERNAL_ID_PREFIXES: dict[OrganisationType, str] = {
    OrganisationType.CHARITY: "CC-",  # Charities Commission
    OrganisationType.COMPANY: "CH-",  # Companies House
    OrganisationType.OTHER: "FS-",  # Funding Service
}


# TODO: Rename PermissionEnum
class RoleEnum(enum.StrEnum):
    # TODO: new 'PLATFORM_ADMIN' role that specifically only grants access to our admin panel?
    ADMIN = (
        "admin"  # Admin level permissions, combines with null columns in UserRole table to denote level of admin access
    )
    # TODO: rename to 'read/view' to better reflect what access it gives?
    MEMBER = "member"  # Basic read level permissions
    DATA_PROVIDER = "data-provider"
    CERTIFIER = "certifier"
    GRANT_LIFECYCLE_MANAGER = "grant-lifecycle-manager"
    DATA_ANALYST = "data-analyst"

    @staticmethod
    def get_access_grant_funding_roles() -> tuple[RoleEnum, ...]:
        return RoleEnum.DATA_PROVIDER, RoleEnum.CERTIFIER


class AuthMethodEnum(str, enum.Enum):
    SSO = "sso"
    MAGIC_LINK = "magic link"


class QuestionDataType(enum.StrEnum):
    # NOTE: Changing any of the values here may require a database migration due to the text forming part of
    # the config on `DataSource.schema` for eg grant recipient data sources
    TEXT_SINGLE_LINE = "Single line of text"
    TEXT_MULTI_LINE = "Multiple lines of text"
    EMAIL = "Email address"
    # todo: should we call this "A URL" or "A website address"
    URL = "Website address (URL)"
    NUMBER = "A number"
    YES_NO = "Yes or no"
    RADIOS = "Select one from a list (radios)"
    CHECKBOXES = "Select one or more from a list (checkboxes)"
    DATE = "A date"
    FILE_UPLOAD = "File upload"

    @staticmethod
    def coerce(value: Any) -> QuestionDataType:
        if isinstance(value, QuestionDataType):
            return value
        if isinstance(value, str):
            return QuestionDataType[value]
        raise ValueError(f"Cannot coerce {value} to QuestionDataType")


class SubmissionModeEnum(enum.StrEnum):
    TEST = "test"
    PREVIEW = "preview"
    LIVE = "live"

    @staticmethod
    def from_similar(mode: GrantRecipientModeEnum | OrganisationModeEnum) -> SubmissionModeEnum:
        return SubmissionModeEnum(mode.value)


class OrganisationModeEnum(enum.StrEnum):
    LIVE = "live"
    TEST = "test"

    @staticmethod
    def from_similar(mode: GrantRecipientModeEnum | SubmissionModeEnum) -> OrganisationModeEnum:
        return OrganisationModeEnum(mode.value)


class GrantRecipientModeEnum(enum.StrEnum):
    LIVE = "live"
    TEST = "test"

    @staticmethod
    def from_similar(mode: OrganisationModeEnum | SubmissionModeEnum) -> GrantRecipientModeEnum:
        return GrantRecipientModeEnum(mode.value)


class GrantRecipientStatusEnum(enum.StrEnum):
    APPLYING = "applying"
    ALLOCATED = "allocated"
    AWARDED = "awarded"


class SubmissionStatusEnum(enum.StrEnum):
    NOT_STARTED = "Not started"
    IN_PROGRESS = "In progress"
    READY_TO_SUBMIT = "Ready to submit"
    AWAITING_SIGN_OFF = "Awaiting sign off"
    SUBMITTED = "Submitted"
    NOT_SUBMITTED = "Not submitted"
    PARTIALLY_SUBMITTED = "Partially submitted"
    CHANGES_REQUESTED = "Changes requested"
    SUBMITTED_WITH_CHANGES = "Submitted with changes"


class SubmissionAssessmentStatusEnum(enum.StrEnum):
    NOT_STARTED = "Not started"
    MARKED_AS_APPROVED = "Marked as approved"
    MARKED_AS_REJECTED = "Marked as rejected"


SUBMITTED_STATUSES = (SubmissionStatusEnum.SUBMITTED, SubmissionStatusEnum.SUBMITTED_WITH_CHANGES)
IN_PROGRESS_STATUSES = (SubmissionStatusEnum.IN_PROGRESS, SubmissionStatusEnum.CHANGES_REQUESTED)


class TasklistSectionStatusEnum(enum.StrEnum):
    CANNOT_START_YET = "Cannot start yet"
    NOT_STARTED = "Not started"
    IN_PROGRESS = "In progress"
    COMPLETED = "Completed"
    NO_QUESTIONS = "No questions"
    NOT_NEEDED = "Not needed"
    CHANGES_REQUESTED = "Changes requested"
    CHANGES_MADE = "Changes made"


COMPLETE_TASKLIST_SECTION_STATUSES = (
    TasklistSectionStatusEnum.COMPLETED,
    TasklistSectionStatusEnum.CHANGES_MADE,
    TasklistSectionStatusEnum.NOT_NEEDED,
)
IN_PROGRESS_TASKLIST_SECTION_STATUSES = (
    TasklistSectionStatusEnum.IN_PROGRESS,
    TasklistSectionStatusEnum.CHANGES_REQUESTED,
)
NOT_NEEDED_TASKLIST_SECTION_STATUSES = (TasklistSectionStatusEnum.NOT_NEEDED,)


class SubmissionEventType(enum.StrEnum):
    FORM_RUNNER_FORM_COMPLETED = "Form completed"
    FORM_RUNNER_FORM_RESET_TO_IN_PROGRESS = "Form reset to in progress"
    FORM_RUNNER_FORM_RESET_BY_CERTIFIER = "Form reset by certifier"
    SUBMISSION_SENT_FOR_CERTIFICATION = "Submission sent for certification"
    SUBMISSION_DECLINED_BY_CERTIFIER = "Submission declined by certifier"
    SUBMISSION_APPROVED_BY_CERTIFIER = "Submission approved by certifier"
    SUBMISSION_SUBMITTED = "Submission submitted"
    SUBMISSION_REOPENED = "Submission reopened"
    SUBMISSION_CHANGES_REQUESTED = "Submission changes requested"
    ASSESSOR_MARKED_AS_APPROVED = "Assessor marked as approved"
    ASSESSOR_MARKED_AS_REJECTED = "Assessor marked as rejected"


class CollectionTypeConstants(typing.NamedTuple):
    singular: str
    plural: str
    active_nav: str
    list_endpoint: str
    slug: str


monitoring_report_constants = CollectionTypeConstants(
    singular="report",
    plural="reports",
    active_nav="reports",
    list_endpoint="deliver_grant_funding.list_reports",
    slug="reports",
)

application_constants = CollectionTypeConstants(
    singular="form",
    plural="forms",
    active_nav="pre_award",
    list_endpoint="deliver_grant_funding.list_pre_award_forms",
    slug="applications",
)


class CollectionType(enum.StrEnum):
    MONITORING_REPORT = "monitoring report"
    APPLICATION = "application"

    @property
    def constants(self) -> CollectionTypeConstants:
        match self:
            case CollectionType.APPLICATION:
                return application_constants
            case CollectionType.MONITORING_REPORT:
                return monitoring_report_constants
            case _:
                raise ValueError(f"No constants defined for {self=}")

    @staticmethod
    def from_slug(slug: str) -> "CollectionType":
        match slug:
            case "applications":
                return CollectionType.APPLICATION
            case "reports":
                return CollectionType.MONITORING_REPORT
            case _:
                raise ValueError(f"No collection type defined for {slug=}")


PRE_AWARD_COLLECTIONS = frozenset([CollectionType.APPLICATION])
MONITORING_COLLECTIONS = frozenset([CollectionType.MONITORING_REPORT])


class CollectionAdminEmailTypeEnum(enum.StrEnum):
    COLLECTION_OPEN_NOTIFICATION = "collection-open-notification"
    DEADLINE_REMINDER = "deadline-reminder"
    COLLECTION_OVERDUE = "collection-overdue"
    COLLECTION_CLOSED_NOTIFICATION = "collection-closed-notification"


class CollectionStatusEnum(enum.StrEnum):
    DRAFT = "Draft"
    SCHEDULED = "Scheduled to open"
    OPEN = "Open"
    CLOSED = "Closed"

    def __lt__(self, other: str) -> bool:
        if not isinstance(other, CollectionStatusEnum):
            return NotImplemented
        ordered_list_of_names = CollectionStatusEnum._member_names_
        return ordered_list_of_names.index(self.name) < ordered_list_of_names.index(other.name)

    def __gt__(self, other: str) -> bool:
        if not isinstance(other, CollectionStatusEnum):
            return NotImplemented
        ordered_list_of_names = CollectionStatusEnum._member_names_
        return ordered_list_of_names.index(self.name) > ordered_list_of_names.index(other.name)


class ExpressionType(enum.StrEnum):
    CONDITION = "CONDITION"
    VALIDATION = "VALIDATION"


class TraceLevelEnum(enum.StrEnum):
    TRACE = "sentry tracing"
    PROFILE = "sentry profiling"
    DEBUG_LOGGING = "debug logging"


class ComponentVisibilityState(enum.Enum):
    VISIBLE = "visible"  # Conditions evaluated to True
    HIDDEN = "hidden"  # Conditions evaluated to False (definitive)
    UNDETERMINED = "undetermined"  # Conditions couldn't evaluate (missing data)


class ConditionsOperator(enum.StrEnum):
    ALL = "ALL"
    ANY = "ANY"


class ManagedExpressionsEnum(enum.StrEnum):
    GREATER_THAN = "Greater than"
    LESS_THAN = "Less than"
    BETWEEN = "Between"
    IS_YES = "Yes"
    IS_NO = "No"
    ANY_OF = "Any of"
    SPECIFICALLY = "Specifically"
    IS_BEFORE = "Is before"
    IS_AFTER = "Is after"
    BETWEEN_DATES = "Between dates"
    UK_POSTCODE = "UK postcode"


class FormRunnerState(enum.StrEnum):
    TASKLIST = "tasklist"
    QUESTION = "question"
    CHECK_YOUR_ANSWERS = "check-your-answers"
    VIEW_REPORT_PAGE = "view-report-page"


TRunnerUrlMapCallable = Callable[
    [
        "FormRunner",
        Optional["Question"],
        Optional["Form"],
        Optional["FormRunnerState"],
        Optional[int],
        Optional[str],
        Optional[int],
    ],
    str,
]


TRunnerUrlMap = typing.TypedDict(
    "TRunnerUrlMap",
    {
        FormRunnerState.TASKLIST: TRunnerUrlMapCallable,  # ty: ignore[invalid-argument-type]
        FormRunnerState.QUESTION: TRunnerUrlMapCallable,  # ty: ignore[invalid-argument-type]
        FormRunnerState.CHECK_YOUR_ANSWERS: TRunnerUrlMapCallable,  # ty: ignore[invalid-argument-type]
        FormRunnerState.VIEW_REPORT_PAGE: TRunnerUrlMapCallable,  # ty: ignore[invalid-argument-type]
    },
)


class MultilineTextInputRows(IntEnum):
    SMALL = 3
    MEDIUM = 5
    LARGE = 10


class NumberInputWidths(enum.StrEnum):
    HUNDREDS = "govuk-input--width-3"
    THOUSANDS = "govuk-input--width-4"
    MILLIONS = "govuk-input--width-5"
    BILLIONS = "govuk-input--width-10"


# for now this is just used by the form but this could also be used to serialise the
# value used in the question presentation options and provide a consistent human readable value
class GroupDisplayOptions(enum.StrEnum):
    ONE_QUESTION_PER_PAGE = "one-question-per-page"
    ALL_QUESTIONS_ON_SAME_PAGE = "all-questions-on-same-page"


class NumberTypeEnum(enum.StrEnum):
    INTEGER = "Whole number"
    DECIMAL = "Decimal number"


class MaximumFileSize(enum.StrEnum):
    SMALL = "Small"
    MEDIUM = "Medium"
    LARGE = "Large"

    @property
    def human_readable(self) -> str:
        return {
            MaximumFileSize.SMALL: "7MB",
            MaximumFileSize.MEDIUM: "30MB",
            MaximumFileSize.LARGE: "100MB",
        }[self]

    @property
    def max_bytes(self) -> int:
        return {
            MaximumFileSize.SMALL: 7 * 1024 * 1024,
            MaximumFileSize.MEDIUM: 30 * 1024 * 1024,
            MaximumFileSize.LARGE: 100 * 1024 * 1024,
        }[self]


class FileUploadTypes(enum.StrEnum):
    CSV = "CSV"
    IMAGE = "image"
    SPREADSHEET = "Microsoft Excel Spreadsheet"
    DOCUMENT = "Microsoft Word Document"
    PDF = "PDF"
    TEXT = "text"

    @property
    def extensions(self) -> list[str]:
        return {
            FileUploadTypes.CSV: [".csv"],
            FileUploadTypes.IMAGE: [".jpeg", ".jpg", ".png"],
            FileUploadTypes.SPREADSHEET: [".xlsx"],
            FileUploadTypes.DOCUMENT: [".docx", ".doc"],
            FileUploadTypes.PDF: [".pdf"],
            FileUploadTypes.TEXT: [".json", ".odt", ".rtf", ".txt"],
        }[self]

    @property
    def mime_types(self) -> list[str]:
        return {
            FileUploadTypes.CSV: ["text/csv"],
            FileUploadTypes.IMAGE: ["image/jpeg", "image/png"],
            FileUploadTypes.SPREADSHEET: ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"],
            FileUploadTypes.DOCUMENT: [
                "application/msword",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ],
            FileUploadTypes.PDF: ["application/pdf"],
            FileUploadTypes.TEXT: [
                "application/json",
                "application/vnd.oasis.opendocument.text",
                "application/rtf",
                "text/plain",
            ],
        }[self]


class QuestionPresentationOptions(BaseModel):
    # This is for radios (and maybe checkboxes) question types; the last item will be separated from the rest of the
    # data source items, visually by an 'or' break. It is meant to indicate that Other options are
    # appropriate and the user needs to fallback to some kind of 'not known' / 'Other' instead.
    last_data_source_item_is_distinct_from_others: bool | None = None

    # Multi-line text input
    # https://design-system.service.gov.uk/components/textarea/#use-appropriately-sized-textareas
    rows: MultilineTextInputRows | None = None
    # https://design-system.service.gov.uk/components/character-count/
    word_limit: int | None = None

    # Integer
    prefix: str | None = None
    suffix: str | None = None
    # https://design-system.service.gov.uk/components/text-input/#fixed-width-inputs
    width: NumberInputWidths | None = None

    # Groups
    show_questions_on_the_same_page: bool | None = None
    add_another_summary_line_question_ids: list[UUID] | None = None

    # Dates
    approximate_date: bool | None = None

    @staticmethod
    def from_question_form(form: QuestionForm) -> QuestionPresentationOptions:
        match form._question_type:
            case QuestionDataType.RADIOS | QuestionDataType.CHECKBOXES:
                return QuestionPresentationOptions(
                    last_data_source_item_is_distinct_from_others=form.separate_option_if_no_items_match.data
                )
            case QuestionDataType.TEXT_MULTI_LINE:
                return QuestionPresentationOptions(
                    rows=form.rows.data,
                    word_limit=form.word_limit.data,
                )
            case QuestionDataType.NUMBER:
                return QuestionPresentationOptions(
                    prefix=form.prefix.data,
                    suffix=form.suffix.data,
                    width=form.width.data,
                )
            case QuestionDataType.DATE:
                return QuestionPresentationOptions(approximate_date=form.approximate_date.data)
            case _:
                return QuestionPresentationOptions()

    @staticmethod
    def from_group_form(form: GroupDisplayOptionsForm) -> QuestionPresentationOptions:
        return QuestionPresentationOptions(
            show_questions_on_the_same_page=form.show_questions_on_the_same_page.data
            == GroupDisplayOptions.ALL_QUESTIONS_ON_SAME_PAGE
        )


class QuestionDataOptions(BaseModel):
    # numbers
    number_type: NumberTypeEnum | None = None
    max_decimal_places: int | None = None

    # file uploads
    file_types_supported: list[FileUploadTypes] | None = None
    maximum_file_size: MaximumFileSize | None = None

    @staticmethod
    def from_question_form(form: QuestionForm) -> QuestionDataOptions:
        match form._question_type:
            case QuestionDataType.NUMBER:
                return QuestionDataOptions(
                    number_type=form.number_type.data, max_decimal_places=form.max_decimal_places.data
                )
            case QuestionDataType.FILE_UPLOAD:
                return QuestionDataOptions(
                    file_types_supported=form.file_types_supported.data,
                    maximum_file_size=form.maximum_file_size.data,
                )
            case _:
                return QuestionDataOptions()


class QuestionOptionsPostgresType(TypeDecorator):
    impl = JSONB

    cache_ok = False

    def process_bind_param(self, value: BaseModel | None, dialect: Any) -> Any:
        if value is None:
            return None
        return value.model_dump(mode="json", exclude_none=True)

    def process_result_value(self, value: typing.Any, dialect: Any) -> QuestionPresentationOptions | None:
        if value is None:
            return None
        return QuestionPresentationOptions(**value)


class QuestionDataOptionsPostgresType(TypeDecorator):
    impl = JSONB

    cache_ok = False

    def process_bind_param(self, value: BaseModel | None, dialect: Any) -> Any:
        if value is None:
            return None
        return value.model_dump(mode="json", exclude_none=True)

    def process_result_value(self, value: typing.Any, dialect: Any) -> QuestionDataOptions | None:
        if value is None:
            return None
        return QuestionDataOptions(**value)


class ComponentType(enum.StrEnum):
    QUESTION = "QUESTION"
    GROUP = "GROUP"


class OrganisationData(BaseModel):
    external_id: str
    name: str
    type: OrganisationType
    active_date: datetime.date | None
    retirement_date: datetime.date | None
    iati_id: str | None = None
    ons_lad_id: str | None = None
    companies_house_number: str | None = None
    charity_commission_number: str | None = None
    custom_code: str | None = None


class AuditEventType(enum.Enum):
    PLATFORM_ADMIN_DB_EVENT = "platform-admin-db-event"
    SYSTEM = "system"


class DataSourceType(enum.StrEnum):
    CUSTOM = "Custom"
    GRANT_RECIPIENT = "Grant recipient"


class DataSourceSchemaColumn(BaseModel):
    data_type: Literal[QuestionDataType.TEXT_SINGLE_LINE, QuestionDataType.NUMBER]
    presentation_options: QuestionPresentationOptions
    data_options: QuestionDataOptions
    original_column_name: str
    order: int | None = None


class DataSourceSchema(RootModel[dict[str, DataSourceSchemaColumn]]):
    def ordered_items(self) -> list[tuple[str, DataSourceSchemaColumn]]:
        # Historically, columns didn't preserve order, so we add backwards compatability for None values
        return sorted(
            self.root.items(),
            key=lambda item: (
                item[1].order is None,
                item[1].order if item[1].order is not None else 0,
            ),
        )

    def ordered_values(self) -> list[DataSourceSchemaColumn]:
        return [column for _, column in self.ordered_items()]


class DataSourceFileTagEnum(enum.StrEnum):
    PENDING = "pending"
    IN_USE = "in_use"


class DataSourceFileMetadata(BaseModel):
    s3_key: str
    original_filename: str


TUnvalidatedDataSetRow = dict[str, str]
TUnvalidatedDataSetRows = list[TUnvalidatedDataSetRow]
TDataSetPreviewData = dict[str, list[str]]


class GrantRecipientMismatch(BaseModel):
    row_number: int
    external_id: str
    csv_organisation_name: str
    service_organisation_name: str


class DataSourceFileMetadataPostgresType(TypeDecorator):
    impl = JSONB
    cache_ok = False

    def process_bind_param(self, value: DataSourceFileMetadata | None, dialect: Any) -> dict[str, str] | None:
        if value is None:
            return None
        return value.model_dump(mode="json", exclude_none=True)

    def process_result_value(self, value: Any, dialect: Any) -> DataSourceFileMetadata | None:
        if value is None:
            return None
        return DataSourceFileMetadata.model_validate(value)


class DataSourceSchemaPostgresType(TypeDecorator):
    impl = JSONB
    cache_ok = False

    def process_bind_param(self, value: DataSourceSchema | None, dialect: Any) -> dict[str, dict[str, Any]] | None:
        if value is None:
            return None
        return value.model_dump(mode="json", exclude_none=True)

    def process_result_value(self, value: Any, dialect: Any) -> DataSourceSchema | None:
        if value is None:
            return None
        return DataSourceSchema.model_validate(value)
