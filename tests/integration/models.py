# mypy: disable-error-code="no-untyped-call"
# FactoryBoy doesn't have typing on its functions yet, so we disable that type check for this file only.

"""
A module containing FactoryBoy definitions for our DB models. Do not use these classes directly - they should be
accessed through fixtures such as `grant_factory`, which can ensure the Flask app and DB are properly instrumented
for transactional isolation.
"""

import datetime
import secrets
from uuid import uuid4

import factory
from flask import url_for

from app.common.data.base import QuestionDataType
from app.common.data.models import (
    CollectionSchema,
    Form,
    Grant,
    MagicLink,
    Organisation,
    Question,
    Section,
    User,
    UserRole,
)
from app.extensions import db


class _GrantFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = Grant
        sqlalchemy_session_factory = lambda: db.session  # noqa: E731
        sqlalchemy_session_persistence = "flush"

    id = factory.LazyFunction(uuid4)
    name = factory.Sequence(lambda n: "Grant %d" % n)


class _UserFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = User
        sqlalchemy_session_factory = lambda: db.session  # noqa: E731
        sqlalchemy_session_persistence = "flush"

    id = factory.LazyFunction(uuid4)
    email = factory.Faker("email")


class _OrganisationFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = Organisation
        sqlalchemy_session_factory = lambda: db.session  # noqa: E731

    id = factory.LazyFunction(uuid4)
    name = factory.Sequence(lambda n: "Organisation %d" % n)


class _UserRoleFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = UserRole
        sqlalchemy_session_factory = lambda: db.session  # noqa: E731
        sqlalchemy_session_persistence = "flush"

    id = factory.LazyFunction(uuid4)
    user_id = factory.LazyAttribute(lambda o: o.user.id)
    user = factory.SubFactory(_UserFactory)
    organisation_id = None
    organisation = None
    grant_id = None
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


class _MagicLinkFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = MagicLink
        sqlalchemy_session_factory = lambda: db.session  # noqa: E731
        sqlalchemy_session_persistence = "flush"

    id = factory.LazyFunction(uuid4)
    code = factory.LazyFunction(lambda: secrets.token_urlsafe(12))
    user_id = factory.LazyAttribute(lambda o: o.user.id)
    user = factory.SubFactory(_UserFactory)
    redirect_to_path = factory.LazyFunction(lambda: url_for("platform.list_grants"))
    expires_at_utc = factory.LazyFunction(lambda: datetime.datetime.now() + datetime.timedelta(minutes=15))
    claimed_at_utc = None


class _CollectionSchemaFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = CollectionSchema
        sqlalchemy_session_factory = lambda: db.session  # noqa: E731
        sqlalchemy_session_persistence = "flush"

    id = factory.LazyFunction(uuid4)
    name = factory.Sequence(lambda n: "Collection %d" % n)
    slug = factory.Sequence(lambda n: "collection-%d" % n)

    created_by_id = factory.LazyAttribute(lambda o: o.created_by.id)
    created_by = factory.SubFactory(_UserFactory)

    grant_id = factory.LazyAttribute(lambda o: "o.grant.id")
    grant = factory.SubFactory(_GrantFactory)


class _SectionFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = Section
        sqlalchemy_session_factory = lambda: db.session  # noqa: E731
        sqlalchemy_session_persistence = "flush"

    id = factory.LazyFunction(uuid4)
    title = factory.Sequence(lambda n: "Section %d" % n)
    order = factory.LazyAttribute(lambda o: len(o.collection_schema.sections))
    slug = factory.Sequence(lambda n: "section-%d" % n)

    collection_schema = factory.SubFactory(_CollectionSchemaFactory)
    collection_schema_id = factory.LazyAttribute(lambda o: o.collection_schema.id)


class _FormFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = Form
        sqlalchemy_session_factory = lambda: db.session  # noqa: E731
        sqlalchemy_session_persistence = "flush"

    id = factory.LazyFunction(uuid4)
    title = factory.Sequence(lambda n: "Form %d" % n)
    slug = factory.Sequence(lambda n: "form-%d" % n)
    order = factory.LazyAttribute(lambda o: len(o.section.forms))

    section = factory.SubFactory(_SectionFactory)
    section_id = factory.LazyAttribute(lambda o: o.section.id)


class _QuestionFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = Question
        sqlalchemy_session_factory = lambda: db.session  # noqa: E731

    id = factory.LazyFunction(uuid4)
    text = factory.Sequence(lambda n: "Question %d" % n)
    name = factory.Sequence(lambda n: "Question name %d" % n)
    slug = factory.Sequence(lambda n: "question-%d" % n)
    order = factory.LazyAttribute(lambda o: len(o.form.questions))
    data_type = QuestionDataType.TEXT

    form = factory.SubFactory(_FormFactory)
    form_id = factory.LazyAttribute(lambda o: o.form.id)
