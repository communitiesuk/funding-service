import datetime
import uuid
from decimal import Decimal

import pytest
from playwright.sync_api import Page, expect

from app import NumberTypeEnum
from app.common.data.types import (
    ManagedExpressionsEnum,
    MultilineTextInputRows,
    NumberInputWidths,
    QuestionDataOptions,
    QuestionDataType,
    QuestionPresentationOptions,
)
from app.common.expressions import ExpressionContext
from app.common.expressions.custom import CustomExpression
from app.common.expressions.managed import (
    AnyOf,
    Between,
    BetweenDates,
    GreaterThan,
    IsNo,
    IsYes,
    LessThan,
    Specifically,
    UKPostcode,
)
from tests.e2e.access_grant_funding.pages import AccessGrantPage, AccessHomePage
from tests.e2e.config import EndToEndTestSecrets
from tests.e2e.conftest import (
    TEST_DATA_TO_BE_SEEDED,
    DeliverGrantFundingUserType,
    e2e_user_configs,
)
from tests.e2e.dataclasses import (
    DataReferenceConfig,
    E2EManagedExpression,
    E2ETestUser,
    GuidanceText,
    QuestionDict,
    QuestionResponse,
    ReportDict,
    SectionDict,
    TextFieldWithData,
)
from tests.e2e.deliver_grant_funding.helpers import (
    complete_task,
    create_question_or_group,
    extract_uuid_from_url,
    navigate_to_report_sections_page,
    switch_user,
    task_check_your_answers,
)
from tests.e2e.deliver_grant_funding.pages import AllGrantsPage, GrantDetailsPage
from tests.e2e.deliver_grant_funding.reports_pages import (
    AdminReportingLifecycleTasklistPage,
    DeliverTestGrantRecipientJourneyPage,
    GrantReportsPage,
    MarkAsOnboardingWithFundingServicePage,
    OverrideGrantRecipientCertifiersPage,
    PlatformAdminGrantSettingsPage,
    PlatformAdminReportSettingsPage,
    RunnerTasklistPage,
    SetPrivacyPolicyPage,
    SetReportingDatesPage,
    SetUpDataProvidersPage,
    SetUpGrantRecipientsPage,
    SetUpOrganisationsPage,
    ViewLockedReportPage,
)
from tests.e2e.helpers import (
    delete_grant_recipient_through_admin,
    delete_grant_through_admin,
)

