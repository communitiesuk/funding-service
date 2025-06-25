import datetime
import secrets
import uuid
from typing import TYPE_CHECKING, Optional

from pytz import utc
from sqlalchemy import Enum as SqlEnum
from sqlalchemy import ForeignKey, ForeignKeyConstraint, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.orderinglist import ordering_list
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy_json import mutable_json_type

from app.common.data.base import BaseModel, CIStr
from app.common.data.models_user import User
from app.common.data.types import (
    ExpressionType,
    ManagedExpressionsEnum,
    QuestionDataType,
    SubmissionEventKey,
    SubmissionModeEnum,
    SubmissionStatusEnum,
    json_flat_scalars,
    json_scalars,
)
from app.common.expressions.managed import get_managed_expression

if TYPE_CHECKING:
    from app.common.data.models_user import UserRole
    from app.common.expressions.managed import ManagedExpression


class Grant(BaseModel):
    __tablename__ = "grant"

    ggis_number: Mapped[str]
    name: Mapped[CIStr] = mapped_column(unique=True)
    description: Mapped[str]
    primary_contact_name: Mapped[str]
    primary_contact_email: Mapped[str]

    collections: Mapped[list["Collection"]] = relationship("Collection", lazy=True, cascade="all, delete-orphan")

    users: Mapped[list["User"]] = relationship(
        "User",
        secondary="user_role",
        primaryjoin="Grant.id==UserRole.grant_id",
        secondaryjoin="User.id==UserRole.user_id",
        viewonly=True,
    )


class Organisation(BaseModel):
    __tablename__ = "organisation"

    name: Mapped[CIStr] = mapped_column(unique=True)
    roles: Mapped[list["UserRole"]] = relationship(
        "UserRole", back_populates="organisation", cascade="all, delete-orphan"
    )


class MagicLink(BaseModel):
    __tablename__ = "magic_link"

    code: Mapped[str] = mapped_column(unique=True, default=lambda: secrets.token_urlsafe(12))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    redirect_to_path: Mapped[str]
    expires_at_utc: Mapped[datetime.datetime]
    claimed_at_utc: Mapped[datetime.datetime | None]

    user: Mapped[User] = relationship("User", back_populates="magic_links")

    __table_args__ = (Index(None, code, unique=True, postgresql_where="claimed_at_utc IS NOT NULL"),)

    @property
    def usable(self) -> bool:
        return self.claimed_at_utc is None and self.expires_at_utc > datetime.datetime.now(utc).replace(tzinfo=None)


class Collection(BaseModel):
    __tablename__ = "collection"

    # NOTE: The ID provided by the BaseModel should *NOT CHANGE* when incrementing the version. That part is a stable
    #       identifier for linked collection/versioning.
    version: Mapped[int] = mapped_column(default=1, primary_key=True)

    # Name will be superseded by domain specific application contexts but allows us to
    # try out different collections and scenarios
    name: Mapped[str]
    slug: Mapped[str]

    grant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("grant.id"))
    grant: Mapped[Grant] = relationship("Grant", back_populates="collections")

    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    created_by: Mapped[User] = relationship("User")

    # NOTE: Don't use this relationship directly; use either `test_submissions` or `live_submissions`.
    _submissions: Mapped[list["Submission"]] = relationship(
        "Submission",
        lazy=True,
        order_by="Submission.created_at_utc",
        back_populates="collection",
        cascade="all, delete-orphan",
    )

    sections: Mapped[list["Section"]] = relationship(
        "Section",
        lazy=True,
        order_by="Section.order",
        collection_class=ordering_list("order"),
        # Importantly we don't `delete-orphan` here; when we move sections up/down, we remove them from the collection,
        # which would trigger the delete-orphan rule
        cascade="all",
    )

    __table_args__ = (UniqueConstraint("name", "grant_id", "version", name="uq_collection_name_version_grant_id"),)

    @property
    def test_submissions(self) -> list["Submission"]:
        return list(submission for submission in self._submissions if submission.mode == SubmissionModeEnum.TEST)

    @property
    def live_submissions(self) -> list["Submission"]:
        return list(submission for submission in self._submissions if submission.mode == SubmissionModeEnum.LIVE)


class Submission(BaseModel):
    __tablename__ = "submission"

    data: Mapped[json_scalars] = mapped_column(mutable_json_type(dbtype=JSONB, nested=True))  # type: ignore[no-untyped-call]
    mode: Mapped[SubmissionModeEnum] = mapped_column(
        SqlEnum(SubmissionModeEnum, name="submission_mode_enum", validate_strings=True)
    )
    status: Mapped[SubmissionStatusEnum] = mapped_column(
        SqlEnum(SubmissionStatusEnum, name="submission_status_enum", validate_strings=True)
    )

    # TODO: generated and persisted human readable references for submissions
    #       these will likely want to fit the domain need
    @property
    def reference(self) -> str:
        return str(self.id)[:8]

    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    created_by: Mapped[User] = relationship("User", back_populates="submissions")

    collection_id: Mapped[uuid.UUID]
    collection_version: Mapped[int]
    collection: Mapped[Collection] = relationship("Collection")

    events: Mapped[list["SubmissionEvent"]] = relationship(
        "SubmissionEvent", back_populates="submission", cascade="all, delete-orphan"
    )

    __table_args__ = (
        ForeignKeyConstraint(["collection_id", "collection_version"], ["collection.id", "collection.version"]),
    )


