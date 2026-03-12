import uuid
from dataclasses import dataclass

from flask import current_app

from app.common.data.types import CollectionType, GrantRecipientStatus, RoleEnum


# todo: this shouldn't be duplicated between deliver and access grant funding
#       we should have one definition in common which they both use (to the extent they're actually needed)
@dataclass(frozen=True)
class AccessCollectionContext:
    """Display configuration for a collection type in Access Grant Funding templates."""

    active_nav_item: str  # "reports" or "award"
    singular_name: str  # "report", "application", "collection"
    list_route: str  # route name for the back link to the list page
    back_link_text: str  # "reports", "award" — destination name for back links


_MONITORING_REPORT_CONTEXT = AccessCollectionContext(
    active_nav_item="reports",
    singular_name="report",
    list_route="access_grant_funding.list_reports",
    back_link_text="reports",
)

_DEFAULT_AWARD_CONTEXT = AccessCollectionContext(
    active_nav_item="award",
    singular_name="collection",
    list_route="access_grant_funding.list_award_collections",
    back_link_text="award",
)

_COLLECTION_TYPE_CONTEXTS: dict[CollectionType, AccessCollectionContext] = {
    CollectionType.MONITORING_REPORT: _MONITORING_REPORT_CONTEXT,
    CollectionType.APPLICATION: AccessCollectionContext(
        active_nav_item="award",
        singular_name="application",
        list_route="access_grant_funding.list_award_collections",
        back_link_text="award",
    ),
    CollectionType.ELIGIBILITY_CHECK: AccessCollectionContext(
        active_nav_item="award",
        singular_name="eligibility check",
        list_route="access_grant_funding.list_award_collections",
        back_link_text="award",
    ),
    CollectionType.EXPRESSION_OF_INTEREST: AccessCollectionContext(
        active_nav_item="award",
        singular_name="expression of interest",
        list_route="access_grant_funding.list_award_collections",
        back_link_text="award",
    ),
    CollectionType.BASELINE: AccessCollectionContext(
        active_nav_item="award",
        singular_name="baseline",
        list_route="access_grant_funding.list_award_collections",
        back_link_text="award",
    ),
    CollectionType.ASSESSMENT: AccessCollectionContext(
        active_nav_item="award",
        singular_name="assessment",
        list_route="access_grant_funding.list_award_collections",
        back_link_text="award",
    ),
}


def get_access_collection_context(collection_type: CollectionType) -> AccessCollectionContext:
    return _COLLECTION_TYPE_CONTEXTS.get(collection_type, _DEFAULT_AWARD_CONTEXT)


class PublicSignUpResult:
    """Result of attempting to associate a user with a grant via public sign-up."""

    def __init__(
        self,
        *,
        success: bool,
        organisation_id: uuid.UUID | None = None,
        grant_id: uuid.UUID | None = None,
    ) -> None:
        self.success = success
        self.organisation_id = organisation_id
        self.grant_id = grant_id


def process_public_grant_sign_up(user_email: str, grant_id_str: str) -> PublicSignUpResult | None:
    """Process public sign-up: match user email domain to an organisation, create grant recipient if needed.

    Returns a PublicSignUpResult if the user was successfully associated, or None if no match was found.
    """
    from app.common.data import interfaces
    from app.common.data.interfaces.grant_recipients import (
        create_grant_recipients,
        get_grant_recipient_or_none,
    )
    from app.common.data.interfaces.grants import get_grant_with_open_public_sign_up_collection
    from app.common.data.interfaces.organisations import get_organisation_by_email_domain

    try:
        grant_id = uuid.UUID(grant_id_str)
    except ValueError:
        current_app.logger.warning(
            "Invalid grant ID in signing_up_for_grant_id session: %(grant_id)s",
            {"grant_id": grant_id_str},
        )
        return None

    grant = get_grant_with_open_public_sign_up_collection(grant_id)
    if not grant:
        current_app.logger.warning("Grant %(grant_id)s not eligible for public sign-up", {"grant_id": str(grant_id)})
        return None

    email_domain = user_email.rsplit("@", 1)[-1].lower() if "@" in user_email else None
    if not email_domain:
        return None

    organisation = get_organisation_by_email_domain(email_domain)
    if not organisation:
        current_app.logger.info(
            "No organisation found for email domain %(domain)s during public sign-up",
            {"domain": email_domain},
        )
        return None

    user = interfaces.user.get_user_by_email(email_address=user_email)
    if not user:
        return None

    grant_recipient = get_grant_recipient_or_none(grant_id, organisation.id)
    if not grant_recipient:
        create_grant_recipients(grant, organisation_ids=[organisation.id], status=GrantRecipientStatus.APPLYING)
        grant_recipient = get_grant_recipient_or_none(grant_id, organisation.id)
        if not grant_recipient:
            current_app.logger.error(
                "Failed to create grant recipient for org %(org_id)s on grant %(grant_id)s",
                {"org_id": str(organisation.id), "grant_id": str(grant_id)},
            )
            return None

    interfaces.user.add_permissions_to_user(
        user=user,
        permissions=[RoleEnum.DATA_PROVIDER],
        organisation_id=organisation.id,
        grant_id=grant_id,
    )

    return PublicSignUpResult(success=True, organisation_id=organisation.id, grant_id=grant_id)