report_with_all_question_types: ReportDict = {
    "id": None,
    "name": f"E2E Report with all question types {str(uuid.uuid4())}",
    "require_certification": True,
    "allow_multi_submissions": False,
    "sections": [
        SectionDict(
            name="E2E second task - all question types",
            components=[
                QuestionDict(
                    type=QuestionDataType.DATE,
                    text="Enter a date",
                    display_text="Enter a date",
                    answers=[
                        QuestionResponse(
                            ["2003", "2", "01"],
                            "The answer must be between 1 January 2020 (inclusive) and 1 January 2025 (exclusive)",
                        ),
                        QuestionResponse(answer=["2022", "04", "05"], check_your_answers_text="5 April 2022"),
                    ],
                    validation=E2EManagedExpression(
                        evaluatable_expression=BetweenDates(
                            subject_reference="q_00000000000000000000000000001234",
                            earliest_value=datetime.date(2020, 1, 1),
                            earliest_inclusive=True,
                            latest_value=datetime.date(2025, 1, 1),
                            latest_inclusive=False,
                        )
                    ),
                ),
                QuestionDict(
                    type=QuestionDataType.DATE,
                    text="Enter an approximate date",
                    display_text="Enter an approximate date",
                    hint=TextFieldWithData(
                        prefix="You entered an exact date of",
                        data_reference=DataReferenceConfig(
                            ExpressionContext.ContextSources.SECTION, question_text="Enter a date"
                        ),
                    ),
                    display_hint="You entered an exact date of Tuesday 5 April 2022",
                    answers=[
                        QuestionResponse(
                            ["2003", "2"],
                            "The answer must be between April 2020 (inclusive) and March 2022 (exclusive)",
                        ),
                        QuestionResponse(["2021", "04"], check_your_answers_text="April 2021"),
                    ],
                    options=QuestionPresentationOptions(approximate_date=True),
                    validation=E2EManagedExpression(
                        evaluatable_expression=BetweenDates(
                            subject_reference="q_00000000000000000000000000001234",
                            earliest_value=datetime.date(2020, 4, 1),
                            earliest_inclusive=True,
                            latest_value=datetime.date(2022, 3, 1),
                            latest_inclusive=False,
                        )
                    ),
                ),
                QuestionDict(
                    type=QuestionDataType.NUMBER,
                    text="Enter the total cost as a number",
                    display_text="Enter the total cost as a number",
                    answers=[
                        QuestionResponse("0", "The answer must be greater than 1"),
                        QuestionResponse("10000"),
                    ],
                    options=QuestionPresentationOptions(
                        prefix="£", width=NumberInputWidths.BILLIONS, approximate_date=True
                    ),
                    data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
                    validation=E2EManagedExpression(
                        evaluatable_expression=GreaterThan(
                            subject_reference="q_00000000000000000000000000001234",
                            minimum_value=1,
                            inclusive=False,
                        )
                    ),
                    condition=E2EManagedExpression(
                        evaluatable_expression=BetweenDates(
                            subject_reference="q_00000000000000000000000000001234",
                            earliest_value=datetime.date(2020, 4, 1),
                            earliest_inclusive=False,
                            latest_value=None,
                            latest_expression="",
                            latest_inclusive=False,
                        ),
                        conditional_on=DataReferenceConfig(
                            data_source=ExpressionContext.ContextSources.SECTION,
                            question_text="Enter an approximate date",
                        ),
                        context_source=DataReferenceConfig(
                            data_source=ExpressionContext.ContextSources.SECTION, question_text="Enter a date"
                        ),
                    ),
                ),
                QuestionDict(
                    type=QuestionDataType.NUMBER,
                    text="Enter the total weight as a number",
                    display_text="Enter the total weight as a number",
                    answers=[
                        QuestionResponse("10001", "The answer must be less than or equal to £10,000"),
                        QuestionResponse("100"),
                    ],
                    options=QuestionPresentationOptions(suffix="kg", width=NumberInputWidths.HUNDREDS),
                    data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
                    validation=E2EManagedExpression(
                        evaluatable_expression=LessThan(
                            subject_reference="q_00000000000000000000000000001234",
                            maximum_value=None,
                            maximum_expression="",
                            inclusive=True,
                        ),
                        context_source=DataReferenceConfig(
                            data_source=ExpressionContext.ContextSources.SECTION,
                            question_text="Enter the total cost as a number",
                        ),
                    ),  # question_id does not matter here
                    condition=E2EManagedExpression(
                        conditional_on=DataReferenceConfig(
                            data_source=ExpressionContext.ContextSources.SECTION,
                            question_text="Enter the total cost as a number",
                        ),
                        evaluatable_expression=GreaterThan(
                            subject_reference="q_00000000000000000000000000001234",
                            minimum_value=1,
                            inclusive=False,
                        ),
                    ),
                ),
                QuestionDict(
                    type=QuestionDataType.NUMBER,
                    text="Enter a number between 20 and 100",
                    display_text="Enter a number between 20 and 100",
                    answers=[
                        QuestionResponse("101", "The answer must be between 20 (inclusive) and 100 (exclusive)"),
                        QuestionResponse("20"),
                    ],
                    options=QuestionPresentationOptions(),
                    data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
                    validation=E2EManagedExpression(
                        evaluatable_expression=Between(
                            subject_reference="q_00000000000000000000000000001234",
                            maximum_value=100,
                            maximum_inclusive=False,
                            minimum_value=20,
                            minimum_inclusive=True,
                        )
                    ),  # question_id does not matter here
                    condition=E2EManagedExpression(
                        conditional_on=DataReferenceConfig(
                            data_source=ExpressionContext.ContextSources.SECTION,
                            question_text="Enter the total weight as a number",
                        ),
                        evaluatable_expression=LessThan(
                            subject_reference="q_00000000000000000000000000001234",
                            maximum_value=100,
                            inclusive=True,
                        ),
                    ),
                ),
                QuestionDict(
                    type=QuestionDataType.NUMBER,
                    text="Enter the percentage of employees involved in this project",
                    display_text="Enter the percentage of employees involved in this project",
                    answers=[
                        QuestionResponse("1,250.4", "The answer must be less than or equal to 100"),
                        QuestionResponse("50.423", "The answer cannot be more than 2 decimal places"),
                        QuestionResponse("35.67"),
                    ],
                    options=QuestionPresentationOptions(suffix="%", width=NumberInputWidths.BILLIONS),
                    data_options=QuestionDataOptions(number_type=NumberTypeEnum.DECIMAL, max_decimal_places=2),
                    validation=E2EManagedExpression(
                        evaluatable_expression=LessThan(
                            subject_reference="q_00000000000000000000000000001234",
                            maximum_value=100,
                            inclusive=True,
                        )
                    ),
                ),
                QuestionDict(
                    type=QuestionDataType.NUMBER,
                    text="Enter the number with 5 decimal places",
                    display_text="Enter the number with 5 decimal places",
                    answers=[
                        QuestionResponse(
                            "1.12346", "The answer must be between 0.22334 (exclusive) and 1.12345 (inclusive)"
                        ),
                        QuestionResponse("1.123456", "The answer cannot be more than 5 decimal places"),
                        QuestionResponse(
                            "0.22333", "The answer must be between 0.22334 (exclusive) and 1.12345 (inclusive)"
                        ),
                        QuestionResponse("0.45678"),
                    ],
                    options=QuestionPresentationOptions(),
                    data_options=QuestionDataOptions(number_type=NumberTypeEnum.DECIMAL, max_decimal_places=5),
                    validation=E2EManagedExpression(
                        evaluatable_expression=Between(
                            subject_reference="q_00000000000000000000000000001234",
                            maximum_value=Decimal("1.12345"),
                            maximum_inclusive=True,
                            minimum_value=Decimal("0.22334"),
                            minimum_inclusive=False,
                        )
                    ),
                ),
                QuestionDict(
                    type=QuestionDataType.NUMBER,
                    text="Enter a number that is greater than the weight plus the number from the previous section",
                    display_text="Enter a number that is greater than the weight plus the number from the previous "
                    "section",
                    answers=[
                        QuestionResponse(
                            "121",
                            "The answer must be greater than the weight plus the number from the previous section",
                        ),
                        QuestionResponse("250"),
                    ],
                    options=QuestionPresentationOptions(),
                    data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
                    validation=E2EManagedExpression(
                        evaluatable_expression=CustomExpression(
                            custom_expression="((ref1)) > ((ref2))",  # + ((ref3))",
                            custom_message="The answer must be greater than the weight plus the number from the "
                            "previous section",
                        ),
                        expression_references={
                            "ref1": DataReferenceConfig(data_source="THIS_QUESTION"),
                            "ref2": DataReferenceConfig(
                                data_source=ExpressionContext.ContextSources.SECTION,
                                question_text="Enter the total weight as a number",
                            ),
                            # TODO add a test for referencing previous section
                            # "ref3": DataReferenceConfig(
                            #     data_source=ExpressionContext.ContextSources.PREVIOUS_SECTION,
                            #     section_text="E2E first task - grouped questions",
                            #     question_text="What number do you want to see in another section?",
                            # ),
                        },
                    ),
                ),
                QuestionDict(
                    type=QuestionDataType.TEXT_MULTI_LINE,
                    text="Enter the reason why suffix-integer was greater than the between and prefix "
                    "integers added together",
                    display_text=(
                        "Enter the reason why suffix-integer was greater than the between and prefix integers added "
                        "together"
                    ),
                    answers=[
                        QuestionResponse("I have my reasons"),
                    ],
                    options=QuestionPresentationOptions(),
                    data_options=QuestionDataOptions(),
                    condition=E2EManagedExpression(
                        evaluatable_expression=CustomExpression(
                            custom_expression="((ref1)) > ((ref2)) + ((ref3))",
                            expression_name="Show if cost greater than weight plus number",
                        ),
                        expression_references={
                            "ref1": DataReferenceConfig(
                                data_source=ExpressionContext.ContextSources.SECTION,
                                question_text="Enter the total cost as a number",
                            ),
                            "ref2": DataReferenceConfig(
                                data_source=ExpressionContext.ContextSources.SECTION,
                                question_text="Enter the total weight as a number",
                            ),
                            "ref3": DataReferenceConfig(
                                data_source=ExpressionContext.ContextSources.SECTION,
                                question_text="Enter a number between 20 and 100",
                            ),
                        },
                    ),
                ),
                QuestionDict(
                    type=QuestionDataType.YES_NO,
                    text="Yes or no",
                    display_text="Yes or no",
                    answers=[
                        QuestionResponse("Yes"),
                    ],
                    condition=E2EManagedExpression(
                        conditional_on=DataReferenceConfig(
                            data_source=ExpressionContext.ContextSources.SECTION,
                            question_text="Enter a number between 20 and 100",
                        ),
                        evaluatable_expression=Between(
                            subject_reference="q_00000000000000000000000000001234",
                            maximum_value=40,
                            maximum_inclusive=True,
                            minimum_value=15,
                            minimum_inclusive=False,
                        ),
                    ),
                ),
                QuestionDict(
                    type=QuestionDataType.RADIOS,
                    text="Select an option",
                    display_text="Select an option",
                    choices=["option 1", "option 2", "option 3"],
                    answers=[
                        QuestionResponse("option 2"),
                    ],
                    condition=E2EManagedExpression(
                        conditional_on=DataReferenceConfig(
                            data_source=ExpressionContext.ContextSources.SECTION, question_text="Yes or no"
                        ),
                        evaluatable_expression=IsYes(subject_reference="q_00000000000000000000000000001234"),
                    ),
                ),
                QuestionDict(
                    type=QuestionDataType.RADIOS,
                    text="Select an option from the accessible autocomplete",
                    display_text="Select an option from the accessible autocomplete",
                    choices=[f"option {x}" for x in range(1, 30)],
                    answers=[
                        QuestionResponse("Other"),
                    ],
                    options=QuestionPresentationOptions(last_data_source_item_is_distinct_from_others=True),
                    condition=E2EManagedExpression(
                        conditional_on=DataReferenceConfig(
                            data_source=ExpressionContext.ContextSources.SECTION, question_text="Select an option"
                        ),
                        evaluatable_expression=AnyOf(
                            subject_reference="q_00000000000000000000000000001234",
                            items=[{"key": "option-2", "label": "option 2"}, {"key": "option-3", "label": "option 3"}],
                        ),
                    ),
                ),
                QuestionDict(
                    type=QuestionDataType.CHECKBOXES,
                    text="Select one or more options",
                    display_text="Select one or more options",
                    choices=["option 1", "option 2", "option 3", "option 4"],
                    answers=[
                        QuestionResponse(["option 2", "option 3"]),
                    ],
                    options=QuestionPresentationOptions(last_data_source_item_is_distinct_from_others=True),
                    condition=E2EManagedExpression(
                        conditional_on=DataReferenceConfig(
                            data_source=ExpressionContext.ContextSources.SECTION,
                            question_text="Select an option from the accessible autocomplete",
                        ),
                        evaluatable_expression=AnyOf(
                            subject_reference="q_00000000000000000000000000001234",
                            items=[{"key": "other", "label": "Other"}],
                        ),
                    ),
                ),
                QuestionDict(
                    type=QuestionDataType.EMAIL,
                    text="Enter an email address",
                    display_text="Enter an email address",
                    answers=[
                        QuestionResponse(
                            "not-an-email", "Enter an email address in the correct format, like name@example.com"
                        ),
                        QuestionResponse("name@example.com"),
                    ],
                    condition=E2EManagedExpression(
                        conditional_on=DataReferenceConfig(
                            data_source=ExpressionContext.ContextSources.SECTION,
                            question_text="Select one or more options",
                        ),
                        evaluatable_expression=Specifically(
                            subject_reference="q_00000000000000000000000000001234",
                            item={"key": "option-2", "label": "option 2"},
                        ),
                    ),
                ),
                QuestionDict(
                    type=QuestionDataType.TEXT_SINGLE_LINE,
                    text="Enter a postcode",
                    display_text="Enter a postcode",
                    answers=[
                        QuestionResponse("E2E question text single line", "The answer must be a UK postcode"),
                        QuestionResponse("SW1A 1AA"),
                    ],
                    validation=E2EManagedExpression(
                        evaluatable_expression=UKPostcode(
                            subject_reference="q_00000000000000000000000000001234",
                        )
                    ),  # question_id does not matter here
                    guidance=GuidanceText(
                        heading="This is a guidance page heading",
                        body_heading="Guidance subheading",
                        body_link_text="Design system link text",
                        body_link_url="https://design-system.service.gov.uk",
                        body_ul_items=["UL item one", "UL item two"],
                        body_ol_items=["OL item one", "OL item two"],
                    ),
                ),
                QuestionDict(
                    type=QuestionDataType.TEXT_MULTI_LINE,
                    text="Enter a few lines of text",
                    display_text="Enter a few lines of text",
                    answers=[
                        QuestionResponse("E2E question text multi line\nwith a second line that's over the word limit"),
                        QuestionResponse("E2E question text multi line\nwith a second line"),
                    ],
                    options=QuestionPresentationOptions(word_limit=10, rows=MultilineTextInputRows.LARGE),
                ),
                QuestionDict(
                    type=QuestionDataType.URL,
                    text="Enter a website address",
                    display_text="Enter a website address",
                    answers=[
                        QuestionResponse("not-a-url", "Enter a website address in the correct format, like www.gov.uk"),
                        QuestionResponse("https://gov.uk"),
                    ],
                ),
                QuestionDict(
                    type=QuestionDataType.FILE_UPLOAD,
                    text="Upload a supporting document",
                    display_text="Upload a supporting document",
                    answers=[
                        # ./tests/fixtures/e2e-test-file.txt
                        QuestionResponse("e2e-test-file.txt"),
                    ],
                ),
                QuestionDict(
                    type=QuestionDataType.TEXT_SINGLE_LINE,
                    text="This question should not be shown",
                    display_text="This question should not be shown",
                    answers=[QuestionResponse("This question shouldn't be shown")],
                    condition=E2EManagedExpression(
                        conditional_on=DataReferenceConfig(
                            data_source=ExpressionContext.ContextSources.SECTION, question_text="Yes or no"
                        ),
                        evaluatable_expression=IsNo(subject_reference="q_00000000000000000000000000001234"),
                    ),
                ),
                QuestionDict(
                    # TODO put this in its own test
                    type=QuestionDataType.NUMBER,
                    text="Prove that referencing data from another section works",
                    display_text="Prove that referencing data from another section works",
                    hint=TextFieldWithData(
                        prefix="You entered this in the last section: ",
                        data_reference=DataReferenceConfig(
                            data_source=ExpressionContext.ContextSources.PREVIOUS_SECTION,
                            section_text="E2E first task - grouped questions",
                            question_text="What number do you want to see in another section?",
                        ),
                    ),
                    display_hint="You entered this in the last section: 100",
                    options=QuestionPresentationOptions(),
                    data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
                    answers=[
                        QuestionResponse("500", "The answer must be less than 100"),
                        QuestionResponse("50"),
                    ],
                    validation=E2EManagedExpression(
                        evaluatable_expression=LessThan(
                            subject_reference="q_00000000000000000000000000001234",
                            maximum_value=None,
                            maximum_expression="",
                            inclusive=False,
                        ),
                        context_source=DataReferenceConfig(
                            data_source=ExpressionContext.ContextSources.PREVIOUS_SECTION,
                            section_text="E2E first task - grouped questions",
                            question_text="What number do you want to see in another section?",
                        ),
                    ),
                ),
            ],
        ),
    ],
}


