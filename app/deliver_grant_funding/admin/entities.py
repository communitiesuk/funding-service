import datetime
from abc import abstractmethod

from flask import current_app, flash
from flask_admin.actions import action
from flask_admin.helpers import is_form_submitted
from flask_babel import ngettext
from sqlalchemy import delete, func, orm, select, update
from sqlalchemy.exc import IntegrityError
from wtforms import Form
from wtforms.validators import Email
from xgovuk_flask_admin import XGovukModelView

from app.common.data.base import BaseModel
from app.common.data.interfaces.user import get_current_user
from app.common.data.models import Collection, Grant, GrantRecipient, Organisation
from app.common.data.models_user import Invitation, User, UserRole
from app.common.data.types import RoleEnum
from app.deliver_grant_funding.admin.mixins import FlaskAdminPlatformAdminAccessibleMixin
from app.extensions import db, notification_service


class PlatformAdminModelView(FlaskAdminPlatformAdminAccessibleMixin, XGovukModelView):
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


class PlatformAdminUserView(PlatformAdminModelView):
    _model = User

    column_list = ["email", "name", "last_logged_in_at_utc"]
    column_searchable_list = ["email", "name"]

    form_columns = ["email", "name"]

    can_edit = True

    column_filters = ["email", "name"]

    form_args = {
        "email": {"validators": [Email()], "filters": [lambda val: val.strip() if isinstance(val, str) else val]},
    }

    @action(
        "revoke_all_permissions",
        "Revoke all permissions",
        "Are you sure you want to revoke all permissiosn for these users?",
    )  # type: ignore[misc]
    def revoke_permissions(self, ids: list[str]) -> None:
        if not self.can_edit:
            flash("You do not have permission to do this", "error")
            return

        try:
            self.session.execute(delete(UserRole).where(UserRole.user_id.in_(ids)))
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


class PlatformAdminOrganisationView(PlatformAdminModelView):
    _model = Organisation

    can_create = True
    can_edit = True
    can_delete = True

    column_list = ["external_id", "name", "type", "status", "can_manage_grants"]
    column_searchable_list = ["external_id", "name"]
    column_filters = ["external_id", "name", "type", "status", "can_manage_grants"]

    form_columns = ["external_id", "name", "type", "status", "can_manage_grants", "active_date", "retirement_date"]
    column_descriptions = {"external_id": "IATI or LAD24 identifier"}


class PlatformAdminCollectionView(PlatformAdminModelView):
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

    form_columns = ["name", "slug", "type", "status"]


class PlatformAdminUserRoleView(PlatformAdminModelView):
    _model = UserRole

    can_create = True
    can_edit = True
    can_delete = True

    column_list = ["user.email", "organisation.name", "grant.name", "role", "permissions"]
    column_filters = ["user.email", "organisation.name", "grant.name", "role", "permissions"]
    column_labels = {"organisation.name": "Organisation name", "grant.name": "Grant name", "user.email": "User email"}

    form_columns = ["user", "organisation", "grant", "role", "permissions"]

    form_args = {
        "user": {"get_label": "email"},
        "organisation": {"get_label": "name"},
        "grant": {"get_label": "name"},
    }


class PlatformAdminGrantView(PlatformAdminModelView):
    _model = Grant

    can_create = False
    can_edit = True
    can_delete = True

    column_list = ["name", "status", "ggis_number", "organisation.name"]
    column_filters = ["name", "status", "ggis_number", "organisation.name"]
    column_searchable_list = ["name", "ggis_number"]
    column_labels = {"ggis_number": "GGIS number", "organisation.name": "Organisation name"}

    form_columns = ["name", "organisation", "ggis_number", "status"]

    form_args = {
        "organisation": {
            "get_label": "name",
            "query_factory": lambda: db.session.query(Organisation).filter_by(can_manage_grants=True),
        },
    }


