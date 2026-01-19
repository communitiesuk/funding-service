import datetime
from abc import abstractmethod
from typing import TYPE_CHECKING, cast

import markupsafe
from flask import current_app, flash, g, url_for
from flask_admin.actions import action
from flask_admin.contrib.sqla.filters import BaseSQLAFilter
from flask_admin.helpers import is_form_submitted
from flask_babel import ngettext
from govuk_frontend_wtf.wtforms_widgets import GovTextArea
from sqlalchemy import func, orm, select
from sqlalchemy.exc import IntegrityError
from wtforms import Form
from wtforms.validators import Email
from xgovuk_flask_admin import XGovukModelView

from app.common.audit import (
    create_database_model_change_for_create,
    create_database_model_change_for_delete,
    create_database_model_change_for_update,
    track_audit_event,
)
from app.common.data.base import BaseModel
from app.common.data.interfaces.user import get_current_user
from app.common.data.models import Collection, Grant, GrantRecipient, Organisation
from app.common.data.models_audit import AuditEvent
from app.common.data.models_user import Invitation, User, UserRole
from app.common.data.types import RoleEnum
from app.deliver_grant_funding.admin.mixins import (
    FlaskAdminPlatformAdminAccessibleMixin,
    FlaskAdminPlatformMemberAccessibleMixin,
)
from app.extensions import db, notification_service
from app.metrics import MetricEventName, emit_metric_count

if TYPE_CHECKING:
    from app.common.audit import DatabaseModelChange


class PlatformAdminModelView(XGovukModelView):
    page_size = 50
    can_set_page_size = True

    can_create = False
    can_view_details = True
    can_edit = False
    can_delete = False
    can_export = False

    def __init__(
        self,
        session: orm.Session,
        name: "str | None" = None,
        category: "str | None" = None,
        endpoint: "str | None" = None,
        url: "str | None" = None,
        static_folder: "str | None" = None,
        menu_class_name: "str | None" = None,
        menu_icon_type: "str | None" = None,
        menu_icon_value: "str | None" = None,
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

    @property
    @abstractmethod
    def _model(self) -> type[BaseModel]:
        pass

    def on_model_change(self, form: Form, model: BaseModel, is_created: bool) -> None:
        if not is_created:
            g.audit_event = create_database_model_change_for_update(model, get_current_user())
        return super().on_model_change(form, model, is_created)  # type: ignore[no-any-return]

    def after_model_change(self, form: Form, model: BaseModel, is_created: bool) -> None:
        """This is called after flask-admin has committed the changes; when we track an audit event, that event
        needs to be responsible for committing itself, as flask-admin won't commit again automatically.
        """
        user = get_current_user()
        if is_created:
            event = create_database_model_change_for_create(model, user)
            track_audit_event(self.session, event, user)
            self.session.commit()
        elif pending_event := g.pop("audit_event", None):
            track_audit_event(self.session, pending_event, user)
            self.session.commit()

        return super().after_model_change(form, model, is_created)  # type: ignore[no-any-return]

    def on_model_delete(self, model: BaseModel) -> None:
        g.audit_event = create_database_model_change_for_delete(model, get_current_user())
        return super().on_model_delete(model)  # type: ignore[no-any-return]

    def after_model_delete(self, model: BaseModel) -> None:
        """This is called after flask-admin has committed the changes; when we track an audit event, that event
        needs to be responsible for committing itself, as flask-admin won't commit again automatically.
        """
        if audit_event := g.pop("audit_event", None):
            track_audit_event(self.session, audit_event, get_current_user())
            self.session.commit()

        return super().after_model_delete(model)  # type: ignore[no-any-return]


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

    @action(  # type: ignore[untyped-decorator]
        "revoke_all_permissions",
        "Revoke all permissions",
        "Are you sure you want to revoke all permissiosn for these users?",
    )
    def revoke_permissions(self, ids: list[str]) -> None:
        if not self.can_edit:
            flash("You do not have permission to do this", "error")
            return

        try:
            roles_to_delete = self.session.scalars(select(UserRole).where(UserRole.user_id.in_(ids)))
            for user_role in roles_to_delete:
                audit_event = create_database_model_change_for_delete(user_role, get_current_user())
                track_audit_event(self.session, audit_event, get_current_user())
                db.session.delete(user_role)

            self.session.commit()
            current_app.logger.warning(
                "%(name)s revoked all user permissions for user(s): %(user_ids)s",
                dict(name=get_current_user().id, user_ids=", ".join(ids)),
            )

            count = len(ids)
            flash(
                ngettext(
                    "All permissions were successfully revoked for the user.",
                    "All permissions were successfully revoked for %(count)s users.",
                    count,
                    count=count,
                ),
                "success",
            )

        except IntegrityError:
            flash(
                "Failed to revoke permissions.",
                "error",
            )


class PlatformAdminOrganisationView(FlaskAdminPlatformAdminAccessibleMixin, PlatformAdminModelView):
    _model = Organisation

    can_create = True
    can_edit = True
    can_delete = True

    column_list = ["external_id", "name", "type", "mode", "status", "can_manage_grants"]
    column_searchable_list = ["external_id", "name"]
    column_filters = ["external_id", "name", "type", "mode", "status", "can_manage_grants"]

    form_columns = [
        "external_id",
        "name",
        "type",
        "mode",
        "status",
        "can_manage_grants",
        "active_date",
        "retirement_date",
    ]
    column_descriptions = {"external_id": "IATI or LAD24 identifier"}


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
    }

    form_columns = ["name", "slug", "type", "status", "requires_certification"]

    def after_model_change(self, form: Form, model: Collection, is_created: bool) -> None:  # type: ignore[override]
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
    column_labels = {"ggis_number": "GGIS number", "organisation.name": "Organisation name"}

    form_columns = ["name", "code", "organisation", "ggis_number", "status", "privacy_policy_markdown"]

    form_args = {
        "organisation": {
            "get_label": "name",
            "query_factory": lambda: db.session.query(Organisation).filter_by(can_manage_grants=True),
        },
        "privacy_policy_markdown": {
            "widget": GovTextArea(),
        },
    }

    def edit_form(self, obj: Grant | None = None) -> Form:
        form = super().edit_form(obj)
        if obj:
            privacy_policy_url = url_for("access_grant_funding.privacy_policy", grant_id=obj.id)
            form.privacy_policy_markdown.description = markupsafe.Markup(  # ty: ignore[unresolved-attribute]
                "GOV.UK-style markdown for the grant's privacy policy. Once saved, "
                f"<a class='govuk-link govuk-link--no-visited-state' href='{privacy_policy_url}' target='_blank'>"
                "preview the privacy policy (opens in a new tab)"
                "</a>."
            )
        return form  # type: ignore[no-any-return]

    def after_model_change(self, form: Form, model: Grant, is_created: bool) -> None:  # type: ignore[override]
        if audit_event := cast("DatabaseModelChange | None", getattr(g, "audit_event", None)):
            if "status" in audit_event.changes:
                emit_metric_count(MetricEventName.GRANT_STATUS_CHANGED, count=1, grant=model)

        super().after_model_change(form, model, is_created)


