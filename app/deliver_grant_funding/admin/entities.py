import datetime
import uuid
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlencode

import markupsafe
from flask import flash, g, redirect, request, url_for
from flask_admin.actions import action
from flask_admin.contrib.sqla.filters import BaseSQLAFilter
from flask_admin.helpers import is_form_submitted
from flask_babel import ngettext
from flask_sqlalchemy_lite import SQLAlchemy
from govuk_frontend_wtf.wtforms_widgets import GovTextArea
from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import InstrumentedAttribute
from werkzeug.wrappers import Response
from wtforms import Form
from wtforms.validators import Email
from xgovuk_flask_admin import XGovukModelView

from app.common.audit import (
    create_database_model_change_for_create,
    create_database_model_change_for_delete,
    create_database_model_change_for_update,
)
from app.common.data.base import BaseModel
from app.common.data.interfaces.audit import track_audit_event
from app.common.data.interfaces.user import get_current_user
from app.common.data.models import (
    Collection,
    Grant,
    GrantRecipient,
    Organisation,
    Question,
    Submission,
    SubmissionEvent,
)
from app.common.data.models_audit import AuditEvent
from app.common.data.models_user import Invitation, User, UserRole
from app.common.data.types import (
    AuditEventType,
    GrantRecipientStatusEnum,
    OrganisationType,
    RoleEnum,
    SubmissionEventType,
)
from app.common.helpers.collections import SubmissionHelper
from app.common.security.utils import sanitise_redirect_url
from app.deliver_grant_funding.admin.forms import PlatformAdminChangeGrantRecipientStatusForm
from app.deliver_grant_funding.admin.mixins import (
    FlaskAdminPlatformAdminAccessibleMixin,
    FlaskAdminPlatformAdminGrantLifecycleManagerAccessibleMixin,
)
from app.extensions import db, notification_service
from app.metrics import MetricEventName, emit_metric_count

if TYPE_CHECKING:
    from app.common.audit import DatabaseModelChange


class PlatformAdminModelView(XGovukModelView):
    _model: type[BaseModel]

    page_size = 50
    can_set_page_size = True

    can_create = False
    can_view_details = True
    can_edit = False
    can_delete = False
    can_export = False

    session: SQLAlchemy

    def __init__(
        self,
        session: SQLAlchemy,
        name: str | None = None,
        category: str | None = None,
        endpoint: str | None = None,
        url: str | None = None,
        static_folder: str | None = None,
        menu_class_name: str | None = None,
        menu_icon_type: str | None = None,
        menu_icon_value: str | None = None,
    ) -> None:
        super().__init__(
            self._model,
            session,
            name=name,
            category=category,
            endpoint=endpoint,
            url=url,
            static_folder=static_folder,
            menu_class_name=menu_class_name,
            menu_icon_type=menu_icon_type,
            menu_icon_value=menu_icon_value,
        )

    def on_model_change(self, form: Form, model: BaseModel, is_created: bool) -> None:  # ty: ignore[invalid-method-override]
        if not is_created:
            g.audit_event = create_database_model_change_for_update(model, get_current_user())
        return super().on_model_change(form, model, is_created)

    def after_model_change(self, form: Form, model: BaseModel, is_created: bool) -> None:  # ty:ignore[invalid-method-override]
        """This is called after flask-admin has committed the changes; when we track an audit event, that event
        needs to be responsible for committing itself, as flask-admin won't commit again automatically.
        """
        user = get_current_user()
        if is_created:
            event = create_database_model_change_for_create(model, user)
            track_audit_event(event, user)
            self.session.session.commit()
        elif pending_event := g.pop("audit_event", None):
            track_audit_event(pending_event, user)
            self.session.session.commit()

        return super().after_model_change(form, model, is_created)

    def on_model_delete(self, model: BaseModel) -> None:  # ty:ignore[invalid-method-override]
        g.audit_event = create_database_model_change_for_delete(model, get_current_user())
        return super().on_model_delete(model)

    def after_model_delete(self, model: BaseModel) -> None:  # ty:ignore[invalid-method-override]
        """This is called after flask-admin has committed the changes; when we track an audit event, that event
        needs to be responsible for committing itself, as flask-admin won't commit again automatically.
        """
        if audit_event := g.pop("audit_event", None):
            track_audit_event(audit_event, get_current_user())
            self.session.session.commit()

        return super().after_model_delete(model)


