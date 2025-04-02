import uuid

from tests.integration.example_models import ExampleAccountFactory, ExamplePerson


def test_example_person(example_factories):
    person = example_factories.person.create()
    assert isinstance(person.id, uuid.UUID)
    assert person.name is not None
    assert 18 <= person.age <= 100
    assert len(person.accounts) == 2


def test_example_person_with_no_accounts(example_factories):
    person = example_factories.person.create(accounts=[])
    assert len(person.accounts) == 0


def test_example_person_with_custom_accounts(example_factories):
    person = example_factories.person.create(accounts=[ExampleAccountFactory(owner=None, balance=50.0)])
    assert len(person.accounts) == 1
    assert person.accounts[0].balance == 50.0


def test_example_person_with_custom_name(example_factories):
    person = example_factories.person.create(name="John Doe")
    assert person.name == "John Doe"


def test_example_account(example_factories):
    account = example_factories.account.create()
    assert isinstance(account.owner, ExamplePerson)
    assert 1 <= account.balance <= 100
    assert account.account_name == f"{account.owner.name}'s account"


def test_example_account_with_owner_name(example_factories):
    account = example_factories.account.create(owner__name="John Doe")
    assert account.owner.name == "John Doe"
