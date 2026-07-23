import re
import uuid
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from app.common.data.types import (
    GrantRecipientStatusEnum,
    GroupDisplayOptions,
    NumberTypeEnum,
    QuestionDataOptions,
    QuestionDataType,
    QuestionPresentationOptions,
)
from app.common.expressions import EvaluationStatement, ExpressionContext, InterpolationStatement
from app.common.expressions.custom import CustomExpression
from app.common.expressions.managed import GreaterThan
from tests.e2e.access_grant_funding.pages import AccessHomePage
from tests.e2e.config import EndToEndTestSecrets
from tests.e2e.conftest import (
    DeliverGrantFundingUserType,
    e2e_user_configs,
)
from tests.e2e.dataclasses import (
    DataReferenceConfig,
    E2EManagedExpression,
    E2ETestUser,
    QuestionDict,
    QuestionGroupDict,
    QuestionResponse,
    ReportDict,
    SectionDict,
    TextFieldWithData,
)
from tests.e2e.deliver_grant_funding.helpers import create_grant, extract_uuid_from_url
from tests.e2e.deliver_grant_funding.pages import AllGrantsPage, GrantDashboardPage
from tests.e2e.deliver_grant_funding.reports_pages import (
    DeliverTestGrantRecipientJourneyPage,
    GrantReportsPage,
    MarkAsOnboardingWithFundingServicePage,
    PlatformAdminGrantSettingsPage,
    PlatformAdminReportSettingsPage,
    RunnerTasklistPage,
    SetPrivacyPolicyPage,
    SetReportingDatesPage,
    SetSubmissionDatesPage,
    SetUpGrantRecipientsPage,
    SetUpOrganisationsPage,
    UploadedDataSetsPage,
)
from tests.e2e.deliver_grant_funding.test_create_preview_collection import (
    complete_task,
    create_question_or_group,
    switch_user,
    task_check_your_answers,
)
from tests.e2e.helpers import (
    delete_grant_recipient_through_admin,
    delete_grant_through_admin,
)

SPACE_COUNT_COLUMN = "Free spaces"
GROUP_QUESTION_TEXT = "How many spaces should we keep back?"
GROUP_VALIDATION_ERROR = "Only 100 spaces are free"


def _add_grant_team_member(page: Page, domain: str, grant_id: str, grant_name: str, email_address: str) -> None:
    grant_reports_page = GrantReportsPage(page, domain, grant_name)
    grant_reports_page.navigate(grant_id)
    grant_team_page = grant_reports_page.click_nav_grant_team()
    add_grant_team_member_page = grant_team_page.click_add_grant_team_member()
    add_grant_team_member_page.fill_in_user_email(email_address)
    add_grant_team_member_page.click_continue()


def _create_report(
    page: Page, domain: str, grant_dashboard_page: GrantDashboardPage, grant_name: str
) -> tuple[str, str]:
    grant_reports_page = grant_dashboard_page.click_reports(grant_name)

    choose_method_page = grant_reports_page.click_add_report()
    add_report_page = choose_method_page.click_create_new()
    report_name = f"E2E shelf check report {uuid.uuid4()}"
    add_report_page.fill_in_report_name(report_name)
    grant_reports_page = add_report_page.click_submit(grant_name)
    grant_reports_page.check_report_exists(report_name)

    page.get_by_role("link", name="0 data sets").click()
    expect(page.get_by_role("heading", name="Uploaded data sets")).to_be_visible()
    return report_name, extract_uuid_from_url(page.url, r"/reports/(?P<uuid>[a-f0-9-]+)")


def _start_grant_with_recipients(
    page: Page, domain: str, grant_name: str, unique_id: str
) -> tuple[str, str, str, str, str, str, str]:
    all_grants_page = AllGrantsPage(page, domain)
    all_grants_page.navigate()
    grant_dashboard_page = create_grant(grant_name, unique_id, all_grants_page)
    grant_id = extract_uuid_from_url(page.url, r"/grant/(?P<uuid>[a-f0-9-]+)")
    report_name, collection_id = _create_report(page, domain, grant_dashboard_page, grant_name)
    external_id_1, external_id_2, organisation_1, organisation_2 = _set_up_grant_recipients(
        page, domain, grant_id, collection_id, unique_id
    )

    return grant_id, collection_id, report_name, external_id_1, external_id_2, organisation_1, organisation_2


