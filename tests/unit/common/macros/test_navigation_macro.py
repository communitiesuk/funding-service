import re

import pytest
from bs4 import BeautifulSoup
from flask import render_template_string


class TestAccessGrantFundingServiceNavigationMacro:
    @pytest.mark.parametrize(
        "grant_recipient_org_names, should_show_org_nav",
        [
            ([], False),
            (["First organisation"], False),
            (["First organisation", "Second organisation"], True),
        ],
    )
    def test_shows_org_nav_and_change_org(self, factories, grant_recipient_org_names, should_show_org_nav):
        current_user = factories.user.build()

        for org_name in grant_recipient_org_names:
            organisation = factories.organisation.build(name=org_name)
            current_user._grant_recipients.extend(factories.grant_recipient.build_batch(3, organisation=organisation))
        current_organisation = (
            current_user.get_grant_recipients()[0].organisation if current_user.get_grant_recipients() else None
        )

        template_content = """
        {% from "common/macros/navigation.html" import accessGrantFundingServiceNavigation %}
        {{ accessGrantFundingServiceNavigation(current_user, organisation=current_organisation) }}
        """
        macro = BeautifulSoup(
            render_template_string(
                template_content, current_user=current_user, current_organisation=current_organisation
            ),
            "html.parser",
        )

        if not should_show_org_nav:
            assert macro.get_text(strip=True) == ""
        else:
            assert (
                macro.find(
                    "a", class_="govuk-service-navigation__link", string=re.compile(r"^\s*Change organisation\s*$")
                )
                is not None
            )
            assert (
                macro.find("span", class_="govuk-service-navigation__service-name").get_text(strip=True)
                == current_organisation.name
            )
            assert "app-service-nav-org" not in macro.find("section", {"id": "org-nav"})["class"]

    @pytest.mark.parametrize(
        "grant_recipient_names, should_show_grant_nav, should_show_change_grant",
        [
            ([], False, False),
            (["First grant"], True, False),
            (["First grant", "Second grant"], True, True),
        ],
    )
    def test_shows_grant_nav_and_change_grant(
        self, factories, grant_recipient_names, should_show_grant_nav, should_show_change_grant
    ):
        current_user = factories.user.build()

        organisation = factories.organisation.build()
        for grant_name in grant_recipient_names:
            current_user._grant_recipients.append(
                factories.grant_recipient.build(organisation=organisation, grant__name=grant_name)
            )
        current_grant_recipient = (
            current_user.get_grant_recipients()[0] if current_user.get_grant_recipients() else None
        )

        template_content = """
        {% from "common/macros/navigation.html" import accessGrantFundingServiceNavigation %}
        {{ accessGrantFundingServiceNavigation(current_user, grant_recipient=current_grant_recipient) }}
        """
        macro = BeautifulSoup(
            render_template_string(
                template_content, current_user=current_user, current_grant_recipient=current_grant_recipient
            ),
            "html.parser",
        )

        if not should_show_grant_nav:
            assert macro.get_text(strip=True) == ""
        else:
            assert macro.find("section", {"id": "grant-nav"}) is not None
            assert (
                macro.find("span", class_="govuk-service-navigation__service-name").get_text(strip=True)
                == current_grant_recipient.grant.name
            )

            change_grant_link = macro.find(
                "a", class_="govuk-service-navigation__link", string=re.compile(r"^\s*Change grant\s*$")
            )
            if not should_show_change_grant:
                assert change_grant_link is None
            else:
                assert (
                    "app-service-navigation__wrapper-sectional"
                    in macro.find("nav", {"class": "govuk-service-navigation__wrapper"})["class"]
                )
                assert change_grant_link is not None

    def test_includes_provided_navigation_alongside_change_links(self, factories):
        current_user = factories.user.build()
        organisation = factories.organisation.build()
        current_user._grant_recipients.append(
            factories.grant_recipient.build(organisation=organisation, grant__name="Test Grant")
        )
        current_user._grant_recipients.append(
            factories.grant_recipient.build(organisation=organisation, grant__name="Another Grant")
        )
        current_grant_recipient = current_user.get_grant_recipients()[0]

        template_content = """
        {% from "common/macros/navigation.html" import accessGrantFundingServiceNavigation %}
        {{ accessGrantFundingServiceNavigation(
            current_user,
            nav_items=[{"text": "Link one", "href": "#"}, {"text": "Link two", "href": "#"}],
            grant_recipient=current_grant_recipient
        ) }}
        """
        macro = BeautifulSoup(
            render_template_string(
                template_content, current_user=current_user, current_grant_recipient=current_grant_recipient
            ),
            "html.parser",
        )

        nav_items = macro.find_all(class_="govuk-service-navigation__item")
        links = [item.find("a", class_="govuk-service-navigation__link") for item in nav_items]
        assert [link.get_text(strip=True) for link in links if link] == ["Link one", "Link two", "Change grant"]

    def test_shows_both_navs_selects_the_correct_grant_recipient_org_if_not_provided(self, factories):
        current_user = factories.user.build()
        first_organisation = factories.organisation.build(name="First organisation")
        second_organisation = factories.organisation.build(name="Second organisation")

        first_grant_recipient = factories.grant_recipient.build(
            organisation=first_organisation, grant__name="First Grant"
        )
        second_grant_recipient = factories.grant_recipient.build(
            organisation=second_organisation, grant__name="Second Grant"
        )
        third_grant_recipient = factories.grant_recipient.build(
            organisation=second_organisation, grant__name="Third Grant"
        )
        current_user._grant_recipients.extend([first_grant_recipient, second_grant_recipient, third_grant_recipient])
        current_grant_recipient = second_grant_recipient

        template_content = """
        {% from "common/macros/navigation.html" import accessGrantFundingServiceNavigation %}
        {{ accessGrantFundingServiceNavigation(
            current_user,
            grant_recipient=current_grant_recipient
        ) }}
        """
        macro = BeautifulSoup(
            render_template_string(
                template_content, current_user=current_user, current_grant_recipient=current_grant_recipient
            ),
            "html.parser",
        )

        assert [
            span.get_text(strip=True)
            for span in macro.find_all("span", class_="govuk-service-navigation__service-name")
        ] == ["Second organisation", "Second Grant"]

        grant_nav = macro.find("section", {"id": "grant-nav"})
        assert (
            "app-service-navigation__wrapper-sectional-org-hidden"
            in grant_nav.find("nav", {"class": "govuk-service-navigation__wrapper"})["class"]
        )

        assert "govuk-service-navigation" in macro.find("div", {"id": "org-nav"})["class"]
