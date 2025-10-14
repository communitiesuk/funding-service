# mypy: disable-error-code="no-untyped-call"
# FactoryBoy doesn't have typing on its functions yet, so we disable that type check for this file only.

"""
A module containing FactoryBoy definitions for our DB models. Do not use these classes directly - they should be
accessed through fixtures such as `grant_factory`, which can ensure the Flask app and DB are properly instrumented
for transactional isolation.
"""

import datetime
import random
import secrets
from typing import Any, cast
from uuid import uuid4

import factory.fuzzy
import faker
from factory.alchemy import SQLAlchemyModelFactory
from flask import url_for

from app.common.collections.types import (
    DateAnswer,
    EmailAnswer,
    IntegerAnswer,
    MultipleChoiceFromListAnswer,
    SingleChoiceFromListAnswer,
    TextMultiLineAnswer,
    TextSingleLineAnswer,
    YesNoAnswer,
)
from app.common.data.interfaces.collections import _validate_and_sync_component_references
from app.common.data.models import (
    Collection,
    DataSource,
    DataSourceItem,
    Expression,
    Form,
    Grant,
    Group,
    Organisation,
    Question,
    Submission,
    SubmissionEvent,
)
from app.common.data.models_user import Invitation, MagicLink, User, UserRole
from app.common.data.types import (
    CollectionType,
    QuestionDataType,
    QuestionPresentationOptions,
    SubmissionEventKey,
    SubmissionModeEnum,
)
from app.common.expressions import ExpressionContext
from app.common.expressions.managed import AnyOf, GreaterThan, IsYes, Specifically
from app.extensions import db
from app.types import TRadioItem


def _required() -> None:
    raise ValueError("Value must be set explicitly for tests")


class _GrantFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Grant
        sqlalchemy_session_factory = lambda: db.session  # noqa: E731
        sqlalchemy_session_persistence = "commit"

    id = factory.LazyFunction(uuid4)
    ggis_number = factory.Sequence(lambda n: f"GGIS-{n:06d}")
    name = factory.Sequence(lambda n: "Grant %d" % n)
    description = factory.Faker("text", max_nb_chars=200)
    primary_contact_name = factory.Faker("name")
    primary_contact_email = factory.Faker("email")


class _UserFactory(SQLAlchemyModelFactory):
    class Meta:
        model = User
        sqlalchemy_session_factory = lambda: db.session  # noqa: E731
        sqlalchemy_session_persistence = "commit"

    id = factory.LazyFunction(uuid4)
    name = factory.Faker("name")
    email = factory.Faker("email")
    azure_ad_subject_id = factory.fuzzy.FuzzyText(length=25)
    last_logged_in_at_utc = factory.LazyFunction(lambda: datetime.datetime.now())


class _OrganisationFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Organisation
        sqlalchemy_session_factory = lambda: db.session  # noqa: E731

    id = factory.LazyFunction(uuid4)
    name = factory.Sequence(lambda n: "Organisation %d" % n)


class _UserRoleFactory(SQLAlchemyModelFactory):
    class Meta:
        model = UserRole
        sqlalchemy_session_factory = lambda: db.session  # noqa: E731
        sqlalchemy_session_persistence = "commit"

    id = factory.LazyFunction(uuid4)
    user_id = factory.LazyAttribute(lambda o: o.user.id)
    user = factory.SubFactory(_UserFactory)
    organisation_id = None
    organisation = None
    grant_id = factory.LazyAttribute(lambda o: o.grant.id if o.grant else None)
    grant = None
    role = None  # This needs to be overridden when initialising the factory

    class Params:
        has_organisation = factory.Trait(
            organisation_id=factory.LazyAttribute(lambda o: o.organisation.id),
            organisation=factory.SubFactory(_OrganisationFactory),
        )
        has_grant = factory.Trait(
            grant_id=factory.LazyAttribute(lambda o: o.grant.id),
            grant=factory.SubFactory(_GrantFactory),
        )


class _MagicLinkFactory(SQLAlchemyModelFactory):
    class Meta:
        model = MagicLink
        sqlalchemy_session_factory = lambda: db.session  # noqa: E731
        sqlalchemy_session_persistence = "commit"

    id = factory.LazyFunction(uuid4)
    code = factory.LazyFunction(lambda: secrets.token_urlsafe(12))
    user_id = factory.LazyAttribute(lambda o: o.user.id if o.user else None)  # noqa: E731
    user = None
    email = factory.Faker("email")
    redirect_to_path = factory.LazyFunction(lambda: url_for("deliver_grant_funding.list_grants"))
    expires_at_utc = factory.LazyFunction(lambda: datetime.datetime.now() + datetime.timedelta(minutes=15))
    claimed_at_utc = None


