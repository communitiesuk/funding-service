import secrets
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pytz import utc
from sqlalchemy import CheckConstraint, ColumnElement, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.data.base import BaseModel, CIStr
from app.common.data.types import RoleEnum

if TYPE_CHECKING:
    from app.common.data.models import Grant, Organisation, Submission


class User(BaseModel):
    __tablename__ = "user"

    name: Mapped[str] = mapped_column(nullable=True)
    email: Mapped[CIStr] = mapped_column(unique=True)
    azure_ad_subject_id: Mapped[str] = mapped_column(nullable=True, unique=True)

    magic_links: Mapped[list["MagicLink"]] = relationship("MagicLink", back_populates="user")
    invitations: Mapped[list["Invitation"]] = relationship(
        "Invitation", back_populates="user", cascade="all, delete-orphan"
    )
    roles: Mapped[list["UserRole"]] = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")
    submissions: Mapped[list["Submission"]] = relationship("Submission", back_populates="created_by")

    last_logged_in_at_utc: Mapped[datetime | None] = mapped_column(nullable=True)

    # START: Flask-Login attributes
    # These ideally might be provided by UserMixin, except that breaks our type hinting when using this class in
    # SQLAlchemy queries. So we've just lifted the key attributes here directly.
    @property
    def is_active(self) -> bool:
        return True

    @property
    def is_authenticated(self) -> bool:
        return self.is_active

    @property
    def is_anonymous(self) -> bool:
        return False

    def get_id(self) -> str | None:
        return str(self.id)


class UserRole(BaseModel):
    __tablename__ = "user_role"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    organisation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organisation.id", ondelete="CASCADE"), nullable=True
    )
    grant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("grant.id", ondelete="CASCADE"), nullable=True)
    role: Mapped["RoleEnum"] = mapped_column(
        SqlEnum(
            RoleEnum,
            name="role_enum",
            validate_strings=True,
        ),
        nullable=False,
    )

    user: Mapped[User] = relationship("User", back_populates="roles")
    organisation: Mapped["Organisation"] = relationship("Organisation", back_populates="roles")
    grant: Mapped["Grant"] = relationship("Grant")

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "organisation_id",
            "grant_id",
            name="uq_user_org_grant",
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
    )


class MagicLink(BaseModel):
    __tablename__ = "magic_link"

    code: Mapped[str] = mapped_column(unique=True, default=lambda: secrets.token_urlsafe(12))
    email: Mapped[CIStr] = mapped_column(nullable=True)

    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    redirect_to_path: Mapped[str]
    expires_at_utc: Mapped[datetime]
    claimed_at_utc: Mapped[datetime | None]

    user: Mapped[User] = relationship("User", back_populates="magic_links")

    __table_args__ = (Index(None, code, unique=True, postgresql_where="claimed_at_utc IS NOT NULL"),)

    @hybrid_property
    def is_usable(self) -> bool:
        return self.claimed_at_utc is None and self.expires_at_utc > datetime.now(utc).replace(tzinfo=None)

    @is_usable.inplace.expression
    @classmethod
    def _is_usable_expression(cls) -> ColumnElement[bool]:
        return cls.claimed_at_utc.is_(None) & (cls.expires_at_utc > func.now())


class Invitation(BaseModel):
    __tablename__ = "invitation"

    email: Mapped[CIStr]

    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    organisation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organisation.id", ondelete="CASCADE"), nullable=True
    )
    grant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("grant.id", ondelete="CASCADE"), nullable=True)
    role: Mapped["RoleEnum"] = mapped_column(
        SqlEnum(
            RoleEnum,
            name="role_enum",
            validate_strings=True,
        ),
        nullable=False,
    )

    user: Mapped[User] = relationship("User", back_populates="invitations")
    organisation: Mapped["Organisation"] = relationship("Organisation")
    grant: Mapped["Grant"] = relationship("Grant", back_populates="invitations")

    expires_at_utc: Mapped[datetime] = mapped_column(nullable=False)
    claimed_at_utc: Mapped[datetime | None] = mapped_column(nullable=True)

    @hybrid_property
    def is_usable(self) -> bool:
        return self.claimed_at_utc is None and self.expires_at_utc > datetime.now(utc).replace(tzinfo=None)

    @is_usable.inplace.expression
    @classmethod
    def _is_usable_expression(cls) -> ColumnElement[bool]:
        return cls.claimed_at_utc.is_(None) & (cls.expires_at_utc > func.now())
