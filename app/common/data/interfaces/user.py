from sqlalchemy.dialects.postgresql import insert as postgresql_upsert

from app.common.data.models import User
from app.extensions import db


def get_or_create_user(email_address: str) -> User:
    # This feels like it should be a `on_conflict_do_nothing`, except in that case the DB won't return any rows
    # So we use `on_conflict_do_update` with a noop change, so that this upsert will always return the User regardless
    # of if its doing an insert or an 'update'.
    user = db.session.scalars(
        postgresql_upsert(User)
        .values(email=email_address)
        .on_conflict_do_update(index_elements=["email"], set_={"email": email_address})
        .returning(User),
        execution_options={"populate_existing": True},
    ).one()

    return user