def _set_up_grant_recipients(
    page: Page, domain: str, grant_id: str, collection_id: str, unique_id: str
) -> tuple[str, str, str, str]:
    external_id_1 = f"E2E-ANDY-{unique_id[:8].upper()}-1"
    external_id_2 = f"E2E-BONNIE-{unique_id[:8].upper()}-2"
    organisation_1 = f"E2E Andy's room {unique_id[:8]}"
    organisation_2 = f"E2E Bonnie's room {unique_id[:8]}"

    set_up_orgs_page = SetUpOrganisationsPage(page, domain, grant_id, collection_id)
    set_up_orgs_page.navigate()
    set_up_orgs_page.fill_organisations_tsv_data(
        "organisation-id\torganisation-name\ttype\tactive-date\tretirement-date\n"
        f"{external_id_1}\t{organisation_1}\tUnitary Authority\t\t\n"
        f"{external_id_2}\t{organisation_2}\tUnitary Authority\t\t\n"
    )
    set_up_orgs_page.click_set_up_organisations(
        expected_organisations_created=2,
    )

    set_up_grant_recipients_page = SetUpGrantRecipientsPage(page, domain, grant_id, collection_id)
    set_up_grant_recipients_page.navigate()
    set_up_grant_recipients_page.select_organisations([organisation_1, organisation_2])
    set_up_grant_recipients_page.select_status(GrantRecipientStatusEnum.AWARDED)
    set_up_grant_recipients_page.click_set_up_grant_recipients(
        expected_message="Created 2 grant recipients and 2 test grant recipients."
    )

    return external_id_1, external_id_2, organisation_1, organisation_2


def _write_data_set_csv(
    csv_path: Path,
    external_id_1: str,
    external_id_2: str,
    organisation_1: str,
    organisation_2: str,
    replacement: bool = False,
) -> None:
    second_row_spaces = "80" if replacement else ""
    second_row_note = "Found under the bed" if replacement else ""
    csv_path.write_text(
        f"Organisation ID,Grant recipient,{SPACE_COUNT_COLUMN},Pizza Planet tokens,Shelf note,Notes\n"
        f"{external_id_1},{organisation_1},100,250.50,Ready for pickup,Marked with a boot\n"
        f"{external_id_2},{organisation_2},{second_row_spaces},125.75,Needs batteries,{second_row_note}\n",
        encoding="utf-8",
    )


def _upload_data_set(
    page: Page,
    domain: str,
    grant_id: str,
    collection_id: str,
    csv_path: Path,
    data_set_name: str,
    complete_organisation_name: str,
    missing_data_organisation_name: str,
) -> None:
    uploaded_data_sets_page = UploadedDataSetsPage(page, domain)
    uploaded_data_sets_page.navigate(grant_id, collection_id)
    upload_data_set_page = uploaded_data_sets_page.click_upload_new_data_set()

    upload_data_set_page.fill_data_set_name(data_set_name)
    upload_data_set_page.upload_file(str(csv_path))
    review_missing_data_page = upload_data_set_page.click_continue_and_format_data(data_set_name)

    review_missing_data_page.expect_organisation_with_missing_data(missing_data_organisation_name)
    review_missing_data_page.expect_organisation_without_missing_data(complete_organisation_name)
    map_columns_page = review_missing_data_page.click_continue()

    map_columns_page.select_data_set_column_type(SPACE_COUNT_COLUMN, "Whole number")
    map_columns_page.select_data_set_column_type("Pizza Planet tokens", "Decimal number")
    map_columns_page.select_data_set_column_type("Shelf note", "Text")
    map_columns_page.select_data_set_column_type("Notes", "Text")
    map_number_columns_page = map_columns_page.click_continue()

    map_number_columns_page.set_max_decimal_places(column_name="Pizza Planet tokens", decimal_places=2)
    confirm_data_set_page = map_number_columns_page.click_continue()
    confirm_data_set_page.click_upload_data_set()

    expect(page.get_by_role("link", name=data_set_name)).to_be_visible()
    expect(page.get_by_text("Data missing")).to_be_visible()


