import typing as t
from typing import Any, Generator

import html5lib
import pytest
from _pytest.config import Config
from _pytest.config.argparsing import Parser
from flask import Flask
from flask.testing import FlaskClient
from werkzeug.test import TestResponse

from app import create_app

html5parser = html5lib.HTMLParser(strict=False)


def pytest_addoption(parser: Parser) -> None:
    parser.addoption("--e2e", action="store_true", default=False, help="run e2e (browser) tests")
    parser.addoption("--e2e-env", default="local", choices=["local"], action="store", help="run e2e (browser) tests")
    parser.addoption(
        "--viewport",
        default="1920x1080",
        type=str,
        help="Change the viewport size of the browser window used for playwright tests (default: 1920x1080)",
    )


def pytest_collection_modifyitems(config: Config, items: list[Any]) -> None:
    # Determines whether e2e tests have been requested. If not, skips anything marked as e2e.
    # If e2e tests are requested, skips everything not marked as e2e
    skip_e2e = pytest.mark.skip(reason="only running non-e2e tests")
    skip_non_e2e = pytest.mark.skip(reason="only running e2e tests")

    e2e_run = config.getoption("--e2e")
    if e2e_run:
        for item in items:
            if "e2e" not in item.keywords:
                item.add_marker(skip_non_e2e)
    else:
        for item in items:
            if "e2e" in item.keywords:
                item.add_marker(skip_e2e)


class FundingServiceTestClient(FlaskClient):
    def open(
        self,
        *args: t.Any,
        buffered: bool = False,
        follow_redirects: bool = False,
        **kwargs: t.Any,
    ) -> TestResponse:
        response = super().open(*args, buffered=buffered, follow_redirects=follow_redirects, **kwargs)

        # Validate that our HTML is well-structured.
        if response.content_type.startswith("text/html"):
            html = response.data.decode()
            html5parser.parse(html)

            if html5parser.errors:
                location, error, _extra_info = html5parser.errors[-1]
                line_number, character_number = location
                line_with_context = "\n".join(html.splitlines()[line_number - 10 : line_number])

                # TODO: remove this when https://github.com/communitiesuk/funding-service/pull/36 has been merged.
                if "FLASK_VITE_HEADER" not in line_with_context and "^ unexpected-end-tag" not in line_with_context:
                    raise html5lib.html5parser.ParseError(
                        f"\n\n{line_with_context}\n{' ' * (character_number - 1)}^ {error}"
                    )

        return response


@pytest.fixture(scope="session")
def app() -> Generator[Flask, None, None]:
    app = create_app()
    app.test_client_class = FundingServiceTestClient
    app.config.update({"TESTING": True})

    yield app


def _precompile_templates(app: Flask) -> None:
    # Precompile all of our Jinja2 templates so that this doesn't happen within individual tests. It can lead to the
    # first test that hits templates taking significantly longer than its baseline, which makes it harder for us
    # to add time limits on tests that we run (see `_integration_test_timeout` below).
    # This doesn't *completely* warm up the flask app - still seeing that some first runs are a bit slower, but this
    # takes away a significant amount of the difference between the first and second pass.
    for template_name in app.jinja_env.list_templates():
        app.jinja_env.get_template(template_name)
