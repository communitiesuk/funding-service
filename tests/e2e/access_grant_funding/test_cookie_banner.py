from playwright.sync_api import Page

from tests.e2e.access_grant_funding.pages import RequestALinkToSignInPage


def test_cookie_banner_accepted(page: Page, domain: str):
    fetched_google_tag_manager_requests = []
    page.on(
        "request",
        lambda request: fetched_google_tag_manager_requests.append(request.url)
        if "https://www.googletagmanager.com/gtm.js" in request.url
        else None,
    )

    request_a_link_page = RequestALinkToSignInPage(page, domain)
    request_a_link_page.navigate()
    assert page.locator("#cookie_choice_msg").is_visible()

    assert len(fetched_google_tag_manager_requests) == 0, (
        "Should not have fetched google tag manager before cookies are accepted"
    )

    with page.expect_request("https://www.googletagmanager.com/gtm.js?id=**"):
        request_a_link_page.click_accept_cookies()

    assert len(fetched_google_tag_manager_requests) == 1, (
        "Should have fetched google tag manager when cookies are accepted"
    )

    assert not page.locator("#cookie_choice_msg").is_visible()
    assert page.locator("#cookies_accepted_msg").is_visible()

    request_a_link_page.click_hide_cookies()

    assert not page.locator("#cookie_choice_msg").is_visible()
    assert not page.locator("#cookies_accepted_msg").is_visible()

    # reload the page and assert the choice is persisted
    request_a_link_page.navigate()
    assert not page.locator("#cookie_choice_msg").is_visible()
    assert not page.locator("#cookie_banner").is_visible()

    assert len(fetched_google_tag_manager_requests) == 2, (
        "Should have fetched google tag manager for a page load with accepted cookies"
    )


def test_cookie_banner_declined(page: Page, domain: str):
    fetched_google_tag_manager_requests = []
    page.on(
        "request",
        lambda request: fetched_google_tag_manager_requests.append(request.url)
        if "https://www.googletagmanager.com/gtm.js" in request.url
        else None,
    )

    request_a_link_page = RequestALinkToSignInPage(page, domain)
    request_a_link_page.navigate()
    assert page.locator("#cookie_choice_msg").is_visible()

    request_a_link_page.click_reject_cookies()

    assert page.locator("#cookies_rejected_msg").is_visible()
    assert not page.locator("#cookie_choice_msg").is_visible()

    request_a_link_page.click_hide_cookies()
    assert not page.locator("#cookies_rejected_msg").is_visible()

    # reload the page and assert the choice is persisted
    request_a_link_page.navigate()
    assert not page.locator("#cookie_choice_msg").is_visible()
    assert not page.locator("#cookie_banner").is_visible()

    assert len(fetched_google_tag_manager_requests) == 0, (
        "Google tag manager should never be fetched before cookies consent is explicit or rejected"
    )