# Module-level storage for shared test data across dependent tests
_shared_setup_data: dict | None = None


def test_setup_grant_and_collection(
    page: Page,
    domain: str,
    e2e_test_secrets: EndToEndTestSecrets,
    authenticated_browser_sso: E2ETestUser,
    email,
    seeded_e2e_grant,
) -> None:

    # Sense check that the test includes all question types
    assert (
        len(QuestionDataType) == 10
        and len(report_with_all_question_types["sections"][0]["components"]) == 20
        and len(ManagedExpressionsEnum) == 11
        and len(NumberTypeEnum) == 2
    ), (
        "If you have added a new question/number type or managed expression, update this test to include the "
        "new question/number type or managed expression in `questions_to_test`."
    )
    all_grants_page = AllGrantsPage(page, domain)
    all_grants_page.navigate()
    grant_dashboard_page = all_grants_page.click_grant(seeded_e2e_grant["name"])

    # Go to Reports tab
    grant_reports_page = grant_dashboard_page.click_reports(seeded_e2e_grant["name"])

    # Add a new report
    add_report_page = grant_reports_page.click_add_report()
    new_report_name = report_with_all_question_types["name"]
    add_report_page.fill_in_report_name(new_report_name)
    grant_reports_page = add_report_page.click_submit(seeded_e2e_grant["name"])
    grant_reports_page.check_report_exists(new_report_name)
    collection_id = None

    for section in report_with_all_question_types["sections"]:
        # If it's the first section
        if not collection_id:
            add_section_page = grant_reports_page.click_add_section(
                report_name=new_report_name, grant_name=seeded_e2e_grant["name"]
            )
            # Extract collection_id from URL (e.g., /grant/<uuid>/reports/<uuid>/sections)
            collection_id = extract_uuid_from_url(page.url, r"/report/(?P<uuid>[a-f0-9-]+)")
            report_with_all_question_types["id"] = uuid.UUID(collection_id)
        else:
            report_sections_page = navigate_to_report_sections_page(
                page, domain, seeded_e2e_grant["name"], new_report_name
            )
            add_section_page = report_sections_page.click_add_section()

        add_section_page.fill_in_section_name(section["name"])
        report_sections_page = add_section_page.click_add_section()
        report_sections_page.check_section_exists(section["name"])

        manage_section_page = report_sections_page.click_manage_section(section_name=section["name"])
        for question_to_test in section["components"]:
            create_question_or_group(question_to_test, manage_section_page)

    # Add grant team member
    grant_team_page = grant_reports_page.click_nav_grant_team()
    add_grant_team_member_page = grant_team_page.click_add_grant_team_member()
    grant_team_email = e2e_user_configs[DeliverGrantFundingUserType.GRANT_TEAM_MEMBER].email
    add_grant_team_member_page.fill_in_user_email(grant_team_email)
    grant_team_page = add_grant_team_member_page.click_continue()

    # Switch to grant team member (claim invitation/userrole), then switch back to platform admin
    switch_user(page, domain, e2e_test_secrets, DeliverGrantFundingUserType.GRANT_TEAM_MEMBER, grant_team_email)
    switch_user(page, domain, e2e_test_secrets, DeliverGrantFundingUserType.PLATFORM_ADMIN, email)

    reporting_lifecycle_tasklist_page = AdminReportingLifecycleTasklistPage(
        page, domain, seeded_e2e_grant["id"], collection_id
    )
    reporting_lifecycle_tasklist_page.navigate()
    reporting_lifecycle_tasklist_page.click_task("Set up organisations")

    # TODO seed our e2e test organisation; note a shadow test org will be created automatically

    tsv_data = (
        "organisation-id\torganisation-name\ttype\tactive-date\tretirement-date\n"
        f"MHCLG-TEST-ORG\t{TEST_DATA_TO_BE_SEEDED['grant_recipient_org']}\tCentral Government\t\t\n"
    )
    set_up_orgs_page = SetUpOrganisationsPage(page, domain, seeded_e2e_grant["id"], collection_id)
    set_up_orgs_page.fill_organisations_tsv_data(tsv_data)
    set_up_orgs_page.click_set_up_organisations()

    reporting_lifecycle_tasklist_page.click_task("Set up grant recipients")
    set_up_grant_recipients_page = SetUpGrantRecipientsPage(page, domain, seeded_e2e_grant["id"], collection_id)
    set_up_grant_recipients_page.select_organisation(TEST_DATA_TO_BE_SEEDED["grant_recipient_org"])
    set_up_grant_recipients_page.click_set_up_grant_recipients()

    tsv_data = (
        f"organisation-name\tfull-name\temail-address\n{TEST_DATA_TO_BE_SEEDED['grant_recipient_org']}"
        f"\t{TEST_DATA_TO_BE_SEEDED['grant_recipient_user_name']}\t"
        f"{TEST_DATA_TO_BE_SEEDED['grant_recipient_user_email']}\n"
    )
    reporting_lifecycle_tasklist_page.click_task("Set up grant recipient data providers")
    setup_data_providers_page = SetUpDataProvidersPage(page, domain, seeded_e2e_grant["id"], collection_id)
    setup_data_providers_page.fill_users_tsv_data(tsv_data)
    setup_data_providers_page.click_set_up_users()

    reporting_lifecycle_tasklist_page.click_task("Override certifiers for this grant")
    override_certifiers_page = OverrideGrantRecipientCertifiersPage(page, domain, seeded_e2e_grant["id"], collection_id)
    override_certifiers_page.select_organisation(TEST_DATA_TO_BE_SEEDED["grant_recipient_org"])
    override_certifiers_page.complete_user_details(
        TEST_DATA_TO_BE_SEEDED["grant_recipient_user_name"], TEST_DATA_TO_BE_SEEDED["grant_recipient_user_email"]
    )
    override_certifiers_page.click_add_certifier()

    reporting_lifecycle_tasklist_page.navigate()
    reporting_lifecycle_tasklist_page.click_task("Set reporting dates")
    set_reporting_dates_page = SetReportingDatesPage(page, domain, seeded_e2e_grant["id"], collection_id)
    set_reporting_dates_page.set_dates_for_open_report()
    set_reporting_dates_page.click_save_dates(report_name=new_report_name)

    reporting_lifecycle_tasklist_page.click_task("Mark as onboarding with Funding Service")
    mark_as_onboarding_page = MarkAsOnboardingWithFundingServicePage(
        page, domain, seeded_e2e_grant["id"], collection_id
    )
    mark_as_onboarding_page.click_mark_as_onboarding()

    reporting_lifecycle_tasklist_page.click_task("Set privacy policy")
    set_privacy_policy_page = SetPrivacyPolicyPage(page, domain, seeded_e2e_grant["id"], collection_id)
    set_privacy_policy_page.fill_privacy_policy_markdown("https://www.gov.uk/help/privacy-notice")
    set_privacy_policy_page.click_save_privacy_policy()

    # Do this the admin way so we don't have to create grant team users (that's why the option is
    # greyed out in the tasklist at this point)
    grant_settings_page = PlatformAdminGrantSettingsPage(page, domain, seeded_e2e_grant["id"])
    grant_settings_page.navigate()
    grant_settings_page.select_grant_status("LIVE")
    grant_settings_page.click_save()

    report_settings_page = PlatformAdminReportSettingsPage(page, domain, collection_id)
    report_settings_page.navigate()
    report_settings_page.select_collection_status("OPEN")
    report_settings_page.click_save()

    # The report is now open and ready for submissions
    # TODO go on to login with the fsd-post-award user via magic link and complete the report


