from typing import TYPE_CHECKING, Sequence

import click

from app.common.data import interfaces
from app.common.data.interfaces.temporary import delete_grant
from app.common.data.types import QuestionDataType
from app.developers import developers_blueprint

if TYPE_CHECKING:
    from app.common.data.models import Grant


def _seed_chessboards_in_parks(grants: Sequence["Grant"]) -> None:
    grant_name = "Chessboards in parks"

    if grant := next((grant for grant in grants if grant.name == grant_name), None):
        click.echo(f"Grant '{grant_name}' already exists; recreating it.")
        delete_grant(grant.id)

    from tests.integration.models import (
        _CollectionSchemaFactory,
        _FormFactory,
        _GrantFactory,
        _QuestionFactory,
        _SectionFactory,
    )

    grant = _GrantFactory.create(name=grant_name)

    schema = _CollectionSchemaFactory.create(
        grant=grant, name="Report on chessboards in parks", slug="report-on-chessboards-in-parks"
    )

    s = _SectionFactory.create(collection_schema=schema, title="About the park", slug="about-the-park")

    f = _FormFactory.create(section=s, title="Park information")

    _QuestionFactory.create(form=f, text="What is the name of the park?", data_type=QuestionDataType.TEXT_SINGLE_LINE)
    _QuestionFactory.create(form=f, text="How many chessboards are there?", data_type=QuestionDataType.INTEGER)
    f = _FormFactory.create(section=s, title="Visitor information")
    _QuestionFactory.create(
        form=f, text="How many visitors were there in the last reporting period?", data_type=QuestionDataType.INTEGER
    )

    s = _SectionFactory.create(collection_schema=schema, title="About the chess", slug="about-the-chess")
    f = _FormFactory.create(section=s, title="Information about the chess games played")
    _QuestionFactory.create(
        form=f,
        text="Describe the most exciting game played in the last reporting period.",
        data_type=QuestionDataType.TEXT_MULTI_LINE,
    )

    click.echo(f"Seeded the ‘{grant_name}’ grant.")


@developers_blueprint.cli.command("seed-grants", help="Seed exemplar grants to aid development and testing.")
def seed_grants() -> None:
    grants = interfaces.grants.get_all_grants()

    _seed_chessboards_in_parks(grants)
