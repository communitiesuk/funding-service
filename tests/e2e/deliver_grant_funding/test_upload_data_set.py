import re
import uuid
from pathlib import Path
from typing import Callable

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
    switch_user,
)
from tests.e2e.dataclasses import (
    BuiltGrantScenario,
    CollectionConfig,
    DataReferenceConfig,
    E2EManagedExpression,
    GrantScenario,
    OrganisationConfig,
    QuestionDict,
    QuestionGroupDict,
    QuestionResponse,
    ReportDict,
    SectionDict,
    TextFieldWithData,
)
from tests.e2e.deliver_grant_funding.helpers import (
    complete_task,
    create_question_or_group,
    mark_as_onboarding,
    set_grant_and_collection_live,
    set_privacy_policy,
    set_reporting_and_submission_dates,
    task_check_your_answers,
)
from tests.e2e.deliver_grant_funding.reports_pages import (
    DeliverTestGrantRecipientJourneyPage,
    GrantReportsPage,
    RunnerTasklistPage,
    UploadedDataSetsPage,
)

SPACE_COUNT_COLUMN = "Free spaces"
GROUP_QUESTION_TEXT = "How many spaces should we keep back?"
GROUP_VALIDATION_ERROR = "Only 100 spaces are free"


def _write_data_set_csv(
    csv_path: Path,
    external_id_1: str,
    external_id_2: str,
    organisation_1: str,
    organisation_2: str,
    *,
    has_missing_data: bool,
) -> None:
    second_row_spaces = "" if has_missing_data else "80"
    second_row_note = "" if has_missing_data else "Found under the bed"
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
    page: Page, domain: str, grant_id: str, collection_id: str, report_name: str
) -> None:
    set_reporting_and_submission_dates(page, domain, grant_id, collection_id, report_name)
    mark_as_onboarding(page, domain, grant_id, collection_id)
    set_privacy_policy(page, domain, grant_id, collection_id)
    set_grant_and_collection_live(page, domain, grant_id, collection_id)


def _build_shelf_scenario(
    build_grant_scenario: Callable[..., BuiltGrantScenario], report_name: str
) -> tuple[BuiltGrantScenario, str, str, str, str]:
    """Build a grant/report with two grant recipients. Returns the handle plus the external ids/names needed to
    write a matching data set CSV."""
    organisation_1 = f"E2E Andy's room {uuid.uuid4()}"
    organisation_2 = f"E2E Bonnie's room {uuid.uuid4()}"
    external_id_1 = f"E2E-ANDY-{uuid.uuid4().hex[:8].upper()}"
    external_id_2 = f"E2E-BONNIE-{uuid.uuid4().hex[:8].upper()}"

    handle = build_grant_scenario(
        GrantScenario(
            collection=CollectionConfig(name=report_name),
            organisations=[
                OrganisationConfig(
                    name=organisation_1,
                    external_id=external_id_1,
                    type="Unitary Authority",
                    grant_recipient_status=GrantRecipientStatusEnum.AWARDED,
                    set_certifiers=False,
                ),
                OrganisationConfig(
                    name=organisation_2,
                    external_id=external_id_2,
                    type="Unitary Authority",
                    grant_recipient_status=GrantRecipientStatusEnum.AWARDED,
                    set_certifiers=False,
                ),
            ],
        )
    )
    return handle, external_id_1, external_id_2, organisation_1, organisation_2


@pytest.mark.skip_in_environments(["prod"])
def test_upload_data_set_with_complete_and_missing_data(
    page: Page,
    domain: str,
    tmp_path: Path,
    build_grant_scenario: Callable[..., BuiltGrantScenario],
):
    report_name = f"E2E shelf check report {uuid.uuid4()}"
    handle, external_id_1, external_id_2, organisation_1, organisation_2 = _build_shelf_scenario(
        build_grant_scenario, report_name
    )

    csv_path = tmp_path / "toy-shelf-data-with-complete-and-missing-data.csv"
    _write_data_set_csv(csv_path, external_id_1, external_id_2, organisation_1, organisation_2, has_missing_data=True)

    data_set_name = f"E2E toy shelf data {uuid.uuid4().hex[:8]}"
    _upload_data_set(
        page, domain, handle.grant_id, handle.collection_id, csv_path, data_set_name, organisation_1, organisation_2
    )

    page.get_by_role("link", name=data_set_name).click()
    expect(page.get_by_role("heading", name=re.compile(data_set_name))).to_be_visible()
    expect(page.get_by_text("Marked with a boot")).to_be_visible()
    expect(page.get_by_text("Data missing").first).to_be_visible()


