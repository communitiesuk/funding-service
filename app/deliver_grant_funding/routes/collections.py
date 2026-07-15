import csv
import io
import uuid
from itertools import groupby
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from flask import abort, current_app, flash, g, redirect, render_template, request, send_file, session, url_for
from flask.typing import ResponseReturnValue
from flask_wtf import FlaskForm
from markupsafe import Markup, escape
from pydantic import BaseModel, ValidationError
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename
from wtforms import Field

from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.auth.decorators import collection_is_editable, has_deliver_grant_role
from app.common.data import interfaces
from app.common.data.interfaces.collections import (
    AddAnotherDependencyException,
    AddAnotherNotValidException,
    DataSourceHasReferencesException,
    DataSourceItemReferenceDependencyException,
    DependencyOrderException,
    GroupContainsAddAnotherException,
    GroupHasValidationsCannotBeOnePerPageException,
    IncompatibleDataTypeException,
    IncompatibleDataTypeInCalculationException,
    NestedGroupDisplayTypeSamePageException,
    NestedGroupException,
    SectionComponentDependencyException,
    SectionDependencyOrderException,
    copy_collection,
    create_collection,
    create_form,
    create_group,
    create_question,
    delete_form,
    delete_question,
    get_all_submissions_with_mode_for_collection,
    get_collection,
    get_component_by_id,
    get_expression_by_id,
    get_form_by_id,
    get_group_by_id,
    get_question_by_id,
    get_submission_list_for_collection,
    move_component_down,
    move_component_up,
    move_form_down,
    move_form_up,
    raise_if_component_or_section_has_any_dependencies,
    raise_if_data_source_has_references,
    raise_if_nested_group_creation_not_valid_here,
    remove_question_expression,
    reset_all_test_submissions,
    reset_test_submission,
    update_collection,
    update_form,
    update_group,
    update_question,
)
from app.common.data.interfaces.data_sets import (
    create_uploaded_data_source,
    delete_data_source,
    get_data_source,
    get_data_source_list_for_collection,
    replace_uploaded_data_source,
)
from app.common.data.interfaces.exceptions import (
    DuplicateValueError,
    InvalidReferenceInExpression,
)
from app.common.data.interfaces.grant_recipients import get_grant_recipients_for_collection_with_submitted_submissions
from app.common.data.interfaces.grants import get_all_deliver_grants_by_user, get_grant
from app.common.data.interfaces.organisations import get_organisations
from app.common.data.interfaces.user import get_current_user
from app.common.data.types import (
    CollectionType,
    ComponentType,
    ConditionsOperator,
    DataSourceFileTagEnum,
    DataSourceType,
    ExpressionType,
    GrantRecipientModeEnum,
    GroupDisplayOptions,
    ManagedExpressionsEnum,
    NumberTypeEnum,
    OrganisationModeEnum,
    QuestionDataOptions,
    QuestionDataType,
    QuestionPresentationOptions,
    RoleEnum,
    SubmissionEventType,
    SubmissionModeEnum,
    TUnvalidatedDataSetRows,
)
from app.common.exceptions import WTFormRenderableException
from app.common.expressions import (
    ExpressionContext,
)
from app.common.expressions.custom import CustomExpression
from app.common.expressions.forms import (
    CalculatedConditionForm,
    CustomValidationExpressionForm,
    _ManagedExpressionForm,
    build_managed_expression_form,
)
from app.common.expressions.references import ExpressionReference, InterpolationStatement
from app.common.expressions.registry import get_managed_validators_by_data_type, lookup_managed_expression
from app.common.forms import GenericConfirmDeletionForm, GenericSubmitForm
from app.common.helpers.collections import (
    AllSubmissionsHelper,
    CollectionIsNotOpenError,
    SubmissionAuthorisationError,
    SubmissionHelper,
    SubmissionIsNotSubmittedError,
)
from app.common.helpers.feature_flags import FeatureFlags
from app.common.helpers.pdf import render_pdf
from app.common.utils import slugify
from app.constants import (
    DATA_SET_EXTERNAL_ID_COLUMN_HEADER,
    DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER,
    DATA_SET_IDENTIFIER_COLUMN_HEADERS,
    DATA_SET_PREVIEW_LENGTH,
    SESSION_DATA_SET_REPLACE,
    SESSION_DATA_SET_UPLOAD,
)
from app.deliver_grant_funding.data_sets import (
    BritishPoundsError,
    DataSetValidationResult,
    build_current_data_set_view,
    build_data_display_rows_with_missing_tags,
    build_data_set_upload_s3_key,
    find_grant_recipient_mismatches,
    format_data_set_csv_data_for_column_type,
    generate_latest_csv_template,
    validate_data_set,
    validate_data_set_grant_recipients,
)
from app.deliver_grant_funding.forms import (
    AddContextSelectSourceForm,
    AddGuidanceForm,
    AddSectionForm,
    ApproveOrRejectSubmissionForm,
    CollectionCreationMethodForm,
    CollectionSettingsForm,
    ConditionsOperatorForm,
    GroupAddAnotherOptionsForm,
    GroupAddAnotherSummaryForm,
    GroupDisplayOptionsForm,
    GroupForm,
    MapDataSetColumnsForm,
    MapNumberColumnsForm,
    PublicSignUpSettingsForm,
    QuestionForm,
    QuestionTypeForm,
    ReopenSubmissionForm,
    RequestChangesSubmissionForm,
    RequestOrAllowChangesSubmissionForm,
    SelectCollectionToCopyForm,
    SelectConditionCalculationForm,
    SelectDataSourceDataSetColumnForm,
    SelectDataSourceDataSetForm,
    SelectDataSourceQuestionForm,
    SelectDataSourceSectionForm,
    SetUpCollectionForm,
    SubmissionGuidanceForm,
    TestGrantRecipientJourneyForm,
    UploadDataSetForm,
)
from app.deliver_grant_funding.helpers import start_previewing_collection
from app.deliver_grant_funding.routes import deliver_grant_funding_blueprint
from app.deliver_grant_funding.session_models import (
    AddConditionDependsOnSessionModel,
    AddContextToComponentGuidanceSessionModel,
    AddContextToComponentSessionModel,
    AddContextToExpressionsModel,
    DataSetColumnMapping,
    DataSetUploadSessionModel,
)
from app.extensions import auto_commit_after_request, notification_service, s3_service
from app.metrics import MetricAttributeName, MetricEventName, emit_metric_count
from app.types import NOT_PROVIDED, FlashMessageType, TNotProvided

if TYPE_CHECKING:
    from app.common.data.models import Collection, DataSource, Expression, Group, Question

SessionModelType = (
    AddConditionDependsOnSessionModel
    | AddContextToComponentSessionModel
    | AddContextToComponentGuidanceSessionModel
    | AddContextToExpressionsModel
)


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/<collection_type:collection_type>/<uuid:collection_id>/test-grant-recipient-journey",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.MEMBER)
@auto_commit_after_request
def start_test_grant_recipient_journey(
    grant_id: UUID, collection_type: CollectionType, collection_id: UUID
) -> ResponseReturnValue:
    grant = get_grant(grant_id, with_all_collections=True)
    collection = get_collection(collection_id, grant_id=grant_id, type_=collection_type, with_full_schema=False)

    user = get_current_user()
    test_grant_recipients = [
        grant_recipient
        for grant_recipient in user.get_grant_recipients(limit_to_grant_id=grant_id)
        if grant_recipient.mode == GrantRecipientModeEnum.TEST
    ]
    test_grant_organisations = [gr.organisation for gr in test_grant_recipients]

    # todo: currently checks for the existence of test submissions but could
    #       set nice submission events when inviting data provider users initially and be specific here
    existing_submissions = [
        submission
        for submission in get_all_submissions_with_mode_for_collection(
            collection_id=collection.id, submission_mode=SubmissionModeEnum.TEST, with_full_schema=False
        )
        if submission.grant_recipient and submission.grant_recipient.organisation in test_grant_organisations
    ]

    form = TestGrantRecipientJourneyForm(users_test_grant_recipients=test_grant_recipients)

    if form.validate_on_submit():
        grant_recipient = next(gr for gr in test_grant_recipients if str(gr.id) == form.organisation.data)
        notification_service.send_access_report_opened(
            email_address=user.email,
            collection=collection,
            grant_recipient=grant_recipient,
            submission_helpers=[SubmissionHelper(s) for s in grant_recipient.submissions if s.collection == collection],
        )
        flash(
            "We emailed you a link to test the grant recipient journey.",
            FlashMessageType.TESTING_GRANT_RECIPIENT_JOURNEY_STARTED.value,
        )
        return redirect(
            url_for(
                "deliver_grant_funding.list_collection_sections",
                grant_id=grant_id,
                collection_type=collection_type,
                collection_id=collection_id,
            )
        )

    return render_template(
        "deliver_grant_funding/collections/start_test_grant_recipient_journey.html",
        grant=grant,
        collection=collection,
        form=form,
        test_grant_recipients=test_grant_recipients,
        existing_submissions=existing_submissions,
    )


