import uuid

import pytest
from flask import Flask, session, url_for

from app.access_grant_funding.session_models import (
    CompleteCreateOrganisationSession,
    CreateOrganisationPage,
    CreateOrganisationSession,
    NamedCreateOrganisationSession,
    OrganisationIdentification,
    SignUpOrganisationType,
    start_public_sign_up,
)
from app.constants import CHECK_YOUR_ANSWERS, SESSION_EMITTED_PUBLIC_SIGN_UP_METRICS


def _session(collection_id, *, needs_user_name=False, can_share_email_domain=True, **answers):
    return CreateOrganisationSession(
        collection_id=collection_id,
        needs_user_name=needs_user_name,
        can_share_email_domain=can_share_email_domain,
        **answers,
    )


class TestCreateOrganisationSession:
    def test_start_records_the_steps_this_user_will_be_asked(self, factories):
        collection_id = uuid.uuid4()

        session = CreateOrganisationSession.start(
            collection_id=collection_id,
            user=factories.user.build(email="someone@no-org.com", name=None),
            companies_house_lookup=True,
        )

        assert session.collection_id == collection_id
        assert session.needs_user_name is True
        assert session.can_share_email_domain is True
        assert session.companies_house_lookup is True

    def test_start_skips_the_steps_that_do_not_apply_to_this_user(self, factories):
        session = CreateOrganisationSession.start(
            collection_id=uuid.uuid4(),
            user=factories.user.build(email="someone@gmail.com", name="Test applicant"),
            companies_house_lookup=False,
        )

        assert session.needs_user_name is False
        assert session.can_share_email_domain is False
        assert session.companies_house_lookup is False

    def test_answering_the_name_generates_the_organisation_identifier(self):
        session = _session(uuid.uuid4(), organisation_type=SignUpOrganisationType.OTHER)

        session.answer_name("Acme Ltd")

        assert session.name == "Acme Ltd"
        assert session.external_id

    def test_answering_a_company_from_the_register_takes_its_number_as_the_identifier(self):
        session = _session(
            uuid.uuid4(),
            organisation_type=SignUpOrganisationType.COMPANY,
            identified_by=OrganisationIdentification.COMPANIES_HOUSE,
        )

        session.answer_company("TEST COMPANY LIMITED", "00000001")

        assert session.name == "TEST COMPANY LIMITED"
        assert session.external_id == "00000001"

    def test_falling_back_to_manual_entry_names_the_company_by_hand_for_the_rest_of_the_sign_up(self):
        session = _session(
            uuid.uuid4(),
            organisation_type=SignUpOrganisationType.COMPANY,
            identified_by=OrganisationIdentification.COMPANIES_HOUSE,
            companies_house_lookup=True,
        )

        session.fall_back_to_manual_entry()

        assert session.identified_by is OrganisationIdentification.MANUAL
        assert session.name_page is CreateOrganisationPage.NAME

        session.answer_organisation_type(SignUpOrganisationType.COMPANY)

        assert session.identified_by is OrganisationIdentification.MANUAL

    def test_falling_back_to_manual_entry_is_kept_in_the_session(self):
        collection_id = uuid.uuid4()
        session = _session(collection_id, organisation_type=SignUpOrganisationType.COMPANY)
        session.fall_back_to_manual_entry()

        restored = CreateOrganisationSession.from_session(
            collection_id=collection_id, session_data=session.to_session_dict()
        )

        assert restored is not None
        assert restored.companies_house_unavailable is True

    def test_to_session_dict_round_trips_through_json(self):
        collection_id = uuid.uuid4()
        session = _session(
            collection_id,
            organisation_type=SignUpOrganisationType.COMPANY,
            name="Acme Ltd",
            external_id="000123456",
            allow_team_members=True,
        )

        session_dict = session.to_session_dict()

        assert session_dict["collection_id"] == str(collection_id)
        assert session_dict["organisation_type"] == "COMPANY"
        assert session_dict["allow_team_members"] is True

        restored = CreateOrganisationSession.from_session(collection_id=collection_id, session_data=session_dict)
        assert restored == session
        assert restored.collection_id == collection_id
        assert restored.organisation_type is SignUpOrganisationType.COMPANY
        assert restored.allow_team_members is True

    def test_to_session_dict_excludes_none(self):
        session_dict = _session(uuid.uuid4()).to_session_dict()

        assert "organisation_type" not in session_dict
        assert "allow_team_members" not in session_dict
        assert "name" not in session_dict
        assert "external_id" not in session_dict

    def test_to_session_dict_keeps_allow_team_members_when_false(self):
        collection_id = uuid.uuid4()
        session_dict = _session(collection_id, allow_team_members=False).to_session_dict()

        assert session_dict["allow_team_members"] is False
        restored = CreateOrganisationSession.from_session(collection_id=collection_id, session_data=session_dict)
        assert restored.allow_team_members is False

    def test_from_session_loads_a_session_started_before_the_lookup_flag_existed(self):
        collection_id = uuid.uuid4()
        session_dict = _session(collection_id).to_session_dict()
        del session_dict["companies_house_lookup"]

        restored = CreateOrganisationSession.from_session(collection_id=collection_id, session_data=session_dict)

        assert restored is not None
        assert restored.companies_house_lookup is False

    def test_from_session_requires_matching_collection_id(self):
        session = _session(
            uuid.uuid4(),
            organisation_type=SignUpOrganisationType.COMPANY,
            name="Acme Ltd",
            external_id="000123456",
        )
        assert (
            CreateOrganisationSession.from_session(collection_id=uuid.uuid4(), session_data=session.to_session_dict())
            is None
        )

    @pytest.mark.parametrize("unanswered", ["needs_user_name", "can_share_email_domain"])
    def test_from_session_needs_the_steps_this_user_is_asked_to_have_been_settled(self, unanswered):
        collection_id = uuid.uuid4()
        session_dict = _session(collection_id).to_session_dict()
        del session_dict[unanswered]

        assert CreateOrganisationSession.from_session(collection_id=collection_id, session_data=session_dict) is None