class PlatformAdminUserView(FlaskAdminPlatformAdminAccessibleMixin, PlatformAdminModelView):
    _model = User

    column_list = ["email", "name", "last_logged_in_at_utc"]
    column_searchable_list = ["email", "name"]

    form_columns = ["email", "name"]

    can_edit = True

    column_filters = ["email", "name"]

    form_args = {
        "email": {"validators": [Email()], "filters": [lambda val: val.strip() if isinstance(val, str) else val]},
    }


class PlatformAdminOrganisationView(FlaskAdminPlatformAdminAccessibleMixin, PlatformAdminModelView):
    _model = Organisation

    can_create = True
    can_edit = True
    can_delete = True

    can_export = True

    column_list = ["external_id", "name", "type", "mode", "status", "can_manage_grants"]
    column_searchable_list = ["external_id", "name"]
    column_filters = ["external_id", "name", "type", "mode", "status", "can_manage_grants"]

    form_columns = [
        "name",
        "type",
        "mode",
        "status",
        "can_manage_grants",
        "active_date",
        "retirement_date",
        "iati_id",
        "ons_lad_id",
        "companies_house_number",
        "charity_commission_number",
        "custom_code",
    ]
    column_labels = {
        "iati_id": "IATI ID",
        "ons_lad_id": "ONS LAD(24) ID",
    }
    column_descriptions = {
        "custom_code": "Our own custom identifier code for 'Other' organisation types",
    }

    def on_model_change(self, form: Form, model: Organisation, is_created: bool) -> None:  # ty:ignore[invalid-method-override]
        external_id_before = model.external_id

        if not isinstance(model.type, OrganisationType):
            model.type = getattr(OrganisationType, model.type)

        if not model.typed_id:
            raise ValueError(f"{model.type.typed_id_field} is required for organisation type {model.type.value}")
        model.external_id = model.make_external_id()
        result = super().on_model_change(form, model, is_created)

        if not is_created and model.external_id != external_id_before:
            raise ValueError("Must not change the organisation's external ID")

        return result


class PlatformAdminCollectionView(FlaskAdminPlatformAdminAccessibleMixin, PlatformAdminModelView):
    _model = Collection

    can_edit = True

    column_list = ["name", "type", "status", "grant.name"]
    column_filters = ["name", "type", "status"]

    column_details_list = ["grant.name", "created_by.email", "created_at_utc", "type.value", "name"]
    column_labels = {
        "grant.name": "Grant name",
        "created_by.email": "Created by",
        "created_at_utc": "Created at",
        "type.value": "Type",
        "allow_multiple_submissions": "Allow multiple submissions",
        "multiple_submissions_are_managed_by_service": "Allow managed submissions only",
        "allow_public_sign_up": "Allow public sign up",
    }

    form_columns = [
        "name",
        "slug",
        "type",
        "status",
        "requires_certification",
        "reporting_period_start_date",
        "reporting_period_end_date",
        "submission_period_start_date",
        "submission_period_end_date",
        "submission_guidance",
        "allow_multiple_submissions",
        "multiple_submissions_are_managed_by_service",
        "allow_public_sign_up",
    ]

    form_args = {
        "submission_guidance": {
            "widget": GovTextArea(),
        },
    }

    def after_model_change(self, form: Form, model: Collection, is_created: bool) -> None:  # ty: ignore[invalid-method-override]
        if audit_event := cast("DatabaseModelChange | None", getattr(g, "audit_event", None)):
            if "status" in audit_event.changes:
                emit_metric_count(MetricEventName.COLLECTION_STATUS_CHANGED, count=1, collection=model)

        super().after_model_change(form, model, is_created)