def _replace_data_set(page: Page, data_set_name: str, csv_path: Path) -> None:
    expect(page.get_by_role("heading", name=re.compile(data_set_name))).to_be_visible()
    page.get_by_role("link", name="Replace data set").click()

    expect(page.get_by_role("heading", name=re.compile(f"Replace {re.escape(data_set_name)} data set"))).to_be_visible()
    page.locator("input[type='file']").set_input_files(str(csv_path))
    page.get_by_role("button", name="Check and replace data set").click()

    expect(page.get_by_role("heading", name=re.compile(f"Confirm {re.escape(data_set_name)} data"))).to_be_visible()
    page.get_by_role("button", name="Upload data set").click()

    expect(page.get_by_role("heading", name=f"{data_set_name} data set replaced")).to_be_visible()
    expect(page.get_by_role("link", name="Replace data set")).to_be_visible()
    expect(page.get_by_text("Data missing")).to_have_count(0)
    expect(page.get_by_text("Found under the bed")).to_be_visible()


def _delete_uploaded_data_set(page: Page, domain: str, grant_id: str, collection_id: str, data_set_name: str) -> None:
    page.goto(f"{domain}/deliver/grant/{grant_id}/reports/{collection_id}/data-sets")
    data_set_link = page.get_by_role("link", name=data_set_name)
    if not data_set_link.is_visible():
        return

    data_set_link.click()
    expect(page.get_by_role("heading", name=re.compile(data_set_name))).to_be_visible()
    page.get_by_role("link", name="Delete data set").click()

    confirm_delete_button = page.get_by_role("button", name="Yes, delete this data set")
    if confirm_delete_button.is_visible(timeout=5_000):
        confirm_delete_button.click()
        expect(page.get_by_text(f"'{data_set_name}' data set has been deleted.")).to_be_visible()


def _set_collection_to_draft(page: Page, domain: str, collection_id: str) -> None:
    report_settings_page = PlatformAdminReportSettingsPage(page, domain, collection_id)
    report_settings_page.navigate()
    report_settings_page.select_collection_status("DRAFT")
    report_settings_page.click_save()


def _delete_section_from_draft_collection(page: Page, domain: str, grant_id: str, section_id: str) -> None:
    page.goto(f"{domain}/deliver/grant/{grant_id}/section/{section_id}/questions?delete")
    expect(page.get_by_role("heading", name=re.compile("E2E shelf check section"))).to_be_visible()
    page.get_by_role("button", name="Yes, delete this section").click()
    expect(page.get_by_role("heading", name=re.compile("E2E shelf check report"))).to_be_visible()


def _open_report_for_test_recipient(
    page: Page,
    domain: str,
    grant_id: str,
    collection_id: str,
    grant_name: str,
    report_name: str,
    organisation_name: str,
) -> RunnerTasklistPage:
    test_journey_page = DeliverTestGrantRecipientJourneyPage(page, domain, grant_id, collection_id, report_name)
    test_journey_page.navigate()
    test_journey_page.select_test_organisation(f"{organisation_name} (test)")
    test_journey_page.click_start_test_journey()

    access_home = AccessHomePage(page, domain)
    access_home.navigate()
    access_home.click_accept_cookies()
    access_grant = access_home.select_grant(f"{organisation_name} (test)", grant_name)
    access_grant.click_collection(report_name)

    return RunnerTasklistPage(page, domain, grant_name, report_name)


