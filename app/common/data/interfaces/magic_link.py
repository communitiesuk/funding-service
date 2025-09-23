import datetime
import uuid

from sqlalchemy import and_, func, select, update

from app.common.data.interfaces.exceptions import flush_and_rollback_on_exceptions
from app.common.data.models_user import MagicLink, User
from app.extensions import db


@flush_and_rollback_on_exceptions
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

    return magic_link


def get_magic_link(id_: uuid.UUID | None = None, code: str | None = None) -> MagicLink | None:
    """
    This interface will return a magic link even if it deemed 'not usable' ie. it has expired, so if using this
    interface you need to make sure you're dealing appropriately with unusable magic links.
    """
    if (id_ and code) or (not id_ and not code):
        raise ValueError("Must provide exactly one of `id_` and `code`")
    stmt = select(MagicLink)
    if id_:
        stmt = stmt.where(MagicLink.id == id_)
    else:
        stmt = stmt.where(MagicLink.code == code)

    return db.session.scalar(stmt)


@flush_and_rollback_on_exceptions
def claim_magic_link(magic_link: MagicLink, user: User | None) -> None:
    if not user:
        raise ValueError("User must be provided")
    magic_link.claimed_at_utc = func.now()
    magic_link.user = user
