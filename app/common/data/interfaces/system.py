import sentry_sdk
from flask import Flask
from psycopg import IntegrityError

from app.common.data.models import Organisation
from app.common.data.types import OrganisationStatus
from app.extensions import db


def seed_system_data(app: Flask) -> None:
    """
    A single interface to seed any "systems-level" data, ie data that we absolutely need to be in the database or else
    we have a very confusion/invalid system state.

    This is currently *only* the MHCLG organisation. There should be no need to add other organisations to the system
    here, not even other grant-owning organisations.

    If you're thinking of adding more data here to seed it into the database, think very carefully. It is extremely
    unlikely to be necessary, and it is quite likely to lead to hard-coding identifiers or adding implicit expectations
    into the system that will degrade maintainability.

    I'm doing this because I've limited the system to allowing a single grant-managing organisation for now; when we
    remove that constraint and allow OGDs to manage grants through the platform, it's likely we'd want to consider
    *all* grant-managing organisations to just be standard data in the system, rather than snowflake-systems-level data
    that we're creating/expecting here. So if/when we allow multiple orgs to manage grants, we should aim to remove
    this seeding function.
    """
    platform_org = db.session.query(Organisation).filter_by(can_manage_grants=True).one_or_none()
    if platform_org:
        return

    try:
        platform_org = Organisation(
            status=OrganisationStatus.ACTIVE,
            can_manage_grants=True,
            **app.config["PLATFORM_DEPARTMENT_ORGANISATION_CONFIG"],
        )
        db.session.add(platform_org)
        db.session.commit()
    except IntegrityError as e:
        # Presumably a race condition where two instances have got through to here at the same time; let's ignore the
        # failing one. But capture it just in case.
        sentry_sdk.capture_exception(e)
        db.session.rollback()