class _CollectionFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Collection
        sqlalchemy_session_factory = lambda: db.session  # noqa: E731
        sqlalchemy_session_persistence = "commit"

    id = factory.LazyFunction(uuid4)
    name = factory.Sequence(lambda n: "Collection %d" % n)
    slug = factory.Sequence(lambda n: "collection-%d" % n)
    type = CollectionType.MONITORING_REPORT

    created_by_id = factory.LazyAttribute(lambda o: o.created_by.id)
    created_by = factory.SubFactory(_UserFactory)

    grant_id = factory.LazyAttribute(lambda o: "o.grant.id")
    grant = factory.SubFactory(_GrantFactory)

    @factory.post_generation  # type: ignore
    def create_completed_submissions_conditional_question(  # type: ignore
        obj: Collection,
        create,
        extracted,
        test: bool = False,
        live: bool = False,
        **kwargs,
    ) -> None:
        if not live and not test:
            return

        form = _FormFactory.create(collection=obj, title="Export test form", slug="export-test-form")

        # Create a conditional branch of questions
        q1 = _QuestionFactory.create(
            name="Number of cups of tea",
            form=form,
            data_type=QuestionDataType.INTEGER,
            text="How many cups of tea do you drink in a week?",
        )
        q2 = _QuestionFactory.create(
            name="Tea bag pack size",
            form=form,
            data_type=QuestionDataType.INTEGER,
            text="What size pack of teabags do you usually buy?",
            expressions=[
                Expression.from_managed(GreaterThan(question_id=q1.id, minimum_value=30), _UserFactory.create())
            ],
        )
        q3 = _QuestionFactory.create(
            name="Favourite dunking biscuit",
            form=form,
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            text="What is your favourite biscuit to dunk?",
        )

        def _create_submission(mode: SubmissionModeEnum, complete_question_2: bool = False) -> None:
            response_data: dict[str, Any] = {
                str(q1.id): IntegerAnswer(value=(40 if complete_question_2 else 20)).get_value_for_submission()  # ty: ignore[missing-argument]
            }
            if complete_question_2:
                response_data[str(q2.id)] = IntegerAnswer(value=80).get_value_for_submission()  # ty: ignore[missing-argument]

            response_data[str(q3.id)] = TextSingleLineAnswer("digestive").get_value_for_submission()  # ty: ignore[missing-argument]

            _SubmissionFactory.create(
                collection=obj,
                mode=mode,
                data=response_data,
            )

        if test:
            _create_submission(SubmissionModeEnum.TEST, complete_question_2=True)
            _create_submission(SubmissionModeEnum.TEST, complete_question_2=False)
        if live:
            _create_submission(SubmissionModeEnum.LIVE, complete_question_2=True)
            _create_submission(SubmissionModeEnum.LIVE, complete_question_2=False)

    @factory.post_generation  # type: ignore
    def create_completed_submissions_conditional_question_random(  # type: ignore
        obj: Collection,
        create,
        extracted,
        test: int = 0,
        live: int = 0,
        **kwargs,
    ) -> None:
        if not live and not test:
            return

        form = _FormFactory.create(collection=obj, title="Export test form", slug="export-test-form")

        # Create a conditional branch of questions
        q1 = _QuestionFactory.create(
            name="Number of cups of tea",
            form=form,
            data_type=QuestionDataType.INTEGER,
            text="How many cups of tea do you drink in a week?",
        )
        q2 = _QuestionFactory.create(
            name="Buy teabags in bulk",
            form=form,
            data_type=QuestionDataType.YES_NO,
            text="Do you buy teabags in bulk?",
            expressions=[
                Expression.from_managed(GreaterThan(question_id=q1.id, minimum_value=30), _UserFactory.create())
            ],
        )
        q3 = _QuestionFactory.create(
            name="Favourite dunking biscuit",
            form=form,
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            text="What is your favourite biscuit to dunk?",
        )
        q4 = _QuestionFactory.create(
            name="Favourite brand of teabags",
            form=form,
            data_type=QuestionDataType.RADIOS,
            text="What is your favourite brand of teabags?",
        )
        q5 = _QuestionFactory.create(
            name="Favourite brand of teabags (Other)",
            form=form,
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            text="What is your favourite brand of teabags (Other)?",
            expressions=[
                Expression.from_managed(
                    AnyOf(
                        question_id=q4.id,
                        items=[
                            cast(
                                TRadioItem, {"key": q4.data_source.items[0].key, "label": q4.data_source.items[0].label}
                            )
                        ],
                    ),
                    _UserFactory.create(),
                )
            ],
        )
        q6 = _QuestionFactory.create(
            name="Favourite types of cheese",
            form=form,
            data_type=QuestionDataType.CHECKBOXES,
            text="What are your favourite types of cheese?",
        )
        q7 = _QuestionFactory.create(
            name="Favourite type of cheese (Other)",
            form=form,
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            text="What is your type of cheese (Other)?",
            expressions=[
                Expression.from_managed(
                    Specifically(
                        question_id=q4.id,
                        item=cast(
                            TRadioItem, {"key": q4.data_source.items[0].key, "label": q4.data_source.items[0].label}
                        ),
                    ),
                    _UserFactory.create(),
                )
            ],
        )

        def _create_submission(mode: SubmissionModeEnum, count: int = 0) -> None:
            for _ in range(count):
                response_data: dict[str, Any] = {
                    str(q1.id): IntegerAnswer(value=faker.Faker().random_int(min=0, max=60)).get_value_for_submission()  # ty: ignore[missing-argument]
                }
                response_data[str(q2.id)] = YesNoAnswer(random.choice([True, False])).get_value_for_submission()  # ty: ignore[missing-argument]

                response_data[str(q3.id)] = TextSingleLineAnswer(faker.Faker().word()).get_value_for_submission()  # ty: ignore[missing-argument]
                item_choice = faker.Faker().random_int(min=0, max=2)
                response_data[str(q4.id)] = SingleChoiceFromListAnswer(
                    key=q4.data_source.items[item_choice].key, label=q4.data_source.items[item_choice].label
                ).get_value_for_submission()

                response_data[str(q5.id)] = TextSingleLineAnswer(faker.Faker().word()).get_value_for_submission()  # ty: ignore[missing-argument]
                response_data[str(q6.id)] = MultipleChoiceFromListAnswer(
                    choices=[
                        {"key": q6.data_source.items[0].key, "label": q6.data_source.items[0].label},
                        {"key": q6.data_source.items[-1].key, "label": q6.data_source.items[-1].label},
                    ]
                ).get_value_for_submission()  # ty: ignore[missing-argument]
                response_data[str(q7.id)] = TextSingleLineAnswer(faker.Faker().word()).get_value_for_submission()  # ty: ignore[missing-argument]

                _SubmissionFactory.create(
                    collection=obj,
                    mode=mode,
                    data=response_data,
                )

        _create_submission(SubmissionModeEnum.TEST, test)
        _create_submission(SubmissionModeEnum.LIVE, live)

    @factory.post_generation  # type: ignore
    def create_completed_submissions_each_question_type(  # type: ignore
        obj: Collection,
        create,
        extracted,
        test: int = 0,
        live: int = 0,
        use_random_data: bool = True,
        **kwargs,
    ) -> None:
        if not test and not live:
            return
        form = _FormFactory.create(collection=obj, title="Export test form", slug="export-test-form")

        # Assertion to remind us to add more question types here when we start supporting them
        assert len(QuestionDataType) == 9, "If you have added a new question type, please update this factory."

        # Create a question of each supported type
        q1 = _QuestionFactory.create(
            name="Your name", form=form, data_type=QuestionDataType.TEXT_SINGLE_LINE, text="What is your name?"
        )
        q2 = _QuestionFactory.create(
            name="Your quest", form=form, data_type=QuestionDataType.TEXT_MULTI_LINE, text="What is your quest?"
        )
        q3 = _QuestionFactory.create(
            name="Airspeed velocity",
            form=form,
            data_type=QuestionDataType.INTEGER,
            text="What is the airspeed velocity of an unladen swallow?",
        )
        q4 = _QuestionFactory.create(
            form=form,
            data_type=QuestionDataType.RADIOS,
            text="What is the best option?",
            name="Best option",
        )
        q5 = _QuestionFactory.create(
            form=form, data_type=QuestionDataType.YES_NO, text="Do you like cheese?", name="Like cheese"
        )
        q6 = _QuestionFactory.create(
            form=form, data_type=QuestionDataType.EMAIL, text="What is your email address?", name="Email address"
        )
        q7 = _QuestionFactory.create(
            form=form, data_type=QuestionDataType.URL, text="What is your website address?", name="Website address"
        )
        q8 = _QuestionFactory.create(
            form=form,
            data_type=QuestionDataType.CHECKBOXES,
            text="What are your favourite cheeses?",
            name="Favourite cheeses",
            data_source__items=[],
        )

        q8.data_source.items = [
            _DataSourceItemFactory.build(data_source=q8.data_source, key=key, label=label)
            for key, label in [("cheddar", "Cheddar"), ("brie", "Brie"), ("stilton", "Stilton")]
        ]
        q9 = _QuestionFactory.create(
            name="Last cheese purchase date",
            form=form,
            data_type=QuestionDataType.DATE,
            text="When did you last buy some cheese?",
        )

        def _create_submission_of_type(submission_mode: SubmissionModeEnum, count: int) -> None:
            for _ in range(0, count):
                item_choice = faker.Faker().random_int(min=0, max=2) if use_random_data else 0
                _SubmissionFactory.create(
                    collection=obj,
                    mode=submission_mode,
                    data={
                        str(q1.id): TextSingleLineAnswer(  # ty: ignore[missing-argument]
                            faker.Faker().name() if use_random_data else "test name"
                        ).get_value_for_submission(),
                        str(q2.id): TextMultiLineAnswer(  # ty: ignore[missing-argument]
                            "\r\n".join(faker.Faker().sentences(nb=3))
                            if use_random_data
                            else "Line 1\r\nline2\r\nline 3"
                        ).get_value_for_submission(),
                        str(q3.id): IntegerAnswer(  # ty: ignore[missing-argument]
                            value=(faker.Faker().random_number(2) if use_random_data else 123)
                        ).get_value_for_submission(),
                        str(q4.id): SingleChoiceFromListAnswer(  # ty: ignore[missing-argument]
                            key=q4.data_source.items[item_choice].key, label=q4.data_source.items[item_choice].label
                        ).get_value_for_submission(),
                        str(q5.id): YesNoAnswer(  # ty: ignore[missing-argument]
                            random.choice([True, False]) if use_random_data else True
                        ).get_value_for_submission(),  # ty: ignore[missing-argument]
                        str(q6.id): TextSingleLineAnswer(  # ty: ignore[missing-argument]
                            faker.Faker().email() if use_random_data else "test@email.com"
                        ).get_value_for_submission(),
                        str(q7.id): TextSingleLineAnswer(  # ty: ignore[missing-argument]
                            faker.Faker().url()
                            if use_random_data
                            else "https://www.gov.uk/government/organisations/ministry-of-housing-communities-local-government"
                        ).get_value_for_submission(),
                        str(q8.id): MultipleChoiceFromListAnswer(
                            choices=[
                                {"key": q8.data_source.items[0].key, "label": q8.data_source.items[0].label},
                                {"key": q8.data_source.items[-1].key, "label": q8.data_source.items[-1].label},
                            ]
                        ).get_value_for_submission(),
                        str(q9.id): DateAnswer(
                            answer=datetime.datetime.strptime(faker.Faker().date(), "%Y-%m-%d").date()
                            if use_random_data
                            else datetime.date(2025, 1, 1)
                        ).get_value_for_submission(),
                    },
                )

        _create_submission_of_type(SubmissionModeEnum.TEST, test)
        _create_submission_of_type(SubmissionModeEnum.LIVE, live)

    @factory.post_generation  # type: ignore
    def create_submissions(  # type: ignore
        obj: Collection,
        create,
        extracted,
        test: int = 0,
        live: int = 0,
        **kwargs,
    ) -> None:
        """
        Uses this pattern https://factoryboy.readthedocs.io/en/stable/reference.html#post-generation-hooks to create
        submissions for the collection of different types.
        Doesn't use a sub/related factory because of circular import problems.
        :param create:
        :param extracted:
        :param test: Number of test submissions to create
        :param live: Number of live submissions to create
        :param kwargs:
        :return:
        """
        for _ in range(0, test):
            _SubmissionFactory.create(collection=obj, mode=SubmissionModeEnum.TEST)
        for _ in range(0, live):
            _SubmissionFactory.create(collection=obj, mode=SubmissionModeEnum.LIVE)

    @factory.post_generation  # type: ignore
    def create_completed_submissions_add_another_nested_group(  # type: ignore
        obj: Collection,
        create,
        extracted,
        test: int = 0,
        live: int = 0,
        use_random_data: bool = True,
        number_of_add_another_answers: int = 5,
        **kwargs,
    ) -> None:
        if not test and not live:
            return
        form = _FormFactory.create(
            collection=obj, title="Add another nested group test form", slug="add-another-nested-group-test-form"
        )

        # Create a form with a nested add another group
        q1 = _QuestionFactory.create(
            name="Your name", form=form, data_type=QuestionDataType.TEXT_SINGLE_LINE, text="What is your name?"
        )
        g1 = _GroupFactory.create(
            name="Organisation details test group",
            text="Organisation details test group",
            slug="org-details-test-group",
            form=form,
        )
        q2 = _QuestionFactory.create(
            name="Organisation name",
            form=form,
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            text="What is your organisation name?",
            parent=g1,
        )
        g2 = _GroupFactory.create(
            name="Organisation contacts test group",
            text="Organisation contacts test group",
            slug="org-contacts-test-group",
            parent=g1,
            add_another=True,
            form=form,
        )
        q3 = _QuestionFactory.create(
            name="Contact name",
            form=form,
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            text="What is the name of this person?",
            parent=g2,
        )
        q4 = _QuestionFactory.create(
            form=form,
            data_type=QuestionDataType.EMAIL,
            text="What is this person's email address?",
            name="Contact email",
            parent=g2,
        )
        q5 = _QuestionFactory.create(
            name="Length of service",
            form=form,
            data_type=QuestionDataType.INTEGER,
            text="How many years have you worked here?",
        )

        add_another_responses = []
        for i in range(0, number_of_add_another_answers):
            add_another_responses.append(
                {
                    str(q3.id): TextSingleLineAnswer(  # ty:ignore[missing-argument]
                        faker.Faker().name() if use_random_data else f"test name {i}"
                    ).get_value_for_submission(),
                    str(q4.id): EmailAnswer(  # ty:ignore[missing-argument]
                        faker.Faker().company_email() if use_random_data else f"test_user_{i}@email.com"
                    ).get_value_for_submission(),
                }
            )

        def _create_submission_of_type(submission_mode: SubmissionModeEnum, count: int) -> None:
            for _ in range(0, count):
                _SubmissionFactory.create(
                    collection=obj,
                    mode=submission_mode,
                    data={
                        str(q1.id): TextSingleLineAnswer(  # ty:ignore[missing-argument]
                            faker.Faker().name() if use_random_data else "test name"
                        ).get_value_for_submission(),
                        str(q2.id): TextSingleLineAnswer(  # ty:ignore[missing-argument]
                            faker.Faker().name() if use_random_data else "test org name"
                        ).get_value_for_submission(),
                        str(g2.id): add_another_responses,
                        str(q5.id): IntegerAnswer(
                            value=random.randint(0, 10) if use_random_data else 3
                        ).get_value_for_submission(),
                    },
                )

        _create_submission_of_type(SubmissionModeEnum.TEST, test)
        _create_submission_of_type(SubmissionModeEnum.LIVE, live)

    # TODO can we streamline these different options for creating collections or will that make it more complicated
    @factory.post_generation  # type: ignore
    def create_completed_submissions_add_another_nested_group_with_conditions(  # type: ignore
        obj: Collection,
        create,
        extracted,
        test: int = 0,
        live: int = 0,
        **kwargs,
    ) -> None:
        if not test and not live:
            return
        form = _FormFactory.create(
            collection=obj, title="Add another nested group test form", slug="add-another-nested-group-test-form"
        )

        # Create a form with a nested add another group
        q0 = _QuestionFactory.create(
            name="Park name",
            form=form,
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            text="What is the name of your park?",
            add_another=False,
        )
        q1 = _QuestionFactory.create(
            name="Has trees", form=form, data_type=QuestionDataType.YES_NO, text="Does your park have trees?"
        )
        q2 = _QuestionFactory.create(
            name="Tree species",
            expressions=[
                Expression.from_managed(
                    IsYes(
                        question_id=q1.id,
                    ),
                    _UserFactory.create(),
                )
            ],
            form=form,
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            text="What type of tree species do you have?",
            add_another=True,
        )
        q3 = _QuestionFactory.create(
            name="Has play equipment",
            form=form,
            data_type=QuestionDataType.YES_NO,
            text="Does your park have play equipment?",
        )
        q9 = _QuestionFactory.create(
            name="Equipment fenced off",
            form=form,
            data_type=QuestionDataType.YES_NO,
            text="Is the equipment fenced off?",
            expressions=[
                Expression.from_managed(
                    IsYes(
                        question_id=q3.id,
                    ),
                    _UserFactory.create(),
                )
            ],
        )

        g1 = _GroupFactory.create(
            name="Play equipment details group",
            text="Tell us about your play equipment",
            slug="play-equipment-test-group",
            form=form,
            expressions=[
                Expression.from_managed(
                    IsYes(
                        question_id=q3.id,
                    ),
                    _UserFactory.create(),
                )
            ],
        )
        q4 = _QuestionFactory.create(
            name="Number of pieces of equipment",
            form=form,
            data_type=QuestionDataType.INTEGER,
            text="How many pieces of play equipment do you have?",
            parent=g1,
        )
        g2 = _GroupFactory.create(
            name="Equipment details",
            text="Tell us about each piece of equipment",
            slug="equipment-add-another-group",
            parent=g1,
            add_another=True,
            form=form,
        )
        q5 = _QuestionFactory.create(
            name="Type of equipment",
            form=form,
            data_type=QuestionDataType.RADIOS,
            text="What is this piece of equipment?",
            data_source__items=["swing", "slide", "other"],
            parent=g2,
        )
        q6 = _QuestionFactory.create(
            form=form,
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            text="Describe this piece of equipment",
            name="Equipment type - Other",
            expressions=[
                Expression.from_managed(
                    AnyOf(question_id=q5.id, items=[{"key": "other", "label": "other"}]), _UserFactory.create()
                )
            ],
            parent=g2,
        )
        q7 = _QuestionFactory.create(
            name="How many years old is this piece of equipment?",
            form=form,
            data_type=QuestionDataType.INTEGER,
            text="Age",
            parent=g2,
        )
        q8 = _QuestionFactory.create(
            name="Under a tree",
            form=form,
            data_type=QuestionDataType.YES_NO,
            text="Is this piece of equipment under a tree?",
            parent=g2,
            expressions=[
                Expression.from_managed(
                    IsYes(
                        question_id=q1.id,
                    ),
                    _UserFactory.create(),
                )
            ],
        )

        obj.park_name_question = q0
        obj.has_trees_question = q1
        obj.tree_species_question = q2
        obj.has_equipment_question = q3
        obj.equipment_number_question = q4
        obj.equipment_group = g1
        obj.add_another_group = g2
        obj.type_of_equipment_question = q5
        obj.other_equipment_question = q6
        obj.under_a_tree_question = q8
        obj.fenced_off_question = q9

        add_another_responses = []
        add_another_responses.append(
            {
                str(q5.id): SingleChoiceFromListAnswer(key="slide", label="slide").get_value_for_submission(),
                str(q7.id): IntegerAnswer(value=1).get_value_for_submission(),
            }
        )
        add_another_responses.append(
            {
                str(q5.id): SingleChoiceFromListAnswer(key="swing", label="swing").get_value_for_submission(),
                str(q7.id): IntegerAnswer(value=2).get_value_for_submission(),
            }
        )
        add_another_responses.append(
            {
                str(q5.id): SingleChoiceFromListAnswer(key="other", label="other").get_value_for_submission(),
                str(q6.id): TextSingleLineAnswer("It's a seasaw").get_value_for_submission(),  # type:ignore[dict-item]
                str(q7.id): IntegerAnswer(value=3).get_value_for_submission(),
            }
        )

        def _create_submission_of_type(submission_mode: SubmissionModeEnum, count: int) -> None:
            for _ in range(count):
                _SubmissionFactory.create(
                    collection=obj,
                    mode=submission_mode,
                    data={
                        str(q0.id): TextSingleLineAnswer(  # ty:ignore[missing-argument]
                            "No play equipment, No trees"
                        ).get_value_for_submission(),
                        str(q1.id): YesNoAnswer(  # ty:ignore[missing-argument]
                            False
                        ).get_value_for_submission(),
                        str(q3.id): YesNoAnswer(  # ty:ignore[missing-argument]
                            False
                        ).get_value_for_submission(),
                    },
                )
                _SubmissionFactory.create(
                    collection=obj,
                    mode=submission_mode,
                    data={
                        str(q0.id): TextSingleLineAnswer(  # ty:ignore[missing-argument]
                            "No play equipment, Has trees"
                        ).get_value_for_submission(),
                        str(q1.id): YesNoAnswer(  # ty:ignore[missing-argument]
                            True
                        ).get_value_for_submission(),
                        str(q2.id): [
                            {
                                str(q2.id): TextSingleLineAnswer(  # ty:ignore[missing-argument]
                                    "Oak"
                                ).get_value_for_submission()
                            },
                            {
                                str(q2.id): TextSingleLineAnswer(  # ty:ignore[missing-argument]
                                    "Sycamore"
                                ).get_value_for_submission()
                            },
                        ],
                        str(q3.id): YesNoAnswer(  # ty:ignore[missing-argument]
                            False
                        ).get_value_for_submission(),
                    },
                )
                _SubmissionFactory.create(
                    collection=obj,
                    mode=submission_mode,
                    data={
                        str(q0.id): TextSingleLineAnswer(  # ty:ignore[missing-argument]
                            "Has play equipment, No trees"
                        ).get_value_for_submission(),
                        str(q1.id): YesNoAnswer(  # ty:ignore[missing-argument]
                            False
                        ).get_value_for_submission(),
                        str(q3.id): YesNoAnswer(  # ty:ignore[missing-argument]
                            True
                        ).get_value_for_submission(),
                        str(q4.id): IntegerAnswer(value=1).get_value_for_submission(),
                        str(g2.id): add_another_responses,
                        str(q9.id): YesNoAnswer(  # ty:ignore[missing-argument]
                            False
                        ).get_value_for_submission(),
                    },
                )
                sub = _SubmissionFactory.create(
                    collection=obj,
                    mode=submission_mode,
                    data={
                        str(q0.id): TextSingleLineAnswer(  # ty:ignore[missing-argument]
                            "Has play equipment, Has trees"
                        ).get_value_for_submission(),
                        str(q1.id): YesNoAnswer(  # ty:ignore[missing-argument]
                            True
                        ).get_value_for_submission(),
                        str(q2.id): [
                            {
                                str(q2.id): TextSingleLineAnswer(  # ty:ignore[missing-argument]
                                    "Oak"
                                ).get_value_for_submission()
                            },
                            {
                                str(q2.id): TextSingleLineAnswer(  # ty:ignore[missing-argument]
                                    "Sycamore"
                                ).get_value_for_submission()
                            },
                        ],
                        str(q3.id): YesNoAnswer(  # ty:ignore[missing-argument]
                            True
                        ).get_value_for_submission(),
                        str(q4.id): IntegerAnswer(value=1).get_value_for_submission(),
                        str(g2.id): add_another_responses,
                        str(q9.id): YesNoAnswer(  # ty:ignore[missing-argument]
                            True
                        ).get_value_for_submission(),
                    },
                )
                sub.data[str(g2.id)][0][str(q8.id)] = YesNoAnswer(True).get_value_for_submission()
                sub.data[str(g2.id)][1][str(q8.id)] = YesNoAnswer(False).get_value_for_submission()
                sub.data[str(g2.id)][2][str(q8.id)] = YesNoAnswer(True).get_value_for_submission()

        _create_submission_of_type(SubmissionModeEnum.TEST, test)
        _create_submission_of_type(SubmissionModeEnum.LIVE, live)

    @factory.post_generation
    def commit_the_things_to_clean_the_session(self, create, extracted, **kwargs):  # type: ignore
        # Runs after all of the other post_generation hooks (hopefully) and commits anything created to the DB,
        # so that our clean-session-tracking logic has a clean session again.
        if create:
            _CollectionFactory._meta.sqlalchemy_session_factory().commit()  # type: ignore


