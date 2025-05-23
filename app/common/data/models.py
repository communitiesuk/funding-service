import datetime
import enum
import secrets
import uuid
from typing import Any, Optional

from pytz import utc
from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, UniqueConstraint
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.ext.orderinglist import ordering_list
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.data.base import BaseModel, CIStr
from app.common.data.types import json_scalars


class RoleEnum(str, enum.Enum):
    ADMIN = (
        "admin"  # Admin level permissions, combines with null columns in UserRole table to denote level of admin access
    )
    MEMBER = "member"  # Basic read level permissions
    EDITOR = "editor"  # Read/write level permissions
    ASSESSOR = "assessor"  # Assessor level permissions
    S151_OFFICER = "s151_officer"  # S151 officer sign-off permissions


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


class User(BaseModel):
    __tablename__ = "user"

    email: Mapped[CIStr] = mapped_column(unique=True)

    magic_links: Mapped[list["MagicLink"]] = relationship("MagicLink", back_populates="user")

    roles: Mapped[list["UserRole"]] = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")
    collections: Mapped[list["Collection"]] = relationship("Collection", back_populates="created_by")

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

    @property
    def is_platform_admin(self) -> bool:
        is_platform_admin = any(
            role.role == RoleEnum.ADMIN and role.organisation_id is None and role.grant_id is None
            for role in self.roles
        )
        return is_platform_admin

    def get_id(self) -> str:
        return str(self.id)


class UserRole(BaseModel):
    __tablename__ = "user_role"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    organisation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organisation.id", ondelete="CASCADE"), nullable=True
    )
    grant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("grant.id", ondelete="CASCADE"), nullable=True)
    role: Mapped[RoleEnum] = mapped_column(
        SqlEnum(
            RoleEnum,
            name="role_enum",
            validate_strings=True,
        ),
        nullable=False,
    )

    user: Mapped[User] = relationship("User", back_populates="roles")
    organisation: Mapped[Organisation] = relationship("Organisation", back_populates="roles")
    grant: Mapped[Grant] = relationship("Grant", back_populates="roles")

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "organisation_id",
            "grant_id",
            "role",
            name="uq_user_org_grant_role",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_user_roles_user_id", "user_id"),
        Index("ix_user_roles_organisation_id", "organisation_id"),
        Index("ix_user_roles_grant_id", "grant_id"),
        Index("ix_user_roles_user_id_organisation_id", "user_id", "organisation_id"),
        Index("ix_user_roles_user_id_grant_id", "user_id", "grant_id"),
        Index("ix_user_roles_organisation_id_role_id_grant_id", "user_id", "organisation_id", "grant_id"),
        CheckConstraint(
            "role != 'MEMBER' OR NOT (organisation_id IS NULL AND grant_id IS NULL)",
            name="member_role_not_platform",
        ),
        CheckConstraint(
            "role != 'S151_OFFICER' OR (organisation_id IS NOT NULL AND grant_id IS NULL)",
            name="s151_officer_role_org_only",
        ),
        CheckConstraint(
            "role != 'ASSESSOR' OR (organisation_id IS NULL AND grant_id IS NOT NULL)",
            name="assessor_role_grant_only",
        ),
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

    sections: Mapped[list["Section"]] = relationship(
        "Section", lazy=True, order_by="Section.order", collection_class=ordering_list("order")
    )

    __table_args__ = (UniqueConstraint("name", "grant_id", "version", name="uq_schema_name_version_grant_id"),)


class CollectionStatusEnum(enum.StrEnum):
    NOT_STARTED = "Not started"


class Collection(BaseModel):
    __tablename__ = "collection"

    data: Mapped[json_scalars] = mapped_column(default=dict)
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


class QuestionDataType(enum.StrEnum):
    # If adding values here, also update QuestionTypeForm
    # and manually create a migration to update question_type_enum in the db
    TEXT_SINGLE_LINE = "A single line of text"
    TEXT_MULTI_LINE = "Multiple lines of text"
    INTEGER = "A whole number"

    @staticmethod
    def coerce(value: Any) -> "QuestionDataType":
        if isinstance(value, QuestionDataType):
            return value
        if isinstance(value, str):
            return QuestionDataType[value]
        raise ValueError(f"Cannot coerce {value} to QuestionDataType")


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
