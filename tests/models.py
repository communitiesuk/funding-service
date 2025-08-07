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
    IntegerAnswer,
    MultipleChoiceFromListAnswer,
    SingleChoiceFromListAnswer,
    TextMultiLineAnswer,
    TextSingleLineAnswer,
    YesNoAnswer,
)
from app.common.data.models import (
    Collection,
    DataSource,
    DataSourceItem,
    DataSourceItemReference,
    Expression,
    Form,
    Grant,
    Group,
    Organisation,
    Question,
    Section,
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
from app.common.expressions.managed import AnyOf, BaseDataSourceManagedExpression, GreaterThan, Specifically
from app.constants import DEFAULT_SECTION_NAME
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
    def default_section(obj: Collection, create, extracted: bool = True, **kwargs):  # type: ignore
        # Our system automatically creates a default section for every collection that exists, so to closely match
        # the real system behaviour, our collection factory should do the same thing by default.

        if extracted is False:
            return

        if len(obj.sections) == 0:
            if create:
                obj.sections = [_SectionFactory.create(collection=obj, title=DEFAULT_SECTION_NAME)]
            else:
                obj.sections = [_SectionFactory.build(collection=obj, title=DEFAULT_SECTION_NAME)]  # type: ignore

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

        section = obj.sections[0]
        form = _FormFactory.create(section=section, title="Export test form", slug="export-test-form")

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
                str(q1.id): IntegerAnswer(40 if complete_question_2 else 20).get_value_for_submission()  # ty: ignore[missing-argument]
            }
            if complete_question_2:
                response_data[str(q2.id)] = IntegerAnswer(80).get_value_for_submission()  # ty: ignore[missing-argument]

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

        section = obj.sections[0]
        form = _FormFactory.create(section=section, title="Export test form", slug="export-test-form")

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
                    str(q1.id): IntegerAnswer(faker.Faker().random_int(min=0, max=60)).get_value_for_submission()  # ty: ignore[missing-argument]
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
        section = obj.sections[0]
        form = _FormFactory.create(section=section, title="Export test form", slug="export-test-form")

        # Assertion to remind us to add more question types here when we start supporting them
        assert len(QuestionDataType) == 8, "If you have added a new question type, please update this factory."

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
                            faker.Faker().random_number(2) if use_random_data else 123
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


class _SectionFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Section
        sqlalchemy_session_factory = lambda: db.session  # noqa: E731
        sqlalchemy_session_persistence = "commit"

    id = factory.LazyFunction(uuid4)
    title = factory.Sequence(lambda n: "Section %d" % n)
    order = factory.LazyAttribute(lambda o: len(o.collection.sections))
    slug = factory.Sequence(lambda n: "section-%d" % n)

    collection = factory.SubFactory(_CollectionFactory)
    collection_id = factory.LazyAttribute(lambda o: o.collection.id)


class _FormFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Form
        sqlalchemy_session_factory = lambda: db.session  # noqa: E731
        sqlalchemy_session_persistence = "commit"

    id = factory.LazyFunction(uuid4)
    title = factory.Sequence(lambda n: "Form %d" % n)
    slug = factory.Sequence(lambda n: "form-%d" % n)
    order = factory.LazyAttribute(lambda o: len(o.section.forms))

    section = factory.SubFactory(_SectionFactory)
    section_id = factory.LazyAttribute(lambda o: o.section.id)


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
    # todo: assumes flat question factories not nested in groups
    order = factory.LazyAttribute(lambda o: len(o.form.components))
    data_type = QuestionDataType.TEXT_SINGLE_LINE

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

    presentation_options = factory.LazyFunction(lambda: QuestionPresentationOptions())

    @factory.post_generation  # type: ignore[misc]
    def expressions(self, create: bool, extracted: list[Any], **kwargs: Any) -> None:
        if not extracted:
            return
        for expression in extracted:
            expression.question_id = self.id

            if (
                isinstance(expression.managed, BaseDataSourceManagedExpression)
                and expression.managed.referenced_question.data_source
            ):
                # Longwindedly doing this via ORM to avoid additional DB queries when we switch the data export
                # performance tests back on
                all_referenced_question_data_source_items = expression.managed.referenced_question.data_source.items
                expression_referenced_data_source_items = expression.managed.referenced_data_source_items
                referenced_items = [
                    item
                    for item in all_referenced_question_data_source_items
                    if any(
                        item.key == expression_ref_item["key"]
                        for expression_ref_item in expression_referenced_data_source_items
                    )
                ]
                expression.data_source_item_references = [
                    DataSourceItemReference(expression_id=expression.id, data_source_item_id=item.id)
                    for item in referenced_items
                ]

            db.session.add(expression)
            self.expressions.append(expression)

        if create:
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
    # todo: assumes flat question factories not nested in groups
    order = factory.LazyAttribute(lambda o: len(o.form.components))

    form = factory.SubFactory(_FormFactory)
    form_id = factory.LazyAttribute(lambda o: o.form.id)

    @factory.post_generation  # type: ignore[misc]
    def expressions(self, create: bool, extracted: list[Any], **kwargs: Any) -> None:
        if not extracted:
            return
        for expression in extracted:
            expression.question_id = self.id

            if (
                isinstance(expression.managed, BaseDataSourceManagedExpression)
                and expression.managed.referenced_question.data_source
            ):
                # Longwindedly doing this via ORM to avoid additional DB queries when we switch the data export
                # performance tests back on
                all_referenced_question_data_source_items = expression.managed.referenced_question.data_source.items
                expression_referenced_data_source_items = expression.managed.referenced_data_source_items
                referenced_items = [
                    item
                    for item in all_referenced_question_data_source_items
                    if any(
                        item.key == expression_ref_item["key"]
                        for expression_ref_item in expression_referenced_data_source_items
                    )
                ]
                expression.data_source_item_references = [
                    DataSourceItemReference(expression_id=expression.id, data_source_item_id=item.id)
                    for item in referenced_items
                ]

            db.session.add(expression)
            self.expressions.append(expression)

        if create:
            db.session.commit()


class _SubmissionEventFactory(SQLAlchemyModelFactory):
    class Meta:
        model = SubmissionEvent
        sqlalchemy_session_factory = lambda: db.session  # noqa: E731
        sqlalchemy_session_persistence = "commit"

    id = factory.LazyFunction(uuid4)
    key = SubmissionEventKey.FORM_RUNNER_FORM_COMPLETED
    submission = factory.SubFactory(_SubmissionFactory)
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
    type = factory.LazyFunction(_required)


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