class TestCreateOrganisationNavigation:
    def _named_session(self, **overrides):
        answers = {
            "organisation_type": SignUpOrganisationType.OTHER,
            "name": "Acme Ltd",
            "external_id": "000123456",
        } | overrides
        return _session(uuid.uuid4(), **answers)

    def test_the_pages_cover_every_step_this_user_is_asked(self):
        session = _session(uuid.uuid4(), needs_user_name=True, can_share_email_domain=True)

        assert session.pages == [
            CreateOrganisationPage.TYPE,
            CreateOrganisationPage.NAME,
            CreateOrganisationPage.TEAM_MEMBERS,
            CreateOrganisationPage.USER_NAME,
            CreateOrganisationPage.CHECK_YOUR_ANSWERS,
        ]

    def test_the_pages_leave_out_the_steps_that_do_not_apply(self):
        session = _session(uuid.uuid4(), needs_user_name=False, can_share_email_domain=False)

        assert session.pages == [
            CreateOrganisationPage.TYPE,
            CreateOrganisationPage.NAME,
            CreateOrganisationPage.CHECK_YOUR_ANSWERS,
        ]

    def test_a_local_authority_journey_ends_at_the_support_page(self):
        session = _session(uuid.uuid4(), organisation_type=SignUpOrganisationType.LOCAL_AUTHORITY)

        assert session.pages == [CreateOrganisationPage.TYPE, CreateOrganisationPage.LOCAL_AUTHORITY]
        assert session.first_incomplete_page is CreateOrganisationPage.LOCAL_AUTHORITY

    def test_a_registered_company_is_found_through_the_lookup_when_it_is_on(self):
        session = _session(uuid.uuid4(), companies_house_lookup=True)

        session.answer_organisation_type(SignUpOrganisationType.COMPANY)

        assert session.identified_by is OrganisationIdentification.COMPANIES_HOUSE
        assert session.name_page is CreateOrganisationPage.COMPANY_SEARCH
        assert session.pages[:2] == [CreateOrganisationPage.TYPE, CreateOrganisationPage.COMPANY_SEARCH]
        assert session.first_incomplete_page is CreateOrganisationPage.COMPANY_SEARCH

    @pytest.mark.parametrize(
        "organisation_type, companies_house_lookup",
        [(SignUpOrganisationType.COMPANY, False), (SignUpOrganisationType.CHARITY, True)],
    )
    def test_other_organisations_are_named_by_hand(self, organisation_type, companies_house_lookup):
        session = _session(uuid.uuid4(), companies_house_lookup=companies_house_lookup)

        session.answer_organisation_type(organisation_type)

        assert session.identified_by is OrganisationIdentification.MANUAL
        assert session.name_page is CreateOrganisationPage.NAME
        assert session.first_incomplete_page is CreateOrganisationPage.NAME

    @pytest.mark.parametrize("identified_by", list(OrganisationIdentification))
    def test_a_company_is_complete_however_it_was_found(self, identified_by):
        session = self._named_session(
            organisation_type=SignUpOrganisationType.COMPANY, identified_by=identified_by, allow_team_members=True
        )

        assert session.first_incomplete_page is CreateOrganisationPage.CHECK_YOUR_ANSWERS

    def test_changing_to_a_type_found_another_way_forgets_the_name_and_identifier(self):
        session = self._named_session(companies_house_lookup=True, allow_team_members=True)

        session.answer_organisation_type(SignUpOrganisationType.COMPANY)

        assert session.name is None
        assert session.external_id is None
        assert session.allow_team_members is True

    def test_changing_to_a_type_found_the_same_way_keeps_the_name_and_identifier(self):
        session = self._named_session(companies_house_lookup=True)

        session.answer_organisation_type(SignUpOrganisationType.CHARITY)

        assert session.name == "Acme Ltd"
        assert session.external_id == "000123456"

    def test_first_incomplete_page_starts_with_the_organisation_type(self):
        assert _session(uuid.uuid4()).first_incomplete_page is CreateOrganisationPage.TYPE

    def test_first_incomplete_page_needs_a_name_and_identifier(self):
        session = _session(uuid.uuid4(), organisation_type=SignUpOrganisationType.OTHER, name="Acme Ltd")

        assert session.first_incomplete_page is CreateOrganisationPage.NAME

    def test_first_incomplete_page_asks_for_team_members_when_the_domain_can_be_shared(self):
        assert self._named_session().first_incomplete_page is CreateOrganisationPage.TEAM_MEMBERS

    def test_first_incomplete_page_asks_for_the_users_name_when_we_do_not_hold_one(self):
        session = self._named_session(needs_user_name=True, allow_team_members=False, user_name="")

        assert session.first_incomplete_page is CreateOrganisationPage.USER_NAME

    def test_first_incomplete_page_is_check_your_answers_once_everything_applicable_is_answered(self):
        session = self._named_session(can_share_email_domain=False, needs_user_name=True, user_name="Test")

        assert session.first_incomplete_page is CreateOrganisationPage.CHECK_YOUR_ANSWERS

    @pytest.mark.parametrize("organisation_type", list(SignUpOrganisationType))
    def test_the_pages_follow_the_order_the_enum_declares(self, organisation_type):
        session = _session(
            uuid.uuid4(), needs_user_name=True, can_share_email_domain=True, organisation_type=organisation_type
        )
        journey_order = list(CreateOrganisationPage)

        assert session.pages == sorted(session.pages, key=journey_order.index)


