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
from typing import Any
from uuid import uuid4

import factory
import factory.fuzzy
import faker
from factory.alchemy import SQLAlchemyModelFactory
from flask import url_for

from app.common.collections.types import Integer, SingleChoiceFromList, TextMultiLine, TextSingleLine, YesNo
from app.common.data.models import (
    Collection,
    DataSource,
    DataSourceItem,
    Expression,
    Form,
    Grant,
    Organisation,
    Question,
    Section,
    Submission,
    SubmissionEvent,
)
from app.common.data.models_user import Invitation, MagicLink, User, UserRole
from app.common.data.types import QuestionDataType, SubmissionEventKey, SubmissionModeEnum, SubmissionStatusEnum
from app.extensions import db


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

    created_by_id = factory.LazyAttribute(lambda o: o.created_by.id)
    created_by = factory.SubFactory(_UserFactory)

    grant_id = factory.LazyAttribute(lambda o: "o.grant.id")
    grant = factory.SubFactory(_GrantFactory)

    @factory.post_generation  # type: ignore
    def create_completed_submissions(  # type: ignore
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
        section = _SectionFactory.create(collection=obj)
        form = _FormFactory.create(section=section)

        # Assertion to remind us to add more question types here when we start supporting them
        assert len(QuestionDataType) == 7, "If you have added a new question type, please update this factory."

        # Create a question of each supported type
        q1 = _QuestionFactory.create(form=form, data_type=QuestionDataType.TEXT_SINGLE_LINE, text="What is your name?")
        q2 = _QuestionFactory.create(form=form, data_type=QuestionDataType.TEXT_MULTI_LINE, text="What is your quest?")
        q3 = _QuestionFactory.create(form=form, data_type=QuestionDataType.INTEGER, text="What is your age?")
        q4 = _QuestionFactory.create(form=form, data_type=QuestionDataType.YES_NO, text="Do you like cheese?")
        q5 = _QuestionFactory.create(form=form, data_type=QuestionDataType.RADIOS, text="What is the best option?")
        q6 = _QuestionFactory.create(form=form, data_type=QuestionDataType.EMAIL, text="What is your email address?")
        q7 = _QuestionFactory.create(form=form, data_type=QuestionDataType.URL, text="What is your website address?")

        def _create_submission_of_type(submission_mode: SubmissionModeEnum, count: int) -> None:
            for _ in range(0, count):
                _SubmissionFactory.create(
                    collection=obj,
                    mode=submission_mode,
                    data={
                        str(q1.id): TextSingleLine(
                            faker.Faker().name() if use_random_data else "test name"
                        ).get_value_for_submission(),
                        str(q2.id): TextMultiLine(
                            "\r\n".join(faker.Faker().sentences(nb=3))
                            if use_random_data
                            else "Line 1\r\nline2\r\nline 3"
                        ).get_value_for_submission(),
                        str(q3.id): Integer(
                            faker.Faker().random_number(2) if use_random_data else 123
                        ).get_value_for_submission(),
                        str(q4.id): YesNo(
                            random.choice([True, False]) if use_random_data else True
                        ).get_value_for_submission(),  # ty: ignore[missing-argument]
                        str(q5.id): SingleChoiceFromList(
                            key=q5.data_source.items[0].key, label=q5.data_source.items[0].label
                        ).get_value_for_submission(),
                        str(q6.id): TextSingleLine(faker.Faker().email()).get_value_for_submission(),
                        str(q7.id): TextSingleLine(faker.Faker().url()).get_value_for_submission(),
                    },
                    status=SubmissionStatusEnum.COMPLETED,
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


class _SubmissionFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Submission
        sqlalchemy_session_factory = lambda: db.session  # noqa: E731
        sqlalchemy_session_persistence = "commit"

    id = factory.LazyFunction(uuid4)
    mode = SubmissionModeEnum.TEST
    data = factory.LazyFunction(dict)
    status = SubmissionStatusEnum.NOT_STARTED

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
    order = factory.LazyAttribute(lambda o: len(o.form.questions))
    data_type = QuestionDataType.TEXT_SINGLE_LINE

    form = factory.SubFactory(_FormFactory)
    form_id = factory.LazyAttribute(lambda o: o.form.id)

    needs_data_source = factory.LazyAttribute(lambda o: o.data_type == QuestionDataType.RADIOS)
    data_source = factory.Maybe(
        "needs_data_source",
        yes_declaration=factory.RelatedFactory(_DataSourceFactory, factory_related_name="question"),
        no_declaration=None,
    )

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
