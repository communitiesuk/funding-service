import datetime
import secrets
import uuid
from typing import Any

from pytz import utc
from slugify import slugify
from sqlalchemy import JSON, ForeignKey, Index, UniqueConstraint
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.ext.orderinglist import ordering_list
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.data.base import BaseModel, CIStr
from app.common.data.types import ConditionType, DataType, QuestionType, SubmissionType


class Grant(BaseModel):
    __tablename__ = "grant"

    name: Mapped[CIStr] = mapped_column(unique=True)

    collection_schemas: Mapped[list["CollectionSchema"]] = relationship("CollectionSchema", lazy=True)


class User(BaseModel):
    __tablename__ = "user"

    email: Mapped[CIStr] = mapped_column(unique=True)

    magic_links: Mapped[list["MagicLink"]] = relationship("MagicLink", back_populates="user")

    # Required by Flask-Login; should be provided by UserMixin, except that breaks our type hinting
    # when using this class in SQLAlchemy queries. So we've just lifted the key attributes here directly.
    @property
    def is_active(self) -> bool:
        return True

    @property
    def is_authenticated(self) -> bool:
        return self.is_active

    @property
    def is_anonymous(self) -> bool:
        return False

    def get_id(self) -> str:
        return str(self.id)


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


class CollectionSchema(BaseModel):
    __tablename__ = "collection_schema"

    # Name will be superseded by domain specific application contexts but allows us to
    # try out different schemas and scenarios
    name: Mapped[str]
    version: Mapped[int] = mapped_column(default=1)

    grant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("grant.id"))
    grant: Mapped[Grant] = relationship("Grant", back_populates="collection_schemas")

    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    created_by: Mapped[User] = relationship("User")

    sections: Mapped[list["Section"]] = relationship(
        "Section", lazy=True, order_by="Section.order", collection_class=ordering_list("order", count_from=1)
    )

    @property
    def slug(self) -> str:
        return slugify(self.name)

    __table_args__ = (UniqueConstraint("name", "grant_id", "version", name="uq_schema_name_version_grant_id"),)


class Section(BaseModel):
    __tablename__ = "section"

    title: Mapped[str]
    order: Mapped[int]

    collection_schema_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("collection_schema.id"))
    collection_schema: Mapped[CollectionSchema] = relationship("CollectionSchema", back_populates="sections")

    forms: Mapped[list["Form"]] = relationship(
        "Form", lazy=True, order_by="Form.order", collection_class=ordering_list("order", count_from=1)
    )

    __table_args__ = (
        UniqueConstraint("order", "collection_schema_id", name="uq_section_order_collection_schema", deferrable=True),
        UniqueConstraint("title", "collection_schema_id", name="uq_section_title_collection_schema"),
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
        # TODO how can we make this unique per collection schema?
        UniqueConstraint("title", "section_id", name="uq_form_title_section"),
        UniqueConstraint("slug", "section_id", name="uq_form_slug_section"),
    )

    questions: Mapped[list["Question"]] = relationship(
        "Question", lazy=True, order_by="Question.order", collection_class=ordering_list("order", count_from=1)
    )


class Question(BaseModel):
    __tablename__ = "question"

    title: Mapped[str]
    name: Mapped[str]
    slug: Mapped[str]
    hint: Mapped[str]
    data_source: Mapped[dict[str, Any]] = mapped_column(JSON)
    data_type: Mapped[DataType] = mapped_column(SqlEnum(DataType), nullable=False)
    type: Mapped[QuestionType] = mapped_column(SqlEnum(QuestionType), nullable=False)
    order: Mapped[int]
    show_all_on_same_page: Mapped[bool] = mapped_column(default=False)

    form_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("form.id"))
    form: Mapped[Form] = relationship("Form", back_populates="questions")

    parent_question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("question.id"))
    parent_question: Mapped["Question"] = relationship("Question", foreign_keys=[parent_question_id])

    conditions: Mapped[list["Condition"]] = relationship(
        "Condition",
        back_populates="question",  # Assuming bidirectional relationship
        lazy=True,
        foreign_keys="[Condition.question_id]",
    )
    dependent_conditions: Mapped[list["Condition"]] = relationship(
        "Condition", back_populates="depends_on", foreign_keys="[Condition.depends_on_question_id]"
    )
    validations: Mapped[list["Validation"]] = relationship("Validation", lazy=True)

    __table_args__ = (
        UniqueConstraint("order", "form_id", name="uq_form_order_question", deferrable=True),
        UniqueConstraint("title", "form_id", name="uq_form_title_question"),
        UniqueConstraint("name", "form_id", name="uq_form_name_question"),
    )


class Condition(BaseModel):
    __tablename__ = "condition"

    expression: Mapped[str]
    type: Mapped[ConditionType] = mapped_column(SqlEnum(ConditionType))
    description: Mapped[str]
    context: Mapped[str]

    depends_on_question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("question.id"))
    depends_on: Mapped["Question"] = relationship(
        "Question", back_populates="dependent_conditions", foreign_keys=[depends_on_question_id]
    )

    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("question.id"))
    question: Mapped["Question"] = relationship("Question", back_populates="conditions", foreign_keys=[question_id])


class Validation(BaseModel):
    __tablename__ = "validation"

    expression: Mapped[str]
    type: Mapped[ConditionType] = mapped_column(SqlEnum(ConditionType))
    description: Mapped[str]
    message: Mapped[str]
    context: Mapped[str]

    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("question.id"))
    question: Mapped[Question] = relationship("Question", back_populates="validations")


class Submission(BaseModel):
    __tablename__ = "submission"

    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[SubmissionType] = mapped_column(SqlEnum(SubmissionType))
    collection_schema_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("collection_schema.id"))
    collection_schema: Mapped[CollectionSchema] = relationship("CollectionSchema", back_populates="collection_schema")
