import datetime
import secrets
import uuid
from enum import Enum

from pytz import utc
from sqlalchemy import Enum as PgEnum
from sqlalchemy import ForeignKey, Index, UniqueConstraint
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


class Organisation(BaseModel):
    __tablename__ = "organisation"

    name: Mapped[CIStr] = mapped_column(unique=True)


class User(BaseModel):
    __tablename__ = "user"

    email: Mapped[CIStr] = mapped_column(unique=True)

    magic_links: Mapped[list["MagicLink"]] = relationship("MagicLink", back_populates="user")

    roles: Mapped[list["UserRole"]] = relationship(
        "UserRole", secondary="user_role", back_populates="user", cascade="all, delete-orphan"
    )

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
    org_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organisation.id", ondelete="CASCADE"), nullable=True)
    grant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("grant.id", ondelete="CASCADE"), nullable=True)
    role: Mapped[RoleEnum] = mapped_column(
        PgEnum(
            RoleEnum,
            name="role_enum",
            validate_strings=True,
        ),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("user_id", "org_id", "grant_id", "role", name="uq_user_org_grant_role"),
        Index("ix_user_roles_user_id", "user_id"),
        Index("ix_user_roles_org_id", "org_id"),
        Index("ix_user_roles_grant_id", "grant_id"),
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

    grant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("grant.id"))
    grant: Mapped[Grant] = relationship("Grant", back_populates="collection_schemas")

    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    created_by: Mapped[User] = relationship("User")

    __table_args__ = (UniqueConstraint("name", "grant_id", "version", name="uq_schema_name_version_grant_id"),)
