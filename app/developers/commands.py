import csv
import hashlib
import json
import uuid
from collections import defaultdict
from difflib import SequenceMatcher
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, TextIO, TypedDict, cast
from uuid import UUID

import click
from flask import current_app
from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import NoResultFound
from werkzeug.datastructures import FileStorage, MultiDict

from app.common.collections.forms import build_question_form
from app.common.data.interfaces.collections import (
    _validate_and_sync_component_references,
    create_submission,
    get_collection,
    get_submissions_by_grant_recipient_collection,
)
from app.common.data.interfaces.grant_recipients import (
    create_grant_recipients,
    get_grant_recipient,
    get_grant_recipients,
)
from app.common.data.interfaces.grants import get_all_grants
from app.common.data.interfaces.organisations import get_organisations
from app.common.data.interfaces.temporary import delete_grant
from app.common.data.interfaces.user import add_permissions_to_user, get_user_by_email
from app.common.data.models import (
    Collection,
    Component,
    ComponentReference,
    DataSource,
    DataSourceItem,
    DataSourceOrganisationItem,
    Expression,
    Form,
    Grant,
    GrantRecipient,
    Group,
    Organisation,
    Question,
    Submission,
    SubmissionEvent,
)
from app.common.data.models_user import User, UserRole
from app.common.data.types import (
    ComponentType,
    DataSourceFileMetadata,
    DataSourceSchema,
    DataSourceType,
    GrantRecipientModeEnum,
    OrganisationModeEnum,
    QuestionDataOptions,
    QuestionPresentationOptions,
    RoleEnum,
    SubmissionModeEnum,
)
from app.common.data.utils import to_dict
from app.common.exceptions import SubmissionAnswerConflict
from app.common.expressions import ExpressionContext
from app.common.helpers.collections import SubmissionHelper
from app.common.utils import slugify
from app.developers import developers_blueprint
from app.extensions import db, notification_service, s3_service
from app.services.notify import NotificationError

export_path = Path.cwd() / "app" / "developers" / "data" / "grants.json"

# The export process anonymises user data, but if any users need to be consistent
# across environments (eg SSO test users), their emails can be added here and they will not be anonymised.
USERS_NOT_TO_ANONYMISE = ["fsd-post-award@levellingup.gov.uk", "john.cheese@communities.gov.uk"]


class GrantExport(TypedDict):
    grant: dict[str, Any]
    grant_recipients: list[Any]
    collections: list[Any]
    forms: list[Any]
    # intentionally leaving this as questions for now to avoid
    # transitioning to a new schema, we can change this to components for
    # clarity when everything is settled if we need to
    questions: list[Any]
    expressions: list[Any]
    data_sources: list[Any]
    data_source_items: list[Any]
    data_source_organisation_items: list[Any]
    component_references: list[Any]


class ExportData(TypedDict):
    grants: list[GrantExport]
    users: list[Any]
    user_roles: list[Any]
    organisations: list[Any]