class _SubmissionFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Submission
        sqlalchemy_session_factory = lambda: db.session  # noqa: E731
        sqlalchemy_session_persistence = "commit"

    id = factory.LazyFunction(uuid4)
    mode = SubmissionModeEnum.TEST
    data = factory.LazyFunction(dict)

    created_by_id = factory.LazyAttribute(lambda o: o.created_by.id)
    created_by = factory.SubFactory(_UserFactory)

    collection = factory.SubFactory(_CollectionFactory)
    collection_id = factory.LazyAttribute(lambda o: o.collection.id)
    collection_version = factory.LazyAttribute(lambda o: o.collection.version)


class _FormFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Form
        sqlalchemy_session_factory = lambda: db.session  # noqa: E731
        sqlalchemy_session_persistence = "commit"

    id = factory.LazyFunction(uuid4)
    title = factory.Sequence(lambda n: "Form %d" % n)
    slug = factory.Sequence(lambda n: "form-%d" % n)
    order = factory.LazyAttribute(lambda o: len(o.collection.forms))

    collection = factory.SubFactory(_CollectionFactory)
    collection_id = factory.LazyAttribute(lambda o: o.collection.id)


class _DataSourceItemFactory(SQLAlchemyModelFactory):
    class Meta:
        model = DataSourceItem
        sqlalchemy_session_factory = lambda: db.session  # noqa: E731
        sqlalchemy_session_persistence = "commit"

    order = factory.Sequence(lambda n: n)
    key = factory.Sequence(lambda n: "key-%d" % n)
    label = factory.Sequence(lambda n: "Option %d" % n)

    data_source_id = factory.LazyAttribute(lambda o: o.data_source.id if o.data_source else None)
    data_source = None


