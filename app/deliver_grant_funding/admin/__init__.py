from flask_admin import Admin
from flask_sqlalchemy_lite import SQLAlchemy

from app.deliver_grant_funding.admin.entities import (
    PlatformAdminCollectionView,
    PlatformAdminGrantView,
    PlatformAdminOrganisationView,
    PlatformAdminUserRoleView,
    PlatformAdminUserView,
)


class ProxySession:
    """
    We provide a live proxy to db.session here, so that any access is scoped to the `app_context` of the moment.
    When we weren't using this and were passing `db.session` directly through to the model views below, it was
    holding a single session (id:1) open and using that forever, rather than using request-scoped sessions. This
    definitely feels very wrong and I suspect is a bug/bad practice recommendation in either flask-sqlalchemy-lite
    or flask-admin.

    This was discovered when adding the following config to `form_args` of one of the model views:

        "query_factory": lambda: db.session.query(Organisation).filter_by(can_manage_grants=True),

    This was causing some queries to be executed by flask-admin using the global/permanent session (id:1), and
    anything using that query factory to use request-scoped sessions. This was causing errors in SQLAlchemy when
    trying to persist certain changes.

    Using this proxy, initial set up will use the app context from `create_app`, but then any queries that are fired
    off during requests will use the request-scoped session.
    """

    def __init__(self, db_: SQLAlchemy) -> None:
        self.db = db_

    def __getattr__(self, name):  # type: ignore[no-untyped-def]
        return getattr(self.db.session, name)


def register_admin_views(flask_admin: Admin, db_: SQLAlchemy) -> None:
    flask_admin.add_view(PlatformAdminUserView(ProxySession(db_)))  # type: ignore[arg-type]
    flask_admin.add_view(PlatformAdminUserRoleView(ProxySession(db_)))  # type: ignore[arg-type]
    flask_admin.add_view(PlatformAdminOrganisationView(ProxySession(db_)))  # type: ignore[arg-type]
    flask_admin.add_view(PlatformAdminGrantView(ProxySession(db_)))  # type: ignore[arg-type]
    flask_admin.add_view(PlatformAdminCollectionView(ProxySession(db_)))  # type: ignore[arg-type]