class PlatformAdminInvitationView(PlatformAdminModelView):
    _model = Invitation

    can_create = True

    column_searchable_list = ["email"]

    column_filters = ["is_usable", "organisation.name", "grant.name", "role", "permissions"]

    column_list = ["email", "organisation.name", "grant.name", "role", "permissions", "is_usable"]
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
        "role",
        "permissions",
    ]
    form_columns = ["email", "organisation", "grant", "role", "permissions"]

    form_args = {
        "email": {"validators": [Email()], "filters": [lambda val: val.strip() if isinstance(val, str) else val]},
        "user": {"get_label": "email"},
        "organisation": {"get_label": "name"},
        "grant": {"get_label": "name"},
        "role": {"coerce": RoleEnum},
    }

    def on_model_change(self, form: Form, model: Invitation, is_created: bool) -> None:
        if is_created:
            # Make new invitations last 1 hour by default, since these invitations are very privileged.
            model.expires_at_utc = func.now() + datetime.timedelta(hours=1)

            if user := self.session.scalar(select(User).where(User.email == form.email.data)):  # type: ignore[attr-defined]
                model.user = user

        return super().on_model_change(form, model, is_created)  # type: ignore[no-any-return]

    def validate_form(self, form: Form) -> bool:
        result = super().validate_form(form)

        if result:
            # Only create/edit forms have this - not delete
            if (
                is_form_submitted()
                and hasattr(form, "role")
                and hasattr(form, "organisation")
                and hasattr(form, "grant")
            ):
                # Only allow 'Deliver grant funding' org admin (ie form designer) invitations to be created for now
                _, organisation, grant = (
                    RoleEnum[form.role.data] if form.role.data else None,  # ty: ignore[unresolved-attribute]
                    form.organisation.data,  # ty: ignore[unresolved-attribute]
                    form.grant.data,  # ty: ignore[unresolved-attribute]
                )

                if (not organisation or not organisation.can_manage_grants) or grant:
                    form.form_errors.append("You can only create invitations for MHCLG admins and members")
                    result = False

        return result  # type: ignore[no-any-return]

    def after_model_change(self, form: Form, model: Invitation, is_created: bool) -> None:
        if is_created:
            if (not model.organisation or not model.organisation.can_manage_grants) or model.grant:
                db.session.delete(model)
                db.session.commit()
                raise RuntimeError("Invalid invitation created")
            else:
                if model.role == RoleEnum.ADMIN:
                    notification_service.send_deliver_org_admin_invitation(model.email, organisation=model.organisation)
                else:
                    notification_service.send_deliver_org_member_invitation(
                        model.email, organisation=model.organisation
                    )

        return super().after_model_change(form, model, is_created)  # type: ignore[no-any-return]

    @action(
        "cancel_invitation",
        "Cancel invitation",
        "Are you sure you want to cancel these invitations?",
    )  # type: ignore[misc]
    def cancel_invitation(self, ids: list[str]) -> None:
        if not self.can_create:
            flash("You do not have permission to do this", "error")
            return

        try:
            usable_invitations = (
                self.session.execute(select(Invitation.id).where(Invitation.id.in_(ids), Invitation.is_usable))
                .scalars()
                .all()
            )
            self.session.execute(
                update(Invitation).where(Invitation.id.in_(usable_invitations)).values(expires_at_utc=func.now())
            )
            self.session.commit()
            if usable_invitations:
                current_app.logger.warning(
                    "%(user_id)s cancelled the following invitations: %(invite_ids)s",
                    dict(user_id=get_current_user().id, invite_ids=", ".join(str(x) for x in usable_invitations)),
                )

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


class PlatformAdminGrantRecipientView(PlatformAdminModelView):
    _model = GrantRecipient

    can_create = True
    can_edit = False
    can_delete = True

    column_list = ["grant.name", "organisation.name"]
    column_filters = ["grant.name", "organisation.name"]
    column_searchable_list = ["grant.name", "organisation.name"]
    column_labels = {"grant.name": "Grant name", "organisation.name": "Organisation name"}

    column_formatters_detail = {
        "grant": lambda v, c, m, n: m.grant.name,
        "organisation": lambda v, c, m, n: m.organisation.name,
    }

    form_columns = ["grant", "organisation"]

    form_args = {
        "grant": {
            "get_label": "name",
        },
        "organisation": {
            "get_label": "name",
            "query_factory": lambda: db.session.query(Organisation).filter_by(can_manage_grants=False),
        },
    }