def _report_with_data_set_references(
    report_name: str, section_name: str, group_name: str, data_set_name: str
) -> ReportDict:
    free_spaces_data_reference = DataReferenceConfig(
        data_source=ExpressionContext.ContextSources.DATASET,
        data_set_name=data_set_name,
        column_name=SPACE_COUNT_COLUMN,
    )
    return ReportDict(
        id=None,
        name=report_name,
        require_certification=False,
        allow_multi_submissions=False,
        sections=[
            SectionDict(
                name=section_name,
                components=[
                    QuestionDict(
                        type=QuestionDataType.TEXT_SINGLE_LINE,
                        text="What should we keep aside from",
                        display_text="What should we keep aside from 100",
                        text_reference=free_spaces_data_reference,
                        hint=TextFieldWithData(
                            prefix="Use the room count before deciding",
                            data_reference=free_spaces_data_reference,
                        ),
                        display_hint="Use the room count before deciding 100",
                        answers=[
                            QuestionResponse("Keep a few spaces free for later"),
                        ],
                    ),
                    QuestionGroupDict(
                        type="group",
                        text=group_name,
                        display_options=GroupDisplayOptions.ALL_QUESTIONS_ON_SAME_PAGE,
                        condition=E2EManagedExpression(
                            conditional_on=free_spaces_data_reference,
                            evaluatable_expression=GreaterThan(
                                subject_reference="q_00000000000000000000000000001234",
                                minimum_value=0,
                                inclusive=False,
                            ),
                        ),
                        validation=E2EManagedExpression(
                            evaluatable_expression=CustomExpression(
                                custom_expression=EvaluationStatement("((ref1)) <= ((ref2))"),
                                custom_message=InterpolationStatement(GROUP_VALIDATION_ERROR),
                            ),
                            expression_references={
                                "ref1": DataReferenceConfig(
                                    data_source=ExpressionContext.ContextSources.SECTION,
                                    question_text=GROUP_QUESTION_TEXT,
                                ),
                                "ref2": free_spaces_data_reference,
                            },
                        ),
                        questions=[
                            QuestionDict(
                                type=QuestionDataType.NUMBER,
                                text=GROUP_QUESTION_TEXT,
                                display_text=GROUP_QUESTION_TEXT,
                                options=QuestionPresentationOptions(),
                                data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
                                answers=[
                                    QuestionResponse("101", expect_group_validation_error=True),
                                    QuestionResponse("50"),
                                ],
                            )
                        ],
                    ),
                ],
            )
        ],
    )


def _make_report_available_to_test_recipients(
    page: Page, domain: str, grant_id: str, collection_id: str, grant_name: str, report_name: str
) -> None:
    page.goto(f"{domain}/deliver/admin/collection-lifecycle/{grant_id}/{collection_id}")
    page.get_by_role("link", name=re.compile("Set reporting dates")).click()
    set_reporting_dates_page = SetReportingDatesPage(page, domain, grant_id, collection_id)
    set_reporting_dates_page.set_reporting_dates_for_open_report()
    set_reporting_dates_page.click_save_dates(report_name=report_name)

    page.goto(f"{domain}/deliver/admin/collection-lifecycle/{grant_id}/{collection_id}")
    page.get_by_role("link", name=re.compile("Set submission dates")).click()
    set_submission_dates_page = SetSubmissionDatesPage(page, domain, grant_id, collection_id)
    set_submission_dates_page.set_submission_dates_for_open_report()
    set_submission_dates_page.click_save_dates(report_name=report_name)

    page.goto(f"{domain}/deliver/admin/collection-lifecycle/{grant_id}/{collection_id}")
    page.get_by_role("link", name=re.compile("Mark as onboarding with Funding Service")).click()
    mark_as_onboarding_page = MarkAsOnboardingWithFundingServicePage(page, domain, grant_id, collection_id)
    mark_as_onboarding_page.click_mark_as_onboarding()

    page.goto(f"{domain}/deliver/admin/collection-lifecycle/{grant_id}/{collection_id}")
    page.get_by_role("link", name=re.compile("Set privacy policy")).click()
    set_privacy_policy_page = SetPrivacyPolicyPage(page, domain, grant_id, collection_id)
    set_privacy_policy_page.fill_privacy_policy_markdown("https://www.gov.uk/help/privacy-notice")
    set_privacy_policy_page.click_save_privacy_policy()

    grant_settings_page = PlatformAdminGrantSettingsPage(page, domain, grant_id)
    grant_settings_page.navigate()
    grant_settings_page.select_grant_status("LIVE")
    grant_settings_page.click_save()

    report_settings_page = PlatformAdminReportSettingsPage(page, domain, collection_id)
    report_settings_page.navigate()
    report_settings_page.select_collection_status("OPEN")
    report_settings_page.click_save()


def _reset_test_submission(
    page: Page, domain: str, grant_id: str, grant_name: str, report_name: str, organisation_name: str
) -> None:
    # Reset submission before deleting grant recipients
    grant_reports_page = GrantReportsPage(page, domain, grant_name)
    grant_reports_page.navigate(grant_id)
    submissions_list_page = grant_reports_page.click_view_submissions(report_name)
    view_submission_page = submissions_list_page.click_on_submission(f"{organisation_name} (test)")
    view_submission_page.click_reset_submission()