class _DataSourceFactory(SQLAlchemyModelFactory):
    class Meta:
        model = DataSource
        sqlalchemy_session_factory = lambda: db.session  # noqa: E731
        sqlalchemy_session_persistence = "commit"

    items = factory.RelatedFactoryList(_DataSourceItemFactory, size=3, factory_related_name="data_source")

    question = None
    question_id = factory.LazyAttribute(lambda o: o.question.id if o.question else None)


class _QuestionFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Question
        sqlalchemy_session_factory = lambda: db.session  # noqa: E731
        sqlalchemy_session_persistence = "commit"
        exclude = ("needs_data_source",)

    id = factory.LazyFunction(uuid4)
    text = factory.Sequence(lambda n: "Question %d" % n)
    name = factory.Sequence(lambda n: "Question name %d" % n)
    slug = factory.Sequence(lambda n: "question-%d" % n)
    order = factory.LazyAttribute(
        lambda o: len(o.parent.components) if getattr(o, "parent", None) else len(o.form.components)
    )
    data_type = QuestionDataType.TEXT_SINGLE_LINE
    add_another = False

    form = factory.SubFactory(_FormFactory)
    form_id = factory.LazyAttribute(lambda o: o.form.id)

    needs_data_source = factory.LazyAttribute(
        lambda o: o.data_type in [QuestionDataType.RADIOS, QuestionDataType.CHECKBOXES]
    )
    data_source = factory.Maybe(
        "needs_data_source",
        yes_declaration=factory.RelatedFactory(_DataSourceFactory, factory_related_name="question"),
        no_declaration=None,
    )
    parent = None
    parent_id = factory.LazyAttribute(lambda o: o.parent.id if o.parent else None)

    presentation_options = factory.LazyFunction(lambda: QuestionPresentationOptions())

    @factory.post_generation  # type: ignore[misc]
    def expressions(self, create: bool, extracted: list[Any], **kwargs: Any) -> None:
        if not extracted:
            return
        for expression in extracted:
            expression.question_id = self.id
            self.expressions.append(expression)

        if create:
            db.session.add(expression)
            db.session.commit()

    @factory.post_generation  # type: ignore[misc]
    def _references(self: "Question", create: bool, extracted: list[Any], **kwargs: Any) -> None:
        if not create:
            return

        _validate_and_sync_component_references(
            self,
            ExpressionContext.build_expression_context(collection=self.form.collection, mode="interpolation"),
        )

        # Wipe the cache of questions on a form - because we're likely to be creating more forms/questions
        del self.form.cached_questions
        try:
            del self.form.cached_all_components
        except AttributeError:
            pass
        db.session.commit()