class PlatformAdminUserRoleView(FlaskAdminPlatformAdminAccessibleMixin, PlatformAdminModelView):
    _model = UserRole

    can_create = True
    can_edit = True
    can_delete = True

    column_list = ["user.email", "organisation.name", "grant.name", "permissions"]
    column_filters = ["user.email", "organisation.name", "grant.name", "permissions"]
    column_labels = {"organisation.name": "Organisation name", "grant.name": "Grant name", "user.email": "User email"}

    form_columns = ["user", "organisation", "grant", "permissions"]

    form_args = {
        "user": {"get_label": "email"},
        "organisation": {"get_label": "name"},
        "grant": {"get_label": "name"},
    }


class PlatformAdminGrantView(FlaskAdminPlatformAdminAccessibleMixin, PlatformAdminModelView):
    _model = Grant

    can_create = False
    can_edit = True
    can_delete = True

    column_list = ["name", "code", "status", "ggis_number", "organisation.name"]
    column_filters = ["name", "code", "status", "ggis_number", "organisation.name"]
    column_searchable_list = ["name", "code", "ggis_number"]
    column_labels = {
        "ggis_number": "GGIS number",
        "organisation.name": "Organisation name",
        "allow_pre_award": "Allow pre-award features",
    }

    form_columns = [
        "name",
        "code",
        "organisation",
        "ggis_number",
        "status",
        "privacy_policy_markdown",
        "allow_pre_award",
    ]

    form_args = {
        "organisation": {
            "get_label": "name",
            "query_factory": lambda: db.session.query(Organisation).filter_by(can_manage_grants=True),
        },
        "privacy_policy_markdown": {
            "widget": GovTextArea(),
        },
    }

    def edit_form(self, obj: Grant | None = None) -> Form:  # ty:ignore[invalid-method-override]
        form = super().edit_form(obj)
        if obj:
            privacy_policy_url = url_for("access_grant_funding.privacy_policy", grant_id=obj.id)
            form.privacy_policy_markdown.description = markupsafe.Markup(  # ty: ignore[unresolved-attribute]
                "GOV.UK-style markdown for the grant's privacy policy. Once saved, "
                f"<a class='govuk-link govuk-link--no-visited-state' href='{privacy_policy_url}' target='_blank'>"
                "preview the privacy policy (opens in a new tab)"
                "</a>."
            )
        return form

    def after_model_change(self, form: Form, model: Grant, is_created: bool) -> None:  # ty: ignore[invalid-method-override]
        if audit_event := cast("DatabaseModelChange | None", getattr(g, "audit_event", None)):
            if "status" in audit_event.changes:
                emit_metric_count(MetricEventName.GRANT_STATUS_CHANGED, count=1, grant=model)

        super().after_model_change(form, model, is_created)