@pytest.mark.skip_in_environments(["prod"])
def test_upload_data_set_with_complete_and_missing_data(
    page: Page,
    domain: str,
    tmp_path: Path,
    e2e_test_secrets: EndToEndTestSecrets,
    authenticated_browser_sso: E2ETestUser,
):
    grant_name_uuid = str(uuid.uuid4())
    grant_name = f"E2E toy shelf upload grant {grant_name_uuid}"
    grant_id = None
    collection_id = None
    data_set_name = None
    grant_recipients_created = False

    try:
        (
            grant_id,
            collection_id,
            _,
            external_id_1,
            external_id_2,
            organisation_1,
            organisation_2,
        ) = _start_grant_with_recipients(
            page,
            domain,
            grant_name,
            grant_name_uuid,
        )
        grant_recipients_created = True

        csv_path = tmp_path / "toy-shelf-data-with-complete-and-missing-data.csv"
        _write_data_set_csv(csv_path, external_id_1, external_id_2, organisation_1, organisation_2)

        data_set_name = f"E2E toy shelf data {grant_name_uuid[:8]}"
        _upload_data_set(page, domain, grant_id, collection_id, csv_path, data_set_name, organisation_1, organisation_2)

        page.get_by_role("link", name=data_set_name).click()
        expect(page.get_by_role("heading", name=re.compile(data_set_name))).to_be_visible()
        expect(page.get_by_text("Marked with a boot")).to_be_visible()
        expect(page.get_by_text("Data missing").first).to_be_visible()
    finally:
        if grant_id and collection_id and data_set_name:
            _delete_uploaded_data_set(page, domain, grant_id, collection_id, data_set_name)
        if grant_recipients_created:
            delete_grant_recipient_through_admin(
                page, domain, grant_name_uuid, expected_grant_recipients_matching_search=4
            )
        if grant_id:
            delete_grant_through_admin(page, domain, grant_name_uuid)


@pytest.mark.skip_in_environments(["prod"])
def test_replace_data_set_fills_missing_data(
    page: Page,
    domain: str,
    tmp_path: Path,
    e2e_test_secrets: EndToEndTestSecrets,
    authenticated_browser_sso: E2ETestUser,
):
    grant_name_uuid = str(uuid.uuid4())
    grant_name = f"E2E toy shelf replace grant {grant_name_uuid}"
    grant_id = None
    collection_id = None
    data_set_name = None
    grant_recipients_created = False

    try:
        (
            grant_id,
            collection_id,
            _,
            external_id_1,
            external_id_2,
            organisation_1,
            organisation_2,
        ) = _start_grant_with_recipients(
            page,
            domain,
            grant_name,
            grant_name_uuid,
        )
        grant_recipients_created = True

        csv_path = tmp_path / "toy-shelf-data-with-missing-data.csv"
        _write_data_set_csv(csv_path, external_id_1, external_id_2, organisation_1, organisation_2)

        data_set_name = f"E2E toy box count {grant_name_uuid[:8]}"
        _upload_data_set(page, domain, grant_id, collection_id, csv_path, data_set_name, organisation_1, organisation_2)

        page.get_by_role("link", name=data_set_name).click()
        expect(page.get_by_role("heading", name=re.compile(data_set_name))).to_be_visible()
        expect(page.get_by_text("Data missing").first).to_be_visible()

        replacement_csv_path = tmp_path / "toy-shelf-data-without-missing-data.csv"
        _write_data_set_csv(
            replacement_csv_path, external_id_1, external_id_2, organisation_1, organisation_2, replacement=True
        )
        _replace_data_set(page, data_set_name, replacement_csv_path)
    finally:
        if grant_id and collection_id and data_set_name:
            _delete_uploaded_data_set(page, domain, grant_id, collection_id, data_set_name)
        if grant_recipients_created:
            delete_grant_recipient_through_admin(
                page, domain, grant_name_uuid, expected_grant_recipients_matching_search=4
            )
        if grant_id:
            delete_grant_through_admin(page, domain, grant_name_uuid)


