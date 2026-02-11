import pytest

from app.common.utils import comma_join_items, slugify


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


@pytest.mark.parametrize(
    "items, join_word, expected",
    [
        ([], "and", ""),
        (["foo"], "and", "foo"),
        (["foo", "bar"], "and", "foo and bar"),
        (["foo", "bar", "baz"], "and", "foo, bar, and baz"),
        (["a", "b", "c", "d"], "and", "a, b, c, and d"),
        (["foo", "bar"], "or", "foo or bar"),
        (["foo", "bar", "baz"], "or", "foo, bar, or baz"),
    ],
)
def test_comma_join_items(items, join_word, expected):
    assert comma_join_items(items, join_word=join_word) == expected
