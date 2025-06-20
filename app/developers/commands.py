from typing import TYPE_CHECKING, Sequence, TypedDict

import click

from app.common.data import interfaces
from app.common.data.interfaces.temporary import delete_grant
from app.common.data.types import QuestionDataType
from app.developers import developers_blueprint

if TYPE_CHECKING:
    from app.common.data.models import Grant


class QuestionSpec(TypedDict):
    text: str
    data_type: QuestionDataType


class FormSpec(TypedDict):
    title: str
    questions: list[QuestionSpec]


class SectionSpec(TypedDict):
    title: str
    slug: str
    forms: list[FormSpec]


def _seed_grant(
    grants: Sequence["Grant"], grant_name: str, collection_name: str, collection_slug: str, sections: list[SectionSpec]
) -> None:
    from tests.models import (
        _CollectionFactory,
        _FormFactory,
        _GrantFactory,
        _QuestionFactory,
        _SectionFactory,
    )

    if grant := next((grant for grant in grants if grant.name == grant_name), None):
        click.echo(f"Grant '{grant_name}' already exists; recreating it.")
        delete_grant(grant.id)

    grant = _GrantFactory.create(name=grant_name)
    collection = _CollectionFactory.create(grant=grant, name=collection_name, slug=collection_slug)

    for section_data in sections:
        section = _SectionFactory.create(collection=collection, title=section_data["title"], slug=section_data["slug"])
        for form_data in section_data["forms"]:
            form = _FormFactory.create(section=section, title=form_data["title"])
            for question in form_data["questions"]:
                _QuestionFactory.create(form=form, text=question["text"], data_type=question["data_type"])

    click.echo(f"Seeded the ‘{grant_name}’ grant.")


def _seed_chessboards_in_parks(grants: Sequence["Grant"]) -> None:
    _seed_grant(
        grants,
        grant_name="Chessboards in parks",
        collection_name="Report on chessboards in parks",
        collection_slug="report-on-chessboards-in-parks",
        sections=[
            {
                "title": "About the park",
                "slug": "about-the-park",
                "forms": [
                    {
                        "title": "Park information",
                        "questions": [
                            {"text": "What is the name of the park?", "data_type": QuestionDataType.TEXT_SINGLE_LINE},
                            {"text": "How many chessboards are there?", "data_type": QuestionDataType.INTEGER},
                        ],
                    },
                    {
                        "title": "Visitor information",
                        "questions": [
                            {
                                "text": "How many visitors were there in the last reporting period?",
                                "data_type": QuestionDataType.INTEGER,
                            },
                        ],
                    },
                ],
            },
            {
                "title": "About the chess",
                "slug": "about-the-chess",
                "forms": [
                    {
                        "title": "Information about the chess games played",
                        "questions": [
                            {
                                "text": "Describe the most exciting game played in the last reporting period.",
                                "data_type": QuestionDataType.TEXT_MULTI_LINE,
                            }
                        ],
                    }
                ],
            },
        ],
    )


def _seed_playgrounds_in_parks(grants: Sequence["Grant"]) -> None:
    _seed_grant(
        grants,
        grant_name="Playgrounds in Parks",
        collection_name="Report on playgrounds in parks",
        collection_slug="report-on-playgrounds-in-parks",
        sections=[
            {
                "title": "Playground Overview",
                "slug": "playground-overview",
                "forms": [
                    {
                        "title": "Playground Details",
                        "questions": [
                            {"text": "What is the name of the park?", "data_type": QuestionDataType.TEXT_SINGLE_LINE},
                            {
                                "text": "How many pieces of playground equipment are there?",
                                "data_type": QuestionDataType.INTEGER,
                            },
                            {
                                "text": "Is the playground accessible to children with disabilities?",
                                "data_type": QuestionDataType.INTEGER,
                            },
                        ],
                    }
                ],
            },
            {
                "title": "Usage & Maintenance",
                "slug": "usage-maintenance",
                "forms": [
                    {
                        "title": "Usage Statistics",
                        "questions": [
                            {
                                "text": "How many children used the playground last month?",
                                "data_type": QuestionDataType.INTEGER,
                            },
                        ],
                    },
                    {
                        "title": "Maintenance Notes",
                        "questions": [
                            {
                                "text": "Were there any safety incidents reported?",
                                "data_type": QuestionDataType.INTEGER,
                            },
                            {
                                "text": """
                                Describe any maintenance activities or issues during the last reporting period.
                                """,
                                "data_type": QuestionDataType.TEXT_MULTI_LINE,
                            },
                        ],
                    },
                ],
            },
        ],
    )


def _seed_picnic_areas_in_parks(grants: Sequence["Grant"]) -> None:
    _seed_grant(
        grants,
        grant_name="Picnic Areas in Parks",
        collection_name="Report on picnic areas in parks",
        collection_slug="report-on-picnic-areas-in-parks",
        sections=[
            {
                "title": "Park Overview",
                "slug": "park-overview",
                "forms": [
                    {
                        "title": "General Park Information",
                        "questions": [
                            {"text": "What is the name of the park?", "data_type": QuestionDataType.TEXT_SINGLE_LINE},
                            {"text": "How many picnic tables are available?", "data_type": QuestionDataType.INTEGER},
                        ],
                    },
                    {
                        "title": "Usage Information",
                        "questions": [
                            {
                                "text": "How many families used the picnic area last month?",
                                "data_type": QuestionDataType.INTEGER,
                            },
                        ],
                    },
                ],
            },
            {
                "title": "Feedback",
                "slug": "feedback",
                "forms": [
                    {
                        "title": "Public Feedback on Picnic Areas",
                        "questions": [
                            {
                                "text": "Share any notable comments or stories from visitors about the picnic areas.",
                                "data_type": QuestionDataType.TEXT_MULTI_LINE,
                            }
                        ],
                    }
                ],
            },
        ],
    )


@developers_blueprint.cli.command("seed-grants", help="Seed exemplar grants to aid development and testing.")
def seed_grants() -> None:
    grants = interfaces.grants.get_all_grants()

    _seed_chessboards_in_parks(grants)
    _seed_picnic_areas_in_parks(grants)
    _seed_playgrounds_in_parks(grants)