def _sort_export_data_in_place(export_data: ExportData) -> None:
    # Python 3.14 sets uuid.NIL and uuid.MAX we should use when we upgrade
    NIL = uuid.UUID(int=0)

    export_data["users"].sort(key=lambda u: u["email"])
    export_data["user_roles"].sort(
        key=lambda ur: (ur["user_id"], ur.get("organisation_id", NIL), ur.get("grant_id", NIL), ur["permissions"])
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
@click.option("--output", type=click.Choice(["file", "stdout", "email"]), default="file")
@click.option("--email", "email_address", help="Email address to send the export to. Required when --output=email.")
@click.option(
    "--exclude-users/--no-exclude-users",
    default=None,
    help="Replace all user associations when exporting with a single placeholder user. Forced on for production.",
)
def export_grants(  # noqa: C901
    grant_ids: list[uuid.UUID], output: str, email_address: str | None, exclude_users: bool | None
) -> None:
    from faker import Faker

    if current_app.config["IS_PRODUCTION"]:
        if exclude_users is False:
            click.echo("Warning: --no-exclude-users is ignored in production; user data will be stripped.")
        exclude_users = True
    else:
        exclude_users = bool(exclude_users)

    if output == "email" and not email_address:
        raise click.ClickException("--email is required when --output=email")

    if len(grant_ids) == 0:
        if not export_path.exists():
            raise click.ClickException(
                f"Could not find the exported data at {export_path}. "
                f"Make sure you're running this command from the root of the repository."
            )
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
            "data_source_organisation_items": [],
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

            for ds in collection.data_sources:
                # CUSTOM data sources won't ever be tied explicitly to a collection, but if something rogue happens then
                # this avoids duplicate data sources being exported
                if ds.type == DataSourceType.CUSTOM:
                    continue
                grant_export["data_sources"].append(to_dict(ds))
                if ds.created_by:
                    users.add(ds.created_by)
                if ds.updated_by:
                    users.add(ds.updated_by)
                for org_item in ds.organisation_items:
                    org_item_dict = to_dict(org_item)
                    # _data is the DB model attribute but underscored attributes are skipped by to_dict so
                    # explicitly set it here - persisting the underscored name means no need for explicit handling
                    # when seeding the grants
                    org_item_dict["_data"] = org_item._data
                    grant_export["data_source_organisation_items"].append(org_item_dict)

        for gr in grant.grant_recipients:
            if gr.organisation_id not in [o["id"] for o in export_data["organisations"]]:
                export_data["organisations"].append(to_dict(gr.organisation))

            grant_export["grant_recipients"].append(to_dict(gr))

            for user in gr.users:
                users.add(user)

        for user in grant.grant_team_users:
            users.add(user)

    if exclude_users:
        placeholder_user = User(
            id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            email="placeholder@communities.test.gov.localhost",
            name="Placeholder User",
        )

        for user in users:
            export_data = __replace_id(export_data, str(user.id), str(placeholder_user.id))

        export_data["users"] = [to_dict(placeholder_user)]
        export_data["user_roles"] = []

    else:
        org_ids = {org["id"] for org in export_data["organisations"]}
        for user in users:
            if user.id in [u["id"] for u in export_data["users"]]:
                continue

            user_data = to_dict(user)

            # Anonymise the user, but in a consistent way.
            if user.email not in USERS_NOT_TO_ANONYMISE:
                faker = Faker()
                faker.seed_instance(int(hashlib.md5(str(user_data["id"]).encode()).hexdigest(), 16))
                first_name = faker.first_name()
                last_name = faker.last_name()
                user_data["email"] = f"{first_name.lower()}.{last_name.lower()}@test.communities.gov.uk"
                user_data["name"] = f"{first_name} {last_name}"

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

        case "email":
            assert email_address is not None
            try:
                notification_service.send_grant_export(
                    email_address,
                    export_json=export_json,
                    filename="grants.json",
                )
            except (ValueError, NotificationError) as e:
                raise click.ClickException(f"Failed to send grant export: {e}") from e

            click.echo(f"Emailed {len(grants)} grants to {email_address}")


@developers_blueprint.cli.command("seed-grants", help="Load exported grants into the database")
@click.option(
    "--file",
    "file",
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=Path),
    default=export_path,
    show_default=True,
    help="Path to the exported grants JSON file to load.",
)
def seed_grants(file: Path) -> None:  # noqa: C901
    if current_app.config["IS_PRODUCTION"]:
        raise click.ClickException("seed-grants must not be run in production; it deletes and recreates grants.")

    with open(file) as infile:
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
        # Collection.submission_name_question points at components, which don't exist until later - so we have to do
        # a bit of a dance to clear this out and then write it back after the components are created.
        collection_submission_name_question_ids = {}

        grant_data["grant"]["id"] = uuid.UUID(grant_data["grant"]["id"])

        try:
            relevant_submissions = (
                select(Submission.id)
                .join(Submission.collection)
                .where(Collection.grant_id == grant_data["grant"]["id"])
            )

            db.session.execute(delete(SubmissionEvent).where(SubmissionEvent.submission_id.in_(relevant_submissions)))
            db.session.execute(delete(Submission).where(Submission.id.in_(relevant_submissions)))
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

        db.session.flush()

        for collection in grant_data["collections"]:
            collection["id"] = uuid.UUID(collection["id"])
            collection = Collection(**collection)
            if collection.submission_name_question_id is not None:
                collection_submission_name_question_ids[collection] = collection.submission_name_question_id
                collection.submission_name_question_id = None
            db.session.add(collection)

        db.session.flush()

        for form in grant_data["forms"]:
            form["id"] = uuid.UUID(form["id"])
            form = Form(**form)
            db.session.add(form)

        db.session.flush()

        for data_source in grant_data["data_sources"]:
            data_source["id"] = uuid.UUID(data_source["id"])
            if data_source.get("schema") is not None:
                data_source["schema"] = DataSourceSchema.model_validate(data_source["schema"])
            if data_source.get("file_metadata") is not None:
                data_source["file_metadata"] = DataSourceFileMetadata.model_validate(data_source["file_metadata"])
            data_source = DataSource(**data_source)
            db.session.add(data_source)

        for data_source_item in grant_data["data_source_items"]:
            data_source_item["id"] = uuid.UUID(data_source_item["id"])
            data_source_item = DataSourceItem(**data_source_item)
            db.session.add(data_source_item)

        for organisation_item in grant_data["data_source_organisation_items"]:
            organisation_item["id"] = uuid.UUID(organisation_item["id"])
            organisation_item["data_source_id"] = uuid.UUID(organisation_item["data_source_id"])
            organisation_item = DataSourceOrganisationItem(**organisation_item)
            db.session.add(organisation_item)

        db.session.flush()

        for component in grant_data["questions"]:
            component["id"] = uuid.UUID(component["id"])
            if "presentation_options" in component:
                component["presentation_options"] = QuestionPresentationOptions(**component["presentation_options"])

            if "data_options" in component:
                component["data_options"] = QuestionDataOptions(**component["data_options"])
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

        for component_reference in grant_data["component_references"]:
            component_reference["id"] = uuid.UUID(component_reference["id"])
            component_reference = ComponentReference(**component_reference)
            db.session.add(component_reference)

        for collection, submission_name_question_id in collection_submission_name_question_ids.items():
            collection.submission_name_question_id = submission_name_question_id
        db.session.flush()

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
            db_role.permissions = role["permissions"]
        else:
            role_data = {**role, "permissions": role["permissions"]}
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


