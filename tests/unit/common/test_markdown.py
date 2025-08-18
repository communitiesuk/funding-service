import pytest
from flask import Flask, render_template_string
from markupsafe import Markup

from app.common.markdown import FlaskGOVUKMarkdown, _GOVUKRenderer, convert_text_to_govuk_markup


class TestGOVUKRenderer:
    def setup_method(self):
        self.renderer = _GOVUKRenderer(escape=True, allow_harmful_protocols=False)

    def test_link(self):
        result = self.renderer.link("Example", "https://example.com", "Example Title")
        expected = (
            '<a href="https://example.com" class="govuk-link govuk-link--no-visited-state" title="Example Title">'
            "Example"
            "</a>"
        )
        assert result == expected

    def test_link_without_title(self):
        result = self.renderer.link("Example", "https://example.com")
        expected = '<a href="https://example.com" class="govuk-link govuk-link--no-visited-state">Example</a>'
        assert result == expected

    def test_image_with_alt_text(self):
        result = self.renderer.image("Alt text", "https://example.com/image.jpg", "Image Title")
        assert result == "Alt text"

    def test_image_without_alt_text(self):
        result = self.renderer.image("", "https://example.com/image.jpg")
        assert result == ""

    def test_emphasis_strips_formatting(self):
        result = self.renderer.emphasis("emphasized text")
        assert result == "emphasized text"

    def test_strong_strips_formatting(self):
        result = self.renderer.strong("strong text")
        assert result == "strong text"

    def test_codespan_strips_formatting(self):
        result = self.renderer.codespan("code text")
        assert result == "code text"

    def test_linebreak(self):
        result = self.renderer.linebreak()
        assert result == "<br>\n"

    def test_inline_html_escapes(self):
        result = self.renderer.inline_html("<script>alert('xss')</script>")
        assert result == "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;"

    def test_paragraph(self):
        result = self.renderer.paragraph("Test paragraph")
        assert result == "<p class='govuk-body'>Test paragraph</p>\n"

    def test_heading_level_2(self):
        result = self.renderer.heading("Test Heading", 2)
        assert result == '<h2 class="govuk-heading-m">Test Heading</h2>\n'

    def test_heading_other_levels(self):
        result = self.renderer.heading("Test Heading", 1)
        assert result == '<p class="govuk-body">Test Heading</p>\n'

        result = self.renderer.heading("Test Heading", 3)
        assert result == '<p class="govuk-body">Test Heading</p>\n'

    def test_blank_line(self):
        result = self.renderer.blank_line()
        assert result == ""

    def test_thematic_break(self):
        result = self.renderer.thematic_break()
        assert result == ""

    def test_block_text(self):
        result = self.renderer.block_text("block text")
        assert result == "block text"

    def test_block_code(self):
        result = self.renderer.block_code("  print('hello')  \n")
        assert result == "<p class='govuk-body'>print(&#x27;hello&#x27;)</p>\n"

    def test_block_quote(self):
        result = self.renderer.block_quote("<p>quoted text</p>")
        assert result == "<p class='govuk-body'>quoted text</p>\n"

    def test_block_html_escapes(self):
        result = self.renderer.block_html("<div>test</div>")
        assert result == "&lt;div&gt;test&lt;/div&gt;"

    def test_block_error_escapes(self):
        result = self.renderer.block_error("<error>test</error>")
        assert result == "&lt;error&gt;test&lt;/error&gt;"

    def test_unordered_list(self):
        result = self.renderer.list("list content", False)
        assert result == '<ul class="govuk-list govuk-list--bullet">\nlist content</ul>\n'

    def test_ordered_list(self):
        result = self.renderer.list("list content", True)
        assert result == '<ol class="govuk-list govuk-list--number">\nlist content</ol>\n'

    def test_list_item(self):
        result = self.renderer.list_item("item text")
        assert result == "<li>item text</li>\n"


class TestConvertTextToGovukMarkup:
    def test_handles_empty_string(self):
        result = convert_text_to_govuk_markup("")
        assert isinstance(result, Markup)
        assert str(result) == ""

    def test_escapes_html_in_markdown(self):
        markdown_text = "This has <script>alert('xss')</script> in it."
        result = convert_text_to_govuk_markup(markdown_text)

        assert str(result) == "<p class='govuk-body'>This has &lt;script&gt;alert('xss')&lt;/script&gt; in it.</p>\n"

    def test_h2_headings(self):
        markdown_text = "## Heading Level 2"
        result = convert_text_to_govuk_markup(markdown_text)
        expected = '<h2 class="govuk-heading-m">Heading Level 2</h2>\n'
        assert str(result) == expected

    def test_bullet_lists(self):
        markdown_text = "- Item 1\n- Item 2\n- Item 3"
        result = convert_text_to_govuk_markup(markdown_text)
        expected = (
            '<ul class="govuk-list govuk-list--bullet">\n<li>Item 1</li>\n<li>Item 2</li>\n<li>Item 3</li>\n</ul>\n'
        )
        assert str(result) == expected

    def test_numbered_lists(self):
        markdown_text = "1. First item\n2. Second item\n3. Third item"
        result = convert_text_to_govuk_markup(markdown_text)
        expected = (
            '<ol class="govuk-list govuk-list--number">\n'
            "<li>First item</li>\n"
            "<li>Second item</li>\n"
            "<li>Third item</li>"
            "\n</ol>\n"
        )
        assert str(result) == expected

    def test_paragraphs(self):
        markdown_text = "This is a paragraph.\n\nThis is another paragraph."
        result = convert_text_to_govuk_markup(markdown_text)
        expected = (
            "<p class='govuk-body'>This is a paragraph.</p>\n<p class='govuk-body'>This is another paragraph.</p>\n"
        )
        assert str(result) == expected

    def test_links(self):
        markdown_text = "Visit [Example](https://example.com) for more info."
        result = convert_text_to_govuk_markup(markdown_text)
        expected = (
            "<p class='govuk-body'>"
            "Visit "
            '<a href="https://example.com" class="govuk-link govuk-link--no-visited-state">Example</a> '
            "for more info.</p>\n"
        )
        assert str(result) == expected

    @pytest.mark.parametrize(
        "markdown_input,expected_output",
        [
            ("**bold**", "<p class='govuk-body'>bold</p>\n"),
            ("*italic*", "<p class='govuk-body'>italic</p>\n"),
            ("`code`", "<p class='govuk-body'>code</p>\n"),
            ("![alt](image.jpg)", "<p class='govuk-body'>alt</p>\n"),
        ],
    )
    def test_strips_formatting(self, markdown_input, expected_output):
        result = convert_text_to_govuk_markup(markdown_input)
        assert expected_output == str(result)


class TestFlaskGOVUKMarkdown:
    def test_jinja_filter_integration(self):
        app = Flask(__name__)
        FlaskGOVUKMarkdown(app)

        with app.app_context():
            result = render_template_string('{{ "## Heading" | govuk_markdown }}')
            assert '<h2 class="govuk-heading-m">Heading</h2>' in str(result)
