import typing as t
from typing import TYPE_CHECKING, Any, Literal, Optional

from flask import Flask, Response, redirect, render_template, url_for
from flask.typing import ResponseReturnValue
from flask_babel import Babel
from govuk_frontend_wtf.main import WTFormsHelpers
from jinja2 import ChoiceLoader, PackageLoader, PrefixLoader
from sqlalchemy.exc import NoResultFound
from werkzeug.routing import BaseConverter

from app import logging
from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.data import interfaces
from app.common.data.types import (
    FormRunnerState,
    QuestionDataType,
    SubmissionModeEnum,
    SubmissionStatusEnum,
    TasklistTaskStatusEnum,
)
from app.common.filters import (
    format_date,
    format_date_range,
    format_date_short,
    format_datetime,
    format_datetime_range,
    to_ordinal,
)
from app.config import get_settings
from app.extensions import (
    auto_commit_after_request,
    db,
    flask_assets_vite,
    login_manager,
    migrate,
    notification_service,
    record_sqlalchemy_queries,
    register_signals,
    talisman,
    toolbar,
)
from app.monkeypatch import patch_sqlalchemy_lite_async
from app.sentry import init_sentry
from app.types import FlashMessageType

if TYPE_CHECKING:
    from app.common.data.models_user import User

init_sentry()


def _register_global_error_handlers(app: Flask) -> None:
    @app.errorhandler(403)
    def handle_403(error: Literal[403]) -> ResponseReturnValue:
        return render_template("common/errors/403.html", service_desk_url=app.config["SERVICE_DESK_URL"]), 403

    @app.errorhandler(NoResultFound)
    def handle_sqlalchemy_no_result(error: NoResultFound) -> ResponseReturnValue:
        return render_template("common/errors/404.html", service_desk_url=app.config["SERVICE_DESK_URL"]), 404

    @app.errorhandler(404)
    def handle_404(error: Literal[404]) -> ResponseReturnValue:
        return render_template("common/errors/404.html", service_desk_url=app.config["SERVICE_DESK_URL"]), 404


def _register_custom_converters(app: Flask) -> None:
    """
    This registers some custom converters for URL routing in Flask.

    We're used to standard converts like uuid, eg:

        @app.route("/grant/<uuid:grant_id")
        def handler(grant_id: uuid.UUID):
            ...

    Here we register some Enums to use as converters as well, so that the plaintext representation in a URL
    is converted automatically to an enum value, eg:

        @app.route("/submissions/<submission_mode:mode>")
        def handler(submission_mode: SubmissionModeEnum):
            ...
    """

    class SubmissionModeConverter(BaseConverter):
        def to_python(self, value: str) -> t.Any:
            value = value.lower()
            return SubmissionModeEnum(value.lower())

        def to_url(self, value: t.Any) -> str:
            return str(value).lower()

    app.url_map.converters["submission_mode"] = SubmissionModeConverter


