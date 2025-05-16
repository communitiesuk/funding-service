import datetime
import secrets
import uuid
from typing import Optional

from pytz import utc
from sqlalchemy import ForeignKey, Index, UniqueConstraint
from sqlalchemy.ext.orderinglist import ordering_list
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.data.base import BaseModel, CIStr


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

    __table_args__ = (UniqueConstraint("name", "grant_id", "version", name="uq_schema_name_version_grant_id"),)


class Section(BaseModel):
    __tablename__ = "section"

    title: Mapped[str]
    order: Mapped[int]

    collection_schema_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("collection_schema.id"))
    collection_schema: Mapped[CollectionSchema] = relationship("CollectionSchema", back_populates="sections")

    forms: Mapped[list["Form"]] = relationship(
        "Form", order_by="Form.order", collection_class=ordering_list("order", count_from=1)
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

    # this is denormalised intentionally to allow for a unique constraint on the parent table
    # having sections not be a heirarchical element would allow for this in a cleaner way I think
    collection_schema_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("collection_schema.id"))

    __table_args__ = (
        UniqueConstraint("order", "section_id", name="uq_form_order_section", deferrable=True),
        UniqueConstraint("title", "collection_schema_id", name="uq_form_title_collection_schema"),
        UniqueConstraint("slug", "section_id", name="uq_form_slug_section"),
    )

    questions: Mapped[list["Question"]] = relationship(
        "Question", lazy=True, order_by="Question.order", collection_class=ordering_list("order", count_from=1)
    )

    sections: Mapped[list["Section"]] = relationship(
        "Section", lazy=True, order_by="Section.order", collection_class=ordering_list("order", count_from=1)
    )


# feels like types of "Question", "Group" or "Page" (informational only)
class Question(BaseModel):
    __tablename__ = "question"

    text: Mapped[str]
    slug: Mapped[str]
    order: Mapped[int]
    hint: Mapped[Optional[str]]
    name: Mapped[str]

    data_type: Mapped[str]  # TODO this will be an enum in proper data model

    form_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("form.id"))
    form: Mapped[Form] = relationship("Form", back_populates="questions")

    parent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("question.id"), nullable=True)
    parent: Mapped["Question"] = relationship(
        "Question",
        remote_side=[id],
        back_populates="questions",
        # lazy="joined",
    )

    questions: Mapped[list["Question"]] = relationship(
        "Question",
        back_populates="parent",
        # cascade="all, delete-orphan", - might want to think about this,
        order_by="Question.order",
        collection_class=ordering_list("order", count_from=1),
        # lazy="selectin" - consider performance, I think this allows a balance of perf and sensible queries - will have a think
    )

    __table_args__ = (
        UniqueConstraint("order", "parent_id", "form_id", name="uq_question_order_parent_form", deferrable=True),
        UniqueConstraint("slug", "form_id", name="uq_question_slug_form"),
        UniqueConstraint("name", "form_id", name="uq_question_name_form"),
    )
