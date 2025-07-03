import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, TypedDict

import click
from faker import Faker
from flask import current_app
from sqlalchemy.exc import NoResultFound

from app.common.data.base import BaseModel
from app.common.data.interfaces.grants import get_all_grants
from app.common.data.interfaces.temporary import delete_grant
from app.common.data.models import Collection, Expression, Form, Grant, Question, Section
from app.common.data.models_user import User
from app.developers import developers_blueprint
from app.extensions import db

export_path = Path.cwd() / "app" / "developers" / "data" / "grants.json"


def to_dict(instance: BaseModel) -> dict[str, Any]:
    return {col.name: getattr(instance, col.name) for col in instance.__table__.columns}


GrantExport = TypedDict(
    "GrantExport",
    {
        "grant": dict[str, Any],
        "collections": list[Any],
        "sections": list[Any],
        "forms": list[Any],
        "questions": list[Any],
        "expressions": list[Any],
    },
)
ExportData = TypedDict("ExportData", {"grants": list[GrantExport], "users": list[Any]})


@developers_blueprint.cli.command("export-grants", help="Export configured grants to consistently seed environments")
@click.argument("grant_ids", nargs=-1, type=click.UUID)
def export_grants(grant_ids: list[uuid.UUID]) -> None:
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

        for user in users:
            if user.id in [u["id"] for u in export_data["users"]]:
                continue

            user_data = to_dict(user)

            # Anonymise the user, but in a consistent way
            faker = Faker()
            faker.seed_instance(int(hashlib.md5(user_data["email"].encode()).hexdigest(), 16))
            user_data["email"] = faker.email(domain="test.communities.gov.uk")
            user_data["name"] = faker.name()

            export_data["users"].append(user_data)

    export_json = current_app.json.dumps(export_data, indent=2)
    with open(export_path, "w") as outfile:
        outfile.write(export_json + "\n")

    click.echo(f"Written {len(grants)} grants to {export_path}")


@developers_blueprint.cli.command("seed-grants", help="Load exported grants into the database")
def seed_grants() -> None:
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
            collection = Collection(**collection)
            db.session.add(collection)

        for section in grant_data["sections"]:
            section = Section(**section)
            db.session.add(section)

        for form in grant_data["forms"]:
            form = Form(**form)
            db.session.add(form)

        for question in grant_data["questions"]:
            question = Question(**question)
            db.session.add(question)

        for expression in grant_data["expressions"]:
            expression = Expression(**expression)
            db.session.add(expression)

    db.session.commit()
    click.echo(f"Loaded/synced {len(export_data['grants'])} grant(s) into the database.")