def create_app() -> Flask:
    from app.common.data.base import BaseModel

    app = Flask(__name__, static_folder="assets/dist/", static_url_path="/static")
    app.config.from_object(get_settings())

    # Initialise extensions
    logging.init_app(app)
    patch_sqlalchemy_lite_async()
    db.init_app(app)
    auto_commit_after_request.init_app(app)
    migrate.init_app(
        app,
        db,  # type: ignore[arg-type]  # not natively compatible with Flask-SQLAlchemy-Lite; but is fine for us.
        directory="app/common/data/migrations",
        compare_type=True,
        render_as_batch=True,
        metadatas=BaseModel.metadata,
    )
    flask_assets_vite.init_app(app)
    toolbar.init_app(app)
    notification_service.init_app(app)
    talisman.init_app(app, **app.config["TALISMAN_SETTINGS"])
    login_manager.init_app(app)
    register_signals(app)
    record_sqlalchemy_queries.init_app(app, db)

    @login_manager.user_loader  # type: ignore[misc]
    def load_user(user_id: str) -> Optional["User"]:
        return interfaces.user.get_user(user_id)

    # This section is needed for url_for("foo", _external=True) to
    # automatically generate http scheme when this sample is
    # running on localhost, and to generate https scheme when it is
    # deployed behind reversed proxy.
    # See also #proxy_setups section at
    # flask.palletsprojects.com/en/1.0.x/deploying/wsgi-standalone
    from werkzeug.middleware.proxy_fix import ProxyFix

    app.wsgi_app = (  # type: ignore[method-assign]
        ProxyFix(app.wsgi_app, x_proto=app.config["PROXY_FIX_PROTO"], x_host=app.config["PROXY_FIX_HOST"])
    )

    # Configure templates
    app.jinja_loader = ChoiceLoader(
        [
            PackageLoader("app.common"),
            PackageLoader("app.access_grant_funding"),
            PackageLoader("app.deliver_grant_funding"),
            PackageLoader("app.developers"),
            PrefixLoader({"govuk_frontend_jinja": PackageLoader("govuk_frontend_jinja")}),
            PrefixLoader({"govuk_frontend_wtf": PackageLoader("govuk_frontend_wtf")}),
        ]
    )
    WTFormsHelpers(app)

    Babel(app)
    app.jinja_env.add_extension("jinja2.ext.i18n")
    app.jinja_env.add_extension("jinja2.ext.do")

    @app.context_processor
    def _jinja_template_context() -> dict[str, Any]:
        return dict(
            format_date=format_date,
            format_date_short=format_date_short,
            format_datetime=format_datetime,
            format_date_range=format_date_range,
            format_datetime_range=format_datetime_range,
            to_ordinal=to_ordinal,
            enum=dict(
                submission_mode=SubmissionModeEnum,
                flash_message_type=FlashMessageType,
                question_type=QuestionDataType,
                form_runner_state=FormRunnerState,
                submission_status=SubmissionStatusEnum,
                tasklist_task_status=TasklistTaskStatusEnum,
            ),
        )

    # TODO: Remove our basic auth application code when the app is deployed behind CloudFront and the app is not
    #       otherwise publicly accessible; we can then do basic auth through something like a cloudfront edge function
    #       rather than application code.
    if app.config["BASIC_AUTH_ENABLED"]:

        @app.before_request
        def basic_auth() -> ResponseReturnValue | None:
            from flask import request

            unauth_response = Response(status=401, headers={"WWW-Authenticate": "Basic"})

            if request.endpoint == "healthcheck.healthcheck":
                return None

            auth = request.authorization
            if not auth:
                return unauth_response

            if auth.type != "basic":
                return unauth_response

            username, password = auth.parameters["username"], auth.parameters["password"]
            if username != app.config["BASIC_AUTH_USERNAME"] or password != app.config["BASIC_AUTH_PASSWORD"]:
                return unauth_response

            return None

    # Attach routes
    _register_custom_converters(app)

    from app.access_grant_funding.routes import access_grant_funding_blueprint
    from app.common.auth import auth_blueprint
    from app.deliver_grant_funding.routes import deliver_grant_funding_blueprint
    from app.developers import developers_blueprint
    from app.healthcheck import healthcheck_blueprint

    app.register_blueprint(healthcheck_blueprint)
    app.register_blueprint(access_grant_funding_blueprint)
    app.register_blueprint(deliver_grant_funding_blueprint)
    app.register_blueprint(developers_blueprint)
    app.register_blueprint(auth_blueprint)

    _register_global_error_handlers(app)

    @app.route("/", methods=["GET"])
    def index() -> ResponseReturnValue:
        return redirect(url_for("deliver_grant_funding.list_grants"))

    # when developing we want the toolbar assets to not cause the page to flicker
    # otherwise we don't want the server to continually 304 on assets the browser has
    # should make an intentional decision for when to be setting this
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 3600
    app.add_template_global(AuthorisationHelper, "authorisation_helper")
    return app