@pytest.mark.skip_in_environments(["prod"])
def test_complete_report_with_data_set_reference(
    page: Page,
    domain: str,
    tmp_path: Path,
    e2e_test_secrets: EndToEndTestSecrets,
    authenticated_browser_sso: E2ETestUser,
    email,
):
    grant_name_uuid = str(uuid.uuid4())
    grant_name = f"E2E toy shelf reference grant {grant_name_uuid}"
    data_set_name = f"E2E room inventory {grant_name_uuid[:8]}"
    csv_path = tmp_path / "toy-shelf-reference-data.csv"

    is_platform_admin = True
    grant_id = None
    collection_id = None
    section_id = None
    report_name = None
    organisation_1 = None
    grant_recipients_created = False
    test_submission_created = False

    try:
        (
            grant_id,
            collection_id,
            report_name,
            external_id_1,
            external_id_2,
            organisation_1,
            organisation_2,
        ) = _start_grant_with_recipients(
            page,
            domain,
            grant_name,
            grant_name_uuid,
        )
        grant_recipients_created = True

        grant_team_email = e2e_user_configs[DeliverGrantFundingUserType.GRANT_TEAM_MEMBER].email
        _add_grant_team_member(page, domain, grant_id, grant_name, grant_team_email)

        _write_data_set_csv(csv_path, external_id_1, external_id_2, organisation_1, organisation_2)
        _upload_data_set(page, domain, grant_id, collection_id, csv_path, data_set_name, organisation_1, organisation_2)

        section_name = f"E2E shelf check section {uuid.uuid4()}"
        group_name = f"E2E shelf check group {uuid.uuid4()}"
        report = _report_with_data_set_references(report_name, section_name, group_name, data_set_name)

        grant_reports_page = GrantReportsPage(page, domain, grant_name)
        grant_reports_page.navigate(grant_id)
        add_section_page = grant_reports_page.click_add_section(report_name=report_name, grant_name=grant_name)
        add_section_page.fill_in_section_name(section_name)
        report_sections_page = add_section_page.click_add_section()
        manage_section_page = report_sections_page.click_manage_section(section_name)
        section_id = extract_uuid_from_url(page.url, r"/section/(?P<uuid>[a-f0-9-]+)/questions")

        for component in report["sections"][0]["components"]:
            create_question_or_group(component, manage_section_page)

        section_name = report["sections"][0]["name"]

        _make_report_available_to_test_recipients(page, domain, grant_id, collection_id, grant_name, report_name)
        switch_user(
            page,
            domain,
            e2e_test_secrets,
            DeliverGrantFundingUserType.GRANT_TEAM_MEMBER,
            grant_team_email,
        )
        is_platform_admin = False
        tasklist_page = _open_report_for_test_recipient(
            page, domain, grant_id, collection_id, grant_name, report_name, organisation_1
        )
        expect(tasklist_page.page.get_by_role("link", name=section_name)).to_be_visible()
        complete_task(tasklist_page, section_name, grant_name, report["sections"][0]["components"])
        task_check_your_answers(tasklist_page, grant_name, report_name, report["sections"][0]["components"])

        expect(
            tasklist_page.submission_status_box.filter(has=tasklist_page.page.get_by_text("Ready to submit"))
        ).to_be_visible()
        test_submission_created = True
    finally:
        # TODO: Clean up all of the deletion logic after FSPT-1471 has been implemented - on all three test cases
        if not is_platform_admin:
            switch_user(page, domain, e2e_test_secrets, DeliverGrantFundingUserType.PLATFORM_ADMIN, email)
        if test_submission_created and grant_id and report_name and organisation_1:
            _reset_test_submission(page, domain, grant_id, grant_name, report_name, organisation_1)
        if grant_id and collection_id and section_id:
            _set_collection_to_draft(page, domain, collection_id)
            _delete_section_from_draft_collection(page, domain, grant_id, section_id)
        if grant_id and collection_id and data_set_name:
            _delete_uploaded_data_set(page, domain, grant_id, collection_id, data_set_name)
        if grant_recipients_created:
            delete_grant_recipient_through_admin(
                page, domain, grant_name_uuid, expected_grant_recipients_matching_search=4
            )
        delete_grant_through_admin(page, domain, grant_name_uuid)
