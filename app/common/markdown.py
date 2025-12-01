from html import escape
from typing import Any, Optional

import mistune
from flask import Flask
from markupsafe import Markup
from mistune import safe_entity
from mistune.renderers.html import HTMLRenderer


class _GOVUKRenderer(HTMLRenderer):
    # Taken from https://mistune.lepture.com/en/latest/renderers.html#available-methods

    # inline level
    def link(self, text: str, url: str, title: str | None = None) -> str:
        title_attr = f' title="{safe_entity(title)}"' if title else ""
        return f'<a href="{self.safe_url(url)}" class="govuk-link govuk-link--no-visited-state"{title_attr}>{text}</a>'

    def image(self, text: str, url: str, title: Optional[str] = None) -> str:
        return escape(text) if text else ""

    def emphasis(self, text: str) -> str:
        return text

    def strong(self, text: str) -> str:
        return text

    def codespan(self, text: str) -> str:
        return text

    def linebreak(self) -> str:
        return "<br>\n"

    def inline_html(self, html: str) -> str:
        return escape(html)

    # block level
    def paragraph(self, text: str) -> str:
        return f"<p class='govuk-body'>{text}</p>\n"

    def heading(self, text: str, level: int, **attrs: Any) -> str:
        if level == 2:
            return f'<h2 class="govuk-heading-m">{text}</h2>\n'
        else:
            # Convert other headings to plain text
            return f'<p class="govuk-body">{text}</p>\n'

    def blank_line(self) -> str:
        return ""

    def thematic_break(self) -> str:
        return ""

    def block_text(self, text: str) -> str:
        return text

    def block_code(self, code: str, info: str | None = None) -> str:
        return f"<p class='govuk-body'>{escape(code.strip())}</p>\n"

    def block_quote(self, text: str) -> str:
        clean_text = text.replace("<p>", "").replace("</p>", "").strip()
        return f"<p class='govuk-body'>{clean_text}</p>\n"

    def block_html(self, html: str) -> str:
        return escape(html)

    def block_error(self, text: str) -> str:
        return escape(text)

    def list(self, text: str, ordered: bool, **attrs: Any) -> str:
        if ordered:
            return f'<ol class="govuk-list govuk-list--number">\n{text}</ol>\n'
        else:
            return f'<ul class="govuk-list govuk-list--bullet">\n{text}</ul>\n'

    def list_item(self, text: str) -> str:
        return f"<li>{text}</li>\n"


def convert_text_to_govuk_markup(text: str) -> Markup:
    return Markup(
        mistune.create_markdown(
            renderer=_GOVUKRenderer(escape=True, allow_harmful_protocols=False),
            plugins=[],
        )(text)
    )


class FlaskGOVUKMarkdown:
    def __init__(self, app: Flask | None = None):
        if app:
            self.init_app(app)

    def init_app(self, app: Flask) -> None:
        app.jinja_env.filters["govuk_markdown"] = self.convert
        app.extensions["govuk_markdown"] = self

    def convert(self, text: str) -> Markup:
        return convert_text_to_govuk_markup(text or "")
