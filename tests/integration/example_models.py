# mypy: disable-error-code="no-untyped-call"
# FactoryBoy doesn't have typing on its functions yet, so we disable that type check for this file only.

"""
This module contains exemplar FactoryBoy factories that should prove/demonstrate a few complex scenarios. We expect
this to be drawn upon as we add more real DB models to the app, and when sufficient real examples exist and this
module provides no unique/new information, this module should be deleted.
"""

import dataclasses
import decimal
import random
import uuid
from dataclasses import field
from uuid import uuid4

import factory


@dataclasses.dataclass
class ExamplePerson:
    id: uuid.UUID
    name: str
    age: int
    accounts: list["ExampleAccount"] = field(default_factory=list)


@dataclasses.dataclass
class ExampleAccount:
    owner: ExamplePerson
    balance: decimal.Decimal
    account_name: str


class ExamplePersonFactory(factory.Factory[ExamplePerson]):
    class Meta:
        model = ExamplePerson

    id = factory.LazyFunction(uuid4)
    name = factory.Faker("name")
    age = factory.LazyFunction(lambda: random.randrange(18, 100))

    @factory.post_generation
    def accounts(self, create, extract, **kwargs):  # type: ignore[no-untyped-def]
        if not create:
            return

        if extract is not None:
            for account in extract:
                self.accounts.append(account)
        else:
            # Create 2 accounts by default
            for _ in range(2):
                account = ExampleAccountFactory(owner=self)
                self.accounts.append(account)


class ExampleAccountFactory(factory.Factory[ExampleAccount]):
    class Meta:
        model = ExampleAccount

    owner = factory.SubFactory(ExamplePersonFactory)
    balance = factory.LazyFunction(lambda: decimal.Decimal(random.randrange(1, 100)))
    account_name = factory.LazyAttribute(lambda o: f"{o.owner.name}'s account" if o.owner else "Nobody's account")