def test_preview_collection(
    page: Page,
    domain: str,
    e2e_test_secrets: EndToEndTestSecrets,
    authenticated_browser_sso: E2ETestUser,
    email,
    seeded_e2e_grant,
) -> None:
    """Grant team member previews and fills the collection."""
    assert report_with_all_question_types["id"] is not None, "Setup test must run first"

    # Switch to grant team member
    switch_user(
        page,
        domain,
        e2e_test_secrets,
        DeliverGrantFundingUserType.GRANT_TEAM_MEMBER,
        TEST_DATA_TO_BE_SEEDED["grant_team_email"],
    )

    # Preview the report
    all_grants_page = AllGrantsPage(page, domain)
    all_grants_page.navigate()

    # This page can auto-redirect to the grant page; if it doesn't we should click the grant name.
    if all_grants_page.title.is_visible():
        all_grants_page.click_grant(seeded_e2e_grant["name"])

    grant_details_page = GrantDetailsPage(page, domain, seeded_e2e_grant["name"])
    grant_reports_page = grant_details_page.click_reports(seeded_e2e_grant["name"])
    report_sections_page = grant_reports_page.click_manage_sections(
        grant_name=seeded_e2e_grant["name"], report_name=report_with_all_question_types["name"]
    )
    tasklist_page = report_sections_page.click_preview_report()

    # Check the tasklist has loaded
    expect(
        tasklist_page.submission_status_box.filter(has=tasklist_page.page.get_by_text("Not started"))
    ).to_be_visible()
    expect(tasklist_page.submit_button).to_be_disabled()
    expect(
        tasklist_page.page.get_by_role("link", name=report_with_all_question_types["sections"][0]["name"])
    ).to_be_visible()

    # Complete the first task with question groups
    complete_task(
        tasklist_page,
        report_with_all_question_types["sections"][0]["name"],
        seeded_e2e_grant["name"],
        report_with_all_question_types["sections"][0]["components"],
    )

    # Check your answers page
    task_check_your_answers(
        tasklist_page,
        seeded_e2e_grant["name"],
        report_with_all_question_types["name"],
        report_with_all_question_types["sections"][0]["components"],
    )

    # Submit the report
    expect(
        tasklist_page.submission_status_box.filter(has=tasklist_page.page.get_by_text("Ready to submit"))
    ).to_be_visible()
    expect(tasklist_page.submit_button).to_be_enabled()

    tasklist_page.click_submit_for_preview()


