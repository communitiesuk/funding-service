import os
import threading

from flask import current_app
from playwright.sync_api import sync_playwright

# Playwright's sync API runs an asyncio loop while it talks to chromium. Under gunicorn+gevent,
# multiple greenlets share an OS thread and asyncio's running-loop is thread-local, so concurrent
# PDF exports on one worker would observe each other's loop and Playwright would raise. Serialise
# PDF generation per worker. threading.Lock is monkey-patched by gevent into a greenlet-aware lock,
# so blocked greenlets cooperatively yield rather than block the OS thread.
_pdf_export_lock = threading.Lock()


def render_pdf(html_content: str) -> bytes:
    # as we're calling to an external binary this makes sure we're set up if the flask app
    # has defined its own path, this could also be set in the container terraform
    with _pdf_export_lock:
        if current_app.config["PLAYWRIGHT_BROWSERS_PATH"] is not None:
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = current_app.config["PLAYWRIGHT_BROWSERS_PATH"]

        # note that we're opening a new browser per request
        # with a single request at a time this responds in ~200ms but if we ever anticipate higher
        # simultaneous usage we'd probably want a singleton module to manage the browser connection
        # and close and open pages as needed, this would allow a lot more simultaneous requests to be
        # processed performantly
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(
                java_script_enabled=False,
                http_credentials={
                    "username": current_app.config["BASIC_AUTH_USERNAME"],
                    "password": current_app.config["BASIC_AUTH_PASSWORD"],
                }
                if current_app.config["BASIC_AUTH_ENABLED"]
                else None,
            )
            page.set_content(html_content, wait_until="load")
            pdf_bytes = page.pdf(
                format="A4",
                print_background=True,
                scale=0.9,
                margin={"top": "5mm", "bottom": "5mm", "left": "5mm", "right": "5mm"},
            )

    return pdf_bytes
