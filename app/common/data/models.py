import datetime
import secrets
import uuid
from typing import TYPE_CHECKING, Optional

from pytz import utc
from sqlalchemy import Enum as SqlEnum
from sqlalchemy import ForeignKey, ForeignKeyConstraint, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.orderinglist import ordering_list
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy_json import mutable_json_type

from app.common.data.base import BaseModel, CIStr
from app.common.data.models_user import User
from app.common.data.types import CollectionStatusEnum, QuestionDataType, json_scalars

if TYPE_CHECKING:
    from app.common.data.models_user import UserRole


class Grant(BaseModel):
    __tablename__ = "grant"

    name: Mapped[CIStr] = mapped_column(unique=True)

    collection_schemas: Mapped[list["CollectionSchema"]] = relationship("CollectionSchema", lazy=True)
    roles: Mapped[list["UserRole"]] = relationship("UserRole", back_populates="grant", cascade="all, delete-orphan")


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


class CollectionSchema(BaseModel):
    __tablename__ = "collection_schema"

    # NOTE: The ID provided by the BaseModel should *NOT CHANGE* when incrementing the version. That part is a stable
    #       identifier for linked collection schemas/versioning.
    version: Mapped[int] = mapped_column(default=1, primary_key=True)

    # Name will be superseded by domain specific application contexts but allows us to
    # try out different schemas and scenarios
    name: Mapped[str]
    slug: Mapped[str]

    grant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("grant.id"))
    grant: Mapped[Grant] = relationship("Grant", back_populates="collection_schemas")

    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    created_by: Mapped[User] = relationship("User")

    collections: Mapped[list["Collection"]] = relationship(
        "Collection", lazy=True, order_by="Collection.created_at_utc", back_populates="collection_schema"
    )

    sections: Mapped[list["Section"]] = relationship(
        "Section", lazy=True, order_by="Section.order", collection_class=ordering_list("order")
    )

    __table_args__ = (UniqueConstraint("name", "grant_id", "version", name="uq_schema_name_version_grant_id"),)


class Collection(BaseModel):
    __tablename__ = "collection"

    data: Mapped[json_scalars] = mapped_column(mutable_json_type(dbtype=JSONB, nested=True))  # type: ignore[no-untyped-call]
    status: Mapped[CollectionStatusEnum] = mapped_column(
        SqlEnum(CollectionStatusEnum, name="collection_status_enum", validate_strings=True)
    )

    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    created_by: Mapped[User] = relationship("User", back_populates="collections")

    collection_schema_id: Mapped[uuid.UUID]
    collection_schema_version: Mapped[int]
    collection_schema: Mapped[CollectionSchema] = relationship("CollectionSchema")

    __table_args__ = (
        ForeignKeyConstraint(
            ["collection_schema_id", "collection_schema_version"], ["collection_schema.id", "collection_schema.version"]
        ),
    )


class Section(BaseModel):
    __tablename__ = "section"

    title: Mapped[str]
    order: Mapped[int]
    slug: Mapped[str]

    collection_schema_id: Mapped[uuid.UUID]
    collection_schema_version: Mapped[int]
    collection_schema: Mapped[CollectionSchema] = relationship("CollectionSchema", back_populates="sections")

    forms: Mapped[list["Form"]] = relationship(
        "Form", lazy=True, order_by="Form.order", collection_class=ordering_list("order")
    )

    __table_args__ = (
        UniqueConstraint(
            "collection_schema_id",
            "collection_schema_version",
            "order",
            name="uq_section_order_collection_schema",
            deferrable=True,
        ),
        UniqueConstraint(
            "collection_schema_id", "collection_schema_version", "title", name="uq_section_title_collection_schema"
        ),
        UniqueConstraint(
            "collection_schema_id", "collection_schema_version", "slug", name="uq_section_slug_collection_schema"
        ),
        ForeignKeyConstraint(
            ["collection_schema_id", "collection_schema_version"], ["collection_schema.id", "collection_schema.version"]
        ),
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
        "Question", lazy=True, order_by="Question.order", collection_class=ordering_list("order")
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

    __table_args__ = (
        UniqueConstraint("order", "form_id", name="uq_question_order_form", deferrable=True),
        UniqueConstraint("slug", "form_id", name="uq_question_slug_form"),
        UniqueConstraint("text", "form_id", name="uq_question_text_form"),
        UniqueConstraint("name", "form_id", name="uq_question_name_form"),
    )
