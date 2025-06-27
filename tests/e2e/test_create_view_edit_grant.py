import uuid

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.config import EndToEndTestSecrets
from tests.e2e.dataclasses import E2ETestUser
from tests.e2e.pages import AllGrantsPage


@pytest.mark.skip_in_environments(["prod"])
def test_create_view_edit_grant_success(
    page: Page, domain: str, e2e_test_secrets: EndToEndTestSecrets, authenticated_browser_sso: E2ETestUser
):
    try:
        all_grants_page = AllGrantsPage(page, domain)
        all_grants_page.navigate()

        # Set up new grant
        grant_intro_page = all_grants_page.click_set_up_a_grant()
        grant_ggis_page = grant_intro_page.click_continue()
        grant_ggis_page.select_yes()
        ggis_ref = f"GGIS-{uuid.uuid4()}"
        grant_ggis_page.fill_ggis_number(ggis_ref)
        grant_name_page = grant_ggis_page.click_save_and_continue()
        new_grant_name = f"E2E {uuid.uuid4()}"
        grant_name_page.fill_name(new_grant_name)
        grant_description_page = grant_name_page.click_save_and_continue()
        new_grant_description = f"Description for {new_grant_name}"
        grant_description_page.fill_description(new_grant_description)
        grant_contact_page = grant_description_page.click_save_and_continue()
        contact_name = "Test contact name"
        contact_email = "test@contact.com"
        grant_contact_page.fill_contact_name(contact_name)
        grant_contact_page.fill_contact_email(contact_email)
        grant_check_your_answers_page = grant_contact_page.click_save_and_continue()
        grant_dashboard_page = grant_check_your_answers_page.click_add_grant()

        # On grant dashboard
        grant_dashboard_page.check_grant_name(new_grant_name)
        grant_details_page = grant_dashboard_page.click_settings(new_grant_name)

        # Change grant name
        change_grant_name_page = grant_details_page.click_change_grant_name(new_grant_name)
        edited_grant_name = f"{new_grant_name} - edited"
        change_grant_name_page.fill_in_grant_name(edited_grant_name)
        grant_details_page = change_grant_name_page.click_submit(edited_grant_name)
        expect(grant_details_page.page.get_by_text(f"Name {edited_grant_name}")).to_be_visible()

        # Change GGIS reference
        change_ggis_page = grant_details_page.click_change_grant_ggis(existing_ggis_ref=ggis_ref)
        expect(change_ggis_page.ggis_textbox).to_have_value(ggis_ref)
        new_ggis_ref = f"edit-{uuid.uuid4()}"
        change_ggis_page.fill_ggis_number(new_ggis_ref)
        grant_details_page = change_ggis_page.click_submit(grant_name=edited_grant_name)
        expect(grant_details_page.page.get_by_text(new_ggis_ref)).to_be_visible()

        # Change grant description
        change_description_page = grant_details_page.click_change_grant_description(new_grant_description)
        new_description = f"New grant description {uuid.uuid4()}"
        change_description_page.fill_in_grant_description(new_description)
        grant_details_page = change_description_page.click_submit(edited_grant_name)
        expect(grant_details_page.page.get_by_text(f"Main purpose {new_description}")).to_be_visible()

        # Change main contact
        change_contact_page = grant_details_page.click_change_grant_contact_details(
            existing_contact_name=contact_name, existing_contact_email=contact_email
        )
        new_contact_name = f"New contact {uuid.uuid4()}"
        change_contact_page.fill_contact_name(new_contact_name)
        new_contact_email = f"contact-{uuid.uuid4()}@example.com"
        change_contact_page.fill_contact_email(new_contact_email)
        grant_details_page = change_contact_page.click_submit(edited_grant_name)
        expect(
            grant_details_page.page.get_by_text(f"Main contact {new_contact_name}{new_contact_email}")
        ).to_be_visible()

        # Go back to Grants list and check new name appears/old name doesn't appear
        all_grants_page = grant_details_page.click_grants()
        all_grants_page.check_grant_exists(edited_grant_name)
        all_grants_page.check_grant_doesnt_exist(new_grant_name)
    finally:
        # Tidy up by deleting the grant, which will cascade to all related entities
        grant_dashboard_page = all_grants_page.click_grant(edited_grant_name)
        developers_page = grant_dashboard_page.click_developers(edited_grant_name)
        developers_page.delete_grant()
