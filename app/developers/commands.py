import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, TypedDict, cast

import click
from flask import current_app
from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy import delete, inspect, or_, select
from sqlalchemy.exc import NoResultFound

from app.common.data.base import BaseModel
from app.common.data.interfaces.collections import _validate_and_sync_component_references
from app.common.data.interfaces.grants import get_all_grants
from app.common.data.interfaces.temporary import delete_grant
from app.common.data.models import (
    Collection,
    Component,
    ComponentReference,
    DataSource,
    DataSourceItem,
    Expression,
    Form,
    Grant,
    GrantRecipient,
    Group,
    Organisation,
    Question,
)
from app.common.data.models_user import User, UserRole
from app.common.data.types import ComponentType, QuestionPresentationOptions
from app.common.expressions import ExpressionContext
from app.developers import developers_blueprint
from app.extensions import db

export_path = Path.cwd() / "app" / "developers" / "data" / "grants.json"


def to_dict(instance: BaseModel, exclude: list[str] | None = None) -> dict[str, Any]:
    return {
        prop.key: (field.model_dump(mode="json", exclude_none=True) if isinstance(field, PydanticBaseModel) else field)
        for prop in inspect(instance.__class__).column_attrs
        if (field := getattr(instance, prop.key)) is not None
        and prop.columns[0].name not in {"created_at_utc", "updated_at_utc"}
        and not prop.key.startswith("_")
        and (exclude is None or prop.key not in exclude)
    }


GrantExport = TypedDict(
    "GrantExport",
    {
        "grant": dict[str, Any],
        "grant_recipients": list[Any],
        "collections": list[Any],
        "forms": list[Any],
        # intentionally leaving this as questions for now to avoid
        # transitioning to a new schema, we can change this to components for
        # clarity when everything is settled if we need to
        "questions": list[Any],
        "expressions": list[Any],
        "data_sources": list[Any],
        "data_source_items": list[Any],
        "component_references": list[Any],
    },
)
ExportData = TypedDict(
    "ExportData",
    {
        "grants": list[GrantExport],
        "users": list[Any],
        "user_roles": list[Any],
        "organisations": list[Any],
    },
)


def _sort_export_data_in_place(export_data: ExportData) -> None:
    export_data["users"].sort(key=lambda u: u["email"])
    export_data["user_roles"].sort(
        key=lambda ur: (ur["user_id"], ur.get("organisation_id"), ur.get("grant_id"), ur["role"])
    )

    # Grant-managing orgs first, then by name
    export_data["organisations"].sort(key=lambda o: (not o["can_manage_grants"], o["name"]))

    for grants_data in export_data["grants"]:
        for k, v in grants_data.items():
            if k == "grant":
                continue

            v.sort(key=lambda u: u["id"])  # type: ignore[attr-defined]


def __replace_id(export_data: ExportData, old_id: str, new_id: str) -> ExportData:
    export_json = current_app.json.dumps(export_data)
    export_json = export_json.replace(old_id, new_id)
    return cast(ExportData, current_app.json.loads(export_json))


def _handle_org_ids_for_export(export_data: ExportData) -> ExportData:
    """When exporting organisations, the MHCLG org doesn't have a stable internal ID, so let's switch it to a stable
    representation.
    """
    for organisation in export_data["organisations"]:
        if organisation["can_manage_grants"] is True:
            export_data = __replace_id(export_data, str(organisation["id"]), f"<UUID:{organisation['external_id']}>")

    return export_data


def _import_organisations_and_handle_org_ids(export_data: ExportData) -> ExportData:
    """Try to map organisations in the export to any organisations that exist in the database already.

    This lets the import work without having to start with an empty database each time.

    We do the inverse mapping from above to convert MHCLG's stable org identifier back to a PK ID where needed.
    """
    for organisation_data in export_data["organisations"]:
        matched_org: Organisation | None = db.session.scalar(
            select(Organisation).where(
                (Organisation.name == organisation_data["name"])
                if organisation_data["can_manage_grants"]
                else or_(
                    Organisation.id == organisation_data["id"],
                    Organisation.name == organisation_data["name"],
                )
            )
        )
        if matched_org:
            export_data = __replace_id(export_data, organisation_data["id"], str(matched_org.id))
        else:
            matched_org = Organisation(**organisation_data)
            db.session.add(matched_org)
            db.session.flush()

        export_data = __replace_id(export_data, f"<UUID:{organisation_data['external_id']}>", str(matched_org.id))

    return export_data


@developers_blueprint.cli.command("export-grants", help="Export configured grants to consistently seed environments")
@click.argument("grant_ids", nargs=-1, type=click.UUID)
@click.option("--output", type=click.Choice(["file", "stdout"]), default="file")
def export_grants(grant_ids: list[uuid.UUID], output: str) -> None:  # noqa: C901
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
        "user_roles": [],
        "organisations": [],
    }

    for org in db.session.query(Organisation).where(Organisation.can_manage_grants.is_(True)).all():
        export_data["organisations"].append(to_dict(org))

    users = set()
    for grant in grants:
        # Don't persist `grant.organisation_id`, as the UUID for MHCLG is not static
        grant_export: GrantExport = {
            "grant": to_dict(grant, exclude=["organisation_id"]),
            "grant_recipients": [],
            "collections": [],
            "forms": [],
            "questions": [],
            "expressions": [],
            "data_sources": [],
            "data_source_items": [],
            "component_references": [],
        }

        export_data["grants"].append(grant_export)

        for collection in grant.collections:
            grant_export["collections"].append(to_dict(collection))
            users.add(collection.created_by)

            for form in collection.forms:
                grant_export["forms"].append(to_dict(form))

                for component in form.components:
                    add_all_components_flat(component, users, grant_export)

        for gr in grant.grant_recipients:
            if gr.organisation_id not in [o["id"] for o in export_data["organisations"]]:
                export_data["organisations"].append(to_dict(gr.organisation))

            grant_export["grant_recipients"].append(to_dict(gr))

            for user in gr.users:
                users.add(user)

        for user in grant.grant_team_users:
            users.add(user)

    org_ids = {org["id"] for org in export_data["organisations"]}
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

        for role in user.roles:
            if (role.organisation_id and role.organisation_id not in org_ids) or (
                role.grant_id and role.grant_id not in grant_ids
            ):
                continue

            export_data["user_roles"].append(to_dict(role))

    _sort_export_data_in_place(export_data)
    export_data = _handle_org_ids_for_export(export_data)

    export_json = current_app.json.dumps(export_data, indent=2)
    match output:
        case "file":
            with open(export_path, "w") as outfile:
                outfile.write(export_json + "\n")

            click.echo(f"Written {len(grants)} grants to {export_path}")

        case "stdout":
            click.echo(f"Writing {len(grants)} grants to stdout")
            click.echo("\n\n\n")
            click.echo(export_json)
            click.echo("\n\n\n")
            click.echo(f"Written {len(grants)} grants to stdout")