# TODO: remove me after this has been executed in all envs as part of https://github.com/communitiesuk/funding-service/pull/1344
@developers_blueprint.cli.command(
    "create-test-organisations", help="Create test organisations based on all live organisations"
)
@click.option("--commit", is_flag=True, help="Actually commit changes proposed by this command; defaults to a dry run")
def create_test_organisation_from_live(commit: bool) -> None:
    if not commit:
        click.echo("Dry run:")

    click.echo("Creating test organisations based on all live organisations.")

    live_organisations = (
        db.session.query(Organisation)
        .where(Organisation.mode == OrganisationModeEnum.LIVE, Organisation.can_manage_grants.is_(False))
        .all()
    )

    created = 0
    for organisation in live_organisations:
        if get_organisations(mode=OrganisationModeEnum.TEST, with_external_ids=[organisation.external_id]):
            continue

        created += 1
        db.session.add(
            Organisation(
                external_id=organisation.external_id,
                name=f"{organisation.name} (test)",
                status=organisation.status,
                type=organisation.type,
                active_date=organisation.active_date,
                retirement_date=organisation.retirement_date,
                can_manage_grants=organisation.can_manage_grants,
                mode=OrganisationModeEnum.TEST,
            )
        )
        click.echo(f" -> Created test organisation for {organisation.name}")

    if commit:
        db.session.commit()
        click.echo(f"\nDone. Created {created} test organisations.")
    else:
        click.echo(f"\nDry run complete. Would create {created} test organisations.")