class _GroupFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Group
        sqlalchemy_session_factory = lambda: db.session  # noqa: E731
        sqlalchemy_session_persistence = "commit"

    id = factory.LazyFunction(uuid4)
    text = factory.Sequence(lambda n: "Group %d" % n)
    name = factory.Sequence(lambda n: "Group name %d" % n)
    slug = factory.Sequence(lambda n: "group-%d" % n)
    order = factory.LazyAttribute(
        lambda o: len(o.parent.components) if getattr(o, "parent", None) else len(o.form.components)
    )

    form = factory.SubFactory(_FormFactory)
    form_id = factory.LazyAttribute(lambda o: o.form.id)
    add_another = False

    parent = None
    parent_id = factory.LazyAttribute(lambda o: o.parent.id if o.parent else None)

    presentation_options = factory.LazyFunction(lambda: QuestionPresentationOptions())

    @factory.post_generation  # type: ignore[misc]
    def expressions(self, create: bool, extracted: list[Any], **kwargs: Any) -> None:
        if not extracted:
            return
        for expression in extracted:
            expression.question_id = self.id
            db.session.add(expression)
            self.expressions.append(expression)

        if create:
            db.session.commit()

    @factory.post_generation  # type: ignore[misc]
    def _references(self: "Group", create: bool, extracted: list[Any], **kwargs: Any) -> None:
        if not create:
            return

        _validate_and_sync_component_references(
            self,
            ExpressionContext.build_expression_context(collection=self.form.collection, mode="interpolation"),
        )

        # Wipe the cache of questions on a form - because we're likely to be creating more forms/questions
        del self.form.cached_questions
        try:
            del self.form.cached_all_components
        except AttributeError:
            pass
        db.session.commit()