class TestCreateOrganisationNavigationUrls:
    def _bind(self, session, page, *, from_check_your_answers=False):
        request_args = {"source": CHECK_YOUR_ANSWERS} if from_check_your_answers else {}
        session.validate_for_page(
            page, grant_slug="test-grant", collection_slug="test-collection", request_args=request_args
        )
        return session

    def _url(self, page, **params):
        return url_for(
            f"access_grant_funding.{page}", grant_slug="test-grant", collection_slug="test-collection", **params
        )

    def _named_session(self, **overrides):
        answers = {"organisation_type": SignUpOrganisationType.OTHER, "name": "Acme Ltd", "external_id": "000123456"}
        return _session(uuid.uuid4(), **(answers | overrides))

    def test_next_page_is_the_next_applicable_page(self):
        session = self._bind(self._named_session(), CreateOrganisationPage.NAME)

        assert session.next_page == self._url(CreateOrganisationPage.TEAM_MEMBERS)

    def test_next_page_skips_the_steps_that_do_not_apply(self):
        session = self._named_session(can_share_email_domain=False, needs_user_name=True)
        self._bind(session, CreateOrganisationPage.NAME)

        assert session.next_page == self._url(CreateOrganisationPage.USER_NAME)

    def test_next_page_from_check_your_answers_returns_there_once_everything_is_answered(self):
        session = self._named_session(allow_team_members=False)
        self._bind(session, CreateOrganisationPage.NAME, from_check_your_answers=True)

        assert session.next_page == self._url(CreateOrganisationPage.CHECK_YOUR_ANSWERS)

    def test_next_page_from_check_your_answers_goes_to_the_first_unanswered_page(self):
        session = self._bind(self._named_session(), CreateOrganisationPage.TYPE, from_check_your_answers=True)

        assert session.next_page == self._url(CreateOrganisationPage.TEAM_MEMBERS, source=CHECK_YOUR_ANSWERS)

    def test_previous_page_from_the_first_page_leaves_the_journey(self):
        session = self._bind(_session(uuid.uuid4()), CreateOrganisationPage.TYPE)

        assert session.previous_page == self._url(CreateOrganisationPage.ELIGIBLE_TO_APPLY)

    def test_previous_page_skips_the_steps_that_do_not_apply(self):
        session = self._named_session(can_share_email_domain=False, needs_user_name=True)
        self._bind(session, CreateOrganisationPage.USER_NAME)

        assert session.previous_page == self._url(CreateOrganisationPage.NAME)

    def test_previous_page_from_check_your_answers_returns_there_once_everything_is_answered(self):
        session = self._named_session(allow_team_members=False)
        self._bind(session, CreateOrganisationPage.NAME, from_check_your_answers=True)

        assert session.previous_page == self._url(CreateOrganisationPage.CHECK_YOUR_ANSWERS)

    def test_previous_page_from_check_your_answers_steps_back_while_answers_are_missing(self):
        session = _session(uuid.uuid4(), organisation_type=SignUpOrganisationType.OTHER)
        self._bind(session, CreateOrganisationPage.NAME, from_check_your_answers=True)

        assert session.previous_page == self._url(CreateOrganisationPage.TYPE, source=CHECK_YOUR_ANSWERS)

    def test_previous_page_from_already_exists_is_the_name_page(self):
        session = self._bind(self._named_session(), CreateOrganisationPage.ALREADY_EXISTS)

        assert session.previous_page == self._url(CreateOrganisationPage.NAME)

    def _register_session(self):
        return _session(
            uuid.uuid4(),
            organisation_type=SignUpOrganisationType.COMPANY,
            identified_by=OrganisationIdentification.COMPANIES_HOUSE,
            companies_house_lookup=True,
        )

    def test_previous_page_from_the_unavailable_page_is_the_search(self):
        session = self._bind(self._register_session(), CreateOrganisationPage.COMPANY_SEARCH_UNAVAILABLE)

        assert session.previous_page == self._url(CreateOrganisationPage.COMPANY_SEARCH)

    def test_previous_page_from_the_unavailable_page_keeps_the_way_back_to_check_your_answers(self):
        session = self._bind(
            self._register_session(), CreateOrganisationPage.COMPANY_SEARCH_UNAVAILABLE, from_check_your_answers=True
        )

        assert session.previous_page == self._url(CreateOrganisationPage.COMPANY_SEARCH, source=CHECK_YOUR_ANSWERS)

    def test_next_page_after_falling_back_to_manual_entry_is_the_name_page(self):
        session = self._bind(self._register_session(), CreateOrganisationPage.COMPANY_SEARCH_UNAVAILABLE)

        session.fall_back_to_manual_entry()

        assert session.next_page == self._url(CreateOrganisationPage.NAME)

    def test_next_page_after_falling_back_from_check_your_answers_asks_for_the_name_first(self):
        session = self._bind(
            self._register_session(), CreateOrganisationPage.COMPANY_SEARCH_UNAVAILABLE, from_check_your_answers=True
        )

        session.fall_back_to_manual_entry()

        assert session.next_page == self._url(CreateOrganisationPage.NAME, source=CHECK_YOUR_ANSWERS)


