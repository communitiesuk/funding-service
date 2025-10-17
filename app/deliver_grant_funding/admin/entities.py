import datetime
from abc import abstractmethod

from flask import flash
from flask_admin.actions import action
from flask_admin.helpers import is_form_submitted
from flask_babel import ngettext
from sqlalchemy import func, orm, select, update
from sqlalchemy.exc import IntegrityError
from wtforms import Form
from wtforms.validators import Email
from xgovuk_flask_admin import XGovukModelView

from app.common.data.base import BaseModel
from app.common.data.interfaces.user import get_user, remove_platform_admin_role_from_user, upsert_user_role
from app.common.data.models import Collection, Grant, Organisation
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

    form_columns = [
        "email",
        "name",
    ]

    can_edit = True

    column_filters = ["email", "name"]

    form_args = {
        "email": {"validators": [Email()], "filters": [lambda val: val.strip() if isinstance(val, str) else val]},
    }

    # TODO: Remove me; this is just a temporary action to help migrate existing form designers (and mildly demonstrate
    #       custom actions).
    @action(
        "make_form_designer",
        "Make MHCLG form designer",
        "Are you sure you want to make these people form designers for MHCLG grants?",
    )  # type: ignore[misc]
    def make_owned(self, ids: list[str]) -> None:
        if not self.can_edit:
            flash("You do not have permission to do this", "error")
            return

        try:
            mhclg_org = self.session.execute(
                select(Organisation).where(Organisation.can_manage_grants.is_(True))
            ).scalar_one()

            for user_id in ids:
                user = get_user(user_id)

                if user is None:
                    continue

                remove_platform_admin_role_from_user(user)
                upsert_user_role(user, role=RoleEnum.ADMIN, organisation_id=mhclg_org.id, grant_id=None)

            self.session.commit()
            count = len(ids)
            flash(
                ngettext(
                    "User was successfully assigned to MHCLG.",
                    "%(count)s users were successfully assigned to MHCLG.",
                    count,
                    count=count,
                ),
                "success",
            )

        except IntegrityError:
            flash(
                "Failed to assign users as MHCLG form designers.",
                "error",
            )


class PlatformAdminOrganisationView(PlatformAdminModelView):
    _model = Organisation

    can_create = True
    can_edit = True
    can_delete = True

    column_list = ["name", "can_manage_grants"]
    # TODO: https://github.com/pallets-eco/flask-admin/issues/2674
    #       filtering on boolean fields currently broken in flask-admin when using psycopg(3) lib =[
    column_filters = ["name"]

    form_columns = ["name", "can_manage_grants"]


class PlatformAdminCollectionView(PlatformAdminModelView):
    _model = Collection

    column_list = ["name", "type", "grant.name"]
    column_filters = ["name", "type"]

    column_details_list = ["grant.name", "created_by.email", "created_at_utc", "type.value", "name"]
    column_labels = {
        "grant.name": "Grant name",
        "created_by.email": "Created by",
        "created_at_utc": "Created at",
        "type.value": "Type",
    }


class PlatformAdminUserRoleView(PlatformAdminModelView):
    _model = UserRole

    can_create = True
    can_edit = True
    can_delete = True

    column_list = ["user.email", "organisation.name", "grant.name", "role"]
    column_filters = ["user.email", "organisation.name", "grant.name", "role"]
    column_labels = {"organisation.name": "Organisation name", "grant.name": "Grant name", "user.email": "User email"}

    form_columns = ["user", "organisation", "grant", "role"]

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

    column_list = ["name", "ggis_number", "organisation.name"]
    column_filters = ["name", "ggis_number", "organisation.name"]
    column_searchable_list = ["name", "ggis_number"]
    column_labels = {"ggis_number": "GGIS number", "organisation.name": "Organisation name"}

    form_columns = ["name", "organisation", "ggis_number"]

    form_args = {
        "organisation": {
            "get_label": "name",
            "query_factory": lambda: db.session.query(Organisation).filter_by(can_manage_grants=True),
        },
    }

    # TODO: Remove me; this is just a temporary action to help migrate existing grants (and mildly demonstrate custom
    #       actions).
    @action(
        "make_owned_by_mhclg",
        "Make owned by MHCLG",
        "Are you sure you want to make these grants owned by MHCLG?",
    )  # type: ignore[misc]
    def make_owned(self, ids: list[str]) -> None:
        if not self.can_edit:
            flash("You do not have permission to do this", "error")
            return

        try:
            mhclg_org = self.session.execute(
                select(Organisation).where(Organisation.can_manage_grants.is_(True))
            ).scalar_one()
            self.session.execute(update(Grant).where(Grant.id.in_(ids)).values(organisation_id=mhclg_org.id))
            self.session.commit()
            count = len(ids)
            flash(
                ngettext(
                    "Grant was successfully assigned to MHCLG.",
                    "%(count)s grants were successfully assigned to MHCLG.",
                    count,
                    count=count,
                ),
                "success",
            )

        except IntegrityError:
            flash(
                "Failed to assign grants to MHCLG.",
                "error",
            )


class PlatformAdminInvitationView(PlatformAdminModelView):
    _model = Invitation

    can_create = True
    can_delete = True

    column_searchable_list = ["email"]

    column_filters = ["is_usable", "organisation.name", "grant.name", "role"]

    column_list = ["email", "user.id", "organisation.name", "grant.name", "role"]
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
    ]
    form_columns = ["email", "user", "organisation", "grant", "role"]

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
                role, organisation, grant = (
                    RoleEnum[form.role.data] if form.role.data else None,  # ty: ignore[unresolved-attribute]
                    form.organisation.data,  # ty: ignore[unresolved-attribute]
                    form.grant.data,  # ty: ignore[unresolved-attribute]
                )

                if role != RoleEnum.ADMIN or (not organisation or not organisation.can_manage_grants) or grant:
                    form.form_errors.append("You can only create invitations for MHCLG admins")
                    result = False

        return result  # type: ignore[no-any-return]

    def after_model_change(self, form: Form, model: Invitation, is_created: bool) -> None:
        if is_created:
            if (
                model.role != RoleEnum.ADMIN
                or (not model.organisation or not model.organisation.can_manage_grants)
                or model.grant
            ):
                db.session.delete(model)
                db.session.commit()
                raise RuntimeError("Invalid invitation created")
            else:
                notification_service.send_deliver_org_admin_invitation(model.email, organisation=model.organisation)

        return super().after_model_change(form, model, is_created)  # type: ignore[no-any-return]
