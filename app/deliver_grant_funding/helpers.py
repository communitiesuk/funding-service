from dataclasses import dataclass
from typing import TYPE_CHECKING

from flask import redirect, session, url_for
from flask.typing import ResponseReturnValue

from app.common.data import interfaces
from app.common.data.interfaces.collections import (
    create_submission,
    delete_collection_preview_submissions_created_by_user,
    get_submissions_by_user,
)
from app.common.data.types import CollectionType, SubmissionModeEnum
from app.common.helpers.collections import SubmissionHelper
from app.extensions import s3_service

if TYPE_CHECKING:
    from app.common.data.models import Collection, Form


@dataclass(frozen=True)
class CollectionTypeConfig:
    """Display configuration for a collection type, used to adapt routes and templates."""

    collection_type: CollectionType
    singular_name: str  # "report", "application"
    plural_name: str  # "reports", "applications"
    title_name: str  # "Reports", "Applications"
    setup_label: str  # "monitoring report", "application"
    list_route: str  # "deliver_grant_funding.list_reports"
    setup_route: str  # "deliver_grant_funding.set_up_report"
    active_nav_item: str  # "reports", "applications"
    active_sub_nav_item: str | None  # "reports", "allocation", "applications", or None if no sub nav
    has_reporting_period: bool


COLLECTION_TYPE_CONFIGS: dict[CollectionType, CollectionTypeConfig] = {
    CollectionType.MONITORING_REPORT: CollectionTypeConfig(
        collection_type=CollectionType.MONITORING_REPORT,
        singular_name="report",
        plural_name="reports",
        title_name="Reports",
        setup_label="monitoring report",
        list_route="deliver_grant_funding.list_reports",
        setup_route="deliver_grant_funding.set_up_report",
        active_nav_item="reports",
        active_sub_nav_item=None,
        has_reporting_period=True,
    ),
    CollectionType.APPLICATION: CollectionTypeConfig(
        collection_type=CollectionType.APPLICATION,
        singular_name="application",
        plural_name="applications",
        title_name="Applications",
        setup_label="application",
        list_route="deliver_grant_funding.list_applications",
        setup_route="deliver_grant_funding.set_up_application",
        active_nav_item="recipients",
        active_sub_nav_item="applications",
        has_reporting_period=False,
    ),
    CollectionType.ALLOCATION: CollectionTypeConfig(
        collection_type=CollectionType.ALLOCATION,
        singular_name="allocation",
        plural_name="allocations",
        title_name="Allocations",
        setup_label="allocation",
        list_route="deliver_grant_funding.list_applications",
        setup_route="deliver_grant_funding.set_up_application",
        active_nav_item="recipients",
        active_sub_nav_item="applications",
        has_reporting_period=False,
    ),
    CollectionType.EXPRESSION_OF_INTEREST: CollectionTypeConfig(
        collection_type=CollectionType.EXPRESSION_OF_INTEREST,
        singular_name="expression of interest",
        plural_name="expressions of interest",
        title_name="Expressions of Interest",
        setup_label="expression of interest",
        list_route="deliver_grant_funding.list_applications",
        setup_route="deliver_grant_funding.set_up_application",
        active_nav_item="recipients",
        active_sub_nav_item="applications",
        has_reporting_period=False,
    ),
}


def get_collection_type_config(collection_type: CollectionType) -> CollectionTypeConfig:
    return COLLECTION_TYPE_CONFIGS[collection_type]


def start_previewing_collection(collection: Collection, form: Form | None = None) -> ResponseReturnValue:
    user = interfaces.user.get_current_user()

    file_prefixes_to_delete = [
        submission.s3_key_prefix
        for submission in get_submissions_by_user(
            user, collection_id=collection.id, submission_mode=SubmissionModeEnum.PREVIEW
        )
    ]

    delete_collection_preview_submissions_created_by_user(collection=collection, created_by_user=user)
    submission = create_submission(collection=collection, created_by=user, mode=SubmissionModeEnum.PREVIEW)
    helper = SubmissionHelper(submission)

    for file_prefix in file_prefixes_to_delete:
        s3_service.delete_prefix(file_prefix)

    # Pop this if it exists; sanity check for not terminating a session correctly
    session.pop("test_submission_form_id", None)
    if form:
        question = helper.get_first_question_for_form(form)
        if question:
            session["test_submission_form_id"] = form.id
            return redirect(
                url_for(
                    "deliver_grant_funding.ask_a_question",
                    grant_id=collection.grant_id,
                    submission_id=helper.submission.id,
                    question_id=question.id,
                )
            )

    return redirect(
        url_for(
            "deliver_grant_funding.submission_tasklist",
            grant_id=collection.grant_id,
            submission_id=helper.submission.id,
        )
    )
