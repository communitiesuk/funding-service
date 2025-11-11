import secrets
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pytz import utc
from sqlalchemy import CheckConstraint, ColumnElement, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.data.base import BaseModel, CIStr
from app.common.data.types import RoleEnum

if TYPE_CHECKING:
    from app.common.data.models import Grant, GrantRecipient, Organisation, Submission


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

    # These relationships need Organisation table as part of the join for filtering
    # Using string expressions to allow forward references to work properly
    # NOTE: This does not account for platform admin privileges; this is specifically for normal users
    deliver_grants: Mapped[list["Grant"]] = relationship(
        "Grant",
        secondary="join(UserRole, Organisation, UserRole.organisation_id == Organisation.id)",
        primaryjoin="User.id == UserRole.user_id",
        secondaryjoin="""and_(
            or_(
                Grant.id == UserRole.grant_id,
                and_(
                    Grant.organisation_id == UserRole.organisation_id,
                    UserRole.grant_id.is_(None)
                )
            ),
            Organisation.can_manage_grants == True
        )""",
        viewonly=True,
        order_by="Grant.name",
    )

    # For access_grants, we need to join through GrantRecipient for organization-level access
    # The logic is:
    # - Direct: Grant.id == UserRole.grant_id, OR
    # - Org-level: exists(GrantRecipient where GrantRecipient.grant_id == Grant.id
    #              AND GrantRecipient.organisation_id == UserRole.organisation_id)
    # We also filter by Organisation.can_manage_grants == False
    # NOTE: This does not account for platform admin privileges; this is specifically for normal users
    access_grants: Mapped[list["Grant"]] = relationship(
        "Grant",
        secondary="""join(
            join(UserRole, Organisation, UserRole.organisation_id == Organisation.id),
            GrantRecipient,
            GrantRecipient.organisation_id == UserRole.organisation_id,
            isouter=True
        )""",
        primaryjoin="User.id == UserRole.user_id",
        secondaryjoin="""and_(
            or_(
                Grant.id == UserRole.grant_id,
                and_(
                    Grant.id == GrantRecipient.grant_id,
                    UserRole.grant_id.is_(None)
                )
            ),
            Organisation.can_manage_grants == False
        )""",
        viewonly=True,
        order_by="Grant.name",
    )

    # this has some overlap with access_grants above but is most interested in the organisation you
    # have access to
    _grant_recipients: Mapped[list["GrantRecipient"]] = relationship(
        "GrantRecipient",
        secondary="""join(
            UserRole,
            Organisation,
            UserRole.organisation_id == Organisation.id
        )""",
        primaryjoin="User.id == UserRole.user_id",
        secondaryjoin="""and_(
            or_(
                and_(
                    GrantRecipient.grant_id == UserRole.grant_id,
                    GrantRecipient.organisation_id == UserRole.organisation_id
                ),
                and_(
                    GrantRecipient.organisation_id == UserRole.organisation_id,
                    UserRole.grant_id.is_(None)
                )
            ),
            Organisation.can_manage_grants == False
        )""",
        viewonly=True,
    )

    def grant_recipients(self, *, limit_to_organisation_id: uuid.UUID | None = None) -> list["GrantRecipient"]:
        if limit_to_organisation_id is None:
            return self._grant_recipients
        return [gr for gr in self._grant_recipients if gr.organisation.id == limit_to_organisation_id]

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
    permissions: Mapped[list["RoleEnum"]] = mapped_column(
        postgresql.ARRAY(SqlEnum(RoleEnum, name="role_enum", validate_strings=True)),
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
            (
                "('MEMBER' != ALL(permissions) AND 'CERTIFIER' != ALL(permissions) AND "
                "'DATA_PROVIDER' != ALL(permissions)) OR organisation_id IS NOT NULL"
            ),
            name="non_admin_permissions_require_org",
        ),
        CheckConstraint(
            "(organisation_id IS NULL AND grant_id IS NULL) or (organisation_id IS NOT NULL)",
            name="org_required_if_grant",
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
    permissions: Mapped[list["RoleEnum"]] = mapped_column(
        postgresql.ARRAY(SqlEnum(RoleEnum, name="role_enum", validate_strings=True)),
        nullable=False,
    )

    user: Mapped[User] = relationship("User", back_populates="invitations")
    organisation: Mapped["Organisation"] = relationship("Organisation")
    grant: Mapped["Grant"] = relationship("Grant", back_populates="invitations")

    expires_at_utc: Mapped[datetime] = mapped_column(nullable=False)
    claimed_at_utc: Mapped[datetime | None] = mapped_column(nullable=True)

    __table_args__ = (
        CheckConstraint(
            (
                "('MEMBER' != ALL(permissions) AND 'CERTIFIER' != ALL(permissions) AND "
                "'DATA_PROVIDER' != ALL(permissions)) OR organisation_id IS NOT NULL"
            ),
            name="non_admin_permissions_require_org",
        ),
    )

    @hybrid_property
    def is_usable(self) -> bool:
        return self.claimed_at_utc is None and self.expires_at_utc > datetime.now(utc).replace(tzinfo=None)

    @is_usable.inplace.expression
    @classmethod
    def _is_usable_expression(cls) -> ColumnElement[bool]:
        return cls.claimed_at_utc.is_(None) & (cls.expires_at_utc > func.now())
