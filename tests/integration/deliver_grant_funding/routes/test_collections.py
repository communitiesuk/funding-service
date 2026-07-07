import csv
import datetime
import io
import logging
import uuid
from copy import deepcopy
from datetime import date
from decimal import Decimal
from unittest.mock import patch
from tests.utils import build_file_upload_form_data
import pytest
from _pytest.fixtures import FixtureRequest
from bs4 import BeautifulSoup
from flask import url_for
from sqlalchemy import func, select

from app import CollectionStatusEnum, FlashMessageType, QuestionDataType
from app.common.collections.types import IntegerAnswer, TextSingleLineAnswer
from app.common.data import interfaces
from app.common.data.interfaces.collections import (
    add_component_validation,
)
from app.common.data.models import (
    Collection,
    DataSource,
    DataSourceOrganisationItem,
    Expression,
    Form,
    Group,
    Question,
    Submission,
    SubmissionEvent,
)
from app.common.data.types import (
    CollectionType,
    ConditionsOperator,
    DataSourceFileMetadata,
    DataSourceFileTagEnum,
    DataSourceSchema,
    DataSourceSchemaColumn,
    DataSourceType,
    ExpressionType,
    GrantRecipientModeEnum,
    ManagedExpressionsEnum,
    NumberTypeEnum,
    OrganisationModeEnum,
    QuestionDataOptions,
    QuestionPresentationOptions,
    SubmissionEventType,
    SubmissionModeEnum,
    SubmissionStatusEnum,
    TasklistSectionStatusEnum,
)
from app.common.expressions import (
    ExpressionContext,
)
from app.common.expressions.custom import CustomExpression
from app.common.expressions.forms import (
    CalculatedConditionForm,
    CustomValidationExpressionForm,
    build_managed_expression_form,
)
from app.common.expressions.managed import AnyOf, GreaterThan, IsAfter, IsNo, IsYes, LessThan
from app.common.expressions.references import EvaluationStatement, ExpressionReference, InterpolationStatement
from app.common.forms import GenericConfirmDeletionForm, GenericSubmitForm
from app.common.helpers.collections import SubmissionHelper
from app.constants import (
    DATA_SET_EXTERNAL_ID_COLUMN_HEADER,
    DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER,
    SESSION_DATA_SET_REPLACE,
    SESSION_DATA_SET_UPLOAD,
)
from app.deliver_grant_funding.data_sets import build_data_set_upload_s3_key
from app.deliver_grant_funding.forms import (
    AddGuidanceForm,
    AddSectionForm,
    CollectionCreationMethodForm,
    ConditionsOperatorForm,
    GroupAddAnotherOptionsForm,
    GroupAddAnotherSummaryForm,
    GroupDisplayOptionsForm,
    GroupForm,
    QuestionForm,
    QuestionTypeForm,
    ReopenSubmissionForm,
    RequestChangesSubmissionForm,
    RequestOrAllowChangesSubmissionForm,
    SelectCollectionToCopyForm,
    SetUpCollectionForm,
)
from app.deliver_grant_funding.routes.collections import (
    _determine_return_url_and_update_session_after_choosing_reference_for_expression,
)
from app.deliver_grant_funding.session_models import (
    AddConditionDependsOnSessionModel,
    AddContextToComponentGuidanceSessionModel,
    AddContextToComponentSessionModel,
    AddContextToExpressionsModel,
    DataSetColumnMapping,
    DataSetUploadSessionModel,
)
from tests.integration.utils import build_file_upload_form_data
from tests.models import ALL_COLUMN_TYPE_HEADERS_STR, FactoryAnswer
from app.metrics import MetricEventName
from tests.models import FactoryAnswer
from tests.utils import (
    AnyStringMatching,
    get_form_data,
    get_h1_text,
    get_h2_text,
    get_test_flashes,
    page_has_button,
    page_has_error,
    page_has_flash,
    page_has_link,
)


class TestSetUpCollection:
    @pytest.mark.parametrize(
        "collection_type",
        [CollectionType.MONITORING_REPORT, CollectionType.APPLICATION],
    )
    def test_404(self, authenticated_grant_member_client, collection_type):
        response = authenticated_grant_member_client.get(
            url_for("deliver_grant_funding.set_up_collection", grant_id=uuid.uuid4(), collection_type=collection_type)
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "collection_type, expected_button_text",
        [
            (CollectionType.MONITORING_REPORT, "Create report"),
            (CollectionType.APPLICATION, "Create form"),
        ],
    )
    @pytest.mark.parametrize(
        "client_fixture, can_access",
        [
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ],
    )
    def test_get(
        self,
        request: FixtureRequest,
        client_fixture: str,
        can_access: bool,
        collection_type: CollectionType,
        expected_button_text: str,
        factories,
    ):
        client = request.getfixturevalue(client_fixture)
        factories.collection.create(grant=client.grant)

        response = client.get(
            url_for(
                "deliver_grant_funding.set_up_collection", grant_id=client.grant.id, collection_type=collection_type
            )
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert page_has_button(soup, expected_button_text)

    @pytest.mark.parametrize(
        "collection_type, expected_redirect_pattern",
        [
            (CollectionType.MONITORING_REPORT, r"^/deliver/grant/[a-z0-9-]{36}/reports$"),
            (CollectionType.APPLICATION, r"^/deliver/grant/[a-z0-9-]{36}/pre-award$"),
        ],
    )
    @pytest.mark.parametrize(
        "client_fixture, can_access",
        [
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ],
    )
    def test_post(
        self,
        request: FixtureRequest,
        client_fixture: str,
        can_access: bool,
        collection_type: CollectionType,
        expected_redirect_pattern: str,
        factories,
        db_session,
    ):
        client = request.getfixturevalue(client_fixture)
        collections_attr = "reports" if collection_type == CollectionType.MONITORING_REPORT else "pre_award_forms"
        assert len(getattr(client.grant, collections_attr)) == 0

        form = SetUpCollectionForm(data={"name": "Test collection"}, collection_type=collection_type)
        response = client.post(
            url_for(
                "deliver_grant_funding.set_up_collection", grant_id=client.grant.id, collection_type=collection_type
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 302
            assert response.location == AnyStringMatching(expected_redirect_pattern)

            created = getattr(client.grant, collections_attr)
            assert len(created) == 1
            assert created[0].name == "Test collection"
            assert created[0].created_by == client.user

    @pytest.mark.parametrize(
        "collection_type, copy",
        [
            (CollectionType.MONITORING_REPORT, False),
            (CollectionType.APPLICATION, False),
            (CollectionType.MONITORING_REPORT, True),
            (CollectionType.APPLICATION, True),
        ],
    )
    def test_post_shows_created_flash(
        self, authenticated_grant_admin_client, factories, collection_type: CollectionType, copy: bool
    ):
        client = authenticated_grant_admin_client
        client.grant.allow_pre_award = True
        url = url_for(
            "deliver_grant_funding.set_up_collection", grant_id=client.grant.id, collection_type=collection_type
        )
        if copy:
            source = factories.collection.create(grant=client.grant, name="Source", type=collection_type)
            url = f"{url}?copy_from={source.id}"

        form = SetUpCollectionForm(data={"name": "My new collection"}, collection_type=collection_type)
        response = client.post(url, data=get_form_data(form), follow_redirects=True)

        soup = BeautifulSoup(response.data, "html.parser")
        singular = collection_type.constants.singular
        banner = page_has_flash(soup, f"My new collection {singular} created")
        assert banner
        link = banner.find("a", class_="govuk-notification-banner__link")
        assert link
        assert f"My new collection {singular}" in link.text

    @pytest.mark.parametrize(
        "collection_type, expected_error",
        [
            (CollectionType.MONITORING_REPORT, "A report with this name already exists"),
            (CollectionType.APPLICATION, "A form with this name already exists"),
        ],
    )
    def test_post_duplicate_name(
        self, authenticated_grant_admin_client, factories, collection_type: CollectionType, expected_error: str
    ):
        factories.collection.create(
            grant=authenticated_grant_admin_client.grant, name="Test collection", type=collection_type
        )

        form = SetUpCollectionForm(data={"name": "Test collection"}, collection_type=collection_type)
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.set_up_collection",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=collection_type,
            ),
            data=get_form_data(form),
        )
        soup = BeautifulSoup(response.data, "html.parser")

        assert response.status_code == 200
        assert page_has_error(soup, expected_error)

    @pytest.mark.parametrize("collection_type", CollectionType)
    @patch("app.deliver_grant_funding.routes.collections.emit_metric_count")
    def test_set_up_collection_as_a_copy(
        self, mock_count, authenticated_grant_admin_client, factories, collection_type
    ):
        source_collection = factories.collection.create(
            grant=authenticated_grant_admin_client.grant, name="Test collection", type=collection_type
        )

        form = SetUpCollectionForm(data={"name": "Test collection copy"}, collection_type=collection_type)
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.set_up_collection",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=collection_type,
                copy_from=source_collection.id,
            ),
            data=get_form_data(form),
        )
        assert response.status_code == 302

        mock_count.assert_called_once_with(MetricEventName.COLLECTION_COPIED, 1, collection=source_collection)


class TestChangeCollectionName:
    def test_404(self, authenticated_grant_member_client):
        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.change_collection_name",
                grant_id=uuid.uuid4(),
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=uuid.uuid4(),
            )
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get(self, request: FixtureRequest, client_fixture: str, can_access: bool, factories):
        client = request.getfixturevalue(client_fixture)
        collection = factories.collection.create(grant=client.grant, name="Test Report")

        response = client.get(
            url_for(
                "deliver_grant_funding.change_collection_name",
                grant_id=client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert "Test Report" in soup.text

    def test_get_with_delete_parameter_with_live_submissions(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        factories.submission.create(collection=collection, mode=SubmissionModeEnum.LIVE)

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.change_collection_name",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                delete="",
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert not page_has_button(soup, "Yes, delete this report")

    @pytest.mark.parametrize(
        "collection_type, expected_redirect_pattern",
        [
            (CollectionType.MONITORING_REPORT, r"^/deliver/grant/[a-z0-9-]{36}/reports$"),
            (CollectionType.APPLICATION, r"^/deliver/grant/[a-z0-9-]{36}/pre-award$"),
        ],
    )
    @pytest.mark.parametrize(
        "client_fixture, can_access",
        [
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ],
    )
    def test_post_update_name(
        self,
        request: FixtureRequest,
        client_fixture: str,
        can_access: bool,
        collection_type: CollectionType,
        expected_redirect_pattern: str,
        factories,
        db_session,
    ):
        client = request.getfixturevalue(client_fixture)
        collection = factories.collection.create(grant=client.grant, name="Original Name", type=collection_type)

        form = SetUpCollectionForm(data={"name": "Updated Name"}, collection_type=collection_type)
        response = client.post(
            url_for(
                "deliver_grant_funding.change_collection_name",
                grant_id=client.grant.id,
                collection_type=collection_type,
                collection_id=collection.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 302
            assert response.location == AnyStringMatching(expected_redirect_pattern)

            updated_collection = db_session.get(Collection, collection.id)
            assert updated_collection.name == "Updated Name"

    def test_post_update_name_duplicate(self, authenticated_grant_admin_client, factories):
        factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Existing Report")
        collection2 = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Another Report")

        form = SetUpCollectionForm(data={"name": "Existing Report"}, collection_type=CollectionType.MONITORING_REPORT)
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.change_collection_name",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection2.id,
            ),
            data=get_form_data(form),
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "A report with this name already exists")

    def test_update_name_when_delete_banner_showing_does_not_delete(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Original Name")

        form = SetUpCollectionForm(data={"name": "Updated Name"}, collection_type=CollectionType.MONITORING_REPORT)
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.change_collection_name",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                delete="",
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/reports$")

        updated_collection = db_session.get(Collection, collection.id)
        assert updated_collection is not None
        assert updated_collection.name == "Updated Name"


class TestAddSection:
    def test_404(self, authenticated_grant_member_client):
        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.add_section",
                grant_id=uuid.uuid4(),
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=uuid.uuid4(),
            )
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get(self, request: FixtureRequest, client_fixture: str, can_access: bool, factories):
        client = request.getfixturevalue(client_fixture)
        collection = factories.collection.create(grant=client.grant)

        response = client.get(
            url_for(
                "deliver_grant_funding.add_section",
                grant_id=client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert get_h1_text(soup) == "What is the name of the section?"

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_post(self, request: FixtureRequest, client_fixture: str, can_access: bool, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        collection = factories.collection.create(grant=client.grant)

        form = AddSectionForm(data={"title": "Organisation information"})
        response = client.post(
            url_for(
                "deliver_grant_funding.add_section",
                grant_id=client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 302
            assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/reports/[a-z0-9-]{36}$")

            assert len(collection.forms) == 1
            assert collection.forms[0].title == "Organisation information"

    def test_post_duplicate_form_name(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Monitoring report")
        factories.form.create(collection=collection, title="Organisation information")

        form = AddSectionForm(data={"title": "Organisation information"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_section",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            ),
            data=get_form_data(form),
        )
        soup = BeautifulSoup(response.data, "html.parser")

        assert response.status_code == 200
        assert page_has_error(soup, "A section with this name already exists")


class TestListCollectionSections:
    def test_404(self, authenticated_grant_member_client):
        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.list_collection_sections",
                grant_id=uuid.uuid4(),
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=uuid.uuid4(),
            )
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_edit",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get_no_sections(self, request: FixtureRequest, client_fixture: str, can_edit: bool, factories):
        client = request.getfixturevalue(client_fixture)
        collection = factories.collection.create(grant=client.grant, name="Test Report")

        response = client.get(
            url_for(
                "deliver_grant_funding.list_collection_sections",
                grant_id=client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "This report has no sections." in soup.text

        add_section_link = page_has_link(soup, "Add a section")
        assert (add_section_link is not None) is can_edit

        if add_section_link:
            expected_href = AnyStringMatching(r"/deliver/grant/[a-z0-9-]{36}/reports/[a-z0-9-]{36}/add-section")
            assert add_section_link.get("href") == expected_href

    @pytest.mark.parametrize(
        "client_fixture, can_edit",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get_with_sections(self, request: FixtureRequest, client_fixture: str, can_edit: bool, factories):
        client = request.getfixturevalue(client_fixture)
        collection = factories.collection.create(grant=client.grant, name="Test Report")
        factories.form.create(collection=collection, title="Organisation information")

        response = client.get(
            url_for(
                "deliver_grant_funding.list_collection_sections",
                grant_id=client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Organisation information" in soup.text

        manage_section_link = page_has_link(soup, "Organisation information")
        add_another_section_list = page_has_link(soup, "Add another section")

        assert manage_section_link is not None
        assert (add_another_section_list is not None) is can_edit

        assert soup.find("details", id="previewers-details") is None

    @pytest.mark.parametrize(
        "client_fixture, can_edit",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get_with_previews(self, request: FixtureRequest, client_fixture: str, can_edit: bool, factories):
        preview_user = factories.user.create()
        client = request.getfixturevalue(client_fixture)
        collection = factories.collection.create(grant=client.grant, name="Test Report")
        factories.form.create(collection=collection, title="Organisation information")

        factories.submission.create(collection=collection, mode=SubmissionModeEnum.PREVIEW, created_by=preview_user)

        response = client.get(
            url_for(
                "deliver_grant_funding.list_collection_sections",
                grant_id=client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Organisation information" in soup.text

        # only people that can edit should see who has previewed, this should always be shown even
        # after the collection is locked
        if can_edit:
            assert "1 previewers" in soup.text
            preview_list = soup.find("details", id="previewers-details")
            assert preview_user.name in preview_list.text
        else:
            assert "1 previewers" not in soup.text

    def test_get_preview_not_available_when_data_sources(self, authenticated_grant_member_client, factories):
        grant = authenticated_grant_member_client.grant
        collection = factories.collection.create(grant=grant, name="Test Report")
        form = factories.form.create(collection=collection)
        factories.question.create(form=form)
        factories.data_source.create(
            grant=grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
        )

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.list_collection_sections",
                grant_id=grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Preview not available" in soup.text
        assert not page_has_button(soup, button_text="Preview report")

    def test_get_preview_not_available_when_collection_closed(self, authenticated_grant_member_client, factories):
        grant = authenticated_grant_member_client.grant
        collection = factories.collection.create(grant=grant, name="Test Report", status=CollectionStatusEnum.CLOSED)
        form = factories.form.create(collection=collection)
        factories.question.create(form=form)

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.list_collection_sections",
                grant_id=grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Preview not available" in soup.text
        assert not page_has_button(soup, button_text="Preview report")

    @pytest.mark.parametrize(
        "client_fixture, can_preview",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_member_client", True),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_post_list_report_sections_preview(
        self, request: FixtureRequest, client_fixture: str, can_preview: bool, factories, db_session
    ):
        client = request.getfixturevalue(client_fixture)
        generic_grant = factories.grant.create()
        grant = getattr(client, "grant", None) or generic_grant

        collection = factories.collection.create(grant=grant, name="Test Report")

        form = GenericSubmitForm()
        response = client.post(
            url_for(
                "deliver_grant_funding.list_collection_sections",
                grant_id=grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        if not can_preview:
            assert response.status_code == 403
        else:
            assert response.status_code == 302
            assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/submissions/[a-z0-9-]{36}$")


class TestCollectionTypeURLMatching:
    """Tests that the collection_type URL converter correctly gates collection type access."""

    def test_monitoring_report_type_loads_monitoring_report_collection(
        self, authenticated_grant_member_client, factories
    ):
        collection = factories.collection.create(
            grant=authenticated_grant_member_client.grant, type=CollectionType.MONITORING_REPORT
        )
        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.list_collection_sections",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )
        assert response.status_code == 200

    def test_application_type_loads_application_collection(self, authenticated_grant_member_client, factories):
        collection = factories.collection.create(
            grant=authenticated_grant_member_client.grant, type=CollectionType.APPLICATION
        )
        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.list_collection_sections",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.APPLICATION,
                collection_id=collection.id,
            )
        )
        assert response.status_code == 200

    def test_monitoring_report_type_returns_404_for_application_collection(
        self, authenticated_grant_member_client, factories
    ):
        collection = factories.collection.create(
            grant=authenticated_grant_member_client.grant, type=CollectionType.APPLICATION
        )
        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.list_collection_sections",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )
        assert response.status_code == 404

    def test_application_type_returns_404_for_monitoring_report_collection(
        self, authenticated_grant_member_client, factories
    ):
        collection = factories.collection.create(
            grant=authenticated_grant_member_client.grant, type=CollectionType.MONITORING_REPORT
        )
        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.list_collection_sections",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.APPLICATION,
                collection_id=collection.id,
            )
        )
        assert response.status_code == 404

    def test_invalid_slug_returns_404(self, authenticated_grant_member_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant)
        grant_id = authenticated_grant_member_client.grant.id
        collection_id = collection.id
        response = authenticated_grant_member_client.get(f"/deliver/grant/{grant_id}/invalid_slug/{collection_id}")
        assert response.status_code == 404


class TestConfigureMultipleSubmissions:
    def test_get_configure_multiple_submissions(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.collection_configure_multiple_submissions",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Should this collection allow multiple submissions per grant recipient?" in soup.text

    def test_can_only_select_from_supported_question_types(self, app, authenticated_grant_admin_client, factories):
        assert app.config["QUESTION_DATA_TYPES_ALLOWED_FOR_MULTI_SUBMISSION_NAMES"] == {
            QuestionDataType.RADIOS,
            QuestionDataType.TEXT_SINGLE_LINE,
        }

        q1 = factories.question.create(
            form__collection__grant=authenticated_grant_admin_client.grant,
            form__collection__allow_multiple_submissions=True,
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
        )
        q2 = factories.question.create(
            form=q1.form,
            data_type=QuestionDataType.RADIOS,
        )
        q3 = factories.question.create(
            form=q1.form,
            data_type=QuestionDataType.NUMBER,
        )
        q4 = factories.question.create(
            form=q1.form,
            data_type=QuestionDataType.CHECKBOXES,
        )
        collection = q1.form.collection
        collection.submission_name_question_id = q1.id

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.collection_configure_multiple_submissions",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert soup.find("option", {"value": str(q1.id)})
        assert soup.find("option", {"value": str(q2.id)})
        assert not soup.find("option", {"value": str(q3.id)})
        assert not soup.find("option", {"value": str(q4.id)})

    def test_cant_select_add_another_questions_of_valid_data_type(
        self, app, authenticated_grant_admin_client, factories
    ):
        group = factories.group.create(
            form__collection__grant=authenticated_grant_admin_client.grant,
            form__collection__allow_multiple_submissions=True,
            add_another=True,
        )
        q1 = factories.question.create(
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            parent=group,
        )
        q2 = factories.question.create(
            form=q1.form,
            data_type=QuestionDataType.RADIOS,
            parent=group,
        )
        collection = q1.form.collection
        collection.submission_name_question_id = q1.id

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.collection_configure_multiple_submissions",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert not soup.find("option", {"value": str(q1.id)})
        assert not soup.find("option", {"value": str(q2.id)})

    def test_get_configure_multiple_submissions_prepopulates_when_already_enabled(
        self, authenticated_grant_admin_client, factories
    ):
        question = factories.question.create(
            form__collection__grant=authenticated_grant_admin_client.grant,
            form__collection__allow_multiple_submissions=True,
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            name="submission_name_field",
        )
        collection = question.form.collection
        collection.submission_name_question_id = question.id

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.collection_configure_multiple_submissions",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        yes_radio = soup.find("input", {"value": "True"})
        assert yes_radio is not None

    def test_post_disable_multiple_submissions(self, authenticated_grant_admin_client, factories):
        question = factories.question.create(
            form__collection__grant=authenticated_grant_admin_client.grant,
            form__collection__allow_multiple_submissions=True,
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
        )
        collection = question.form.collection
        collection.submission_name_question_id = question.id

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.collection_configure_multiple_submissions",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            ),
            data={"allow_multiple_submissions": False, "submit": "Save"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert collection.allow_multiple_submissions is False
        assert collection.submission_name_question_id is None

    def test_post_enable_multiple_submissions(self, authenticated_grant_admin_client, factories):
        question = factories.question.create(
            form__collection__grant=authenticated_grant_admin_client.grant,
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
        )
        collection = question.form.collection

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.collection_configure_multiple_submissions",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            ),
            data={
                "allow_multiple_submissions": True,
                "submission_name_question": str(question.id),
                "submit": "Save",
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert collection.allow_multiple_submissions is True
        assert collection.submission_name_question_id == question.id

    def test_post_enable_without_question_shows_error(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.collection_configure_multiple_submissions",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            ),
            data={"allow_multiple_submissions": True, "submit": "Save"},
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "Select a question to use as the submission name")


class TestConfigurePublicSignUp:
    def test_get_configure_public_sign_up(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.collection_configure_public_sign_up",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Should this collection allow public self sign up?" in soup.text

    def test_get_configure_public_sign_up_prepopulates_when_already_enabled(
        self, authenticated_grant_admin_client, factories
    ):
        collection = factories.collection.create(
            grant=authenticated_grant_admin_client.grant,
            allow_public_sign_up=True,
        )

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.collection_configure_public_sign_up",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        yes_radio = soup.find("input", {"value": "True"})
        assert yes_radio is not None

    def test_post_enable_public_sign_up(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.collection_configure_public_sign_up",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            ),
            data={"allow_public_sign_up": True, "submit": "Save"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert collection.allow_public_sign_up is True

    def test_post_disable_public_sign_up(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(
            grant=authenticated_grant_admin_client.grant,
            allow_public_sign_up=True,
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.collection_configure_public_sign_up",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            ),
            data={"allow_public_sign_up": False, "submit": "Save"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert collection.allow_public_sign_up is False

    def test_post_shows_error_when_collection_not_editable(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(
            grant=authenticated_grant_admin_client.grant,
            status=CollectionStatusEnum.OPEN,
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.collection_configure_public_sign_up",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            ),
            data={"allow_public_sign_up": True, "submit": "Save"},
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "You cannot change this setting as the collection is not currently editable")

    def test_grant_member_cannot_access(self, authenticated_grant_member_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant)

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.collection_configure_public_sign_up",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )

        assert response.status_code == 403


class TestReportSectionsConfigurePublicSignUp:
    def test_link_hidden_when_grant_pre_award_disabled(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.list_collection_sections",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Configure public sign up" not in soup.text

    def test_link_hidden_when_grant_pre_award_enabled(self, authenticated_grant_admin_client, factories):
        authenticated_grant_admin_client.grant.allow_pre_award = True
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.list_collection_sections",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Configure public sign up" in soup.text


class TestSetGuidanceForMultipleSubmissions:
    def test_get_renders_form(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(
            grant=authenticated_grant_admin_client.grant, name="Test Report", allow_multiple_submissions=True
        )

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.set_guidance_for_multiple_submissions",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Set guidance for multiple submissions"

    def test_get_prepopulates_existing_guidance(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(
            grant=authenticated_grant_admin_client.grant,
            allow_multiple_submissions=True,
            submission_guidance="Existing guidance content",
        )

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.set_guidance_for_multiple_submissions",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        textarea = soup.find("textarea")
        assert textarea is not None
        assert "Existing guidance content" in textarea.text

    def test_post_save_guidance_redirects_to_sections(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(
            grant=authenticated_grant_admin_client.grant, name="Test Report", allow_multiple_submissions=True
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.set_guidance_for_multiple_submissions",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            ),
            data={"guidance_body": "New guidance content", "submit": "Save guidance"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "deliver_grant_funding.list_collection_sections",
            grant_id=authenticated_grant_admin_client.grant.id,
            collection_type=CollectionType.MONITORING_REPORT,
            collection_id=collection.id,
        )
        assert collection.submission_guidance == "New guidance content"

    def test_post_save_and_preview_redirects_back_with_anchor(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(
            grant=authenticated_grant_admin_client.grant, name="Test Report", allow_multiple_submissions=True
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.set_guidance_for_multiple_submissions",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            ),
            data={"guidance_body": "Preview this", "preview": "Save and preview guidance"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "#preview-guidance" in response.location
        assert collection.submission_guidance == "Preview this"

    def test_post_save_empty_guidance_clears_it(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(
            grant=authenticated_grant_admin_client.grant,
            allow_multiple_submissions=True,
            submission_guidance="Old guidance",
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.set_guidance_for_multiple_submissions",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            ),
            data={"guidance_body": "", "submit": "Save guidance"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert collection.submission_guidance is None


class TestMoveSection:
    def test_404(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.move_section",
                grant_id=uuid.uuid4(),
                form_id=uuid.uuid4(),
                direction="up",
            )
        )
        assert response.status_code == 404

    def test_400(self, authenticated_grant_admin_client, factories, db_session):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        forms = factories.form.create_batch(3, collection=collection)

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.move_section",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=forms[0].id,
                direction="blah",
            )
        )
        assert response.status_code == 400

    @pytest.mark.parametrize(
        "direction",
        ["up", "down"],
    )
    def test_move(self, authenticated_grant_admin_client, factories, db_session, direction):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        factories.form.reset_sequence()
        forms = factories.form.create_batch(3, collection=collection)
        assert forms[1].title == "Form 1"

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.move_section",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=forms[1].id,
                direction=direction,
            )
        )
        assert response.status_code == 302

        if direction == "up":
            assert collection.forms[0].title == "Form 1"
        else:
            assert collection.forms[2].title == "Form 1"

    def test_cannot_move_above_referenced_section(self, app, authenticated_grant_admin_client, factories, db_session):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        factories.form.reset_sequence()
        forms = factories.form.create_batch(2, collection=collection)
        assert forms[1].title == "Form 1"

        q1 = factories.question.create(form=forms[0], data_type=QuestionDataType.YES_NO)
        factories.question.create(
            form=forms[1],
            expressions=[
                Expression.from_evaluatable_expression(
                    IsYes(subject_reference=ExpressionReference.from_question(q1)),
                    ExpressionType.CONDITION,
                    authenticated_grant_admin_client.user,
                )
            ],
        )

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.move_section",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=forms[1].id,
                direction="up",
            )
        )
        assert response.status_code == 302

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.move_section",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=forms[0].id,
                direction="down",
            )
        )
        assert response.status_code == 302

        flashes = get_test_flashes(authenticated_grant_admin_client, FlashMessageType.SECTION_DEPENDENCY_ORDER_ERROR)
        assert len(flashes) == 2
        assert flashes[0]["message"] == "You cannot move sections above ones they depend on"
        assert flashes[1]["message"] == "You cannot move sections below ones that depend on them"


class TestChangeQuestionGroupName:
    def test_404(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for("deliver_grant_funding.change_group_name", grant_id=uuid.uuid4(), group_id=uuid.uuid4())
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get(self, request: FixtureRequest, client_fixture: str, can_access: bool, factories):
        client = request.getfixturevalue(client_fixture)
        collection = factories.collection.create(grant=client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")
        group = factories.group.create(form=form, name="Test group")
        response = client.get(
            url_for("deliver_grant_funding.change_group_name", grant_id=client.grant.id, group_id=group.id)
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert "Test group" in soup.text

    def test_post(self, authenticated_grant_admin_client, factories, db_session):
        db_form = factories.form.create(
            collection__grant=authenticated_grant_admin_client.grant, title="Organisation information"
        )
        db_group = factories.group.create(form=db_form, name="Test group")

        form = GroupForm(data={"name": "Updated test group"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.change_group_name",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=db_group.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/group/[a-z0-9-]{36}/questions$")

        updated_group = db_session.get(Group, db_group.id)
        assert updated_group.name == "Updated test group"

    def test_post_duplicate(self, authenticated_grant_admin_client, factories):
        db_form = factories.form.create(
            collection__grant=authenticated_grant_admin_client.grant, title="Organisation information"
        )
        factories.group.create(form=db_form, name="Duplicate test group")
        db_group = factories.group.create(form=db_form, name="Test group")

        form = GroupForm(data={"name": "Duplicate test group"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.change_group_name",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=db_group.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "A question group with this name already exists")


class TestChangeGroupDisplayOptions:
    def test_404(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for("deliver_grant_funding.change_group_display_options", grant_id=uuid.uuid4(), group_id=uuid.uuid4())
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get(self, request: FixtureRequest, client_fixture: str, can_access: bool, factories):
        client = request.getfixturevalue(client_fixture)
        collection = factories.collection.create(grant=client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")
        group = factories.group.create(
            form=form,
            name="Test group",
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True),
        )
        response = client.get(
            url_for("deliver_grant_funding.change_group_display_options", grant_id=client.grant.id, group_id=group.id)
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            # the correct option is selected based on whats in the database
            assert (
                soup.find(
                    "input",
                    {
                        "type": "radio",
                        "name": "show_questions_on_the_same_page",
                        "value": "all-questions-on-same-page",
                        "checked": True,
                    },
                )
                is not None
            )

    def test_post(self, authenticated_grant_admin_client, factories, db_session):
        db_form = factories.form.create(
            collection__grant=authenticated_grant_admin_client.grant, title="Organisation information"
        )
        db_group = factories.group.create(
            form=db_form,
            name="Test group",
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=False),
        )

        assert db_group.presentation_options.show_questions_on_the_same_page is False

        form = GroupDisplayOptionsForm(data={"show_questions_on_the_same_page": "all-questions-on-same-page"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.change_group_display_options",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=db_group.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/group/[a-z0-9-]{36}/questions$")

        updated_group = db_session.get(Group, db_group.id)
        assert updated_group.presentation_options.show_questions_on_the_same_page is True

    def test_post_change_same_page_with_question_inter_dependencies(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        db_user = factories.user.create()
        db_form = factories.form.create(
            collection__grant=authenticated_grant_admin_client.grant, title="Organisation information"
        )
        db_group = factories.group.create(
            form=db_form,
            name="Test group",
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=False),
        )
        db_question1 = factories.question.create(form=db_form, parent=db_group)
        _ = factories.question.create(
            form=db_form,
            parent=db_group,
            expressions=[
                Expression.from_evaluatable_expression(
                    GreaterThan(subject_reference=ExpressionReference.from_question(db_question1), minimum_value=1000),
                    ExpressionType.CONDITION,
                    db_user,
                )
            ],
        )

        form = GroupDisplayOptionsForm(data={"show_questions_on_the_same_page": "all-questions-on-same-page"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.change_group_display_options",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=db_group.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(
            soup, "A question group cannot display on the same page if questions depend on answers within the group"
        )

    def test_post_change_same_page_allowed_with_only_self_referencing_validations(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        db_form = factories.form.create(
            collection__grant=authenticated_grant_admin_client.grant, title="Organisation information"
        )
        db_group = factories.group.create(
            form=db_form,
            name="Test group",
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=False),
        )
        q1 = factories.question.create(form=db_form, parent=db_group, data_type=QuestionDataType.NUMBER)
        q2 = factories.question.create(form=db_form, parent=db_group, data_type=QuestionDataType.NUMBER)
        user = factories.user.create()
        add_component_validation(
            q1,
            user,
            GreaterThan(subject_reference=ExpressionReference.from_question(q1), minimum_value=0, inclusive=True),
        )
        add_component_validation(
            q2,
            user,
            GreaterThan(subject_reference=ExpressionReference.from_question(q2), minimum_value=0, inclusive=True),
        )
        db_session.commit()

        form = GroupDisplayOptionsForm(data={"show_questions_on_the_same_page": "all-questions-on-same-page"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.change_group_display_options",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=db_group.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        updated_group = db_session.get(Group, db_group.id)
        assert updated_group.presentation_options.show_questions_on_the_same_page is True

    def test_post_change_same_page_with_internal_question_references(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        db_group = factories.group.create(
            name="Test group",
            form__collection__grant=authenticated_grant_admin_client.grant,
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=False),
        )
        db_question1 = factories.question.create(form=db_group.form, parent=db_group)
        factories.question.create(
            form=db_group.form,
            parent=db_group,
            text=f"Reference to (({db_question1.safe_qid}))",
        )

        form = GroupDisplayOptionsForm(data={"show_questions_on_the_same_page": "all-questions-on-same-page"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.change_group_display_options",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=db_group.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(
            soup, "A question group cannot display on the same page if questions depend on answers within the group"
        )


class TestChangeGroupAddAnotherOptions:
    def test_404(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.change_group_add_another_options", grant_id=uuid.uuid4(), group_id=uuid.uuid4()
            )
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get(self, request: FixtureRequest, client_fixture: str, can_access: bool, factories):
        client = request.getfixturevalue(client_fixture)
        collection = factories.collection.create(grant=client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")
        group = factories.group.create(form=form, name="Test group", add_another=False)
        response = client.get(
            url_for(
                "deliver_grant_funding.change_group_add_another_options", grant_id=client.grant.id, group_id=group.id
            )
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            # the correct option is selected based on whats in the database
            assert (
                soup.find(
                    "input",
                    {
                        "type": "radio",
                        "name": "question_group_is_add_another",
                        "value": "no",
                        "checked": True,
                    },
                )
                is not None
            )

    def test_post(self, authenticated_grant_admin_client, factories, db_session):
        db_form = factories.form.create(
            collection__grant=authenticated_grant_admin_client.grant, title="Organisation information"
        )
        db_group = factories.group.create(form=db_form, name="Test group", add_another=False)

        assert db_group.add_another is False

        form = GroupAddAnotherOptionsForm(data={"question_group_is_add_another": "yes"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.change_group_add_another_options",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=db_group.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/group/[a-z0-9-]{36}/questions$")

        updated_group = db_session.get(Group, db_group.id)
        assert updated_group.add_another is True

    def test_post_is_blocked_if_group_contains_add_another(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        db_form = factories.form.create(
            collection__grant=authenticated_grant_admin_client.grant, title="Organisation information"
        )
        db_group = factories.group.create(form=db_form, name="Test group", add_another=False)
        factories.question.create(form=db_form, parent=db_group, add_another=True)

        assert db_group.add_another is False

        form = GroupAddAnotherOptionsForm(data={"question_group_is_add_another": "yes"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.change_group_add_another_options",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=db_group.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(
            soup,
            "A question group cannot be answered more than once if it already contains questions that can "
            "be answered more than once",
        )

        updated_group = db_session.get(Group, db_group.id)
        assert updated_group.add_another is False

    def test_post_is_blocked_if_group_is_inside_add_another(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        db_form = factories.form.create(
            collection__grant=authenticated_grant_admin_client.grant, title="Organisation information"
        )
        db_group = factories.group.create(form=db_form, name="Test group", add_another=True)
        factories.question.create(form=db_form, parent=db_group, add_another=True)
        db_group_2 = factories.group.create(form=db_form, name="Test group 2", add_another=False, parent=db_group)

        assert db_group_2.add_another is False

        form = GroupAddAnotherOptionsForm(data={"question_group_is_add_another": "yes"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.change_group_add_another_options",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=db_group_2.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(
            soup,
            "A question group cannot be answered more than once if it is already inside a group that can be "
            "answered more than once",
        )

        updated_group = db_session.get(Group, db_group_2.id)
        assert updated_group.add_another is False

    def test_post_is_blocked_if_group_contains_depended_on_questions(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        db_form = factories.form.create(
            collection__grant=authenticated_grant_admin_client.grant, title="Organisation information"
        )
        db_group = factories.group.create(form=db_form, name="Test group", add_another=False)
        group_question = factories.question.create(form=db_form, parent=db_group)
        db_question = factories.question.create(form=db_form)

        add_component_validation(
            component=db_question,
            user=factories.user.create(),
            evaluatable_expression=GreaterThan(
                subject_reference=ExpressionReference.from_question(group_question), minimum_value=100
            ),
        )

        assert db_group.add_another is False

        form = GroupAddAnotherOptionsForm(data={"question_group_is_add_another": "yes"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.change_group_add_another_options",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=db_group.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(
            soup,
            "A question group cannot be answered more than once if questions elsewhere in the form depend "
            "on questions in this group",
        )

        updated_group = db_session.get(Group, db_group.id)
        assert updated_group.add_another is False


class TestChangeGroupAddAnotherSummaryQuestions:
    def test_get(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")
        group = factories.group.create(form=form, name="Test group", add_another=True)
        q1 = factories.question.create(form=form, parent=group)
        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.change_group_add_another_summary",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert (
            soup.find(
                "input",
                {
                    "type": "checkbox",
                    "name": "questions_to_show_in_add_another_summary",
                    "value": str(q1.id),
                    "checked": True,
                },
            )
            is not None
        )

    def test_post(self, authenticated_grant_admin_client, factories, db_session):
        form = factories.form.create(
            collection__grant=authenticated_grant_admin_client.grant, title="Organisation information"
        )
        group = factories.group.create(form=form, name="Test group", add_another=True)
        q1 = factories.question.create(form=form, parent=group)

        summary_form = GroupAddAnotherSummaryForm(
            group=group, data={"questions_to_show_in_add_another_summary": [str(q1.id)]}
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.change_group_add_another_summary",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
            ),
            data=get_form_data(summary_form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/group/[a-z0-9-]{36}/questions$")

        updated_group = db_session.get(Group, group.id)
        assert updated_group.presentation_options.add_another_summary_line_question_ids == [q1.id]


class TestChangeConditionsOperator:
    def test_404(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.change_conditions_operator", grant_id=uuid.uuid4(), component_id=uuid.uuid4()
            )
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get_for_question(self, request: FixtureRequest, client_fixture: str, can_access: bool, factories):
        client = request.getfixturevalue(client_fixture)
        collection = factories.collection.create(grant=client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")
        question = factories.question.create(
            form=form, name="Test question", conditions_operator=ConditionsOperator.ANY
        )

        response = client.get(
            url_for(
                "deliver_grant_funding.change_conditions_operator",
                grant_id=client.grant.id,
                component_id=question.id,
            )
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            # the correct option is selected based on whats in the database
            assert (
                soup.find(
                    "input",
                    {
                        "type": "radio",
                        "name": "conditions_operator",
                        "value": "ANY",
                        "checked": True,
                    },
                )
                is not None
            )

    def test_get_for_group(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")
        group = factories.group.create(form=form, name="Test group", conditions_operator=ConditionsOperator.ALL)

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.change_conditions_operator",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=group.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert (
            soup.find(
                "input",
                {
                    "type": "radio",
                    "name": "conditions_operator",
                    "value": "ALL",
                    "checked": True,
                },
            )
            is not None
        )

    def test_post_for_question(self, authenticated_grant_admin_client, factories, db_session):
        db_form = factories.form.create(
            collection__grant=authenticated_grant_admin_client.grant, title="Organisation information"
        )
        db_question = factories.question.create(
            form=db_form, name="Test question", conditions_operator=ConditionsOperator.ALL
        )

        assert db_question.conditions_operator == ConditionsOperator.ALL

        form = ConditionsOperatorForm(data={"conditions_operator": "ANY"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.change_conditions_operator",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=db_question.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/question/[a-z0-9-]{36}$")

        updated_question = db_session.get(Question, db_question.id)
        assert updated_question.conditions_operator == ConditionsOperator.ANY

    def test_post_for_group(self, authenticated_grant_admin_client, factories, db_session):
        from app.common.data.models import Group

        db_form = factories.form.create(
            collection__grant=authenticated_grant_admin_client.grant, title="Organisation information"
        )
        db_group = factories.group.create(form=db_form, name="Test group", conditions_operator=ConditionsOperator.ANY)

        assert db_group.conditions_operator == ConditionsOperator.ANY

        form = ConditionsOperatorForm(data={"conditions_operator": "ALL"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.change_conditions_operator",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=db_group.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/group/[a-z0-9-]{36}/questions$")

        updated_group = db_session.get(Group, db_group.id)
        assert updated_group.conditions_operator == ConditionsOperator.ALL

    def test_get_multiple_conditions(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")
        user = factories.user.create()
        question0 = factories.question.create(form=form, name="Test question 0", data_type=QuestionDataType.NUMBER)
        question1 = factories.question.create(
            form=form,
            name="Test question",
            conditions_operator=ConditionsOperator.ANY,
            expressions=[
                Expression.from_evaluatable_expression(
                    GreaterThan(minimum_value=1000, subject_reference=ExpressionReference.from_question(question0)),
                    ExpressionType.CONDITION,
                    user,
                ),
                Expression.from_evaluatable_expression(
                    CustomExpression(custom_expression="1<2", custom_message="test"),
                    ExpressionType.CONDITION,
                    user,
                ),
            ],
        )

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.change_conditions_operator",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=question1.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        # the correct option is selected based on whats in the database
        assert (
            soup.find(
                "input",
                {
                    "type": "radio",
                    "name": "conditions_operator",
                    "value": "ANY",
                    "checked": True,
                },
            )
            is not None
        )

    def test_post_multiple_conditions(self, authenticated_grant_admin_client, factories, db_session):
        db_form = factories.form.create(
            collection__grant=authenticated_grant_admin_client.grant, title="Organisation information"
        )
        user = factories.user.create()
        question0 = factories.question.create(form=db_form, name="Test question 0", data_type=QuestionDataType.NUMBER)
        question1 = factories.question.create(
            form=db_form,
            name="Test question",
            conditions_operator=ConditionsOperator.ANY,
            expressions=[
                Expression.from_evaluatable_expression(
                    GreaterThan(minimum_value=1000, subject_reference=ExpressionReference.from_question(question0)),
                    ExpressionType.CONDITION,
                    user,
                ),
                Expression.from_evaluatable_expression(
                    CustomExpression(custom_expression="1<2", custom_message="test"),
                    ExpressionType.CONDITION,
                    user,
                ),
            ],
        )

        assert question1.conditions_operator == ConditionsOperator.ANY

        form = ConditionsOperatorForm(data={"conditions_operator": "ALL"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.change_conditions_operator",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=question1.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/question/[a-z0-9-]{36}$")

        updated_question = db_session.get(Question, question1.id)
        assert updated_question.conditions_operator == ConditionsOperator.ALL


class TestChangeFormName:
    def test_404(self, authenticated_grant_member_client):
        response = authenticated_grant_member_client.get(
            url_for("deliver_grant_funding.change_form_name", grant_id=uuid.uuid4(), form_id=uuid.uuid4())
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get(self, request: FixtureRequest, client_fixture: str, can_access: bool, factories):
        client = request.getfixturevalue(client_fixture)
        collection = factories.collection.create(grant=client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")

        response = client.get(
            url_for("deliver_grant_funding.change_form_name", grant_id=client.grant.id, form_id=form.id)
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert "Organisation information" in soup.text

    def test_get_blocked_if_live_submissions(self, authenticated_grant_admin_client, factories, caplog):
        form = factories.form.create(
            collection__grant=authenticated_grant_admin_client.grant, title="Organisation information"
        )
        factories.submission.create(mode=SubmissionModeEnum.LIVE, collection=form.collection)

        with caplog.at_level(logging.INFO):
            response = authenticated_grant_admin_client.get(
                url_for(
                    "deliver_grant_funding.change_form_name",
                    grant_id=authenticated_grant_admin_client.grant.id,
                    form_id=form.id,
                )
            )

        assert response.status_code == 403
        assert any(
            message
            == AnyStringMatching(
                r"^Blocking access to manage form [a-z0-9-]{36} because related collection has live submissions"
            )
            for message in caplog.messages
        )

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_post_update_name(
        self, request: FixtureRequest, client_fixture: str, can_access: bool, factories, db_session
    ):
        client = request.getfixturevalue(client_fixture)
        db_form = factories.form.create(collection__grant=client.grant, title="Organisation information")

        form = AddSectionForm(data={"title": "Updated Name"})
        response = client.post(
            url_for("deliver_grant_funding.change_form_name", grant_id=client.grant.id, form_id=db_form.id),
            data=get_form_data(form),
            follow_redirects=False,
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 302
            assert response.location == AnyStringMatching(
                "^/deliver/grant/[a-z0-9-]{36}/section/[a-z0-9-]{36}/questions$"
            )

            updated_form = db_session.get(Form, db_form.id)
            assert updated_form.title == "Updated Name"

    def test_post_update_name_duplicate(self, authenticated_grant_admin_client, factories):
        db_form = factories.form.create(
            collection__grant=authenticated_grant_admin_client.grant, title="Organisation information"
        )
        db_form2 = factories.form.create(collection=db_form.collection, title="Project information")

        form = AddSectionForm(data={"title": "Organisation information"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.change_form_name",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=db_form2.id,
            ),
            data=get_form_data(form),
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "A section with this name already exists")


class TestListGroupQuestions:
    def test_404(self, authenticated_grant_member_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant)
        form = factories.form.create(collection=collection)
        question = factories.question.create(form=form)
        response = authenticated_grant_member_client.get(
            url_for("deliver_grant_funding.list_group_questions", grant_id=uuid.uuid4(), group_id=uuid.uuid4())
        )
        assert response.status_code == 404

        # we don't load the group management page for any type of component
        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.list_group_questions",
                grant_id=question.form.collection.grant.id,
                group_id=question.id,
            )
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_edit",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_admin_actions(self, request, client_fixture, can_edit, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        collection = factories.collection.create(grant=client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")
        group = factories.group.create(form=form, name="Test group", order=0)
        factories.question.create(form=form, parent=group, order=0)

        response = client.get(
            url_for("deliver_grant_funding.list_group_questions", grant_id=client.grant.id, group_id=group.id)
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Test group"

        # todo: extend with "change name" and "question group settings"
        delete_group_link = page_has_link(soup, "Delete question group")
        add_question_group = page_has_link(soup, "Add a question group")

        assert (delete_group_link is not None) is can_edit
        assert (add_question_group is not None) is can_edit

        if can_edit:
            assert delete_group_link.get("href") == AnyStringMatching(r"\?delete")

    def test_get_shows_interpolated_questions(self, authenticated_grant_admin_client, factories, db_session):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")
        q1 = factories.question.create(form=form, name="my question name")
        group = factories.group.create(form=form, name="Test group", order=1)
        factories.question.create(form=form, parent=group, text=f"Reference to (({q1.safe_qid}))")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.list_group_questions",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Reference to ((Test Report → Organisation information → my question name))" in soup.text

    def test_delete_confirmation_banner(self, authenticated_grant_admin_client, factories, db_session):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")
        group = factories.group.create(form=form, name="Test group", order=0)

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.list_group_questions",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
                delete="",
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_button(soup, "Yes, delete this question group")

    def test_cannot_delete_with_depended_on_questions_in_group(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        user = factories.user.create()
        form = factories.form.create(collection=collection, title="Organisation information")
        group = factories.group.create(form=form, name="Test group", order=0)
        question = factories.question.create(form=form, parent=group, order=0, data_type=QuestionDataType.NUMBER)
        factories.question.create(
            form=form,
            order=1,
            expressions=[
                Expression.from_evaluatable_expression(
                    GreaterThan(subject_reference=ExpressionReference.from_question(question), minimum_value=1000),
                    ExpressionType.CONDITION,
                    user,
                )
            ],
        )

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.list_group_questions",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
                delete="",
            )
        )

        assert response.status_code == 302

        response = authenticated_grant_admin_client.get(response.location)
        soup = BeautifulSoup(response.data, "html.parser")
        assert "You cannot delete an answer that other questions depend on" in soup.text

    def test_can_delete_group_with_only_internal_group_validation(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        group = factories.group.create(
            form=db_form,
            name="Test group",
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True),
        )
        q1 = factories.question.create(form=db_form, parent=group, data_type=QuestionDataType.NUMBER)
        q2 = factories.question.create(form=db_form, parent=group, data_type=QuestionDataType.NUMBER)
        add_component_validation(
            group,
            factories.user.create(),
            CustomExpression(
                custom_expression=EvaluationStatement(f"(({q1.safe_qid})) + (({q2.safe_qid})) > 100"),
                custom_message=InterpolationStatement("Total must exceed 100"),
            ),
        )
        db_session.commit()
        group_id = group.id

        confirm_form = GenericConfirmDeletionForm(data={"confirm_deletion": True})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.list_group_questions",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group_id,
                delete="",
            ),
            data=get_form_data(confirm_form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert db_session.get(Group, group_id) is None

    def test_can_delete_outer_group_when_only_nested_group_has_internal_validation(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        outer_group = factories.group.create(form=db_form, name="Outer group")
        inner_group = factories.group.create(
            form=db_form,
            parent=outer_group,
            name="Inner group",
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True),
        )
        q1 = factories.question.create(form=db_form, parent=inner_group, data_type=QuestionDataType.NUMBER)
        q2 = factories.question.create(form=db_form, parent=inner_group, data_type=QuestionDataType.NUMBER)
        add_component_validation(
            inner_group,
            factories.user.create(),
            CustomExpression(
                custom_expression=EvaluationStatement(f"(({q1.safe_qid})) + (({q2.safe_qid})) > 100"),
                custom_message=InterpolationStatement("Total must exceed 100"),
            ),
        )
        db_session.commit()
        outer_group_id = outer_group.id

        confirm_form = GenericConfirmDeletionForm(data={"confirm_deletion": True})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.list_group_questions",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=outer_group_id,
                delete="",
            ),
            data=get_form_data(confirm_form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert db_session.get(Group, outer_group_id) is None


class TestListSectionQuestions:
    def test_404(self, authenticated_grant_member_client):
        response = authenticated_grant_member_client.get(
            url_for("deliver_grant_funding.list_section_questions", grant_id=uuid.uuid4(), form_id=uuid.uuid4())
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_edit",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_admin_actions(self, request, client_fixture, can_edit, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        collection = factories.collection.create(grant=client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")
        factories.question.create_batch(2, form=form)

        response = client.get(
            url_for("deliver_grant_funding.list_section_questions", grant_id=client.grant.id, form_id=form.id)
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Organisation information"

        change_section_name_link = page_has_link(soup, "Change section name")
        delete_section_link = page_has_link(soup, "Delete section")

        assert (change_section_name_link is not None) is can_edit
        assert (delete_section_link is not None) is can_edit

        if can_edit:
            assert change_section_name_link.get("href") == AnyStringMatching(
                "/deliver/grant/[a-z0-9-]{36}/section/[a-z0-9-]{36}/change-name"
            )
            assert delete_section_link.get("href") == AnyStringMatching(r"\?delete")

    def test_delete_confirmation_banner(self, authenticated_grant_admin_client, factories, db_session):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.list_section_questions",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
                delete="",
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_button(soup, "Yes, delete this section")

    def test_get_shows_interpolated_questions(self, authenticated_grant_admin_client, factories, db_session):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")
        q1 = factories.question.create(form=form, name="my question name")
        factories.question.create(form=form, text=f"Reference to (({q1.safe_qid}))")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.list_section_questions",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            )
        )

        assert response.status_code == 200
        assert "Reference to ((Test Report → Organisation information → my question name))" in response.text

    def test_cannot_delete_with_live_submissions(self, authenticated_grant_admin_client, factories, db_session, caplog):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")
        factories.submission.create(collection=collection, mode=SubmissionModeEnum.LIVE)

        with caplog.at_level(logging.INFO):
            response = authenticated_grant_admin_client.post(
                url_for(
                    "deliver_grant_funding.list_section_questions",
                    grant_id=authenticated_grant_admin_client.grant.id,
                    form_id=form.id,
                    delete="",
                )
            )

        assert response.status_code == 403
        assert any(
            message
            == AnyStringMatching(
                r"^Blocking access to delete form [a-z0-9-]{36} because related collection has live submissions"
            )
            for message in caplog.messages
        )

    def test_cannot_delete_section_with_questions_depended_on_by_other_section(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        section_to_delete = factories.form.create(collection=report, title="Section being deleted")
        dependent_section = factories.form.create(collection=report, title="Dependent section")

        depended_on_question = factories.question.create(form=section_to_delete, data_type=QuestionDataType.YES_NO)
        dependent_question = factories.question.create(
            form=dependent_section,
            text="Do you want a biscuit?",
            expressions=[
                Expression.from_evaluatable_expression(
                    IsYes(subject_reference=ExpressionReference.from_question(depended_on_question)),
                    ExpressionType.CONDITION,
                    authenticated_grant_admin_client.user,
                )
            ],
        )

        confirm_form = GenericConfirmDeletionForm(data={"confirm_deletion": True})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.list_section_questions",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=section_to_delete.id,
                delete="",
            ),
            data=get_form_data(confirm_form),
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert db_session.get(Form, section_to_delete.id) is not None

        soup = BeautifulSoup(response.data, "html.parser")
        banner = soup.select_one(".govuk-notification-banner.app-notification-banner--destructive")
        assert banner is not None
        banner_text = " ".join(banner.text.split())
        assert (
            "You cannot delete Section being deleted because it is being referenced in another section's questions"
            in banner_text
        )
        assert "Condition for Do you want a biscuit? in Dependent section" in banner_text
        assert "Delete the other section references to delete this section." in banner_text

        banner_links = banner.select("a.govuk-notification-banner__link")
        assert [link.text for link in banner_links] == ["Do you want a biscuit?", "Dependent section"]
        assert banner_links[0].get("href") == url_for(
            "deliver_grant_funding.edit_question",
            grant_id=authenticated_grant_admin_client.grant.id,
            question_id=dependent_question.id,
        )
        assert banner_links[1].get("href") == url_for(
            "deliver_grant_funding.list_section_questions",
            grant_id=authenticated_grant_admin_client.grant.id,
            form_id=dependent_section.id,
        )

    @pytest.mark.parametrize(
        "client_fixture, can_preview",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_member_client", True),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_post_list_section_questions_preview(
        self, request: FixtureRequest, client_fixture: str, can_preview: bool, factories, db_session
    ):
        client = request.getfixturevalue(client_fixture)
        generic_grant = factories.grant.create()
        grant = getattr(client, "grant", None) or generic_grant
        collection = factories.collection.create(grant=grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")
        factories.question.create(form=form)

        preview_form = GenericSubmitForm()
        response = client.post(
            url_for("deliver_grant_funding.list_section_questions", grant_id=grant.id, form_id=form.id),
            data=preview_form.data,
            follow_redirects=False,
        )

        if not can_preview:
            assert response.status_code == 403
        else:
            assert response.status_code == 302
            assert response.location == AnyStringMatching(
                "/deliver/grant/[a-z0-9-]{36}/submissions/[a-z0-9-]{36}/[a-z0-9-]{36}"
            )

    @pytest.mark.parametrize(
        "collection_status", [status for status in CollectionStatusEnum if status != CollectionStatusEnum.DRAFT]
    )
    @pytest.mark.parametrize(
        "client_fixture", ("authenticated_grant_admin_client", "authenticated_platform_admin_client")
    )
    def test_get_no_admin_actions_when_report_not_draft(self, factories, collection_status, client_fixture, request):
        client = request.getfixturevalue(client_fixture)
        grant = client.grant if client.grant else factories.grant.create()
        collection = factories.collection.create(grant=grant, name="Test Report", status=collection_status)
        form = factories.form.create(collection=collection, title="Organisation information")
        factories.question.create_batch(2, form=form)

        response = client.get(
            url_for(
                "deliver_grant_funding.list_section_questions",
                grant_id=grant.id,
                form_id=form.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")

        change_section_name_link = page_has_link(soup, "Change section name")
        delete_section_link = page_has_link(soup, "Delete section")
        add_question_button = page_has_button(soup, "Add a question")
        add_another_question_button = page_has_button(soup, "Add another question")

        assert change_section_name_link is None
        assert delete_section_link is None
        assert add_question_button is None
        assert add_another_question_button is None

    def test_post_list_section_questions_returns_to_task_list(
        self, factories, db_session, authenticated_grant_admin_client
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")
        factories.question.create(form=form)

        preview_form = GenericSubmitForm()
        runner_response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.list_section_questions",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            ),
            data=preview_form.data,
            follow_redirects=True,
        )
        soup = BeautifulSoup(runner_response.data, "html.parser")
        assert page_has_link(soup, "Back").get("href") == url_for(
            "deliver_grant_funding.list_section_questions",
            grant_id=authenticated_grant_admin_client.grant.id,
            form_id=form.id,
        )

    def test_get_hides_preview_button_when_no_questions(self, factories, db_session, authenticated_grant_admin_client):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.list_section_questions",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert not page_has_button(soup, "Preview section")

    def test_get_shows_preview_button_when_questions(self, factories, db_session, authenticated_grant_admin_client):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")
        factories.question.create(form=form)

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.list_section_questions",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_button(soup, "Preview section")

    def test_get_hides_preview_button_when_data_sources(self, factories, db_session, authenticated_grant_admin_client):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant, name="Test Report")
        form = factories.form.create(collection=collection)
        factories.question.create(form=form)
        factories.data_source.create(
            grant=grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
        )

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.list_section_questions",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert not page_has_button(soup, "Preview section")
        assert "You cannot preview sections in this report because it requires uploaded data" in soup.text

    def test_get_hides_preview_button_when_collection_closed(
        self, factories, db_session, authenticated_grant_admin_client
    ):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant, name="Test Report", status=CollectionStatusEnum.CLOSED)
        form = factories.form.create(collection=collection)
        factories.question.create(form=form)

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.list_section_questions",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert not page_has_button(soup, "Preview section")
        # This message should only show if preview is disabled due to data source references - if a collection is closed
        # or the section has no questions then it doesn't make sense to show it
        assert "You cannot preview sections in this report because it requires uploaded data" not in soup.text


class TestMoveQuestion:
    def test_404(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.move_component",
                grant_id=uuid.uuid4(),
                component_id=uuid.uuid4(),
                direction="up",
            )
        )
        assert response.status_code == 404

    def test_no_access_for_grant_members(self, authenticated_grant_member_client, factories, db_session):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")
        questions = factories.question.create_batch(3, form=form)

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.move_component",
                grant_id=authenticated_grant_member_client.grant.id,
                component_id=questions[0].id,
                direction="blah",
            )
        )
        assert response.status_code == 403

    def test_400(self, authenticated_grant_admin_client, factories, db_session):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")
        questions = factories.question.create_batch(3, form=form)

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.move_component",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=questions[0].id,
                direction="blah",
            )
        )
        assert response.status_code == 400

    @pytest.mark.parametrize(
        "direction",
        ["up", "down"],
    )
    def test_move(self, authenticated_grant_admin_client, factories, db_session, direction):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")
        factories.question.reset_sequence()
        questions = factories.question.create_batch(3, form=form)
        assert form.cached_questions[1].text == "Question 1"

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.move_component",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=questions[1].id,
                direction=direction,
            )
        )
        form.clear_caches()
        assert response.status_code == 302

        if direction == "up":
            assert form.cached_questions[0].text == "Question 1"
        else:
            assert form.cached_questions[2].text == "Question 1"

    # todo: think about if interfaces that update questions should also clear their forms
    #       cachce if it exists (for now we're just going to leave it and assume instances are
    #       loaded once per request)
    def test_move_group(self, authenticated_grant_admin_client, factories, db_session):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")
        group = factories.group.create(form=form, name="Test group", order=0)
        question1 = factories.question.create(parent=group, text="Question 1", order=0)
        factories.question.create(parent=group, text="Question 2", order=1)
        factories.question.create(form=form, text="Question 3", order=1)
        assert form.cached_questions[0].text == "Question 1"

        # we can move the whole group on the form page
        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.move_component",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=group.id,
                direction="down",
            )
        )
        form.clear_caches()

        assert response.status_code == 302
        assert response.location == AnyStringMatching(r"/deliver/grant/[a-z0-9-]{36}/section/[a-z0-9-]{36}/questions")
        assert form.cached_questions[0].text == "Question 3"

        # we can move questions inside the group
        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.move_component",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=question1.id,
                source=group.id,
                direction="down",
            )
        )
        form.clear_caches()
        assert response.status_code == 302
        assert response.location == AnyStringMatching(r"/deliver/grant/[a-z0-9-]{36}/group/[a-z0-9-]{36}/questions")

        assert form.cached_questions[1].text == "Question 2"


class TestChooseQuestionType:
    def test_404(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for("deliver_grant_funding.choose_question_type", grant_id=uuid.uuid4(), form_id=uuid.uuid4())
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access, expected_question_types",
        (
            ["authenticated_grant_member_client", False, 10],
            ["authenticated_grant_admin_client", True, 10],
            ["authenticated_platform_admin_client", True, 10],
        ),
    )
    def test_get(self, request, client_fixture, can_access, expected_question_types, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        grant = getattr(client, "grant", None) or factories.grant.create()
        collection = factories.collection.create(grant=grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")

        response = client.get(url_for("deliver_grant_funding.choose_question_type", grant_id=grant.id, form_id=form.id))

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert get_h1_text(soup) == "What type of question do you need?"

            assert len(soup.select("input[type=radio]")) == expected_question_types, (
                "Should show an option for each kind of question"
            )

    def test_post(self, authenticated_grant_admin_client, factories, db_session):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")

        form = QuestionTypeForm(data={"question_data_type": QuestionDataType.TEXT_SINGLE_LINE.name})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.choose_question_type",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=db_form.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            r"/deliver/grant/[a-z0-9-]{36}/section/[a-z0-9-]{36}/questions/add\?question_data_type=TEXT_SINGLE_LINE"
        )


class TestAddQuestion:
    def test_404(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for("deliver_grant_funding.add_question", grant_id=uuid.uuid4(), form_id=uuid.uuid4())
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ["authenticated_grant_member_client", False],
            ["authenticated_grant_admin_client", True],
        ),
    )
    def test_get(self, request, client_fixture, can_access, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        collection = factories.collection.create(grant=client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")

        response = client.get(url_for("deliver_grant_funding.add_question", grant_id=client.grant.id, form_id=form.id))

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert get_h1_text(soup) == "Add question"

    def test_post(self, authenticated_grant_admin_client, factories, db_session):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question",
                grant_id=grant.id,
                form_id=db_form.id,
                question_type=QuestionDataType.TEXT_SINGLE_LINE.name,
            ),
            data={
                "text": "question",
                "hint": "hint text",
                "name": "question name",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/question/[a-z0-9-]{36}$")

        # Stretching the test case a little but validates the flash message
        response = authenticated_grant_admin_client.get(response.location)
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Edit question"
        assert get_h2_text(soup) == "Question created"

    def test_post_with_invalid_context_references(self, authenticated_grant_admin_client, factories, db_session):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question",
                grant_id=grant.id,
                form_id=db_form.id,
                question_type=QuestionDataType.TEXT_SINGLE_LINE.name,
            ),
            data={
                "text": "question ((invalid_reference))",
                "hint": "hint text",
                "name": "question name",
            },
            follow_redirects=False,
        )
        soup = BeautifulSoup(response.data, "html.parser")
        assert response.status_code == 200

        assert page_has_error(soup, "You cannot use ((invalid_reference)) because it does not exist")

    @pytest.mark.parametrize("context_field", ["text", "hint"])
    def test_post_to_add_context_redirects_and_sets_up_session(
        self, authenticated_grant_admin_client, factories, db_session, mocker, context_field
    ):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        form = QuestionForm(
            data={
                "text": "Updated question",
                "hint": "Updated hint",
                "name": "Updated name",
                "add_context": context_field,
            },
            question_type=QuestionDataType.TEXT_SINGLE_LINE,
        )
        spy_validate = mocker.spy(interfaces.collections, "_validate_and_sync_component_references")
        response = authenticated_grant_admin_client.post(
            url_for("deliver_grant_funding.add_question", grant_id=grant.id, form_id=db_form.id),
            data=get_form_data(form, submit=""),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            "^/deliver/grant/[a-z0-9-]{36}/section/[a-z0-9-]{36}/add-context/select-source$"
        )
        assert spy_validate.call_count == 0

        with authenticated_grant_admin_client.session_transaction() as sess:
            assert sess["question"]["field"] == "component"

    def test_post_from_add_context_success_cleans_that_bit_of_session(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")

        session_data = AddContextToComponentSessionModel(
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            component_form_data={
                "text": "Test question text",
                "name": "Test question name",
                "hint": "Test question hint",
                "add_context": "text",
            },
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = session_data.model_dump(mode="json")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question",
                grant_id=grant.id,
                form_id=db_form.id,
                question_type=QuestionDataType.TEXT_SINGLE_LINE.name,
            ),
            data={
                "text": "Test question text",
                "name": "Test question name",
                "hint": "Test question hint",
                "submit": "y",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/question/[a-z0-9-]{36}$")

        # Stretching the test case a little but validates the flash message
        response = authenticated_grant_admin_client.get(response.location)
        assert response.status_code == 200

        with authenticated_grant_admin_client.session_transaction() as sess:
            assert "question" not in sess

    def test_post_add_to_group(self, authenticated_grant_admin_client, factories, db_session):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        group = factories.group.create(form=db_form, name="Test group", order=0)

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question",
                grant_id=grant.id,
                form_id=db_form.id,
                question_type=QuestionDataType.TEXT_SINGLE_LINE.name,
                parent_id=group.id,
            ),
            data={
                "text": "question",
                "hint": "hint text",
                "name": "question name",
                "submit": "y",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/question/[a-z0-9-]{36}$")

        # Stretching the test case a little but validates the group specific flash message
        response = authenticated_grant_admin_client.get(response.location)
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Edit question"
        assert get_h2_text(soup) == "Question created"
        assert page_has_link(soup, "Return to the question group")

    def test_restore_from_session_when_returning_from_add_session_flow(
        self, authenticated_grant_admin_client, factories
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")
        group = factories.group.create(form=form, name="Test group", order=0)

        session_data = AddContextToComponentSessionModel(
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            component_form_data={
                "text": "Test question text",
                "name": "Test question name",
                "hint": "Test question hint",
                "add_context": "text",
            },
            parent_id=group.id,
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = session_data.model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.add_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
                question_type=QuestionDataType.TEXT_SINGLE_LINE.name,
                parent_id=group.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")

        # Verify that the session data is restored to the form
        text_input = soup.find("textarea", {"name": "text"})
        assert text_input.text.strip() == "Test question text"

        name_input = soup.find("input", {"name": "name"})
        assert name_input["value"] == "Test question name"

        hint_textarea = soup.find("textarea", {"name": "hint"})
        assert hint_textarea.text.strip() == "Test question hint"


class TestAddQuestionGroup:
    def test_404(self, authenticated_grant_admin_client, factories):
        response = authenticated_grant_admin_client.get(
            url_for("deliver_grant_funding.add_question", grant_id=uuid.uuid4(), form_id=uuid.uuid4())
        )
        assert response.status_code == 404

        # valid grant and form context but adding to a missing question group
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)
        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.add_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
                parent_id=uuid.uuid4(),
            )
        )
        assert response.status_code == 404

    def test_missing_name(self, authenticated_grant_admin_client, factories, db_session):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant)
        db_form = factories.form.create(collection=collection)

        form = GroupDisplayOptionsForm(
            data={
                "show_questions_on_the_same_page": "all-questions-on-same-page",
            },
        )
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question_group_display_options",
                grant_id=grant.id,
                form_id=db_form.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/section/[a-z0-9-]{36}/groups/add$")

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ["authenticated_grant_member_client", False],
            ["authenticated_grant_admin_client", True],
        ),
    )
    def test_get(self, request, client_fixture, can_access, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        collection = factories.collection.create(grant=client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")

        with client.session_transaction() as session:
            session["add_question_group"] = {"group_name": "Test group"}

        response = client.get(
            url_for(
                "deliver_grant_funding.add_question_group_display_options", grant_id=client.grant.id, form_id=form.id
            )
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert get_h1_text(soup) == "How should the question group be displayed?"

    def test_post_display_options(self, authenticated_grant_admin_client, factories, db_session):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")

        with authenticated_grant_admin_client.session_transaction() as session:
            session["add_question_group"] = {"group_name": "Test group"}

        form = GroupDisplayOptionsForm(
            data={
                "show_questions_on_the_same_page": "all-questions-on-same-page",
            },
        )
        response = authenticated_grant_admin_client.post(
            url_for("deliver_grant_funding.add_question_group_display_options", grant_id=grant.id, form_id=db_form.id),
            data=get_form_data(form),
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            r"^/deliver/grant/[a-z0-9-]{36}/section/[a-z0-9-]{36}/groups/add/add_another$"
        )

    def test_get_add_another_skipped_when_parent_add_another(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        group = factories.group.create(form=db_form, add_another=True)

        with authenticated_grant_admin_client.session_transaction() as session:
            session["add_question_group"] = {"group_name": "Test group", "show_questions_on_the_same_page": True}

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.add_question_group_add_another_option",
                grant_id=grant.id,
                form_id=db_form.id,
                parent_id=group.id,
            ),
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            r"^/deliver/grant/[a-z0-9-]{36}/group/[a-z0-9-]{36}/questions\?form_id=[a-z0-9-]{36}$"
        )

        group.add_another = False

        with authenticated_grant_admin_client.session_transaction() as session:
            session["add_question_group"] = {"group_name": "Test group", "show_questions_on_the_same_page": True}

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.add_question_group_add_another_option",
                grant_id=grant.id,
                form_id=db_form.id,
                parent_id=group.id,
            ),
            follow_redirects=False,
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert (
            get_h1_text(soup) == "Should people be able to answer all questions in this question group more than once?"
        )

    def test_post_add_another(self, authenticated_grant_admin_client, factories, db_session):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")

        with authenticated_grant_admin_client.session_transaction() as session:
            session["add_question_group"] = {"group_name": "Test group", "show_questions_on_the_same_page": True}

        form = GroupAddAnotherOptionsForm(
            data={
                "question_group_is_add_another": "yes",
            },
        )
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question_group_add_another_option", grant_id=grant.id, form_id=db_form.id
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            r"^/deliver/grant/[a-z0-9-]{36}/group/[a-z0-9-]{36}/questions\?form_id=[a-z0-9-]{36}$"
        )

    def test_post_duplicate(self, authenticated_grant_admin_client, factories, db_session):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        factories.group.create(form=db_form, name="Duplicate test group")

        form = GroupForm(
            data={
                "name": "Duplicate test group",
            },
        )
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question_group_name",
                grant_id=grant.id,
                form_id=db_form.id,
                name="Duplicate test group",
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "A question group with this name already exists")


class TestSelectContextSource:
    def test_get_fails_with_empty_session(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_context_source",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            )
        )
        assert response.status_code == 400

    def test_get_shows_available_context_source_choices(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToComponentSessionModel(
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                component_form_data={
                    "text": "Test question text",
                    "name": "Test question name",
                    "hint": "Test question hint",
                    "add_context": "text",
                },
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_context_source",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            )
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "Select a data source" in soup.text
        assert "This question" not in soup.text

    def test_get_shows_this_question_for_custom_validation_expression(
        self, authenticated_grant_admin_client, factories
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)
        question = factories.question.create(form=form, name="Test question", data_type=QuestionDataType.NUMBER)

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToExpressionsModel(
                field=ExpressionType.VALIDATION,
                component_id=question.id,
                managed_expression_name=None,
                is_custom=True,
                expression_form_data={
                    "add_context": "custom_expression",
                },
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_context_source",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            )
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "Select a data source" in soup.text
        assert "This question" in soup.text

    @pytest.mark.parametrize(
        "session_data",
        [
            (
                AddContextToExpressionsModel(
                    field=ExpressionType.VALIDATION,
                    managed_expression_name=None,
                    component_id=uuid.uuid4(),
                    is_custom=True,
                    expression_form_data={
                        "add_context": "custom_message",
                    },
                )
            ),
            (
                AddContextToExpressionsModel(
                    field=ExpressionType.VALIDATION,
                    managed_expression_name=ManagedExpressionsEnum.GREATER_THAN,
                    component_id=uuid.uuid4(),
                    is_custom=False,
                    expression_form_data={
                        "add_context": "custom_expression",
                    },
                )
            ),
            (
                AddContextToExpressionsModel(
                    field=ExpressionType.CONDITION,
                    managed_expression_name=None,
                    component_id=uuid.uuid4(),
                    is_custom=True,
                    expression_form_data={
                        "add_context": "custom_expression",
                    },
                )
            ),
            (
                AddConditionDependsOnSessionModel(
                    component_id=uuid.uuid4(),
                )
            ),
        ],
    )
    def test_get_does_not_show_this_question(self, authenticated_grant_admin_client, factories, session_data):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)
        question = factories.question.create(form=form, name="Test question", data_type=QuestionDataType.NUMBER)

        session_data.component_id = question.id
        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = session_data.model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_context_source",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            )
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "Select a data source" in soup.text
        assert "This question" not in soup.text

    def test_get_works_for_existing_group_available_context_source_choices(
        self, authenticated_grant_admin_client, factories
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)
        group = factories.group.create(form=form)

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToComponentSessionModel(
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                component_form_data={
                    "text": "Test text",
                    "name": "Test name",
                    "hint": "Test hint",
                    "add_context": "text",
                },
                component_id=group.id,
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_context_source",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            )
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "Select a data source" in soup.text

    def test_post_redirect_and_updates_session(self, authenticated_grant_admin_client, factories):
        assert len(ExpressionContext.ContextSources) == 4, "Check all redirects if adding new context source choices"

        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)
        factories.question.create(form=form)

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToComponentSessionModel(
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                component_form_data={
                    "text": "Test text",
                    "name": "Test name",
                    "hint": "Test hint",
                    "add_context": "text",
                },
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.select_context_source",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            ),
            data={"data_source": "SECTION"},
        )
        assert response.status_code == 302
        assert response.location.endswith(
            url_for(
                "deliver_grant_funding.select_context_source_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            )
        )


class TestSelectContextSourceCollection:
    def test_404(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToComponentSessionModel(
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                component_form_data={
                    "text": "Test text",
                    "name": "Test name",
                    "hint": "Test hint",
                    "add_context": "text",
                },
                data_source=ExpressionContext.ContextSources.SECTION,
                collection_id=None,
                form_id=None,
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_context_source_collection",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            )
        )
        assert response.status_code == 404


class TestSelectContextSourceSection:
    def test_get_lists_sections(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection, title="Section 1")
        form_2 = factories.form.create(collection=collection, title="Section 2")
        factories.question.create(form=form_2, text="Question 1")

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToComponentSessionModel(
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                component_form_data={
                    "text": "Test text",
                    "name": "Test name",
                    "hint": "Test hint",
                    "add_context": "text",
                },
                data_source=ExpressionContext.ContextSources.SECTION,
                collection_id=form.collection_id,
                form_id=None,
                component_id=None,
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_context_source_section",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            )
        )
        assert response.status_code == 200
        assert "Section 1" in response.text
        assert "Section 2" not in response.text

    def test_get_lists_sections_with_dependent_question(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection, title="Section 1")
        form_2 = factories.form.create(collection=collection, title="Section 2")
        form_3 = factories.form.create(collection=collection, title="Section 3")
        question = factories.question.create(form=form_2, text="Question 1")
        question_2 = factories.question.create(form=form_3, text="Question 2")

        subject_reference = ExpressionReference.from_question(question)

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToExpressionsModel(
                data_source=ExpressionContext.ContextSources.SECTION,
                collection_id=form.collection_id,
                form_id=None,
                component_id=question_2.id,
                subject_reference=subject_reference,
                field=ExpressionType.CONDITION,
                managed_expression_name=ManagedExpressionsEnum.ANY_OF,
                expression_form_data={},
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_context_source_section",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            )
        )
        assert response.status_code == 200
        assert "Section 1" in response.text
        assert "Section 2" in response.text
        assert "Section 3" not in response.text

    def test_post_stores_form_id_and_redirects(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form_1 = factories.form.create(collection=collection, title="Section 1")
        form_2 = factories.form.create(collection=collection, title="Section 2")
        factories.question.create(form=form_1)
        question_in_form_2 = factories.question.create(form=form_2)

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToComponentSessionModel(
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                component_form_data={
                    "text": "Test text",
                    "name": "Test name",
                    "hint": "Test hint",
                    "add_context": "text",
                },
                data_source=ExpressionContext.ContextSources.SECTION,
                collection_id=collection.id,
                form_id=None,
                component_id=question_in_form_2.id,
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.select_context_source_section",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form_2.id,
            ),
            data={"section": str(form_1.id)},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == url_for(
            "deliver_grant_funding.select_context_source_question",
            grant_id=authenticated_grant_admin_client.grant.id,
            form_id=form_2.id,
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            question_data = sess.get("question")
            assert question_data is not None
            assert question_data["form_id"] == str(form_1.id)


class TestSelectContextSourceQuestion:
    def test_get_fails_with_invalid_session(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_context_source_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            )
        )
        assert response.status_code == 400

    def test_get_lists_questions(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)
        question1 = factories.question.create(form=form, text="Question 1")
        question2 = factories.question.create(form=form, text="Question 2")

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToComponentSessionModel(
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                component_form_data={
                    "text": "Test text",
                    "name": "Test name",
                    "hint": "Test hint",
                    "add_context": "text",
                },
                data_source=ExpressionContext.ContextSources.SECTION,
                collection_id=form.collection_id,
                form_id=form.id,
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_context_source_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            )
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "Select which question's answer to use" in soup.text
        assert question1.text in soup.text
        assert question2.text in soup.text

    def test_get_lists_questions_from_target_section(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form_1 = factories.form.create(collection=collection)
        form_2 = factories.form.create(collection=collection)
        question_in_form_1 = factories.question.create(form=form_1, text="Question from section 1")
        question_in_form_2 = factories.question.create(form=form_2, text="Question from section 2")

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToComponentSessionModel(
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                component_form_data={
                    "text": "Test text",
                    "name": "Test name",
                    "hint": "Test hint",
                    "add_context": "text",
                },
                data_source=ExpressionContext.ContextSources.SECTION,
                collection_id=collection.id,
                form_id=form_1.id,
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_context_source_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form_2.id,
            )
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert question_in_form_1.text in soup.text
        assert question_in_form_2.text not in soup.text

    def test_get_lists_questions_from_depends_on_question_if_condition(
        self, authenticated_grant_admin_client, factories
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)
        reference_question = factories.question.create(form=form, data_type=QuestionDataType.NUMBER)
        depends_on_question = factories.question.create(form=form, data_type=QuestionDataType.NUMBER)
        skipped_question = factories.question.create(form=form, data_type=QuestionDataType.NUMBER)
        target_question = factories.question.create(form=form, data_type=QuestionDataType.TEXT_SINGLE_LINE)

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToExpressionsModel(
                field=ExpressionType.CONDITION,
                managed_expression_name=ManagedExpressionsEnum.GREATER_THAN,
                expression_form_data={
                    "type": "Greater than",
                    "greater_than_value": None,
                    "greater_than_inclusive": True,
                    "add_context": "greater_than_expression",
                },
                component_id=target_question.id,
                subject_reference=ExpressionReference.from_question(depends_on_question),
                data_source=ExpressionContext.ContextSources.SECTION,
                collection_id=form.collection_id,
                form_id=form.id,
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_context_source_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            )
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "Select which question's answer to use" in soup.text
        assert reference_question.text in soup.text
        assert depends_on_question.text not in soup.text and skipped_question.text not in soup.text

    def test_get_lists_questions_before_component_id_when_subject_reference_is_data_set_column(
        self, authenticated_grant_admin_client, factories
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)
        reference_question = factories.question.create(form=form, data_type=QuestionDataType.NUMBER)
        target_question = factories.question.create(form=form, data_type=QuestionDataType.TEXT_SINGLE_LINE)
        skipped_question = factories.question.create(form=form, data_type=QuestionDataType.NUMBER)
        data_set = factories.data_source.create(
            grant=authenticated_grant_admin_client.grant,
            collection=collection,
            name="Test data set",
            type=DataSourceType.GRANT_RECIPIENT,
        )
        data_set_reference = ExpressionReference.from_data_source_column(data_set, "c_allocation")

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToExpressionsModel(
                field=ExpressionType.CONDITION,
                managed_expression_name=ManagedExpressionsEnum.GREATER_THAN,
                expression_form_data={
                    "type": "Greater than",
                    "greater_than_value": None,
                    "greater_than_inclusive": True,
                    "add_context": "greater_than_expression",
                },
                component_id=target_question.id,
                subject_reference=data_set_reference,
                data_source=ExpressionContext.ContextSources.SECTION,
                collection_id=form.collection_id,
                form_id=form.id,
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_context_source_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            )
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert reference_question.text in soup.text
        assert skipped_question.text not in soup.text
        assert target_question.text not in soup.text

    def test_get_back_link_points_to_select_context_source_when_same_section(
        self, authenticated_grant_admin_client, factories
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)
        reference_question = factories.question.create(form=form, data_type=QuestionDataType.NUMBER)

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToComponentSessionModel(
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                component_form_data={
                    "text": "Test text",
                    "name": "Test name",
                    "hint": "Test hint",
                    "add_context": "text",
                },
                data_source=ExpressionContext.ContextSources.SECTION,
                collection_id=collection.id,
                form_id=form.id,
                component_id=reference_question.id,
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_context_source_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            )
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_link(soup, "Back").get("href") == url_for(
            "deliver_grant_funding.select_context_source",
            grant_id=authenticated_grant_admin_client.grant.id,
            form_id=form.id,
        )

    def test_get_back_link_points_to_select_context_section_when_different_section(
        self, authenticated_grant_admin_client, factories
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form_1 = factories.form.create(collection=collection)
        form_2 = factories.form.create(collection=collection)
        reference_question = factories.question.create(form=form_2, data_type=QuestionDataType.NUMBER)

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToComponentSessionModel(
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                component_form_data={
                    "text": "Test text",
                    "name": "Test name",
                    "hint": "Test hint",
                    "add_context": "text",
                },
                data_source=ExpressionContext.ContextSources.SECTION,
                collection_id=collection.id,
                form_id=form_1.id,
                component_id=reference_question.id,
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_context_source_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form_2.id,
            )
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_link(soup, "Back").get("href") == url_for(
            "deliver_grant_funding.select_context_source_section",
            grant_id=authenticated_grant_admin_client.grant.id,
            form_id=form_2.id,
        )

    def test_post_redirects_to_component_and_updates_session(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)
        question = factories.question.create(form=form, text="Source question")

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToComponentSessionModel(
                data_type=QuestionDataType.YES_NO,
                component_form_data={
                    "text": "Test text",
                    "name": "Test name",
                    "hint": "Test hint",
                    "add_context": "text",
                },
                data_source=ExpressionContext.ContextSources.SECTION,
                collection_id=form.collection_id,
                form_id=form.id,
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.select_context_source_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            ),
            data={"question": ExpressionReference.from_question(question)},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            r"^/deliver/grant/[a-z0-9-]{36}/section/[a-z0-9-]{36}/questions/add\?question_data_type=YES_NO$"
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            question_data = sess.get("question")
            assert question_data is not None
            assert question_data["component_form_data"]["text"] == f"Test text (({question.safe_qid}))"

    def test_post_redirects_to_guidance_and_updates_session(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)
        referenced_question = factories.question.create(form=form)
        question = factories.question.create(form=form)

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToComponentGuidanceSessionModel(
                component_form_data={
                    "add_context": "guidance_body",
                    "guidance_body": "Some guidance text here",
                    "guidance_heading": "Guidance header",
                    "preview": False,
                },
                component_id=question.id,
                data_source=ExpressionContext.ContextSources.SECTION,
                collection_id=form.collection_id,
                form_id=form.id,
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.select_context_source_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            ),
            data={"question": ExpressionReference.from_question(referenced_question)},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{question.id}/guidance"
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            question_data = sess.get("question")
            assert question_data is not None
            assert (
                question_data["component_form_data"]["guidance_body"]
                == f"Some guidance text here (({referenced_question.safe_qid}))"
            )

    @pytest.mark.parametrize(
        "expression_type, existing_expression",
        (
            (ExpressionType.CONDITION, False),
            (ExpressionType.CONDITION, True),
            (ExpressionType.VALIDATION, False),
            (ExpressionType.VALIDATION, True),
        ),
    )
    def test_post_redirects_to_expression_and_updates_session(
        self, authenticated_grant_admin_client, factories, db_session, expression_type, existing_expression
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)
        reference_data_question = factories.question.create(form=form, data_type=QuestionDataType.NUMBER)
        depends_on_question = factories.question.create(form=form, data_type=QuestionDataType.NUMBER)
        target_question = factories.question.create(form=form, data_type=QuestionDataType.NUMBER)

        expression_id = None
        if existing_expression:
            expression = GreaterThan(
                subject_reference=ExpressionReference.from_question(target_question), minimum_value=100
            )
            interfaces.collections.add_component_validation(
                target_question, interfaces.user.get_current_user(), expression
            )
            db_session.commit()
            expression_id = target_question.expressions[0].id

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToExpressionsModel(
                field=expression_type,
                managed_expression_name=ManagedExpressionsEnum.GREATER_THAN,
                expression_form_data={
                    "type": "Greater than",
                    "greater_than_value": None,
                    "greater_than_expression": "",
                    "greater_than_inclusive": False,
                    "add_context": "greater_than_expression",
                },
                component_id=target_question.id,
                data_source=ExpressionContext.ContextSources.SECTION,
                collection_id=form.collection_id,
                form_id=form.id,
                subject_reference=ExpressionReference.from_question(depends_on_question)
                if (expression_type is ExpressionType.CONDITION and not existing_expression)
                else None,
                expression_id=expression_id,
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.select_context_source_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            ),
            data={"question": ExpressionReference.from_question(reference_data_question)},
            follow_redirects=False,
        )
        assert response.status_code == 302

        with authenticated_grant_admin_client.session_transaction() as sess:
            question_data = sess.get("question")
            assert question_data is not None
            assert (
                question_data["expression_form_data"]["greater_than_expression"]
                == f"(({reference_data_question.safe_qid}))"
            )

        if expression_type is ExpressionType.CONDITION:
            if existing_expression:
                assert response.location == AnyStringMatching(
                    rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/condition/{expression_id}"
                )
            else:
                assert response.location == AnyStringMatching(
                    rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/"
                    + rf"{target_question.id}/add-condition/{ExpressionReference.from_question(depends_on_question)}"
                )
        else:
            if existing_expression:
                assert response.location == AnyStringMatching(
                    rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/validation/{expression_id}"
                )
            else:
                assert response.location == AnyStringMatching(
                    rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{target_question.id}/add-validation"
                )

    def test_post_redirects_to_add_condition_and_clears_session(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)
        referenced_question = factories.question.create(form=form)
        question = factories.question.create(form=form)

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddConditionDependsOnSessionModel(
                field="condition_depends_on",
                component_id=question.id,
                data_source=ExpressionContext.ContextSources.SECTION,
                collection_id=form.collection_id,
                form_id=form.id,
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.select_context_source_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            ),
            data={"question": ExpressionReference.from_question(referenced_question)},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{question.id}/add-condition/{ExpressionReference.from_question(referenced_question)}"
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            assert sess.get("question") is None


class TestSelectContextSourceDataSet:
    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get(self, request, client_fixture, can_access, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        collection = factories.collection.create(grant=client.grant)
        form = factories.form.create(collection=collection)

        with client.session_transaction() as sess:
            sess["question"] = AddContextToComponentSessionModel(
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                component_form_data={
                    "text": "Test question text",
                    "name": "Test question name",
                    "hint": "Test question hint",
                    "add_context": "text",
                },
            ).model_dump(mode="json")

        response = client.get(
            url_for(
                "deliver_grant_funding.select_context_source_data_set",
                grant_id=client.grant.id,
                form_id=form.id,
            )
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200

    def test_get_fails_with_empty_session(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_context_source_data_set",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            )
        )
        assert response.status_code == 400

    def test_get_shows_available_data_set_choices(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        report_2 = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)

        data_source = factories.data_source.create(
            grant=authenticated_grant_admin_client.grant,
            collection=collection,
            name="Test data set",
            type=DataSourceType.GRANT_RECIPIENT,
        )

        data_source_2 = factories.data_source.create(
            grant=authenticated_grant_admin_client.grant,
            collection=collection,
            name="Second data set",
            type=DataSourceType.GRANT_RECIPIENT,
        )

        data_source_3 = factories.data_source.create(
            grant=authenticated_grant_admin_client.grant,
            collection=collection,
            name="Data set with just text column should still show",
            type=DataSourceType.GRANT_RECIPIENT,
            schema=DataSourceSchema.model_validate(
                {
                    "c_description": DataSourceSchemaColumn(
                        data_type=QuestionDataType.TEXT_SINGLE_LINE,
                        presentation_options=QuestionPresentationOptions(),
                        data_options=QuestionDataOptions(),
                        original_column_name="Description",
                    )
                }
            ),
        )

        data_source_4 = factories.data_source.create(
            grant=authenticated_grant_admin_client.grant,
            collection=report_2,
            name="Data set that shouldn't be shown",
            type=DataSourceType.GRANT_RECIPIENT,
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToComponentSessionModel(
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                component_form_data={
                    "text": "Test question text",
                    "name": "Test question name",
                    "hint": "Test question hint",
                    "add_context": "text",
                },
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_context_source_data_set",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            )
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "Select uploaded data set" in soup.text
        assert data_source.name in soup.text
        assert data_source_2.name in soup.text
        assert data_source_3.name in soup.text
        assert data_source_4.name not in soup.text

    def test_get_shows_only_data_sets_with_number_columns_when_expression_reference(
        self, authenticated_grant_admin_client, factories
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        report_2 = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)
        question = factories.question.create(form=form, data_type=QuestionDataType.NUMBER)

        data_source = factories.data_source.create(
            grant=authenticated_grant_admin_client.grant,
            collection=collection,
            name="Test data set",
            type=DataSourceType.GRANT_RECIPIENT,
        )

        data_source_2 = factories.data_source.create(
            grant=authenticated_grant_admin_client.grant,
            collection=collection,
            name="Second data set",
            type=DataSourceType.GRANT_RECIPIENT,
        )

        data_source_3 = factories.data_source.create(
            grant=authenticated_grant_admin_client.grant,
            collection=collection,
            name="Data set with just text column",
            type=DataSourceType.GRANT_RECIPIENT,
            schema=DataSourceSchema.model_validate(
                {
                    "c_description": DataSourceSchemaColumn(
                        data_type=QuestionDataType.TEXT_SINGLE_LINE,
                        presentation_options=QuestionPresentationOptions(),
                        data_options=QuestionDataOptions(),
                        original_column_name="Description",
                    )
                }
            ),
        )

        data_source_4 = factories.data_source.create(
            grant=authenticated_grant_admin_client.grant,
            collection=report_2,
            name="Data set that shouldn't be shown",
            type=DataSourceType.GRANT_RECIPIENT,
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToExpressionsModel(
                field=ExpressionType.VALIDATION,
                managed_expression_name=ManagedExpressionsEnum.GREATER_THAN,
                expression_form_data={
                    "type": "Greater than",
                    "greater_than_value": None,
                    "greater_than_expression": "",
                    "greater_than_inclusive": False,
                    "add_context": "greater_than_expression",
                },
                component_id=question.id,
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_context_source_data_set",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            )
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "Select uploaded data set" in soup.text
        assert data_source.name in soup.text
        assert data_source_2.name in soup.text
        assert data_source_3.name not in soup.text
        assert data_source_4.name not in soup.text

    def test_get_shows_only_data_sets_with_number_columns_when_condition_depends_on_reference(
        self, authenticated_grant_admin_client, factories
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)
        question = factories.question.create(form=form, data_type=QuestionDataType.NUMBER)

        data_source = factories.data_source.create(
            grant=authenticated_grant_admin_client.grant,
            collection=collection,
            name="Test data set",
            type=DataSourceType.GRANT_RECIPIENT,
        )

        data_source_2 = factories.data_source.create(
            grant=authenticated_grant_admin_client.grant,
            collection=collection,
            name="Second data set",
            type=DataSourceType.GRANT_RECIPIENT,
        )

        data_source_3 = factories.data_source.create(
            grant=authenticated_grant_admin_client.grant,
            collection=collection,
            name="Data set with just text column",
            type=DataSourceType.GRANT_RECIPIENT,
            schema=DataSourceSchema.model_validate(
                {
                    "c_description": DataSourceSchemaColumn(
                        data_type=QuestionDataType.TEXT_SINGLE_LINE,
                        presentation_options=QuestionPresentationOptions(),
                        data_options=QuestionDataOptions(),
                        original_column_name="Description",
                    )
                }
            ),
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddConditionDependsOnSessionModel(
                component_id=question.id,
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_context_source_data_set",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            )
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "Select uploaded data set" in soup.text
        assert data_source.name in soup.text
        assert data_source_2.name in soup.text
        assert data_source_3.name not in soup.text

    def test_get_shows_text_when_no_data_sets(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToComponentSessionModel(
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                component_form_data={
                    "text": "Test question text",
                    "name": "Test question name",
                    "hint": "Test question hint",
                    "add_context": "text",
                },
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_context_source_data_set",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            )
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "Select uploaded data set" in soup.text
        assert "There are no data sets to reference in this collection" in soup.text
        assert page_has_link(soup, "Cancel")

    def test_post_redirects_to_select_data_set_column_and_updates_session(
        self, authenticated_grant_admin_client, factories
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)
        data_source = factories.data_source.create(
            grant=authenticated_grant_admin_client.grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToComponentSessionModel(
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                component_form_data={
                    "text": "Test question text",
                    "name": "Test question name",
                    "hint": "Test question hint",
                    "add_context": "text",
                },
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.select_context_source_data_set",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            ),
            data={"data_set": data_source.id},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == (
            f"/deliver/grant/{authenticated_grant_admin_client.grant.id}/section/"
            f"{form.id}/add-context/data-set/{data_source.id}/select-column"
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            question_data = sess.get("question")
            assert question_data is not None


class TestSelectContextSourceDataSetColumn:
    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get(self, request, client_fixture, can_access, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        collection = factories.collection.create(grant=client.grant)
        form = factories.form.create(collection=collection)
        data_set = factories.data_source.create(
            grant=client.grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
        )

        with client.session_transaction() as sess:
            sess["question"] = AddContextToComponentSessionModel(
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                component_form_data={
                    "text": "Test question text",
                    "name": "Test question name",
                    "hint": "Test question hint",
                    "add_context": "text",
                },
            ).model_dump(mode="json")

        response = client.get(
            url_for(
                "deliver_grant_funding.select_context_source_data_set_column",
                grant_id=client.grant.id,
                form_id=form.id,
                data_set_id=data_set.id,
            )
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200

    def test_get_404_if_other_collection_data_set(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)

        report_2 = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        data_set_2 = factories.data_source.create(
            grant=authenticated_grant_admin_client.grant,
            collection=report_2,
            name="Different collection data set",
            type=DataSourceType.GRANT_RECIPIENT,
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToComponentSessionModel(
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                component_form_data={
                    "text": "Test question text",
                    "name": "Test question name",
                    "hint": "Test question hint",
                    "add_context": "text",
                },
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_context_source_data_set_column",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
                data_set_id=data_set_2.id,
            )
        )
        assert response.status_code == 404

    def test_get_fails_with_empty_session(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)
        data_set = factories.data_source.create(
            grant=authenticated_grant_admin_client.grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
        )

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_context_source_data_set_column",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
                data_set_id=data_set.id,
            )
        )
        assert response.status_code == 400

    def test_get_shows_available_data_set_columns(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)
        data_set = factories.data_source.create(
            grant=authenticated_grant_admin_client.grant,
            collection=collection,
            name="Test data set",
            type=DataSourceType.GRANT_RECIPIENT,
            schema=DataSourceSchema.model_validate(
                {
                    "c_capital_allocation": DataSourceSchemaColumn(
                        data_type=QuestionDataType.NUMBER,
                        presentation_options=QuestionPresentationOptions(),
                        data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
                        original_column_name="Capital Allocation",
                    ),
                    "c_revenue_allocation": DataSourceSchemaColumn(
                        data_type=QuestionDataType.NUMBER,
                        presentation_options=QuestionPresentationOptions(),
                        data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
                        original_column_name="Revenue Allocation",
                    ),
                    "c_description": DataSourceSchemaColumn(
                        data_type=QuestionDataType.TEXT_SINGLE_LINE,
                        presentation_options=QuestionPresentationOptions(),
                        data_options=QuestionDataOptions(),
                        original_column_name="Description",
                    ),
                }
            ),
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToComponentSessionModel(
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                component_form_data={
                    "text": "Test question text",
                    "name": "Test question name",
                    "hint": "Test question hint",
                    "add_context": "text",
                },
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_context_source_data_set_column",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
                data_set_id=data_set.id,
            )
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert f"Select column in {data_set.name} data set" in soup.text
        assert "Capital Allocation" in soup.text
        assert "Revenue Allocation" in soup.text
        assert "Description" in soup.text

    def test_get_shows_only_number_columns_when_expression(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)
        question = factories.question.create(form=form, data_type=QuestionDataType.NUMBER)
        data_set = factories.data_source.create(
            grant=authenticated_grant_admin_client.grant,
            collection=collection,
            name="Test data set",
            type=DataSourceType.GRANT_RECIPIENT,
            schema=DataSourceSchema.model_validate(
                {
                    "c_capital_allocation": DataSourceSchemaColumn(
                        data_type=QuestionDataType.NUMBER,
                        presentation_options=QuestionPresentationOptions(),
                        data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
                        original_column_name="Capital Allocation",
                    ),
                    "c_revenue_allocation": DataSourceSchemaColumn(
                        data_type=QuestionDataType.NUMBER,
                        presentation_options=QuestionPresentationOptions(),
                        data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
                        original_column_name="Revenue Allocation",
                    ),
                    "c_description": DataSourceSchemaColumn(
                        data_type=QuestionDataType.TEXT_SINGLE_LINE,
                        presentation_options=QuestionPresentationOptions(),
                        data_options=QuestionDataOptions(),
                        original_column_name="Description",
                    ),
                }
            ),
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToExpressionsModel(
                field=ExpressionType.VALIDATION,
                managed_expression_name=ManagedExpressionsEnum.GREATER_THAN,
                expression_form_data={
                    "type": "Greater than",
                    "greater_than_value": None,
                    "greater_than_expression": "",
                    "greater_than_inclusive": False,
                    "add_context": "greater_than_expression",
                },
                component_id=question.id,
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_context_source_data_set_column",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
                data_set_id=data_set.id,
            )
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert f"Select column in {data_set.name} data set" in soup.text
        assert "Capital Allocation" in soup.text
        assert "Revenue Allocation" in soup.text
        assert "Description" not in soup.text

    def test_get_shows_only_number_columns_when_condition_depends_on_reference(
        self, authenticated_grant_admin_client, factories
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)
        question = factories.question.create(form=form, data_type=QuestionDataType.NUMBER)
        data_set = factories.data_source.create(
            grant=authenticated_grant_admin_client.grant,
            collection=collection,
            name="Test data set",
            type=DataSourceType.GRANT_RECIPIENT,
            schema=DataSourceSchema.model_validate(
                {
                    "c_capital_allocation": DataSourceSchemaColumn(
                        data_type=QuestionDataType.NUMBER,
                        presentation_options=QuestionPresentationOptions(),
                        data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
                        original_column_name="Capital Allocation",
                    ),
                    "c_revenue_allocation": DataSourceSchemaColumn(
                        data_type=QuestionDataType.NUMBER,
                        presentation_options=QuestionPresentationOptions(),
                        data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
                        original_column_name="Revenue Allocation",
                    ),
                    "c_description": DataSourceSchemaColumn(
                        data_type=QuestionDataType.TEXT_SINGLE_LINE,
                        presentation_options=QuestionPresentationOptions(),
                        data_options=QuestionDataOptions(),
                        original_column_name="Description",
                    ),
                }
            ),
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddConditionDependsOnSessionModel(
                component_id=question.id,
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_context_source_data_set_column",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
                data_set_id=data_set.id,
            )
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert f"Select column in {data_set.name} data set" in soup.text
        assert "Capital Allocation" in soup.text
        assert "Revenue Allocation" in soup.text
        assert "Description" not in soup.text

    def test_get_shows_text_when_data_set_has_no_number_columns(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)
        question = factories.question.create(form=form, data_type=QuestionDataType.NUMBER)
        data_set = factories.data_source.create(
            grant=authenticated_grant_admin_client.grant,
            collection=collection,
            name="Test data set",
            type=DataSourceType.GRANT_RECIPIENT,
            schema=DataSourceSchema.model_validate(
                {
                    "c_description": DataSourceSchemaColumn(
                        data_type=QuestionDataType.TEXT_SINGLE_LINE,
                        presentation_options=QuestionPresentationOptions(),
                        data_options=QuestionDataOptions(),
                        original_column_name="Description",
                    ),
                }
            ),
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToExpressionsModel(
                field=ExpressionType.VALIDATION,
                managed_expression_name=ManagedExpressionsEnum.GREATER_THAN,
                expression_form_data={
                    "type": "Greater than",
                    "greater_than_value": None,
                    "greater_than_expression": "",
                    "greater_than_inclusive": False,
                    "add_context": "greater_than_expression",
                },
                component_id=question.id,
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_context_source_data_set_column",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
                data_set_id=data_set.id,
            )
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert f"Select column in {data_set.name} data set" in soup.text
        assert "You cannot reference this data set because there are no columns with numbers" in soup.text
        assert page_has_link(soup, "Cancel")

    def test_post_with_component_session_model_new_question_redirects_and_updates_session(
        self, authenticated_grant_admin_client, factories
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)
        data_set = factories.data_source.create(
            grant=authenticated_grant_admin_client.grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToComponentSessionModel(
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                component_form_data={
                    "text": "Test question text",
                    "name": "Test question name",
                    "hint": "Test question hint",
                    "add_context": "text",
                },
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.select_context_source_data_set_column",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
                data_set_id=data_set.id,
            ),
            data={"column": next(iter(data_set.schema.root))},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == (
            f"/deliver/grant/{authenticated_grant_admin_client.grant.id}/section/"
            f"{form.id}/questions/add?question_data_type=TEXT_SINGLE_LINE"
        )
        with authenticated_grant_admin_client.session_transaction() as sess:
            question_data = sess.get("question")
            assert question_data is not None
            expected_reference = ExpressionReference.from_data_source_column(data_set, "c_allocation")
            assert question_data["component_form_data"]["text"] == f"Test question text {expected_reference.wrapped}"

    def test_post_with_component_session_model_existing_question_redirects_and_updates_session(
        self, authenticated_grant_admin_client, factories
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)
        question = factories.question.create(form=form)
        data_set = factories.data_source.create(
            grant=authenticated_grant_admin_client.grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToComponentSessionModel(
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                component_form_data={
                    "text": "Test question text",
                    "name": "Test question name",
                    "hint": "Test question hint",
                    "add_context": "text",
                },
                component_id=question.id,
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.select_context_source_data_set_column",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
                data_set_id=data_set.id,
            ),
            data={"column": next(iter(data_set.schema.root))},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == (
            f"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{question.id}"
        )
        with authenticated_grant_admin_client.session_transaction() as sess:
            question_data = sess.get("question")
            assert question_data is not None
            expected_reference = ExpressionReference.from_data_source_column(data_set, "c_allocation")
            assert question_data["component_form_data"]["text"] == f"Test question text {expected_reference.wrapped}"

    def test_post_with_guidance_session_model_redirects_and_updates_session(
        self, authenticated_grant_admin_client, factories
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)
        question = factories.question.create(form=form)
        data_set = factories.data_source.create(
            grant=authenticated_grant_admin_client.grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToComponentGuidanceSessionModel(
                component_form_data={
                    "add_context": "guidance_body",
                    "guidance_body": "Some guidance text",
                    "guidance_heading": "Guidance header",
                    "preview": False,
                },
                component_id=question.id,
                is_add_another_guidance=False,
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.select_context_source_data_set_column",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
                data_set_id=data_set.id,
            ),
            data={"column": next(iter(data_set.schema.root))},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == (
            f"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{question.id}/guidance"
        )
        with authenticated_grant_admin_client.session_transaction() as sess:
            question_data = sess.get("question")
            assert question_data is not None
            expected_reference = ExpressionReference.from_data_source_column(data_set, "c_allocation")
            assert (
                question_data["component_form_data"]["guidance_body"]
                == f"Some guidance text {expected_reference.wrapped}"
            )

    def test_post_with_expressions_session_model_redirects_and_updates_session(
        self, authenticated_grant_admin_client, factories
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)
        question = factories.question.create(form=form)
        data_set = factories.data_source.create(
            grant=authenticated_grant_admin_client.grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToExpressionsModel(
                field=ExpressionType.VALIDATION,
                managed_expression_name=ManagedExpressionsEnum.GREATER_THAN,
                expression_form_data={
                    "type": "Greater than",
                    "greater_than_value": None,
                    "greater_than_expression": "",
                    "greater_than_inclusive": False,
                    "add_context": "greater_than_expression",
                },
                component_id=question.id,
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.select_context_source_data_set_column",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
                data_set_id=data_set.id,
            ),
            data={"column": next(iter(data_set.schema.root))},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == (
            f"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{question.id}/add-validation"
        )
        with authenticated_grant_admin_client.session_transaction() as sess:
            question_data = sess.get("question")
            assert question_data is not None
            expected_reference = ExpressionReference.from_data_source_column(data_set, "c_allocation")
            assert question_data["expression_form_data"]["greater_than_expression"] == expected_reference.wrapped

    def test_post_with_custom_validation_expressions_session_model_redirects_and_updates_session(
        self, authenticated_grant_admin_client, factories
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)
        question = factories.question.create(form=form)
        data_set = factories.data_source.create(
            grant=authenticated_grant_admin_client.grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToExpressionsModel(
                field=ExpressionType.VALIDATION,
                managed_expression_name=None,
                expression_form_data={
                    "custom_expression": "some existing text",
                    "add_context": "custom_expression",
                },
                component_id=question.id,
                is_custom=True,
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.select_context_source_data_set_column",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
                data_set_id=data_set.id,
            ),
            data={"column": next(iter(data_set.schema.root))},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == (
            f"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{question.id}/add-validation/custom"
        )
        with authenticated_grant_admin_client.session_transaction() as sess:
            question_data = sess.get("question")
            assert question_data is not None
            expected_reference = ExpressionReference.from_data_source_column(data_set, "c_allocation")
            assert (
                question_data["expression_form_data"]["custom_expression"]
                == f"some existing text {expected_reference.wrapped}"
            )

    def test_post_with_calculated_condition_expressions_session_model_redirects_and_updates_session(
        self, authenticated_grant_admin_client, factories
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)
        question = factories.question.create(form=form)
        data_set = factories.data_source.create(
            grant=authenticated_grant_admin_client.grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToExpressionsModel(
                field=ExpressionType.CONDITION,
                managed_expression_name=None,
                expression_form_data={
                    "custom_expression": "some existing text",
                    "add_context": "custom_expression",
                },
                component_id=question.id,
                is_custom=True,
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.select_context_source_data_set_column",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
                data_set_id=data_set.id,
            ),
            data={"column": next(iter(data_set.schema.root))},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == (
            f"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{question.id}/add-calculated-condition"
        )
        with authenticated_grant_admin_client.session_transaction() as sess:
            question_data = sess.get("question")
            assert question_data is not None
            expected_reference = ExpressionReference.from_data_source_column(data_set, "c_allocation")
            assert (
                question_data["expression_form_data"]["custom_expression"]
                == f"some existing text {expected_reference.wrapped}"
            )

    def test_post_with_condition_depends_on_session_model_redirects_and_updates_session(
        self, authenticated_grant_admin_client, factories
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=collection)
        question = factories.question.create(form=form)
        data_set = factories.data_source.create(
            grant=authenticated_grant_admin_client.grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddConditionDependsOnSessionModel(
                component_id=question.id,
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.select_context_source_data_set_column",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
                data_set_id=data_set.id,
            ),
            data={"column": next(iter(data_set.schema.root))},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            "^/deliver/grant/[a-z0-9-]{36}/question/[a-z0-9-]{36}/add-condition/d_[0-9a-f]{32}.c_allocation"
        )
        with authenticated_grant_admin_client.session_transaction() as sess:
            assert sess.get("question") is None

        # Additional request to follow the response through to the final destination and confirm the data set
        # is being referenced
        follow_response = authenticated_grant_admin_client.get(response.location)
        assert follow_response.status_code == 200
        soup = BeautifulSoup(follow_response.data, "html.parser")
        assert "Allocation from Grant allocation data set" in soup.text


class TestEditQuestion:
    def test_404(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for("deliver_grant_funding.edit_question", grant_id=uuid.uuid4(), question_id=uuid.uuid4())
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ["authenticated_grant_member_client", False],
            ["authenticated_grant_admin_client", True],
        ),
    )
    def test_get(self, request, client_fixture, can_access, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        collection = factories.collection.create(grant=client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")
        question = factories.question.create(
            form=form,
            text="My question",
            name="Question name",
            hint="Question hint",
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
        )

        response = client.get(
            url_for("deliver_grant_funding.edit_question", grant_id=client.grant.id, question_id=question.id)
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert get_h1_text(soup) == "Edit question"

            db_question = db_session.get(Question, question.id)
            assert db_question.text == "My question"
            assert db_question.name == "Question name"
            assert db_question.hint == "Question hint"
            assert db_question.data_type == QuestionDataType.TEXT_SINGLE_LINE

    def test_get_with_group(self, request, authenticated_grant_admin_client, factories, db_session):
        group = factories.group.create(
            form__collection__grant=authenticated_grant_admin_client.grant,
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True),
            name="Test group",
        )
        question = factories.question.create(parent=group, form=group.form)

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.edit_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=question.id,
            )
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")

        # we link back to the parent group in the breadcrumbs
        assert page_has_link(soup, "Test group")

        # the option to edit guidance text is removed and we give a prompt for what you can do
        assert "This question is part of a group of questions that are all on the same page." in soup.text
        assert page_has_link(soup, "question group")

    def test_post(self, authenticated_grant_admin_client, factories, db_session, mocker):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        question = factories.question.create(
            form=db_form,
            text="My question",
            name="Question name",
            hint="Question hint",
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
        )
        form = QuestionForm(
            data={
                "text": "Updated question",
                "hint": "Updated hint",
                "name": "Updated name",
            },
            question_type=QuestionDataType.TEXT_SINGLE_LINE,
        )
        spy_validate = mocker.spy(interfaces.collections, "_validate_and_sync_component_references")
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question",
                grant_id=grant.id,
                question_id=question.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/section/[a-z0-9-]{36}/questions$")
        assert spy_validate.call_count == 1

    def test_post_update_question_in_group_redirects_to_group_questions_page(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        grant = authenticated_grant_admin_client.grant
        group = factories.group.create(form__collection__grant=grant)
        question = factories.question.create(
            form=group.form,
            parent=group,
            text="My question",
            name="Question name",
            hint="Question hint",
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
        )
        form = QuestionForm(
            data={
                "text": "Updated question",
                "hint": "Updated hint",
                "name": "Updated name",
            },
            question_type=QuestionDataType.TEXT_SINGLE_LINE,
        )
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question",
                grant_id=grant.id,
                question_id=question.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/group/[a-z0-9-]{36}/questions$")

    def test_post_with_invalid_context_references(self, authenticated_grant_admin_client, factories, db_session):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        question = factories.question.create(
            form=db_form,
            text="My question",
            name="Question name",
            hint="Question hint",
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
        )
        form = QuestionForm(
            data={
                "text": "Updated question",
                "hint": "Updated hint ((invalid_reference))",
                "name": "Updated name",
            },
            question_type=QuestionDataType.TEXT_SINGLE_LINE,
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question",
                grant_id=grant.id,
                question_id=question.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )
        soup = BeautifulSoup(response.data, "html.parser")
        assert response.status_code == 200

        assert page_has_error(soup, "You cannot use ((invalid_reference)) because it does not exist")

    @pytest.mark.parametrize("context_field", ["text", "hint"])
    def test_post_to_add_context_redirects_and_sets_up_session(
        self, authenticated_grant_admin_client, factories, db_session, mocker, context_field
    ):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        question = factories.question.create(
            form=db_form,
            text="My question",
            name="Question name",
            hint="Question hint",
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
        )
        form = QuestionForm(
            data={
                "text": "Updated question",
                "hint": "Updated hint",
                "name": "Updated name",
                "add_context": context_field,
            },
            question_type=QuestionDataType.TEXT_SINGLE_LINE,
        )
        spy_validate = mocker.spy(interfaces.collections, "_validate_and_sync_component_references")
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question",
                grant_id=grant.id,
                question_id=question.id,
            ),
            data=get_form_data(form, submit=""),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            "^/deliver/grant/[a-z0-9-]{36}/section/[a-z0-9-]{36}/add-context/select-source$"
        )
        assert spy_validate.call_count == 0

        with authenticated_grant_admin_client.session_transaction() as sess:
            assert sess["question"]["field"] == "component"

    def test_post_from_add_context_success_cleans_that_bit_of_session(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        question = factories.question.create(
            form=db_form,
            text="My question",
            name="Question name",
            hint="Question hint",
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
        )

        session_data = AddContextToComponentSessionModel(
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            component_form_data={
                "text": "Test question text",
                "name": "Test question name",
                "hint": "Test question hint",
            },
            component_id=question.id,
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = session_data.model_dump(mode="json")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question",
                grant_id=grant.id,
                question_id=question.id,
            ),
            data={
                "text": "Test question text",
                "name": "Test question name",
                "hint": "Test question hint",
                "submit": "y",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/section/[a-z0-9-]{36}/questions$")

        with authenticated_grant_admin_client.session_transaction() as sess:
            assert "question" not in sess

    @pytest.mark.xfail
    def test_post_dependency_order_errors(self):
        # TODO: write me, followup PR, sorry
        # If you're a dev and you're looking at this please consider doing a kindness and taking 10 mins to write a nice
        # test here.
        raise AssertionError()

    def test_post_data_source_item_errors(self, authenticated_grant_admin_client, factories, db_session):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        q1 = factories.question.create(
            form=db_form,
            text="My question",
            name="Question name",
            hint="Question hint",
            data_type=QuestionDataType.RADIOS,
        )

        form = QuestionForm(
            data={
                "text": "My question",
                "hint": "Question name",
                "name": "Question hint",
                # duplicates option 1
                "data_source_items": f"{q1.data_source.items[0].label}\n{q1.data_source.items[1].label}\n"
                f"{q1.data_source.items[1].label}\n{q1.data_source.items[2].label}",
            },
            question_type=QuestionDataType.RADIOS,
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question",
                grant_id=grant.id,
                question_id=q1.id,
            ),
            data=get_form_data(form),
            follow_redirects=True,
        )
        soup = BeautifulSoup(response.data, "html.parser")
        assert response.status_code == 200

        assert page_has_error(soup, "Remove duplicate options from the list")

    def test_post_with_option_dependency_error(self, authenticated_grant_admin_client, factories, db_session):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        q1 = factories.question.create(
            form=db_form,
            text="My question",
            name="Question name",
            hint="Question hint",
            data_type=QuestionDataType.RADIOS,
        )
        q2 = factories.question.create(
            form=db_form,
            text="Dependent question",
            name="Dependent question name",
            hint="Dependent question hint",
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            expressions=[
                Expression.from_evaluatable_expression(
                    AnyOf(
                        subject_reference=ExpressionReference.from_question(q1),
                        items=[
                            {"key": q1.data_source.items[0].key, "label": q1.data_source.items[0].label},
                        ],
                    ),
                    ExpressionType.CONDITION,
                    factories.user.create(),
                )
            ],
        )
        form = QuestionForm(
            data={
                "text": "My question",
                "hint": "Question name",
                "name": "Question hint",
                # removes option 0
                "data_source_items": f"{q1.data_source.items[1].label}\n{q1.data_source.items[2].label}",
            },
            question_type=QuestionDataType.RADIOS,
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question",
                grant_id=grant.id,
                question_id=q1.id,
            ),
            data=get_form_data(form),
            follow_redirects=True,
        )
        soup = BeautifulSoup(response.data, "html.parser")
        assert response.status_code == 200

        # Check the dependency error flash/banner is present
        alert = soup.find(attrs={"role": "alert"})
        assert alert is not None, "expected an alert notification banner in the page"

        links = alert.select("a.govuk-notification-banner__link")
        assert len(links) == 2, f"expected 2 links in the dependency banner, found {len(links)}"

        # First link should point to the dependent question (q2)
        expected_q2_href = url_for("deliver_grant_funding.edit_question", grant_id=grant.id, question_id=q2.id)
        assert links[0]["href"] == expected_q2_href
        assert links[0].get_text(strip=True) == q2.text

        # Second link should point to the question being edited/deleted (q1)
        expected_q1_href = url_for("deliver_grant_funding.edit_question", grant_id=grant.id, question_id=q1.id)
        assert links[1]["href"] == expected_q1_href
        assert links[1].get_text(strip=True) == q1.text

    def test_post_with_integer_dependency_error(self, authenticated_grant_admin_client, factories, db_session):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")

        # Create integer question that will be referenced
        q1 = factories.question.create(
            form=db_form,
            text="Integer question",
            name="Integer question name",
            hint="Integer question hint",
            data_type=QuestionDataType.NUMBER,
        )

        # Create a dependent question that references q1 via a GreaterThan managed expression
        q2 = factories.question.create(
            form=db_form,
            text="Dependent on integer",
            name="Dependent question name",
            hint="Dependent question hint",
            data_type=QuestionDataType.NUMBER,
            expressions=[
                Expression.from_evaluatable_expression(
                    GreaterThan(subject_reference=ExpressionReference.from_question(q1), minimum_value=100),
                    ExpressionType.CONDITION,
                    factories.user.create(),
                )
            ],
        )

        # Attempt to delete q1 via the edit_question endpoint using the delete query param
        confirm_form = GenericConfirmDeletionForm()
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question",
                grant_id=grant.id,
                question_id=q1.id,
                delete="",
            ),
            data=get_form_data(confirm_form, submit=""),
            follow_redirects=True,
        )

        soup = BeautifulSoup(response.data, "html.parser")
        assert response.status_code == 200

        # Check the dependency error flash/banner is present
        alert = soup.find(attrs={"role": "alert"})
        assert alert is not None, "expected an alert notification banner in the page"

        links = alert.select("a.govuk-notification-banner__link")
        assert len(links) == 2, f"expected 2 links in the dependency banner, found {len(links)}"

        # First link should point to the dependent question (q2)
        expected_q2_href = url_for("deliver_grant_funding.edit_question", grant_id=grant.id, question_id=q2.id)
        assert links[0]["href"] == expected_q2_href
        assert links[0].get_text(strip=True) == q2.text

        # Second link should point to the question being edited/deleted (q1)
        expected_q1_href = url_for("deliver_grant_funding.edit_question", grant_id=grant.id, question_id=q1.id)
        assert links[1]["href"] == expected_q1_href
        assert links[1].get_text(strip=True) == q1.text

    def test_post_can_delete_question_with_only_self_referencing_managed_validation(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        question = factories.question.create(
            form=db_form,
            text="Self-validated number",
            data_type=QuestionDataType.NUMBER,
        )
        add_component_validation(
            question,
            factories.user.create(),
            GreaterThan(subject_reference=ExpressionReference.from_question(question), minimum_value=0, inclusive=True),
        )
        db_session.commit()
        question_id = question.id

        confirm_form = GenericConfirmDeletionForm(data={"confirm_deletion": True})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question",
                grant_id=grant.id,
                question_id=question_id,
                delete="",
            ),
            data=get_form_data(confirm_form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert db_session.get(Question, question_id) is None

    def test_restore_from_session_when_returning_from_add_session_flow(
        self, authenticated_grant_admin_client, factories
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")
        question = factories.question.create(
            form=form,
            text="Existing question text",
            name="Existing question name",
            hint="Existing question hint",
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
        )

        session_data = AddContextToComponentSessionModel(
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            component_form_data={
                "text": "Updated question text from session",
                "name": "Updated question name from session",
                "hint": "Updated question hint from session",
                "add_context": "text",
            },
            component_id=question.id,
            parent_id=None,
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = session_data.model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.edit_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=question.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")

        # Verify that the session data overrides the existing question data
        text_input = soup.find("textarea", {"name": "text"})
        assert text_input.text.strip() == "Updated question text from session"

        hint_textarea = soup.find("textarea", {"name": "hint"})
        assert hint_textarea.text.strip() == "Updated question hint from session"


class TestAddQuestionConditionSelectQuestion:
    def test_404(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.add_question_condition_select_question",
                grant_id=uuid.uuid4(),
                component_id=uuid.uuid4(),
            )
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get(self, request, client_fixture, can_access, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        collection = factories.collection.create(grant=client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")
        question = factories.question.create(
            form=form,
            text="My question",
            name="Question name",
            hint="Question hint",
            data_type=QuestionDataType.TEXT_MULTI_LINE,
        )
        group = factories.group.create(form=form, name="Test group")

        response = client.get(
            url_for(
                "deliver_grant_funding.add_question_condition_select_question",
                grant_id=client.grant.id,
                component_id=question.id,
            )
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert "The question" in soup.text
            assert "Reference data" in soup.text

        response = client.get(
            url_for(
                "deliver_grant_funding.add_question_condition_select_question",
                grant_id=client.grant.id,
                component_id=group.id,
            )
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert "The question group" in soup.text
            assert "Reference data" in soup.text

    def test_post_redirects_to_select_context_source(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")

        question = factories.question.create(
            form=form,
            text="My question",
            name="my_question",
            data_type=QuestionDataType.NUMBER,
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question_condition_select_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=question.id,
            ),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/section/{form.id}/add-context/select-source"
        )


class TestAddCalculatedCondition:
    def test_404(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.add_calculated_condition",
                grant_id=uuid.uuid4(),
                component_id=uuid.uuid4(),
            )
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_platform_admin_client", True),
        ),
    )
    def test_get(self, request, client_fixture, can_access, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        collection = factories.collection.create(grant=client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")

        group = factories.group.create(
            form=form,
        )

        target_question = factories.question.create(
            form=form,
            text="What is your email?",
            name="email question",
            hint="Enter your email",
            data_type=QuestionDataType.EMAIL,
        )

        response = client.get(
            url_for(
                "deliver_grant_funding.add_calculated_condition",
                grant_id=client.grant.id,
                component_id=target_question.id,
            )
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200

        response = client.get(
            url_for(
                "deliver_grant_funding.add_calculated_condition",
                grant_id=client.grant.id,
                component_id=group.id,
            )
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200

    def test_post_success(self, authenticated_grant_admin_client, factories, db_session, mocker):

        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")

        q1, q2, q3 = factories.question.create_batch(3, form=db_form, data_type=QuestionDataType.NUMBER)

        target_question = factories.question.create(
            form=db_form,
            text="Why so much?",
            name="text question",
            data_type=QuestionDataType.TEXT_MULTI_LINE,
        )

        assert len(target_question.expressions) == 0

        form = CalculatedConditionForm(
            data={
                "custom_expression": f"(({q3.safe_qid}))>(({q2.safe_qid}))+(({q1.safe_qid}))",
                "expression_name": "the name",
            },
            component=target_question,
            interpolation_context=ExpressionContext(),
            evaluation_context=ExpressionContext(),
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_calculated_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=target_question.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{target_question.id}"
        )

        assert len(target_question.expressions) == 1
        expression = target_question.expressions[0]
        assert expression.type_ == ExpressionType.CONDITION
        assert expression.managed_name is None
        assert expression.is_custom is True
        assert expression.evaluatable_expression.description == "the name"

    def test_post_error(self, authenticated_platform_admin_client, factories, db_session):
        collection = factories.collection.create(name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")

        q1, q2, q3 = factories.question.create_batch(3, form=db_form, data_type=QuestionDataType.NUMBER)

        target_question = factories.question.create(
            form=db_form,
            text="Why so much?",
            name="text question",
            data_type=QuestionDataType.TEXT_MULTI_LINE,
        )

        assert len(target_question.expressions) == 0

        form = CalculatedConditionForm(
            data={
                "custom_expression": f"(({q3.safe_qid})) greater than (({q2.safe_qid}))+(({q1.safe_qid}))",
                "expression_name": "new name",
            },
            component=target_question,
            interpolation_context=ExpressionContext(),
            evaluation_context=ExpressionContext(),
        )

        response = authenticated_platform_admin_client.post(
            url_for(
                "deliver_grant_funding.add_calculated_condition",
                grant_id=authenticated_platform_admin_client.grant.id,
                component_id=target_question.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 200

        assert len(target_question.expressions) == 0
        assert page_has_error(
            BeautifulSoup(response.data, "html.parser"),
            "The calculation does not make sense",
        )

    def test_post_error_wrong_order(self, authenticated_platform_admin_client, factories, db_session):
        collection = factories.collection.create(name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")

        q1, q2, q3 = factories.question.create_batch(3, form=db_form, data_type=QuestionDataType.NUMBER)

        assert len(q1.expressions) == 0

        form = CalculatedConditionForm(
            data={
                "custom_expression": f"(({q1.safe_qid}))<(({q2.safe_qid}))",
                "expression_name": "new name",
            },
            component=q1,
            interpolation_context=ExpressionContext(),
            evaluation_context=ExpressionContext(),
        )

        response = authenticated_platform_admin_client.post(
            url_for(
                "deliver_grant_funding.add_calculated_condition",
                grant_id=authenticated_platform_admin_client.grant.id,
                component_id=q1.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 200

        assert len(q1.expressions) == 0
        assert page_has_error(
            BeautifulSoup(response.data, "html.parser"),
            "because it comes after this question",
        )


class TestEditCalculatedCondition:
    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_platform_admin_client", True),
        ),
    )
    def test_get(self, request, client_fixture, can_access, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        collection = factories.collection.create(grant=client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")

        group = factories.group.create(
            form=form,
        )
        group_condition = Expression.from_evaluatable_expression(
            evaluatable_expression=CustomExpression(custom_expression="6>5"),
            expression_type=ExpressionType.CONDITION,
            created_by=factories.user.create(),
        )
        group.expressions.append(group_condition)
        db_session.add(group_condition)

        target_question = factories.question.create(form=form)
        question_condition = Expression.from_evaluatable_expression(
            evaluatable_expression=CustomExpression(custom_expression="4>5"),
            expression_type=ExpressionType.CONDITION,
            created_by=factories.user.create(),
        )
        target_question.expressions.append(question_condition)
        db_session.add(question_condition)
        db_session.commit()

        response = client.get(
            url_for(
                "deliver_grant_funding.edit_calculated_condition",
                grant_id=client.grant.id,
                expression_id=target_question.expressions[0].id,
            )
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200

        response = client.get(
            url_for(
                "deliver_grant_funding.edit_calculated_condition",
                grant_id=client.grant.id,
                expression_id=group.expressions[0].id,
            )
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200

    def test_post_success(self, authenticated_platform_admin_client, factories, db_session):
        collection = factories.collection.create(grant=authenticated_platform_admin_client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")

        group = factories.group.create(
            form=form,
        )
        group_condition = Expression.from_evaluatable_expression(
            evaluatable_expression=CustomExpression(custom_expression="6>5"),
            expression_type=ExpressionType.CONDITION,
            created_by=factories.user.create(),
        )
        group.expressions.append(group_condition)
        db_session.add(group_condition)

        target_question = factories.question.create(form=form)
        question_condition = Expression.from_evaluatable_expression(
            evaluatable_expression=CustomExpression(custom_expression="4>5", expression_name="test name"),
            expression_type=ExpressionType.CONDITION,
            created_by=factories.user.create(),
        )
        target_question.expressions.append(question_condition)
        db_session.add(question_condition)
        db_session.commit()

        wt_form = CalculatedConditionForm(
            data={"custom_expression": "68>70"},
            component=target_question,
            interpolation_context=ExpressionContext(),
            evaluation_context=ExpressionContext(),
        )
        response = authenticated_platform_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_calculated_condition",
                grant_id=authenticated_platform_admin_client.grant.id,
                expression_id=question_condition.id,
            ),
            data=get_form_data(wt_form),
        )
        assert response.status_code == 302
        updated_condition = db_session.get(Expression, question_condition.id)
        assert updated_condition.custom.custom_expression == "68>70"

        wt_form = CalculatedConditionForm(
            data={"custom_expression": "100<900", "expression_name": "new name"},
            component=target_question,
            interpolation_context=ExpressionContext(),
            evaluation_context=ExpressionContext(),
        )
        response = authenticated_platform_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_calculated_condition",
                grant_id=authenticated_platform_admin_client.grant.id,
                expression_id=group_condition.id,
            ),
            data=get_form_data(wt_form),
        )
        assert response.status_code == 302
        updated_condition = db_session.get(Expression, group_condition.id)
        assert updated_condition.custom.custom_expression == "100<900"
        assert updated_condition.custom.expression_name == "new name"

    def test_post_error(self, authenticated_platform_admin_client, factories, db_session):
        collection = factories.collection.create(grant=authenticated_platform_admin_client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")

        target_question = factories.question.create(form=form)
        later_question = factories.question.create(form=form, data_type=QuestionDataType.NUMBER)
        question_condition = Expression.from_evaluatable_expression(
            evaluatable_expression=CustomExpression(custom_expression="4>5", expression_name="test name"),
            expression_type=ExpressionType.CONDITION,
            created_by=factories.user.create(),
        )
        target_question.expressions.append(question_condition)
        db_session.add(question_condition)
        db_session.commit()

        wt_form = CalculatedConditionForm(
            data={"custom_expression": f"(({later_question.safe_qid}))>5", "expression_name": "new name"},
            component=target_question,
            interpolation_context=ExpressionContext(),
            evaluation_context=ExpressionContext(),
        )
        response = authenticated_platform_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_calculated_condition",
                grant_id=authenticated_platform_admin_client.grant.id,
                expression_id=question_condition.id,
            ),
            data=get_form_data(wt_form),
        )
        assert response.status_code == 200
        updated_condition = db_session.get(Expression, question_condition.id)
        assert updated_condition.custom.custom_expression == "4>5"
        assert page_has_error(
            BeautifulSoup(response.data, "html.parser"),
            f"You cannot use {later_question.name} because it comes after this question",
        )


class TestAddQuestionCondition:
    def test_404(self, authenticated_grant_admin_client):
        reference = ExpressionReference(f"q_{uuid.uuid4().hex}")
        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.add_question_condition",
                grant_id=uuid.uuid4(),
                component_id=uuid.uuid4(),
                subject_reference=reference,
            )
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get(self, request, client_fixture, can_access, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        collection = factories.collection.create(grant=client.grant, name="Test Report")
        form = factories.form.create(collection=collection, title="Organisation information")

        group = factories.group.create(
            form=form,
        )

        depends_on_question = factories.question.create(
            form=form,
            text="Do you like cheese?",
            name="cheese question",
            hint="Please select yes or no",
            data_type=QuestionDataType.YES_NO,
        )

        target_question = factories.question.create(
            form=form,
            text="What is your email?",
            name="email question",
            hint="Enter your email",
            data_type=QuestionDataType.EMAIL,
        )

        response = client.get(
            url_for(
                "deliver_grant_funding.add_question_condition",
                grant_id=client.grant.id,
                component_id=target_question.id,
                subject_reference=ExpressionReference.from_question(depends_on_question),
            )
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200

        response = client.get(
            url_for(
                "deliver_grant_funding.add_question_condition",
                grant_id=client.grant.id,
                component_id=group.id,
                subject_reference=ExpressionReference.from_question(depends_on_question),
            )
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200

    def test_post(self, authenticated_grant_admin_client, factories, db_session):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")

        depends_on_question = factories.question.create(
            form=db_form,
            text="Do you like cheese?",
            name="cheese question",
            hint="Please select yes or no",
            data_type=QuestionDataType.YES_NO,
        )
        reference = ExpressionReference.from_question(depends_on_question)

        target_question = factories.question.create(
            form=db_form,
            text="What is your email?",
            name="email question",
            hint="Enter your email",
            data_type=QuestionDataType.EMAIL,
        )

        assert len(target_question.expressions) == 0

        ConditionForm = build_managed_expression_form(ExpressionType.CONDITION, reference)
        form = ConditionForm(data={"type": "Yes"})

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=target_question.id,
                subject_reference=reference,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{target_question.id}"
        )

        assert len(target_question.expressions) == 1
        expression = target_question.expressions[0]
        assert expression.type_ == ExpressionType.CONDITION
        assert expression.managed_name == "Yes"
        assert expression.managed.referenced_question.id == depends_on_question.id

    def test_post_for_group(self, authenticated_grant_admin_client, factories, db_session):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")

        depends_on_question = factories.question.create(
            form=db_form,
            text="Do you like cheese?",
            name="cheese question",
            hint="Please select yes or no",
            data_type=QuestionDataType.YES_NO,
        )
        reference = ExpressionReference.from_question(depends_on_question)

        target_group = factories.group.create(form=db_form)

        assert len(target_group.expressions) == 0

        ConditionForm = build_managed_expression_form(ExpressionType.CONDITION, reference)
        form = ConditionForm(data={"type": "Yes"})

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=target_group.id,
                subject_reference=reference,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/group/{target_group.id}/questions"
        )

        assert len(target_group.expressions) == 1
        expression = target_group.expressions[0]
        assert expression.type_ == ExpressionType.CONDITION
        assert expression.managed_name == "Yes"
        assert expression.managed.referenced_question.id == depends_on_question.id

    def test_post_for_data_set(self, authenticated_grant_admin_client, factories, db_session):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        target_question = factories.question.create(
            form=db_form,
            text="How much cheese do you eat a month?",
            name="total cheese eaten",
            data_type=QuestionDataType.NUMBER,
        )
        data_set = factories.data_source.create(
            grant=authenticated_grant_admin_client.grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
        )

        reference = ExpressionReference.from_data_source_column(data_set, "c_allocation")

        ConditionForm = build_managed_expression_form(ExpressionType.CONDITION, reference)
        form = ConditionForm(
            data={
                "type": "Greater than",
                "greater_than_value": 100,
                "greater_than_expression": "",
                "greater_than_inclusive": False,
            }
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=target_question.id,
                subject_reference=reference,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{target_question.id}"
        )

        assert len(target_question.expressions) == 1
        expression = target_question.expressions[0]
        assert expression.type_ == ExpressionType.CONDITION
        assert expression.managed.subject_reference == reference
        assert len(expression.component_references) == 1
        assert expression.component_references[0].depends_on_data_source_id == data_set.id
        assert expression.component_references[0].depends_on_column_name == "c_allocation"

    def test_post_duplicate_condition(self, authenticated_grant_admin_client, factories, db_session):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")

        depends_on_question = factories.question.create(
            form=db_form,
            text="Do you like cheese?",
            name="cheese question",
            hint="Please select yes or no",
            data_type=QuestionDataType.YES_NO,
        )
        reference = ExpressionReference.from_question(depends_on_question)

        target_question = factories.question.create(
            form=db_form,
            text="What is your email?",
            name="email question",
            hint="Enter your email",
            data_type=QuestionDataType.EMAIL,
        )

        expression = IsYes(
            subject_reference=ExpressionReference.from_question(depends_on_question),
            referenced_question=depends_on_question,
        )
        interfaces.collections.add_component_condition(target_question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        ConditionForm = build_managed_expression_form(ExpressionType.CONDITION, reference)
        form = ConditionForm(data={"type": "Yes"})

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=target_question.id,
                subject_reference=reference,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "condition based on this question already exists" in soup.text

    def test_post_to_add_context_redirects_and_sets_up_session(
        self, authenticated_grant_admin_client, factories, db_session, mocker
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Cheese habits")

        depends_on_question = factories.question.create(
            form=db_form,
            text="How much cheese do you eat a month?",
            name="total cheese eaten",
            data_type=QuestionDataType.NUMBER,
        )
        reference = ExpressionReference.from_question(depends_on_question)

        target_question = factories.question.create(
            form=db_form,
            text="Why do you eat so much cheese?",
            name="why so much cheese",
            data_type=QuestionDataType.TEXT_MULTI_LINE,
        )

        assert len(target_question.expressions) == 0

        ConditionForm = build_managed_expression_form(ExpressionType.CONDITION, reference)
        form = ConditionForm(
            data={
                "type": "Greater than",
                "greater_than_value": None,
                "greater_than_expression": "",
                "greater_than_inclusive": False,
                "add_context": "greater_than_expression",
            }
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=target_question.id,
                subject_reference=reference,
            ),
            data=get_form_data(form, submit=""),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            "^/deliver/grant/[a-z0-9-]{36}/section/[a-z0-9-]{36}/add-context/select-source$"
        )
        assert len(target_question.expressions) == 0

        with authenticated_grant_admin_client.session_transaction() as session:
            assert session["question"]["field"] == ExpressionType.CONDITION

    def test_post_to_remove_context_updates_session_and_reloads_page(
        self, authenticated_grant_admin_client, factories, db_session, mocker
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Cheese habits")

        reference_data_question = factories.question.create(form=db_form, data_type=QuestionDataType.NUMBER)
        depends_on_question = factories.question.create(form=db_form, data_type=QuestionDataType.NUMBER)
        target_question = factories.question.create(form=db_form, data_type=QuestionDataType.TEXT_MULTI_LINE)
        reference = ExpressionReference.from_question(depends_on_question)

        session_data = AddContextToExpressionsModel(
            field=ExpressionType.CONDITION,
            managed_expression_name=ManagedExpressionsEnum.GREATER_THAN,
            expression_form_data={
                "type": "Greater than",
                "greater_than_value": None,
                "greater_than_expression": ExpressionReference.from_question(reference_data_question),
                "greater_than_inclusive": True,
            },
            component_id=target_question.id,
            subject_reference=ExpressionReference.from_question(depends_on_question),
        )

        with authenticated_grant_admin_client.session_transaction() as session:
            session["question"] = session_data.model_dump(mode="json")

        ConditionForm = build_managed_expression_form(ExpressionType.CONDITION, reference)
        form = ConditionForm(
            data={
                "type": "Greater than",
                "greater_than_value": None,
                "greater_than_expression": ExpressionReference.from_question(reference_data_question),
                "greater_than_inclusive": False,
                "remove_context": "greater_than_expression",
            }
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=target_question.id,
                subject_reference=reference,
            ),
            data=get_form_data(form, submit=""),
            follow_redirects=False,
        )

        assert response.status_code == 302

        assert response.location.endswith(
            url_for(
                "deliver_grant_funding.add_question_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=target_question.id,
                subject_reference=reference,
            )
        )
        assert len(target_question.expressions) == 0

        with authenticated_grant_admin_client.session_transaction() as session:
            assert session["question"]["field"] == ExpressionType.CONDITION
            assert session["question"]["expression_form_data"]["greater_than_expression"] == ""
            assert session["question"]["expression_form_data"]["greater_than_inclusive"] is False

    def test_post_from_add_context_success_cleans_that_bit_of_session(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Cheese habits")

        reference_data_question = factories.question.create(
            form=db_form,
            text="How much cheese do you buy a month?",
            name="total cheese bought",
            data_type=QuestionDataType.NUMBER,
        )

        depends_on_question = factories.question.create(
            form=db_form,
            text="How much cheese do you eat a month?",
            name="total cheese eaten",
            data_type=QuestionDataType.NUMBER,
        )
        reference = ExpressionReference.from_question(depends_on_question)

        target_question = factories.question.create(
            form=db_form,
            text="Why do you eat so much cheese?",
            name="why so much cheese",
            data_type=QuestionDataType.TEXT_MULTI_LINE,
        )

        ConditionForm = build_managed_expression_form(ExpressionType.CONDITION, reference)
        form = ConditionForm(
            data={
                "type": "Greater than",
                "greater_than_value": None,
                "greater_than_expression": ExpressionReference.from_question(reference_data_question),
                "greater_than_inclusive": False,
            }
        )

        session_data = AddContextToExpressionsModel(
            field=ExpressionType.CONDITION,
            managed_expression_name=ManagedExpressionsEnum.GREATER_THAN,
            expression_form_data=form.data,
            component_id=target_question.id,
            subject_reference=reference,
            value_dependent_question_id=reference_data_question.id,
        )

        with authenticated_grant_admin_client.session_transaction() as session:
            session["question"] = session_data.model_dump(mode="json")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=target_question.id,
                subject_reference=reference,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{target_question.id}"
        )

        assert len(target_question.expressions) == 1
        expression = target_question.expressions[0]
        assert expression.type_ == ExpressionType.CONDITION
        assert expression.managed_name == "Greater than"
        assert expression.managed.referenced_question.id == depends_on_question.id

        with authenticated_grant_admin_client.session_transaction() as session:
            assert "question" not in session


class TestEditQuestionCondition:
    def test_404(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for("deliver_grant_funding.edit_question_condition", grant_id=uuid.uuid4(), expression_id=uuid.uuid4())
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get(self, request, client_fixture, can_access, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        collection = factories.collection.create(grant=client.grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        depends_on_question = factories.question.create(
            form=db_form,
            text="Do you like cheese?",
            name="cheese question",
            data_type=QuestionDataType.YES_NO,
        )
        target_question = factories.question.create(
            form=db_form,
            text="What is your email?",
            name="email question",
            data_type=QuestionDataType.EMAIL,
        )
        expression = IsYes(
            subject_reference=ExpressionReference.from_question(depends_on_question),
            referenced_question=depends_on_question,
        )
        interfaces.collections.add_component_condition(target_question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        expression_id = target_question.expressions[0].id

        response = client.get(
            url_for(
                "deliver_grant_funding.edit_question_condition",
                grant_id=client.grant.id,
                expression_id=expression_id,
            )
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")

            assert get_h1_text(soup) == "Edit condition"

            assert "The question" in soup.text
            assert "What is your email?" in soup.text

            assert "Depends on" in soup.text
            assert "Do you like cheese?" in soup.text

            yes_radio = soup.find("input", {"type": "radio", "value": "Yes"})
            no_radio = soup.find("input", {"type": "radio", "value": "No"})
            assert yes_radio is not None
            assert no_radio is not None
            assert yes_radio.get("checked") is not None
            assert no_radio.get("checked") is None

            assert page_has_button(soup, "Save condition")

            delete_link = page_has_link(soup, "Delete condition")
            assert delete_link is not None

    def test_get_with_delete_parameter(self, authenticated_grant_admin_client, factories, db_session):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        depends_on_question = factories.question.create(
            form=db_form,
            text="Do you like cheese?",
            name="cheese question",
            data_type=QuestionDataType.YES_NO,
        )
        target_question = factories.question.create(
            form=db_form,
            text="What is your email?",
            name="email question",
            data_type=QuestionDataType.EMAIL,
        )
        expression = IsYes(
            subject_reference=ExpressionReference.from_question(depends_on_question),
            referenced_question=depends_on_question,
        )
        interfaces.collections.add_component_condition(target_question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        expression_id = target_question.expressions[0].id

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.edit_question_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=expression_id,
                delete="",
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_button(soup, "Yes, delete this condition")

    def test_post_update_condition(self, authenticated_grant_admin_client, factories, db_session):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        depends_on_question = factories.question.create(
            form=db_form,
            text="Do you like cheese?",
            name="cheese question",
            data_type=QuestionDataType.YES_NO,
        )
        target_question = factories.question.create(
            form=db_form,
            text="What is your email?",
            name="email question",
            data_type=QuestionDataType.EMAIL,
        )
        expression = IsYes(
            subject_reference=ExpressionReference.from_question(depends_on_question),
            referenced_question=depends_on_question,
        )
        interfaces.collections.add_component_condition(target_question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        expression_id = target_question.expressions[0].id
        assert target_question.expressions[0].managed_name == "Yes"

        ConditionForm = build_managed_expression_form(
            ExpressionType.CONDITION,
            ExpressionReference.from_question(depends_on_question),
            target_question.expressions[0],
        )
        form = ConditionForm(data={"type": "No"})

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=expression_id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{target_question.id}"
        )

        assert len(target_question.expressions) == 1
        assert target_question.expressions[0].managed_name == "No"

    def test_post_update_group_condition(self, authenticated_grant_admin_client, factories, db_session):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        depends_on_question = factories.question.create(
            form=db_form,
            text="Do you like cheese?",
            name="cheese question",
            data_type=QuestionDataType.YES_NO,
        )
        target_question = factories.group.create(form=db_form)
        expression = IsYes(
            subject_reference=ExpressionReference.from_question(depends_on_question),
            referenced_question=depends_on_question,
        )
        interfaces.collections.add_component_condition(target_question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        expression_id = target_question.expressions[0].id
        assert target_question.expressions[0].managed_name == "Yes"

        ConditionForm = build_managed_expression_form(
            ExpressionType.CONDITION,
            ExpressionReference.from_question(depends_on_question),
            target_question.expressions[0],
        )
        form = ConditionForm(data={"type": "No"})

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=expression_id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/group/{target_question.id}/questions"
        )

        assert len(target_question.expressions) == 1
        assert target_question.expressions[0].managed_name == "No"

    def test_post_update_condition_duplicate(self, authenticated_grant_admin_client, factories, db_session):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        depends_on_question = factories.question.create(
            form=db_form,
            text="Do you like cheese?",
            name="cheese question",
            data_type=QuestionDataType.YES_NO,
        )
        target_question = factories.question.create(
            form=db_form,
            text="What is your email?",
            name="email question",
            data_type=QuestionDataType.EMAIL,
        )
        yes_expression = IsYes(
            subject_reference=ExpressionReference.from_question(depends_on_question),
            referenced_question=depends_on_question,
        )
        interfaces.collections.add_component_condition(
            target_question, interfaces.user.get_current_user(), yes_expression
        )

        no_expression = IsNo(
            subject_reference=ExpressionReference.from_question(depends_on_question),
            referenced_question=depends_on_question,
        )
        interfaces.collections.add_component_condition(
            target_question, interfaces.user.get_current_user(), no_expression
        )
        db_session.commit()

        assert len(target_question.expressions) == 2
        yes_expression_id = None
        for expr in target_question.expressions:
            if expr.managed_name == "Yes":
                yes_expression_id = expr.id
                break

        ConditionForm = build_managed_expression_form(
            ExpressionType.CONDITION,
            ExpressionReference.from_question(depends_on_question),
            target_question.expressions[0],
        )
        form = ConditionForm(data={"type": "No"})

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=yes_expression_id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "condition based on this question already exists" in soup.text

    def test_post_delete(self, authenticated_grant_admin_client, factories, db_session):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        depends_on_question = factories.question.create(
            form=db_form,
            text="Do you like cheese?",
            name="cheese question",
            data_type=QuestionDataType.YES_NO,
        )
        target_question = factories.question.create(
            form=db_form,
            text="What is your email?",
            name="email question",
            data_type=QuestionDataType.EMAIL,
        )
        expression = IsYes(
            subject_reference=ExpressionReference.from_question(depends_on_question),
            referenced_question=depends_on_question,
        )
        interfaces.collections.add_component_condition(target_question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        expression_id = target_question.expressions[0].id
        assert len(target_question.expressions) == 1

        form = GenericConfirmDeletionForm(data={"confirm_deletion": True})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=expression_id,
                delete="",
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{target_question.id}"
        )

        assert len(target_question.expressions) == 0

    def test_post_to_add_context_redirects_and_sets_up_session(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Cheese habits")

        depends_on_question = factories.question.create(
            form=db_form,
            text="When did you last buy cheese?",
            name="last cheese purchase",
            data_type=QuestionDataType.DATE,
        )

        target_question = factories.question.create(
            form=db_form,
            text="Why haven't you bought cheese in such a long time?",
            name="lack of cheese reason",
            data_type=QuestionDataType.TEXT_MULTI_LINE,
        )

        expression = IsAfter(
            subject_reference=ExpressionReference.from_question(depends_on_question),
            earliest_value=date(2025, 1, 1),
        )
        interfaces.collections.add_component_condition(target_question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        expression_id = target_question.expressions[0].id

        assert len(target_question.expressions) == 1
        assert target_question.expressions[0].managed_name == "Is after"

        ConditionForm = build_managed_expression_form(
            ExpressionType.CONDITION,
            ExpressionReference.from_question(depends_on_question),
            target_question.expressions[0],
        )
        form = ConditionForm(
            data={
                "type": "Is after",
                "earliest_value": date(2025, 1, 1),
                "earliest_expression": "",
                "add_context": "earliest_expression",
            }
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=expression_id,
            ),
            data=get_form_data(form, submit=""),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            "^/deliver/grant/[a-z0-9-]{36}/section/[a-z0-9-]{36}/add-context/select-source$"
        )
        assert len(target_question.expressions) == 1

        with authenticated_grant_admin_client.session_transaction() as session:
            assert session["question"]["field"] == ExpressionType.CONDITION

    def test_post_to_remove_context_updates_session_and_reloads_page(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Cheese habits")

        reference_data_question = factories.question.create(form=db_form, data_type=QuestionDataType.DATE)
        depends_on_question = factories.question.create(form=db_form, data_type=QuestionDataType.DATE)
        target_question = factories.question.create(form=db_form, data_type=QuestionDataType.TEXT_MULTI_LINE)

        expression = IsAfter(
            subject_reference=ExpressionReference.from_question(depends_on_question),
            earliest_value=None,
            earliest_expression=ExpressionReference.from_question(reference_data_question),
            inclusive=True,
        )
        interfaces.collections.add_component_condition(target_question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        expression_id = target_question.expressions[0].id

        ConditionForm = build_managed_expression_form(
            ExpressionType.CONDITION,
            ExpressionReference.from_question(depends_on_question),
            target_question.expressions[0],
        )
        form = ConditionForm(
            data={
                "type": "Is after",
                "earliest_value": None,
                "earliest_expression": ExpressionReference.from_question(reference_data_question),
                "earliest_inclusive": False,
                "remove_context": "earliest_expression",
            }
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=expression_id,
            ),
            data=get_form_data(form, submit=""),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location.endswith(
            url_for(
                "deliver_grant_funding.edit_question_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=expression_id,
            )
        )
        assert len(target_question.expressions) == 1

        with authenticated_grant_admin_client.session_transaction() as session:
            assert session["question"]["field"] == ExpressionType.CONDITION
            assert session["question"]["expression_form_data"]["earliest_expression"] == ""
            assert session["question"]["expression_form_data"]["earliest_inclusive"] is False

    def test_post_from_add_context_success_cleans_that_bit_of_session(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Cheese habits")

        reference_data_question = factories.question.create(
            form=db_form,
            text="When did the year start?",
            name="start of year",
            data_type=QuestionDataType.DATE,
        )

        depends_on_question = factories.question.create(
            form=db_form,
            text="When did you last buy cheese?",
            name="last cheese purchase",
            data_type=QuestionDataType.DATE,
        )

        target_question = factories.question.create(
            form=db_form,
            text="Why haven't you bought cheese in such a long time?",
            name="lack of cheese reason",
            data_type=QuestionDataType.TEXT_MULTI_LINE,
        )

        expression = IsAfter(
            subject_reference=ExpressionReference.from_question(depends_on_question),
            earliest_value=date(2025, 12, 1),
        )
        interfaces.collections.add_component_condition(target_question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        expression_id = target_question.expressions[0].id
        assert len(target_question.expressions) == 1
        assert target_question.expressions[0].managed_name == "Is after"

        ConditionForm = build_managed_expression_form(
            ExpressionType.CONDITION,
            ExpressionReference.from_question(depends_on_question),
            target_question.expressions[0],
        )
        form = ConditionForm(
            data={
                "type": "Is after",
                "earliest_value": None,
                "earliest_expression": ExpressionReference.from_question(reference_data_question),
            }
        )

        session_data = AddContextToExpressionsModel(
            field=ExpressionType.CONDITION,
            managed_expression_name=ManagedExpressionsEnum.IS_AFTER,
            expression_id=expression_id,
            expression_form_data=form.data,
            component_id=target_question.id,
            subject_reference=ExpressionReference.from_question(depends_on_question),
            value_dependent_question_id=reference_data_question.id,
        )

        with authenticated_grant_admin_client.session_transaction() as session:
            session["question"] = session_data.model_dump(mode="json")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=expression_id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{target_question.id}"
        )

        assert len(target_question.expressions) == 1
        expression = target_question.expressions[0]
        assert expression.type_ == ExpressionType.CONDITION
        assert expression.managed_name == "Is after"
        assert expression.managed.referenced_question.id == depends_on_question.id
        assert expression.statement == f"{depends_on_question.safe_qid} > {reference_data_question.safe_qid}"

        with authenticated_grant_admin_client.session_transaction() as session:
            assert "question" not in session


class TestAddQuestionValidation:
    def test_404(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for("deliver_grant_funding.add_question_validation", grant_id=uuid.uuid4(), question_id=uuid.uuid4())
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get(self, request, client_fixture, can_access, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        collection = factories.collection.create(grant=client.grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        question = factories.question.create(
            form=db_form,
            text="How many employees do you have?",
            name="employee count",
            data_type=QuestionDataType.NUMBER,
        )

        response = client.get(
            url_for(
                "deliver_grant_funding.add_question_validation",
                grant_id=client.grant.id,
                question_id=question.id,
            )
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")

            assert get_h1_text(soup) == "Add validation"

            assert "Section" in soup.text
            assert "Organisation information" in soup.text

            assert "Question" in soup.text
            assert "How many employees do you have?" in soup.text

            greater_than_radio = soup.find("input", {"type": "radio", "value": "Greater than"})
            less_than_radio = soup.find("input", {"type": "radio", "value": "Less than"})
            between_radio = soup.find("input", {"type": "radio", "value": "Between"})
            assert greater_than_radio is not None
            assert less_than_radio is not None
            assert between_radio is not None

            assert page_has_button(soup, "Add validation")

    def test_get_no_validation_available(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        question = factories.question.create(
            form=db_form,
            text="What is your name?",
            name="applicant name",
            data_type=QuestionDataType.TEXT_MULTI_LINE,
        )

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.add_question_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=question.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "This question cannot be validated." in soup.text

    def test_post(self, authenticated_grant_admin_client, factories, db_session):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        question = factories.question.create(
            form=db_form,
            text="How many employees do you have?",
            name="employee count",
            data_type=QuestionDataType.NUMBER,
        )

        assert len(question.expressions) == 0

        ValidationForm = build_managed_expression_form(
            ExpressionType.VALIDATION, ExpressionReference.from_question(question)
        )
        form = ValidationForm(
            data={"type": "Greater than", "greater_than_value": "10", "greater_than_inclusive": False}
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=question.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{question.id}"
        )

        assert len(question.expressions) == 1
        expression = question.expressions[0]
        assert expression.type_ == ExpressionType.VALIDATION
        assert expression.managed_name == "Greater than"

    def test_post_duplicate_validation(self, authenticated_grant_admin_client, factories, db_session):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        question = factories.question.create(
            form=db_form,
            text="How many employees do you have?",
            name="employee count",
            data_type=QuestionDataType.NUMBER,
        )

        ValidationForm = build_managed_expression_form(
            ExpressionType.VALIDATION, ExpressionReference.from_question(question)
        )
        first_validation = ValidationForm(
            data={"type": "Greater than", "greater_than_value": "10", "greater_than_inclusive": False}
        )
        expression = first_validation.get_expression(ExpressionReference.from_question(question))
        interfaces.collections.add_component_validation(question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        duplicate_form = ValidationForm(
            data={"type": "Greater than", "greater_than_value": "10", "greater_than_inclusive": False}
        )
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=question.id,
            ),
            data=duplicate_form.data,
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "validation already exists on the question" in soup.text

    def test_post_to_add_context_redirects_and_sets_up_session(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Cheese habits")

        target_question = factories.question.create(
            form=db_form,
            text="How much cheese do you eat?",
            name="quantity of cheese",
            data_type=QuestionDataType.NUMBER,
        )

        assert len(target_question.expressions) == 0

        ValidationForm = build_managed_expression_form(
            ExpressionType.VALIDATION, ExpressionReference.from_question(target_question)
        )
        form = ValidationForm(
            data={
                "type": "Less than",
                "less_than_value": None,
                "less_than_expression": "",
                "less_than_inclusive": False,
                "add_context": "less_than_expression",
            }
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=target_question.id,
            ),
            data=get_form_data(form, submit=""),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            "^/deliver/grant/[a-z0-9-]{36}/section/[a-z0-9-]{36}/add-context/select-source$"
        )
        assert len(target_question.expressions) == 0

        with authenticated_grant_admin_client.session_transaction() as session:
            assert session["question"]["field"] == ExpressionType.VALIDATION

    def test_post_to_remove_context_updates_session_and_reloads_page(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Cheese habits")

        referenced_question = factories.question.create(form=db_form, data_type=QuestionDataType.NUMBER)
        target_question = factories.question.create(form=db_form, data_type=QuestionDataType.NUMBER)

        assert len(target_question.expressions) == 0

        session_data = AddContextToExpressionsModel(
            field=ExpressionType.VALIDATION,
            managed_expression_name=ManagedExpressionsEnum.BETWEEN,
            expression_form_data={
                "type": "Between",
                "between_bottom_of_range": None,
                "between_bottom_of_range_expression": ExpressionReference.from_question(referenced_question),
                "between_bottom_inclusive": True,
                "between_top_of_range": 100,
                "between_top_of_range_expression": "",
                "between_top_inclusive": True,
            },
            component_id=target_question.id,
        )

        with authenticated_grant_admin_client.session_transaction() as session:
            session["question"] = session_data.model_dump(mode="json")

        ValidationForm = build_managed_expression_form(
            ExpressionType.VALIDATION, ExpressionReference.from_question(target_question)
        )
        form = ValidationForm(
            data={
                "type": "Between",
                "between_bottom_of_range": None,
                "between_bottom_of_range_expression": ExpressionReference.from_question(referenced_question),
                "between_bottom_inclusive": False,
                "between_top_of_range": 100,
                "between_top_of_range_expression": "",
                "between_top_inclusive": True,
                "remove_context": "between_bottom_of_range_expression",
            }
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=target_question.id,
            ),
            data=get_form_data(form, submit=""),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location.endswith(
            url_for(
                "deliver_grant_funding.add_question_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=target_question.id,
            )
        )
        assert len(target_question.expressions) == 0

        with authenticated_grant_admin_client.session_transaction() as session:
            assert session["question"]["field"] == ExpressionType.VALIDATION
            assert session["question"]["expression_form_data"]["between_bottom_of_range_expression"] == ""
            assert session["question"]["expression_form_data"]["between_bottom_inclusive"] is False
            assert session["question"]["expression_form_data"]["between_top_of_range"] == str(Decimal("100"))

    def test_post_from_add_context_success_cleans_that_bit_of_session(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Cheese habits")

        reference_data_question = factories.question.create(
            form=db_form,
            text="How much cheese do you buy a month?",
            name="total cheese bought",
            data_type=QuestionDataType.NUMBER,
        )

        target_question = factories.question.create(
            form=db_form,
            text="How much cheese do you eat a month?",
            name="quantity of cheese",
            data_type=QuestionDataType.NUMBER,
        )

        ValidationForm = build_managed_expression_form(
            ExpressionType.VALIDATION, ExpressionReference.from_question(target_question)
        )
        form = ValidationForm(
            data={
                "type": "Less than",
                "less_than_value": None,
                "less_than_expression": ExpressionReference.from_question(reference_data_question),
                "less_than_inclusive": True,
            }
        )

        session_data = AddContextToExpressionsModel(
            field=ExpressionType.VALIDATION,
            managed_expression_name=ManagedExpressionsEnum.LESS_THAN,
            expression_form_data=form.data,
            component_id=target_question.id,
            value_dependent_question_id=reference_data_question.id,
        )

        with authenticated_grant_admin_client.session_transaction() as session:
            session["question"] = session_data.model_dump(mode="json")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=target_question.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{target_question.id}"
        )

        assert len(target_question.expressions) == 1
        expression = target_question.expressions[0]
        assert expression.type_ == ExpressionType.VALIDATION
        assert expression.managed_name == "Less than"
        assert expression.managed.referenced_question.id == target_question.id

        with authenticated_grant_admin_client.session_transaction() as session:
            assert "question" not in session


class TestEditQuestionValidation:
    def test_404(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for("deliver_grant_funding.edit_question_validation", grant_id=uuid.uuid4(), expression_id=uuid.uuid4())
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get(self, request, client_fixture, can_access, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        collection = factories.collection.create(grant=client.grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        question = factories.question.create(
            form=db_form,
            text="How many employees do you have?",
            name="employee count",
            data_type=QuestionDataType.NUMBER,
        )

        ValidationForm = build_managed_expression_form(
            ExpressionType.VALIDATION, ExpressionReference.from_question(question)
        )
        form = ValidationForm(
            data={"type": "Greater than", "greater_than_value": "10", "greater_than_inclusive": False}
        )
        expression = form.get_expression(ExpressionReference.from_question(question))
        interfaces.collections.add_component_validation(question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        db_session.refresh(question)
        expression_id = question.expressions[0].id

        response = client.get(
            url_for(
                "deliver_grant_funding.edit_question_validation",
                grant_id=client.grant.id,
                expression_id=expression_id,
            )
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")

            assert get_h1_text(soup) == "Edit validation"

            assert "Section" in soup.text
            assert "Organisation information" in soup.text

            assert "Question" in soup.text
            assert "How many employees do you have?" in soup.text

            greater_than_radio = soup.find("input", {"type": "radio", "value": "Greater than"})
            less_than_radio = soup.find("input", {"type": "radio", "value": "Less than"})
            between_radio = soup.find("input", {"type": "radio", "value": "Between"})
            assert greater_than_radio.get("checked") is not None
            assert less_than_radio.get("checked") is None
            assert between_radio.get("checked") is None

            min_value_input = soup.find("input", {"name": "greater_than_value"})
            assert min_value_input.get("value") == "10"

            assert page_has_button(soup, "Save validation")

            delete_link = page_has_link(soup, "Delete validation")
            assert delete_link is not None

    def test_get_with_delete_parameter(self, authenticated_grant_admin_client, factories, db_session):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        question = factories.question.create(
            form=db_form,
            text="How many employees do you have?",
            name="employee count",
            data_type=QuestionDataType.NUMBER,
        )

        ValidationForm = build_managed_expression_form(
            ExpressionType.VALIDATION, ExpressionReference.from_question(question)
        )
        form = ValidationForm(
            data={"type": "Greater than", "greater_than_value": "10", "greater_than_inclusive": False}
        )
        expression = form.get_expression(ExpressionReference.from_question(question))
        interfaces.collections.add_component_validation(question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        db_session.refresh(question)
        expression_id = question.expressions[0].id

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.edit_question_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=expression_id,
                delete="",
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_button(soup, "Yes, delete this validation")

    def test_post_update_validation(self, authenticated_grant_admin_client, factories, db_session):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        question = factories.question.create(
            form=db_form,
            text="How many employees do you have?",
            name="employee count",
            data_type=QuestionDataType.NUMBER,
        )

        ValidationForm = build_managed_expression_form(
            ExpressionType.VALIDATION, ExpressionReference.from_question(question)
        )
        original_form = ValidationForm(
            data={"type": "Greater than", "greater_than_value": "10", "greater_than_inclusive": False}
        )
        expression = original_form.get_expression(ExpressionReference.from_question(question))
        interfaces.collections.add_component_validation(question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        expression_id = question.expressions[0].id
        assert question.expressions[0].managed_name == "Greater than"

        UpdateForm = build_managed_expression_form(
            ExpressionType.VALIDATION, ExpressionReference.from_question(question), question.expressions[0]
        )
        form = UpdateForm(data={"type": "Less than", "less_than_value": "100", "less_than_inclusive": True})

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=expression_id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{question.id}"
        )

        assert len(question.expressions) == 1
        assert question.expressions[0].managed_name == "Less than"

    def test_post_update_validation_duplicate(self, authenticated_grant_admin_client, factories, db_session):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        question = factories.question.create(
            form=db_form,
            text="How many employees do you have?",
            name="employee count",
            data_type=QuestionDataType.NUMBER,
        )

        ValidationForm = build_managed_expression_form(
            ExpressionType.VALIDATION, ExpressionReference.from_question(question)
        )
        greater_than_form = ValidationForm(
            data={"type": "Greater than", "greater_than_value": "10", "greater_than_inclusive": False}
        )
        greater_than_expression = greater_than_form.get_expression(ExpressionReference.from_question(question))
        interfaces.collections.add_component_validation(
            question, interfaces.user.get_current_user(), greater_than_expression
        )

        less_than_form = ValidationForm(
            data={"type": "Less than", "less_than_value": "100", "less_than_inclusive": True}
        )
        less_than_expression = less_than_form.get_expression(ExpressionReference.from_question(question))
        interfaces.collections.add_component_validation(
            question, interfaces.user.get_current_user(), less_than_expression
        )
        db_session.commit()

        assert len(question.expressions) == 2
        greater_than_expression_id = None
        for expr in question.expressions:
            if expr.managed_name == "Greater than":
                greater_than_expression_id = expr.id
                break

        UpdateForm = build_managed_expression_form(
            ExpressionType.VALIDATION, ExpressionReference.from_question(question), question.expressions[0]
        )
        form = UpdateForm(data={"type": "Less than", "less_than_value": "100", "less_than_inclusive": True})

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=greater_than_expression_id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "validation already exists on the question" in soup.text

    def test_post_delete(self, authenticated_grant_admin_client, factories, db_session):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        question = factories.question.create(
            form=db_form,
            text="How many employees do you have?",
            name="employee count",
            data_type=QuestionDataType.NUMBER,
        )

        ValidationForm = build_managed_expression_form(
            ExpressionType.VALIDATION, ExpressionReference.from_question(question)
        )
        form = ValidationForm(
            data={"type": "Greater than", "greater_than_value": "10", "greater_than_inclusive": False}
        )
        expression = form.get_expression(ExpressionReference.from_question(question))
        interfaces.collections.add_component_validation(question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        expression_id = question.expressions[0].id
        assert len(question.expressions) == 1

        delete_form = GenericConfirmDeletionForm(data={"confirm_deletion": True})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=expression_id,
                delete="",
            ),
            data=delete_form.data,
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{question.id}"
        )

        assert len(question.expressions) == 0

    def test_post_to_remove_context_updates_session_and_reloads_page(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Cheese habits")

        referenced_question = factories.question.create(form=db_form, data_type=QuestionDataType.NUMBER)
        target_question = factories.question.create(form=db_form, data_type=QuestionDataType.NUMBER)

        expression = LessThan(
            subject_reference=ExpressionReference.from_question(target_question),
            maximum_value=None,
            maximum_expression=ExpressionReference.from_question(referenced_question),
            inclusive=True,
        )
        interfaces.collections.add_component_validation(target_question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        expression_id = target_question.expressions[0].id
        assert target_question.expressions[0].managed_name == "Less than"
        assert len(target_question.expressions) == 1

        ValidationForm = build_managed_expression_form(
            ExpressionType.VALIDATION,
            ExpressionReference.from_question(target_question),
            target_question.expressions[0],
        )
        form = ValidationForm(
            data={
                "type": "Less than",
                "less_than_value": None,
                "less_than_expression": ExpressionReference.from_question(referenced_question),
                "less_than_inclusive": False,
                "remove_context": "less_than_expression",
            }
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=expression_id,
            ),
            data=get_form_data(form, submit=""),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location.endswith(
            url_for(
                "deliver_grant_funding.edit_question_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=expression_id,
            )
        )
        assert len(target_question.expressions) == 1

        with authenticated_grant_admin_client.session_transaction() as session:
            assert session["question"]["field"] == ExpressionType.VALIDATION
            assert session["question"]["expression_form_data"]["less_than_expression"] == ""
            assert session["question"]["expression_form_data"]["less_than_inclusive"] is False

    def test_post_to_add_context_redirects_and_sets_up_session(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Cheese habits")

        target_question = factories.question.create(
            form=db_form,
            text="How much cheese do you eat a month?",
            name="quantity of cheese",
            data_type=QuestionDataType.NUMBER,
        )

        expression = LessThan(subject_reference=ExpressionReference.from_question(target_question), maximum_value=1000)
        interfaces.collections.add_component_validation(target_question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        expression_id = target_question.expressions[0].id
        assert target_question.expressions[0].managed_name == "Less than"
        assert len(target_question.expressions) == 1

        ValidationForm = build_managed_expression_form(
            ExpressionType.VALIDATION,
            ExpressionReference.from_question(target_question),
            target_question.expressions[0],
        )
        form = ValidationForm(
            data={
                "type": "Less than",
                "less_than_value": 1000,
                "less_than_expression": "",
                "less_than_inclusive": False,
                "add_context": "less_than_expression",
            }
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=expression_id,
            ),
            data=get_form_data(form, submit=""),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            "^/deliver/grant/[a-z0-9-]{36}/section/[a-z0-9-]{36}/add-context/select-source$"
        )
        assert len(target_question.expressions) == 1

        with authenticated_grant_admin_client.session_transaction() as session:
            assert session["question"]["field"] == ExpressionType.VALIDATION

    def test_post_from_add_context_success_cleans_that_bit_of_session(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Cheese habits")

        reference_data_question = factories.question.create(
            form=db_form,
            text="How much cheese do you buy a month?",
            name="total cheese bought",
            data_type=QuestionDataType.NUMBER,
        )

        target_question = factories.question.create(
            form=db_form,
            text="How much cheese do you eat a month?",
            name="quantity of cheese eaten",
            data_type=QuestionDataType.NUMBER,
        )

        expression = LessThan(subject_reference=ExpressionReference.from_question(target_question), maximum_value=1000)
        interfaces.collections.add_component_validation(target_question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        expression_id = target_question.expressions[0].id
        assert target_question.expressions[0].managed_name == "Less than"
        assert len(target_question.expressions) == 1

        ValidationForm = build_managed_expression_form(
            ExpressionType.VALIDATION,
            ExpressionReference.from_question(target_question),
            target_question.expressions[0],
        )
        form = ValidationForm(
            data={
                "type": "Less than",
                "less_than_value": 1000,
                "less_than_expression": ExpressionReference.from_question(reference_data_question),
                "less_than_inclusive": True,
            }
        )

        session_data = AddContextToExpressionsModel(
            field=ExpressionType.VALIDATION,
            managed_expression_name=ManagedExpressionsEnum.LESS_THAN,
            expression_form_data=form.data,
            component_id=target_question.id,
            value_dependent_question_id=reference_data_question.id,
            expression_id=expression_id,
        )

        with authenticated_grant_admin_client.session_transaction() as session:
            session["question"] = session_data.model_dump(mode="json")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=expression_id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{target_question.id}"
        )

        assert len(target_question.expressions) == 1
        expression = target_question.expressions[0]
        assert expression.type_ == ExpressionType.VALIDATION
        assert expression.managed_name == "Less than"
        assert expression.managed.referenced_question.id == target_question.id
        assert expression.statement == f"{target_question.safe_qid} <= {reference_data_question.safe_qid}"

        with authenticated_grant_admin_client.session_transaction() as session:
            assert "question" not in session


class TestManageGuidance:
    def test_404(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for("deliver_grant_funding.manage_guidance", grant_id=uuid.uuid4(), question_id=uuid.uuid4())
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get_access_control(self, request: FixtureRequest, client_fixture: str, can_access: bool, factories):
        client = request.getfixturevalue(client_fixture)
        question = factories.question.create(form__collection__grant=client.grant)

        response = client.get(
            url_for("deliver_grant_funding.manage_guidance", grant_id=client.grant.id, question_id=question.id)
        )

        if can_access:
            assert response.status_code == 200
        else:
            assert response.status_code == 403

    def test_get_add_guidance(self, authenticated_grant_admin_client, factories):
        question = factories.question.create(form__collection__grant=authenticated_grant_admin_client.grant)

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.manage_guidance",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=question.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Add guidance" in soup.text
        assert page_has_button(soup, "Save guidance")

    def test_get_edit_guidance(self, authenticated_grant_admin_client, factories):
        question = factories.question.create(
            form__collection__grant=authenticated_grant_admin_client.grant,
            guidance_heading="Existing heading",
            guidance_body="Existing body",
        )

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.manage_guidance",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=question.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Edit guidance" in soup.text
        assert page_has_button(soup, "Save guidance")

    def test_post_add_guidance(self, authenticated_grant_admin_client, factories, db_session):
        question = factories.question.create(form__collection__grant=authenticated_grant_admin_client.grant)

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.manage_guidance",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=question.id,
            ),
            data={
                "guidance_heading": "How to answer",
                "guidance_body": "Please provide detailed information",
                "submit": "y",
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            f"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{question.id}"
        )

        updated_question = db_session.get(Question, question.id)
        assert updated_question.guidance_heading == "How to answer"
        assert updated_question.guidance_body == "Please provide detailed information"

    def test_post_to_add_context_redirects_and_sets_up_session(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        question = factories.question.create(form__collection__grant=authenticated_grant_admin_client.grant)

        form = AddGuidanceForm(
            guidance_heading="How to answer",
            guidance_body="Please provide detailed information",
            add_context="guidance_body",
        )
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.manage_guidance",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=question.id,
            ),
            data=get_form_data(form, submit=""),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            r"^/deliver/grant/[a-z0-9-]{36}/section/[a-z0-9-]{36}/add-context/select-source$"
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            assert sess["question"]["field"] == "guidance"

    def test_post_update_guidance(self, authenticated_grant_admin_client, factories, db_session):
        question = factories.question.create(
            form__collection__grant=authenticated_grant_admin_client.grant,
            guidance_heading="Old heading",
            guidance_body="Old body",
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.manage_guidance",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=question.id,
            ),
            data={"guidance_heading": "Updated heading", "guidance_body": "Updated body", "submit": "y"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/question/[a-z0-9-]{36}$")

        updated_question = db_session.get(Question, question.id)
        assert updated_question.guidance_heading == "Updated heading"
        assert updated_question.guidance_body == "Updated body"

    def test_post_clear_guidance(self, authenticated_grant_admin_client, factories, db_session):
        question = factories.question.create(
            form__collection__grant=authenticated_grant_admin_client.grant,
            guidance_heading="Existing heading",
            guidance_body="Existing body",
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.manage_guidance",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=question.id,
            ),
            data={"guidance_heading": "", "guidance_body": "", "submit": "y"},
            follow_redirects=False,
        )

        assert response.status_code == 302

        updated_question = db_session.get(Question, question.id)
        assert updated_question.guidance_heading == ""
        assert updated_question.guidance_body == ""

    def test_post_guidance_with_heading_or_text_but_not_both(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        question = factories.question.create(
            form__collection__grant=authenticated_grant_admin_client.grant,
            guidance_heading="Existing heading",
            guidance_body="Existing body",
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.manage_guidance",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=question.id,
            ),
            data={"guidance_heading": "Existing heading", "guidance_body": "", "submit": "y"},
            follow_redirects=False,
        )

        assert response.status_code == 200

        soup = BeautifulSoup(response.text, "html.parser")
        assert page_has_error(soup, "Provide both a page heading and guidance text, or neither")

        updated_question = db_session.get(Question, question.id)
        assert updated_question.guidance_heading == "Existing heading"
        assert updated_question.guidance_body == "Existing body"

    def test_get_edit_guidance_groups(self, authenticated_grant_admin_client, factories, db_session):
        group = factories.group.create(
            form__collection__grant=authenticated_grant_admin_client.grant,
            guidance_heading="Existing heading",
            guidance_body="Existing body",
        )

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.manage_guidance",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=group.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Edit guidance" in soup.text
        assert "Existing body" in soup.text

    def test_post_update_guidance_groups(self, authenticated_grant_admin_client, factories, db_session):
        group = factories.group.create(
            form__collection__grant=authenticated_grant_admin_client.grant,
            guidance_heading="Old heading",
            guidance_body="Old body",
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.manage_guidance",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=group.id,
            ),
            data={"guidance_heading": "Updated heading", "guidance_body": "Updated body", "submit": "y"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/group/[a-z0-9-]{36}/questions$")

        updated_group = db_session.get(Group, group.id)
        assert updated_group.guidance_heading == "Updated heading"
        assert updated_group.guidance_body == "Updated body"


class TestManageAddAnotherGuidance:
    def test_404(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for("deliver_grant_funding.manage_add_another_guidance", grant_id=uuid.uuid4(), group_id=uuid.uuid4())
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get_access_control(self, request: FixtureRequest, client_fixture: str, can_access: bool, factories):
        client = request.getfixturevalue(client_fixture)
        group = factories.group.create(form__collection__grant=client.grant)

        response = client.get(
            url_for("deliver_grant_funding.manage_add_another_guidance", grant_id=client.grant.id, group_id=group.id)
        )

        if can_access:
            assert response.status_code == 200
        else:
            assert response.status_code == 403

    def test_get_add_guidance(self, authenticated_grant_admin_client, factories):
        group = factories.group.create(form__collection__grant=authenticated_grant_admin_client.grant)

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.manage_add_another_guidance",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Add another summary page guidance" in soup.text
        assert page_has_button(soup, "Save guidance")

    def test_get_edit_guidance(self, authenticated_grant_admin_client, factories):
        group = factories.question.create(
            form__collection__grant=authenticated_grant_admin_client.grant, add_another_guidance_body="Existing body"
        )

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.manage_add_another_guidance",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Existing body" in soup.text
        assert "Edit add another summary page guidance" in soup.text
        assert page_has_button(soup, "Save guidance")

    def test_post_add_guidance(self, authenticated_grant_admin_client, factories, db_session):
        group = factories.group.create(form__collection__grant=authenticated_grant_admin_client.grant)

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.manage_add_another_guidance",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
            ),
            data={
                "guidance_body": "Please provide detailed information",
                "submit": "y",
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            f"/deliver/grant/{authenticated_grant_admin_client.grant.id}/group/{group.id}/questions"
        )

        updated_group = db_session.get(Group, group.id)
        assert updated_group.add_another_guidance_body == "Please provide detailed information"

    def test_post_to_add_context_redirects_and_sets_up_session(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        group = factories.group.create(form__collection__grant=authenticated_grant_admin_client.grant)

        form = AddGuidanceForm(
            guidance_body="Please provide detailed information",
            add_context="guidance_body",
        )
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.manage_add_another_guidance",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
            ),
            data=get_form_data(form, submit=""),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            r"^/deliver/grant/[a-z0-9-]{36}/section/[a-z0-9-]{36}/add-context/select-source$"
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            assert sess["question"]["field"] == "guidance"
            assert sess["question"]["is_add_another_guidance"] is True

    def test_post_update_guidance(self, authenticated_grant_admin_client, factories, db_session):
        group = factories.group.create(
            form__collection__grant=authenticated_grant_admin_client.grant,
            add_another_guidance_body=InterpolationStatement("Old body"),
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.manage_add_another_guidance",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
            ),
            data={"guidance_body": "Updated body", "submit": "y"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/group/[a-z0-9-]{36}/questions$")

        updated_group = db_session.get(Group, group.id)
        assert updated_group.add_another_guidance_body == "Updated body"


class TestListSubmissions:
    def test_404(self, authenticated_grant_member_client):
        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.list_submissions",
                grant_id=uuid.uuid4(),
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=uuid.uuid4(),
                submission_mode=SubmissionModeEnum.TEST,
            )
        )
        assert response.status_code == 404

    def test_no_submissions(self, authenticated_grant_member_client, factories, db_session):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant, name="Test Report")

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.list_submissions",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                submission_mode=SubmissionModeEnum.TEST,
            )
        )
        assert response.status_code == 200
        assert "No submissions found for this report" in response.text

    def test_based_on_submission_mode(self, authenticated_grant_member_client, factories, db_session):
        collection = factories.collection.create(
            grant=authenticated_grant_member_client.grant,
            name="Test Report",
            create_completed_submissions_each_question_type__test=1,
        )
        test_grant_recipient = factories.grant_recipient.create(
            grant=authenticated_grant_member_client.grant,
            mode=GrantRecipientModeEnum.TEST,
            organisation__name="Test Organisation Ltd",
        )
        live_grant_recipient = factories.grant_recipient.create(
            grant=authenticated_grant_member_client.grant,
            organisation__name="Live Organisation Ltd",
        )
        factories.submission.create(
            collection=collection,
            mode=SubmissionModeEnum.TEST,
            grant_recipient=test_grant_recipient,
            created_by__email="submitter-test@recipient.org",
            status=SubmissionStatusEnum.NOT_STARTED,
        )
        factories.submission.create(
            collection=collection,
            mode=SubmissionModeEnum.LIVE,
            grant_recipient=live_grant_recipient,
            created_by__email="submitter-live@recipient.org",
            status=SubmissionStatusEnum.NOT_STARTED,
        )

        test_response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.list_submissions",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                submission_mode=SubmissionModeEnum.TEST,
            )
        )
        live_response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.list_submissions",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                submission_mode=SubmissionModeEnum.LIVE,
            )
        )
        test_soup = BeautifulSoup(test_response.data, "html.parser")
        live_soup = BeautifulSoup(live_response.data, "html.parser")
        assert test_response.status_code == 200
        assert live_response.status_code == 200

        test_recipient_link = page_has_link(test_soup, "Test Organisation Ltd")
        live_recipient_link = page_has_link(live_soup, "Live Organisation Ltd")
        assert test_recipient_link.get("href") == AnyStringMatching(
            "/deliver/grant/[a-z0-9-]{36}/submission/[a-z0-9-]{36}"
        )
        assert live_recipient_link.get("href") == AnyStringMatching(
            "/deliver/grant/[a-z0-9-]{36}/submission/[a-z0-9-]{36}"
        )

        test_submission_tags = test_soup.select(".govuk-tag")
        live_submission_tags = live_soup.select(".govuk-tag")
        assert {tag.text.strip() for tag in test_submission_tags} == {"Not started"}
        assert {tag.text.strip() for tag in live_submission_tags} == {"Not started"}

    def test_live_mode_shows_all_grant_recipients_including_those_without_submissions(
        self, authenticated_grant_member_client, factories, db_session
    ):
        collection = factories.collection.create(
            grant=authenticated_grant_member_client.grant,
            name="Test Report",
        )
        grant_recipient_with_submission = factories.grant_recipient.create(
            grant=authenticated_grant_member_client.grant, organisation__name="Organisation With Submission"
        )
        factories.grant_recipient.create(
            grant=authenticated_grant_member_client.grant, organisation__name="Organisation Without Submission"
        )
        factories.submission.create(
            collection=collection,
            mode=SubmissionModeEnum.LIVE,
            grant_recipient=grant_recipient_with_submission,
        )

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.list_submissions",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                submission_mode=SubmissionModeEnum.LIVE,
            )
        )
        soup = BeautifulSoup(response.data, "html.parser")
        assert response.status_code == 200

        assert "Organisation With Submission" in response.text
        assert "Organisation Without Submission" in response.text

        link_with_submission = page_has_link(soup, "Organisation With Submission")
        assert link_with_submission is not None
        assert link_with_submission.get("href") == AnyStringMatching(
            "/deliver/grant/[a-z0-9-]{36}/submission/[a-z0-9-]{36}"
        )

        link_without_submission = page_has_link(soup, "Organisation Without Submission")
        assert link_without_submission is None

        submission_tags = soup.select(".govuk-tag")
        tag_texts = {tag.text.strip() for tag in submission_tags}
        assert "Not started" in tag_texts

    def test_live_mode_shows_overdue_status_when_submission_period_passed(
        self, authenticated_grant_member_client, grant_recipient, factories, db_session
    ):
        collection = factories.collection.create(
            grant=authenticated_grant_member_client.grant,
            submission_period_end_date=date(2020, 1, 1),  # past date
            name="Test Report",
        )
        factories.submission.create(
            collection=collection,
            mode=SubmissionModeEnum.LIVE,
            grant_recipient=grant_recipient,
        )

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.list_submissions",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                submission_mode=SubmissionModeEnum.LIVE,
            )
        )

        soup = BeautifulSoup(response.data, "html.parser")
        assert response.status_code == 200

        submission_tags = soup.select(".govuk-tag")
        tag_texts = {tag.text.strip() for tag in submission_tags}
        assert "Ready to submit (Overdue)" in tag_texts

    def test_live_mode_shows_not_started_overdue_status_for_open_collections_without_submissions(
        self, authenticated_grant_member_client, factories
    ):
        collection = factories.collection.create(
            allow_multiple_submissions=True,
            grant=authenticated_grant_member_client.grant,
            submission_period_end_date=date(2020, 1, 1),  # past date
            status=CollectionStatusEnum.OPEN,
            name="Test Report",
        )

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.list_submissions",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                submission_mode=SubmissionModeEnum.LIVE,
            )
        )

        soup = BeautifulSoup(response.data, "html.parser")
        assert response.status_code == 200

        submission_tags = soup.select(".govuk-tag")
        tag_texts = {tag.text.strip() for tag in submission_tags}
        assert len(tag_texts) == 1
        assert "Not started (Overdue)" in tag_texts

    def test_live_mode_wont_show_not_submitted_overdue_status_for_closed_collections_without_submissions(
        self, authenticated_grant_member_client, factories
    ):
        collection = factories.collection.create(
            allow_multiple_submissions=True,
            grant=authenticated_grant_member_client.grant,
            name="Test Report",
            submission_period_end_date=date(2020, 1, 1),  # past date
            status=CollectionStatusEnum.CLOSED,
        )

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.list_submissions",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                submission_mode=SubmissionModeEnum.LIVE,
            )
        )

        soup = BeautifulSoup(response.data, "html.parser")
        assert response.status_code == 200

        submission_tags = soup.select(".govuk-tag")
        tag_texts = {tag.text.strip() for tag in submission_tags}
        assert len(tag_texts) == 1
        assert "Not submitted" in tag_texts

    def test_closed_collection_shows_not_submitted_for_grant_recipients_without_submissions(
        self, authenticated_grant_member_client, factories, db_session
    ):
        collection = factories.collection.create(
            grant=authenticated_grant_member_client.grant,
            name="Closed Report",
            status=CollectionStatusEnum.CLOSED,
            submission_period_end_date=datetime.date(2026, 1, 1),
        )
        factories.grant_recipient.create(
            grant=authenticated_grant_member_client.grant, organisation__name="Organisation Without Submission"
        )

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.list_submissions",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                submission_mode=SubmissionModeEnum.LIVE,
            )
        )
        soup = BeautifulSoup(response.data, "html.parser")
        assert response.status_code == 200

        submission_tags = soup.select(".govuk-tag")
        tag_texts = {tag.text.strip() for tag in submission_tags}
        assert "Not submitted" in tag_texts

    def test_test_mode_shows_reset_all_link(self, authenticated_grant_member_client, factories, db_session):
        collection = factories.collection.create(
            grant=authenticated_grant_member_client.grant,
            name="Test Report",
            create_submissions__test=1,
        )

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.list_submissions",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                submission_mode=SubmissionModeEnum.TEST,
            )
        )
        soup = BeautifulSoup(response.data, "html.parser")

        assert response.status_code == 200
        assert page_has_link(soup, "Reset all test submissions")

    def test_live_mode_does_not_show_reset_all_link(self, authenticated_grant_member_client, factories, db_session):
        collection = factories.collection.create(
            grant=authenticated_grant_member_client.grant,
            name="Test Report",
            create_submissions__live=1,
        )

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.list_submissions",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=collection.type,
                collection_id=collection.id,
                submission_mode=SubmissionModeEnum.LIVE,
            )
        )
        soup = BeautifulSoup(response.data, "html.parser")

        assert response.status_code == 200
        assert not page_has_link(soup, "Reset all test submissions")

    def test_delete_all_query_param_shows_confirmation_banner(
        self, authenticated_grant_member_client, factories, db_session
    ):
        collection = factories.collection.create(
            grant=authenticated_grant_member_client.grant,
            name="Test Report",
            create_submissions__test=1,
        )

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.list_submissions",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                submission_mode=SubmissionModeEnum.TEST,
                delete_all=True,
            )
        )

        assert response.status_code == 200
        assert "Are you sure you want to reset all test submissions?" in response.text

    def test_post_resets_all_test_submissions(
        self, authenticated_grant_member_client, factories, db_session, mock_s3_service_calls
    ):
        collection = factories.collection.create(
            grant=authenticated_grant_member_client.grant,
            name="Test Report",
            create_submissions__test=3,
        )
        test_submission_ids = [s.id for s in collection.test_submissions]

        for submission in collection.test_submissions:
            factories.submission_event.create(submission=submission, created_by=submission.created_by)

        form = GenericConfirmDeletionForm(data={"confirm_deletion": True})
        response = authenticated_grant_member_client.post(
            url_for(
                "deliver_grant_funding.list_submissions",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                submission_mode=SubmissionModeEnum.TEST,
                delete_all=True,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302

        remaining_submissions = db_session.query(Submission).where(Submission.id.in_(test_submission_ids)).all()
        remaining_events = (
            db_session.query(SubmissionEvent).where(SubmissionEvent.submission_id.in_(test_submission_ids)).all()
        )
        assert len(remaining_submissions) == 0
        assert len(remaining_events) == 0
        assert len(mock_s3_service_calls.delete_prefix_calls) == 1
        assert mock_s3_service_calls.delete_prefix_calls[0].args[0] == f"uploaded-submission-files/test/{collection.id}"

    def test_post_redirects_with_flash_message(
        self, authenticated_grant_member_client, factories, db_session, mock_s3_service_calls
    ):
        collection = factories.collection.create(
            grant=authenticated_grant_member_client.grant,
            name="Test Report",
            create_submissions__test=1,
        )

        form = GenericConfirmDeletionForm(data={"confirm_deletion": True})
        response = authenticated_grant_member_client.post(
            url_for(
                "deliver_grant_funding.list_submissions",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                submission_mode=SubmissionModeEnum.TEST,
                delete_all=True,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "deliver_grant_funding.list_submissions",
            grant_id=authenticated_grant_member_client.grant.id,
            collection_type=CollectionType.MONITORING_REPORT,
            collection_id=collection.id,
            submission_mode=SubmissionModeEnum.TEST,
        )
        flashes = get_test_flashes(authenticated_grant_member_client, FlashMessageType.TEST_SUBMISSIONS_RESET)
        assert flashes == ["All test submissions reset"]
        assert len(mock_s3_service_calls.delete_prefix_calls) == 1

    def test_post_on_live_view_400s_and_does_not_delete_anything(
        self, authenticated_grant_member_client, factories, db_session, mock_s3_service_calls
    ):
        collection = factories.collection.create(
            grant=authenticated_grant_member_client.grant,
            name="Test Report",
            create_submissions__test=2,
            create_submissions__live=2,
        )
        live_submission_ids = [s.id for s in collection.live_submissions]
        test_submission_ids = [s.id for s in collection.test_submissions]

        form = GenericConfirmDeletionForm(data={"confirm_deletion": True})
        response = authenticated_grant_member_client.post(
            url_for(
                "deliver_grant_funding.list_submissions",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                submission_mode=SubmissionModeEnum.LIVE,
                delete_all=True,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 400

        remaining_live = db_session.query(Submission).where(Submission.id.in_(live_submission_ids)).all()
        remaining_test = db_session.query(Submission).where(Submission.id.in_(test_submission_ids)).all()

        assert len(remaining_live) == 2
        assert len(remaining_test) == 2

        assert len(mock_s3_service_calls.all_calls) == 0


class TestListSubmissionsMultipleSubmissions:
    def test_multi_submission_table_shows_submission_submission_name(
        self, authenticated_grant_member_client, factories, db_session
    ):
        question = factories.question.create(
            form__collection__grant=authenticated_grant_member_client.grant,
            form__collection__allow_multiple_submissions=True,
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            name="project name",
        )
        collection = question.form.collection
        collection.submission_name_question_id = question.id
        db_session.commit()
        grant_recipient = factories.grant_recipient.create(
            grant=authenticated_grant_member_client.grant, organisation__name="Acme Corp"
        )
        factories.submission.create(
            collection=collection,
            mode=SubmissionModeEnum.LIVE,
            grant_recipient=grant_recipient,
            answers=[FactoryAnswer(question, TextSingleLineAnswer("Alpha Project"))],
        )
        factories.submission.create(
            collection=collection,
            mode=SubmissionModeEnum.LIVE,
            grant_recipient=grant_recipient,
            answers=[FactoryAnswer(question, TextSingleLineAnswer("Beta Project"))],
        )

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.list_submissions",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                submission_mode=SubmissionModeEnum.LIVE,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_link(soup, "Alpha Project") is not None
        assert page_has_link(soup, "Beta Project") is not None
        assert "Acme Corp" in soup.text

    def test_multi_submission_table_uses_question_name_as_column_header(
        self, authenticated_grant_member_client, factories, db_session
    ):
        question = factories.question.create(
            form__collection__grant=authenticated_grant_member_client.grant,
            form__collection__allow_multiple_submissions=True,
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            name="project name",
        )
        collection = question.form.collection
        collection.submission_name_question_id = question.id
        db_session.commit()

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.list_submissions",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                submission_mode=SubmissionModeEnum.LIVE,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        table_headers = [th.text.strip() for th in soup.select("th")]
        assert "Project name" in table_headers
        assert "Grant recipient" in table_headers

    def test_multi_submission_no_grant_recipients_shows_empty_message(
        self, authenticated_grant_member_client_no_grant_recipients, factories, db_session
    ):
        collection = factories.collection.create(
            grant=authenticated_grant_member_client_no_grant_recipients.grant,
            allow_multiple_submissions=True,
        )

        response = authenticated_grant_member_client_no_grant_recipients.get(
            url_for(
                "deliver_grant_funding.list_submissions",
                grant_id=authenticated_grant_member_client_no_grant_recipients.grant.id,
                collection_type=collection.type,
                collection_id=collection.id,
                submission_mode=SubmissionModeEnum.LIVE,
            )
        )

        assert response.status_code == 200
        assert "No submissions found for this report" in response.text

    def test_multi_submission_table_shows_no_submission_for_recipients_without_submissions(
        self, authenticated_grant_member_client, factories, db_session
    ):
        collection = factories.collection.create(
            grant=authenticated_grant_member_client.grant,
            allow_multiple_submissions=True,
        )
        factories.grant_recipient.create(
            grant=authenticated_grant_member_client.grant, organisation__name="Organisation Without Submission"
        )

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.list_submissions",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                submission_mode=SubmissionModeEnum.LIVE,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Organisation Without Submission" in soup.text
        assert "No submission" in soup.text
        assert page_has_link(soup, "No submission") is None
        submission_tags = soup.select(".govuk-tag")
        assert {tag.text.strip() for tag in submission_tags} == {"Not started"}


class TestExportCollectionSubmissions:
    def test_404(self, authenticated_grant_member_client, factories, db_session):
        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.export_collection_submissions",
                grant_id=uuid.uuid4(),
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=uuid.uuid4(),
                submission_mode=SubmissionModeEnum.TEST,
                export_format="csv",
            )
        )
        assert response.status_code == 404

    def test_unknown_export_type(self, authenticated_grant_member_client, factories, db_session):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant, name="Test Report")
        factories.submission.create(
            collection=collection, mode=SubmissionModeEnum.TEST, created_by__email="submitter-test@recipient.org"
        )
        factories.submission.create(
            collection=collection, mode=SubmissionModeEnum.LIVE, created_by__email="submitter-live@recipient.org"
        )
        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.export_collection_submissions",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                submission_mode=SubmissionModeEnum.TEST,
                export_format="zip",
            )
        )
        assert response.status_code == 400

    def test_csv_download(self, authenticated_grant_member_client, factories, db_session):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant, name="Test Report")
        factories.submission.create(
            collection=collection, mode=SubmissionModeEnum.TEST, created_by__email="submitter-test@recipient.org"
        )
        factories.submission.create(
            collection=collection, mode=SubmissionModeEnum.LIVE, created_by__email="submitter-live@recipient.org"
        )
        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.export_collection_submissions",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                submission_mode=SubmissionModeEnum.TEST,
                export_format="csv",
            )
        )
        assert response.status_code == 200
        assert response.mimetype == "text/csv"
        # relying on testing for the internal implementation that we're generating a good CSV
        assert response.content_length > 0
        assert len(response.text.splitlines()) == 2  # Header + 1 submission

        # Check that it begins with the UTF-8-BOM, which provides better signalling to MS Excel to open in UTF-8 mode.
        assert response.data[:3] == bytes.fromhex("efbbbf")

    def test_json_download(self, authenticated_grant_member_client, factories, db_session):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant, name="Test Report")
        factories.submission.create(
            collection=collection, mode=SubmissionModeEnum.TEST, created_by__email="submitter-test@recipient.org"
        )
        factories.submission.create(
            collection=collection, mode=SubmissionModeEnum.LIVE, created_by__email="submitter-live@recipient.org"
        )
        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.export_collection_submissions",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                submission_mode=SubmissionModeEnum.TEST,
                export_format="json",
            )
        )
        assert response.status_code == 200
        assert response.mimetype == "application/json"

        assert response.content_length > 0
        assert len(response.json["submissions"]) == 1

    def test_csv_includes_submission_name_for_multiple_submissions(
        self, authenticated_grant_member_client, factories, db_session
    ):
        question = factories.question.create(
            form__collection__grant=authenticated_grant_member_client.grant,
            form__collection__allow_multiple_submissions=True,
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            name="project name",
        )
        collection = question.form.collection
        collection.submission_name_question_id = question.id
        db_session.commit()

        grant_recipient = factories.grant_recipient.create(grant=authenticated_grant_member_client.grant)
        factories.submission.create(
            collection=collection,
            mode=SubmissionModeEnum.LIVE,
            grant_recipient=grant_recipient,
            answers=[FactoryAnswer(question, TextSingleLineAnswer("Alpha Project"))],
        )
        factories.submission.create(
            collection=collection,
            mode=SubmissionModeEnum.LIVE,
            grant_recipient=grant_recipient,
            answers=[FactoryAnswer(question, TextSingleLineAnswer("Beta Project"))],
        )

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.export_collection_submissions",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                submission_mode=SubmissionModeEnum.LIVE,
                export_format="csv",
            )
        )

        assert response.status_code == 200
        lines = response.text.splitlines()
        headers = lines[0].split(",")
        assert "Submission name" in headers
        assert len(lines) == 3
        assert "Alpha Project" in response.text
        assert "Beta Project" in response.text

    def test_json_includes_name_for_multiple_submissions(
        self, authenticated_grant_member_client, factories, db_session
    ):
        question = factories.question.create(
            form__collection__grant=authenticated_grant_member_client.grant,
            form__collection__allow_multiple_submissions=True,
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            name="project name",
        )
        collection = question.form.collection
        collection.submission_name_question_id = question.id
        db_session.commit()

        grant_recipient = factories.grant_recipient.create(grant=authenticated_grant_member_client.grant)
        factories.submission.create(
            collection=collection,
            mode=SubmissionModeEnum.LIVE,
            grant_recipient=grant_recipient,
            answers=[FactoryAnswer(question, TextSingleLineAnswer("Alpha Project"))],
        )
        factories.submission.create(
            collection=collection,
            mode=SubmissionModeEnum.LIVE,
            grant_recipient=grant_recipient,
            answers=[FactoryAnswer(question, TextSingleLineAnswer("Beta Project"))],
        )

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.export_collection_submissions",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                submission_mode=SubmissionModeEnum.LIVE,
                export_format="json",
            )
        )

        assert response.status_code == 200
        submissions = response.json["submissions"]
        assert len(submissions) == 2
        names = {s["name"] for s in submissions}
        assert names == {"Alpha Project", "Beta Project"}


class TestViewSubmission:
    def test_404(self, authenticated_grant_member_client):
        response = authenticated_grant_member_client.get(
            url_for("deliver_grant_funding.view_submission", grant_id=uuid.uuid4(), submission_id=uuid.uuid4())
        )
        assert response.status_code == 404

    def test_forms_and_questions_and_answers_displayed(self, authenticated_grant_member_client, factories, db_session):
        factories.data_source_item.reset_sequence()
        collection = factories.collection.create(
            grant=authenticated_grant_member_client.grant,
            name="Test Report",
            create_completed_submissions_each_question_type__test=1,
            create_completed_submissions_each_question_type__use_random_data=False,
        )

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.view_submission",
                grant_id=authenticated_grant_member_client.grant.id,
                submission_id=collection.test_submissions[0].id,
            )
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")

        assert "Export test form" in soup.text
        assert len(collection.forms[0].cached_questions) == 11, "If more questions added, check+update this test"

        assert "What is your name?" in soup.text
        assert "test name" in soup.text

        assert "What is your quest?" in soup.text
        assert "Line 1" in soup.text
        assert "line2" in soup.text
        assert "line 3" in soup.text

        assert "What is the airspeed velocity of an unladen swallow?" in soup.text
        assert "123" in soup.text

        assert "How much is that doggy in the window?" in soup.text
        assert "456.78" in soup.text

        assert "What is the best option?" in soup.text
        assert "Option 0" in soup.text

        assert "Do you like cheese?" in soup.text
        assert "Yes" in soup.text

        assert "What is your email address?" in soup.text
        assert "test@email.com" in soup.text

        assert "What is your website address?" in soup.text
        assert (
            "https://www.gov.uk/government/organisations/ministry-of-housing-communities-local-government" in soup.text
        )
        assert "What are your favourite cheeses?" in soup.text
        assert "Cheddar" in soup.text
        assert "Stilton" in soup.text

        assert "When did you last buy some cheese" in soup.text
        assert "1 January 2025" in soup.text

        assert "Upload a supporting document" in soup.text
        assert "test-document.pdf" in soup.text

    # TODO: combine into above test when feature flag removed
    def test_ff_metadata_and_tab_panels_are_displayed(self, authenticated_grant_member_client, submission_submitted):
        grant = authenticated_grant_member_client.grant
        grant.allow_pre_award = True

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.view_submission",
                grant_id=grant.id,
                submission_id=submission_submitted.id,
            )
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")

        assert get_h1_text(soup) == "Submission"

        assert "Organisation" in soup.text
        assert "Grant name" in soup.text
        assert "Report name" in soup.text
        assert "Submitted by" in soup.text

        tab_labels = [tab.text.strip() for tab in soup.select(".govuk-tabs__tab")]

        assert "Submission responses" in tab_labels
        assert "Timeline" in tab_labels

        form_responses_panel = soup.select_one("#submission-responses")
        assert form_responses_panel.find("h2", class_="govuk-heading-m").text.strip() == "Submission responses"

        timeline_panel = soup.select_one("#timeline")
        assert timeline_panel.find("h2", class_="govuk-heading-m").text.strip() == "Timeline"

    @pytest.mark.parametrize(
        "client_fixture, submission_fixture, can_see_button",
        [
            ("authenticated_org_member_client", "submission_submitted", False),
            ("authenticated_grant_member_client", "submission_in_progress", False),
            ("authenticated_grant_member_client", "submission_submitted", True),
        ],
    )
    def test_can_see_request_or_allow_changes_button(
        self, request, client_fixture, grant_recipient, submission_fixture, can_see_button, factories
    ):
        client = request.getfixturevalue(client_fixture)
        submission = request.getfixturevalue(submission_fixture)
        grant = grant_recipient.grant
        grant.allow_pre_award = True

        response = client.get(
            url_for(
                "deliver_grant_funding.view_submission",
                grant_id=grant.id,
                submission_id=submission.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        button = page_has_link(soup, "Request or allow changes")
        if can_see_button:
            assert button is not None
            assert button["href"] == url_for(
                "deliver_grant_funding.request_or_allow_changes",
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
            )
        else:
            assert button is None

    def test_can_see_download_pdf_button(
        self, authenticated_grant_member_client, grant_recipient, submission_submitted
    ):
        client = authenticated_grant_member_client
        grant = grant_recipient.grant
        grant.allow_pre_award = True

        response = client.get(
            url_for(
                "deliver_grant_funding.view_submission",
                grant_id=grant.id,
                submission_id=submission_submitted.id,
            )
        )

        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        button = page_has_link(soup, "Download responses as PDF")

        assert button["href"] == url_for(
            "deliver_grant_funding.export_submission_pdf",
            grant_id=grant.id,
            submission_id=submission_submitted.id,
        )

    def test_get_view_submission_displays_questions_with_add_another(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(
            grant=authenticated_grant_admin_client.grant,
            create_completed_submissions_add_another_nested_group__test=1,
            create_completed_submissions_add_another_nested_group__use_random_data=False,
        )
        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.view_submission",
                grant_id=authenticated_grant_admin_client.grant.id,
                submission_id=collection.test_submissions[0].id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")

        assert "There are 5 answers" in soup.text

        assert (
            len(
                [
                    key
                    for key in soup.find_all("dt", {"class": "govuk-summary-list__key"})
                    if key.text.strip() == "What is the name of this person?"
                ]
            )
            == 5
        )
        assert (
            len(
                [
                    key
                    for key in soup.find_all("dt", {"class": "govuk-summary-list__key"})
                    if key.text.strip() == "What is this person's email address?"
                ]
            )
            == 5
        )

    def test_view_submission_add_another_interpolates_with_display_value(
        self, authenticated_grant_admin_client, factories
    ):
        grant = authenticated_grant_admin_client.grant
        group = factories.group.create(
            form__collection__grant=grant,
            add_another=True,
        )
        amount_question = factories.question.create(
            text="How much funding was received?",
            data_type=QuestionDataType.NUMBER,
            presentation_options=QuestionPresentationOptions(prefix="£"),
            parent=group,
            form=group.form,
        )
        detail_question = factories.question.create(
            text=f"How was the (({amount_question.safe_qid})) spent?",
            parent=group,
            form=group.form,
        )

        submission = factories.submission.create(
            collection=group.form.collection,
            mode=SubmissionModeEnum.TEST,
            answers=[
                FactoryAnswer(amount_question, IntegerAnswer(value=50_000, prefix="£"), add_another_index=0),
                FactoryAnswer(detail_question, TextSingleLineAnswer("On staffing costs"), add_another_index=0),
            ],
        )

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.view_submission",
                grant_id=grant.id,
                submission_id=submission.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        question_keys = [dt.text.strip() for dt in soup.find_all("dt", {"class": "govuk-summary-list__key"})]
        assert "How was the £50,000 spent?" in question_keys

    def test_post_view_submission_resets_test_submission(
        self, authenticated_grant_member_client, factories, db_session, mock_s3_service_calls
    ):
        collection = factories.collection.create(
            grant=authenticated_grant_member_client.grant,
            name="Test Report",
            create_completed_submissions_each_question_type__test=1,
        )
        test_submission = collection.test_submissions[0]
        test_submission_id = test_submission.id

        factories.submission_event.create(
            related_entity_id=test_submission.collection.forms[0].id,
            event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED,
            submission=test_submission,
            created_by=test_submission.created_by,
        )

        form = GenericConfirmDeletionForm(data={"confirm_deletion": True})
        response = authenticated_grant_member_client.post(
            url_for(
                "deliver_grant_funding.view_submission",
                grant_id=authenticated_grant_member_client.grant.id,
                submission_id=test_submission_id,
                delete=True,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "deliver_grant_funding.list_submissions",
            grant_id=authenticated_grant_member_client.grant.id,
            collection_type=CollectionType.MONITORING_REPORT,
            collection_id=collection.id,
            submission_mode=SubmissionModeEnum.TEST,
        )

        submissions_from_db = db_session.query(Submission).where(Submission.id == test_submission_id).all()
        events_from_db = (
            db_session.query(SubmissionEvent).where(SubmissionEvent.submission_id == test_submission_id).all()
        )

        assert len(submissions_from_db) == 0
        assert len(events_from_db) == 0
        assert len(mock_s3_service_calls.delete_prefix_calls) == 1
        assert mock_s3_service_calls.delete_prefix_calls[0].args[0] == (
            f"uploaded-submission-files/test/{test_submission.collection.id}/{test_submission_id}"
        )

    @pytest.mark.parametrize(
        "submission_mode, should_show_reset_link",
        [
            (SubmissionModeEnum.TEST, True),
            (SubmissionModeEnum.PREVIEW, False),
            (SubmissionModeEnum.LIVE, False),
        ],
    )
    def test_get_view_submission_only_shows_manage_test_section_for_test(
        self, authenticated_grant_member_client, factories, submission_mode, should_show_reset_link
    ):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant, name="Test collection")
        submission = factories.submission.create(
            collection=collection,
            mode=submission_mode,
        )

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.view_submission",
                grant_id=authenticated_grant_member_client.grant.id,
                submission_id=submission.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")

        reset_link = page_has_link(soup, "Reset this submission")

        if should_show_reset_link:
            assert reset_link is not None, "Reset this submission link should be present for TEST mode"
        else:
            assert reset_link is None, (
                f"Reset this submission link should NOT be present for {submission_mode.value} mode"
            )

    @pytest.mark.parametrize(
        "client_fixture, submission_fixture, can_see_reopen_button",
        [
            ("authenticated_org_member_client", "submission_submitted", False),
            ("authenticated_grant_member_client", "submission_in_progress", False),
            ("authenticated_grant_member_client", "submission_submitted", True),
        ],
    )
    def test_can_see_reopen_submission_button(
        self, request, client_fixture, grant_recipient, submission_fixture, can_see_reopen_button, factories
    ):

        client = request.getfixturevalue(client_fixture)
        submission = request.getfixturevalue(submission_fixture)
        response = client.get(
            url_for(
                "deliver_grant_funding.view_submission",
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        reopen_button = page_has_link(soup, "Reopen submission")
        if can_see_reopen_button:
            assert reopen_button is not None
        else:
            assert reopen_button is None

    def test_shows_changed_tag_and_original_response_for_resubmitted_answers(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        question = factories.question.create(form__collection__grant=authenticated_grant_admin_client.grant)
        submission = factories.submission.create(
            collection=question.form.collection,
            answers=[FactoryAnswer(question, TextSingleLineAnswer("original answer"))],
        )
        previous_data = deepcopy(submission.data_manager.data)

        factories.submission_event.create(
            submission=submission,
            event_type=SubmissionEventType.SUBMISSION_CHANGES_REQUESTED,
            data={
                "changes_requested_reason": "Please fix",
                "submission_data": previous_data,
                "section_ids": [],
            },
        )
        submission.data_manager.set(question, TextSingleLineAnswer("updated answer"))
        submission.status = SubmissionStatusEnum.SUBMITTED
        db_session.flush()

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.view_submission",
                grant_id=authenticated_grant_admin_client.grant.id,
                submission_id=submission.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Changed" in soup.text
        assert "Original response" in soup.text
        assert "original answer" in soup.text
        assert "updated answer" in soup.text

    def test_wont_show_diff_for_ready_to_submit_with_changes_made(
        self, authenticated_grant_member_client, submission_ready_to_submit_with_changes_made
    ):
        submission = submission_ready_to_submit_with_changes_made
        helper = SubmissionHelper(submission)
        form = submission.collection.forms[0]

        assert submission.status == SubmissionStatusEnum.READY_TO_SUBMIT
        assert helper.get_status_for_form(form) == TasklistSectionStatusEnum.CHANGES_MADE

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.view_submission",
                grant_id=submission.collection.grant_id,
                submission_id=submission.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        tag_texts = {tag.text.strip() for tag in soup.select(".govuk-tag")}
        assert "Changed" not in tag_texts

    def test_wont_show_diff_for_awaiting_sign_off_with_changes(
        self,
        authenticated_grant_member_client,
        submission_awaiting_sign_off_with_changes_made,
    ):
        submission = submission_awaiting_sign_off_with_changes_made
        grant_recipient = authenticated_grant_member_client.grant_recipient

        assert submission.status == SubmissionStatusEnum.AWAITING_SIGN_OFF

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.view_submission",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                collection_type=submission.collection.type,
                submission_id=submission.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        tag_texts = {tag.text.strip() for tag in soup.select(".govuk-tag")}
        assert "Changed" not in tag_texts


class TestExportSubmissionPDFLock:
    def test_lock_is_held_around_sync_playwright(
        self,
        authenticated_grant_member_client,
        submission_submitted,
        monkeypatch,
    ):
        from app.common.helpers import pdf as pdf_module

        observed_lock_states: list[bool] = []

        class _FakePage:
            def set_content(self, html_content, wait_until):
                pass

            def pdf(self, **kwargs):
                return b"%PDF-fake-content"

        class _FakeBrowser:
            def new_page(self, **kwargs):
                return _FakePage()

        class _FakeChromium:
            def launch(self):
                return _FakeBrowser()

        class _FakePlaywright:
            chromium = _FakeChromium()

        class _FakeSyncPlaywrightCM:
            def __enter__(self_inner):
                observed_lock_states.append(pdf_module._pdf_export_lock.locked())
                return _FakePlaywright()

            def __exit__(self_inner, *args):
                pass

        monkeypatch.setattr(pdf_module, "sync_playwright", lambda: _FakeSyncPlaywrightCM())

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.export_submission_pdf",
                grant_id=authenticated_grant_member_client.grant.id,
                submission_id=submission_submitted.id,
            )
        )

        assert response.status_code == 200
        assert observed_lock_states == [True]
        assert not pdf_module._pdf_export_lock.locked()


class TestReopenSubmission:
    def test_404(self, authenticated_platform_member_client):
        response = authenticated_platform_member_client.get(
            url_for("deliver_grant_funding.reopen_submission", grant_id=uuid.uuid4(), submission_id=uuid.uuid4())
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_org_member_client", False),
            ("authenticated_grant_member_client", True),
        ),
    )
    def test_get(self, request, client_fixture, can_access, submission_submitted):
        client = request.getfixturevalue(client_fixture)
        response = client.get(
            url_for(
                "deliver_grant_funding.reopen_submission",
                grant_id=submission_submitted.collection.grant.id,
                submission_id=submission_submitted.id,
            )
        )
        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert f"Why are you reopening this {submission_submitted.collection.name} submission?" in get_h1_text(soup)
            assert submission_submitted.grant_recipient.organisation.name in get_h1_text(soup)
            assert page_has_button(soup, "Reopen submission")

    def test_post(self, authenticated_grant_member_client, submission_submitted):
        helper = SubmissionHelper(submission_submitted)
        assert helper.status == SubmissionStatusEnum.SUBMITTED
        form = ReopenSubmissionForm(data={"reopened_reason": "as discussed"})
        response = authenticated_grant_member_client.post(
            url_for(
                "deliver_grant_funding.reopen_submission",
                grant_id=submission_submitted.collection.grant.id,
                submission_id=submission_submitted.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == url_for(
            "deliver_grant_funding.view_submission",
            grant_id=submission_submitted.collection.grant.id,
            submission_id=submission_submitted.id,
        )
        assert helper.status == SubmissionStatusEnum.IN_PROGRESS


class TestRequestOrAllowChanges:
    def test_get_request_or_allow_changes_page_1(self, authenticated_grant_member_client, submission_submitted):
        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.request_or_allow_changes",
                grant_id=submission_submitted.collection.grant.id,
                submission_id=submission_submitted.id,
            )
        )

        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")

        assert "Are you requesting changes to" in soup.text

    def test_select_no_request_or_allow_changes_page_1(self, authenticated_grant_member_client, submission_submitted):
        form = RequestOrAllowChangesSubmissionForm(data={"request_changes": "no"})
        response = authenticated_grant_member_client.post(
            url_for(
                "deliver_grant_funding.request_or_allow_changes",
                grant_id=submission_submitted.collection.grant.id,
                submission_id=submission_submitted.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302

        assert response.location == url_for(
            "deliver_grant_funding.reopen_submission",
            grant_id=submission_submitted.collection.grant.id,
            submission_id=submission_submitted.id,
        )

    def test_select_yes_redirects_to_request_changes_submission(
        self, authenticated_grant_member_client, submission_submitted
    ):
        form = RequestOrAllowChangesSubmissionForm(data={"request_changes": "yes"})
        response = authenticated_grant_member_client.post(
            url_for(
                "deliver_grant_funding.request_or_allow_changes",
                grant_id=submission_submitted.collection.grant.id,
                submission_id=submission_submitted.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302

        assert response.location == url_for(
            "deliver_grant_funding.request_changes_submission",
            grant_id=submission_submitted.collection.grant.id,
            submission_id=submission_submitted.id,
        )


class TestRequestChangesSubmission:
    def test_get_request_changes_submission_page(self, authenticated_grant_member_client, submission_submitted):
        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.request_changes_submission",
                grant_id=submission_submitted.collection.grant.id,
                submission_id=submission_submitted.id,
            )
        )

        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")

        assert "Changes needed to" in soup.text

    def test_post_request_changes_submission_without_section_ids(
        self, authenticated_grant_member_client, submission_submitted, db_session
    ):
        client = authenticated_grant_member_client
        grant = client.grant
        grant.allow_pre_award = True

        submission_events_changes_requests_before = (
            db_session.query(SubmissionEvent)
            .where(
                SubmissionEvent.submission_id == submission_submitted.id,
                SubmissionEvent.event_type == SubmissionEventType.SUBMISSION_CHANGES_REQUESTED,
            )
            .all()
        )

        # No SUBMISSION_CHANGES_REQUESTED events before
        assert len(submission_events_changes_requests_before) == 0

        form = RequestChangesSubmissionForm(
            data={
                "changes_requested_reason": "Please update this section",
                "section_ids": [],  # no section_ids
            },
            submission_helper=SubmissionHelper(submission_submitted),
        )
        response = client.post(
            url_for(
                "deliver_grant_funding.request_changes_submission",
                grant_id=grant.id,
                submission_id=submission_submitted.id,
            ),
            data=get_form_data(form),
            follow_redirects=True,
        )

        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")

        assert page_has_flash(soup, "Changes have been requested")

        submission_events_changes_requests_after = (
            db_session.query(SubmissionEvent)
            .where(
                SubmissionEvent.submission_id == submission_submitted.id,
                SubmissionEvent.event_type == SubmissionEventType.SUBMISSION_CHANGES_REQUESTED,
            )
            .all()
        )

        # One SUBMISSION_CHANGES_REQUESTED events created
        assert len(submission_events_changes_requests_after) == 1

    def test_post_request_changes_submission_with_section_ids(
        self, authenticated_grant_member_client, submission_submitted, db_session
    ):
        client = authenticated_grant_member_client
        grant = client.grant
        grant.allow_pre_award = True

        submission_events_changes_requests_before = (
            db_session.query(SubmissionEvent)
            .where(
                SubmissionEvent.submission_id == submission_submitted.id,
                SubmissionEvent.event_type == SubmissionEventType.SUBMISSION_CHANGES_REQUESTED,
            )
            .all()
        )

        # No SUBMISSION_CHANGES_REQUESTED events before
        assert len(submission_events_changes_requests_before) == 0

        section_ids = [str(submission_submitted.collection.forms[0].id)]
        form = RequestChangesSubmissionForm(
            data={
                "changes_requested_reason": "Please update this section",
                "section_ids": section_ids,  # with section_ids
            },
            submission_helper=SubmissionHelper(submission_submitted),
        )
        response = client.post(
            url_for(
                "deliver_grant_funding.request_changes_submission",
                grant_id=grant.id,
                submission_id=submission_submitted.id,
            ),
            data=get_form_data(form),
            follow_redirects=True,
        )

        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")

        assert page_has_flash(soup, "Changes have been requested")

        submission_events_changes_requests_after = (
            db_session.query(SubmissionEvent)
            .where(
                SubmissionEvent.submission_id == submission_submitted.id,
                SubmissionEvent.event_type == SubmissionEventType.SUBMISSION_CHANGES_REQUESTED,
            )
            .all()
        )

        # One SUBMISSION_CHANGES_REQUESTED events created
        assert len(submission_events_changes_requests_after) == 1


class TestListCollectionDataSets:
    def test_404(self, authenticated_grant_member_client):
        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.list_collection_data_sets",
                grant_id=uuid.uuid4(),
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=uuid.uuid4(),
            )
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_upload",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get(self, request: FixtureRequest, client_fixture: str, can_upload: bool, factories):
        client = request.getfixturevalue(client_fixture)
        collection = factories.collection.create(grant=client.grant, name="Test Report")
        factories.grant_recipient.create_batch(3, grant=client.grant)

        uploader = factories.user.create(name="Bilbo Baggins")
        uploader_2 = factories.user.create(name="Frodo Baggins")

        data_source_1 = factories.data_source.create(
            type=DataSourceType.GRANT_RECIPIENT,
            name="Allocations Data",
            grant=client.grant,
            collection=collection,
            created_by=uploader,
            updated_by=None,
            created_at_utc=datetime.datetime(2025, 7, 1, 13, 30, 0),
            create_gr_org_items=True,
        )
        data_source_2 = factories.data_source.create(
            type=DataSourceType.GRANT_RECIPIENT,
            name="Organisation Data",
            grant=client.grant,
            collection=collection,
            created_by=uploader,
            updated_by=uploader_2,
            created_at_utc=datetime.datetime(2025, 7, 1, 13, 30, 0),
            updated_at_utc=datetime.datetime(2025, 7, 1, 14, 30, 0),
            create_gr_org_items=True,
        )

        other_report = factories.collection.create(name="Other Report")
        data_source_3 = factories.data_source.create(
            type=DataSourceType.GRANT_RECIPIENT,
            name="Other Data",
            grant=other_report.grant,
            collection=other_report,
        )

        response = client.get(
            url_for(
                "deliver_grant_funding.list_collection_data_sets",
                grant_id=client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == f"{collection.name} Uploaded data sets"
        assert response.status_code == 200
        assert page_has_link(soup, link_text=f"{data_source_1.name}") is not None
        assert page_has_link(soup, link_text=f"{data_source_2.name}") is not None
        assert uploader.name in soup.text
        assert uploader_2.name in soup.text
        assert data_source_3.name not in soup.text
        data_source_timestamps = soup.find_all("time")
        assert data_source_timestamps[0].text == "1 Jul 2025 at 2:30pm"
        assert data_source_timestamps[1].text == "1 Jul 2025 at 3:30pm"

        data_missing_tags = soup.select(".govuk-tag")
        assert len(data_missing_tags) == 0

        if not can_upload:
            assert page_has_button(soup, button_text="Upload new data set") is None
        else:
            assert page_has_button(soup, button_text="Upload new data set") is not None

    def test_get_shows_missing_data_tag(self, authenticated_org_admin_client, factories):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant, name="Test Report")
        factories.grant_recipient.create_batch(3, grant=grant)
        factories.data_source.create(
            name="Allocations Data",
            type=DataSourceType.GRANT_RECIPIENT,
            grant=grant,
            collection=collection,
            create_gr_org_items=True,
            create_gr_org_items__data=[111, 222, 333],
        )
        factories.data_source.create(
            name="Organisation Data",
            type=DataSourceType.GRANT_RECIPIENT,
            grant=grant,
            collection=collection,
            create_gr_org_items=True,
            create_gr_org_items__data=[111, 222, None],
        )

        response = authenticated_org_admin_client.get(
            url_for(
                "deliver_grant_funding.list_collection_data_sets",
                grant_id=grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )

        soup = BeautifulSoup(response.data, "html.parser")
        assert response.status_code == 200
        data_missing_tags = soup.select(".govuk-tag")
        assert len(data_missing_tags) == 1
        tag_texts = {tag.text.strip() for tag in data_missing_tags}
        assert "Data missing" in tag_texts

    def test_get_upload_button_not_visible_for_live_report(self, authenticated_org_admin_client, factories):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant, name="Test Report", status=CollectionStatusEnum.OPEN)

        response = authenticated_org_admin_client.get(
            url_for(
                "deliver_grant_funding.list_collection_data_sets",
                grant_id=grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )

        soup = BeautifulSoup(response.data, "html.parser")
        assert response.status_code == 200
        assert page_has_button(soup, button_text="Upload new data set") is None

    def test_post_redirects_and_clears_session_data(self, authenticated_grant_admin_client, factories):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant)
        preview_form = GenericSubmitForm()

        with authenticated_grant_admin_client.session_transaction() as session:
            session[SESSION_DATA_SET_UPLOAD] = {
                "name": "Test Data Set",
                "is_grant_recipient_data": True,
                "is_grant_recipient_project_level_data": False,
                "data_columns": ["Amount"],
                "preview_data": {},
                "all_rows": [],
                "column_mappings": [],
            }

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.list_collection_data_sets",
                grant_id=grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            ),
            data=preview_form.data,
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "deliver_grant_funding.upload_data_set",
            grant_id=grant.id,
            collection_type=CollectionType.MONITORING_REPORT,
            collection_id=collection.id,
        )

        with authenticated_grant_admin_client.session_transaction() as session:
            assert session.get(SESSION_DATA_SET_UPLOAD) is None


class TestDownloadGrantRecipientDataSetTemplate:
    def test_404(self, authenticated_grant_member_client):
        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.download_grant_recipient_data_set_template",
                grant_id=uuid.uuid4(),
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=uuid.uuid4(),
            )
        )
        assert response.status_code == 404

    def test_csv_download(self, authenticated_grant_member_client_no_grant_recipients, factories):
        grant = authenticated_grant_member_client_no_grant_recipients.grant
        collection = factories.collection.create(grant=grant)

        grant_recipient_1 = factories.grant_recipient.create(
            grant=grant,
            organisation__external_id="E06012345",
            organisation__name="Rivendell",
        )
        grant_recipient_2 = factories.grant_recipient.create(
            grant=grant,
            organisation__external_id="E06067890",
            organisation__name="Lothlorien",
        )
        grant_recipient_3 = factories.grant_recipient.create(
            grant=grant,
            organisation__name="Isengard",
            organisation__external_id="E06050000",
            organisation__mode=OrganisationModeEnum.TEST,
        )
        grant_recipient_4 = factories.grant_recipient.create(
            grant=grant,
            organisation__name="Shire",
            organisation__external_id="E06099999",
        )

        response = authenticated_grant_member_client_no_grant_recipients.get(
            url_for(
                "deliver_grant_funding.download_grant_recipient_data_set_template",
                grant_id=grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )

        assert response.status_code == 200
        assert response.mimetype == "text/csv"
        assert response.content_length > 0

        lines = response.text.splitlines()
        assert len(lines) == 4  # Header + 3 grant recipients

        header = lines[0]
        assert DATA_SET_EXTERNAL_ID_COLUMN_HEADER in header
        assert "Grant recipient" in header

        assert grant_recipient_2.organisation.name in lines[1]
        assert grant_recipient_2.organisation.external_id in lines[1]
        assert grant_recipient_1.organisation.name in lines[2]
        assert grant_recipient_1.organisation.external_id in lines[2]
        assert grant_recipient_4.organisation.name in lines[3]

        # Test grant recipient organisations excluded
        assert grant_recipient_3.organisation.name not in response.text

    def test_csv_download_empty_grant_recipients(
        self, factories, authenticated_grant_member_client_no_grant_recipients
    ):

        collection = factories.collection.create(
            grant=authenticated_grant_member_client_no_grant_recipients.grant, name="Test Report"
        )

        response = authenticated_grant_member_client_no_grant_recipients.get(
            url_for(
                "deliver_grant_funding.download_grant_recipient_data_set_template",
                grant_id=authenticated_grant_member_client_no_grant_recipients.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )

        assert response.status_code == 200
        assert response.mimetype == "text/csv"

        lines = response.text.splitlines()
        assert len(lines) == 1

    def test_csv_download_filename(self, authenticated_grant_member_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant)

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.download_grant_recipient_data_set_template",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )

        assert response.status_code == 200
        content_disposition = response.headers.get("Content-Disposition")
        assert f"{collection.slug}-grant-recipient-data-template.csv" in content_disposition


def _rows_to_csv_bytes(rows: list[dict]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


class TestUploadDataSet:
    def test_404(self, authenticated_grant_member_client):
        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.upload_data_set",
                grant_id=uuid.uuid4(),
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=uuid.uuid4(),
            )
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get(self, client_fixture, can_access, request: FixtureRequest, factories):
        client = request.getfixturevalue(client_fixture)
        grant = client.grant
        collection = factories.collection.create(grant=grant)

        response = client.get(
            url_for(
                "deliver_grant_funding.upload_data_set",
                grant_id=grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )

        soup = BeautifulSoup(response.data, "html.parser")
        if can_access:
            assert response.status_code == 200
            assert f"{collection.name} Upload new data set" in get_h1_text(soup)
        else:
            assert response.status_code == 403

    def test_get_repopulates_form_from_session(self, authenticated_grant_admin_client, factories):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant)

        with authenticated_grant_admin_client.session_transaction() as session:
            session[SESSION_DATA_SET_UPLOAD] = {
                "name": "Test Data Set",
                "data_source_type": DataSourceType.GRANT_RECIPIENT,
                "data_columns": ["Amount"],
                "preview_data": {},
                "column_mappings": [],
                "data_source_id": uuid.uuid4(),
                "original_filename": "test.csv",
                "s3_key": "data-set-uploads/test.csv",
            }

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.upload_data_set",
                grant_id=grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.text, "html.parser")
        name_input = soup.find("input", {"name": "name"})
        assert name_input["value"] == "Test Data Set"

    def test_post_valid_csv_redirects_to_confirm_grant_recipients_with_session(
        self, authenticated_grant_admin_client, factories, mock_s3_service_calls
    ):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant)
        factories.grant_recipient.create(
            grant=grant, organisation__external_id="E06000123", organisation__name="Rivendell"
        )
        factories.grant_recipient.create(
            grant=grant, organisation__external_id="E06000456", organisation__name="Lothlorien"
        )

        csv_content = "Organisation ID,Grant recipient,Amount\nE06000123,Lothlorien,1000\nE06000456,Rivendell,2000"
        data = {
            "name": "Test Data Set",
            "data_source_type": DataSourceType.GRANT_RECIPIENT,
            "file": (io.BytesIO(csv_content.encode("utf-8")), "test.csv"),
        }

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.upload_data_set",
                grant_id=grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            ),
            data=data,
            content_type="multipart/form-data",
        )

        assert response.status_code == 302
        assert response.location == (
            url_for(
                "deliver_grant_funding.confirm_data_set_grant_recipients",
                grant_id=grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )
        assert len(mock_s3_service_calls.upload_file_calls) == 1

        with authenticated_grant_admin_client.session_transaction() as session:
            session_data = session.get(SESSION_DATA_SET_UPLOAD)
            assert session_data is not None

        data_source_id = session_data["data_source_id"]

        expected_s3_key = build_data_set_upload_s3_key(
            grant_id=grant.id,
            collection_id=collection.id,
            data_source_id=data_source_id,
        )

        assert session_data["s3_key"] == expected_s3_key
        assert session_data["name"] == "Test Data Set"
        assert session_data["data_source_type"] == DataSourceType.GRANT_RECIPIENT
        assert session_data["data_columns"] == ["Amount"]
        assert session_data["original_filename"] == "test.csv"
        assert session_data["s3_key"] == expected_s3_key

        assert mock_s3_service_calls.upload_file_calls[0].args[1] == expected_s3_key
        assert mock_s3_service_calls.upload_file_calls[0].args[2] == {"status": DataSourceFileTagEnum.PENDING}

    def test_post_raises_errors_for_incorrect_grant_recipient_data(
        self, authenticated_grant_admin_client, factories, mock_s3_service_calls
    ):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant)
        factories.grant_recipient.create(
            grant=grant, organisation__external_id="E06000123", organisation__name="Lothlorien"
        )
        factories.grant_recipient.create(
            grant=grant, organisation__external_id="E06000456", organisation__name="Numenor"
        )

        csv_content = (
            "Organisation ID,Grant recipient,Amount,Category\nE06000123,Lothlorien,1000,A"
            + "\nE06000123,Rogue,1000,A\nE06000789,Mordor,1000,A"
        )
        data = {
            "name": "Test Data Set",
            "data_source_type": DataSourceType.GRANT_RECIPIENT,
            "file": (io.BytesIO(csv_content.encode("utf-8")), "test.csv"),
        }

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.upload_data_set",
                grant_id=grant.id,
                collection_type=collection.type,
                collection_id=collection.id,
            ),
            data=data,
            content_type="multipart/form-data",
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, f"{DATA_SET_EXTERNAL_ID_COLUMN_HEADER} 'E06000123' already appears in the data set")
        assert page_has_error(soup, f"{DATA_SET_EXTERNAL_ID_COLUMN_HEADER} 'E06000789' not found in grant recipients")
        assert len(mock_s3_service_calls.upload_file_calls) == 1
        assert mock_s3_service_calls.upload_file_calls[0].args[2] == {"status": DataSourceFileTagEnum.PENDING}

    def test_post_stores_preview_data(self, authenticated_grant_admin_client, factories, mock_s3_service_calls):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant)
        factories.grant_recipient.create(
            grant=grant, organisation__external_id="E06000123", organisation__name="Lothlorien"
        )
        factories.grant_recipient.create(
            grant=grant, organisation__external_id="E06000456", organisation__name="Numenor"
        )
        factories.grant_recipient.create(
            grant=grant, organisation__external_id="E06000789", organisation__name="Rivendell"
        )
        factories.grant_recipient.create(
            grant=grant, organisation__external_id="E06000500", organisation__name="Gondor"
        )

        csv_content = (
            "Organisation ID,Grant recipient,Amount,Category\n"
            "E06000123,Lothlorien,,A\n"
            "E06000456,Numenor,1000,A\n"
            "E06000789,Rivendell,2000,A\n"
            "E06000500,Gondor,3000,A"
        )
        data = {
            "name": "Test Data Set",
            "data_source_type": DataSourceType.GRANT_RECIPIENT,
            "file": (io.BytesIO(csv_content.encode("utf-8")), "test.csv"),
        }

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.upload_data_set",
                grant_id=grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            ),
            data=data,
            content_type="multipart/form-data",
        )

        assert response.status_code == 302

        with authenticated_grant_admin_client.session_transaction() as sess:
            session_data = sess.get(SESSION_DATA_SET_UPLOAD)
            assert set(session_data["preview_data"].keys()) == {"Amount", "Category"}
            for values in session_data["preview_data"].values():
                assert len(values) == 3
                assert all(v != "" for v in values)
            assert session_data["preview_data"]["Amount"] == ["1000", "2000", "3000"]
        assert len(mock_s3_service_calls.upload_file_calls) == 1


class TestMapDataSetColumns:
    def test_404_for_non_admin(self, authenticated_grant_member_client):
        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.map_data_set_columns",
                grant_id=uuid.uuid4(),
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=uuid.uuid4(),
            )
        )
        assert response.status_code == 404

    @pytest.mark.parametrize("has_missing_data", [True, False])
    def test_get_renders_columns_and_preview(self, authenticated_grant_admin_client, has_missing_data, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)

        with authenticated_grant_admin_client.session_transaction() as session:
            session[SESSION_DATA_SET_UPLOAD] = DataSetUploadSessionModel(
                name="Test Data Set",
                data_source_type=DataSourceType.GRANT_RECIPIENT,
                data_columns=["Capital allocation", "Revenue allocation", "Notes"],
                preview_data={
                    "Capital allocation": ["£1000", "£2000"],
                    "Revenue allocation": ["£10000", "£30000"],
                    "Notes": ["First", "Second"],
                },
                data_source_id=uuid.uuid4(),
                original_filename="test.csv",
                s3_key="data-set-uploads/test.csv",
                has_missing_data=has_missing_data,
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.map_data_set_columns",
                grant_id=collection.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )
        assert response.status_code == 200

        data_set_session_data = session[SESSION_DATA_SET_UPLOAD]
        soup = BeautifulSoup(response.data, "html.parser")

        assert f"Map {data_set_session_data['name']} data columns" in get_h1_text(soup)

        for _, values in data_set_session_data["preview_data"].items():
            for value in values:
                assert value in soup.text
        for idx, col in enumerate(data_set_session_data["data_columns"]):
            assert col in soup.text
            select = soup.find("select", {"name": f"columns-{idx}-column_type"})
            assert select is not None

        if has_missing_data:
            assert page_has_link(soup, "Back").get("href") == url_for(
                "deliver_grant_funding.data_set_missing_data",
                grant_id=collection.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        else:
            assert page_has_link(soup, "Back").get("href") == url_for(
                "deliver_grant_funding.upload_data_set",
                grant_id=collection.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )

    def test_get_repopulates_form_from_session(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        with authenticated_grant_admin_client.session_transaction() as session:
            session[SESSION_DATA_SET_UPLOAD] = DataSetUploadSessionModel(
                name="Test Data Set",
                data_source_type=DataSourceType.GRANT_RECIPIENT,
                data_columns=[
                    "Capital allocation",
                    "Revenue allocation",
                ],
                preview_data={
                    "Capital allocation": ["£1000", "£2000"],
                    "Revenue allocation": ["£10000", "£30000"],
                },
                column_mappings=[
                    DataSetColumnMapping(column_name="Capital allocation", column_type="INTEGER"),
                    DataSetColumnMapping(column_name="Revenue allocation", column_type="DECIMAL"),
                ],
                data_source_id=uuid.uuid4(),
                original_filename="test.csv",
                s3_key="data-set-uploads/test.csv",
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.map_data_set_columns",
                grant_id=collection.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )
        soup = BeautifulSoup(response.data, "html.parser")

        select_0 = soup.find("select", {"name": "columns-0-column_type"})
        select_1 = soup.find("select", {"name": "columns-1-column_type"})
        assert select_0.find("option", {"selected": True})["value"] == "INTEGER"
        assert select_1.find("option", {"selected": True})["value"] == "DECIMAL"

    def test_get_without_session_redirects_to_upload(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.map_data_set_columns",
                grant_id=collection.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )
        assert response.status_code == 302
        assert response.location.endswith(
            url_for(
                "deliver_grant_funding.upload_data_set",
                grant_id=collection.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )

    def test_post_redirects_to_map_number_columns(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        with authenticated_grant_admin_client.session_transaction() as session:
            session[SESSION_DATA_SET_UPLOAD] = DataSetUploadSessionModel(
                name="Test Data Set",
                data_source_type=DataSourceType.GRANT_RECIPIENT,
                data_columns=["Capital allocation", "Additional info"],
                preview_data={
                    "Capital allocation": ["£1000", "£2000"],
                    "Additional info": ["Some extra details", "Here are some finer details"],
                },
                data_source_id=uuid.uuid4(),
                original_filename="test.csv",
                s3_key="data-set-uploads/test.csv",
            ).model_dump(mode="json")

        data = {
            "columns-0-column_type": "INTEGER",
            "columns-1-column_type": "TEXT",
            "submit": "y",
        }
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.map_data_set_columns",
                grant_id=collection.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            ),
            data=data,
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location.endswith(
            url_for(
                "deliver_grant_funding.map_data_set_number_columns",
                grant_id=collection.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )

    def test_post_no_errors_creates_datasource_and_redirects(
        self, authenticated_grant_admin_client, factories, db_session, mock_s3_service_calls, mocker
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        grant_recipient = factories.grant_recipient.create(
            grant=authenticated_grant_admin_client.grant, organisation__external_id="E06000123"
        )
        grant_recipient_2 = factories.grant_recipient.create(
            grant=authenticated_grant_admin_client.grant, organisation__external_id="E06000456"
        )

        with authenticated_grant_admin_client.session_transaction() as session:
            session[SESSION_DATA_SET_UPLOAD] = DataSetUploadSessionModel(
                name="Test Data Set",
                data_source_type=DataSourceType.GRANT_RECIPIENT,
                data_columns=["Area description"],
                preview_data={"Area description": ["A fine place", "A wonderful place"]},
                data_source_id=uuid.uuid4(),
                original_filename="test.csv",
                s3_key="data-set-uploads/test.csv",
            ).model_dump(mode="json")

        all_rows = [
            {
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: grant_recipient.organisation.name,
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: grant_recipient.organisation.external_id,
                "Area description": "A fine place",
            },
            {
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: grant_recipient_2.organisation.name,
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: grant_recipient_2.organisation.external_id,
                "Area description": "A wonderful place",
            },
        ]
        mocker.patch("app.services.s3.S3Service.download_file", return_value=_rows_to_csv_bytes(all_rows))

        data = {
            "columns-0-column_type": "TEXT",
            "submit": "y",
        }
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.map_data_set_columns",
                grant_id=collection.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            ),
            data=data,
            follow_redirects=True,
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(
            soup, f"You can now reference {session['data_set_upload']['name']} data in the {collection.name} grant form"
        )

        assert authenticated_grant_admin_client.user.name in soup.text
        assert db_session.scalar(select(func.count()).select_from(DataSource)) == 1
        assert db_session.scalar(select(func.count()).select_from(DataSourceOrganisationItem)) == 2

        assert len(mock_s3_service_calls.update_file_tags) == 1
        assert mock_s3_service_calls.update_file_tags[0].args[1] == {"status": DataSourceFileTagEnum.IN_USE}

    def test_post_missing_required_field_shows_error(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        with authenticated_grant_admin_client.session_transaction() as session:
            session[SESSION_DATA_SET_UPLOAD] = DataSetUploadSessionModel(
                name="Test Data Set",
                data_source_type=DataSourceType.GRANT_RECIPIENT,
                data_columns=[
                    "Capital allocation",
                    "Revenue allocation",
                ],
                preview_data={
                    "Capital allocation": ["£1000", "£2000"],
                    "Revenue allocation": ["£10000", "£30000"],
                },
                data_source_id=uuid.uuid4(),
                original_filename="test.csv",
                s3_key="data-set-uploads/test.csv",
            ).model_dump(mode="json")

        data = {
            "columns-0-column_type": "",
            "columns-1-column_type": "INTEGER",
            "submit": "y",
        }
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.map_data_set_columns",
                grant_id=collection.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            ),
            data=data,
            follow_redirects=True,
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, f"Select a data type for {session['data_set_upload']['data_columns'][0]}")

    def test_post_british_pounds_with_bad_data_shows_inline_error(
        self, authenticated_grant_admin_client, factories, mock_s3_service_calls, mocker
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        grant_recipient = factories.grant_recipient.create(
            grant=authenticated_grant_admin_client.grant, organisation__external_id="E06000123"
        )

        with authenticated_grant_admin_client.session_transaction() as session:
            session[SESSION_DATA_SET_UPLOAD] = DataSetUploadSessionModel(
                name="Test Data Set",
                data_source_type=DataSourceType.GRANT_RECIPIENT,
                data_columns=["Capital allocation"],
                preview_data={"Capital allocation": ["100", "£200.5"]},
                data_source_id=uuid.uuid4(),
                original_filename="test.csv",
                s3_key="data-set-uploads/test.csv",
            ).model_dump(mode="json")

        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: grant_recipient.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: grant_recipient.organisation.name,
                "Capital allocation": "£200.555",
            },
        ]
        mocker.patch("app.services.s3.S3Service.download_file", return_value=_rows_to_csv_bytes(all_rows))

        data = {
            "columns-0-column_type": "BRITISH_POUNDS",
            "submit": "y",
        }
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.map_data_set_columns",
                grant_id=collection.grant.id,
                collection_type=collection.type,
                collection_id=collection.id,
            ),
            data=data,
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        expected_message = (
            "One or more numbers in column 'Capital allocation' are not formatted as British pounds to 2 "
            "decimal places with the '£' prefix. For example, £100.00"
        )
        assert page_has_error(soup, expected_message)
        select = soup.find("select", {"name": "columns-0-column_type"})
        error_id = select.get("aria-describedby", "").split()[-1] if select else ""
        error_element = soup.find(id=error_id) if error_id else None
        assert error_element is not None
        assert expected_message in error_element.get_text()

    def test_post_british_pounds_clean_data_proceeds(
        self, authenticated_grant_admin_client, factories, db_session, mock_s3_service_calls, mocker
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        grant_recipient = factories.grant_recipient.create(
            grant=authenticated_grant_admin_client.grant, organisation__external_id="E06000123"
        )

        with authenticated_grant_admin_client.session_transaction() as session:
            session[SESSION_DATA_SET_UPLOAD] = DataSetUploadSessionModel(
                name="Test Data Set",
                data_source_type=DataSourceType.GRANT_RECIPIENT,
                data_columns=["Capital allocation"],
                preview_data={"Capital allocation": ["£100.00"]},
                data_source_id=uuid.uuid4(),
                original_filename="test.csv",
                s3_key="data-set-uploads/test.csv",
            ).model_dump(mode="json")

        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: grant_recipient.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: grant_recipient.organisation.name,
                "Capital allocation": "£100.00",
            },
        ]
        mocker.patch("app.services.s3.S3Service.download_file", return_value=_rows_to_csv_bytes(all_rows))

        data = {
            "columns-0-column_type": "BRITISH_POUNDS",
            "submit": "y",
        }
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.map_data_set_columns",
                grant_id=collection.grant.id,
                collection_type=collection.type,
                collection_id=collection.id,
            ),
            data=data,
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location.endswith(
            url_for(
                "deliver_grant_funding.list_collection_data_sets",
                grant_id=collection.grant.id,
                collection_type=collection.type,
                collection_id=collection.id,
            )
        )
        assert db_session.scalar(select(func.count()).select_from(DataSource)) == 1


class TestMapDataSetNumberColumns:
    def test_404_for_non_admin(self, authenticated_grant_member_client):
        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.map_data_set_number_columns",
                grant_id=uuid.uuid4(),
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=uuid.uuid4(),
            )
        )
        assert response.status_code == 404

    def test_get_renders_number_columns_and_fields(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)

        with authenticated_grant_admin_client.session_transaction() as session:
            session[SESSION_DATA_SET_UPLOAD] = DataSetUploadSessionModel(
                name="Test Data Set",
                data_source_type=DataSourceType.GRANT_RECIPIENT,
                data_columns=["Additional info", "Capital allocation", "Revenue allocation"],
                preview_data={
                    "Additional info": ["Some text", "Some text"],
                    "Capital allocation": ["£1000", "£2000"],
                    "Revenue allocation": ["£10000", "£30000"],
                },
                column_mappings=[
                    DataSetColumnMapping(column_name="Additional info", column_type="TEXT"),
                    DataSetColumnMapping(column_name="Capital allocation", column_type="DECIMAL"),
                    DataSetColumnMapping(column_name="Revenue allocation", column_type="INTEGER"),
                ],
                data_source_id=uuid.uuid4(),
                original_filename="test.csv",
                s3_key="data-set-uploads/test.csv",
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.map_data_set_number_columns",
                grant_id=collection.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")

        assert "Capital allocation" in soup.text
        assert "Revenue allocation" in soup.text
        assert "Additional info" not in soup.text

        assert soup.find("input", {"name": "columns-0-prefix"}) is not None
        assert soup.find("input", {"name": "columns-0-suffix"}) is not None
        assert soup.find("input", {"name": "columns-0-max_decimal_places"}) is not None
        assert soup.find("input", {"name": "columns-1-prefix"}) is not None
        assert soup.find("input", {"name": "columns-1-suffix"}) is not None

        assert soup.find("input", {"name": "columns-1-max_decimal_places"}) is None

    def test_get_repopulates_form_from_session(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        with authenticated_grant_admin_client.session_transaction() as session:
            session[SESSION_DATA_SET_UPLOAD] = DataSetUploadSessionModel(
                name="Test Data Set",
                data_source_type=DataSourceType.GRANT_RECIPIENT,
                data_columns=["Capital allocation", "Revenue allocation", "Additional info"],
                preview_data={
                    "Additional info": ["Some text", "Some text"],
                    "Capital allocation": ["£1000", "£2000"],
                    "Revenue allocation": ["£10000", "£30000"],
                },
                column_mappings=[
                    DataSetColumnMapping(
                        column_name="Capital allocation", column_type="DECIMAL", prefix="£", max_decimal_places=2
                    ),
                    DataSetColumnMapping(column_name="Revenue allocation", column_type="INTEGER", suffix="km"),
                    DataSetColumnMapping(column_name="Additional info", column_type="TEXT"),
                ],
                data_source_id=uuid.uuid4(),
                original_filename="test.csv",
                s3_key="data-set-uploads/test.csv",
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.map_data_set_number_columns",
                grant_id=collection.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )
        soup = BeautifulSoup(response.data, "html.parser")
        assert soup.find("input", {"name": "columns-0-prefix"})["value"] == "£"
        assert soup.find("input", {"name": "columns-0-max_decimal_places"})["value"] == "2"
        assert soup.find("input", {"name": "columns-1-suffix"})["value"] == "km"

    def test_post_no_errors_creates_datasource_and_redirects(
        self, authenticated_grant_admin_client, factories, db_session, mock_s3_service_calls, mocker
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        grant_recipient = factories.grant_recipient.create(
            grant=authenticated_grant_admin_client.grant, organisation__external_id="E06000123"
        )
        grant_recipient_2 = factories.grant_recipient.create(
            grant=authenticated_grant_admin_client.grant, organisation__external_id="E06000456"
        )
        with authenticated_grant_admin_client.session_transaction() as session:
            session[SESSION_DATA_SET_UPLOAD] = DataSetUploadSessionModel(
                name="Test Data Set",
                data_source_type=DataSourceType.GRANT_RECIPIENT,
                data_columns=["Capital allocation", "Revenue allocation", "Additional info"],
                preview_data={
                    "Additional info": ["Some text", "Some text"],
                    "Capital allocation": ["£1000", "£2000"],
                    "Revenue allocation": ["£10000", "£30000"],
                },
                column_mappings=[
                    DataSetColumnMapping(column_name="Capital allocation", column_type="DECIMAL"),
                    DataSetColumnMapping(column_name="Revenue allocation", column_type="INTEGER"),
                    DataSetColumnMapping(column_name="Additional info", column_type="TEXT"),
                ],
                data_source_id=uuid.uuid4(),
                original_filename="test.csv",
                s3_key="data-set-uploads/test.csv",
            ).model_dump(mode="json")

        all_rows = [
            {
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: grant_recipient.organisation.name,
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: grant_recipient.organisation.external_id,
                "Capital allocation": "£1000",
                "Revenue allocation": "£10000",
                "Additional info": "Some text",
            },
            {
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: grant_recipient_2.organisation.name,
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: grant_recipient_2.organisation.external_id,
                "Capital allocation": "£2000",
                "Revenue allocation": "£30000",
                "Additional info": "Some text",
            },
        ]
        mocker.patch("app.services.s3.S3Service.download_file", return_value=_rows_to_csv_bytes(all_rows))

        data = {
            "columns-0-prefix": "£",
            "columns-0-suffix": "",
            "columns-0-max_decimal_places": "2",
            "columns-1-prefix": "£",
            "columns-1-suffix": "",
            "submit": "y",
        }

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.map_data_set_number_columns",
                grant_id=collection.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            ),
            data=data,
            follow_redirects=True,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(
            soup, f"You can now reference {session['data_set_upload']['name']} data in the {collection.name} grant form"
        )
        assert authenticated_grant_admin_client.user.name in soup.text
        assert db_session.scalar(select(func.count()).select_from(DataSource)) == 1
        assert db_session.scalar(select(func.count()).select_from(DataSourceOrganisationItem)) == 2

        assert len(mock_s3_service_calls.update_file_tags) == 1
        assert mock_s3_service_calls.update_file_tags[0].args[1] == {"status": DataSourceFileTagEnum.IN_USE}

        with authenticated_grant_admin_client.session_transaction() as updated_session:
            assert updated_session.get(SESSION_DATA_SET_UPLOAD) is None

    def test_post_shows_form_errors(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        with authenticated_grant_admin_client.session_transaction() as session:
            session[SESSION_DATA_SET_UPLOAD] = DataSetUploadSessionModel(
                name="Test Data Set",
                data_source_type=DataSourceType.GRANT_RECIPIENT,
                data_columns=[
                    "Capital allocation",
                    "Revenue allocation",
                ],
                preview_data={
                    "Capital allocation": ["£1000", "£2000"],
                    "Revenue allocation": ["£10000", "£30000"],
                },
                column_mappings=[
                    DataSetColumnMapping(column_name="Capital allocation", column_type="DECIMAL"),
                    DataSetColumnMapping(column_name="Revenue allocation", column_type="INTEGER"),
                ],
                data_source_id=uuid.uuid4(),
                original_filename="test.csv",
                s3_key="data-set-uploads/test.csv",
            ).model_dump(mode="json")

        data = {
            "columns-0-prefix": "£",
            "columns-0-suffix": "km",
            "columns-0-max_decimal_places": "",
            "columns-1-prefix": "",
            "columns-1-suffix": "",
            "submit": "y",
        }
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.map_data_set_number_columns",
                grant_id=collection.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            ),
            data=data,
            follow_redirects=True,
        )
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "Remove the suffix if you need a prefix")
        assert page_has_error(soup, "Remove the prefix if you need a suffix")
        assert page_has_error(soup, "Enter the maximum number of decimal places")

    def test_post_shows_errors_for_blocking_cell_errors(
        self, authenticated_grant_admin_client, factories, mock_s3_service_calls, mocker
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        grant_recipient = factories.grant_recipient.create(
            grant=authenticated_grant_admin_client.grant, organisation__external_id="E06000123"
        )
        grant_recipient2 = factories.grant_recipient.create(
            grant=authenticated_grant_admin_client.grant, organisation__external_id="E06000456"
        )

        with authenticated_grant_admin_client.session_transaction() as session:
            session[SESSION_DATA_SET_UPLOAD] = {
                "name": "Test Data Set",
                "data_source_type": DataSourceType.GRANT_RECIPIENT,
                "data_columns": ["Capital allocation", "Distance"],
                "preview_data": {},
                "data_source_id": uuid.uuid4(),
                "original_filename": "test.csv",
                "s3_key": "data-set-uploads/test.csv",
                "column_mappings": [
                    DataSetColumnMapping(column_name="Capital allocation", column_type="DECIMAL").model_dump(
                        mode="json"
                    ),
                    DataSetColumnMapping(column_name="Distance", column_type="INTEGER").model_dump(mode="json"),
                ],
            }

        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: grant_recipient.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: grant_recipient.organisation.name,
                "Capital allocation": "$1000.123",
                "Distance": "ABC",
            },
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: grant_recipient2.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: grant_recipient2.organisation.name,
                "Capital allocation": "$1000.123",
                "Distance": "ABCkm",
            },
        ]
        mocker.patch("app.services.s3.S3Service.download_file", return_value=_rows_to_csv_bytes(all_rows))

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.map_data_set_number_columns",
                grant_id=collection.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            ),
            data={
                "columns-0-column_name": "Capital allocation",
                "columns-0-number_type": NumberTypeEnum.DECIMAL,
                "columns-0-prefix": "£",
                "columns-0-suffix": "",
                "columns-0-max_decimal_places": "2",
                "columns-1-column_name": "Distance",
                "columns-1-number_type": NumberTypeEnum.INTEGER,
                "columns-1-prefix": "",
                "columns-1-suffix": "km",
                "columns-1-max_decimal_places": "2",
                "submit": "Continue",
            },
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "One or more numbers in 'Capital allocation' do not match the prefix '£'")
        assert page_has_error(soup, "One or more numbers in 'Capital allocation' have more than 2 decimal places")
        assert page_has_error(soup, "One or more values in 'Capital allocation' are not a valid decimal number")
        assert page_has_error(soup, "One or more numbers in 'Distance' do not match the suffix 'km'")
        assert page_has_error(soup, "One or more values in 'Distance' are not a valid whole number")


class TestDataSetConfirmGrantRecipients:
    def test_404_for_non_admin(self, authenticated_grant_member_client):
        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.confirm_data_set_grant_recipients",
                grant_id=uuid.uuid4(),
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=uuid.uuid4(),
            )
        )
        assert response.status_code == 404

    @pytest.mark.parametrize("session_data_name", [SESSION_DATA_SET_UPLOAD, SESSION_DATA_SET_REPLACE])
    def test_get_with_mismatched_grant_recipients(
        self, authenticated_grant_admin_client, factories, mocker, mock_s3_service_calls, session_data_name
    ):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant)
        gr = factories.grant_recipient.create(
            grant=grant, organisation__external_id="E123", organisation__name="Rivendell"
        )
        gr2 = factories.grant_recipient.create(
            grant=grant, organisation__external_id="E456", organisation__name="Lothlorien"
        )

        with authenticated_grant_admin_client.session_transaction() as session:
            session[session_data_name] = {
                "name": "Test Data Set",
                "data_source_type": DataSourceType.GRANT_RECIPIENT,
                "data_columns": ["Capital allocation"],
                "preview_data": {},
                "column_mappings": [
                    DataSetColumnMapping(column_name="Capital allocation", column_type="BRITISH_POUNDS").model_dump(
                        mode="json"
                    ),
                ],
                "data_source_id": uuid.uuid4(),
                "original_filename": "test.csv",
                "s3_key": "data-set-uploads/test.csv",
            }

        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr.organisation.name,
                "Capital allocation": "",
            },
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr2.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "Different name",
                "Capital allocation": "£1000.00",
            },
        ]

        mocker.patch("app.services.s3.S3Service.download_file", return_value=_rows_to_csv_bytes(all_rows))

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.confirm_data_set_grant_recipients",
                grant_id=grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Confirm grant recipients" in get_h1_text(soup)
        assert gr.organisation.name not in soup.text
        assert gr2.organisation.name in soup.text
        assert "Different name" in soup.text

    @pytest.mark.parametrize("session_data_name", [SESSION_DATA_SET_UPLOAD, SESSION_DATA_SET_REPLACE])
    def test_get_no_gr_mismatch_redirects_to_missing_data(
        self, authenticated_grant_admin_client, factories, mocker, mock_s3_service_calls, session_data_name
    ):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant)
        gr = factories.grant_recipient.create(
            grant=grant, organisation__external_id="E123", organisation__name="Rivendell"
        )
        gr2 = factories.grant_recipient.create(
            grant=grant, organisation__external_id="E456", organisation__name="Lothlorien"
        )

        with authenticated_grant_admin_client.session_transaction() as session:
            session[session_data_name] = {
                "name": "Test Data Set",
                "data_source_type": DataSourceType.GRANT_RECIPIENT,
                "data_columns": ["Capital allocation"],
                "preview_data": {},
                "column_mappings": [
                    DataSetColumnMapping(column_name="Capital allocation", column_type="BRITISH_POUNDS").model_dump(
                        mode="json"
                    ),
                ],
                "data_source_id": uuid.uuid4(),
                "original_filename": "test.csv",
                "s3_key": "data-set-uploads/test.csv",
            }

        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr.organisation.name,
                "Capital allocation": "£2000.00",
            },
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr2.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr2.organisation.name,
                "Capital allocation": "£1000.00",
            },
        ]

        mocker.patch("app.services.s3.S3Service.download_file", return_value=_rows_to_csv_bytes(all_rows))

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.confirm_data_set_grant_recipients",
                grant_id=grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            ),
            data={"submit": "y"},
        )

        assert response.status_code == 302
        assert response.location == (
            url_for(
                "deliver_grant_funding.data_set_missing_data",
                grant_id=grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )

    @pytest.mark.parametrize("session_data_name", [SESSION_DATA_SET_UPLOAD, SESSION_DATA_SET_REPLACE])
    def test_post_csv_with_missing_data_redirects_to_missing_data(
        self, authenticated_grant_admin_client, factories, mocker, mock_s3_service_calls, session_data_name
    ):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant)
        gr = factories.grant_recipient.create(
            grant=grant, organisation__external_id="E123", organisation__name="Rivendell"
        )
        gr2 = factories.grant_recipient.create(
            grant=grant, organisation__external_id="E456", organisation__name="Lothlorien"
        )

        with authenticated_grant_admin_client.session_transaction() as session:
            session[session_data_name] = {
                "name": "Test Data Set",
                "data_source_type": DataSourceType.GRANT_RECIPIENT,
                "data_columns": ["Capital allocation"],
                "preview_data": {},
                "column_mappings": [
                    DataSetColumnMapping(column_name="Capital allocation", column_type="BRITISH_POUNDS").model_dump(
                        mode="json"
                    ),
                ],
                "data_source_id": uuid.uuid4(),
                "original_filename": "test.csv",
                "s3_key": "data-set-uploads/test.csv",
                "is_replace": session_data_name == SESSION_DATA_SET_REPLACE,
            }

        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr.organisation.name,
                "Capital allocation": "",
            },
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr2.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "Different name",
                "Capital allocation": "£1000.00",
            },
        ]

        mocker.patch("app.services.s3.S3Service.download_file", return_value=_rows_to_csv_bytes(all_rows))

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.confirm_data_set_grant_recipients",
                grant_id=grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            ),
            data={"submit": "y"},
        )

        assert response.status_code == 302
        assert response.location == (
            url_for(
                "deliver_grant_funding.data_set_missing_data",
                grant_id=grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )
        with authenticated_grant_admin_client.session_transaction() as sess:
            data_set_data = sess.get(session_data_name)
            assert data_set_data is not None
            assert data_set_data["has_grant_recipient_mismatches"] is True


class TestDataSetMissingData:
    def test_404_for_non_admin(self, authenticated_grant_member_client):
        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.data_set_missing_data",
                grant_id=uuid.uuid4(),
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=uuid.uuid4(),
            )
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "has_grant_recipient_mismatches,session_data_name",
        [
            (True, SESSION_DATA_SET_UPLOAD),
            (True, SESSION_DATA_SET_REPLACE),
            (False, SESSION_DATA_SET_UPLOAD),
            (False, SESSION_DATA_SET_REPLACE),
        ],
    )
    def test_get_data_set_missing_data_shows_rows_with_missing_data(
        self, authenticated_grant_admin_client, factories, mocker, has_grant_recipient_mismatches, session_data_name
    ):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant)
        gr = factories.grant_recipient.create(
            grant=grant, organisation__external_id="E06000123", organisation__name="Rivendell"
        )
        gr2 = factories.grant_recipient.create(
            grant=grant, organisation__external_id="E06000456", organisation__name="Lothlorien"
        )
        gr3 = factories.grant_recipient.create(
            grant=grant, organisation__external_id="EC789", organisation__name="Gondor"
        )

        with authenticated_grant_admin_client.session_transaction() as session:
            session[session_data_name] = {
                "name": "Test Data Set",
                "data_source_type": DataSourceType.GRANT_RECIPIENT,
                "data_columns": ["Capital allocation"],
                "preview_data": {},
                "column_mappings": [
                    DataSetColumnMapping(column_name="Capital allocation", column_type="BRITISH_POUNDS").model_dump(
                        mode="json"
                    ),
                ],
                "data_source_id": uuid.uuid4(),
                "original_filename": "test.csv",
                "s3_key": "data-set-uploads/test.csv",
                "has_grant_recipient_mismatches": has_grant_recipient_mismatches,
            }

        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr.organisation.name,
                "Capital allocation": "",
            },
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr2.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr2.organisation.name,
                "Capital allocation": "£1000.00",
            },
        ]

        mocker.patch("app.services.s3.S3Service.download_file", return_value=_rows_to_csv_bytes(all_rows))

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.data_set_missing_data",
                grant_id=grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        )

        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert gr.organisation.name in response.text
        assert gr2.organisation.name not in response.text
        assert gr3.organisation.name in response.text

        assert soup.find("div", {"class": "govuk-error-summary"}) is None
        assert "Data missing" in soup.text
        assert "Grant recipient missing" in soup.text

        if has_grant_recipient_mismatches:
            assert page_has_link(soup, "Back").get("href") == url_for(
                "deliver_grant_funding.confirm_data_set_grant_recipients",
                grant_id=collection.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )
        else:
            assert page_has_link(soup, "Back").get("href") == url_for(
                "deliver_grant_funding.upload_data_set",
                grant_id=collection.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            )

    @pytest.mark.parametrize("session_data_name", [SESSION_DATA_SET_UPLOAD, SESSION_DATA_SET_REPLACE])
    def test_get_data_set_missing_data_with_no_missing_data_redirects(
        self, authenticated_grant_admin_client, factories, mocker, session_data_name
    ):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant)
        gr = factories.grant_recipient.create(
            grant=grant, organisation__external_id="E06000123", organisation__name="Rivendell"
        )
        gr2 = factories.grant_recipient.create(
            grant=grant, organisation__external_id="E06000456", organisation__name="Lothlorien"
        )

        with authenticated_grant_admin_client.session_transaction() as session:
            session[session_data_name] = {
                "name": "Test Data Set",
                "data_source_type": DataSourceType.GRANT_RECIPIENT,
                "data_columns": ["Capital allocation"],
                "preview_data": {},
                "column_mappings": [
                    DataSetColumnMapping(column_name="Capital allocation", column_type="BRITISH_POUNDS").model_dump(
                        mode="json"
                    ),
                ],
                "data_source_id": uuid.uuid4(),
                "original_filename": "test.csv",
                "s3_key": "data-set-uploads/test.csv",
            }

        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr.organisation.name,
                "Capital allocation": "£2000.00",
            },
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr2.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr2.organisation.name,
                "Capital allocation": "£1000.00",
            },
        ]

        mocker.patch("app.services.s3.S3Service.download_file", return_value=_rows_to_csv_bytes(all_rows))

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.data_set_missing_data",
                grant_id=grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            ),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "deliver_grant_funding.map_data_set_columns",
            grant_id=collection.grant.id,
            collection_type=CollectionType.MONITORING_REPORT,
            collection_id=collection.id,
        )

    @pytest.mark.parametrize("session_data_name", [SESSION_DATA_SET_UPLOAD, SESSION_DATA_SET_REPLACE])
    def test_post_redirects_to_map_columns(
        self, authenticated_grant_admin_client, factories, db_session, mock_s3_service_calls, mocker, session_data_name
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        grant_recipient = factories.grant_recipient.create(
            grant=authenticated_grant_admin_client.grant, organisation__external_id="E06000123"
        )
        grant_recipient_2 = factories.grant_recipient.create(
            grant=authenticated_grant_admin_client.grant, organisation__external_id="E06000456"
        )

        with authenticated_grant_admin_client.session_transaction() as session:
            session[session_data_name] = DataSetUploadSessionModel(
                name="Test Data Set",
                data_source_type=DataSourceType.GRANT_RECIPIENT,
                data_columns=["Capital allocation", "Revenue allocation"],
                preview_data={
                    DATA_SET_EXTERNAL_ID_COLUMN_HEADER: [
                        grant_recipient.organisation.external_id,
                        grant_recipient_2.organisation.external_id,
                    ],
                    DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: [
                        grant_recipient.organisation.name,
                        grant_recipient_2.organisation.name,
                    ],
                    "Capital allocation": [],
                    "Revenue allocation": ["£200.00"],
                },
                column_mappings=[
                    DataSetColumnMapping(column_name="Capital allocation", column_type="INTEGER"),
                    DataSetColumnMapping(column_name="Revenue allocation", column_type="BRITISH_POUNDS"),
                ],
                data_source_id=uuid.uuid4(),
                original_filename="test.csv",
                s3_key="data-set-uploads/test.csv",
                is_replace=session_data_name == SESSION_DATA_SET_REPLACE,
            ).model_dump(mode="json")

        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: grant_recipient.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: grant_recipient.organisation.name,
                "Capital allocation": "",
                "Revenue allocation": "",
            },
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: grant_recipient_2.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: grant_recipient_2.organisation.name,
                "Capital allocation": "",
                "Revenue allocation": "£200.00",
            },
        ]

        mocker.patch("app.services.s3.S3Service.download_file", return_value=_rows_to_csv_bytes(all_rows))

        data = {
            "submit": "y",
        }

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.data_set_missing_data",
                grant_id=collection.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
            ),
            data=data,
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "deliver_grant_funding.map_data_set_columns",
            grant_id=collection.grant.id,
            collection_type=CollectionType.MONITORING_REPORT,
            collection_id=collection.id,
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            data_set_data = sess.get(session_data_name)
            assert data_set_data is not None
            assert data_set_data["has_missing_data"] is True


class TestReplaceDataSet:
    def test_404(self, authenticated_grant_admin_client, factories, subtests):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant)
        data_source = factories.data_source.create(
            collection=collection, grant=grant, type=DataSourceType.GRANT_RECIPIENT
        )
        test_data = [
            (uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), "none exist"),
            (uuid.uuid4(), collection.id, data_source.id, "bad grant id"),
            (grant.id, uuid.uuid4(), data_source.id, "bad collection id"),
            (grant.id, collection.id, uuid.uuid4(), "bad data source id"),
        ]
        for data in test_data:
            with subtests.test(
                msg=f"Expected 404 with mismatched entity IDs: {data[3]}",
            ):
                response = authenticated_grant_admin_client.get(
                    url_for(
                        "deliver_grant_funding.replace_data_set",
                        grant_id=data[0],
                        collection_type=CollectionType.MONITORING_REPORT,
                        collection_id=data[1],
                        data_source_id=data[2],
                    )
                )
                assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get(self, client_fixture, can_access, request: FixtureRequest, factories):
        client = request.getfixturevalue(client_fixture)
        grant = client.grant
        collection = factories.collection.create(grant=grant)
        data_source = factories.data_source.create(
            collection=collection,
            grant=grant,
            type=DataSourceType.GRANT_RECIPIENT,
            name="access test",
        )

        response = client.get(
            url_for(
                "deliver_grant_funding.replace_data_set",
                grant_id=grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                data_source_id=data_source.id,
            )
        )

        soup = BeautifulSoup(response.data, "html.parser")
        if can_access:
            assert response.status_code == 200
            assert f"{collection.name} Replace access test data set" in get_h1_text(soup)
        else:
            assert response.status_code == 403

    @pytest.mark.parametrize(
        "new_name,valid",
        [
            ("data set two", False),
            ("data set three", True),
            ("data set one", True),
        ],
    )
    def test_duplicate_data_set_name(
        self, factories, authenticated_grant_admin_client, mock_s3_service_calls, new_name, valid
    ):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant)
        ds_1 = factories.data_source.create(
            collection=collection, grant=grant, type=DataSourceType.GRANT_RECIPIENT, name="data set one"
        )

        factories.data_source.create(
            collection=collection, grant=grant, type=DataSourceType.GRANT_RECIPIENT, name="data set two"
        )

        data = build_file_upload_form_data(
            csv_content=(f"{DATA_SET_EXTERNAL_ID_COLUMN_HEADER},{DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER},Allocation"),
            name=new_name,
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.replace_data_set",
                grant_id=grant.id,
                collection_type=ds_1.collection.type,
                collection_id=ds_1.collection.id,
                data_source_id=ds_1.id,
            ),
            data=data,
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        if valid:
            assert response.status_code == 302
            assert response.location == url_for(
                "deliver_grant_funding.confirm_data_set_grant_recipients",
                grant_id=grant.id,
                collection_type=collection.type,
                collection_id=collection.id,
            )
        else:
            assert response.status_code == 200
            assert page_has_error(
                BeautifulSoup(response.data, "html.parser"), "A data set with this name already exists"
            )

    def test_valid_upload_redirects(self, factories, authenticated_grant_admin_client, mock_s3_service_calls):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant)
        data_source = factories.data_source.create(
            collection=collection,
            grant=grant,
            type=DataSourceType.GRANT_RECIPIENT,
            has_column_of_each_type=True,
        )
        factories.grant_recipient.create(
            grant=grant,
            organisation__external_id="E123",
            organisation__name="Rivendell",
        )
        factories.grant_recipient.create(
            grant=grant,
            organisation__external_id="E456",
            organisation__name="Lothlorien",
        )

        data = build_file_upload_form_data(
            csv_content=(
                ALL_COLUMN_TYPE_HEADERS_STR
                + "\nE123,Rivendell,£100,1.2,hello,5,$10,12km"
                + "\nE456,Lothlorien,£100,1.2,hello,6,$10,12km"
            )
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.replace_data_set",
                grant_id=grant.id,
                collection_type=data_source.collection.type,
                collection_id=data_source.collection.id,
                data_source_id=data_source.id,
            ),
            data=data,
            content_type="multipart/form-data",
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "deliver_grant_funding.confirm_data_set_grant_recipients",
            grant_id=grant.id,
            collection_type=collection.type,
            collection_id=collection.id,
        )

    def test_upload_with_multiple_data_errors_shows_all(self, factories, authenticated_grant_admin_client):

        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant)
        data_source = factories.data_source.create(
            collection=collection,
            grant=grant,
            type=DataSourceType.GRANT_RECIPIENT,
            has_column_of_each_type=True,
        )
        factories.grant_recipient.create(
            grant=grant,
            organisation__external_id="E123",
            organisation__name="Rivendell",
        )
        factories.grant_recipient.create(
            grant=grant,
            organisation__external_id="E456",
            organisation__name="Lothlorien",
        )

        data = build_file_upload_form_data(
            csv_content=(
                ALL_COLUMN_TYPE_HEADERS_STR
                + "\nE123,Rivendell,£100,1.2123123,hello,5,$10,12km"
                + "\nE456,Lothlorien,£100abc,1.2,hello,5.9,$10,12km"
            )
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.replace_data_set",
                grant_id=grant.id,
                collection_type=data_source.collection.type,
                collection_id=data_source.collection.id,
                data_source_id=data_source.id,
            ),
            data=data,
            content_type="multipart/form-data",
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(
            soup,
            "One or more numbers in column 'British pounds' are not formatted as British pounds to 2 decimal places "
            + "with the '£' prefix. For example, £100.00",
        )
        assert page_has_error(soup, "One or more numbers in column 'Whole number' are not whole numbers")
        assert page_has_error(
            soup,
            "One or more numbers in column 'Decimal number' has more than 3 decimal places",
        )

    def test_upload_with_rogue_grant_recipients_shows_errors(
        self, factories, authenticated_grant_admin_client, mock_s3_service_calls
    ):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant)
        data_source = factories.data_source.create(
            collection=collection,
            grant=grant,
            type=DataSourceType.GRANT_RECIPIENT,
            has_column_of_each_type=True,
        )
        factories.grant_recipient.create(
            grant=grant,
            organisation__external_id="E123",
            organisation__name="Rivendell",
        )
        factories.grant_recipient.create(
            grant=grant,
            organisation__external_id="E456",
            organisation__name="Lothlorien",
        )

        data = build_file_upload_form_data(
            csv_content=(
                ALL_COLUMN_TYPE_HEADERS_STR
                + "\nXX1122,Rogue,£100,1.2,hello,5,$10,12km"
                + "\nE456,Lothlorien,£100,1.2,hello,6,$10,12km"
            )
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.replace_data_set",
                grant_id=grant.id,
                collection_type=data_source.collection.type,
                collection_id=data_source.collection.id,
                data_source_id=data_source.id,
            ),
            data=data,
            content_type="multipart/form-data",
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "Organisation ID 'XX1122' not found in grant recipients")

    def test_upload_with_mismatched_grant_recipients_redirects(
        self, factories, authenticated_grant_admin_client, mock_s3_service_calls
    ):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant)
        data_source = factories.data_source.create(
            collection=collection,
            grant=grant,
            type=DataSourceType.GRANT_RECIPIENT,
            has_column_of_each_type=True,
        )
        factories.grant_recipient.create(
            grant=grant,
            organisation__external_id="E123",
            organisation__name="Rivendell",
        )
        factories.grant_recipient.create(
            grant=grant,
            organisation__external_id="E456",
            organisation__name="Lothlorien",
        )

        data = build_file_upload_form_data(
            csv_content=(
                ALL_COLUMN_TYPE_HEADERS_STR
                + "\nE123,mismatch,£100,1.2,hello,5,$10,12km"
                + "\nE456,Lothlorien,£100,1.2,hello,6,$10,12km"
            )
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.replace_data_set",
                grant_id=grant.id,
                collection_type=data_source.collection.type,
                collection_id=data_source.collection.id,
                data_source_id=data_source.id,
            ),
            data=data,
            content_type="multipart/form-data",
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "deliver_grant_funding.confirm_data_set_grant_recipients",
            grant_id=grant.id,
            collection_type=collection.type,
            collection_id=collection.id,
        )


class TestViewDataSource:
    def test_404(self, authenticated_grant_member_client):
        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.view_data_source",
                grant_id=uuid.uuid4(),
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=uuid.uuid4(),
                data_source_id=uuid.uuid4(),
            )
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access, can_delete",
        (
            ("authenticated_no_role_client", False, False),
            ("authenticated_grant_member_client", True, False),
            ("authenticated_grant_admin_client", True, True),
        ),
    )
    def test_get_view_data_source(
        self, request: FixtureRequest, client_fixture: str, can_access: bool, can_delete: bool, factories
    ):
        client = request.getfixturevalue(client_fixture)
        grant = client.grant or factories.grant.create()
        collection = factories.collection.create(grant=grant, status=CollectionStatusEnum.DRAFT)
        data_source = factories.data_source.create(
            collection=collection,
            grant=grant,
            name="Test data set",
            created_at_utc=datetime.datetime(2026, 7, 1, 12, 0, 0),
            type=DataSourceType.GRANT_RECIPIENT,
        )

        response = client.get(
            url_for(
                "deliver_grant_funding.view_data_source",
                grant_id=grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                data_source_id=data_source.id,
            )
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert "Test data set" in get_h1_text(soup)
            uploaded_at = soup.find("time")
            assert uploaded_at.text == "1 Jul 2026 at 1pm", "Uploaded at UTC should be converted to local London"

            if can_delete:
                assert page_has_link(soup, "Delete data set")
            else:
                assert not page_has_link(soup, "Delete data set")

    def test_get_view_data_source_404_if_not_grant_recipient_level_data_set(
        self, authenticated_grant_member_client, factories
    ):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant)

        # Creates a CUSTOM data source by default so should 404
        data_source = factories.data_source.create(grant=authenticated_grant_member_client.grant, collection=collection)

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.view_data_source",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=collection.type,
                collection_id=collection.id,
                data_source_id=data_source.id,
            )
        )

        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_delete",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get_shows_delete_banner(self, request: FixtureRequest, client_fixture: str, can_delete: bool, factories):
        client = request.getfixturevalue(client_fixture)
        grant = client.grant or factories.grant.create()
        collection = factories.collection.create(grant=grant)
        data_source = factories.data_source.create(
            collection=collection,
            grant=grant,
            name="Test data set",
            type=DataSourceType.GRANT_RECIPIENT,
        )

        response = client.get(
            url_for(
                "deliver_grant_funding.view_data_source",
                grant_id=grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                data_source_id=data_source.id,
                delete="",
            )
        )

        soup = BeautifulSoup(response.data, "html.parser")

        if can_delete:
            assert response.status_code == 200
            assert page_has_button(soup, "Yes, delete this data set")
        else:
            assert response.status_code == 302
            assert response.location == url_for(
                "deliver_grant_funding.view_data_source",
                grant_id=grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                data_source_id=data_source.id,
            )

    def test_get_shows_summary_list_metadata(self, authenticated_grant_member_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant)
        user = factories.user.create()
        data_source = factories.data_source.create(
            collection=collection,
            grant=authenticated_grant_member_client.grant,
            name="Test data set",
            type=DataSourceType.GRANT_RECIPIENT,
            created_by=user,
        )

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.view_data_source",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                data_source_id=data_source.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert user.name in soup.text
        assert "Test data set" in soup.text

    def test_get_shows_grant_recipient_table(self, authenticated_grant_member_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant)
        organisation = authenticated_grant_member_client.grant_recipient.organisation
        data_source = factories.data_source.create(
            collection=collection,
            grant=authenticated_grant_member_client.grant,
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
            create_gr_org_items__data=[500_000],
        )

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.view_data_source",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                data_source_id=data_source.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert organisation.external_id in soup.text
        assert organisation.name in soup.text
        assert "Allocation" in soup.text
        assert "£500,000" in soup.text

    def test_get_shows_missing_data_tag_and_warning_for_empty_values(
        self, authenticated_grant_member_client, factories
    ):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant)
        data_source = factories.data_source.create(
            collection=collection,
            grant=authenticated_grant_member_client.grant,
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
            create_gr_org_items__data=[None],
        )

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.view_data_source",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                data_source_id=data_source.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Data missing" in soup.text
        assert (
            "Grant recipients with missing data will not be able to complete the report"
            " until their missing data is uploaded" in soup.text
        )

    def test_get_shows_missing_grant_recipient_tag_for_not_set_up_grant_recipient(
        self, authenticated_grant_member_client, factories
    ):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant)
        data_source = factories.data_source.create(
            collection=collection,
            grant=authenticated_grant_member_client.grant,
            type=DataSourceType.GRANT_RECIPIENT,
        )
        factories.data_source_organisation_item.create(
            data_source=data_source,
            external_id="E06000123",
            _data={"c_allocation": None},
        )

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.view_data_source",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                data_source_id=data_source.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Grant recipient not set up" in soup.text

    def test_get_excludes_test_grant_recipients_from_name_lookup(self, authenticated_grant_member_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant)
        organisation = factories.organisation.create(external_id="E06000123", name="Rivendell Council")
        factories.grant_recipient.create(
            grant=authenticated_grant_member_client.grant,
            organisation=organisation,
            mode=GrantRecipientModeEnum.LIVE,
        )
        test_organisation = factories.organisation.create(
            external_id="E06000123", name="Rivendell Council (Test)", mode=OrganisationModeEnum.TEST
        )
        factories.grant_recipient.create(
            grant=authenticated_grant_member_client.grant,
            organisation=test_organisation,
            mode=GrantRecipientModeEnum.TEST,
        )
        data_source = factories.data_source.create(
            collection=collection,
            grant=authenticated_grant_member_client.grant,
            type=DataSourceType.GRANT_RECIPIENT,
        )
        factories.data_source_organisation_item.create(
            data_source=data_source,
            external_id="E06000123",
            _data={"c_allocation": 1234},
        )

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.view_data_source",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                data_source_id=data_source.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Rivendell Council" in soup.text
        assert "Test Org Name" not in soup.text

    def test_post_delete_removes_data_source_and_redirects(
        self, authenticated_grant_admin_client, factories, db_session, mock_s3_service_calls
    ):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant)
        data_source = factories.data_source.create(
            grant=grant,
            collection=collection,
            name="My Data Set",
            type=DataSourceType.GRANT_RECIPIENT,
            items=None,
        )
        data_source_id = data_source.id

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.view_data_source",
                grant_id=grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                data_source_id=data_source_id,
                delete="",
            ),
            data={"confirm_deletion": "y"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "deliver_grant_funding.list_collection_data_sets",
            grant_id=grant.id,
            collection_type=CollectionType.MONITORING_REPORT,
            collection_id=collection.id,
        )
        assert db_session.get(DataSource, data_source_id) is None
        assert len(mock_s3_service_calls.delete_file_calls) == 1

    def test_post_delete_shows_flash_message(
        self, authenticated_grant_admin_client, factories, db_session, mock_s3_service_calls
    ):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant)
        data_source = factories.data_source.create(
            grant=grant,
            collection=collection,
            name="My Data Set",
            type=DataSourceType.GRANT_RECIPIENT,
            items=None,
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.view_data_source",
                grant_id=grant.id,
                collection_type=collection.type,
                collection_id=collection.id,
                data_source_id=data_source.id,
                delete="",
            ),
            data={"confirm_deletion": "y"},
            follow_redirects=True,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "'My Data Set' data set has been deleted.")

    def test_post_delete_removes_organisation_items(
        self, authenticated_grant_admin_client, factories, db_session, mock_s3_service_calls
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        factories.grant_recipient.create_batch(2, grant=collection.grant)
        data_source = factories.data_source.create(
            collection=collection,
            grant=authenticated_grant_admin_client.grant,
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
        )

        authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.view_data_source",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                data_source_id=data_source.id,
                delete="",
            ),
            data={"confirm_deletion": "y"},
            follow_redirects=False,
        )

        assert db_session.get(DataSource, data_source.id) is None
        assert db_session.scalar(select(func.count()).select_from(DataSourceOrganisationItem)) == 0

    def test_delete_blocked_when_column_is_referenced_shows_flash_before_confirmation(
        self, authenticated_grant_admin_client, factories, db_session, mock_s3_service_calls
    ):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant)
        data_source = factories.data_source.create(
            grant=grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
        )
        form = factories.form.create(collection=collection)
        question = factories.question.create(
            form=form,
            text=f"Your allocation is (({data_source.safe_did}.c_allocation))",
        )

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.view_data_source",
                grant_id=grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                data_source_id=data_source.id,
                delete="",
            ),
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert db_session.get(DataSource, data_source.id) is not None
        assert mock_s3_service_calls.delete_file_calls == []
        soup = BeautifulSoup(response.data, "html.parser")
        banner = page_has_flash(
            soup,
            "You cannot delete this data set because it's being referenced in the form. "
            "You need to remove references in:",
        )
        assert banner is not None
        # The confirmation banner must NOT be rendered when the deletion has already been blocked.
        assert "Are you sure you want to delete this data set?" not in soup.text
        links = banner.select(".govuk-notification-banner__link")
        assert len(links) == 1
        assert links[0]["href"] == url_for(
            "deliver_grant_funding.edit_question", grant_id=grant.id, question_id=question.id
        )
        assert "Your allocation is" in links[0].text
        assert "(Question)" in links[0].text

    def test_delete_blocked_links_to_group_when_reference_is_on_a_group(
        self, authenticated_grant_admin_client, factories, db_session, mock_s3_service_calls
    ):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant)
        data_source = factories.data_source.create(
            grant=grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
        )
        form = factories.form.create(collection=collection)
        group = factories.group.create(form=form, text=f"Allocation overview (({data_source.safe_did}.c_allocation))")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.view_data_source",
                grant_id=grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                data_source_id=data_source.id,
                delete="",
            ),
            follow_redirects=True,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        banner = page_has_flash(soup, "You cannot delete this data set")
        assert banner is not None
        links = banner.select(".govuk-notification-banner__link")
        assert len(links) == 1
        assert links[0]["href"] == url_for(
            "deliver_grant_funding.list_group_questions", grant_id=grant.id, group_id=group.id
        )
        assert "(Group)" in links[0].text

    def test_delete_blocked_labels_validation_and_question_refs_separately(
        self, authenticated_grant_admin_client, factories, db_session, mock_s3_service_calls
    ):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant)
        data_source = factories.data_source.create(
            grant=grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
        )
        form = factories.form.create(collection=collection)
        question = factories.question.create(
            form=form,
            data_type=QuestionDataType.NUMBER,
            text=f"How much did you spend? (({data_source.safe_did}.c_allocation))",
        )
        interfaces.collections.add_component_validation(
            question,
            authenticated_grant_admin_client.user,
            GreaterThan(
                subject_reference=ExpressionReference.from_question(question),
                minimum_value=None,
                minimum_expression=ExpressionReference.from_data_source_column(data_source, "c_allocation"),
            ),
        )

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.view_data_source",
                grant_id=grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                data_source_id=data_source.id,
                delete="",
            ),
            follow_redirects=True,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        banner = page_has_flash(soup, "You cannot delete this data set")
        assert banner is not None
        link_texts = [link.text.strip() for link in banner.select(".govuk-notification-banner__link")]
        assert any("(Question)" in t for t in link_texts)
        assert any("(Validation)" in t for t in link_texts)

    def test_delete_shows_confirmation_banner_when_data_set_has_no_references(
        self, authenticated_grant_admin_client, factories
    ):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=grant)
        data_source = factories.data_source.create(
            grant=grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
            items=None,
        )

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.view_data_source",
                grant_id=grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                data_source_id=data_source.id,
                delete="",
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Are you sure you want to delete this data set?" in soup.text
        assert page_has_flash(soup, "You cannot delete this data set") is None


class TestDownloadDataSourceCsv:
    def test_404(self, authenticated_grant_member_client):
        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.download_data_source_csv",
                grant_id=uuid.uuid4(),
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=uuid.uuid4(),
                data_source_id=uuid.uuid4(),
            )
        )
        assert response.status_code == 404

    def test_500_when_no_file_metadata(self, authenticated_grant_admin_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        data_source = factories.data_source.create(
            name="Test data set",
            collection=collection,
            grant=authenticated_grant_admin_client.grant,
            type=DataSourceType.GRANT_RECIPIENT,
            items=None,
            file_metadata=None,
        )
        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.download_data_source_csv",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                data_source_id=data_source.id,
            )
        )
        assert response.status_code == 500

    def test_404_when_data_source_doesnt_belong_to_collection(
        self, authenticated_grant_admin_client, factories, mock_s3_service_calls
    ):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)

        grant2 = factories.grant.create()
        collection2 = factories.collection.create(grant=grant2)
        data_source2 = factories.data_source.create(
            name="Test data set",
            collection=collection2,
            grant=grant2,
            type=DataSourceType.GRANT_RECIPIENT,
            items=None,
        )

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.download_data_source_csv",
                grant_id=grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                data_source_id=data_source2.id,
            )
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_member_client", True),
        ),
    )
    def test_get_access(
        self, request: FixtureRequest, client_fixture: str, can_access: bool, factories, mock_s3_service_calls
    ):
        client = request.getfixturevalue(client_fixture)
        grant = client.grant or factories.grant.create()
        collection = factories.collection.create(grant=grant)
        data_source = factories.data_source.create(
            name="Test data set",
            collection=collection,
            grant=grant,
            type=DataSourceType.GRANT_RECIPIENT,
            items=None,
        )
        response = client.get(
            url_for(
                "deliver_grant_funding.download_data_source_csv",
                grant_id=grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                data_source_id=data_source.id,
            )
        )
        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200

    def test_get_returns_file_with_correct_name_and_content(
        self, authenticated_grant_admin_client, factories, mock_s3_service_calls
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        data_source = factories.data_source.create(
            name="Test data set",
            collection=collection,
            grant=authenticated_grant_admin_client.grant,
            type=DataSourceType.GRANT_RECIPIENT,
            items=None,
            file_metadata=DataSourceFileMetadata(s3_key="data-set-uploads/test.csv", original_filename="test.csv"),
        )

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.download_data_source_csv",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                data_source_id=data_source.id,
            )
        )

        assert response.status_code == 200
        assert response.content_type.startswith("text/csv")
        assert "filename=test.csv" in response.headers["Content-Disposition"]
        assert response.data == b"mocked file content"

        assert len(mock_s3_service_calls.download_file_calls) == 1
        assert mock_s3_service_calls.download_file_calls[0].args[0] == "data-set-uploads/test.csv"


class TestDownloadLatestDataSetTemplate:
    def test_404(self, authenticated_grant_member_client):
        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.download_latest_data_set_template",
                grant_id=uuid.uuid4(),
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=uuid.uuid4(),
                data_source_id=uuid.uuid4(),
            )
        )
        assert response.status_code == 404

    def test_404_when_data_source_doesnt_belong_to_collection(
        self, authenticated_grant_admin_client, factories, mock_s3_service_calls
    ):
        grant = authenticated_grant_admin_client.grant
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)

        grant2 = factories.grant.create()
        collection2 = factories.collection.create(grant=grant2)
        data_source2 = factories.data_source.create(
            name="Test data set",
            collection=collection2,
            grant=grant2,
            type=DataSourceType.GRANT_RECIPIENT,
        )

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.download_latest_data_set_template",
                grant_id=grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                data_source_id=data_source2.id,
            )
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_member_client", True),
        ),
    )
    def test_get_access(
        self, request: FixtureRequest, client_fixture: str, can_access: bool, factories, mock_s3_service_calls
    ):
        client = request.getfixturevalue(client_fixture)
        grant = client.grant or factories.grant.create()
        collection = factories.collection.create(grant=grant)
        _ = client.grant_recipient or factories.grant_recipient.create(grant=grant)
        data_source = factories.data_source.create(
            name="Test data set",
            collection=collection,
            grant=grant,
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
        )
        response = client.get(
            url_for(
                "deliver_grant_funding.download_latest_data_set_template",
                grant_id=grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                data_source_id=data_source.id,
            )
        )
        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200

    def test_get_returns_file_with_correct_name_and_content(
        self, authenticated_grant_admin_client, factories, mock_s3_service_calls
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        grant = authenticated_grant_admin_client.grant
        factories.grant_recipient.create(
            grant=grant, organisation__external_id="E06000123", organisation__name="Test org"
        )
        data_source = factories.data_source.create(
            collection=collection,
            grant=authenticated_grant_admin_client.grant,
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
            create_gr_org_items__data=[1000],
        )

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.download_latest_data_set_template",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
                collection_id=collection.id,
                data_source_id=data_source.id,
            )
        )

        assert response.status_code == 200
        assert response.content_type.startswith("text/csv")
        assert f"filename={collection.slug}-grant-allocation-template.csv" in response.headers["Content-Disposition"]
        assert b"Organisation ID,Grant recipient,Allocation\r\nE06000123,Test org,1000" in response.data


class TestAddCustomQuestionValidation:
    def test_post_success(self, authenticated_platform_admin_client, factories, db_session):
        collection = factories.collection.create(name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        q1, q2, q3 = factories.question.create_batch(
            3,
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )

        assert len(q3.expressions) == 0

        form = CustomValidationExpressionForm(
            data={
                "custom_expression": f"(({q3.safe_qid})) <= (({q1.safe_qid})) + (({q2.safe_qid})) ",
                "custom_message": f"Failed custom validation, needs to be less than (({q1.safe_qid})) + "
                f"(({q2.safe_qid}))",
            },
            component=q3,
            interpolation_context=ExpressionContext(),
            evaluation_context=ExpressionContext(),
        )

        response = authenticated_platform_admin_client.post(
            url_for(
                "deliver_grant_funding.add_custom_question_validation",
                grant_id=collection.grant.id,
                question_id=q3.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(rf"/deliver/grant/{collection.grant.id}/question/{q3.id}")

        assert len(q3.expressions) == 1
        expression = q3.expressions[0]
        assert expression.type_ == ExpressionType.VALIDATION
        assert expression.managed_name is None

    def test_post_error_in_expression(self, authenticated_platform_admin_client, factories, db_session):
        collection = factories.collection.create(name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        q1, q2, q3 = factories.question.create_batch(
            3,
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )
        q4 = factories.question.create(
            name="Later question name",
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )

        assert len(q3.expressions) == 0

        form = CustomValidationExpressionForm(
            data={
                "custom_expression": f"(({q3.safe_qid})) <= (({q1.safe_qid})) + (({q4.safe_qid})) ",
                "custom_message": f"Failed custom validation, needs to be less than (({q1.safe_qid})) + "
                f"(({q2.safe_qid}))",
            },
            component=q3,
            interpolation_context=ExpressionContext(),
            evaluation_context=ExpressionContext(),
        )

        response = authenticated_platform_admin_client.post(
            url_for(
                "deliver_grant_funding.add_custom_question_validation",
                grant_id=collection.grant.id,
                question_id=q3.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")

        assert len(q3.expressions) == 0
        assert page_has_error(
            soup,
            "You cannot use Later question name because it comes after this question",
        )
        assert soup.find("p", id="custom_expression-error") is not None

    def test_post_error_in_message(self, authenticated_platform_admin_client, factories, db_session):
        collection = factories.collection.create(name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        q1, q2, q3 = factories.question.create_batch(
            3,
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )

        assert len(q3.expressions) == 0

        form = CustomValidationExpressionForm(
            data={
                "custom_expression": f"(({q3.safe_qid})) <= (({q1.safe_qid})) + (({q2.safe_qid})) ",
                "custom_message": f"Failed custom validation, needs to be less than (({q1.safe_qid})) + "
                f"((bad_reference))",
            },
            component=q3,
            interpolation_context=ExpressionContext(),
            evaluation_context=ExpressionContext(),
        )

        response = authenticated_platform_admin_client.post(
            url_for(
                "deliver_grant_funding.add_custom_question_validation",
                grant_id=collection.grant.id,
                question_id=q3.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 200

        assert len(q3.expressions) == 0

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(
            soup,
            "You cannot use ((bad_reference)) because it does not exist",
        )
        assert soup.find("p", id="custom_message-error") is not None

    def test_post_error_in_expression_and_message(self, authenticated_platform_admin_client, factories, db_session):
        collection = factories.collection.create(name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        q1, q2, q3 = factories.question.create_batch(
            3,
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )
        q4 = factories.question.create(
            name="Later question name",
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )

        assert len(q3.expressions) == 0

        form = CustomValidationExpressionForm(
            data={
                "custom_expression": f"(({q3.safe_qid})) <= (({q1.safe_qid})) + (({q2.safe_qid}))",
                "custom_message": f"Failed custom validation, needs to be less than (({q1.safe_qid})) + "
                f"(({q4.safe_qid}))",
            },
            component=q3,
            interpolation_context=ExpressionContext(),
            evaluation_context=ExpressionContext(),
        )

        response = authenticated_platform_admin_client.post(
            url_for(
                "deliver_grant_funding.add_custom_question_validation",
                grant_id=collection.grant.id,
                question_id=q3.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 200

        assert len(q3.expressions) == 0
        assert page_has_error(
            BeautifulSoup(response.data, "html.parser"),
            "You cannot use Later question name because it comes after this question",
        )

    def test_post_to_add_context(self, authenticated_platform_admin_client, factories, db_session):
        collection = factories.collection.create(name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        q1, q2 = factories.question.create_batch(
            2,
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )

        assert len(q2.expressions) == 0

        form = CustomValidationExpressionForm(
            data={
                "custom_expression": f"(({q1.safe_qid})) <=",
                "custom_message": "Failed custom validation...",
                "add_context": "custom_expression",
            },
            component=q2,
            interpolation_context=ExpressionContext(),
            evaluation_context=ExpressionContext(),
        )

        response = authenticated_platform_admin_client.post(
            url_for(
                "deliver_grant_funding.add_custom_question_validation",
                grant_id=collection.grant.id,
                question_id=q2.id,
            ),
            data=get_form_data(form, submit=""),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            "^/deliver/grant/[a-z0-9-]{36}/section/[a-z0-9-]{36}/add-context/select-source$"
        )
        assert len(q2.expressions) == 0

        with authenticated_platform_admin_client.session_transaction() as session:
            assert session["question"]["field"] == ExpressionType.VALIDATION
            assert session["question"]["expression_form_data"]["custom_expression"] == f"(({q1.safe_qid})) <="
            assert session["question"]["expression_form_data"]["custom_message"] == "Failed custom validation..."


class TestEditCustomQuestionValidation:
    def test_get(self, authenticated_platform_admin_client, factories, db_session):
        collection = factories.collection.create(name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        q1, q2 = factories.question.create_batch(
            2,
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )
        q3 = factories.question.create(
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )
        interfaces.collections.add_component_validation(
            q3,
            authenticated_platform_admin_client.user,
            CustomExpression(
                custom_expression="True",
                custom_message="Failed",
            ),
        )

        assert len(q3.expressions) == 1

        response = authenticated_platform_admin_client.get(
            url_for(
                "deliver_grant_funding.edit_custom_question_validation",
                grant_id=collection.grant.id,
                question_id=q3.id,
                expression_id=q3.expressions[0].id,
            ),
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert soup.find("h1").text == "Edit a calculated validation"

        assert soup.find("textarea", id="custom_expression").text == "True"
        assert soup.find("textarea", id="custom_message").text == "Failed"

    def test_post_success(self, authenticated_platform_admin_client, factories, db_session):
        collection = factories.collection.create(name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        q1, q2 = factories.question.create_batch(
            2,
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )
        q3 = factories.question.create(
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )
        interfaces.collections.add_component_validation(
            q3,
            authenticated_platform_admin_client.user,
            CustomExpression(
                custom_expression="True",
                custom_message="Failed",
            ),
        )

        assert len(q3.expressions) == 1
        expression = q3.expressions[0]
        assert len(expression.component_references) == 0
        form = CustomValidationExpressionForm(
            data={
                "custom_expression": f"(({q3.safe_qid})) <= (({q1.safe_qid})) + (({q2.safe_qid})) ",
                "custom_message": f"Failed custom validation, needs to be less than (({q1.safe_qid})) + "
                f"(({q2.safe_qid}))",
            },
            component=q3,
            interpolation_context=ExpressionContext(),
            evaluation_context=ExpressionContext(),
        )

        response = authenticated_platform_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_custom_question_validation",
                grant_id=collection.grant.id,
                question_id=q3.id,
                expression_id=q3.expressions[0].id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(rf"/deliver/grant/{collection.grant.id}/question/{q3.id}")

        assert len(q3.expressions) == 1
        expression = q3.expressions[0]
        assert len(expression.component_references) == 2

    def test_post_error_in_expression_and_message(self, authenticated_platform_admin_client, factories, db_session):
        collection = factories.collection.create(name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        q1, q2, q3 = factories.question.create_batch(
            3,
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )
        q4 = factories.question.create(
            name="Later question name",
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )
        interfaces.collections.add_component_validation(
            q3,
            authenticated_platform_admin_client.user,
            CustomExpression(
                custom_expression="True",
                custom_message="Failed",
            ),
        )

        assert len(q3.expressions) == 1
        expression = q3.expressions[0]
        assert len(expression.component_references) == 0
        form = CustomValidationExpressionForm(
            data={
                "custom_expression": f"(({q3.safe_qid})) <= (({q1.safe_qid})) + (({q2.safe_qid}))",
                "custom_message": f"Failed custom validation, needs to be less than (({q1.safe_qid})) + "
                f"(({q4.safe_qid}))",
            },
            component=q3,
            interpolation_context=ExpressionContext(),
            evaluation_context=ExpressionContext(),
        )

        response = authenticated_platform_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_custom_question_validation",
                grant_id=collection.grant.id,
                question_id=q3.id,
                expression_id=expression.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 200

        assert len(q3.expressions) == 1
        expression = q3.expressions[0]
        assert len(expression.component_references) == 0
        assert page_has_error(
            BeautifulSoup(response.data, "html.parser"),
            "You cannot use Later question name because it comes after this question",
        )

    def test_post_to_add_context(self, authenticated_platform_admin_client, factories, db_session):
        collection = factories.collection.create(name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        q1, q2 = factories.question.create_batch(
            2,
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )
        interfaces.collections.add_component_validation(
            q2,
            authenticated_platform_admin_client.user,
            CustomExpression(
                custom_expression="True",
                custom_message="Failed",
            ),
        )

        assert len(q2.expressions) == 1

        form = CustomValidationExpressionForm(
            data={
                "custom_expression": f"(({q1.safe_qid})) <=",
                "custom_message": "Failed custom validation...",
                "add_context": "custom_expression",
            },
            component=q2,
            interpolation_context=ExpressionContext(),
            evaluation_context=ExpressionContext(),
        )

        response = authenticated_platform_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_custom_question_validation",
                grant_id=collection.grant.id,
                question_id=q2.id,
                expression_id=q2.expressions[0].id,
            ),
            data=get_form_data(form, submit=""),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            "^/deliver/grant/[a-z0-9-]{36}/section/[a-z0-9-]{36}/add-context/select-source$"
        )
        assert len(q2.expressions) == 1

        with authenticated_platform_admin_client.session_transaction() as session:
            assert session["question"]["field"] == ExpressionType.VALIDATION
            assert session["question"]["expression_form_data"]["custom_expression"] == f"(({q1.safe_qid})) <="
            assert session["question"]["expression_form_data"]["custom_message"] == "Failed custom validation..."


class TestAddGroupValidation:
    def _make_same_page_group_with_questions(self, factories, grant):
        collection = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        group = factories.group.create(
            form=db_form,
            name="Spend totals",
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True),
        )
        capital = factories.question.create(
            form=db_form,
            parent=group,
            name="Capital spend",
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )
        revenue = factories.question.create(
            form=db_form,
            parent=group,
            name="Revenue spend",
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )
        return group, capital, revenue

    def test_get(self, authenticated_grant_admin_client, factories, db_session):
        group, _, _ = self._make_same_page_group_with_questions(factories, authenticated_grant_admin_client.grant)

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.add_group_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Create a group validation"

    def test_get_redirects_when_group_is_not_same_page(self, authenticated_grant_admin_client, factories, db_session):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        group = factories.group.create(
            form=db_form,
            name="Per-page group",
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=False),
        )

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.add_group_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
            ),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(rf"/deliver/grant/[a-z0-9-]{{36}}/group/{group.id}/questions")

    def test_post_success_referencing_questions_within_group(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        group, capital, revenue = self._make_same_page_group_with_questions(
            factories, authenticated_grant_admin_client.grant
        )

        form = CustomValidationExpressionForm(
            data={
                "custom_expression": f"(({capital.safe_qid})) + (({revenue.safe_qid})) <= 1000",
                "custom_message": "Capital plus revenue must not exceed 1000",
            },
            component=group,
            interpolation_context=ExpressionContext(),
            evaluation_context=ExpressionContext(),
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_group_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(rf"/deliver/grant/[a-z0-9-]{{36}}/group/{group.id}/questions")

        db_session.expire_all()
        reloaded = db_session.get(Group, group.id)
        assert len(reloaded.validations) == 1
        validation = reloaded.validations[0]
        assert validation.type_ == ExpressionType.VALIDATION
        assert validation.managed_name is None
        referenced_ids = {ref.depends_on_component_id for ref in validation.component_references}
        assert referenced_ids == {capital.id, revenue.id}

    def test_post_to_add_context_stores_is_group_in_session(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        group, capital, _ = self._make_same_page_group_with_questions(factories, authenticated_grant_admin_client.grant)

        form = CustomValidationExpressionForm(
            data={
                "custom_expression": f"(({capital.safe_qid})) <= ",
                "custom_message": "Failed custom validation...",
                "add_context": "custom_expression",
            },
            component=group,
            interpolation_context=ExpressionContext(),
            evaluation_context=ExpressionContext(),
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_group_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
            ),
            data=get_form_data(form, submit=""),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            "^/deliver/grant/[a-z0-9-]{36}/section/[a-z0-9-]{36}/add-context/select-source$"
        )

        with authenticated_grant_admin_client.session_transaction() as session:
            assert session["question"]["field"] == ExpressionType.VALIDATION
            assert session["question"]["is_group"] is True
            assert session["question"]["component_id"] == str(group.id)

    def test_post_error_when_referencing_question_after_group(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        group, capital, _ = self._make_same_page_group_with_questions(factories, authenticated_grant_admin_client.grant)
        question_after_group = factories.question.create(
            form=group.form,
            name="Later question name",
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )

        form = CustomValidationExpressionForm(
            data={
                "custom_expression": f"(({capital.safe_qid})) + (({question_after_group.safe_qid})) <= 1000",
                "custom_message": "Capital plus later question must not exceed 1000",
            },
            component=group,
            interpolation_context=ExpressionContext(),
            evaluation_context=ExpressionContext(),
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_group_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 200
        assert page_has_error(
            BeautifulSoup(response.data, "html.parser"),
            "You cannot use Later question name because it comes after this question group",
        )

        db_session.expire_all()
        reloaded = db_session.get(Group, group.id)
        assert reloaded.validations == []


class TestEditGroupValidation:
    def _setup_group_with_validation(self, factories, grant):
        collection = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        group = factories.group.create(
            form=db_form,
            name="Spend totals",
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True),
        )
        capital = factories.question.create(
            form=db_form,
            parent=group,
            name="Capital spend",
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )
        user = factories.user.create()
        add_component_validation(
            group,
            user,
            CustomExpression(
                custom_expression=EvaluationStatement(f"(({capital.safe_qid})) > 0"),
                custom_message=InterpolationStatement("Must be positive"),
            ),
        )
        return group, capital

    def test_get(self, authenticated_grant_admin_client, factories, db_session):
        group, _capital = self._setup_group_with_validation(factories, authenticated_grant_admin_client.grant)

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.edit_group_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
                expression_id=group.validations[0].id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Edit a group validation"

    def test_post_delete(self, authenticated_grant_admin_client, factories, db_session):
        group, _capital = self._setup_group_with_validation(factories, authenticated_grant_admin_client.grant)
        expression_id = group.validations[0].id

        confirm_form = GenericConfirmDeletionForm(data={"confirm_deletion": "y"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_group_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
                expression_id=expression_id,
                delete="",
            ),
            data=get_form_data(confirm_form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(rf"/deliver/grant/[a-z0-9-]{{36}}/group/{group.id}/questions")

        db_session.expire_all()
        reloaded = db_session.get(Group, group.id)
        assert reloaded.validations == []

    def test_get_with_delete_query_renders_confirm_banner(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        group, _capital = self._setup_group_with_validation(factories, authenticated_grant_admin_client.grant)
        expression_id = group.validations[0].id

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.edit_group_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
                expression_id=expression_id,
                delete="",
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Are you sure you want to delete this group validation?" in soup.text
        assert page_has_button(soup, "Yes, delete this validation")

    def test_post_success(self, authenticated_grant_admin_client, factories, db_session):
        group, capital = self._setup_group_with_validation(factories, authenticated_grant_admin_client.grant)
        revenue = factories.question.create(
            form=group.form,
            parent=group,
            name="Revenue spend",
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )
        expression = group.validations[0]

        form = CustomValidationExpressionForm(
            data={
                "custom_expression": f"(({capital.safe_qid})) + (({revenue.safe_qid})) <= 1000",
                "custom_message": "Capital plus revenue must not exceed 1000",
            },
            component=group,
            interpolation_context=ExpressionContext(),
            evaluation_context=ExpressionContext(),
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_group_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
                expression_id=expression.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(rf"/deliver/grant/[a-z0-9-]{{36}}/group/{group.id}/questions")

        db_session.expire_all()
        reloaded = db_session.get(Group, group.id)
        assert len(reloaded.validations) == 1
        updated_expression = reloaded.validations[0]
        assert updated_expression.id == expression.id
        assert updated_expression.statement == f"(({capital.safe_qid})) + (({revenue.safe_qid})) <= 1000"
        referenced_ids = {ref.depends_on_component_id for ref in updated_expression.component_references}
        assert referenced_ids == {capital.id, revenue.id}

    def test_post_404_when_expression_belongs_to_a_question(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        group, _capital = self._setup_group_with_validation(factories, authenticated_grant_admin_client.grant)
        question = factories.question.create(
            form=group.form,
            name="Standalone question",
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )
        add_component_validation(
            question,
            factories.user.create(),
            CustomExpression(
                custom_expression=EvaluationStatement(f"(({question.safe_qid})) > 0"),
                custom_message=InterpolationStatement("Must be positive"),
            ),
        )
        question_expression_id = question.expressions[0].id

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.edit_group_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
                expression_id=question_expression_id,
            )
        )

        assert response.status_code == 404

    def test_post_404_when_expression_belongs_to_a_different_group(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        group, _ = self._setup_group_with_validation(factories, authenticated_grant_admin_client.grant)
        other_group = factories.group.create(
            form=group.form,
            name="Other group",
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True),
        )
        other_question = factories.question.create(
            form=group.form,
            parent=other_group,
            name="Other capital",
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )
        add_component_validation(
            other_group,
            factories.user.create(),
            CustomExpression(
                custom_expression=EvaluationStatement(f"(({other_question.safe_qid})) > 0"),
                custom_message=InterpolationStatement("Must be positive"),
            ),
        )
        other_expression_id = other_group.validations[0].id

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.edit_group_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
                expression_id=other_expression_id,
            )
        )

        assert response.status_code == 404

    def test_post_to_add_context_stores_expression_id_and_is_group_in_session(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        group, capital = self._setup_group_with_validation(factories, authenticated_grant_admin_client.grant)
        expression = group.validations[0]

        form = CustomValidationExpressionForm(
            data={
                "custom_expression": f"(({capital.safe_qid})) <= ",
                "custom_message": "Failed custom validation...",
                "add_context": "custom_expression",
            },
            component=group,
            interpolation_context=ExpressionContext(),
            evaluation_context=ExpressionContext(),
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_group_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
                expression_id=expression.id,
            ),
            data=get_form_data(form, submit=""),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            "^/deliver/grant/[a-z0-9-]{36}/section/[a-z0-9-]{36}/add-context/select-source$"
        )

        with authenticated_grant_admin_client.session_transaction() as session:
            assert session["question"]["field"] == ExpressionType.VALIDATION
            assert session["question"]["is_group"] is True
            assert session["question"]["component_id"] == str(group.id)
            assert session["question"]["expression_id"] == str(expression.id)

    def test_post_error_when_referencing_question_after_group(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        group, capital = self._setup_group_with_validation(factories, authenticated_grant_admin_client.grant)
        expression = group.validations[0]
        question_after_group = factories.question.create(
            form=group.form,
            name="Later question name",
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )

        form = CustomValidationExpressionForm(
            data={
                "custom_expression": f"(({capital.safe_qid})) + (({question_after_group.safe_qid})) <= 1000",
                "custom_message": "Capital plus later question must not exceed 1000",
            },
            component=group,
            interpolation_context=ExpressionContext(),
            evaluation_context=ExpressionContext(),
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_group_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
                expression_id=expression.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 200
        assert page_has_error(
            BeautifulSoup(response.data, "html.parser"),
            "You cannot use Later question name because it comes after this question group",
        )

        db_session.expire_all()
        reloaded = db_session.get(Group, group.id)
        assert len(reloaded.validations) == 1
        assert reloaded.validations[0].statement == f"(({capital.safe_qid})) > 0"


class TestListGroupQuestionsValidationsSection:
    def test_section_renders_validations_when_same_page(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        group = factories.group.create(
            form=db_form,
            name="Spend totals",
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True),
        )
        question = factories.question.create(
            form=db_form,
            parent=group,
            name="Capital spend",
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )
        add_component_validation(
            group,
            factories.user.create(),
            CustomExpression(
                custom_expression=EvaluationStatement(f"(({question.safe_qid})) > 0"),
                custom_message=InterpolationStatement("Must be positive"),
            ),
        )

        response = authenticated_platform_admin_client.get(
            url_for(
                "deliver_grant_funding.list_group_questions",
                grant_id=grant.id,
                group_id=group.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert any("Validations" == h.get_text(strip=True) for h in soup.find_all("h2"))
        assert page_has_link(soup, "Add more validation") is not None
        assert "Must be positive" in soup.text

    def test_section_renders_placeholder_when_not_same_page(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        group = factories.group.create(
            form=db_form,
            name="Per-page group",
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=False),
        )
        factories.question.create(form=db_form, parent=group)

        response = authenticated_platform_admin_client.get(
            url_for(
                "deliver_grant_funding.list_group_questions",
                grant_id=grant.id,
                group_id=group.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert any("Validations" == h.get_text(strip=True) for h in soup.find_all("h2"))
        assert (
            "You can only add validations to a question group when questions are displayed on the same page."
        ) in soup.text
        assert page_has_link(soup, "Add validation") is None
        assert page_has_link(soup, "Add more validation") is None


class TestChangeGroupDisplayOptionsBlockedByValidations:
    def test_post_change_to_one_per_page_blocked_when_validations_exist(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=collection, title="Organisation information")
        group = factories.group.create(
            form=db_form,
            name="Spend totals",
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True),
        )
        question = factories.question.create(
            form=db_form,
            parent=group,
            name="Capital spend",
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )
        add_component_validation(
            group,
            factories.user.create(),
            CustomExpression(
                custom_expression=EvaluationStatement(f"(({question.safe_qid})) > 0"),
                custom_message=InterpolationStatement("Must be positive"),
            ),
        )

        form = GroupDisplayOptionsForm(data={"show_questions_on_the_same_page": "one-question-per-page"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.change_group_display_options",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(
            soup,
            "A question group cannot display one question per page while it has validation rules attached. "
            "Delete the group validations first.",
        )

        db_session.expire_all()
        reloaded = db_session.get(Group, group.id)
        assert reloaded.presentation_options.show_questions_on_the_same_page is True


class TestDetermineReturnUrlExpressionReference:
    def test_update_target_field_replace(self, factories):
        question = factories.question.create()
        add_context_data = AddContextToExpressionsModel(
            field=ExpressionType.CONDITION,
            component_id=question.id,
            managed_expression_name=ManagedExpressionsEnum.GREATER_THAN,
            expression_form_data={
                "test_field": "start",
                "add_context": "test_field",
            },
            subject_reference=ExpressionReference.from_question(question),
        )

        _determine_return_url_and_update_session_after_choosing_reference_for_expression(
            uuid.uuid4(), add_context_data, ExpressionReference.from_question(question)
        )

        assert add_context_data.expression_form_data["test_field"] == f"(({question.safe_qid}))"

    def test_update_target_field_append(self, factories):
        question = factories.question.create()
        add_context_data = AddContextToExpressionsModel(
            field=ExpressionType.CONDITION,
            component_id=question.id,
            managed_expression_name=None,
            expression_form_data={
                "test_field": "start +",
                "add_context": "test_field",
            },
        )

        _determine_return_url_and_update_session_after_choosing_reference_for_expression(
            uuid.uuid4(), add_context_data, ExpressionReference.from_question(question)
        )

        assert add_context_data.expression_form_data["test_field"] == f"start + (({question.safe_qid}))"

    def test_return_url_new_non_calculated_condition(self, factories):
        question = factories.question.create()
        add_context_data = AddContextToExpressionsModel(
            field=ExpressionType.CONDITION,
            component_id=question.id,
            managed_expression_name=ManagedExpressionsEnum.GREATER_THAN,
            expression_form_data={
                "test_field": "start + ",
                "add_context": "test_field",
            },
            subject_reference=ExpressionReference.from_question(question),
        )

        result = _determine_return_url_and_update_session_after_choosing_reference_for_expression(
            uuid.uuid4(), add_context_data, ExpressionReference.from_question(question)
        )
        assert result == AnyStringMatching(
            "^/deliver/grant/[a-z0-9-]{36}/question/[a-z0-9-]{36}/add-condition/q_[0-9a-f]{32}"
        )

    def test_return_url_existing_non_calculated_condition(self, factories):
        question = factories.question.create()
        add_context_data = AddContextToExpressionsModel(
            field=ExpressionType.CONDITION,
            component_id=question.id,
            managed_expression_name=ManagedExpressionsEnum.GREATER_THAN,
            expression_form_data={
                "test_field": "start + ",
                "add_context": "test_field",
            },
            subject_reference=ExpressionReference.from_question(question),
            expression_id=uuid.uuid4(),
        )

        result = _determine_return_url_and_update_session_after_choosing_reference_for_expression(
            uuid.uuid4(), add_context_data, ExpressionReference.from_question(question)
        )
        assert result == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/condition/[a-z0-9-]{36}")

    def test_return_url_new_calculated_condition(self, factories):
        question = factories.question.create()
        add_context_data = AddContextToExpressionsModel(
            field=ExpressionType.CONDITION,
            component_id=question.id,
            managed_expression_name=None,
            expression_form_data={
                "test_field": "start + ",
                "add_context": "test_field",
            },
        )

        result = _determine_return_url_and_update_session_after_choosing_reference_for_expression(
            uuid.uuid4(), add_context_data, ExpressionReference.from_question(question)
        )
        assert result == AnyStringMatching(
            "^/deliver/grant/[a-z0-9-]{36}/question/[a-z0-9-]{36}/add-calculated-condition"
        )

    def test_return_url_existing_calculated_condition(self, factories):
        question = factories.question.create()
        add_context_data = AddContextToExpressionsModel(
            field=ExpressionType.CONDITION,
            component_id=question.id,
            managed_expression_name=None,
            expression_form_data={
                "test_field": "start + ",
                "add_context": "test_field",
            },
            expression_id=uuid.uuid4(),
        )

        result = _determine_return_url_and_update_session_after_choosing_reference_for_expression(
            uuid.uuid4(), add_context_data, ExpressionReference.from_question(question)
        )
        assert result == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/calculated-condition/[a-z0-9-]{36}")


class TestChooseCollectionCreationMethod:
    @pytest.mark.parametrize("collection_type", CollectionType)
    def test_redirects_to_set_up_when_no_collections_to_copy(
        self, authenticated_grant_admin_client, collection_type, factories
    ):
        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.choose_collection_creation_method",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=collection_type,
            )
        )

        assert response.status_code == 302
        assert (
            url_for(
                "deliver_grant_funding.set_up_collection",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=collection_type,
            )
            in response.location
        )

    @pytest.mark.parametrize("collection_type", CollectionType)
    def test_get_renders_form_when_collections_exist(
        self, authenticated_grant_admin_client, collection_type, factories
    ):
        factories.collection.create(grant=authenticated_grant_admin_client.grant, type=collection_type)

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.choose_collection_creation_method",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=collection_type,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_button(soup, "Continue")

    def test_403_for_non_admin(self, authenticated_grant_member_client, factories):
        factories.collection.create(
            grant=authenticated_grant_member_client.grant, type=CollectionType.MONITORING_REPORT
        )

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.choose_collection_creation_method",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
            )
        )

        assert response.status_code == 403

    @pytest.mark.parametrize("collection_type", CollectionType)
    def test_post_copy_redirects_to_select_collection(
        self, authenticated_grant_admin_client, collection_type, factories
    ):
        factories.collection.create(grant=authenticated_grant_admin_client.grant, type=collection_type)

        form = CollectionCreationMethodForm(data={"method": "copy"}, collection_type=collection_type)
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.choose_collection_creation_method",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=collection_type,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert (
            url_for(
                "deliver_grant_funding.select_collection_to_copy",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=collection_type,
            )
            in response.location
        )

    @pytest.mark.parametrize("collection_type", CollectionType)
    def test_post_create_redirects_to_set_up(self, authenticated_grant_admin_client, collection_type, factories):
        factories.collection.create(grant=authenticated_grant_admin_client.grant, type=collection_type)

        form = CollectionCreationMethodForm(data={"method": "create"}, collection_type=collection_type)
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.choose_collection_creation_method",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=collection_type,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert (
            url_for(
                "deliver_grant_funding.set_up_collection",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=collection_type,
            )
            in response.location
        )

    def test_post_without_selection_shows_error(self, authenticated_grant_admin_client, factories):
        factories.collection.create(grant=authenticated_grant_admin_client.grant, type=CollectionType.MONITORING_REPORT)

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.choose_collection_creation_method",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
            ),
            data={"submit": "y"},
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "Select how you want to create the report")


class TestSelectCollectionToCopy:
    @pytest.mark.parametrize("collection_type", CollectionType)
    def test_redirects_to_set_up_when_no_collections_to_copy(self, authenticated_grant_admin_client, collection_type):
        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_collection_to_copy",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=collection_type,
            )
        )

        assert response.status_code == 302
        assert (
            url_for(
                "deliver_grant_funding.set_up_collection",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=collection_type,
            )
            in response.location
        )

    @pytest.mark.parametrize("collection_type", CollectionType)
    def test_get_renders_form_when_collections_exist(
        self, authenticated_grant_admin_client, collection_type, factories
    ):
        factories.collection.create(grant=authenticated_grant_admin_client.grant, type=collection_type)

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_collection_to_copy",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=collection_type,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_button(soup, "Continue")

    def test_403_for_non_admin(self, authenticated_grant_member_client, factories):
        factories.collection.create(
            grant=authenticated_grant_member_client.grant, type=CollectionType.MONITORING_REPORT
        )

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.select_collection_to_copy",
                grant_id=authenticated_grant_member_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
            )
        )

        assert response.status_code == 403

    @pytest.mark.parametrize("collection_type", CollectionType)
    def test_post_redirects_to_set_up_with_copy_from(
        self, authenticated_grant_admin_client, collection_type, factories
    ):
        collection = factories.collection.create(grant=authenticated_grant_admin_client.grant, type=collection_type)

        form = SelectCollectionToCopyForm(
            data={"collection": str(collection.id)},
            collection_type=collection_type,
            collections=[collection],
            grant=authenticated_grant_admin_client.grant,
        )
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.select_collection_to_copy",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=collection_type,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert f"copy_from={collection.id}" in response.location

    def test_post_without_selection_shows_error(self, authenticated_grant_admin_client, factories):
        factories.collection.create(grant=authenticated_grant_admin_client.grant, type=CollectionType.MONITORING_REPORT)

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.select_collection_to_copy",
                grant_id=authenticated_grant_admin_client.grant.id,
                collection_type=CollectionType.MONITORING_REPORT,
            ),
            data={"submit": "y"},
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "Select the report to copy")
