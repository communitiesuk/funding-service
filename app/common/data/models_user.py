import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, UniqueConstraint
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.data.base import BaseModel, CIStr
from app.common.data.types import RoleEnum

if TYPE_CHECKING:
    from app.common.data.models import Grant, MagicLink, Organisation, Submission


class User(BaseModel):
    __tablename__ = "user"

    name: Mapped[str] = mapped_column(nullable=True)

    email: Mapped[CIStr] = mapped_column(unique=True)

    magic_links: Mapped[list["MagicLink"]] = relationship("MagicLink", back_populates="user")

    roles: Mapped[list["UserRole"]] = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")
    submissions: Mapped[list["Submission"]] = relationship("Submission", back_populates="created_by")

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

    def get_id(self) -> str:
        return str(self.id)

    # END: Flask-Login attributes

    @property
    def has_logged_in(self) -> bool:
        # FIXME: We should have some actual tracking of whether the user has logged in. This could either be a
        #        field on the model called `last_logged_in_at` or similar, or we could only create entries in the user
        #        table when the user actually logs in, rather than at invitation-time. Then we could simply trust that
        #        if a user entry exists, they have definitely logged in.
        return bool(self.name)

    @property
    def is_platform_admin(self) -> bool:
        is_platform_admin = any(
            role.role == RoleEnum.ADMIN and role.organisation_id is None and role.grant_id is None
            for role in self.roles
        )
        return is_platform_admin


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
        CheckConstraint(
            "role != 'S151_OFFICER' OR (organisation_id IS NOT NULL AND grant_id IS NULL)",
            name="s151_officer_role_org_only",
        ),
        CheckConstraint(
            "role != 'ASSESSOR' OR (organisation_id IS NULL AND grant_id IS NOT NULL)",
            name="assessor_role_grant_only",
        ),
    )
