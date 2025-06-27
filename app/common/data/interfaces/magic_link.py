import datetime
import uuid

from sqlalchemy import and_, func, select, update

from app.common.data.models_user import MagicLink, User
from app.extensions import db


def create_magic_link(email: str, *, user: User | None, redirect_to_path: str) -> MagicLink:
    # This db query checks if any magic links exist for this user/email and if so it expires the magic link before
    # creating a new one.
    db.session.execute(
        update(MagicLink)
        .where(and_(MagicLink.email == email, MagicLink.is_usable.is_(True)))
        .values(expires_at_utc=func.now())
    )

    magic_link = MagicLink(
        email=email,
        user=user,
        redirect_to_path=redirect_to_path,
        expires_at_utc=func.now() + datetime.timedelta(minutes=15),
    )

    db.session.add(magic_link)
    db.session.flush()

    return magic_link


def get_magic_link(id_: uuid.UUID | None = None, code: str | None = None) -> MagicLink | None:
    if (id_ and code) or (not id_ and not code):
        raise ValueError("Must provide exactly one of `id_` and `code`")

    if id_:
        return db.session.scalar(select(MagicLink).where(and_(MagicLink.id == id_, MagicLink.is_usable.is_(True))))

    return db.session.scalar(select(MagicLink).where(and_(MagicLink.code == code, MagicLink.is_usable.is_(True))))


def claim_magic_link(magic_link: MagicLink, user: User) -> None:
    if not user:
        raise ValueError("User must be provided")
    magic_link.claimed_at_utc = func.now()
    magic_link.user = user
    db.session.flush()