@pytest.mark.skip_in_environments(["prod"])
def test_replace_data_set_fills_missing_data(
    page: Page,
    domain: str,
    tmp_path: Path,
    build_grant_scenario: Callable[..., BuiltGrantScenario],
):
    report_name = f"E2E shelf check report {uuid.uuid4()}"
    handle, external_id_1, external_id_2, organisation_1, organisation_2 = _build_shelf_scenario(
        build_grant_scenario, report_name
    )

    csv_path = tmp_path / "toy-shelf-data-with-missing-data.csv"
    _write_data_set_csv(csv_path, external_id_1, external_id_2, organisation_1, organisation_2, has_missing_data=True)

    data_set_name = f"E2E toy box count {uuid.uuid4().hex[:8]}"
    _upload_data_set(
        page, domain, handle.grant_id, handle.collection_id, csv_path, data_set_name, organisation_1, organisation_2
    )

    page.get_by_role("link", name=data_set_name).click()
    expect(page.get_by_role("heading", name=re.compile(data_set_name))).to_be_visible()
    expect(page.get_by_text("Data missing").first).to_be_visible()

    replacement_csv_path = tmp_path / "toy-shelf-data-without-missing-data.csv"
    _write_data_set_csv(
        replacement_csv_path,
        external_id_1,
        external_id_2,
        organisation_1,
        organisation_2,
        has_missing_data=False,
    )
    _replace_data_set(page, data_set_name, replacement_csv_path)


@pytest.mark.skip_in_environments(["prod"])
def test_complete_report_with_data_set_reference(
    page: Page,
    domain: str,
    tmp_path: Path,
    e2e_test_secrets: EndToEndTestSecrets,
    email: str,
    build_grant_scenario: Callable[..., BuiltGrantScenario],
):
    report_name = f"E2E shelf check report {uuid.uuid4()}"
    data_set_name = f"E2E room inventory {uuid.uuid4().hex[:8]}"
    csv_path = tmp_path / "toy-shelf-reference-data.csv"

    handle, external_id_1, external_id_2, organisation_1, organisation_2 = _build_shelf_scenario(
        build_grant_scenario, report_name
    )

    # Sections reference the data set, so it must be uploaded before they're built - this can't be expressed as
    # part of the initial scenario build.
    grant_team_email = e2e_user_configs[DeliverGrantFundingUserType.GRANT_TEAM_MEMBER].email
    grant_reports_page = GrantReportsPage(page, domain, handle.grant_name)
    grant_reports_page.navigate(handle.grant_id)
    grant_team_page = grant_reports_page.click_nav_grant_team()
    add_grant_team_member_page = grant_team_page.click_add_grant_team_member()
    add_grant_team_member_page.fill_in_user_email(grant_team_email)
    add_grant_team_member_page.click_continue()

    _write_data_set_csv(csv_path, external_id_1, external_id_2, organisation_1, organisation_2, has_missing_data=True)
    _upload_data_set(
        page, domain, handle.grant_id, handle.collection_id, csv_path, data_set_name, organisation_1, organisation_2
    )

    section_name = f"E2E shelf check section {uuid.uuid4()}"
    group_name = f"E2E shelf check group {uuid.uuid4()}"
    report = _report_with_data_set_references(report_name, section_name, group_name, data_set_name)

    grant_reports_page = GrantReportsPage(page, domain, handle.grant_name)
    grant_reports_page.navigate(handle.grant_id)
    add_section_page = grant_reports_page.click_add_section(report_name=report_name, grant_name=handle.grant_name)
    add_section_page.fill_in_section_name(section_name)
    report_sections_page = add_section_page.click_add_section()
    manage_section_page = report_sections_page.click_manage_section(section_name)

    for component in report["sections"][0]["components"]:
        create_question_or_group(component, manage_section_page)

    section_name = report["sections"][0]["name"]

    _make_report_available_to_test_recipients(page, domain, handle.grant_id, handle.collection_id, report_name)
    switch_user(page, domain, e2e_test_secrets, DeliverGrantFundingUserType.GRANT_TEAM_MEMBER, grant_team_email)
    tasklist_page = _open_report_for_test_recipient(
        page, domain, handle.grant_id, handle.collection_id, handle.grant_name, report_name, organisation_1
    )
    expect(tasklist_page.page.get_by_role("link", name=section_name)).to_be_visible()
    complete_task(tasklist_page, section_name, handle.grant_name, report["sections"][0]["components"])
    task_check_your_answers(tasklist_page, handle.grant_name, report_name, report["sections"][0]["components"])

    expect(
        tasklist_page.submission_status_box.filter(has=tasklist_page.page.get_by_text("Ready to submit"))
    ).to_be_visible()