class TestNamedCreateOrganisationSession:
    def _session_dict(self, collection_id, **overrides):
        answers = {
            "organisation_type": SignUpOrganisationType.COMPANY,
            "name": "Acme Ltd",
            "external_id": "000123456",
        } | overrides
        return _session(collection_id, **answers).to_session_dict()

    def _load(self, session_dict, collection_id):
        return NamedCreateOrganisationSession.from_session(collection_id=collection_id, session_data=session_dict)

    def test_from_session_loads_a_session_that_has_named_the_organisation(self):
        collection_id = uuid.uuid4()

        loaded = self._load(self._session_dict(collection_id), collection_id)

        assert loaded is not None
        assert loaded.organisation_type is SignUpOrganisationType.COMPANY
        assert loaded.name == "Acme Ltd"
        assert loaded.external_id == "000123456"

    @pytest.mark.parametrize("unanswered", ["organisation_type", "name", "external_id"])
    def test_from_session_needs_the_organisation_type_name_and_id(self, unanswered):
        collection_id = uuid.uuid4()
        session_dict = self._session_dict(collection_id)
        del session_dict[unanswered]

        assert self._load(session_dict, collection_id) is None

    @pytest.mark.parametrize("left_blank", ["name", "external_id"])
    def test_from_session_does_not_take_a_blank_name_or_id_as_an_answer(self, left_blank):
        collection_id = uuid.uuid4()

        assert self._load(self._session_dict(collection_id, **{left_blank: ""}), collection_id) is None


