from abc import abstractmethod

from sqlalchemy import orm
from wtforms.validators import Email
from xgovuk_flask_admin import XGovukModelView

from app.common.data.base import BaseModel
from app.common.data.models_user import User
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

    can_edit = True

    column_filters = ["email", "name"]

    form_args = {
        "email": {"validators": [Email()], "filters": [lambda val: val.strip() if isinstance(val, str) else val]},
        "azure_ad_subject_id": {"filters": [lambda val: val.strip() if isinstance(val, str) else val]},
    }
