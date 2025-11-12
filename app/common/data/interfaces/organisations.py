from typing import Sequence

from flask import current_app
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_upsert

from app.common.data.interfaces.exceptions import flush_and_rollback_on_exceptions
from app.common.data.models import Organisation
from app.common.data.types import OrganisationData, OrganisationStatus
from app.extensions import db


def get_organisations(can_manage_grants: bool | None = None) -> Sequence[Organisation]:
    statement = select(Organisation)

    if can_manage_grants is not None:
        statement = statement.where(Organisation.can_manage_grants.is_(can_manage_grants))

    return db.session.scalars(statement).all()


def get_organisation_count() -> int:
    statement = select(func.count()).select_from(Organisation).where(Organisation.can_manage_grants.is_(False))
    return db.session.scalar(statement) or 0


@flush_and_rollback_on_exceptions()
def upsert_organisations(organisations: list[OrganisationData]) -> None:
    """Upserts organisations based on their external ID, which as of 27/10/25 is an IATI or LAD24 code."""
    existing_active_orgs = db.session.scalars(
        select(Organisation.id).where(Organisation.status == OrganisationStatus.ACTIVE)
    ).all()
    for org in organisations:
        values = {
            "external_id": org.external_id,
            "name": org.name,
            "type": org.type,
            "can_manage_grants": False,
            "status": OrganisationStatus.ACTIVE if not org.retirement_date else OrganisationStatus.RETIRED,
            "active_date": org.active_date,
            "retirement_date": org.retirement_date,
        }
        db.session.execute(
            postgresql_upsert(Organisation)
            .values(**values)
            .on_conflict_do_update(index_elements=["external_id"], set_=values),
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
