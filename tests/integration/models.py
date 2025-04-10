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

from app.common.data.models import Grant, MagicLink, User
from app.extensions import db


class _GrantFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = Grant
        sqlalchemy_session_factory = lambda: db.session  # noqa: E731

    id = factory.LazyFunction(uuid4)
    name = factory.Sequence(lambda n: "Grant %d" % n)


class _UserFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = User
        sqlalchemy_session_factory = lambda: db.session  # noqa: E731

    id = factory.LazyFunction(uuid4)
    email = factory.Faker("email")


class _MagicLinkFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = MagicLink
        sqlalchemy_session_factory = lambda: db.session  # noqa: E731

    id = factory.LazyFunction(uuid4)
    code = factory.LazyFunction(lambda: secrets.token_urlsafe(12))
    user_id = factory.LazyAttribute(lambda o: "o.user.id")
    user = factory.SubFactory(_UserFactory)
    redirect_to_path = factory.LazyFunction(lambda: url_for("platform.list_grants"))
    expires_at_utc = factory.LazyFunction(lambda: datetime.datetime.now() + datetime.timedelta(minutes=15))
    claimed_at_utc = None