class Section(BaseModel):
    __tablename__ = "section"

    title: Mapped[str]
    order: Mapped[int]
    slug: Mapped[str]

    collection_id: Mapped[uuid.UUID]
    collection_version: Mapped[int]
    collection: Mapped[Collection] = relationship("Collection", back_populates="sections")

    forms: Mapped[list["Form"]] = relationship(
        "Form",
        lazy=True,
        order_by="Form.order",
        collection_class=ordering_list("order"),
        # Importantly we don't `delete-orphan` here; when we move forms up/down, we remove them from the collection,
        # which would trigger the delete-orphan rule
        cascade="all, save-update, merge",
    )

    __table_args__ = (
        UniqueConstraint(
            "collection_id",
            "collection_version",
            "order",
            name="uq_section_order_collection",
            deferrable=True,
        ),
        UniqueConstraint("collection_id", "collection_version", "title", name="uq_section_title_collection"),
        UniqueConstraint("collection_id", "collection_version", "slug", name="uq_section_slug_collection"),
        ForeignKeyConstraint(["collection_id", "collection_version"], ["collection.id", "collection.version"]),
    )


class Form(BaseModel):
    __tablename__ = "form"

    title: Mapped[str]
    order: Mapped[int]
    slug: Mapped[str]

    section_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("section.id"))
    section: Mapped[Section] = relationship("Section", back_populates="forms")

    __table_args__ = (
        UniqueConstraint("order", "section_id", name="uq_form_order_section", deferrable=True),
        # TODO how can we make this unique per collection?
        UniqueConstraint("title", "section_id", name="uq_form_title_section"),
        UniqueConstraint("slug", "section_id", name="uq_form_slug_section"),
    )

    questions: Mapped[list["Question"]] = relationship(
        "Question",
        lazy=True,
        order_by="Question.order",
        collection_class=ordering_list("order"),
        # Importantly we don't `delete-orphan` here; when we move questions up/down, we remove them from the collection,
        # which would trigger the delete-orphan rule
        cascade="all, save-update, merge",
    )


class Question(BaseModel):
    __tablename__ = "question"

    text: Mapped[str]
    slug: Mapped[str]
    order: Mapped[int]
    hint: Mapped[Optional[str]]
    data_type: Mapped[QuestionDataType] = mapped_column(
        SqlEnum(
            QuestionDataType,
            name="question_data_type_enum",
            validate_strings=True,
        )
    )
    name: Mapped[str]

    form_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("form.id"))
    form: Mapped[Form] = relationship("Form", back_populates="questions")

    # todo: decide if these should be lazy loaded, eagerly joined or eagerly selectin
    expressions: Mapped[list["Expression"]] = relationship(
        "Expression", back_populates="question", cascade="all, delete-orphan", order_by="Expression.created_at_utc"
    )

    @property
    def conditions(self) -> list["Expression"]:
        return [expression for expression in self.expressions if expression.type == ExpressionType.CONDITION]

    @property
    def validations(self) -> list["Expression"]:
        return [expression for expression in self.expressions if expression.type == ExpressionType.VALIDATION]

    def get_expression(self, id: uuid.UUID) -> "Expression":
        try:
            return next(expression for expression in self.expressions if expression.id == id)
        except StopIteration as e:
            raise ValueError(f"Could not find an expression with id={id} in question={self.id}") from e

    __table_args__ = (
        UniqueConstraint("order", "form_id", name="uq_question_order_form", deferrable=True),
        UniqueConstraint("slug", "form_id", name="uq_question_slug_form"),
        UniqueConstraint("text", "form_id", name="uq_question_text_form"),
        UniqueConstraint("name", "form_id", name="uq_question_name_form"),
    )


class SubmissionEvent(BaseModel):
    __tablename__ = "submission_event"

    key: Mapped[SubmissionEventKey] = mapped_column(
        SqlEnum(SubmissionEventKey, name="submission_event_key_enum", validate_strings=True)
    )

    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submission.id"))
    submission: Mapped[Submission] = relationship("Submission", back_populates="events")

    form_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("form.id"))
    form: Mapped[Optional[Form]] = relationship("Form")

    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    created_by: Mapped[User] = relationship("User")


class Expression(BaseModel):
    __tablename__ = "expression"

    statement: Mapped[str]

    context: Mapped[json_flat_scalars] = mapped_column(mutable_json_type(dbtype=JSONB, nested=True))  # type: ignore[no-untyped-call]

    type: Mapped[ExpressionType] = mapped_column(
        SqlEnum(ExpressionType, name="expression_type_enum", validate_strings=True)
    )

    managed_type: Mapped[Optional[ManagedExpressionsEnum]] = mapped_column(
        SqlEnum(ManagedExpressionsEnum, name="managed_expression_enum", validate_strings=True, nullable=True)
    )

    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("question.id"))
    question: Mapped[Question] = relationship("Question", back_populates="expressions")

    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    created_by: Mapped[User] = relationship("User")

    __table_args__ = (
        Index(
            "uq_type_validation_unique_key",
            "type",
            "question_id",
            "managed_type",
            postgresql_where=f"type = '{ExpressionType.VALIDATION.value}'::expression_type_enum",
            unique=True,
        ),
        Index(
            "uq_type_condition_unique_question",
            "type",
            "question_id",
            "managed_type",
            text("(context ->> 'question_id')"),
            postgresql_where=f"type = '{ExpressionType.CONDITION.value}'::expression_type_enum",
            unique=True,
        ),
    )

    @property
    def managed(self) -> "ManagedExpression":
        return get_managed_expression(self)