@developers_blueprint.cli.command(
    "sync-test-grant-recipients", help="Create test grant recipients for all live grant recipients"
)
@click.option("--commit", is_flag=True, help="Actually commit changes proposed by this command; defaults to a dry run")
def sync_test_grant_recipients(commit: bool) -> None:
    if not commit:
        click.echo("Dry run:")

    click.echo("Syncing test grant recipients for all live grant recipients.")

    grants = get_all_grants()
    created = 0
    for grant in grants:
        click.echo(f"\nProcessing {grant.name} ({grant.id})")

        live_grant_recipients = get_grant_recipients(grant, mode=GrantRecipientModeEnum.LIVE)

        for live_grant_recipient in live_grant_recipients:
            matching_test_organisation = live_grant_recipient.organisation.matching_test_organisation
            if not matching_test_organisation:
                click.echo(
                    f" -> WARNING: No test organisation found for "
                    f"live organisation {live_grant_recipient.organisation.name}"
                )
                continue

            try:
                get_grant_recipient(live_grant_recipient.grant_id, matching_test_organisation.id)

                # The test grant recipient already exists; continue
                click.echo(f" -> Test grant recipient already exists for {live_grant_recipient.organisation.name}")
                continue
            except NoResultFound:
                # We need to create it
                created += 1
                pass

            create_grant_recipients(
                grant,
                [matching_test_organisation.id],
                status=live_grant_recipient.status,
                mode=GrantRecipientModeEnum.TEST,
            )

            click.echo(
                f" -> Created test grant recipient for live organisation {live_grant_recipient.organisation.name}"
            )

            for grant_team_user in grant.grant_team_users:
                add_permissions_to_user(
                    grant_team_user,
                    organisation_id=matching_test_organisation.id,
                    grant_id=grant.id,
                    permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER, RoleEnum.CERTIFIER],
                )
                click.echo(f" -> Adding test grant recipient permissions for {grant_team_user.email}")

    if commit:
        db.session.commit()
        click.echo(f"\nDone. Created {created} test grant recipients.")
    else:
        click.echo(f"\nDry run complete. Would create {created} test grant recipients.")