class PlatformAdminInvitationView(FlaskAdminPlatformMemberAccessibleMixin, PlatformAdminModelView):
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

    def on_model_change(self, form: Form, model: Invitation, is_created: bool) -> None:  # type: ignore[override]
        if is_created:
            # Make new invitations last 1 hour by default, since these invitations are very privileged.
            model.expires_at_utc = func.now() + datetime.timedelta(hours=1)

            if user := self.session.scalar(select(User).where(User.email == form.email.data)):  # type: ignore[attr-defined]
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

        return result  # type: ignore[no-any-return]

    def after_model_change(self, form: Form, model: Invitation, is_created: bool) -> None:  # type: ignore[override]
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

    @action(  # type: ignore[untyped-decorator]
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
                self.session.execute(select(Invitation).where(Invitation.id.in_(ids), Invitation.is_usable))
                .scalars()
                .all()
            )
            for invitation in usable_invitations:
                invitation.expires_at_utc = datetime.datetime.now(datetime.timezone.utc)
                audit_event = create_database_model_change_for_update(invitation, get_current_user())
                if not audit_event:
                    raise RuntimeError("Expected an audit event")
                track_audit_event(self.session, audit_event, get_current_user())

            self.session.commit()

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

    column_list = ["grant.name", "organisation.name", "mode"]
    column_filters = ["grant.name", "organisation.name", "mode"]
    column_searchable_list = ["grant.name", "organisation.name"]
    column_labels = {"grant.name": "Grant name", "organisation.name": "Organisation name"}

    column_formatters_detail = {
        "grant": lambda v, c, m, n: m.grant.name,
        "organisation": lambda v, c, m, n: m.organisation.name,
    }

    form_columns = ["grant", "organisation", "mode"]

    form_args = {
        "grant": {
            "get_label": "name",
        },
        "organisation": {
            "get_label": "name",
            "query_factory": lambda: db.session.query(Organisation).filter_by(can_manage_grants=False),
        },
    }


def _format_json_data(view, context, model, name):  # type: ignore[no-untyped-def]
    import json

    return markupsafe.Markup(
        f"<pre class='govuk-!-margin-top-0'>{markupsafe.escape(json.dumps(model.data, indent=2))}</pre>"
    )


def _format_model_class(view, context, model, name):  # type: ignore[no-untyped-def]
    return model.data.get("model_class", "")


def _format_action(view, context, model, name):  # type: ignore[no-untyped-def]
    return model.data.get("action", "")


class ModelClassFilter(BaseSQLAFilter):
    def __init__(self, column, name: str):  # type: ignore[no-untyped-def]
        super().__init__(column, name)

    def apply(self, query, value, alias=None):  # type: ignore[no-untyped-def]
        return query.filter(self.column["model_class"].astext.ilike(value))

    def operation(self) -> str:
        return "equals"


class ActionFilter(BaseSQLAFilter):
    def __init__(self, column, name: str):  # type: ignore[no-untyped-def]
        super().__init__(column, name)

    def apply(self, query, value, alias=None):  # type: ignore[no-untyped-def]
        return query.filter(self.column["action"].astext.ilike(value))

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
        "created_at_utc": "Timestamp",
        "user.email": "User",
        "model_class": "Model class",
        "action": "Action",
        "updated_at_utc": "Updated at",
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

    def _apply_search(self, query, count_query, joins, count_joins, search):  # type: ignore[no-untyped-def]
        from app.common.data.models_user import User

        if search:
            from sqlalchemy import or_

            search_term = f"%{search}%"
            search_filter = or_(
                User.email.ilike(search_term),
                AuditEvent.event_type.ilike(search_term),
                AuditEvent.data["model_class"].astext.ilike(search_term),
                AuditEvent.data["action"].astext.ilike(search_term),
            )
            query = query.join(AuditEvent.user).filter(search_filter)
            count_query = count_query.join(AuditEvent.user).filter(search_filter)

        return query, count_query, joins, count_joins