class PlatformAdminInvitationView(FlaskAdminPlatformAdminGrantLifecycleManagerAccessibleMixin, PlatformAdminModelView):
    _model = Invitation

    can_create = True

    column_searchable_list = ["email"]

    column_filters = ["is_usable", "organisation.name", "grant.name", "permissions"]

    column_list = ["email", "organisation.name", "grant.name", "permissions", "is_usable"]
    column_labels = {
        "user.id": "User ID",
        "organisation.name": "Organisation name",
        "grant.name": "Grant name",
    }

    column_details_list = [
        "created_at_utc",
        "expires_at_utc",
        "claimed_at_utc",
        "email",
        "user.id",
        "organisation.name",
        "grant.name",
        "permissions",
    ]
    form_columns = ["email", "organisation", "grant", "permissions"]

    form_args = {
        "email": {"validators": [Email()], "filters": [lambda val: val.strip() if isinstance(val, str) else val]},
        "user": {"get_label": "email"},
        "organisation": {"get_label": "name"},
        "grant": {"get_label": "name"},
    }

    def on_model_change(self, form: Form, model: Invitation, is_created: bool) -> None:  # ty:ignore[invalid-method-override]
        if is_created:
            # Make new invitations last 1 hour by default, since these invitations are very privileged.
            model.expires_at_utc = func.now() + datetime.timedelta(hours=1)

            if user := self.session.session.scalar(select(User).where(User.email == form.email.data)):  # ty: ignore[unresolved-attribute]
                model.user = user

        return super().on_model_change(form, model, is_created)

    def validate_form(self, form: Form) -> bool:
        result = super().validate_form(form)

        if result:
            # Only create/edit forms have this - not delete
            if (
                is_form_submitted()
                and hasattr(form, "permissions")
                and hasattr(form, "organisation")
                and hasattr(form, "grant")
            ):
                # Only allow 'Deliver grant funding' org admin+member (ie funding service) invitations to be created
                permissions = [RoleEnum[p] for p in form.permissions.data]  # ty: ignore[unresolved-attribute]
                organisation = form.organisation.data  # ty: ignore[unresolved-attribute]
                grant = form.grant.data  # ty: ignore[unresolved-attribute]

                if (
                    (not organisation or not organisation.can_manage_grants)
                    or grant
                    or not set(permissions).issubset({RoleEnum.ADMIN, RoleEnum.MEMBER})
                ):
                    form.form_errors.append("You can only create invitations for MHCLG admins and members")
                    result = False

        return result

    def after_model_change(self, form: Form, model: Invitation, is_created: bool) -> None:  # ty: ignore[invalid-method-override]
        if is_created:
            if (not model.organisation or not model.organisation.can_manage_grants) or model.grant:
                db.session.delete(model)
                db.session.commit()
                raise RuntimeError("Invalid invitation created")
            else:
                if RoleEnum.ADMIN in model.permissions:
                    notification_service.send_deliver_org_admin_invitation(model.email, organisation=model.organisation)
                else:
                    notification_service.send_deliver_org_member_invitation(
                        model.email, organisation=model.organisation
                    )

        return super().after_model_change(form, model, is_created)

    @action(
        "cancel_invitation",
        "Cancel invitation",
        "Are you sure you want to cancel these invitations?",
    )
    def cancel_invitation(self, ids: list[str]) -> None:
        if not self.can_create:
            flash("You do not have permission to do this", "error")
            return

        try:
            usable_invitations = (
                self.session.session.execute(select(Invitation).where(Invitation.id.in_(ids), Invitation.is_usable))
                .scalars()
                .all()
            )
            for invitation in usable_invitations:
                invitation.expires_at_utc = datetime.datetime.now(datetime.UTC)
                audit_event = create_database_model_change_for_update(invitation, get_current_user())
                if not audit_event:
                    raise RuntimeError("Expected an audit event")
                track_audit_event(audit_event, get_current_user())

            self.session.session.commit()

            count = len(usable_invitations)
            flash(
                ngettext(
                    "The invitation was successfully cancelled.",
                    "%(count)s invitations were successfully cancelled.",
                    count,
                    count=count,
                ),
                "success",
            )

        except IntegrityError:
            flash(
                "Failed to cancel invitation(s).",
                "error",
            )