class _SubmissionEventFactory(SQLAlchemyModelFactory):
    class Meta:
        model = SubmissionEvent
        sqlalchemy_session_factory = lambda: db.session  # noqa: E731
        sqlalchemy_session_persistence = "commit"

    id = factory.LazyFunction(uuid4)
    key = SubmissionEventKey.FORM_RUNNER_FORM_COMPLETED
    submission = factory.SubFactory(_SubmissionFactory)
    form = factory.SubFactory(_FormFactory)
    created_by = factory.SubFactory(_UserFactory)


class _ExpressionFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Expression
        sqlalchemy_session_factory = lambda: db.session  # noqa: E731
        sqlalchemy_session_persistence = "commit"

    id = factory.LazyFunction(uuid4)
    question_id = factory.LazyAttribute(lambda o: o.question.id)
    question = factory.SubFactory(_QuestionFactory)
    context = factory.LazyFunction(dict)
    created_by = factory.SubFactory(_UserFactory)
    created_by_id = factory.LazyAttribute(lambda o: o.created_by.id)

    # todo: we could actually set this based on the question sub factory to make sure the default expression
    #       makes some kind of sense for the question type
    statement = factory.LazyFunction(_required)
    type_ = factory.LazyFunction(_required)


class _InvitationFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Invitation
        sqlalchemy_session_factory = lambda: db.session  # noqa: E731
        sqlalchemy_session_persistence = "commit"

    id = factory.LazyFunction(uuid4)
    email = factory.Faker("email")
    user_id = None
    user = None
    organisation_id = None
    organisation = None
    grant_id = None
    grant = None
    role = None
    expires_at_utc = factory.LazyFunction(lambda: datetime.datetime.now() + datetime.timedelta(days=7))
    claimed_at_utc = None

    class Params:
        has_organisation = factory.Trait(
            organisation_id=factory.LazyAttribute(lambda o: o.organisation.id),
            organisation=factory.SubFactory(_OrganisationFactory),
        )
        has_grant = factory.Trait(
            grant_id=factory.LazyAttribute(lambda o: o.grant.id),
            grant=factory.SubFactory(_GrantFactory),
        )
        is_claimed = factory.Trait(
            claimed_at_utc=factory.LazyFunction(lambda: datetime.datetime.now()),
            user=factory.SubFactory(_UserFactory),
            user_id=factory.LazyAttribute(lambda o: o.user.id if o.user else None),
        )