@developers_blueprint.cli.command("seed-grants", help="Load exported grants into the database")
def seed_grants() -> None:  # noqa: C901
    with open(export_path) as infile:
        raw_export_json = infile.read()
        export_data: ExportData = json.loads(raw_export_json)

    for user in export_data["users"]:
        user = User(**user)
        db.session.merge(user)
    db.session.flush()

    export_data = _import_organisations_and_handle_org_ids(export_data)

    # Lookup MHCLG (the only 'grant managing' org) in the DB and re-associate all grants to it; we don't freeze
    # its org UUID so it will change every time.
    grant_owning_org = db.session.query(Organisation).filter_by(can_manage_grants=True).one()
    db.session.flush()

    for grant_data in export_data["grants"]:
        grant_data["grant"]["id"] = uuid.UUID(grant_data["grant"]["id"])

        try:
            db.session.execute(delete(GrantRecipient).where(GrantRecipient.grant_id == grant_data["grant"]["id"]))
            delete_grant(grant_data["grant"]["id"])
            db.session.flush()
        except NoResultFound:
            pass

        grant = Grant(**grant_data["grant"], organisation=grant_owning_org)
        db.session.add(grant)

        for grant_recipient in grant_data["grant_recipients"]:
            grant_recipient["id"] = uuid.UUID(grant_recipient["id"])
            grant_recipient["organisation_id"] = uuid.UUID(grant_recipient["organisation_id"])
            grant_recipient["grant_id"] = uuid.UUID(grant_recipient["grant_id"])
            db.session.add(GrantRecipient(**grant_recipient))

        for collection in grant_data["collections"]:
            collection["id"] = uuid.UUID(collection["id"])
            collection = Collection(**collection)
            db.session.add(collection)

        for form in grant_data["forms"]:
            form["id"] = uuid.UUID(form["id"])
            form = Form(**form)
            db.session.add(form)

        for component in grant_data["questions"]:
            component["id"] = uuid.UUID(component["id"])
            if "presentation_options" in component:
                component["presentation_options"] = QuestionPresentationOptions(**component["presentation_options"])

            match component["type"]:
                case ComponentType.QUESTION:
                    component = Question(**component)
                case ComponentType.GROUP:
                    component = Group(**component)
                case _:
                    raise Exception(f"Seed command does not know the type {component.type}")
            db.session.add(component)

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

        for component_reference in grant_data["component_references"]:
            component_reference["id"] = uuid.UUID(component_reference["id"])
            component_reference = ComponentReference(**component_reference)
            db.session.add(component_reference)

    for role in export_data["user_roles"]:
        role["id"] = uuid.UUID(role["id"])
        db_role = db.session.scalar(
            select(UserRole).where(
                UserRole.user_id == role.get("user_id"),
                UserRole.organisation_id == role.get("organisation_id"),
                UserRole.grant_id == role.get("grant_id"),
            )
        )
        if db_role:
            db_role.role = role["role"]
            db_role.permissions = [role["role"]]
        else:
            role_data = {**role, "permissions": [role["role"]]}
            db_role = UserRole(**role_data)
            db.session.add(db_role)

        db.session.flush()
        db.session.refresh(db_role)

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


def add_all_components_flat(component: Component, users: set[User], grant_export: GrantExport) -> None:
    grant_export["questions"].append(to_dict(component))

    for expression in component.expressions:
        grant_export["expressions"].append(to_dict(expression))
        users.add(expression.created_by)

    if component.data_source:
        grant_export["data_sources"].append(to_dict(component.data_source))

        for data_source_item in component.data_source.items:
            grant_export["data_source_items"].append(to_dict(data_source_item))

    for component_reference in component.owned_component_references:
        grant_export["component_references"].append(to_dict(component_reference))

    if component.is_group:
        for sub_component in component.components:
            add_all_components_flat(sub_component, users, grant_export)


@developers_blueprint.cli.command(
    "sync-component-references", help="Scan all components and expressions and denormalise their references into the DB"
)
def sync_component_references() -> None:
    click.echo("Syncing all component references.")

    count = db.session.query(ComponentReference).count()
    click.echo(f"Deleting {count} component references.")

    db.session.execute(delete(ComponentReference))

    for component in db.session.query(Component).all():
        _validate_and_sync_component_references(
            component,
            ExpressionContext.build_expression_context(collection=component.form.collection, mode="interpolation"),
        )

    count = db.session.query(ComponentReference).count()

    db.session.commit()

    click.echo(f"Done; created {count} component references.")
