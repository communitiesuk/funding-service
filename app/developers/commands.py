import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, TypedDict

import click
from flask import current_app
from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy.exc import NoResultFound

from app.common.data.base import BaseModel
from app.common.data.interfaces.grants import get_all_grants
from app.common.data.interfaces.temporary import delete_grant
from app.common.data.models import (
    Collection,
    DataSource,
    DataSourceItem,
    DataSourceItemReference,
    Expression,
    Form,
    Grant,
    Question,
    Section,
)
from app.common.data.models_user import User
from app.common.data.types import QuestionPresentationOptions
from app.developers import developers_blueprint
from app.extensions import db

export_path = Path.cwd() / "app" / "developers" / "data" / "grants.json"


def to_dict(instance: BaseModel) -> dict[str, Any]:
    return {
        col.name: (field.model_dump(mode="json") if isinstance(field, PydanticBaseModel) else field)
        for col in instance.__table__.columns
        if (field := getattr(instance, col.name)) is not None and col.name not in {"created_at_utc", "updated_at_utc"}
    }


GrantExport = TypedDict(
    "GrantExport",
    {
        "grant": dict[str, Any],
        "collections": list[Any],
        "sections": list[Any],
        "forms": list[Any],
        "questions": list[Any],
        "expressions": list[Any],
        "data_sources": list[Any],
        "data_source_items": list[Any],
        "data_source_item_references": list[Any],
    },
)
ExportData = TypedDict("ExportData", {"grants": list[GrantExport], "users": list[Any]})


@developers_blueprint.cli.command("export-grants", help="Export configured grants to consistently seed environments")
@click.argument("grant_ids", nargs=-1, type=click.UUID)
def export_grants(grant_ids: list[uuid.UUID]) -> None:  # noqa: C901
    from faker import Faker

    if not export_path.exists():
        raise RuntimeError(
            f"Could not find the exported data at {export_path}. "
            f"Make sure you're running this command from the root of the repository."
        )

    if len(grant_ids) == 0:
        with open(export_path) as infile:
            previous_export_data = json.load(infile)
        grant_ids = [uuid.UUID(grant_data["grant"]["id"]) for grant_data in previous_export_data["grants"]]
        click.echo(
            f"No grant IDs provided. "
            f"Refreshing export data for previously exported grants: {','.join(str(g) for g in grant_ids)}\n"
        )

    all_grants = get_all_grants()
    grants = [grant for grant in all_grants if grant.id in grant_ids]
    missing_grants = [str(grant_id) for grant_id in grant_ids if grant_id not in [grant.id for grant in grants]]
    if missing_grants:
        click.echo(f"Could not find the following grant(s): {','.join(missing_grants)}")
        exit(1)

    export_data: ExportData = {
        "grants": [],
        "users": [],
    }

    for grant in grants:
        grant_export: GrantExport = {
            "grant": to_dict(grant),
            "collections": [],
            "sections": [],
            "forms": [],
            "questions": [],
            "expressions": [],
            "data_sources": [],
            "data_source_items": [],
            "data_source_item_references": [],
        }

        export_data["grants"].append(grant_export)
        users = set()

        for collection in grant.collections:
            grant_export["collections"].append(to_dict(collection))
            users.add(collection.created_by)

            for section in collection.sections:
                grant_export["sections"].append(to_dict(section))

                for form in section.forms:
                    grant_export["forms"].append(to_dict(form))

                    for question in form.questions:
                        grant_export["questions"].append(to_dict(question))

                        for expression in question.expressions:
                            grant_export["expressions"].append(to_dict(expression))
                            users.add(expression.created_by)

                        if question.data_source:
                            grant_export["data_sources"].append(to_dict(question.data_source))

                            for data_source_item in question.data_source.items:
                                grant_export["data_source_items"].append(to_dict(data_source_item))

                                for reference in data_source_item.references:
                                    grant_export["data_source_item_references"].append(to_dict(reference))

        for user in users:
            if user.id in [u["id"] for u in export_data["users"]]:
                continue

            user_data = to_dict(user)

            # Anonymise the user, but in a consistent way
            faker = Faker()
            faker.seed_instance(int(hashlib.md5(str(user_data["id"]).encode()).hexdigest(), 16))
            user_data["email"] = faker.email(domain="test.communities.gov.uk")
            user_data["name"] = faker.name()

            export_data["users"].append(user_data)
        export_data["users"].sort(key=lambda u: u["email"])

    export_json = current_app.json.dumps(export_data, indent=2)
    with open(export_path, "w") as outfile:
        outfile.write(export_json + "\n")

    click.echo(f"Written {len(grants)} grants to {export_path}")