class PlatformAdminGrantRecipientView(FlaskAdminPlatformAdminAccessibleMixin, PlatformAdminModelView):
    _model = GrantRecipient

    can_create = True
    can_edit = False
    can_delete = True

    list_template = "deliver_grant_funding/admin/grant-recipient-list.html"

    column_list = ["grant.name", "organisation.name", "mode", "status"]
    column_filters = ["grant.name", "organisation.name", "mode", "status"]
    column_searchable_list = ["grant.name", "organisation.name"]
    column_labels = {"grant.name": "Grant name", "organisation.name": "Organisation name"}

    column_formatters_detail = {
        "grant": lambda v, c, m, n: m.grant.name,
        "organisation": lambda v, c, m, n: m.organisation.name,
    }

    form_columns = ["grant", "organisation", "mode", "status"]

    form_args = {
        "grant": {
            "get_label": "name",
        },
        "organisation": {
            "get_label": "name",
            "query_factory": lambda: db.session.query(Organisation).filter_by(can_manage_grants=False),
        },
    }

    def render(self, template, **kwargs):
        if "change_status_form" not in kwargs:
            kwargs["change_status_form"] = PlatformAdminChangeGrantRecipientStatusForm()
        if request.args.get("_change_status"):
            preserved_params = [
                (k, v) for k, v in request.args.items(multi=True) if k not in ("_change_status", "rowid")
            ]
            base = request.base_url
            kwargs["change_status_cancel_url"] = f"{base}?{urlencode(preserved_params)}" if preserved_params else base
            kwargs["change_status_return_url"] = kwargs["change_status_cancel_url"]
        return super().render(template, **kwargs)

    @action(
        "change_status",
        "Change status",
    )
    def change_status(self, ids: list[str]) -> Response | None:
        new_status = request.form.get("new_status")
        if not new_status:
            return_url = sanitise_redirect_url(request.form.get("url", self.get_url(".index_view")))
            separator = "&" if "?" in return_url else "?"
            params = [("rowid", id_) for id_ in ids]
            params.append(("_change_status", "1"))
            return redirect(f"{return_url}{separator}{urlencode(params)}")

        try:
            status = GrantRecipientStatusEnum(new_status)
        except ValueError:
            flash("Invalid status selected.", "error")
            return

        try:
            grant_recipient_ids = [uuid.UUID(id_) for id_ in ids]
        except ValueError:
            flash("Invalid grant recipient selection.", "error")
            return

        grant_recipients = (
            self.session.session.execute(select(GrantRecipient).where(GrantRecipient.id.in_(grant_recipient_ids)))
            .scalars()
            .all()
        )

        for grant_recipient in grant_recipients:
            grant_recipient.status = status
            audit_event = create_database_model_change_for_update(grant_recipient, get_current_user())
            if audit_event:
                track_audit_event(audit_event, get_current_user())

        self.session.session.commit()

        count = len(grant_recipients)
        flash(
            ngettext(
                "%(count)s grant recipient status changed to %(status)s.",
                "%(count)s grant recipient statuses changed to %(status)s.",
                count,
                count=count,
                status=status.value,
            ),
            "success",
        )


def _format_json_data(view, context, model, name):
    import json

    return markupsafe.Markup(
        f"<pre class='govuk-!-margin-top-0'>{markupsafe.escape(json.dumps(model.data, indent=2))}</pre>"
    )


def _format_model_class(view, context, model, name):
    return model.data.get("model_class", "")


def _format_action(view, context, model, name):
    return model.data.get("action", "")


class ModelClassFilter(BaseSQLAFilter):
    def __init__(self, column: InstrumentedAttribute, name: str):
        super().__init__(column, name)

    def apply(self, query, value, alias=None):
        return query.filter(cast(InstrumentedAttribute, self.column)["model_class"].astext.ilike(value))

    def operation(self) -> str:
        return "equals"


class ActionFilter(BaseSQLAFilter):
    def __init__(self, column, name: str):
        super().__init__(column, name)

    def apply(self, query, value, alias=None):
        return query.filter(cast(InstrumentedAttribute, self.column)["action"].astext.ilike(value))

    def operation(self) -> str:
        return "equals"


