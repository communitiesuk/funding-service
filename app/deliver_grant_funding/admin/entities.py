from abc import abstractmethod

from sqlalchemy import orm
from wtforms.validators import Email
from xgovuk_flask_admin import XGovukModelView

from app.common.data.base import BaseModel
from app.common.data.models import Collection, Organisation
from app.common.data.models_user import User, UserRole
from app.deliver_grant_funding.admin.mixins import FlaskAdminPlatformAdminAccessibleMixin


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


class PlatformAdminOrganisationView(PlatformAdminModelView):
    _model = Organisation

    can_create = True

    column_list = ["name"]
    column_filters = ["name"]

    form_columns = ["name"]


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
