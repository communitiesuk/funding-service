import pytest

from app.common.utils import slugify


@pytest.mark.parametrize(
    "test_string, expected_result",
    [
        ("Hello World", "hello-world"),
        ("Hello, World!", "hello-world"),
        ("  Leading and trailing  ", "leading-and-trailing"),
        ("Multiple   Spaces", "multiple-spaces"),
        ("Special #$@! Characters", "special-characters"),
        ("Special #$@! Characters $%^$%^      Again    ", "special-characters-again"),
        ("unicode: ångström", "unicode-ngstrm"),
        ("MiXeD CaSe", "mixed-case"),
        ("Numbers 123 and text", "numbers-123-and-text"),
        ("", ""),
        ("    ", ""),
        ("Already-slugified-text", "already-slugified-text"),
        ("Under_score and-dash", "underscore-and-dash"),
        (None, ""),
        ("-", "-"),
    ],
)
def test_slugify(test_string, expected_result):
    assert slugify(test_string) == expected_result
