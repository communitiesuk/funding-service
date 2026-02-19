from collections.abc import Sequence
from uuid import UUID

from flask import current_app
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_upsert

from app.common.data.interfaces.exceptions import flush_and_rollback_on_exceptions
from app.common.data.models import Organisation
from app.common.data.types import OrganisationData, OrganisationModeEnum, OrganisationStatus
from app.extensions import db


def get_organisations(
    can_manage_grants: bool | None = None, mode: OrganisationModeEnum = OrganisationModeEnum.LIVE
) -> Sequence[Organisation]:
    statement = select(Organisation).where(Organisation.mode == mode)

    if can_manage_grants is not None:
        statement = statement.where(Organisation.can_manage_grants.is_(can_manage_grants))

    return db.session.scalars(statement).all()


def get_organisation(organisation_id: UUID) -> Organisation:
    return db.session.get_one(Organisation, organisation_id)


def get_organisation_count(mode: OrganisationModeEnum = OrganisationModeEnum.LIVE) -> int:
    statement = (
        select(func.count())
        .select_from(Organisation)
        .where(Organisation.can_manage_grants.is_(False), Organisation.mode == mode)
    )
    return db.session.scalar(statement) or 0


@flush_and_rollback_on_exceptions()
def upsert_organisations(
    organisations: list[OrganisationData], cascade_to_test_mode_organisations: bool = False
) -> None:
    """Upserts organisations based on their external ID, which as of 27/10/25 is an IATI or LAD24 code."""
    existing_active_orgs = db.session.scalars(
        select(Organisation.id).where(
            Organisation.status == OrganisationStatus.ACTIVE, Organisation.can_manage_grants.is_(False)
        )
    ).all()

    modes = (
        [OrganisationModeEnum.LIVE]
        if not cascade_to_test_mode_organisations
        else [OrganisationModeEnum.LIVE, OrganisationModeEnum.TEST]
    )
    for mode in modes:
        for org in organisations:
            values = {
                "external_id": org.external_id,
                "name": org.name if mode == OrganisationModeEnum.LIVE else f"{org.name} (test)",
                "type": org.type,
                "can_manage_grants": False,
                "status": OrganisationStatus.ACTIVE if not org.retirement_date else OrganisationStatus.RETIRED,
                "active_date": org.active_date,
                "retirement_date": org.retirement_date,
                "mode": mode,
            }
            db.session.execute(
                postgresql_upsert(Organisation)
                .values(**values)
                .on_conflict_do_update(index_elements=["external_id", "mode"], set_=values),
                execution_options={"populate_existing": True},
            )

    db.session.flush()
    db.session.expire_all()

    retired_orgs = {
        org.id: org
        for org in db.session.scalars(
            select(Organisation).where(Organisation.status == OrganisationStatus.RETIRED)
        ).all()
    }

    # If an org has been flipped to RETIRED, log an error that will get thrown to Sentry to flag it for the team to
    # check. This doesn't necessarily need action but I'd like the team to be aware and work out if anything _does_
    # need to happen.
    now_retired_orgs = set(existing_active_orgs).intersection({org_id for org_id in retired_orgs})
    for org_id in now_retired_orgs:
        current_app.logger.error(
            "Active organisation %(name)s [%(external_id)s] has been retired as of %(retirement_date)s",
            {
                "name": retired_orgs[org_id].name,
                "external_id": retired_orgs[org_id].external_id,
                "retirement_date": retired_orgs[org_id].retirement_date,
            },
        )