class PlatformAdminAuditEventView(FlaskAdminPlatformAdminAccessibleMixin, PlatformAdminModelView):
    _model = AuditEvent

    column_default_sort = ("created_at_utc", True)

    column_list = ["created_at_utc", "event_type", "user.email", "model_class", "action"]
    column_filters = [
        "event_type",
        "user.email",
        "created_at_utc",
        ModelClassFilter(AuditEvent.data, "Model Class"),
        ActionFilter(AuditEvent.data, "Action"),
    ]
    column_searchable_list = ["user.email", "event_type"]
    column_labels = {
        "created_at_utc": "Created at UTC",
        "user.email": "User",
        "model_class": "Model class",
        "action": "Action",
        "updated_at_utc": "Updated at UTC",
        "event_type": "Event type",
    }

    column_formatters = {"model_class": _format_model_class, "action": _format_action}
    column_formatters_detail = {
        "data": _format_json_data,
        "user": lambda v, c, m, n: m.user.email,
    }

    can_edit = False
    can_delete = False

    def search_placeholder(self) -> str:
        return "User, Event Type, Model Class, Action"

    def _apply_search(self, query, count_query, joins, count_joins, search):
        if search:
            search_term = f"%{search}%"
            event_type_label = case(
                {member: member.value for member in AuditEventType},
                value=AuditEvent.event_type,
            )
            search_filter = or_(
                User.email.ilike(search_term),
                event_type_label.ilike(search_term),
                AuditEvent.data["model_class"].astext.ilike(search_term),
                AuditEvent.data["action"].astext.ilike(search_term),
            )
            query = query.join(AuditEvent.user).filter(search_filter)
            count_query = count_query.join(AuditEvent.user).filter(search_filter)

        return query, count_query, joins, count_joins


class PlatformAdminSubmissionView(FlaskAdminPlatformAdminGrantLifecycleManagerAccessibleMixin, PlatformAdminModelView):
    _model = Submission

    column_default_sort = ("created_at_utc", True)

    column_list = [
        "reference",
        "collection.grant.name",
        "collection.name",
        "grant_recipient.organisation.name",
        "mode",
        "created_by.email",
    ]
    column_filters = [
        "mode",
        "status",
        "collection.grant.name",
        "grant_recipient.organisation.name",
    ]
    column_searchable_list = ["id", "reference", "collection.name", "collection.grant.name"]
    column_labels = {
        "id": "Id",
        "reference": "Reference",
        "collection.grant.name": "Grant",
        "collection.name": "Report",
        "grant_recipient.organisation.name": "Organisation",
        "created_by.email": "Created by",
    }

    details_template = "deliver_grant_funding/admin/submission-details.html"

    def render(self, template: str, **kwargs: Any) -> Any:
        if (model := kwargs.get("model")) is not None:
            if template == self.details_template:
                kwargs["helper"] = SubmissionHelper(cast("Submission", model))
                kwargs["timeline_event_types"] = list(SubmissionEventType)

        return super().render(template, **kwargs)


class PlatformAdminQuestionView(FlaskAdminPlatformAdminAccessibleMixin, PlatformAdminModelView):
    _model = Question

    can_edit = True
    can_create = False
    can_delete = False

    edit_template = "deliver_grant_funding/admin/edit-question.html"

    column_list = [
        "name",
        "text",
        "data_type",
        "form.collection.grant.name",
        "form.collection.name",
        "form.title",
    ]
    column_labels = {
        "data_type": "Type",
        "form.title": "Section",
        "form.collection.name": "Collection",
        "form.collection.grant.name": "Grant",
    }
    column_filters = [
        "form.collection.grant.name",
        "form.collection.name",
        "form.title",
        "name",
        "data_type",
    ]
    column_searchable_list = ["name", "text"]
    form_columns = ["name"]
    column_default_sort = "name"


class PlatformAdminSubmissionEventView(FlaskAdminPlatformAdminAccessibleMixin, PlatformAdminModelView):
    _model = SubmissionEvent

    column_default_sort = ("created_at_utc", True)

    column_list = [
        "event_type",
        "created_at_utc",
        "submission.reference",
        "submission.mode",
        "created_by.email",
    ]
    column_filters = [
        "submission.mode",
        "event_type",
    ]
    column_searchable_list = ["id", "submission.reference"]
    column_labels = {
        "created_at_utc": "Created at UTC",
        "updated_at_utc": "Updated at UTC",
        "event_type": "Event type",
        "submission.reference": "Submission reference",
        "submission.mode": "Submission mode",
        "created_by.email": "Created by",
    }
    column_formatters_detail = {
        "data": _format_json_data,
    }
