import uuid
from typing import Mapping, Sequence

from sqlalchemy import String, cast, func, select
from sqlalchemy.orm import joinedload

from app.common.data.interfaces.exceptions import flush_and_rollback_on_exceptions
from app.common.data.models import Grant, GrantRecipient, Organisation
from app.common.data.models_user import User, UserRole
from app.common.data.types import GrantRecipientModeEnum, RoleEnum, SubmissionModeEnum, SubmissionStatusEnum
from app.extensions import db


def get_grant_recipients(
    grant: "Grant",
    *,
    mode: GrantRecipientModeEnum = GrantRecipientModeEnum.LIVE,
    with_data_providers: bool = False,
    with_certifiers: bool = False,
) -> Sequence["GrantRecipient"]:
    stmt = select(GrantRecipient).where(GrantRecipient.grant_id == grant.id, GrantRecipient.mode == mode)

    if with_data_providers:
        stmt = stmt.options(joinedload(GrantRecipient.data_providers))

    if with_certifiers:
        stmt = stmt.options(joinedload(GrantRecipient._all_certifiers).joinedload(User.roles))

    return db.session.scalars(stmt).unique().all()


def get_grant_recipients_with_outstanding_submissions_for_collection(
    grant: "Grant", *, collection_id: uuid.UUID, with_data_providers: bool = False, with_certifiers: bool = False
) -> list[GrantRecipient]:
    """
    Gets all the grant recipients who have not submitted their submission for the given collection.

    They are considered not to have submitted if either:
    - They have a submission that is not in the SUBMITTED state
    - They do not have a submission for this collection

    """
    from app.common.data.interfaces.collections import get_all_submissions_with_mode_for_collection_with_full_schema
    from app.common.helpers.collections import SubmissionHelper

    all_grant_recipients = get_grant_recipients(
        grant, with_data_providers=with_data_providers, with_certifiers=with_certifiers
    )
    submissions = get_all_submissions_with_mode_for_collection_with_full_schema(
        grant_recipient_ids=[gr.id for gr in all_grant_recipients],
        collection_id=collection_id,
        submission_mode=SubmissionModeEnum.LIVE,
    )
    grant_recipients_with_outstanding_submissions = []
    for gr in all_grant_recipients:
        submission = next((s for s in submissions if s.grant_recipient_id == gr.id), None)
        if not submission or SubmissionHelper(submission).status != SubmissionStatusEnum.SUBMITTED:
            grant_recipients_with_outstanding_submissions.append(gr)

    return grant_recipients_with_outstanding_submissions


def get_grant_recipient(grant_id: uuid.UUID, organisation_id: uuid.UUID) -> "GrantRecipient":
    statement = (
        select(GrantRecipient)
        .join(Organisation, GrantRecipient.organisation_id == Organisation.id)
        .where(
            GrantRecipient.grant_id == grant_id,
            GrantRecipient.organisation_id == organisation_id,
            cast(GrantRecipient.mode, String) == cast(Organisation.mode, String),
        )
        .options(joinedload(GrantRecipient.grant), joinedload(GrantRecipient.organisation))
    )
    return db.session.scalars(statement).one()


def get_grant_recipients_count(grant: "Grant", mode: GrantRecipientModeEnum = GrantRecipientModeEnum.LIVE) -> int:
    statement = (
        select(func.count())
        .select_from(GrantRecipient)
        .where(GrantRecipient.grant_id == grant.id, GrantRecipient.mode == mode)
    )
    return db.session.scalar(statement) or 0


@flush_and_rollback_on_exceptions()
def create_grant_recipients(
    grant: "Grant", organisation_ids: list[uuid.UUID], mode: GrantRecipientModeEnum = GrantRecipientModeEnum.LIVE
) -> None:
    grant_recipients = []

    for organisation_id in organisation_ids:
        grant_recipients.append(GrantRecipient(grant_id=grant.id, organisation_id=organisation_id, mode=mode))

    db.session.add_all(grant_recipients)


def all_grant_recipients_have_data_providers(grant: "Grant") -> bool:
    grant_recipients = get_grant_recipients(grant, with_data_providers=True)

    if not grant_recipients:
        return False

    return all(grant_recipient.data_providers for grant_recipient in grant_recipients)


def get_grant_recipient_data_providers_count(
    grant: Grant, mode: GrantRecipientModeEnum = GrantRecipientModeEnum.LIVE
) -> int:
    return sum(
        len(grant_recipient.data_providers)
        for grant_recipient in get_grant_recipients(grant, mode=mode, with_data_providers=True)
    )


def get_grant_recipient_data_provider_roles(grant: Grant) -> Sequence[UserRole]:
    """Get all grant recipient data provider roles for a grant."""
    statement = (
        select(UserRole)
        .join(User, UserRole.user_id == User.id)
        .join(Organisation, Organisation.id == UserRole.organisation_id)
        .where(
            UserRole.grant_id == grant.id,
            UserRole.permissions.contains([RoleEnum.DATA_PROVIDER]),
        )
    )

    return db.session.scalars(statement).all()


def get_grant_recipient_data_providers(grant: Grant) -> Mapping[GrantRecipient, Sequence[User]]:
    grant_recipients = get_grant_recipients(grant, with_data_providers=True)

    data_providers = {}
    for grant_recipient in grant_recipients:
        data_providers[grant_recipient] = grant_recipient.data_providers

    return data_providers