def test_deliver_test_grant_recipient_journey(
    page: Page,
    domain: str,
    e2e_test_secrets: EndToEndTestSecrets,
    authenticated_browser_sso: E2ETestUser,
    email,
    seeded_e2e_grant,
) -> None:
    """Grant team member triggers test submission via test organisation."""
    assert report_with_all_question_types["id"] is not None, "Setup test must run first"

    # Switch to grant team member
    switch_user(
        page,
        domain,
        e2e_test_secrets,
        DeliverGrantFundingUserType.GRANT_TEAM_MEMBER,
        TEST_DATA_TO_BE_SEEDED["grant_team_email"],
    )

    test_journey_page = DeliverTestGrantRecipientJourneyPage(
        page,
        domain,
        seeded_e2e_grant["id"],
        report_with_all_question_types["id"],
        report_with_all_question_types["name"],
    )
    test_journey_page.navigate()
    test_journey_page.select_test_organisation(TEST_DATA_TO_BE_SEEDED["test_org_name"])
    test_journey_page.click_start_test_journey()

    access_home = AccessHomePage(page, domain)
    access_home.navigate()
    access_home.click_accept_cookies()
    access_grant = access_home.select_grant(TEST_DATA_TO_BE_SEEDED["test_org_name"], seeded_e2e_grant["name"])
    access_grant.click_collection(report_with_all_question_types["name"])

    # We should now be on the tasklist page for the submission
    tasklist_page = RunnerTasklistPage(page, domain, seeded_e2e_grant["name"], report_with_all_question_types["name"])

    # Check the tasklist has loaded
    expect(
        tasklist_page.submission_status_box.filter(has=tasklist_page.page.get_by_text("Not started"))
    ).to_be_visible()
    expect(
        tasklist_page.page.get_by_role("link", name=report_with_all_question_types["sections"][0]["name"])
    ).to_be_visible()

    # Complete the first task with question groups
    complete_task(
        tasklist_page,
        report_with_all_question_types["sections"][0]["name"],
        seeded_e2e_grant["name"],
        report_with_all_question_types["sections"][0]["components"],
    )

    # Check your answers page
    task_check_your_answers(
        tasklist_page,
        seeded_e2e_grant["name"],
        report_with_all_question_types["name"],
        report_with_all_question_types["sections"][0]["components"],
    )

    # Submit the report
    expect(
        tasklist_page.submission_status_box.filter(has=tasklist_page.page.get_by_text("Ready to submit"))
    ).to_be_visible()
    expect(tasklist_page.submit_button).to_be_enabled()

    confirmation_page = tasklist_page.click_submit_for_certify()
    confirmation_page.click_return_to_reports()

    # Certify the report
    report_list_page = AccessGrantPage(page, domain)
    report_list_page.click_collection(report_with_all_question_types["name"])

    locked_report_page = ViewLockedReportPage(
        page, domain, seeded_e2e_grant["name"], report_with_all_question_types["name"]
    )
    expect(locked_report_page.heading).to_be_visible()

    confirm_sign_off_page = locked_report_page.click_sign_off_and_submit()
    sign_off_confirmation_page = confirm_sign_off_page.click_sign_off_and_submit()
    expect(
        page.get_by_text(
            f"Your {report_with_all_question_types['name']} report for {seeded_e2e_grant['name']} "
            "has been submitted to the"
        )
    ).to_be_visible()
    sign_off_confirmation_page.click_return_to_reports()

    # Reopen the submission
    grant_reports_page = GrantReportsPage(page, domain, seeded_e2e_grant["name"])
    grant_reports_page.navigate(seeded_e2e_grant["id"])
    submissions_list_page = grant_reports_page.click_view_submissions(report_with_all_question_types["name"])
    view_submission_page = submissions_list_page.click_on_submission(TEST_DATA_TO_BE_SEEDED["test_org_name"])
    reopen_page = view_submission_page.click_reopen_submission()
    reopen_page.fill_reopen_reason("Reopening for e2e tests")
    view_submission_page = reopen_page.click_reopen_submission()
    expect(page.get_by_text("Submission reopened and email sent to")).to_be_visible()

    view_submission_page.click_reset_submission()


def test_zzz_cleanup_grant(
    page: Page, domain: str, e2e_test_secrets: EndToEndTestSecrets, authenticated_browser_sso: E2ETestUser, email
) -> None:
    """Cleanup: delete the grant via admin panel. Named zzz_ to run last alphabetically."""
    if _shared_setup_data is None:
        pytest.skip("No setup data to clean up")

    # Switch to platform admin
    switch_user(page, domain, e2e_test_secrets, DeliverGrantFundingUserType.PLATFORM_ADMIN, email)

    # Tidy up by deleting the grant via admin panel, which will cascade to all related entities
    delete_grant_recipient_through_admin(
        page, domain, _shared_setup_data["grant_name_uuid"], expected_grant_recipients_matching_search=2
    )
    delete_grant_through_admin(page, domain, _shared_setup_data["grant_name_uuid"])