@developers_blueprint.cli.command("seed-grants", help="Load exported grants into the database")
def seed_grants() -> None:  # noqa: C901
    with open(export_path) as infile:
        export_data = json.load(infile)

    for user in export_data["users"]:
        user = User(**user)
        db.session.merge(user)
    db.session.flush()

    for grant_data in export_data["grants"]:
        try:
            delete_grant(grant_data["grant"]["id"])
            db.session.commit()
        except NoResultFound:
            pass

        grant = Grant(**grant_data["grant"])
        db.session.add(grant)

        for collection in grant_data["collections"]:
            collection["id"] = uuid.UUID(collection["id"])
            collection = Collection(**collection)
            db.session.add(collection)

        for section in grant_data["sections"]:
            section["id"] = uuid.UUID(section["id"])
            section = Section(**section)
            db.session.add(section)

        for form in grant_data["forms"]:
            form["id"] = uuid.UUID(form["id"])
            form = Form(**form)
            db.session.add(form)

        for question in grant_data["questions"]:
            question["id"] = uuid.UUID(question["id"])
            if "presentation_options" in question:
                question["presentation_options"] = QuestionPresentationOptions(**question["presentation_options"])

            question = Question(**question)
            db.session.add(question)

        for expression in grant_data["expressions"]:
            expression["id"] = uuid.UUID(expression["id"])
            expression = Expression(**expression)
            db.session.add(expression)

        for data_source in grant_data["data_sources"]:
            data_source["id"] = uuid.UUID(data_source["id"])
            data_source = DataSource(**data_source)
            db.session.add(data_source)

        for data_source_item in grant_data["data_source_items"]:
            data_source_item["id"] = uuid.UUID(data_source_item["id"])
            data_source_item = DataSourceItem(**data_source_item)
            db.session.add(data_source_item)

        for data_source_item_reference in grant_data["data_source_item_references"]:
            data_source_item_reference["id"] = uuid.UUID(data_source_item_reference["id"])
            data_source_item_reference = DataSourceItemReference(**data_source_item_reference)
            db.session.add(data_source_item_reference)

    db.session.commit()
    click.echo(f"Loaded/synced {len(export_data['grants'])} grant(s) into the database.")


@developers_blueprint.cli.command(
    "seed-grants-many-submissions", help="Load grants with 100 random submissions into the database"
)
def seed_grants_many_submissions() -> None:
    """
    This uses the test factories to seed 100 submissions for each of two test grants - one with conditional questions,
    and one without. This is useful for testing the performance of the application with a large number of submissions.

    Note: It may fail due to conflicts on the user email in the database, as faker seems to have a fixed set of
    possible emails and the more there are, the more likely we are to hit a conflict. If this happens, you can clear
    down your local database and run this command again to create the grants.
    """
    from tests.models import _CollectionFactory, _GrantFactory

    grant_names = [
        "Test Grant with 100 submissions - non-conditional questions",
        "Test Grant with 100 submissions - conditional questions",
    ]
    for name in grant_names:
        try:
            grant = db.session.query(Grant).filter(Grant.name == name).one()
            delete_grant(grant.id)
            db.session.commit()
        except NoResultFound:
            pass

    grant = _GrantFactory.create(name="Test Grant with 100 submissions - non-conditional questions")
    _CollectionFactory.create(
        grant=grant,
        name="Test Collection with 100 submissions",
        create_completed_submissions_each_question_type__test=100,
    )
    grant = _GrantFactory.create(name="Test Grant with 100 submissions - conditional questions")
    _CollectionFactory.create(
        grant=grant,
        name="Test Collection with 100 submissions",
        create_completed_submissions_conditional_question_random__test=100,
    )