@developers_blueprint.cli.command(
    "create-multi-submissions",
    help="Force creation of multiple submissions for grant recipients",
)
@click.option(
    "--collection_id",
    type=UUID,
    required=True,
    help="The collection to create submissions for",
)
@click.option(
    "--mode",
    type=click.Choice(GrantRecipientModeEnum, case_sensitive=False),
    required=True,
    help="Whether to create submissions for LIVE or TEST grant recipients",
)
@click.option(
    "--file",
    type=click.File("r"),
    required=True,
    help="Filepath to the CSV to ingest",
)
@click.option(
    "--service_user_email_address",
    required=True,
    help="Email address of service user to use for creating submissions",
)
@click.option("--commit", help="Commit changes to the database", is_flag=True)
def create_multi_submissions(  # noqa: C901
    collection_id: UUID, mode: GrantRecipientModeEnum, file: TextIO, service_user_email_address: str, commit: bool
) -> None:
    """Create submissions for a specific collection and set of grant recipients

    Takes a CSV mapping external organisation IDs to submissions that need to exist.

    Existing submissions with the same name will be skipped.
    """
    if not commit:
        click.echo("Dry run:")

    # Read and group CSV rows by organisation_external_id
    rows_by_org: dict[str, list[str]] = defaultdict(list)
    for row in csv.DictReader(file):
        rows_by_org[row["organisation_external_id"]].append(row["submission_name"])

    # Load collection with full schema
    collection = get_collection(collection_id, with_full_schema=True)
    if not collection.allow_multiple_submissions:
        click.echo(f"ERROR: Collection {collection.name} does not allow multiple submissions.")
        return

    question = collection.submission_name_question
    if not question:
        click.echo("ERROR: Collection does not have a submission name question configured.")
        return

    # Get grant recipients for this collection's grant
    grant_recipients = get_grant_recipients(collection.grant, mode=mode, with_organisations=True)
    gr_by_org_ext_id = {gr.organisation.external_id: gr for gr in grant_recipients}

    # Validate CSV against grant recipients
    csv_org_ids = set(rows_by_org.keys())
    gr_org_ids = set(gr_by_org_ext_id.keys())

    missing_from_csv = gr_org_ids - csv_org_ids
    if missing_from_csv:
        click.echo(
            f"WARNING: {len(missing_from_csv)} grant recipient(s) not in CSV: {', '.join(sorted(missing_from_csv))}"
        )

    extra_in_csv = csv_org_ids - gr_org_ids
    if extra_in_csv:
        click.echo(
            f"WARNING: {len(extra_in_csv)} CSV org(s) not matching any grant recipient: "
            f"{', '.join(sorted(extra_in_csv))}"
        )

    orgs_to_process = csv_org_ids & gr_org_ids

    # Build shared resources
    evaluation_context = ExpressionContext.build_expression_context(collection, mode="evaluation")
    interpolation_context = ExpressionContext.build_expression_context(collection, mode="interpolation")
    user = get_user_by_email(service_user_email_address)
    if not user:
        click.echo(f"ERROR: Could not find user {service_user_email_address}")
        return

    submission_mode = SubmissionModeEnum.from_similar(mode)
    form_cls = build_question_form([question], evaluation_context, interpolation_context)

    created = 0
    skipped = 0
    for org_ext_id in sorted(orgs_to_process):
        grant_recipient = gr_by_org_ext_id[org_ext_id]
        click.echo(f"\nProcessing {grant_recipient.organisation.name} ({org_ext_id})")

        for raw_answer in rows_by_org[org_ext_id]:
            # Convert to data source item key format for questions that read from a data source.
            if collection.submission_name_question and collection.submission_name_question.data_source:
                answer = slugify(raw_answer)
            else:
                answer = raw_answer

            savepoint = db.session.begin_nested()
            try:
                # NOTE: `create_submission` emits metrics even in dry-run/no-commit mode. Need to let data analysts
                #       know about this discrepancy each time we run. Ideally we'd be able to delay metric emission
                #       until the `db.commit` succeeds (for most metrics).

                submission = create_submission(
                    collection=collection, created_by=user, mode=submission_mode, grant_recipient=grant_recipient
                )
                form = form_cls(formdata=MultiDict({question.safe_qid: answer}), meta={"csrf": False})
                SubmissionHelper(submission).submit_answer_for_question(question.id, form, user)
                created += 1
                click.echo(f"  -> Created submission '{answer}'")
            except SubmissionAnswerConflict:
                savepoint.rollback()
                skipped += 1
                click.echo(f"  -> Skipping '{answer}' (already exists)")

            # Whether or not we created a submission, we may need to 'backfill' section completeness.
            # If the submission name question is the only question in its section, mark it as complete.
            if question.form.cached_questions == [question]:
                helpers = [
                    SubmissionHelper(s)
                    for s in get_submissions_by_grant_recipient_collection(grant_recipient, collection.id)
                ]
                helper = next(h for h in helpers if h.submission_name == raw_answer)
                helper.toggle_form_completed(question.form, user, is_complete=True)

    if commit:
        db.session.commit()
        click.echo(f"\nDone. Created {created} submissions, skipped {skipped}.")
    else:
        click.echo(f"\nDry run complete. Would create {created} submissions, would skip {skipped}.")


def _render_char_diff(stored: str, generated: str) -> tuple[str, str]:
    matcher = SequenceMatcher(a=stored, b=generated, autojunk=False)
    stored_out: list[str] = []
    generated_out: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            stored_out.append(stored[i1:i2])
            generated_out.append(generated[j1:j2])
            continue
        if i1 != i2:
            stored_out.append(click.style(stored[i1:i2], fg="red", bold=True))
        if j1 != j2:
            generated_out.append(click.style(generated[j1:j2], fg="green", bold=True))
    return "".join(stored_out), "".join(generated_out)