class TestCompleteCreateOrganisationSession:
    def _session_dict(self, collection_id, **overrides):
        answers = {
            "organisation_type": SignUpOrganisationType.COMPANY,
            "name": "Acme Ltd",
            "external_id": "000123456",
            "allow_team_members": True,
        } | overrides
        return _session(collection_id, **answers).to_session_dict()

    def _load(self, session_dict, collection_id):
        return CompleteCreateOrganisationSession.from_session(collection_id=collection_id, session_data=session_dict)

    def test_from_session_loads_a_session_with_every_answer(self):
        collection_id = uuid.uuid4()

        loaded = self._load(self._session_dict(collection_id, needs_user_name=True, user_name="Test"), collection_id)

        assert loaded is not None
        assert loaded.name == "Acme Ltd"
        assert loaded.user_name == "Test"

    def test_from_session_does_not_need_a_full_name_when_the_step_was_skipped(self):
        collection_id = uuid.uuid4()

        assert self._load(self._session_dict(collection_id), collection_id) is not None

    def test_from_session_needs_a_full_name_when_the_user_was_asked_for_one(self):
        collection_id = uuid.uuid4()

        assert self._load(self._session_dict(collection_id, needs_user_name=True), collection_id) is None

    def test_from_session_needs_the_allow_team_members_answer(self):
        collection_id = uuid.uuid4()
        session_dict = self._session_dict(collection_id)
        del session_dict["allow_team_members"]

        assert self._load(session_dict, collection_id) is None

    def test_from_session_does_not_need_the_allow_team_members_answer_when_the_step_was_skipped(self):
        collection_id = uuid.uuid4()
        session_dict = self._session_dict(collection_id, can_share_email_domain=False)
        del session_dict["allow_team_members"]

        assert self._load(session_dict, collection_id) is not None


class TestStartPublicSignUp:
    def test_re_entering_the_same_collection_keeps_which_metrics_have_already_been_emitted(self, app: Flask):
        collection_id = uuid.uuid4()

        with app.test_request_context("/"):
            start_public_sign_up(collection_id)
            session[SESSION_EMITTED_PUBLIC_SIGN_UP_METRICS] = ["public-sign-up-started"]

            start_public_sign_up(collection_id)

            assert session[SESSION_EMITTED_PUBLIC_SIGN_UP_METRICS] == ["public-sign-up-started"]

    def test_starting_a_different_collection_resets_which_metrics_have_already_been_emitted(self, app: Flask):
        collection_id = uuid.uuid4()
        second_collection_id = uuid.uuid4()
        with app.test_request_context("/"):
            start_public_sign_up(collection_id)
            session[SESSION_EMITTED_PUBLIC_SIGN_UP_METRICS] = ["public-sign-up-started"]

            start_public_sign_up(second_collection_id)

            assert SESSION_EMITTED_PUBLIC_SIGN_UP_METRICS not in session
