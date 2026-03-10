from dataclasses import dataclass

from app.common.data.types import CollectionType


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
