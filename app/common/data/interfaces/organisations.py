import uuid
from collections.abc import Sequence
from uuid import UUID

from flask import current_app
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_upsert

from app.common.data.interfaces.exceptions import flush_and_rollback_on_exceptions
from app.common.data.models import Organisation
from app.common.data.types import OrganisationData, OrganisationModeEnum, OrganisationStatus, OrganisationType
from app.extensions import db


def get_organisations(
    can_manage_grants: bool | None = None,
    mode: OrganisationModeEnum = OrganisationModeEnum.LIVE,
    with_ids: list[UUID] | None = None,
    with_external_ids: list[str] | None = None,
) -> Sequence[Organisation]:
    if with_ids is not None and with_external_ids is not None:
        raise ValueError("Cannot specify both with_ids and with_external_ids")

    statement = select(Organisation).where(Organisation.mode == mode)

    if can_manage_grants is not None:
        statement = statement.where(Organisation.can_manage_grants.is_(can_manage_grants))

    if with_ids is not None:
        statement = statement.where(Organisation.id.in_(with_ids))

    if with_external_ids is not None:
        statement = statement.where(Organisation.external_id.in_(with_external_ids))

    statement = statement.order_by(Organisation.name)

    return db.session.scalars(statement).all()


def get_organisation(organisation_id: UUID) -> Organisation:
    return db.session.get_one(Organisation, organisation_id)


def get_organisations_by_trusted_domain(
    domain: str, mode: OrganisationModeEnum = OrganisationModeEnum.LIVE
) -> Sequence[Organisation]:
    """Get the active organisations that trust an email domain, eg 'barnsley.gov.uk'.

    Trusted domains are stored lowercased, so the domain is lowercased before matching.
    """
    statement = (
        select(Organisation)
        .where(
            Organisation.mode == mode,
            Organisation.status == OrganisationStatus.ACTIVE,
            Organisation.trusted_domains.contains([domain.lower()]),
        )
        .order_by(Organisation.name)
    )
    return db.session.scalars(statement).all()


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
                "iati_id": org.iati_id,
                "ons_lad_id": org.ons_lad_id,
                "companies_house_number": org.companies_house_number,
                "charity_commission_number": org.charity_commission_number,
                "custom_code": org.custom_code,
                "trusted_domains": org.trusted_domains,
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


@flush_and_rollback_on_exceptions()
def get_or_create_self_registered_organisation(
    *, name: str, type_: OrganisationType, typed_id: str | None = None
) -> Organisation:
    """Get or create a LIVE organisation (with a TEST counterpart) for an applicant self-registering through the
    public sign up journey.

    Company/charity organisations are matched on their external ID, so registering the same Companies House or
    Charity Commission reference twice reuses the existing organisation rather than duplicating it. 'Other'
    organisations have no external identifier to match on, so they're matched by name instead, otherwise a new
    custom code is generated.
    """
    if type_ in (OrganisationType.COMPANY, OrganisationType.CHARITY):
        external_id = f"{type_.external_id_prefix}{typed_id}"
        existing = db.session.scalars(
            select(Organisation).where(
                Organisation.mode == OrganisationModeEnum.LIVE, Organisation.external_id == external_id
            )
        ).one_or_none()
        if existing:
            return existing
    else:
        existing = db.session.scalars(
            select(Organisation).where(Organisation.mode == OrganisationModeEnum.LIVE, Organisation.name == name)
        ).one_or_none()
        if existing:
            return existing

        typed_id = uuid.uuid4().hex[:12].upper()
        external_id = f"{type_.external_id_prefix}{typed_id}"

    # `uq_organisation_name_mode` is unique on (name, mode); if this name is already taken by a different
    # organisation, suffix it with the reference so we don't 500 on a collision.
    name_taken_by_other_org = (
        db.session.scalars(
            select(Organisation).where(
                Organisation.mode == OrganisationModeEnum.LIVE,
                Organisation.name == name,
                Organisation.external_id != external_id,
            )
        ).first()
        is not None
    )
    resolved_name = f"{name} ({external_id})" if name_taken_by_other_org else name

    organisation = Organisation(
        external_id=external_id,
        name=resolved_name,
        type=type_,
        status=OrganisationStatus.ACTIVE,
        can_manage_grants=False,
        mode=OrganisationModeEnum.LIVE,
    )
    organisation.typed_id = typed_id or ""
    db.session.add(organisation)

    test_organisation = Organisation(
        external_id=external_id,
        name=f"{resolved_name} (test)",
        type=type_,
        status=OrganisationStatus.ACTIVE,
        can_manage_grants=False,
        mode=OrganisationModeEnum.TEST,
    )
    test_organisation.typed_id = typed_id or ""
    db.session.add(test_organisation)

    return organisation