@developers_blueprint.cli.command(
    "check-managed-statements",
    help="Diff each managed expression's stored statement against one regenerated from its ManagedExpression.",
)
@click.option("--output", type=click.Choice(["stdout", "s3"]), default="stdout")
@click.option("--s3-key", help="S3 object key to upload the report to. Required when --output=s3.")
@click.option(
    "--force-colour",
    is_flag=True,
    default=False,
    help="Force ANSI colour codes in output even when stdout is not a TTY (e.g. ECS/CloudWatch, S3).",
)
@click.pass_context
def check_managed_statements(ctx: click.Context, output: str, s3_key: str | None, force_colour: bool) -> None:
    if force_colour:
        ctx.color = True

    if output == "s3" and not s3_key:
        raise click.ClickException("--s3-key is required when --output=s3")

    buf: StringIO | None = StringIO() if output == "s3" else None

    def emit(line: str = "") -> None:
        click.echo(line)
        if buf is not None:
            click.echo(line, file=buf)

    expressions = (
        db.session.query(Expression)
        .where(Expression.managed_name.isnot(None))
        .order_by(Expression.managed_name, Expression.id)
        .all()
    )

    mismatches = 0
    errors = 0
    for expression in expressions:
        assert expression.managed_name is not None
        header = f"expression {expression.id} ({expression.managed_name.value}) on component {expression.question_id}"

        try:
            generated = expression.managed.statement
        except Exception as exc:
            errors += 1
            emit(f"{header}:")
            emit(f"  stored:    {expression.statement}")
            emit(f"  {click.style('could not regenerate: ' + type(exc).__name__ + ': ' + str(exc), fg='yellow')}")
            emit()
            continue

        stored = expression.statement
        if stored == generated:
            continue

        mismatches += 1
        stored_coloured, generated_coloured = _render_char_diff(stored, generated)
        emit(f"{header}:")
        emit(f"  - {stored_coloured}")
        emit(f"  + {generated_coloured}")
        emit()

    emit(
        f"Checked {len(expressions)} managed expressions; {mismatches} mismatch(es), {errors} reconstruction error(s)."
    )

    if buf is not None:
        assert s3_key is not None
        file_storage = FileStorage(
            stream=BytesIO(buf.getvalue().encode("utf-8")),
            filename=s3_key,
            content_type="text/plain; charset=utf-8",
        )
        s3_service.upload_file(file_storage, key=s3_key)
        bucket = current_app.config["AWS_S3_BUCKET_NAME"]
        click.echo(f"Report uploaded to s3://{bucket}/{s3_key}")

    if mismatches or errors:
        raise click.exceptions.Exit(1)


@developers_blueprint.cli.command(
    "refresh-status-for-multi-submissions",
    help="Refresh submission statuses for multi-submission collections",
)
@click.option("--commit", is_flag=True, help="Actually commit changes proposed by this command; defaults to a dry run")
def refresh_status_for_multi_submissions(commit: bool) -> None:
    submission_ids = db.session.scalars(
        select(Submission.id).join(Collection).filter(Collection.allow_multiple_submissions.is_(True))
    ).all()
    updated = 0

    click.echo(f"Found {len(submission_ids)} multi-submissions")

    for submission_id in submission_ids:
        helper = SubmissionHelper.load(submission_id)
        submission = helper.submission

        last_updated_at = submission.updated_at_utc
        from_status = helper.status

        # Manually assign updated_at_utc to prevent it being automatically updated
        db.session.execute(
            update(Submission)
            .where(Submission.id == submission_id)
            .values(updated_at_utc=last_updated_at, status=helper._calculate_submission_status())
        )

        db.session.flush()
        db.session.refresh(submission)

        if submission.updated_at_utc != last_updated_at:
            click.echo(
                f"Failed to preserve updated_at_utc on submission {submission_id} "
                f"(was {last_updated_at}, now is {submission.updated_at_utc}; aborting)"
            )
            db.session.rollback()
            raise click.exceptions.Exit(1)

        if commit:
            click.echo(f"Updated submission {submission.id} from status {from_status} to {submission.status}")
            db.session.commit()
        else:
            click.echo(f"Would update submission {submission.id} from status {from_status} to {submission.status}")
            db.session.rollback()

        updated += 1

    if commit:
        click.echo(f"Updated {updated} submissions with saved statuses")
    else:
        click.echo(f"Would update {updated} submissions with saved statuses")