def _collections_user_can_copy(collection_type: CollectionType) -> list[Any]:
    """All collections of this type that the current user could copy, from any grant they have access to."""
    grants = get_all_deliver_grants_by_user(interfaces.user.get_current_user())
    return sorted(
        (collection for grant in grants for collection in grant.collections if collection.type == collection_type),
        key=lambda collection: (collection.grant.name.lower(), collection.name.lower()),
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/<collection_type:collection_type>/set-up/method", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def choose_collection_creation_method(grant_id: UUID, collection_type: CollectionType) -> ResponseReturnValue:
    grant = get_grant(grant_id)
    if not _collections_user_can_copy(collection_type):
        return redirect(
            url_for("deliver_grant_funding.set_up_collection", grant_id=grant_id, collection_type=collection_type)
        )

    form = CollectionCreationMethodForm(collection_type=collection_type)
    if form.validate_on_submit():
        if form.method.data == "copy":
            return redirect(
                url_for(
                    "deliver_grant_funding.select_collection_to_copy",
                    grant_id=grant_id,
                    collection_type=collection_type,
                )
            )
        return redirect(
            url_for("deliver_grant_funding.set_up_collection", grant_id=grant_id, collection_type=collection_type)
        )

    return render_template(
        "deliver_grant_funding/collections/choose_collection_creation_method.html",
        grant=grant,
        form=form,
        collection_type=collection_type,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/<collection_type:collection_type>/set-up/copy", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def select_collection_to_copy(grant_id: UUID, collection_type: CollectionType) -> ResponseReturnValue:
    grant = get_grant(grant_id)
    collections = _collections_user_can_copy(collection_type)
    if not collections:
        return redirect(
            url_for("deliver_grant_funding.set_up_collection", grant_id=grant_id, collection_type=collection_type)
        )

    form = SelectCollectionToCopyForm(collection_type=collection_type, collections=collections, grant=grant)
    if form.validate_on_submit():
        return redirect(
            url_for(
                "deliver_grant_funding.set_up_collection",
                grant_id=grant_id,
                collection_type=collection_type,
                copy_from=form.collection.data,
            )
        )

    return render_template(
        "deliver_grant_funding/collections/select_collection_to_copy.html",
        grant=grant,
        form=form,
        collection_type=collection_type,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/<collection_type:collection_type>/set-up", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def set_up_collection(grant_id: UUID, collection_type: CollectionType) -> ResponseReturnValue:
    grant = get_grant(grant_id)

    source_collection = None
    if copy_from := request.args.get("copy_from"):
        try:
            copy_from_id = UUID(copy_from)
        except ValueError:
            return abort(404)
        source_collection = get_collection(copy_from_id, type_=collection_type, with_full_schema=True)
        if source_collection.grant not in get_all_deliver_grants_by_user(interfaces.user.get_current_user()):
            return abort(404)

    form = SetUpCollectionForm(collection_type=collection_type)
    if form.validate_on_submit():
        assert form.name.data
        try:
            if source_collection:
                new_collection = copy_collection(
                    source_collection,
                    name=form.name.data,
                    user=interfaces.user.get_current_user(),
                    grant=grant,
                )
                emit_metric_count(MetricEventName.COLLECTION_COPIED, 1, collection=source_collection)
            else:
                new_collection = create_collection(
                    name=form.name.data,
                    user=interfaces.user.get_current_user(),
                    grant=grant,
                    type_=collection_type,
                )
            flash(
                {
                    "name": new_collection.name,
                    "singular": collection_type.constants.singular,
                    "url": url_for(
                        "deliver_grant_funding.list_collection_sections",
                        grant_id=grant_id,
                        collection_type=collection_type,
                        collection_id=new_collection.id,
                    ),
                },  # ty: ignore[invalid-argument-type]
                FlashMessageType.COLLECTION_CREATED,
            )
            return redirect(url_for(collection_type.constants.list_endpoint, grant_id=grant_id))

        except DuplicateValueError:
            form.name.errors.append(f"A {collection_type.constants.singular} with this name already exists")  # ty: ignore[unresolved-attribute]

    return render_template(
        "deliver_grant_funding/collections/set_up_collection.html",
        grant=grant,
        form=form,
        collection_type=collection_type,
        source_collection=source_collection,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/<collection_type:collection_type>/<uuid:collection_id>/change-name", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
@auto_commit_after_request
def change_collection_name(grant_id: UUID, collection_type: CollectionType, collection_id: UUID) -> ResponseReturnValue:
    collection = get_collection(collection_id, grant_id=grant_id, type_=collection_type)

    form = SetUpCollectionForm(obj=collection, collection_type=collection_type)
    if form.validate_on_submit():
        assert form.name.data
        try:
            update_collection(collection, name=form.name.data)
            return redirect(url_for(collection.type.constants.list_endpoint, grant_id=collection.grant_id))
        except DuplicateValueError:
            # FIXME: standardise+consolidate how we handle form errors raised from interfaces
            form.name.errors.append(  # ty: ignore[unresolved-attribute]
                f"A {collection.type.constants.singular} with this name already exists"
            )

    return render_template(
        "deliver_grant_funding/collections/change_collection_name.html",
        grant=collection.grant,
        collection=collection,
        form=form,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/<collection_type:collection_type>/<uuid:collection_id>/configure-multiple-submissions",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def collection_configure_multiple_submissions(
    grant_id: UUID, collection_type: CollectionType, collection_id: UUID
) -> ResponseReturnValue:
    collection = get_collection(collection_id, grant_id=grant_id, type_=collection_type, with_full_schema=True)

    form = CollectionSettingsForm(
        questions=[
            q
            for form in collection.forms
            for q in form.cached_questions
            if q.data_type in current_app.config["QUESTION_DATA_TYPES_ALLOWED_FOR_MULTI_SUBMISSION_NAMES"]
            and not q.add_another_container
        ],
        obj=collection if request.method == "GET" else None,
    )
    if form.validate_on_submit():
        if not AuthorisationHelper.can_edit_collection(get_current_user(), collection.id):
            form.form_errors.append("You cannot change this setting as the collection is not currently editable")

        else:
            if form.allow_multiple_submissions.data == "False":
                try:
                    update_collection(collection, allow_multiple_submissions=False)
                    return redirect(
                        url_for(
                            "deliver_grant_funding.list_collection_sections",
                            grant_id=grant_id,
                            collection_type=collection_type,
                            collection_id=collection_id,
                        )
                    )
                except ValueError as e:
                    form.allow_multiple_submissions.errors.append(str(e))  # ty: ignore[unresolved-attribute]

            else:
                update_collection(
                    collection,
                    allow_multiple_submissions=True,
                    submission_name_question_id=uuid.UUID(form.submission_name_question.data),
                )
                return redirect(
                    url_for(
                        "deliver_grant_funding.list_collection_sections",
                        grant_id=grant_id,
                        collection_type=collection_type,
                        collection_id=collection_id,
                    )
                )

    return render_template(
        "deliver_grant_funding/collections/configure_multiple_submissions.html",
        grant=collection.grant,
        collection=collection,
        form=form,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/<collection_type:collection_type>/<uuid:collection_id>/configure-public-sign-up",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def collection_configure_public_sign_up(
    grant_id: UUID, collection_type: CollectionType, collection_id: UUID
) -> ResponseReturnValue:
    collection = get_collection(collection_id, grant_id=grant_id, type_=collection_type)

    form = PublicSignUpSettingsForm(obj=collection if request.method == "GET" else None)

    if form.validate_on_submit():
        if not AuthorisationHelper.can_edit_collection(get_current_user(), collection.id):
            form.form_errors.append("You cannot change this setting as the collection is not currently editable")
        else:
            update_collection(collection, allow_public_sign_up=form.allow_public_sign_up.data == "True")
            return redirect(
                url_for(
                    "deliver_grant_funding.list_collection_sections",
                    grant_id=grant_id,
                    collection_type=collection_type,
                    collection_id=collection_id,
                )
            )

    return render_template(
        "deliver_grant_funding/collections/configure_public_sign_up.html",
        grant=collection.grant,
        collection=collection,
        form=form,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/<collection_type:collection_type>/<uuid:collection_id>/set-guidance-for-multiple-submissions",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def set_guidance_for_multiple_submissions(
    grant_id: UUID, collection_type: CollectionType, collection_id: UUID
) -> ResponseReturnValue:
    collection = get_collection(collection_id, grant_id=grant_id, type_=collection_type)
    if not collection.allow_multiple_submissions:
        return redirect(
            url_for(
                "deliver_grant_funding.list_collection_sections",
                grant_id=grant_id,
                collection_type=collection_type,
                collection_id=collection_id,
            )
        )

    form = SubmissionGuidanceForm()
    if not form.is_submitted():
        form.guidance_body.data = collection.submission_guidance

    if form.validate_on_submit():
        if not AuthorisationHelper.can_edit_collection(get_current_user(), collection.id):
            form.form_errors.append("You cannot change this setting as the collection is not currently editable")
        else:
            update_collection(collection, submission_guidance=form.guidance_body.data)

            if form.preview.data:
                return redirect(
                    url_for(
                        "deliver_grant_funding.set_guidance_for_multiple_submissions",
                        grant_id=grant_id,
                        collection_type=collection_type,
                        collection_id=collection_id,
                        _anchor="preview-guidance",
                    )
                )

            return redirect(
                url_for(
                    "deliver_grant_funding.list_collection_sections",
                    grant_id=grant_id,
                    collection_type=collection_type,
                    collection_id=collection_id,
                )
            )

    return render_template(
        "deliver_grant_funding/collections/set_guidance_for_multiple_submissions.html",
        grant=collection.grant,
        collection=collection,
        form=form,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/<collection_type:collection_type>/<uuid:collection_id>", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.MEMBER)
@auto_commit_after_request
def list_collection_sections(
    grant_id: UUID, collection_type: CollectionType, collection_id: UUID
) -> ResponseReturnValue:
    collection = get_collection(collection_id, grant_id=grant_id, type_=collection_type, with_full_schema=True)
    previews = get_all_submissions_with_mode_for_collection(
        collection_id=collection.id, submission_mode=SubmissionModeEnum.PREVIEW, with_full_schema=False, with_users=True
    )
    previewers = {preview.created_by for preview in previews}
    form = GenericSubmitForm()

    if form.validate_on_submit() and form.submit.data:
        return start_previewing_collection(collection=collection)

    return render_template(
        "deliver_grant_funding/collections/list_report_sections.html",
        grant=collection.grant,
        collection=collection,
        form=form,
        previewers=previewers,
    )


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/form/<uuid:form_id>/move-<direction>")
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
@auto_commit_after_request
def move_section(grant_id: UUID, form_id: UUID, direction: str) -> ResponseReturnValue:
    form = get_form_by_id(form_id)

    try:
        match direction:
            case "up":
                move_form_up(form)
            case "down":
                move_form_down(form)
            case _:
                return abort(400)
    except SectionDependencyOrderException as e:
        flash(e.as_flash_context(), FlashMessageType.SECTION_DEPENDENCY_ORDER_ERROR.value)  # ty: ignore[invalid-argument-type]

    return redirect(
        url_for(
            "deliver_grant_funding.list_collection_sections",
            grant_id=grant_id,
            collection_type=form.collection.type,
            collection_id=form.collection_id,
        )
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/<collection_type:collection_type>/<uuid:collection_id>/add-section", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
@auto_commit_after_request
def add_section(grant_id: UUID, collection_type: CollectionType, collection_id: UUID) -> ResponseReturnValue:
    collection = get_collection(collection_id, grant_id=grant_id, type_=collection_type)

    # Technically this isn't going to be always correct; if users create a report, add a first section, then delete that
    # section, they will be able to add a section from the 'list report sections' page - but the backlink will take them
    # to the 'list reports' page. This is an edge case I'm not handling right now because: 1) rare, 2) backlinks that
    # are perfect are hard and it doesn't feel worth it yet.
    back_link = (
        url_for(
            "deliver_grant_funding.list_collection_sections",
            grant_id=grant_id,
            collection_type=collection_type,
            collection_id=collection_id,
        )
        if collection.forms
        else url_for(collection.type.constants.list_endpoint, grant_id=grant_id)
    )

    form = AddSectionForm(obj=collection)
    if form.validate_on_submit():
        assert form.title.data
        try:
            create_form(
                title=form.title.data,
                collection=collection,
            )
            return redirect(
                url_for(
                    "deliver_grant_funding.list_collection_sections",
                    grant_id=grant_id,
                    collection_type=collection_type,
                    collection_id=collection.id,
                )
            )

        except DuplicateValueError:
            form.title.errors.append("A section with this name already exists")  # ty: ignore[unresolved-attribute]

    return render_template(
        "deliver_grant_funding/collections/add_section.html",
        grant=collection.grant,
        collection=collection,
        form=form,
        back_link=back_link,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/section/<uuid:form_id>/change-name", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
@auto_commit_after_request
def change_form_name(grant_id: UUID, form_id: UUID) -> ResponseReturnValue:
    db_form = get_form_by_id(form_id, grant_id=grant_id)

    if db_form.collection.live_submissions:
        # Prevent changes to the section if it has any live submissions; this is very coarse layer of protection. We
        # might want to do something more fine-grained to give a better user experience at some point. And/or we might
        # need to allow _some_ people (eg platform admins) to make changes, at their own peril.
        # TODO: flash and redirect back to 'list report sections'?
        current_app.logger.info(
            "Blocking access to manage form %(form_id)s because related collection has live submissions",
            dict(form_id=str(form_id)),
        )
        return abort(403)

    form = AddSectionForm(obj=db_form)
    if form.validate_on_submit():
        assert form.title.data
        try:
            update_form(db_form, title=form.title.data)
            return redirect(
                url_for(
                    "deliver_grant_funding.list_section_questions",
                    grant_id=grant_id,
                    form_id=db_form.id,
                )
            )
        except DuplicateValueError:
            # FIXME: standardise+consolidate how we handle form errors raised from interfaces
            form.title.errors.append("A section with this name already exists")  # ty: ignore[unresolved-attribute]

    return render_template(
        "deliver_grant_funding/collections/change_form_name.html",
        grant=db_form.collection.grant,
        db_form=db_form,
        form=form,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/group/<uuid:group_id>/change-name", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
@auto_commit_after_request
def change_group_name(grant_id: UUID, group_id: UUID) -> ResponseReturnValue:
    db_group = get_group_by_id(group_id)

    form = GroupForm(obj=db_group)
    if form.validate_on_submit():
        assert form.name.data
        try:
            update_group(
                db_group,
                expression_context=ExpressionContext.build_expression_context(
                    collection=db_group.form.collection, mode="interpolation"
                ),
                name=form.name.data,
            )
            return redirect(
                url_for(
                    "deliver_grant_funding.list_group_questions",
                    grant_id=grant_id,
                    group_id=db_group.id,
                )
            )
        except DuplicateValueError:
            form.name.errors.append("A question group with this name already exists")  # ty: ignore[unresolved-attribute]

    return render_template(
        "deliver_grant_funding/collections/change_question_group_name.html",
        grant=db_group.form.collection.grant,
        group=db_group,
        db_form=db_group.form,
        form=form,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/component/<uuid:component_id>/change-conditions-operator", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
@auto_commit_after_request
def change_conditions_operator(grant_id: UUID, component_id: UUID) -> ResponseReturnValue:
    component = get_component_by_id(component_id)

    form = ConditionsOperatorForm(obj=component)
    if form.validate_on_submit():
        assert form.conditions_operator.data
        match component.type:
            case ComponentType.QUESTION:
                update_question(
                    component,
                    expression_context=ExpressionContext.build_expression_context(
                        collection=component.form.collection, mode="interpolation"
                    ),
                    conditions_operator=ConditionsOperator(form.conditions_operator.data),
                )
            case ComponentType.GROUP:
                update_group(
                    component,
                    expression_context=ExpressionContext.build_expression_context(
                        collection=component.form.collection, mode="interpolation"
                    ),
                    conditions_operator=ConditionsOperator(form.conditions_operator.data),
                )
            case _:
                abort(500)

        if component.is_group:
            return redirect(
                url_for(
                    "deliver_grant_funding.list_group_questions",
                    grant_id=grant_id,
                    group_id=component.id,
                )
            )
        else:
            return redirect(
                url_for(
                    "deliver_grant_funding.edit_question",
                    grant_id=grant_id,
                    question_id=component.id,
                )
            )

    return render_template(
        "deliver_grant_funding/collections/change_conditions_operator.html",
        grant=component.form.collection.grant,
        component=component,
        db_form=component.form,
        form=form,
        interpolate=SubmissionHelper.get_interpolator(collection=component.form.collection),
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/group/<uuid:group_id>/change-display-options", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
@auto_commit_after_request
def change_group_display_options(grant_id: UUID, group_id: UUID) -> ResponseReturnValue:
    db_group = get_group_by_id(group_id)

    form = GroupDisplayOptionsForm(
        show_questions_on_the_same_page=GroupDisplayOptions.ALL_QUESTIONS_ON_SAME_PAGE
        if db_group.presentation_options.show_questions_on_the_same_page
        else GroupDisplayOptions.ONE_QUESTION_PER_PAGE
    )
    if form.validate_on_submit():
        try:
            # todo: pass the result of checking if questions depend on each other
            #       into the template so that we can grey out the option before reaching this point
            #       will need to decide how thats displayed: p text before the radio might work - grey hint
            #       on grey hint bad
            update_group(
                db_group,
                expression_context=ExpressionContext.build_expression_context(
                    collection=db_group.form.collection, mode="interpolation"
                ),
                presentation_options=QuestionPresentationOptions.from_group_form(form),
            )
            return redirect(
                url_for(
                    "deliver_grant_funding.list_group_questions",
                    grant_id=grant_id,
                    group_id=db_group.id,
                )
            )
        except DependencyOrderException:
            # TODO: can we show the user the problematic questions like we do when rendering flashable exceptions?
            form.show_questions_on_the_same_page.errors.append(  # ty: ignore[unresolved-attribute]
                "A question group cannot display on the same page if questions depend on answers within the group"
            )
        except NestedGroupDisplayTypeSamePageException:
            form.show_questions_on_the_same_page.errors.append(  # ty: ignore[unresolved-attribute]
                "A question group cannot display on the same page if it contains a nested group"
            )
        except GroupHasValidationsCannotBeOnePerPageException:
            form.show_questions_on_the_same_page.errors.append(  # ty: ignore[unresolved-attribute]
                "A question group cannot display one question per page while it has validation rules attached. "
                "Delete the group validations first."
            )

    return render_template(
        "deliver_grant_funding/collections/change_question_group_display_options.html",
        grant=db_group.form.collection.grant,
        group=db_group,
        db_form=db_group.form,
        form=form,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/group/<uuid:group_id>/change-add-another-summary", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
@auto_commit_after_request
def change_group_add_another_summary(grant_id: UUID, group_id: UUID) -> ResponseReturnValue:
    db_group = get_group_by_id(group_id)
    form = GroupAddAnotherSummaryForm(group=db_group)

    if form.validate_on_submit():
        update_group(
            db_group,
            expression_context=ExpressionContext.build_expression_context(
                collection=db_group.form.collection, mode="interpolation"
            ),
            presentation_options=QuestionPresentationOptions(
                add_another_summary_line_question_ids=form.questions_to_show_in_add_another_summary.data
            ),
        )
        return redirect(
            url_for(
                "deliver_grant_funding.list_group_questions",
                grant_id=grant_id,
                group_id=db_group.id,
            )
        )

    return render_template(
        "deliver_grant_funding/collections/change_question_group_add_another_summary.html",
        grant=db_group.form.collection.grant,
        group=db_group,
        db_form=db_group.form,
        form=form,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/group/<uuid:group_id>/change-add-another-options", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
@auto_commit_after_request
def change_group_add_another_options(grant_id: UUID, group_id: UUID) -> ResponseReturnValue:
    db_group = get_group_by_id(group_id)

    form = GroupAddAnotherOptionsForm(question_group_is_add_another="yes" if db_group.add_another else "no")
    if form.validate_on_submit():
        try:
            # todo: pass the result of checking if questions depend on each other
            #       into the template so that we can grey out the option before reaching this point
            #       will need to decide how thats displayed: p text before the radio might work - grey hint
            #       on grey hint bad
            update_group(
                db_group,
                expression_context=ExpressionContext.build_expression_context(
                    collection=db_group.form.collection, mode="interpolation"
                ),
                add_another=True if form.question_group_is_add_another.data == "yes" else False,
            )
            return redirect(
                url_for(
                    "deliver_grant_funding.list_group_questions",
                    grant_id=grant_id,
                    group_id=db_group.id,
                )
            )
        except GroupContainsAddAnotherException:
            form.question_group_is_add_another.errors.append(  # ty: ignore[unresolved-attribute]
                "A question group cannot be answered more than once if it already contains questions that can "
                "be answered more than once"
            )
        except AddAnotherDependencyException:
            form.question_group_is_add_another.errors.append(  # ty: ignore[unresolved-attribute]
                "A question group cannot be answered more than once if questions elsewhere in the form depend on "
                "questions in this group"
            )
        except AddAnotherNotValidException:
            form.question_group_is_add_another.errors.append(  # ty: ignore[unresolved-attribute]
                "A question group cannot be answered more than once if it is already inside a group that can "
                "be answered more than once"
            )

    return render_template(
        "deliver_grant_funding/collections/change_question_group_add_another_options.html",
        grant=db_group.form.collection.grant,
        group=db_group,
        db_form=db_group.form,
        form=form,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/section/<uuid:form_id>/questions", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.MEMBER)
@auto_commit_after_request
def list_section_questions(grant_id: UUID, form_id: UUID) -> ResponseReturnValue:
    db_form = get_form_by_id(form_id, grant_id=grant_id, with_all_questions=True)

    preview_form = GenericSubmitForm()
    if preview_form.validate_on_submit() and preview_form.submit.data:
        return start_previewing_collection(db_form.collection, form=db_form)

    delete_wtform = GenericConfirmDeletionForm() if "delete" in request.args else None
    if delete_wtform:
        if not AuthorisationHelper.can_edit_collection(user=get_current_user(), collection_id=db_form.collection_id):
            return redirect(url_for("deliver_grant_funding.list_section_questions", grant_id=grant_id, form_id=form_id))

        if db_form.collection.live_submissions:
            # Prevent changes to the section if it has any live submissions; this is very coarse layer of protection. We
            # might want to do something more fine-grained to give a better user experience at some point. And/or we
            # might need to allow _some_ people (eg platform admins) to make changes, at their own peril.
            # TODO: flash and redirect back to 'list report sections'?
            current_app.logger.info(
                "Blocking access to delete form %(form_id)s because related collection has live submissions",
                dict(form_id=str(form_id)),
            )
            abort(403)

        if delete_wtform.validate_on_submit():
            try:
                raise_if_component_or_section_has_any_dependencies(db_form)

                delete_form(db_form)

                return redirect(
                    url_for(
                        "deliver_grant_funding.list_collection_sections",
                        grant_id=grant_id,
                        collection_type=db_form.collection.type,
                        collection_id=db_form.collection_id,
                    )
                )

            except SectionComponentDependencyException as e:
                flash(e.as_flash_context(), FlashMessageType.SECTION_COMPONENT_DEPENDENCY_ERROR.value)  # ty: ignore[invalid-argument-type]
                return redirect(
                    url_for(
                        "deliver_grant_funding.list_section_questions",
                        grant_id=grant_id,
                        form_id=form_id,
                    )
                )

    return render_template(
        "deliver_grant_funding/collections/list_section_questions.html",
        grant=db_form.collection.grant,
        db_form=db_form,
        delete_form=delete_wtform,
        form=preview_form,
        interpolate=SubmissionHelper.get_interpolator(collection=db_form.collection),
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/group/<uuid:group_id>/questions", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.MEMBER)
@auto_commit_after_request
def list_group_questions(grant_id: UUID, group_id: UUID) -> ResponseReturnValue:
    group = get_group_by_id(group_id)

    delete_wtform = GenericConfirmDeletionForm() if "delete" in request.args else None
    if delete_wtform:
        if not AuthorisationHelper.can_edit_collection(user=get_current_user(), collection_id=group.form.collection_id):
            return redirect(url_for("deliver_grant_funding.list_group_questions", grant_id=grant_id, group_id=group_id))

        try:
            raise_if_component_or_section_has_any_dependencies(group)
            if delete_wtform.validate_on_submit() and delete_wtform.confirm_deletion.data:
                delete_question(group)
                if group.parent and group.parent.is_group:
                    return redirect(
                        url_for(
                            "deliver_grant_funding.list_group_questions",
                            grant_id=grant_id,
                            group_id=group.parent.id,
                        )
                    )
                return redirect(
                    url_for("deliver_grant_funding.list_section_questions", grant_id=grant_id, form_id=group.form_id)
                )
        except DependencyOrderException as e:
            flash(e.as_flash_context(), FlashMessageType.DEPENDENCY_ORDER_ERROR.value)  # ty: ignore[invalid-argument-type]
            return redirect(url_for("deliver_grant_funding.list_group_questions", grant_id=grant_id, group_id=group_id))

    return render_template(
        "deliver_grant_funding/collections/list_group_questions.html",
        grant=group.form.collection.grant,
        db_form=group.form,
        delete_form=delete_wtform,
        group=group,
        interpolate=SubmissionHelper.get_interpolator(collection=group.form.collection),
    )


class AddQuestionGroup(BaseModel):
    group_name: str
    show_questions_on_the_same_page: bool | None = None

    def to_session_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)

    @classmethod
    def from_session(cls, session_data: dict[str, Any]) -> AddQuestionGroup:
        return cls.model_validate(session_data)


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/section/<uuid:form_id>/groups/add",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
@auto_commit_after_request
def add_question_group_name(grant_id: UUID, form_id: UUID) -> ResponseReturnValue:
    form = get_form_by_id(form_id)
    group_name = request.args.get("name", None)

    parent_id = request.args.get("parent_id", None)
    parent = get_group_by_id(UUID(parent_id)) if parent_id else None

    if parent:
        try:
            raise_if_nested_group_creation_not_valid_here(parent=parent)
        except (NestedGroupException, NestedGroupDisplayTypeSamePageException) as e:
            flash(e.as_flash_context(), FlashMessageType.NESTED_GROUP_ERROR.value)  # ty: ignore[invalid-argument-type]
            return redirect(
                url_for("deliver_grant_funding.list_group_questions", grant_id=grant_id, group_id=parent.id)
            )

    wt_form = GroupForm(name=group_name, check_name_exists=True, group_form_id=form_id)

    if wt_form.validate_on_submit():
        assert wt_form.name.data is not None
        session["add_question_group"] = AddQuestionGroup(group_name=wt_form.name.data).to_session_dict()
        return redirect(
            url_for(
                "deliver_grant_funding.add_question_group_display_options",
                grant_id=grant_id,
                form_id=form_id,
                parent_id=parent.id if parent else None,
            )
        )

    return render_template(
        "deliver_grant_funding/collections/add_question_group_name.html",
        grant=form.collection.grant,
        db_form=form,
        form=wt_form,
        parent=parent,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/section/<uuid:form_id>/groups/add/display_options",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
@auto_commit_after_request
def add_question_group_display_options(grant_id: UUID, form_id: UUID) -> ResponseReturnValue:
    form = get_form_by_id(form_id)

    parent_id = request.args.get("parent_id", None)
    parent = get_group_by_id(UUID(parent_id)) if parent_id else None

    skip_add_another = parent and parent.add_another

    try:
        add_question_group = AddQuestionGroup.from_session(session.get("add_question_group", {}))
    except ValidationError:
        return redirect(
            url_for(
                "deliver_grant_funding.add_question_group_name",
                grant_id=grant_id,
                form_id=form_id,
                parent_id=parent.id if parent else None,
            )
        )

    wt_form = GroupDisplayOptionsForm()
    if add_question_group.show_questions_on_the_same_page is not None and not wt_form.is_submitted():
        wt_form.show_questions_on_the_same_page.data = (
            GroupDisplayOptions.ALL_QUESTIONS_ON_SAME_PAGE
            if add_question_group.show_questions_on_the_same_page
            else GroupDisplayOptions.ONE_QUESTION_PER_PAGE
        )

    if wt_form.validate_on_submit():
        add_question_group.show_questions_on_the_same_page = (
            wt_form.show_questions_on_the_same_page.data == GroupDisplayOptions.ALL_QUESTIONS_ON_SAME_PAGE
        )
        session["add_question_group"] = add_question_group.to_session_dict()

        return redirect(
            url_for(
                "deliver_grant_funding.add_question_group_add_another_option",
                grant_id=grant_id,
                form_id=form_id,
                parent_id=parent.id if parent else None,
            )
        )

    return render_template(
        "deliver_grant_funding/collections/add_question_group_display_options.html",
        grant=form.collection.grant,
        db_form=form,
        group_name=add_question_group.group_name,
        form=wt_form,
        parent=parent,
        skip_add_another=skip_add_another,
        interpolate=SubmissionHelper.get_interpolator(collection=form.collection),
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/section/<uuid:form_id>/groups/add/add_another",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
@auto_commit_after_request
def add_question_group_add_another_option(grant_id: UUID, form_id: UUID) -> ResponseReturnValue:
    form = get_form_by_id(form_id)

    parent_id = request.args.get("parent_id", None)
    parent = get_group_by_id(UUID(parent_id)) if parent_id else None

    skip_add_another = parent and parent.add_another

    try:
        add_question_group = AddQuestionGroup.from_session(session.get("add_question_group", {}))
    except ValidationError:
        return redirect(
            url_for(
                "deliver_grant_funding.add_question_group_name",
                grant_id=grant_id,
                form_id=form_id,
                parent_id=parent.id if parent else None,
            )
        )

    wt_form = GroupAddAnotherOptionsForm(question_group_is_add_another="no")

    if wt_form.validate_on_submit() or skip_add_another:
        try:
            add_another = False if skip_add_another else (wt_form.question_group_is_add_another.data == "yes")
            group = create_group(
                text=InterpolationStatement(add_question_group.group_name),
                form=form,
                parent=parent,
                presentation_options=QuestionPresentationOptions(
                    show_questions_on_the_same_page=add_question_group.show_questions_on_the_same_page
                ),
                add_another=add_another,
            )
            session.pop("add_question_group", None)
            return redirect(
                url_for(
                    "deliver_grant_funding.list_group_questions", grant_id=grant_id, form_id=form_id, group_id=group.id
                )
            )
        except NestedGroupDisplayTypeSamePageException as e:
            flash(e.as_flash_context(), FlashMessageType.NESTED_GROUP_ERROR.value)  # ty: ignore[invalid-argument-type]
        except NestedGroupException as e:
            flash(e.as_flash_context(), FlashMessageType.NESTED_GROUP_ERROR.value)  # ty: ignore[invalid-argument-type]

    return render_template(
        "deliver_grant_funding/collections/add_question_group_add_another_options.html",
        grant=form.collection.grant,
        db_form=form,
        group_name=add_question_group.group_name,
        form=wt_form,
        parent=parent,
        interpolate=SubmissionHelper.get_interpolator(collection=form.collection),
    )


@deliver_grant_funding_blueprint.route("/grant/<uuid:grant_id>/question/<uuid:component_id>/move-<direction>")
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
@auto_commit_after_request
def move_component(grant_id: UUID, component_id: UUID, direction: str) -> ResponseReturnValue:
    component = get_component_by_id(component_id)

    try:
        match direction:
            case "up":
                move_component_up(component)
            case "down":
                move_component_down(component)
            case _:
                return abort(400)
    except DependencyOrderException as e:
        flash(e.as_flash_context(), FlashMessageType.DEPENDENCY_ORDER_ERROR.value)  # ty: ignore[invalid-argument-type]

    source = request.args.get("source", None)
    if source:
        return redirect(url_for("deliver_grant_funding.list_group_questions", grant_id=grant_id, group_id=source))
    else:
        return redirect(
            url_for("deliver_grant_funding.list_section_questions", grant_id=grant_id, form_id=component.form_id)
        )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/section/<uuid:form_id>/questions/add/choose-type",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
def choose_question_type(grant_id: UUID, form_id: UUID) -> ResponseReturnValue:
    db_form = get_form_by_id(form_id)
    wt_form = QuestionTypeForm(question_data_type=request.args.get("question_data_type", None))

    parent_id = request.args.get("parent_id", None)
    parent = get_group_by_id(UUID(parent_id)) if parent_id else None

    if wt_form.validate_on_submit():
        question_data_type = wt_form.question_data_type.data

        if "question" in session:
            del session["question"]

        return redirect(
            url_for(
                "deliver_grant_funding.add_question",
                grant_id=grant_id,
                form_id=form_id,
                question_data_type=question_data_type,
                parent_id=parent_id if parent else None,
            )
        )

    return render_template(
        "deliver_grant_funding/collections/choose_question_type.html",
        grant=db_form.collection.grant,
        db_form=db_form,
        form=wt_form,
        parent=parent,
    )


def _extract_add_context_data_from_session(
    session_model: type[SessionModelType] | None = None,
    component_id: UUID | TNotProvided | None = NOT_PROVIDED,
    expression_id: UUID | TNotProvided | None = NOT_PROVIDED,
) -> SessionModelType | None:
    add_context_data: SessionModelType | None = None
    if session_data := session.get("question"):
        match session_data["field"]:
            case "component":
                add_context_data = AddContextToComponentSessionModel(**session_data)
                if component_id is not NOT_PROVIDED and component_id != add_context_data.component_id:
                    del session["question"]
                    return None

            case "guidance":
                add_context_data = AddContextToComponentGuidanceSessionModel(**session_data)
                if component_id is not NOT_PROVIDED and component_id != add_context_data.component_id:
                    del session["question"]
                    return None

            case "condition_depends_on":
                add_context_data = AddConditionDependsOnSessionModel(**session_data)
                if component_id is not NOT_PROVIDED and component_id != add_context_data.component_id:
                    del session["question"]
                    return None

            case ExpressionType.CONDITION | ExpressionType.VALIDATION:
                add_context_data = AddContextToExpressionsModel(**session_data)
                if (component_id is not NOT_PROVIDED and component_id != add_context_data.component_id) or (
                    expression_id is not NOT_PROVIDED and expression_id != add_context_data.expression_id
                ):
                    del session["question"]
                    return None

                if add_context_data.is_custom:
                    expression_cls = CustomExpression
                else:
                    expression_cls = lookup_managed_expression(
                        add_context_data.managed_expression_name  # ty:ignore[invalid-argument-type]
                    )

                add_context_data._prepared_form_data = expression_cls.prepare_form_data(add_context_data)
                # Populate the `type` of the form from `build_managed_expression_form` so that the general
                # ManagedExpression selection is preserved.
                add_context_data._prepared_form_data["type"] = add_context_data.managed_expression_name

            case _:
                raise ValueError(f"Unexpected field type: {session_data['field']}")
    else:
        return None

    if add_context_data and session_model and not isinstance(add_context_data, session_model):
        del session["question"]
        return None

    return add_context_data


def _store_question_state_and_redirect_to_add_context(
    form: QuestionForm
    | AddGuidanceForm
    | _ManagedExpressionForm
    | CustomValidationExpressionForm
    | CalculatedConditionForm,
    grant_id: UUID,
    form_id: UUID,
    component_id: UUID | None = None,
    parent_id: UUID | None = None,
    form_data: dict[str, Any] | None = None,
    expression_type: ExpressionType | None = None,
    managed_expression_name: ManagedExpressionsEnum | None = None,
    expression_id: UUID | None = None,
    subject_reference: ExpressionReference | None = None,
    is_add_another_guidance: bool | None = False,
    is_custom: bool | None = False,
    is_group: bool = False,
) -> ResponseReturnValue:
    add_context_data: SessionModelType
    match form:
        case QuestionForm():
            add_context_data = AddContextToComponentSessionModel(
                data_type=form._question_type,
                component_form_data=cast(dict[str, Any], form_data),
                component_id=component_id,
                parent_id=parent_id,
            )
        case AddGuidanceForm():
            if component_id is None:
                raise ValueError()
            add_context_data = AddContextToComponentGuidanceSessionModel(
                component_form_data=cast(dict[str, Any], form_data),
                component_id=component_id,
                parent_id=parent_id,
                is_add_another_guidance=is_add_another_guidance,
            )
        case _ManagedExpressionForm() | CustomValidationExpressionForm() | CalculatedConditionForm():
            add_context_data = AddContextToExpressionsModel(
                field=expression_type,
                managed_expression_name=managed_expression_name,
                expression_form_data=form_data,  # ty: ignore[invalid-argument-type]
                component_id=component_id,  # ty: ignore[invalid-argument-type]
                parent_id=parent_id,
                expression_id=expression_id,
                subject_reference=subject_reference,
                is_custom=is_custom or False,
                is_group=is_group,
            )
        case _:
            raise ValueError(f"Unexpected form type: {form}")
    # TODO: define a parent pydantic model for all of our session context
    session["question"] = add_context_data.model_dump(mode="json")
    return redirect(
        url_for("deliver_grant_funding.select_context_source", grant_id=grant_id, form_id=form_id, parent_id=parent_id)
    )


def _handle_remove_context_for_expression_forms(
    form: _ManagedExpressionForm,
    component_id: UUID,
    expression_type: ExpressionType,
    expression: Expression | None = None,
    add_context_data: AddContextToExpressionsModel | None = None,
    subject_reference: ExpressionReference | None = None,
) -> None:
    field_to_clear = form.remove_context.data  # ty: ignore[unresolved-attribute]
    if not field_to_clear:
        return

    form_data = form.get_expression_form_data()

    if not add_context_data:
        if not expression:
            raise ValueError("Expression required when add_context_data is None")

        add_context_data = AddContextToExpressionsModel(
            field=expression_type,
            managed_expression_name=expression.managed_name,
            expression_form_data=form_data,
            component_id=component_id,
            expression_id=expression.id,
            subject_reference=subject_reference,
        )
    else:
        add_context_data.expression_form_data.update(form_data)

    add_context_data.expression_form_data[field_to_clear] = ""

    if expression:
        add_context_data._prepared_form_data = expression.managed.prepare_form_data(add_context_data)
        add_context_data._prepared_form_data["type"] = expression.managed_name
    else:
        managed_expression = lookup_managed_expression(add_context_data.managed_expression_name)  # ty:ignore[invalid-argument-type]
        add_context_data._prepared_form_data = managed_expression.prepare_form_data(add_context_data)
        add_context_data._prepared_form_data["type"] = add_context_data.managed_expression_name

    session["question"] = add_context_data.model_dump(mode="json")


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/section/<uuid:form_id>/questions/add",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
@auto_commit_after_request
def add_question(grant_id: UUID, form_id: UUID) -> ResponseReturnValue:
    form = get_form_by_id(form_id)
    question_data_type_arg = request.args.get("question_data_type", QuestionDataType.TEXT_SINGLE_LINE.name)
    question_data_type_enum = QuestionDataType.coerce(question_data_type_arg)
    raw_parent_id = request.args.get("parent_id", None)
    parent_id = UUID(raw_parent_id) if raw_parent_id else None
    parent = get_group_by_id(parent_id) if parent_id else None

    add_context_data = _extract_add_context_data_from_session(
        session_model=AddContextToComponentSessionModel, component_id=None
    )

    wt_form = QuestionForm(
        data=add_context_data.component_form_data if add_context_data else None,  # ty: ignore[unresolved-attribute]
        question_type=question_data_type_enum,
    )

    if wt_form.is_submitted_to_add_context():
        form_data = wt_form.get_component_form_data()
        return _store_question_state_and_redirect_to_add_context(
            wt_form, grant_id=grant_id, form_id=form_id, parent_id=parent_id, form_data=form_data
        )

    elif wt_form.validate_on_submit():
        try:
            assert wt_form.text.data is not None
            assert wt_form.hint.data is not None
            assert wt_form.name.data is not None

            question = create_question(
                form=form,
                text=wt_form.text.data,
                hint=wt_form.hint.data,
                name=wt_form.name.data,
                data_type=question_data_type_enum,
                items=wt_form.normalised_data_source_items,
                presentation_options=QuestionPresentationOptions.from_question_form(wt_form),
                expression_context=ExpressionContext.build_expression_context(
                    collection=form.collection, mode="interpolation"
                ),
                parent=parent,
                data_options=QuestionDataOptions.from_question_form(wt_form),
            )
            flash("Question created", FlashMessageType.QUESTION_CREATED)

            if "question" in session:
                del session["question"]

            return redirect(
                url_for(
                    "deliver_grant_funding.edit_question",
                    grant_id=grant_id,
                    question_id=question.id,
                )
            )
        except DuplicateValueError as e:
            field_with_error: Field = getattr(wt_form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # ty: ignore[unresolved-attribute]
        except InvalidReferenceInExpression as e:
            field_with_error = getattr(wt_form, e.field_name)  # ty:ignore[invalid-argument-type]
            field_with_error.errors.append(e.form_error_message)

    return render_template(
        "deliver_grant_funding/collections/add_question.html",
        grant=form.collection.grant,
        collection=form.collection,
        db_form=form,
        chosen_question_data_type=question_data_type_enum,
        form=wt_form,
        parent=parent,
        context_keys_and_labels=ExpressionContext.get_context_keys_and_labels(collection=form.collection),
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/section/<uuid:form_id>/add-context/select-source", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
def select_context_source(grant_id: UUID, form_id: UUID) -> ResponseReturnValue:
    db_form = get_form_by_id(form_id)
    add_context_data = _extract_add_context_data_from_session()
    if not add_context_data:
        return abort(400)

    this_component = get_component_by_id(add_context_data.component_id) if add_context_data.component_id else None

    wtform = AddContextSelectSourceForm(
        form=db_form,
        current_component=this_component,
        parent_component=get_group_by_id(add_context_data.parent_id) if add_context_data.parent_id else None,
        include_this_component=add_context_data.include_current_component_when_referencing_data(this_component),
    )
    question = cast("Question", this_component)
    if wtform.validate_on_submit():
        if wtform.data_source.data == "THIS_QUESTION":
            redirect_response = redirect(
                _determine_return_url_and_update_session_after_choosing_reference_for_expression(
                    grant_id,
                    add_context_data,  # ty:ignore[invalid-argument-type]
                    ExpressionReference.from_question(question),
                )
            )
        else:
            add_context_data.data_source = ExpressionContext.ContextSources[wtform.data_source.data]

            redirect_response = None
            match add_context_data.data_source:
                case ExpressionContext.ContextSources.SECTION:
                    redirect_response = redirect(
                        url_for(
                            "deliver_grant_funding.select_context_source_question", grant_id=grant_id, form_id=form_id
                        )
                    )
                    add_context_data.collection_id = db_form.collection_id
                    add_context_data.form_id = db_form.id

                case ExpressionContext.ContextSources.PREVIOUS_SECTION:
                    redirect_response = redirect(
                        url_for(
                            "deliver_grant_funding.select_context_source_section", grant_id=grant_id, form_id=form_id
                        )
                    )
                    add_context_data.collection_id = db_form.collection_id

                case ExpressionContext.ContextSources.PREVIOUS_COLLECTION:
                    redirect_response = redirect(
                        url_for(
                            "deliver_grant_funding.select_context_source_collection", grant_id=grant_id, form_id=form_id
                        )
                    )

                case ExpressionContext.ContextSources.DATASET:
                    redirect_response = redirect(
                        url_for(
                            "deliver_grant_funding.select_context_source_data_set", grant_id=grant_id, form_id=form_id
                        )
                    )

                case _:
                    wtform.form_errors.append("Unknown data source selected")

        session["question"] = add_context_data.model_dump(mode="json")
        if redirect_response:
            return redirect_response

    return render_template(
        "deliver_grant_funding/collections/select_context_source.html",
        grant=db_form.collection.grant,
        db_form=db_form,
        form=wtform,
        add_context_data=add_context_data,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/section/<uuid:form_id>/add-context/select-collection", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
def select_context_source_collection(grant_id: UUID, form_id: UUID) -> ResponseReturnValue:
    return abort(404)


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/section/<uuid:form_id>/add-context/select-section", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
def select_context_source_section(grant_id: UUID, form_id: UUID) -> ResponseReturnValue:
    db_form = get_form_by_id(form_id)

    add_context_data = _extract_add_context_data_from_session()
    if not add_context_data:
        return abort(400)

    assert add_context_data.collection_id

    # We want to show all sections before the section that the source component is in
    current_component = get_component_by_id(add_context_data.component_id) if add_context_data.component_id else None

    wtform = SelectDataSourceSectionForm(current_form=current_component.form if current_component else db_form)
    if wtform.validate_on_submit():
        referenced_section = get_form_by_id(uuid.UUID(wtform.section.data))
        add_context_data.form_id = referenced_section.id
        session["question"] = add_context_data.model_dump(mode="json")
        return redirect(
            url_for("deliver_grant_funding.select_context_source_question", grant_id=grant_id, form_id=form_id)
        )

    return render_template(
        "deliver_grant_funding/collections/select_context_source_section.html",
        grant=db_form.collection.grant,
        db_form=db_form,
        form=wtform,
        add_context_data=add_context_data,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/section/<uuid:form_id>/add-context/select-data-set", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
def select_context_source_data_set(grant_id: UUID, form_id: UUID) -> ResponseReturnValue:
    db_form = get_form_by_id(form_id)

    add_context_data = _extract_add_context_data_from_session()
    if not add_context_data:
        return abort(400)

    number_columns_only = isinstance(
        add_context_data, (AddConditionDependsOnSessionModel, AddContextToExpressionsModel)
    )
    wtform = SelectDataSourceDataSetForm(
        collection=db_form.collection, data=request.args, number_columns_only=number_columns_only
    )

    if wtform.validate_on_submit():
        reference_data_set = get_data_source(uuid.UUID(wtform.data_set.data))
        return redirect(
            url_for(
                "deliver_grant_funding.select_context_source_data_set_column",
                grant_id=grant_id,
                form_id=form_id,
                data_set_id=reference_data_set.id,
            )
        )

    return render_template(
        "deliver_grant_funding/collections/select_context_source_data_set.html",
        grant=db_form.collection.grant,
        form=wtform,
        db_form=db_form,
        add_context_data=add_context_data,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/section/<uuid:form_id>/add-context/data-set/<uuid:data_set_id>/select-column",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
def select_context_source_data_set_column(grant_id: UUID, form_id: UUID, data_set_id: UUID) -> ResponseReturnValue:
    db_form = get_form_by_id(form_id)
    data_set = get_data_source(data_set_id)

    if data_set.collection_id != db_form.collection_id:
        return abort(404)

    add_context_data = _extract_add_context_data_from_session()
    if not add_context_data:
        return abort(400)

    number_columns_only = isinstance(
        add_context_data, (AddConditionDependsOnSessionModel, AddContextToExpressionsModel)
    )
    wtform = SelectDataSourceDataSetColumnForm(data_set=data_set, number_columns_only=number_columns_only)

    if wtform.validate_on_submit():
        safe_column_id = wtform.column.data
        reference = ExpressionReference.from_data_source_column(data_set, safe_column_id)

        match add_context_data:
            case AddConditionDependsOnSessionModel():
                del session["question"]
                return redirect(
                    url_for(
                        "deliver_grant_funding.add_question_condition",
                        grant_id=grant_id,
                        component_id=add_context_data.component_id,
                        subject_reference=reference,
                    )
                )

            case AddContextToComponentSessionModel():
                return_url = (
                    url_for(
                        "deliver_grant_funding.add_question",
                        grant_id=grant_id,
                        form_id=form_id,
                        parent_id=add_context_data.parent_id,
                        question_data_type=add_context_data.data_type.name,
                    )
                    if add_context_data.component_id is None
                    else url_for(
                        "deliver_grant_funding.edit_question",
                        grant_id=grant_id,
                        question_id=add_context_data.component_id,
                    )
                )

                if add_context_data and isinstance(add_context_data, AddContextToComponentSessionModel):
                    target_field = add_context_data.component_form_data["add_context"]
                    add_context_data.component_form_data[target_field] += f" {reference.wrapped}"

            case AddContextToComponentGuidanceSessionModel():
                return_url = (
                    url_for(
                        "deliver_grant_funding.manage_guidance",
                        grant_id=grant_id,
                        question_id=add_context_data.component_id,
                    )
                    if add_context_data.is_add_another_guidance is False
                    else url_for(
                        "deliver_grant_funding.manage_add_another_guidance",
                        grant_id=grant_id,
                        group_id=add_context_data.component_id,
                    )
                )
                if add_context_data and isinstance(add_context_data, AddContextToComponentGuidanceSessionModel):
                    target_field = add_context_data.component_form_data["add_context"]
                    add_context_data.component_form_data[target_field] += f" {reference.wrapped}"

            case AddContextToExpressionsModel():
                return_url = _determine_return_url_and_update_session_after_choosing_reference_for_expression(
                    grant_id, add_context_data, reference
                )

        session["question"] = add_context_data.model_dump(mode="json")
        return redirect(return_url)

    return render_template(
        "deliver_grant_funding/collections/select_context_source_data_set_column.html",
        grant=db_form.collection.grant,
        form=wtform,
        db_form=db_form,
        data_set=data_set,
        add_context_data=add_context_data,
    )


def _determine_return_url_and_update_session_after_choosing_reference_for_expression(
    grant_id: UUID, add_context_data: AddContextToExpressionsModel, reference: ExpressionReference
) -> str:
    if add_context_data and isinstance(add_context_data, AddContextToExpressionsModel):
        target_field = add_context_data.expression_form_data["add_context"]
        if add_context_data.managed_expression_name is None:
            add_context_data.expression_form_data[target_field] += f" {reference.wrapped}"
        else:
            add_context_data.expression_form_data[target_field] = reference.wrapped

    if add_context_data.field == ExpressionType.CONDITION:
        if not add_context_data.expression_id:
            if add_context_data.managed_expression_name is None:
                return_url = url_for(
                    "deliver_grant_funding.add_calculated_condition",
                    grant_id=grant_id,
                    component_id=add_context_data.component_id,
                )
            else:
                return_url = url_for(
                    "deliver_grant_funding.add_question_condition",
                    grant_id=grant_id,
                    component_id=add_context_data.component_id,
                    subject_reference=add_context_data.subject_reference,
                )
        else:
            if add_context_data.managed_expression_name is None:
                return_url = url_for(
                    "deliver_grant_funding.edit_calculated_condition",
                    grant_id=grant_id,
                    expression_id=add_context_data.expression_id,
                )
            else:
                return_url = url_for(
                    "deliver_grant_funding.edit_question_condition",
                    grant_id=grant_id,
                    expression_id=add_context_data.expression_id,
                )
    else:
        if add_context_data.is_group:
            if not add_context_data.expression_id:
                return_url = url_for(
                    "deliver_grant_funding.add_group_validation",
                    grant_id=grant_id,
                    group_id=add_context_data.component_id,
                )
            else:
                return_url = url_for(
                    "deliver_grant_funding.edit_group_validation",
                    grant_id=grant_id,
                    group_id=add_context_data.component_id,
                    expression_id=add_context_data.expression_id,
                )
        elif not add_context_data.expression_id:
            if add_context_data.managed_expression_name is None:
                return_url = url_for(
                    "deliver_grant_funding.add_custom_question_validation",
                    grant_id=grant_id,
                    question_id=add_context_data.component_id,
                )
            else:
                return_url = url_for(
                    "deliver_grant_funding.add_question_validation",
                    grant_id=grant_id,
                    question_id=add_context_data.component_id,
                )
        else:
            if add_context_data.managed_expression_name is None:
                return_url = url_for(
                    "deliver_grant_funding.edit_custom_question_validation",
                    grant_id=grant_id,
                    question_id=add_context_data.component_id,
                    expression_id=add_context_data.expression_id,
                )
            else:
                return_url = url_for(
                    "deliver_grant_funding.edit_question_validation",
                    grant_id=grant_id,
                    expression_id=add_context_data.expression_id,
                )
    return return_url


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/section/<uuid:form_id>/add-context/select-question-from-section", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
def select_context_source_question(grant_id: UUID, form_id: UUID) -> ResponseReturnValue:  # noqa: C901
    db_form = get_form_by_id(form_id)

    add_context_data = _extract_add_context_data_from_session()
    if not add_context_data:
        return abort(400)

    assert add_context_data.collection_id
    assert add_context_data.form_id
    target_form = get_form_by_id(add_context_data.form_id)

    subject_reference = getattr(add_context_data, "subject_reference", None)
    current_component = get_component_by_id(add_context_data.component_id) if add_context_data.component_id else None

    wtform = SelectDataSourceQuestionForm(
        form=target_form,
        interpolate=SubmissionHelper.get_interpolator(collection=db_form.collection),
        current_component=current_component,
        subject_reference=subject_reference,
        parent_component=get_group_by_id(add_context_data.parent_id) if add_context_data.parent_id else None,
        expression_type=add_context_data.field if isinstance(add_context_data, AddContextToExpressionsModel) else None,
        managed_expression_name=add_context_data.managed_expression_name
        if isinstance(add_context_data, AddContextToExpressionsModel)
        else None,
        include_this_component=add_context_data.include_current_component_when_referencing_data(current_component),
    )

    if wtform.validate_on_submit():
        reference = wtform.question.data
        if not reference.question and not reference.data_source_column:
            abort(400)

        match add_context_data:
            case AddConditionDependsOnSessionModel():
                del session["question"]
                return redirect(
                    url_for(
                        "deliver_grant_funding.add_question_condition",
                        grant_id=grant_id,
                        component_id=add_context_data.component_id,
                        subject_reference=reference,
                    )
                )
            case AddContextToComponentSessionModel():
                return_url = (
                    url_for(
                        "deliver_grant_funding.add_question",
                        grant_id=grant_id,
                        form_id=form_id,
                        parent_id=add_context_data.parent_id,
                        question_data_type=add_context_data.data_type.name,
                    )
                    if add_context_data.component_id is None
                    else url_for(
                        "deliver_grant_funding.edit_question",
                        grant_id=grant_id,
                        question_id=add_context_data.component_id,
                    )
                )

                if add_context_data and isinstance(add_context_data, AddContextToComponentSessionModel):
                    target_field = add_context_data.component_form_data["add_context"]
                    add_context_data.component_form_data[target_field] += " " + reference.wrapped

            case AddContextToComponentGuidanceSessionModel():
                return_url = (
                    url_for(
                        "deliver_grant_funding.manage_guidance",
                        grant_id=grant_id,
                        question_id=add_context_data.component_id,
                    )
                    if add_context_data.is_add_another_guidance is False
                    else url_for(
                        "deliver_grant_funding.manage_add_another_guidance",
                        grant_id=grant_id,
                        group_id=add_context_data.component_id,
                    )
                )
                if add_context_data and isinstance(add_context_data, AddContextToComponentGuidanceSessionModel):
                    target_field = add_context_data.component_form_data["add_context"]
                    add_context_data.component_form_data[target_field] += " " + reference.wrapped

            case AddContextToExpressionsModel():
                return_url = _determine_return_url_and_update_session_after_choosing_reference_for_expression(
                    grant_id, add_context_data, reference
                )

        session["question"] = add_context_data.model_dump(mode="json")
        return redirect(return_url)

    return render_template(
        "deliver_grant_funding/collections/select_context_source_question.html",
        grant=db_form.collection.grant,
        db_form=db_form,
        form=wtform,
        add_context_data=add_context_data,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/question/<uuid:question_id>",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
@auto_commit_after_request
def edit_question(grant_id: UUID, question_id: UUID) -> ResponseReturnValue:  # noqa: C901
    # FIXME: It would be better if the add_question and edit_question endpoints were an all-in-one. The complication
    #        for doing this is around adding conditions and validations when creating a new question. At the moment
    #        both of those endpoints expect to attach it to an existing question in the DB, but through an
    #        'add question' flow that question record doesn't exist yet. We'd need to cache info about
    #        validation+conditions that need to be added to the question, when the question itself is created.
    question = get_question_by_id(question_id=question_id)

    add_context_data = _extract_add_context_data_from_session(
        session_model=AddContextToComponentSessionModel, component_id=question_id
    )

    wt_form = QuestionForm(
        obj=question if not add_context_data else None,
        data=add_context_data.component_form_data if add_context_data else None,  # ty: ignore[unresolved-attribute]
        question_type=question.data_type,
    )

    if wt_form.is_submitted_to_add_context():
        form_data = wt_form.get_component_form_data()
        return _store_question_state_and_redirect_to_add_context(
            wt_form,
            grant_id=grant_id,
            form_id=question.form_id,
            component_id=question.id,
            parent_id=question.parent_id,
            form_data=form_data,
        )

    confirm_deletion_form = GenericConfirmDeletionForm()
    if "delete" in request.args:
        try:
            raise_if_component_or_section_has_any_dependencies(question)

            if confirm_deletion_form.validate_on_submit() and confirm_deletion_form.confirm_deletion.data:
                delete_question(question)
                if question.parent and question.parent.is_group:
                    return redirect(
                        url_for(
                            "deliver_grant_funding.list_group_questions",
                            grant_id=grant_id,
                            group_id=question.parent.id,
                        )
                    )
                return redirect(
                    url_for("deliver_grant_funding.list_section_questions", grant_id=grant_id, form_id=question.form_id)
                )

        except DependencyOrderException as e:
            flash(e.as_flash_context(), FlashMessageType.DEPENDENCY_ORDER_ERROR.value)  # ty: ignore[invalid-argument-type]
            return redirect(
                url_for(
                    "deliver_grant_funding.edit_question",
                    grant_id=grant_id,
                    form_id=question.form_id,
                    question_id=question_id,
                )
            )

    if wt_form.validate_on_submit():
        try:
            assert wt_form.text.data is not None
            assert wt_form.hint.data is not None
            assert wt_form.name.data is not None
            update_question(
                question=question,
                expression_context=ExpressionContext.build_expression_context(
                    collection=question.form.collection, mode="interpolation"
                ),
                text=wt_form.text.data,
                hint=wt_form.hint.data,
                name=wt_form.name.data,
                items=wt_form.normalised_data_source_items,
                presentation_options=QuestionPresentationOptions.from_question_form(wt_form),
                data_options=QuestionDataOptions.from_question_form(wt_form),
            )

            if "question" in session:
                del session["question"]

            if question.parent and question.parent.is_group:
                return redirect(
                    url_for(
                        "deliver_grant_funding.list_group_questions",
                        grant_id=grant_id,
                        group_id=question.parent.id,
                    )
                )
            return redirect(
                url_for(
                    "deliver_grant_funding.list_section_questions",
                    grant_id=grant_id,
                    form_id=question.form_id,
                )
            )
        except DuplicateValueError as e:
            field_with_error: Field = getattr(wt_form, e.field_name)
            field_with_error.errors.append(f"{field_with_error.name.capitalize()} already in use")  # ty: ignore[unresolved-attribute]
        except InvalidReferenceInExpression as e:
            field_with_error = getattr(wt_form, e.field_name)  # ty:ignore[invalid-argument-type]
            field_with_error.errors.append(e.form_error_message)
        except DependencyOrderException as e:
            field_with_error = getattr(wt_form, e.field_name)  # ty:ignore[invalid-argument-type]
            field_with_error.errors.append(e.form_error_message)
        except DataSourceItemReferenceDependencyException as e:
            for flash_context in e.as_flash_contexts():
                flash(flash_context, FlashMessageType.DATA_SOURCE_ITEM_DEPENDENCY_ERROR.value)  # ty: ignore[invalid-argument-type]
            return redirect(
                url_for(
                    "deliver_grant_funding.edit_question",
                    grant_id=grant_id,
                    form_id=question.form_id,
                    question_id=question_id,
                )
            )

    return render_template(
        "deliver_grant_funding/collections/edit_question.html",
        grant=question.form.collection.grant,
        db_form=question.form,
        question=question,
        form=wt_form,
        confirm_deletion_form=confirm_deletion_form if "delete" in request.args else None,
        managed_validation_available=get_managed_validators_by_data_type(question.data_type),
        interpolate=SubmissionHelper.get_interpolator(collection=question.form.collection),
        context_keys_and_labels=ExpressionContext.get_context_keys_and_labels(
            collection=question.form.collection, expression_context_end_point=question
        ),
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/group/<uuid:group_id>/add_another_guidance", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
@auto_commit_after_request
def manage_add_another_guidance(grant_id: UUID, group_id: UUID) -> ResponseReturnValue:
    group = get_component_by_id(component_id=group_id)
    add_context_data = _extract_add_context_data_from_session(
        session_model=AddContextToComponentGuidanceSessionModel, component_id=group_id
    )

    form = AddGuidanceForm(
        data=add_context_data.component_form_data if add_context_data else None,  # ty: ignore[unresolved-attribute]
        heading_required=False,
    )
    if not add_context_data and not form.is_submitted():
        form.guidance_body.data = group.add_another_guidance_body

    if form.is_submitted_to_add_context():
        form_data = form.get_component_form_data()
        return _store_question_state_and_redirect_to_add_context(
            form,
            grant_id=grant_id,
            form_id=group.form_id,
            component_id=group_id,
            parent_id=group.parent_id,
            form_data=form_data,
            is_add_another_guidance=True,
        )

    if form.validate_on_submit():
        try:
            update_group(
                cast("Group", group),
                expression_context=ExpressionContext.build_expression_context(
                    collection=group.form.collection, mode="interpolation"
                ),
                add_another_guidance_body=form.guidance_body.data,
            )

            if "question" in session:
                del session["question"]

            if form.preview.data:
                return redirect(
                    url_for(
                        "deliver_grant_funding.manage_add_another_guidance",
                        grant_id=grant_id,
                        group_id=group_id,
                        _anchor="preview-guidance",
                    )
                )

            return redirect(url_for("deliver_grant_funding.list_group_questions", grant_id=grant_id, group_id=group.id))

        except InvalidReferenceInExpression as e:
            field_with_error = getattr(form, e.field_name)  # ty:ignore[invalid-argument-type]
            field_with_error.errors.append(e.form_error_message)

    return render_template(
        "deliver_grant_funding/collections/manage_add_another_guidance.html",
        grant=group.form.collection.grant,
        question=group,
        form=form,
        interpolate=SubmissionHelper.get_interpolator(collection=group.form.collection),
        context_keys_and_labels=ExpressionContext.get_context_keys_and_labels(
            collection=group.form.collection, expression_context_end_point=group
        ),
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/question/<uuid:question_id>/guidance", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
@auto_commit_after_request
def manage_guidance(grant_id: UUID, question_id: UUID) -> ResponseReturnValue:
    question = get_component_by_id(component_id=question_id)
    add_context_data = _extract_add_context_data_from_session(
        session_model=AddContextToComponentGuidanceSessionModel, component_id=question_id
    )

    form = AddGuidanceForm(
        obj=question if not add_context_data else None,
        data=add_context_data.component_form_data if add_context_data else None,  # ty: ignore[unresolved-attribute]
    )

    if form.is_submitted_to_add_context():
        form_data = form.get_component_form_data()
        return _store_question_state_and_redirect_to_add_context(
            form,
            grant_id=grant_id,
            form_id=question.form_id,
            component_id=question_id,
            parent_id=question.parent_id,
            form_data=form_data,
        )

    if form.validate_on_submit():
        try:
            # todo: both of these are equivalent as this is a property of the underlying component
            #       should there be an update that handles either
            if question.is_group:
                update_group(
                    cast("Group", question),
                    expression_context=ExpressionContext.build_expression_context(
                        collection=question.form.collection, mode="interpolation"
                    ),
                    guidance_heading=form.guidance_heading.data,
                    guidance_body=form.guidance_body.data,
                )
            else:
                update_question(
                    cast("Question", question),
                    expression_context=ExpressionContext.build_expression_context(
                        collection=question.form.collection, mode="interpolation"
                    ),
                    guidance_heading=form.guidance_heading.data,
                    guidance_body=form.guidance_body.data,
                )

            if "question" in session:
                del session["question"]

            if form.preview.data:
                return redirect(
                    url_for(
                        "deliver_grant_funding.manage_guidance",
                        grant_id=grant_id,
                        question_id=question_id,
                        _anchor="preview-guidance",
                    )
                )

            return redirect(
                url_for("deliver_grant_funding.edit_question", grant_id=grant_id, question_id=question_id)
                if not question.is_group
                else url_for("deliver_grant_funding.list_group_questions", grant_id=grant_id, group_id=question.id)
            )

        except InvalidReferenceInExpression as e:
            field_with_error = getattr(form, e.field_name)  # ty:ignore[invalid-argument-type]
            field_with_error.errors.append(e.message)

    # Build expression context for reference mappings
    return render_template(
        "deliver_grant_funding/collections/manage_guidance.html",
        grant=question.form.collection.grant,
        question=question,
        form=form,
        interpolate=SubmissionHelper.get_interpolator(collection=question.form.collection),
        context_keys_and_labels=ExpressionContext.get_context_keys_and_labels(
            collection=question.form.collection, expression_context_end_point=question
        ),
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/question/<uuid:component_id>/add-calculated-condition",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
@auto_commit_after_request
def add_calculated_condition(grant_id: UUID, component_id: UUID) -> ResponseReturnValue:
    component = get_component_by_id(component_id=component_id)
    add_context_data = _extract_add_context_data_from_session(
        session_model=AddContextToExpressionsModel, component_id=component.id
    )
    wt_form = CalculatedConditionForm(
        data=add_context_data._prepared_form_data if add_context_data else None,  # ty:ignore[unresolved-attribute]
        component=component,
        interpolation_context=(
            ExpressionContext.build_expression_context(
                component.form.collection,
                "interpolation",
            )
        ),
        evaluation_context=(
            ExpressionContext.build_expression_context(
                component.form.collection,
                "evaluation",
            )
        ),
    )
    if wt_form.is_submitted_to_add_context():
        form_data = wt_form.get_expression_form_data()
        return _store_question_state_and_redirect_to_add_context(
            form=wt_form,
            grant_id=grant_id,
            form_id=component.form.id,
            component_id=component.id,
            parent_id=component.parent_id,
            form_data=form_data,
            expression_type=ExpressionType.CONDITION,
            is_custom=True,
        )

    if wt_form.validate_on_submit():
        expression = CustomExpression.build_from_form(wt_form)
        interfaces.collections.add_component_condition(component, get_current_user(), expression)

        if "question" in session:
            del session["question"]
        if component.is_question:
            return redirect(
                url_for(
                    "deliver_grant_funding.edit_question",
                    grant_id=grant_id,
                    question_id=component.id,
                )
            )

        else:
            return redirect(
                url_for("deliver_grant_funding.list_group_questions", grant_id=grant_id, group_id=component_id)
            )

    # Note: Mild shortcut; the alternative is passing this through a lot of templates/template logic
    g.context_keys_and_labels = ExpressionContext.get_context_keys_and_labels(
        collection=component.form.collection,
    )
    return render_template(
        "deliver_grant_funding/collections/calculated_condition.html",
        grant=component.form.collection.grant,
        component=component,
        form=wt_form,
        interpolate=SubmissionHelper.get_interpolator(component.form.collection),
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/calculated-condition/<uuid:expression_id>",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
@auto_commit_after_request
def edit_calculated_condition(grant_id: UUID, expression_id: UUID) -> ResponseReturnValue:

    expression = get_expression_by_id(expression_id)
    component = expression.question
    add_context_data = _extract_add_context_data_from_session(
        session_model=AddContextToExpressionsModel, component_id=component.id, expression_id=expression_id
    )
    confirm_deletion_form = GenericConfirmDeletionForm()

    if component.is_question:
        return_url = url_for(
            "deliver_grant_funding.edit_question",
            grant_id=grant_id,
            question_id=component.id,
        )

    else:
        return_url = url_for("deliver_grant_funding.list_group_questions", grant_id=grant_id, group_id=component.id)

    if (
        "delete" in request.args
        and confirm_deletion_form.validate_on_submit()
        and confirm_deletion_form.confirm_deletion.data
    ):
        remove_question_expression(question=component, expression=expression)
        return redirect(return_url)

    wt_form = CalculatedConditionForm(
        data=add_context_data._prepared_form_data if add_context_data else None,  # ty:ignore[unresolved-attribute]
        obj=expression.custom if not add_context_data else None,
        component=component,
        interpolation_context=(
            ExpressionContext.build_expression_context(
                component.form.collection,
                "interpolation",
            )
        ),
        evaluation_context=(
            ExpressionContext.build_expression_context(
                component.form.collection,
                "evaluation",
            )
        ),
    )
    if wt_form.is_submitted_to_add_context():
        form_data = wt_form.get_expression_form_data()
        return _store_question_state_and_redirect_to_add_context(
            form=wt_form,
            grant_id=grant_id,
            form_id=component.form.id,
            component_id=component.id,
            expression_id=expression_id,
            parent_id=component.parent_id,
            form_data=form_data,
            expression_type=ExpressionType.CONDITION,
            is_custom=True,
        )
    if wt_form.validate_on_submit():
        custom_expression = CustomExpression.build_from_form(wt_form)
        interfaces.collections.update_question_expression(expression, custom_expression)

        if "question" in session:
            del session["question"]
        return redirect(return_url)

    # Note: Mild shortcut; the alternative is passing this through a lot of templates/template logic
    g.context_keys_and_labels = ExpressionContext.get_context_keys_and_labels(
        collection=component.form.collection,
    )
    return render_template(
        "deliver_grant_funding/collections/calculated_condition.html",
        grant=component.form.collection.grant,
        expression=expression,
        component=component,
        form=wt_form,
        interpolate=SubmissionHelper.get_interpolator(component.form.collection),
        confirm_deletion_form=confirm_deletion_form if "delete" in request.args else None,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/question/<uuid:component_id>/add-condition/select-calculation",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
def add_question_condition_select_calculation(grant_id: UUID, component_id: UUID) -> ResponseReturnValue:
    component = get_component_by_id(component_id)

    wt_form = SelectConditionCalculationForm()

    if wt_form.validate_on_submit():
        if wt_form.need_calculation.data == "yes":
            return redirect(
                url_for("deliver_grant_funding.add_calculated_condition", grant_id=grant_id, component_id=component_id)
            )
        else:
            return redirect(
                url_for(
                    "deliver_grant_funding.add_question_condition_select_question",
                    grant_id=grant_id,
                    component_id=component_id,
                )
            )

    return render_template(
        "deliver_grant_funding/collections/add_question_condition_select_calculation.html",
        form=wt_form,
        component=component,
        grant=component.form.collection.grant,
        interpolate=SubmissionHelper.get_interpolator(component.form.collection),
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/question/<uuid:component_id>/add-condition",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
def add_question_condition_select_question(grant_id: UUID, component_id: UUID) -> ResponseReturnValue:

    component = get_component_by_id(component_id)

    form = FlaskForm()

    if form.validate_on_submit():
        add_context_data = AddConditionDependsOnSessionModel(
            component_id=component_id,
            parent_id=component.parent_id,
        )
        session["question"] = add_context_data.model_dump(mode="json")
        return redirect(
            url_for(
                "deliver_grant_funding.select_context_source",
                grant_id=grant_id,
                form_id=component.form.id,
                parent_id=component.parent_id,
            )
        )

    return render_template(
        "deliver_grant_funding/collections/add_question_condition_select_question.html",
        component=component,
        grant=component.form.collection.grant,
        form=form,
        interpolate=SubmissionHelper.get_interpolator(component.form.collection),
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/question/<uuid:component_id>/add-condition/<expression_reference:subject_reference>",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
@auto_commit_after_request
def add_question_condition(
    grant_id: UUID, component_id: UUID, subject_reference: ExpressionReference
) -> ResponseReturnValue:
    component = get_component_by_id(component_id)

    add_context_data = _extract_add_context_data_from_session(
        session_model=AddContextToExpressionsModel, component_id=component_id
    )

    ConditionForm = build_managed_expression_form(ExpressionType.CONDITION, subject_reference)
    form = (
        ConditionForm(data=add_context_data._prepared_form_data if add_context_data else None)  # ty: ignore[unresolved-attribute]
        if ConditionForm
        else None
    )

    if form and form.is_submitted_to_add_context():
        form_data = form.get_expression_form_data()
        return _store_question_state_and_redirect_to_add_context(
            form=form,
            grant_id=grant_id,
            form_id=component.form.id,
            component_id=component.id,
            parent_id=component.parent_id,
            form_data=form_data,
            expression_type=ExpressionType.CONDITION,
            managed_expression_name=ManagedExpressionsEnum(form.type.data),
            subject_reference=subject_reference,
        )

    if form and form.is_submitted_to_remove_context():
        _handle_remove_context_for_expression_forms(
            form=form,
            component_id=component.id,
            expression_type=ExpressionType.CONDITION,
            add_context_data=add_context_data,  # ty: ignore[invalid-argument-type]
            subject_reference=subject_reference,
        )
        return redirect(request.url)

    if form and form.validate_on_submit():
        expression = form.get_expression(subject_reference)

        try:
            interfaces.collections.add_component_condition(component, interfaces.user.get_current_user(), expression)
        except DuplicateValueError:
            form.form_errors.append(f"“{expression.description}” condition based on this question already exists.")
        else:
            if "question" in session:
                del session["question"]

            if component.is_group:
                return redirect(
                    url_for(
                        "deliver_grant_funding.list_group_questions",
                        grant_id=grant_id,
                        group_id=component.id,
                    )
                )
            else:
                return redirect(
                    url_for(
                        "deliver_grant_funding.edit_question",
                        grant_id=grant_id,
                        question_id=component.id,
                    )
                )

    # Note: Mild shortcut; the alternative is passing this through a lot of templates/template logic
    g.context_keys_and_labels = ExpressionContext.get_context_keys_and_labels(
        collection=component.form.collection, expression_context_end_point=component
    )

    return render_template(
        "deliver_grant_funding/collections/manage_question_condition_select_condition_type.html",
        component=component,
        subject_reference=subject_reference,
        grant=component.form.collection.grant,
        form=form,
        QuestionDataType=QuestionDataType,
        interpolate=SubmissionHelper.get_interpolator(component.form.collection),
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/condition/<uuid:expression_id>",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
@auto_commit_after_request
def edit_question_condition(grant_id: UUID, expression_id: UUID) -> ResponseReturnValue:
    expression = get_expression_by_id(expression_id)
    component = expression.question
    reference = expression.managed.subject_reference

    return_url = (
        url_for("deliver_grant_funding.edit_question", grant_id=grant_id, question_id=component.id)
        if not component.is_group
        else url_for("deliver_grant_funding.list_group_questions", grant_id=grant_id, group_id=component.id)
    )

    confirm_deletion_form = GenericConfirmDeletionForm()
    if (
        "delete" in request.args
        and confirm_deletion_form.validate_on_submit()
        and confirm_deletion_form.confirm_deletion.data
    ):
        remove_question_expression(question=component, expression=expression)
        return redirect(return_url)

    add_context_data = _extract_add_context_data_from_session(
        session_model=AddContextToExpressionsModel, component_id=component.id, expression_id=expression_id
    )

    ConditionForm = build_managed_expression_form(ExpressionType.CONDITION, reference, expression)
    form = (
        ConditionForm(data=add_context_data._prepared_form_data if add_context_data else None)  # ty: ignore[unresolved-attribute]
        if ConditionForm
        else None
    )

    if form and form.is_submitted_to_add_context():
        form_data = form.get_expression_form_data()
        return _store_question_state_and_redirect_to_add_context(
            form=form,
            grant_id=grant_id,
            form_id=component.form.id,
            component_id=component.id,
            parent_id=component.parent_id,
            form_data=form_data,
            expression_type=ExpressionType.CONDITION,
            managed_expression_name=ManagedExpressionsEnum(form.type.data),
            subject_reference=reference,
            expression_id=expression_id,
        )

    if form and form.is_submitted_to_remove_context():
        _handle_remove_context_for_expression_forms(
            form=form,
            component_id=component.id,
            expression_type=ExpressionType.CONDITION,
            expression=expression,
            add_context_data=add_context_data,  # ty: ignore[invalid-argument-type]
            subject_reference=reference,
        )
        return redirect(request.url)

    if form and form.validate_on_submit():
        updated_managed_expression = form.get_expression(reference)

        try:
            interfaces.collections.update_question_expression(expression, updated_managed_expression)
        except DuplicateValueError:
            form.form_errors.append(
                f"“{updated_managed_expression.description}” condition based on this question already exists."
            )
        else:
            if "question" in session:
                del session["question"]
            return redirect(return_url)

    # Note: Mild shortcut; the alternative is passing this through a lot of templates/template logic
    g.context_keys_and_labels = ExpressionContext.get_context_keys_and_labels(
        collection=component.form.collection, expression_context_end_point=component
    )

    return render_template(
        "deliver_grant_funding/collections/manage_question_condition_select_condition_type.html",
        component=component,
        grant=component.form.collection.grant,
        form=form,
        confirm_deletion_form=confirm_deletion_form if "delete" in request.args else None,
        expression=expression,
        QuestionDataType=QuestionDataType,
        subject_reference=reference,
        interpolate=SubmissionHelper.get_interpolator(component.form.collection),
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/question/<uuid:question_id>/add-validation",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
@auto_commit_after_request
def add_question_validation(grant_id: UUID, question_id: UUID) -> ResponseReturnValue:
    question = get_question_by_id(question_id)

    add_context_data = _extract_add_context_data_from_session(
        session_model=AddContextToExpressionsModel, component_id=question.id
    )

    ValidationForm = build_managed_expression_form(
        ExpressionType.VALIDATION,
        ExpressionReference.from_question(question),
    )
    form = (
        ValidationForm(data=add_context_data._prepared_form_data if add_context_data else None)  # ty: ignore[unresolved-attribute]
        if ValidationForm
        else None
    )

    if form and form.is_submitted_to_add_context():
        form_data = form.get_expression_form_data()
        return _store_question_state_and_redirect_to_add_context(
            form=form,
            grant_id=grant_id,
            form_id=question.form.id,
            component_id=question.id,
            parent_id=question.parent_id,
            form_data=form_data,
            expression_type=ExpressionType.VALIDATION,
            managed_expression_name=ManagedExpressionsEnum(form.type.data),
        )

    if form and form.is_submitted_to_remove_context():
        _handle_remove_context_for_expression_forms(
            form=form,
            component_id=question.id,
            expression_type=ExpressionType.VALIDATION,
            add_context_data=add_context_data,  # ty: ignore[invalid-argument-type]
        )
        return redirect(request.url)

    if form and form.validate_on_submit():
        if form.type.data == "CUSTOM":
            return redirect(
                url_for(
                    "deliver_grant_funding.add_custom_question_validation",
                    grant_id=grant_id,
                    question_id=question_id,
                )
            )

        expression = form.get_expression(ExpressionReference.from_question(question))

        try:
            interfaces.collections.add_component_validation(question, interfaces.user.get_current_user(), expression)
        except DuplicateValueError:
            # FIXME: This is not the most user-friendly way of handling this error, but I'm happy to let our users
            #        complain to us about it before we think about a better way of handling it.
            form.form_errors.append(f"“{expression.description}” validation already exists on the question.")
        else:
            if "question" in session:
                del session["question"]
            return redirect(
                url_for(
                    "deliver_grant_funding.edit_question",
                    grant_id=grant_id,
                    question_id=question.id,
                )
            )

    # Note: Mild shortcut; the alternative is passing this through a lot of templates/template logic
    g.context_keys_and_labels = ExpressionContext.get_context_keys_and_labels(
        collection=question.form.collection, expression_context_end_point=question
    )

    return render_template(
        "deliver_grant_funding/collections/manage_question_validation.html",
        question=question,
        grant=question.form.collection.grant,
        form=form,
        QuestionDataType=QuestionDataType,
        interpolate=SubmissionHelper.get_interpolator(question.form.collection),
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/validation/<uuid:expression_id>",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
@auto_commit_after_request
def edit_question_validation(grant_id: UUID, expression_id: UUID) -> ResponseReturnValue:
    expression = get_expression_by_id(expression_id)
    question = expression.question

    confirm_deletion_form = GenericConfirmDeletionForm()
    if (
        "delete" in request.args
        and confirm_deletion_form.validate_on_submit()
        and confirm_deletion_form.confirm_deletion.data
    ):
        remove_question_expression(question=question, expression=expression)
        return redirect(
            url_for(
                "deliver_grant_funding.edit_question",
                grant_id=grant_id,
                question_id=question.id,
            )
        )

    add_context_data = _extract_add_context_data_from_session(
        session_model=AddContextToExpressionsModel, component_id=question.id, expression_id=expression_id
    )

    ValidationForm = build_managed_expression_form(
        ExpressionType.VALIDATION, ExpressionReference.from_question(cast("Question", question)), expression
    )
    form = (
        ValidationForm(data=add_context_data._prepared_form_data if add_context_data else None)  # ty: ignore[unresolved-attribute]
        if ValidationForm
        else None
    )

    if form and form.is_submitted_to_add_context():
        form_data = form.get_expression_form_data()
        return _store_question_state_and_redirect_to_add_context(
            form=form,
            grant_id=grant_id,
            form_id=question.form.id,
            component_id=question.id,
            parent_id=question.parent_id,
            form_data=form_data,
            expression_type=ExpressionType.VALIDATION,
            managed_expression_name=ManagedExpressionsEnum(form.type.data),
            expression_id=expression_id,
        )

    if form and form.is_submitted_to_remove_context():
        _handle_remove_context_for_expression_forms(
            form=form,
            component_id=question.id,
            expression_type=ExpressionType.VALIDATION,
            expression=expression,
            add_context_data=add_context_data,  # ty: ignore[invalid-argument-type]
        )
        return redirect(request.url)

    if form and form.validate_on_submit():
        # todo: any time we're dealing with the dependant component its a question - make sure this makes sense
        updated_managed_expression = form.get_expression(ExpressionReference.from_question(cast("Question", question)))
        try:
            interfaces.collections.update_question_expression(expression, updated_managed_expression)
        except DuplicateValueError:
            # FIXME: This is not the most user-friendly way of handling this error, but I'm happy to let our users
            #        complain to us about it before we think about a better way of handling it.
            form.form_errors.append(
                f"“{updated_managed_expression.description}” validation already exists on the question."
            )
        else:
            if "question" in session:
                del session["question"]
            return redirect(
                url_for(
                    "deliver_grant_funding.edit_question",
                    grant_id=grant_id,
                    question_id=question.id,
                )
            )

    # Note: Mild shortcut; the alternative is passing this through a lot of templates/template logic
    g.context_keys_and_labels = ExpressionContext.get_context_keys_and_labels(
        collection=question.form.collection, expression_context_end_point=question
    )

    return render_template(
        "deliver_grant_funding/collections/manage_question_validation.html",
        question=question,
        grant=question.form.collection.grant,
        form=form,
        confirm_deletion_form=confirm_deletion_form if "delete" in request.args else None,
        expression=expression,
        QuestionDataType=QuestionDataType,
        interpolate=SubmissionHelper.get_interpolator(question.form.collection),
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/question/<uuid:question_id>/add-validation/custom",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
@auto_commit_after_request
def add_custom_question_validation(grant_id: UUID, question_id: UUID) -> ResponseReturnValue:
    question = get_question_by_id(question_id)

    add_context_data = _extract_add_context_data_from_session(
        session_model=AddContextToExpressionsModel, component_id=question.id
    )
    wt_form = CustomValidationExpressionForm(
        data=add_context_data._prepared_form_data if add_context_data else None,  # ty: ignore[unresolved-attribute]
        component=question,
        interpolation_context=(
            ExpressionContext.build_expression_context(
                question.form.collection,
                "interpolation",
            )
        ),
        evaluation_context=(
            ExpressionContext.build_expression_context(
                question.form.collection,
                "evaluation",
            )
        ),
    )

    if wt_form.is_submitted_to_add_context():
        form_data = wt_form.get_expression_form_data()
        return _store_question_state_and_redirect_to_add_context(
            form=wt_form,
            grant_id=grant_id,
            form_id=question.form.id,
            component_id=question.id,
            parent_id=question.parent_id,
            form_data=form_data,
            expression_type=ExpressionType.VALIDATION,
            is_custom=True,
        )
    if wt_form.validate_on_submit():
        expression = CustomExpression.build_from_form(wt_form)

        try:
            interfaces.collections.add_component_validation(question, interfaces.user.get_current_user(), expression)

        except IncompatibleDataTypeException as e:
            wt_form.handle_exception(IncompatibleDataTypeInCalculationException(e))
        except WTFormRenderableException as e:
            wt_form.handle_exception(e)

        else:
            if "question" in session:
                del session["question"]
            return redirect(
                url_for(
                    "deliver_grant_funding.edit_question",
                    grant_id=grant_id,
                    question_id=question.id,
                )
            )

    # Note: Mild shortcut; the alternative is passing this through a lot of templates/template logic
    g.context_keys_and_labels = ExpressionContext.get_context_keys_and_labels(
        collection=question.form.collection,
    )
    return render_template(
        "deliver_grant_funding/collections/calculated_validation.html",
        form=wt_form,
        question=question,
        grant=question.form.collection.grant,
        interpolate=SubmissionHelper.get_interpolator(question.form.collection),
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/question/<uuid:question_id>/custom-validation/<uuid:expression_id>",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
@auto_commit_after_request
def edit_custom_question_validation(grant_id: UUID, question_id: UUID, expression_id: UUID) -> ResponseReturnValue:

    question = get_question_by_id(question_id)
    expression = get_expression_by_id(expression_id)

    add_context_data = _extract_add_context_data_from_session(
        session_model=AddContextToExpressionsModel, component_id=question.id, expression_id=expression_id
    )

    confirm_deletion_form = GenericConfirmDeletionForm()
    if (
        "delete" in request.args
        and confirm_deletion_form.validate_on_submit()
        and confirm_deletion_form.confirm_deletion.data
    ):
        remove_question_expression(question=question, expression=expression)
        return redirect(
            url_for(
                "deliver_grant_funding.edit_question",
                grant_id=grant_id,
                question_id=question.id,
            )
        )
    wt_form = CustomValidationExpressionForm(
        data=add_context_data._prepared_form_data if add_context_data else None,  # ty:ignore[unresolved-attribute]
        obj=expression.custom if not add_context_data else None,
        component=question,
        interpolation_context=(
            ExpressionContext.build_expression_context(
                question.form.collection,
                "interpolation",
            )
        ),
        evaluation_context=(
            ExpressionContext.build_expression_context(
                question.form.collection,
                "evaluation",
            )
        ),
    )
    if wt_form and wt_form.is_submitted_to_add_context():
        form_data = wt_form.get_expression_form_data()
        return _store_question_state_and_redirect_to_add_context(
            form=wt_form,
            grant_id=grant_id,
            form_id=question.form.id,
            component_id=question.id,
            parent_id=question.parent_id,
            form_data=form_data,
            expression_type=ExpressionType.VALIDATION,
            expression_id=expression.id,
            is_custom=True,
        )
    if wt_form and wt_form.validate_on_submit():
        custom_expression = CustomExpression.build_from_form(wt_form)

        try:
            interfaces.collections.update_question_expression(expression, custom_expression)
        except IncompatibleDataTypeException as e:
            wt_form.handle_exception(IncompatibleDataTypeInCalculationException(e))
        except WTFormRenderableException as e:
            wt_form.handle_exception(e)

        else:
            if "question" in session:
                del session["question"]
            return redirect(
                url_for(
                    "deliver_grant_funding.edit_question",
                    grant_id=grant_id,
                    question_id=question.id,
                )
            )

    # Note: Mild shortcut; the alternative is passing this through a lot of templates/template logic
    g.context_keys_and_labels = ExpressionContext.get_context_keys_and_labels(
        collection=question.form.collection,
    )
    return render_template(
        "deliver_grant_funding/collections/calculated_validation.html",
        form=wt_form,
        question=question,
        grant=question.form.collection.grant,
        expression=expression,
        interpolate=SubmissionHelper.get_interpolator(question.form.collection),
        confirm_deletion_form=confirm_deletion_form if "delete" in request.args else None,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/group/<uuid:group_id>/add-validation",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
@auto_commit_after_request
def add_group_validation(grant_id: UUID, group_id: UUID) -> ResponseReturnValue:
    group = get_group_by_id(group_id)
    if not group.same_page:
        flash(
            "Group validations are only available for question groups that show all questions on the same page.",
            FlashMessageType.GROUP_VALIDATION_NOT_AVAILABLE.value,
        )
        return redirect(url_for("deliver_grant_funding.list_group_questions", grant_id=grant_id, group_id=group.id))

    add_context_data = _extract_add_context_data_from_session(
        session_model=AddContextToExpressionsModel, component_id=group.id
    )
    wt_form = CustomValidationExpressionForm(
        data=add_context_data._prepared_form_data if add_context_data else None,  # ty: ignore[unresolved-attribute]
        component=group,
        interpolation_context=(
            ExpressionContext.build_expression_context(
                group.form.collection,
                "interpolation",
            )
        ),
        evaluation_context=(
            ExpressionContext.build_expression_context(
                group.form.collection,
                "evaluation",
            )
        ),
    )

    if wt_form.is_submitted_to_add_context():
        form_data = wt_form.get_expression_form_data()
        return _store_question_state_and_redirect_to_add_context(
            form=wt_form,
            grant_id=grant_id,
            form_id=group.form.id,
            component_id=group.id,
            parent_id=group.parent_id,
            form_data=form_data,
            expression_type=ExpressionType.VALIDATION,
            is_custom=True,
            is_group=True,
        )
    if wt_form.validate_on_submit():
        expression = CustomExpression.build_from_form(wt_form)

        try:
            interfaces.collections.add_component_validation(group, interfaces.user.get_current_user(), expression)
        except IncompatibleDataTypeException as e:
            wt_form.handle_exception(IncompatibleDataTypeInCalculationException(e))
        except WTFormRenderableException as e:
            wt_form.handle_exception(e)
        else:
            if "question" in session:
                del session["question"]
            return redirect(
                url_for(
                    "deliver_grant_funding.list_group_questions",
                    grant_id=grant_id,
                    group_id=group.id,
                )
            )

    g.context_keys_and_labels = ExpressionContext.get_context_keys_and_labels(
        collection=group.form.collection, expression_type=ExpressionType.VALIDATION
    )
    return render_template(
        "deliver_grant_funding/collections/manage_group_validation.html",
        form=wt_form,
        group=group,
        grant=group.form.collection.grant,
        interpolate=SubmissionHelper.get_interpolator(group.form.collection),
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/group/<uuid:group_id>/validation/<uuid:expression_id>",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@collection_is_editable()
@auto_commit_after_request
def edit_group_validation(grant_id: UUID, group_id: UUID, expression_id: UUID) -> ResponseReturnValue:
    group = get_group_by_id(group_id)
    expression = get_expression_by_id(expression_id)
    if not expression.question or not expression.question.is_group or expression.question_id != group_id:
        abort(404)

    add_context_data = _extract_add_context_data_from_session(
        session_model=AddContextToExpressionsModel, component_id=group.id, expression_id=expression_id
    )

    confirm_deletion_form = GenericConfirmDeletionForm()
    if (
        "delete" in request.args
        and confirm_deletion_form.validate_on_submit()
        and confirm_deletion_form.confirm_deletion.data
    ):
        remove_question_expression(question=group, expression=expression)
        return redirect(
            url_for(
                "deliver_grant_funding.list_group_questions",
                grant_id=grant_id,
                group_id=group.id,
            )
        )

    wt_form = CustomValidationExpressionForm(
        data=add_context_data._prepared_form_data if add_context_data else None,  # ty:ignore[unresolved-attribute]
        obj=expression.custom if not add_context_data else None,
        component=group,
        interpolation_context=(
            ExpressionContext.build_expression_context(
                group.form.collection,
                "interpolation",
            )
        ),
        evaluation_context=(
            ExpressionContext.build_expression_context(
                group.form.collection,
                "evaluation",
            )
        ),
    )
    if wt_form.is_submitted_to_add_context():
        form_data = wt_form.get_expression_form_data()
        return _store_question_state_and_redirect_to_add_context(
            form=wt_form,
            grant_id=grant_id,
            form_id=group.form.id,
            component_id=group.id,
            parent_id=group.parent_id,
            form_data=form_data,
            expression_type=ExpressionType.VALIDATION,
            expression_id=expression.id,
            is_custom=True,
            is_group=True,
        )
    if wt_form.validate_on_submit():
        custom_expression = CustomExpression.build_from_form(wt_form)
        try:
            interfaces.collections.update_question_expression(expression, custom_expression)
        except IncompatibleDataTypeException as e:
            wt_form.handle_exception(IncompatibleDataTypeInCalculationException(e))
        except WTFormRenderableException as e:
            wt_form.handle_exception(e)
        else:
            if "question" in session:
                del session["question"]
            return redirect(
                url_for(
                    "deliver_grant_funding.list_group_questions",
                    grant_id=grant_id,
                    group_id=group.id,
                )
            )

    g.context_keys_and_labels = ExpressionContext.get_context_keys_and_labels(
        collection=group.form.collection, expression_type=ExpressionType.VALIDATION
    )
    return render_template(
        "deliver_grant_funding/collections/manage_group_validation.html",
        form=wt_form,
        group=group,
        grant=group.form.collection.grant,
        expression=expression,
        interpolate=SubmissionHelper.get_interpolator(group.form.collection),
        confirm_deletion_form=confirm_deletion_form if "delete" in request.args else None,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/<collection_type:collection_type>/<uuid:collection_id>/submissions/<submission_mode:submission_mode>",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.MEMBER)
@auto_commit_after_request
def list_submissions(
    grant_id: UUID, collection_type: CollectionType, collection_id: UUID, submission_mode: SubmissionModeEnum
) -> ResponseReturnValue:
    collection = interfaces.collections.get_collection(collection_id, grant_id=grant_id, type_=collection_type)

    delete_all_form = GenericConfirmDeletionForm() if "delete_all" in request.args else None
    if delete_all_form and delete_all_form.validate_on_submit():
        if submission_mode != SubmissionModeEnum.TEST:
            abort(400)

        reset_all_test_submissions(collection)
        s3_service.delete_prefix(collection.s3_key_prefix(submission_mode=submission_mode))

        flash("All test submissions reset", FlashMessageType.TEST_SUBMISSIONS_RESET)
        return redirect(
            url_for(
                "deliver_grant_funding.list_submissions",
                grant_id=grant_id,
                collection_type=collection_type,
                collection_id=collection_id,
                submission_mode=submission_mode,
            )
        )

    submissions = get_submission_list_for_collection(collection=collection, submission_mode=submission_mode)

    return render_template(
        "deliver_grant_funding/collections/list_submissions.html",
        grant=collection.grant,
        collection=collection,
        submission_mode=submission_mode,
        delete_all_form=delete_all_form if submission_mode == SubmissionModeEnum.TEST else None,
        submissions=submissions,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/<collection_type:collection_type>/<uuid:collection_id>/submissions/<submission_mode:submission_mode>/export/<export_format>",
    methods=["GET"],
)
@has_deliver_grant_role(RoleEnum.MEMBER)
def export_collection_submissions(
    grant_id: UUID,
    collection_type: CollectionType,
    collection_id: UUID,
    submission_mode: SubmissionModeEnum,
    export_format: str,
) -> ResponseReturnValue:
    collection = interfaces.collections.get_collection(
        collection_id, grant_id=grant_id, type_=collection_type, with_full_schema=True
    )
    helper = AllSubmissionsHelper(collection=collection, submission_mode=submission_mode)

    export_format = export_format.lower()
    match export_format:
        case "csv":
            data = helper.generate_csv_content_for_all_submissions()
            mimetype = "text/csv"
            encoding = "utf-8-sig"  # Helps Excel open in UTF-8 mode so that eg `£` doesn't get mangled to `Â£`

        case "json":
            data = helper.generate_json_content_for_all_submissions()
            mimetype = "application/json"
            encoding = "utf-8"

        case _:
            abort(400)

    buffer = io.StringIO()
    buffer.write(data)
    buffer.seek(0)
    emit_metric_count(
        MetricEventName.SUBMISSIONS_EXPORTED,
        collection=collection,
        custom_attributes={MetricAttributeName.FILE_FORMAT: export_format},
    )
    return send_file(
        io.BytesIO(buffer.getvalue().encode(encoding)),
        mimetype=mimetype,
        as_attachment=True,
        download_name=f"{collection.name} - {submission_mode.name.lower()}.{export_format}",
        max_age=0,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/submission/<uuid:submission_id>", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.MEMBER)
@auto_commit_after_request
def view_submission(grant_id: UUID, submission_id: UUID) -> ResponseReturnValue:
    helper = SubmissionHelper.load(submission_id)
    collection_id = helper.collection.id
    submission_mode = helper.submission.mode

    delete_wtform = GenericConfirmDeletionForm() if "delete" in request.args else None
    if delete_wtform:
        if delete_wtform.validate_on_submit():
            reset_test_submission(helper.submission)
            s3_service.delete_prefix(helper.submission.s3_key_prefix)

            flash("Submission reset", FlashMessageType.TEST_SUBMISSION_RESET)
            return redirect(
                url_for(
                    "deliver_grant_funding.list_submissions",
                    grant_id=grant_id,
                    collection_type=helper.collection.type,
                    collection_id=collection_id,
                    submission_mode=submission_mode,
                )
            )

    timeline_event_types = [
        SubmissionEventType.SUBMISSION_SENT_FOR_CERTIFICATION,
        SubmissionEventType.SUBMISSION_DECLINED_BY_CERTIFIER,
        SubmissionEventType.SUBMISSION_APPROVED_BY_CERTIFIER,
        SubmissionEventType.SUBMISSION_REOPENED,
        SubmissionEventType.SUBMISSION_CHANGES_REQUESTED,
        SubmissionEventType.ASSESSOR_MARKED_AS_APPROVED,
        SubmissionEventType.ASSESSOR_MARKED_AS_REJECTED,
    ]

    # we are not displaying SUBMISSION_SUBMITTED events when collection requires certification
    if not helper.collection.requires_certification:
        timeline_event_types.append(SubmissionEventType.SUBMISSION_SUBMITTED)

    return render_template(
        (
            "deliver_grant_funding/collections/view_submission.html"
            if not FeatureFlags.PRE_AWARD.is_enabled
            else "deliver_grant_funding/collections/ff_view_submission.html"
        ),
        grant=helper.grant,
        helper=helper,
        interpolate=SubmissionHelper.get_interpolator(collection=helper.collection, submission_helper=helper),
        delete_form=delete_wtform,
        timeline_items=helper.timeline_events,
        timeline_event_types=timeline_event_types,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/submission/<uuid:submission_id>/export-pdf",
    methods=["GET"],
)
@has_deliver_grant_role(RoleEnum.MEMBER)
def export_submission_pdf(grant_id: UUID, submission_id: UUID) -> ResponseReturnValue:
    helper = SubmissionHelper.load(submission_id)

    html_content = render_template(
        "common/submission_print_baseline.html",
        grant=helper.grant,
        submission=helper,
        interpolate=SubmissionHelper.get_interpolator(collection=helper.collection, submission_helper=helper),
    )

    emit_metric_count(MetricEventName.SUBMISSION_PDF_DOWNLOADED, submission=helper.submission)

    return send_file(
        io.BytesIO(render_pdf(html_content)),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=secure_filename(f"{helper.collection.grant.name} - {helper.long_collection_name}.pdf"),
        max_age=0,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/submission/<uuid:submission_id>/reopen", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.MEMBER)
@auto_commit_after_request
def reopen_submission(grant_id: UUID, submission_id: UUID) -> ResponseReturnValue:

    submission_helper = SubmissionHelper.load(submission_id)
    if not AuthorisationHelper.can_request_or_allow_changes(get_current_user(), submission_helper.submission):
        abort(403)
    form = ReopenSubmissionForm()
    if form.validate_on_submit():
        try:
            submission_helper.reopen_submission(
                user=get_current_user(),
                reopened_reason=form.reopened_reason.data,
            )
            flash("Submission reopened", FlashMessageType.SUBMISSION_REOPENED)
            return redirect(
                url_for("deliver_grant_funding.view_submission", grant_id=grant_id, submission_id=submission_id)
            )
        except SubmissionAuthorisationError:
            form.form_errors.append("You do not have permission to reopen this submission")
        except CollectionIsNotOpenError:
            form.form_errors.append("You cannot reopen this submission because the report is not open")
        except SubmissionIsNotSubmittedError:
            form.form_errors.append("You cannot reopen this submission because it has not been submitted")
    return render_template(
        "deliver_grant_funding/collections/reopen_submission.html",
        form=form,
        helper=submission_helper,
        grant=submission_helper.grant,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/submission/<uuid:submission_id>/request-or-allow-changes", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.MEMBER)
def request_or_allow_changes(grant_id: UUID, submission_id: UUID) -> ResponseReturnValue:
    submission_helper = SubmissionHelper.load(submission_id)

    if not AuthorisationHelper.can_request_or_allow_changes(get_current_user(), submission_helper.submission):
        abort(403)

    form = RequestOrAllowChangesSubmissionForm()
    if form.validate_on_submit():
        if form.request_changes.data == "yes":
            return redirect(
                url_for(
                    "deliver_grant_funding.request_changes_submission",
                    grant_id=grant_id,
                    submission_id=submission_id,
                )
            )

        return redirect(
            url_for(
                "deliver_grant_funding.reopen_submission",
                grant_id=grant_id,
                submission_id=submission_id,
            )
        )

    return render_template(
        "deliver_grant_funding/collections/request_or_allow_changes.html",
        form=form,
        helper=submission_helper,
        grant=submission_helper.grant,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/submission/<uuid:submission_id>/request-changes", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.MEMBER)
@auto_commit_after_request
def request_changes_submission(grant_id: UUID, submission_id: UUID) -> ResponseReturnValue:
    submission_helper = SubmissionHelper.load(submission_id)

    if not AuthorisationHelper.can_request_or_allow_changes(get_current_user(), submission_helper.submission):
        abort(403)

    form = RequestChangesSubmissionForm(submission_helper=submission_helper)
    if form.validate_on_submit():
        try:
            submission_helper.request_changes_submission(
                user=get_current_user(),
                changes_requested_reason=form.changes_requested_reason.data,
                section_ids=form.section_ids.data or [],
            )

            flash("Changes requested", FlashMessageType.SUBMISSION_CHANGES_REQUESTED)

            return redirect(
                url_for("deliver_grant_funding.view_submission", grant_id=grant_id, submission_id=submission_id)
            )
        except SubmissionAuthorisationError:
            form.form_errors.append("You do not have permission to request changes to this submission")
        except CollectionIsNotOpenError:
            form.form_errors.append("You cannot request changes because the report is not open")
        except SubmissionIsNotSubmittedError:
            form.form_errors.append("You cannot request changes because the submission has not been submitted")

    return render_template(
        "deliver_grant_funding/collections/request_changes_submission.html",
        form=form,
        helper=submission_helper,
        grant=submission_helper.grant,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/submission/<uuid:submission_id>/approve-or-reject", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.MEMBER)
@auto_commit_after_request
def approve_or_reject_submission(grant_id: UUID, submission_id: UUID) -> ResponseReturnValue:
    submission_helper = SubmissionHelper.load(submission_id)

    if not AuthorisationHelper.can_validate_submission(get_current_user(), submission_helper.submission):
        abort(403)

    form = ApproveOrRejectSubmissionForm()
    if form.validate_on_submit():
        is_approved = form.is_approved.data == "yes"
        try:
            submission_helper.validate_submission(
                user=get_current_user(),
                is_approved=is_approved,
                rejected_reason=form.rejected_reason.data if not is_approved else None,
            )
            flash_type = (
                FlashMessageType.SUBMISSION_MARKED_AS_APPROVED
                if is_approved
                else FlashMessageType.SUBMISSION_MARKED_AS_REJECTED
            )
            flash("Assessment saved", flash_type)
            return redirect(
                url_for("deliver_grant_funding.view_submission", grant_id=grant_id, submission_id=submission_id)
            )
        except SubmissionAuthorisationError:
            form.form_errors.append("You do not have permission to assess this submission")
        except SubmissionIsNotSubmittedError:
            form.form_errors.append("You cannot assess this submission because it has not been submitted")

    return render_template(
        "deliver_grant_funding/collections/approve_or_reject_submission.html",
        form=form,
        helper=submission_helper,
        grant=submission_helper.grant,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/<collection_type:collection_type>/<uuid:collection_id>/data-sets", methods=["GET", "POST"]
)
@has_deliver_grant_role(RoleEnum.MEMBER)
def list_collection_data_sets(
    grant_id: UUID, collection_type: CollectionType, collection_id: UUID
) -> ResponseReturnValue:
    collection = get_collection(collection_id, grant_id=grant_id, type_=collection_type)
    data_sources = get_data_source_list_for_collection(collection_id)

    form = GenericSubmitForm()

    if form.validate_on_submit():
        if SESSION_DATA_SET_UPLOAD in session:
            del session[SESSION_DATA_SET_UPLOAD]

        return redirect(
            url_for(
                "deliver_grant_funding.upload_data_set",
                grant_id=grant_id,
                collection_type=collection_type,
                collection_id=collection_id,
            )
        )

    return render_template(
        "deliver_grant_funding/collections/list_data_sets.html",
        grant=collection.grant,
        collection=collection,
        form=form,
        data_sources=data_sources,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/<collection_type:collection_type>/<uuid:collection_id>/data-sets/template", methods=["GET"]
)
@has_deliver_grant_role(RoleEnum.MEMBER)
def download_grant_recipient_data_set_template(
    grant_id: UUID, collection_type: CollectionType, collection_id: UUID
) -> ResponseReturnValue:
    collection = get_collection(collection_id, grant_id=grant_id, type_=collection_type)

    grant_recipients = interfaces.grant_recipients.get_grant_recipients(collection.grant, with_organisations=True)

    csv_output = io.StringIO()
    csv_writer = csv.DictWriter(
        csv_output,
        fieldnames=[DATA_SET_EXTERNAL_ID_COLUMN_HEADER, DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER],
    )
    csv_writer.writeheader()
    for gr in sorted(grant_recipients, key=lambda gr: gr.organisation.name):
        if gr.organisation.mode == OrganisationModeEnum.TEST:
            continue
        csv_writer.writerow(
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id or "",
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr.organisation.name,
            }
        )

    return send_file(
        io.BytesIO(csv_output.getvalue().encode("utf-8-sig")),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"{collection.slug}-grant-recipient-data-template.csv",
        max_age=0,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/<collection_type:collection_type>/<uuid:collection_id>/data-sets/<uuid:data_source_id>/template",
    methods=["GET"],
)
@has_deliver_grant_role(RoleEnum.MEMBER)
def download_latest_data_set_template(
    grant_id: UUID, collection_type: CollectionType, collection_id: UUID, data_source_id: UUID
) -> ResponseReturnValue:
    collection = get_collection(
        collection_id=collection_id, grant_id=grant_id, with_full_schema=False, type_=collection_type
    )
    data_source = get_data_source(data_source_id, with_organisation_items=True)

    # TODO FSPT-1044: We should do this filtering in the interface rather than here
    if data_source.collection_id != collection_id or data_source.grant_id != grant_id:
        abort(404)

    csv_content = generate_latest_csv_template(data_source)
    return send_file(
        io.BytesIO(csv_content.getvalue().encode("utf-8-sig")),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"{collection.slug}-{slugify(data_source.name)}-template.csv",  # ty:ignore[invalid-argument-type]
        max_age=0,
    )


def _parse_data_set_csv(file_storage: FileStorage) -> tuple[list[str], TUnvalidatedDataSetRows]:
    file_storage.stream.seek(0)
    content = file_storage.stream.read().decode("utf-8-sig")
    file_storage.stream.seek(0)

    reader = csv.DictReader(io.StringIO(content))
    columns = [fieldname.strip() for fieldname in reader.fieldnames or []]
    reader.fieldnames = columns
    rows: TUnvalidatedDataSetRows = list(reader)

    return columns, rows


def _load_rows(data_set_data: DataSetUploadSessionModel) -> TUnvalidatedDataSetRows:
    file_bytes = s3_service.download_file(data_set_data.s3_key)
    file_storage = FileStorage(stream=io.BytesIO(file_bytes), filename=data_set_data.original_filename)
    _, rows = _parse_data_set_csv(file_storage)
    return rows


def _load_and_validate_data_set(
    data_set_data: DataSetUploadSessionModel,
) -> tuple[TUnvalidatedDataSetRows, DataSetValidationResult]:
    rows = _load_rows(data_set_data)
    return rows, validate_data_set(data_set_data, rows)


def _extract_data_set_data_from_session(data_source_id: uuid.UUID | None = None) -> DataSetUploadSessionModel | None:
    session_data_name = SESSION_DATA_SET_REPLACE if data_source_id else SESSION_DATA_SET_UPLOAD
    if session_data := session.get(session_data_name):
        try:
            upload_data = DataSetUploadSessionModel(**session_data)
            return upload_data
        except ValidationError:
            del session[session_data_name]
            return None
    return None


def _upload_data_set_file(
    grant_id: UUID, collection_id: UUID, data_source_id: UUID, file: FileStorage
) -> tuple[str, str]:
    if not file.filename:
        raise ValueError("No filename supplied")
    s3_key = build_data_set_upload_s3_key(grant_id=grant_id, collection_id=collection_id, data_source_id=data_source_id)
    file.stream.seek(0)
    s3_service.upload_file(file, s3_key, {"status": DataSourceFileTagEnum.PENDING})
    return s3_key, secure_filename(file.filename)


def _build_upload_data_set_preview_data(data_columns: list[str], rows: list[dict[str, str]]) -> dict[str, list[str]]:

    preview_data: dict[str, list[str]] = {}
    for column in data_columns:
        values = []
        for row in rows:
            val = row.get(column, "")
            if val:
                values.append(str(escape(val)))
            if len(values) == DATA_SET_PREVIEW_LENGTH:
                break
        preview_data[column] = values
    return preview_data


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/<collection_type:collection_type>/<uuid:collection_id>/data-set/upload",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
def upload_data_set(grant_id: UUID, collection_type: CollectionType, collection_id: UUID) -> ResponseReturnValue:
    collection = get_collection(collection_id, grant_id=grant_id, type_=collection_type)

    data_set_data = _extract_data_set_data_from_session(None)

    form = UploadDataSetForm(existing_data_source_names=[ds.name for ds in collection.data_sources], obj=data_set_data)

    gr_errors: list[str] = []

    if form.validate_on_submit():
        file: FileStorage = form.file.data
        columns, rows = _parse_data_set_csv(form.file.data)

        data_columns = [col for col in columns if col not in DATA_SET_IDENTIFIER_COLUMN_HEADERS]

        data_source_id = uuid.uuid4()
        file_metadata = _upload_data_set_file(grant_id, collection_id, data_source_id, file)

        preview_data = _build_upload_data_set_preview_data(data_columns, rows)

        session_data = DataSetUploadSessionModel(
            name=cast(str, form.name.data),
            data_source_type=DataSourceType.GRANT_RECIPIENT,
            data_columns=data_columns,
            preview_data=preview_data,
            s3_key=file_metadata[0],
            original_filename=file_metadata[1],
            data_source_id=data_source_id,
        )

        session[SESSION_DATA_SET_UPLOAD] = session_data.model_dump(mode="json")

        grant_recipients = interfaces.grant_recipients.get_grant_recipients(collection.grant, with_organisations=True)
        gr_errors = validate_data_set_grant_recipients(session_data, grant_recipients, all_rows=rows)
        if gr_errors:
            return render_template(
                "deliver_grant_funding/collections/data_sets/upload_dataset.html",
                grant=collection.grant,
                collection=collection,
                form=form,
                gr_errors=gr_errors,
            )

        return redirect(
            url_for(
                "deliver_grant_funding.confirm_data_set_grant_recipients",
                grant_id=grant_id,
                collection_type=collection_type,
                collection_id=collection_id,
            )
        )

    return render_template(
        "deliver_grant_funding/collections/data_sets/upload_dataset.html",
        grant=collection.grant,
        collection=collection,
        form=form,
        gr_errors=gr_errors,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/<collection_type:collection_type>/<uuid:collection_id>/data-sets/<uuid:data_source_id>/replace",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
def replace_data_set(
    grant_id: UUID, collection_type: CollectionType, collection_id: UUID, data_source_id: UUID
) -> ResponseReturnValue:
    collection = get_collection(collection_id, grant_id=grant_id, type_=collection_type)
    data_source = get_data_source(data_source_id)

    if (
        data_source.collection_id != collection_id
        or data_source.grant_id != grant_id
        or collection.grant_id != grant_id
    ):
        abort(404)
    form = UploadDataSetForm(
        existing_data_source_names=[ds.name for ds in collection.data_sources if ds.id != data_source_id],
        existing_datasource=data_source,
        data={"name": data_source.name},
        submitted_orgs=[
            gr.organisation
            for gr in get_grant_recipients_for_collection_with_submitted_submissions(
                collection.grant, collection_id=collection_id, submission_mode=SubmissionModeEnum.LIVE
            )
        ],
    )
    gr_errors = []
    if form.validate_on_submit():
        file: FileStorage = form.file.data
        columns, rows = _parse_data_set_csv(form.file.data)
        file_metadata = _upload_data_set_file(grant_id, collection_id, data_source_id, file)

        data_columns = [col for col in columns if col not in DATA_SET_IDENTIFIER_COLUMN_HEADERS]
        preview_data = _build_upload_data_set_preview_data(data_columns, rows)
        data_set_session_data = DataSetUploadSessionModel(
            name=form.name.data,  # ty:ignore[invalid-argument-type]
            data_source_id=data_source_id,
            s3_key=file_metadata[0],
            original_filename=file_metadata[1],
            data_source_type=data_source.type,
            preview_data=preview_data,
            data_columns=data_columns,
            is_replace=True,
        )
        grant_recipients = interfaces.grant_recipients.get_grant_recipients(collection.grant, with_organisations=True)
        gr_errors = validate_data_set_grant_recipients(data_set_session_data, grant_recipients, all_rows=rows)
        if not gr_errors:
            session[SESSION_DATA_SET_REPLACE] = data_set_session_data.model_dump(mode="json")
            return redirect(
                url_for(
                    "deliver_grant_funding.confirm_data_set_grant_recipients",
                    grant_id=grant_id,
                    collection_type=collection_type,
                    collection_id=collection_id,
                    data_source_id=data_source_id,
                )
            )

    removed_columns = []
    removed_column_orgs = set()

    if form.removed_column_errors:
        removed_columns = form.removed_column_errors.keys()
        for _, orgs in form.removed_column_errors.items():
            for org in orgs:
                removed_column_orgs.add(org)

    changed_columns = []
    changed_column_orgs = set()

    if form.changed_column_errors:
        changed_columns = form.changed_column_errors.keys()
        for _, orgs in form.changed_column_errors.items():
            for org in orgs:
                changed_column_orgs.add(org)
    return render_template(
        "deliver_grant_funding/collections/data_sets/replace_dataset.html",
        grant=collection.grant,
        collection=collection,
        gr_errors=gr_errors,
        form=form,
        data_source=data_source,
        removed_column_submitted_errors=removed_columns,
        removed_column_org_submitted_errors=removed_column_orgs,
        changed_column_submitted_errors=changed_columns,
        changed_column_org_submitted_errors=changed_column_orgs,
    )


def _save_replaced_data_set_and_redirect(
    existing_datasource: DataSource,
    grant_id: UUID,
    collection: Collection,
    data_set_data: DataSetUploadSessionModel,
    rows: TUnvalidatedDataSetRows | None = None,
) -> ResponseReturnValue:
    replace_uploaded_data_source(
        data_source=existing_datasource,
        new_columns=data_set_data.column_mappings,
        all_headers=data_set_data.data_columns,
        all_rows=rows or [],
        s3_key=data_set_data.s3_key,
        original_filename=data_set_data.original_filename,
        user=get_current_user(),
        name=data_set_data.name if data_set_data.name != existing_datasource.name else NOT_PROVIDED,
    )

    del session[SESSION_DATA_SET_REPLACE]
    s3_service.update_file_tags(data_set_data.s3_key, {"status": DataSourceFileTagEnum.IN_USE})
    flash(
        Markup(
            f"You can now reference {escape(existing_datasource.name)} data "
            + f"in the {escape(collection.name)} form. "
        ),
        FlashMessageType.DATA_SOURCE_REPLACED_SUCCESS,
    )
    return redirect(
        url_for(
            "deliver_grant_funding.view_data_source",
            grant_id=grant_id,
            collection_id=collection.id,
            collection_type=collection.type,
            data_source_id=existing_datasource.id,
        )
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/<collection_type:collection_type>/<uuid:collection_id>/data-set/<uuid:data_source_id>/replace/map-columns",
    methods=["GET", "POST"],
)
@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/<collection_type:collection_type>/<uuid:collection_id>/data-set/map-columns",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def map_data_set_columns(  # noqa: C901
    grant_id: UUID, collection_type: CollectionType, collection_id: UUID, data_source_id: UUID | None = None
) -> ResponseReturnValue:
    collection = get_collection(collection_id, grant_id=grant_id, type_=collection_type)

    data_set_data = _extract_data_set_data_from_session(data_source_id)

    if not data_set_data:
        if data_source_id:
            return redirect(
                url_for(
                    "deliver_grant_funding.replace_data_set",
                    grant_id=grant_id,
                    collection_type=collection_type,
                    collection_id=collection_id,
                    data_source_id=data_source_id,
                )
            )
        else:
            return redirect(
                url_for(
                    "deliver_grant_funding.upload_data_set",
                    grant_id=grant_id,
                    collection_type=collection_type,
                    collection_id=collection_id,
                )
            )

    if data_set_data.is_replace:
        existing_datasource = get_data_source(data_set_data.data_source_id, with_organisation_items=True)
        existing_column_names = [col_def.original_column_name for _, col_def in existing_datasource.schema.root.items()]  # ty:ignore[unresolved-attribute]
        columns_to_map = [col for col in data_set_data.data_columns if col not in existing_column_names]
        if not columns_to_map:  # no new columns
            return redirect(
                url_for(
                    "deliver_grant_funding.confirm_data_set",
                    grant_id=grant_id,
                    collection_type=collection_type,
                    collection_id=collection_id,
                    data_source_id=data_source_id,
                )
            )
    else:
        columns_to_map = data_set_data.data_columns

    form = MapDataSetColumnsForm(data_columns=columns_to_map)

    if not form.is_submitted() and data_set_data.column_mappings:
        for idx, mapping in enumerate(data_set_data.column_mappings):
            form.columns.entries[idx].form.column_type.data = mapping.column_type

    if form.validate_on_submit():
        data_set_data.column_mappings = form.get_column_mappings()
        session[SESSION_DATA_SET_REPLACE if data_set_data.is_replace else SESSION_DATA_SET_UPLOAD] = (
            data_set_data.model_dump(mode="json")
        )

        if form.has_british_pounds_columns():
            rows, validation_result = _load_and_validate_data_set(data_set_data)
            british_pounds_errors = [e for e in validation_result.blocking_errors if isinstance(e, BritishPoundsError)]
            if british_pounds_errors:
                errors = sorted(british_pounds_errors, key=lambda e: e.column)
                column_errors = {col: list(errs) for col, errs in groupby(errors, key=lambda e: e.column)}
                form.columns.errors = form.build_british_pounds_form_errors(column_errors)  # ty: ignore[invalid-argument-type]
                return render_template(
                    "deliver_grant_funding/collections/data_sets/map_columns.html",
                    grant=collection.grant,
                    collection=collection,
                    form=form,
                    session_data=data_set_data,
                )

        if data_set_data.has_columns_requiring_manual_formatting():
            return redirect(
                url_for(
                    "deliver_grant_funding.map_data_set_number_columns",
                    grant_id=grant_id,
                    collection_type=collection_type,
                    collection_id=collection_id,
                    data_source_id=data_source_id,
                )
            )

        return redirect(
            url_for(
                "deliver_grant_funding.confirm_data_set",
                grant_id=grant_id,
                collection_type=collection_type,
                collection_id=collection_id,
                data_source_id=data_source_id,
            )
        )

    return render_template(
        "deliver_grant_funding/collections/data_sets/map_columns.html",
        grant=collection.grant,
        collection=collection,
        form=form,
        session_data=data_set_data,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/<collection_type:collection_type>/<uuid:collection_id>/data-set/<uuid:data_source_id>/replace/map-number-columns",
    methods=["GET", "POST"],
)
@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/<collection_type:collection_type>/<uuid:collection_id>/data-set/map-number-columns",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def map_data_set_number_columns(
    grant_id: UUID, collection_type: CollectionType, collection_id: UUID, data_source_id: UUID | None = None
) -> ResponseReturnValue:
    collection = get_collection(collection_id, grant_id=grant_id, type_=collection_type)

    data_set_data = _extract_data_set_data_from_session(data_source_id)
    if not data_set_data:
        if data_source_id:
            return redirect(
                url_for(
                    "deliver_grant_funding.replace_data_set",
                    grant_id=grant_id,
                    collection_type=collection_type,
                    collection_id=collection_id,
                    data_source_id=data_source_id,
                )
            )
        else:
            return redirect(
                url_for(
                    "deliver_grant_funding.upload_data_set",
                    grant_id=grant_id,
                    collection_type=collection_type,
                    collection_id=collection_id,
                )
            )

    number_columns = [mapping for mapping in data_set_data.column_mappings if mapping.requires_manual_formatting]

    form = MapNumberColumnsForm(numerical_columns=number_columns, data_set_data=data_set_data)

    if not form.is_submitted() and data_set_data.column_mappings:
        for idx, mapping in enumerate(number_columns):
            entry = form.columns.entries[idx].form
            entry.prefix.data = mapping.prefix or ""
            entry.suffix.data = mapping.suffix or ""
            if mapping.number_type == NumberTypeEnum.DECIMAL:
                entry.max_decimal_places.data = mapping.max_decimal_places if mapping.max_decimal_places else None

    if form.validate_on_submit():
        settings = form.get_number_column_formatting_options_mappings()
        for mapping in data_set_data.column_mappings:
            if mapping.column_name in settings:
                mapping.prefix = settings[mapping.column_name]["prefix"]
                mapping.suffix = settings[mapping.column_name]["suffix"]
                if mapping.number_type == NumberTypeEnum.DECIMAL:
                    mapping.max_decimal_places = settings[mapping.column_name]["max_decimal_places"]
        session[SESSION_DATA_SET_REPLACE if data_set_data.is_replace else SESSION_DATA_SET_UPLOAD] = (
            data_set_data.model_dump(mode="json")
        )

        rows, validation_result = _load_and_validate_data_set(data_set_data)

        if validation_result.blocking_errors:
            errors = sorted(validation_result.blocking_errors, key=lambda e: e.column)
            column_errors = {col: list(errs) for col, errs in groupby(errors, key=lambda e: e.column)}
            form.columns.errors = form.build_number_column_form_errors(column_errors)
        else:
            return redirect(
                url_for(
                    "deliver_grant_funding.confirm_data_set",
                    grant_id=grant_id,
                    collection_type=collection_type,
                    collection_id=collection_id,
                    data_source_id=data_source_id,
                )
            )

    return render_template(
        "deliver_grant_funding/collections/data_sets/map_number_columns.html",
        grant=collection.grant,
        collection=collection,
        form=form,
        session_data=data_set_data,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/<collection_type:collection_type>/<uuid:collection_id>/data-set/<uuid:data_source_id>/replace/confirm",
    methods=["GET", "POST"],
)
@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/<collection_type:collection_type>/<uuid:collection_id>/data-set/confirm",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def confirm_data_set(  # noqa: C901
    grant_id: UUID, collection_type: CollectionType, collection_id: UUID, data_source_id: UUID | None = None
) -> ResponseReturnValue:
    collection = get_collection(collection_id, grant_id=grant_id, type_=collection_type)
    existing_datasource = get_data_source(data_source_id, with_organisation_items=True) if data_source_id else None
    user = get_current_user()
    form = GenericSubmitForm()

    if collection.grant_id != grant_id or (
        existing_datasource is not None
        and (existing_datasource.collection_id != collection_id or existing_datasource.grant_id != grant_id)
    ):
        abort(404)
    data_set_data = _extract_data_set_data_from_session(data_source_id)
    if not data_set_data:
        if data_source_id:
            return redirect(
                url_for(
                    "deliver_grant_funding.replace_data_set",
                    grant_id=grant_id,
                    collection_type=collection_type,
                    collection_id=collection_id,
                    data_source_id=data_source_id,
                )
            )
        else:
            return redirect(
                url_for(
                    "deliver_grant_funding.upload_data_set",
                    grant_id=grant_id,
                    collection_type=collection_type,
                    collection_id=collection_id,
                )
            )

    rows = _load_rows(data_set_data)
    if not form.is_submitted():
        columns_to_display_in_formatting = []
        columns_to_display_in_formatting.extend(data_set_data.column_mappings)
        if data_set_data.is_replace:
            existing_columns = [
                v
                for k, v in existing_datasource.schema.root.items()  # ty:ignore[unresolved-attribute]
                if v.original_column_name in data_set_data.data_columns
            ]
            columns_to_display_in_formatting.extend(
                [DataSetColumnMapping.build_from_data_source_schema_column(col) for col in existing_columns]
            )

        grant_recipients = interfaces.grant_recipients.get_grant_recipients(collection.grant, with_organisations=True)
        missing_data_rows = build_data_display_rows_with_missing_tags(
            data_set_data.data_columns, rows, grant_recipients, include_all_grant_recipients=True
        )
        formatted_data_rows: list[dict[str, str | None]] = []
        for row in rows:
            formatted_row = {
                column_def.column_name: format_data_set_csv_data_for_column_type(
                    column_def, row[column_def.column_name]
                )
                for column_def in columns_to_display_in_formatting
            }
            formatted_data_rows.append(formatted_row)

    if form.validate_on_submit():
        if data_set_data.is_replace:
            return _save_replaced_data_set_and_redirect(
                grant_id=grant_id,
                collection=collection,
                data_set_data=data_set_data,
                existing_datasource=existing_datasource,  # ty:ignore[invalid-argument-type]
                rows=rows,
            )
        data_source = create_uploaded_data_source(
            name=data_set_data.name,
            data_source_type=data_set_data.data_source_type,
            grant_id=grant_id,
            collection_id=collection.id,
            column_mappings=data_set_data.column_mappings,
            all_rows=rows,
            user=user,
            s3_key=data_set_data.s3_key,
            original_filename=data_set_data.original_filename,
            data_source_id=data_set_data.data_source_id,
        )

        s3_service.update_file_tags(data_set_data.s3_key, {"status": DataSourceFileTagEnum.IN_USE})

        data_source_url = url_for(
            "deliver_grant_funding.view_data_source",
            grant_id=grant_id,
            collection_type=collection_type,
            collection_id=collection_id,
            data_source_id=data_source.id,
        )
        session.pop(SESSION_DATA_SET_UPLOAD, None)
        flash(
            Markup(
                (
                    f"You can now reference {escape(data_source.name)} data "
                    + f"in the {escape(collection.name)} grant form. "
                    + f"<a class='govuk-link govuk-link--no-visited-state' href='{data_source_url}'>View data set</a>"
                )
            ),
            FlashMessageType.DATA_SOURCE_UPLOADED_SUCCESS.value,
        )

        return redirect(
            url_for(
                "deliver_grant_funding.list_collection_data_sets",
                grant_id=grant_id,
                collection_type=collection_type,
                collection_id=collection_id,
            )
        )
    return render_template(
        "deliver_grant_funding/collections/data_sets/data_set_final_preview.html",
        grant=collection.grant,
        collection=collection,
        session_data=data_set_data,
        form=form,
        columns_to_display_in_formatting=columns_to_display_in_formatting,
        all_rows=rows,
        missing_data_rows=missing_data_rows,
        formatted_data_rows=formatted_data_rows,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/<collection_type:collection_type>/<uuid:collection_id>/data-set/<uuid:data_source_id>/replace/confirm-grant-recipients",
    methods=["GET", "POST"],
)
@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/<collection_type:collection_type>/<uuid:collection_id>/data-set/confirm-grant-recipients",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
def confirm_data_set_grant_recipients(
    grant_id: UUID, collection_type: CollectionType, collection_id: UUID, data_source_id: UUID | None = None
) -> ResponseReturnValue:
    collection = get_collection(collection_id, grant_id=grant_id, type_=collection_type)

    data_set_data = _extract_data_set_data_from_session(data_source_id)
    if not data_set_data:
        if data_source_id:
            return redirect(
                url_for(
                    "deliver_grant_funding.replace_data_set",
                    grant_id=grant_id,
                    collection_type=collection_type,
                    collection_id=collection_id,
                    data_source_id=data_source_id,
                )
            )
        else:
            return redirect(
                url_for(
                    "deliver_grant_funding.upload_data_set",
                    grant_id=grant_id,
                    collection_type=collection_type,
                    collection_id=collection_id,
                )
            )

    rows = _load_rows(data_set_data)
    grant_recipients = interfaces.grant_recipients.get_grant_recipients(collection.grant, with_organisations=True)
    gr_mismatches = find_grant_recipient_mismatches(rows, grant_recipients)

    if not gr_mismatches:
        return redirect(
            url_for(
                "deliver_grant_funding.data_set_missing_data",
                grant_id=grant_id,
                collection_type=collection_type,
                collection_id=collection_id,
                data_source_id=data_source_id,
            )
        )

    form = GenericSubmitForm()

    if form.validate_on_submit():
        data_set_data.has_grant_recipient_mismatches = True
        session[SESSION_DATA_SET_REPLACE if data_set_data.is_replace else SESSION_DATA_SET_UPLOAD] = (
            data_set_data.model_dump(mode="json")
        )

        return redirect(
            url_for(
                "deliver_grant_funding.data_set_missing_data",
                grant_id=grant_id,
                collection_type=collection_type,
                collection_id=collection_id,
                data_source_id=data_source_id,
            )
        )

    return render_template(
        "deliver_grant_funding/collections/data_sets/data_set_confirm_grant_recipients.html",
        grant=collection.grant,
        collection=collection,
        session_data=data_set_data,
        gr_mismatches=gr_mismatches,
        form=form,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/<collection_type:collection_type>/<uuid:collection_id>/data-set/<uuid:data_source_id>/replace/missing-data",
    methods=["GET", "POST"],
)
@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/<collection_type:collection_type>/<uuid:collection_id>/data-set/missing-data",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.ADMIN)
@auto_commit_after_request
def data_set_missing_data(
    grant_id: UUID, collection_type: CollectionType, collection_id: UUID, data_source_id: UUID | None = None
) -> ResponseReturnValue:
    collection = get_collection(collection_id, grant_id=grant_id, type_=collection_type)

    data_set_data = _extract_data_set_data_from_session(data_source_id)
    if not data_set_data:
        if data_source_id:
            return redirect(
                url_for(
                    "deliver_grant_funding.replace_data_set",
                    grant_id=grant_id,
                    collection_type=collection_type,
                    collection_id=collection_id,
                    data_source_id=data_source_id,
                )
            )
        else:
            return redirect(
                url_for(
                    "deliver_grant_funding.upload_data_set",
                    grant_id=grant_id,
                    collection_type=collection_type,
                    collection_id=collection_id,
                )
            )

    rows = _load_rows(data_set_data)

    grant_recipients = interfaces.grant_recipients.get_grant_recipients(collection.grant, with_organisations=True)
    missing_data_rows = build_data_display_rows_with_missing_tags(data_set_data.data_columns, rows, grant_recipients)

    if not missing_data_rows:
        return redirect(
            url_for(
                "deliver_grant_funding.map_data_set_columns",
                grant_id=grant_id,
                collection_type=collection_type,
                collection_id=collection_id,
                data_source_id=data_source_id,
            )
        )

    form = GenericSubmitForm()

    if form.validate_on_submit():
        data_set_data.has_missing_data = True
        session[SESSION_DATA_SET_REPLACE if data_set_data.is_replace else SESSION_DATA_SET_UPLOAD] = (
            data_set_data.model_dump(mode="json")
        )

        return redirect(
            url_for(
                "deliver_grant_funding.map_data_set_columns",
                grant_id=grant_id,
                collection_type=collection_type,
                collection_id=collection_id,
                data_source_id=data_source_id,
            )
        )

    return render_template(
        "deliver_grant_funding/collections/data_sets/data_set_missing_data.html",
        grant=collection.grant,
        collection=collection,
        session_data=data_set_data,
        form=form,
        missing_data_rows=missing_data_rows,
        all_rows=rows,
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/<collection_type:collection_type>/<uuid:collection_id>/data-sets/<uuid:data_source_id>",
    methods=["GET", "POST"],
)
@has_deliver_grant_role(RoleEnum.MEMBER)
@auto_commit_after_request
def view_data_source(
    grant_id: UUID, collection_type: CollectionType, collection_id: UUID, data_source_id: UUID
) -> ResponseReturnValue:
    collection = get_collection(collection_id, grant_id=grant_id, type_=collection_type)

    data_source = get_data_source(data_source_id, with_organisation_items=True)

    # TODO FSPT-1044: We should do this filtering in the interface rather than here
    if data_source.collection_id != collection_id or data_source.grant_id != grant_id:
        abort(404)

    if data_source.type != DataSourceType.GRANT_RECIPIENT:
        abort(404)

    all_grant_recipients = interfaces.grant_recipients.get_grant_recipients(collection.grant, with_organisations=True)
    current_data_set_view = build_current_data_set_view(data_source, all_grant_recipients)
    has_missing_data = data_source.has_missing_data(all_grant_recipients)

    removed_grant_recipient_names = []
    if current_data_set_view.removed_external_ids:
        removed_organisations = get_organisations(with_external_ids=current_data_set_view.removed_external_ids)
        removed_grant_recipient_names = sorted(org.name for org in removed_organisations)

    delete_wtform = GenericConfirmDeletionForm() if "delete" in request.args else None
    if delete_wtform:
        if not AuthorisationHelper.can_edit_collection(user=get_current_user(), collection_id=collection.id):
            return redirect(
                url_for(
                    "deliver_grant_funding.view_data_source",
                    grant_id=grant_id,
                    collection_type=collection_type,
                    collection_id=collection_id,
                    data_source_id=data_source_id,
                )
            )
        try:
            raise_if_data_source_has_references(data_source)

            if delete_wtform.validate_on_submit():
                name = data_source.name
                delete_data_source(data_source)
                flash(Markup(f"'{escape(name)}' data set has been deleted."), FlashMessageType.DATA_SOURCE_DELETED)
                return redirect(
                    url_for(
                        "deliver_grant_funding.list_collection_data_sets",
                        grant_id=grant_id,
                        collection_type=collection_type,
                        collection_id=collection_id,
                    )
                )
        except DataSourceHasReferencesException as e:
            flash(e.as_flash_context(), FlashMessageType.DATA_SOURCE_REFERENCE_ERROR.value)  # ty: ignore[invalid-argument-type]
            return redirect(
                url_for(
                    "deliver_grant_funding.view_data_source",
                    grant_id=grant_id,
                    collection_type=collection_type,
                    collection_id=collection_id,
                    data_source_id=data_source_id,
                )
            )

    return render_template(
        "deliver_grant_funding/collections/data_sets/view_data_set.html",
        grant=collection.grant,
        collection=collection,
        data_source=data_source,
        delete_form=delete_wtform,
        has_missing_data=has_missing_data,
        current_rows=current_data_set_view.rows,
        added_grant_recipient_names=current_data_set_view.added_grant_recipient_names,
        removed_grant_recipient_names=removed_grant_recipient_names,
        interpolate=SubmissionHelper.get_interpolator(collection=collection),
    )


@deliver_grant_funding_blueprint.route(
    "/grant/<uuid:grant_id>/<collection_type:collection_type>/<uuid:collection_id>/data-sets/<uuid:data_source_id>/download",
    methods=["GET"],
)
@has_deliver_grant_role(RoleEnum.MEMBER)
def download_data_source_csv(
    grant_id: UUID, collection_type: CollectionType, collection_id: UUID, data_source_id: UUID
) -> ResponseReturnValue:
    get_collection(collection_id, grant_id=grant_id, type_=collection_type)
    data_source = get_data_source(data_source_id)

    # TODO FSPT-1044: We should do this filtering in the interface rather than here
    if data_source.collection_id != collection_id or data_source.grant_id != grant_id:
        abort(404)

    if not data_source.file_metadata:
        abort(500)

    file_bytes = s3_service.download_file(data_source.file_metadata.s3_key)
    # This secure_filename use is kind of redundant as we pass the filename through secure_filename when we create the
    # session and ingest to the database, this is just for safety
    filename = secure_filename(data_source.file_metadata.original_filename)

    return send_file(io.BytesIO(file_bytes), mimetype="text/csv", as_attachment=True, download_name=filename, max_age=0)
