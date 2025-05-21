import datetime
import secrets
import uuid
from enum import Enum

from pytz import utc
from sqlalchemy import CheckConstraint, ForeignKey, Index, UniqueConstraint
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.ext.orderinglist import ordering_list
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.data.base import BaseModel, CIStr


class RoleEnum(str, Enum):
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
        UniqueConstraint("user_id", "organisation_id", "grant_id", "role", name="uq_user_org_grant_role"),
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

    # Name will be superseded by domain specific application contexts but allows us to
    # try out different schemas and scenarios
    name: Mapped[str]
    version: Mapped[int] = mapped_column(default=1)
    slug: Mapped[str]

    grant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("grant.id"))
    grant: Mapped[Grant] = relationship("Grant", back_populates="collection_schemas")

    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    created_by: Mapped[User] = relationship("User")

    sections: Mapped[list["Section"]] = relationship(
        "Section", lazy=True, order_by="Section.order", collection_class=ordering_list("order")
    )

    # TODO think about unique constraint on slug, including verison, when we sort out versioning,
    #  eg. compound key on id and version
    __table_args__ = (UniqueConstraint("name", "grant_id", "version", name="uq_schema_name_version_grant_id"),)


class Section(BaseModel):
    __tablename__ = "section"

    title: Mapped[str]
    order: Mapped[int]
    slug: Mapped[str]

    collection_schema_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("collection_schema.id"))
    collection_schema: Mapped[CollectionSchema] = relationship("CollectionSchema", back_populates="sections")

    forms: Mapped[list["Form"]] = relationship(
        "Form", lazy=True, order_by="Form.order", collection_class=ordering_list("order")
    )

    __table_args__ = (
        UniqueConstraint("order", "collection_schema_id", name="uq_section_order_collection_schema", deferrable=True),
        UniqueConstraint("title", "collection_schema_id", name="uq_section_title_collection_schema"),
        UniqueConstraint("slug", "collection_schema_id", name="uq_section_slug_collection_schema"),
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
