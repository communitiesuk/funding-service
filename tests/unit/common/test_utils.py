import uuid

import pytest

from app.common.utils import comma_join_items, slugify, to_dict, uppercase_first


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
        (["foo", "bar", "baz"], "and", "foo, bar and baz"),
        (["a", "b", "c", "d"], "and", "a, b, c and d"),
        (["foo", "bar"], "or", "foo or bar"),
        (["foo", "bar", "baz"], "or", "foo, bar or baz"),
    ],
)
def test_comma_join_items(items, join_word, expected):
    assert comma_join_items(items, join_word=join_word) == expected


@pytest.mark.parametrize(
    "phrase, expected_phrase",
    (
        ("hello", "Hello"),
        ("hello world", "Hello world"),
        ("hello WORLD", "Hello WORLD"),
        ("Hello world", "Hello world"),
        ("123 world", "123 world"),
        ("@ oh no", "@ oh no"),
        (None, None),
    ),
)
def test_uppercase_first(phrase, expected_phrase):
    assert uppercase_first(phrase) == expected_phrase


class TestToDict:
    def test_basic_serialisation(self, factories):
        collection = factories.collection.build(name="Test Collection", slug="test-collection")
        result = to_dict(collection)
        assert result["name"] == "Test Collection"
        assert result["slug"] == "test-collection"
        assert "created_at_utc" not in result
        assert "updated_at_utc" not in result

    def test_excludes_none_values(self, factories):
        collection = factories.collection.build(reporting_period_start_date=None)
        result = to_dict(collection)
        assert "reporting_period_start_date" not in result

    def test_exclude_parameter(self, factories):
        collection = factories.collection.build(name="Test", slug="test")
        result = to_dict(collection, exclude=["slug"])
        assert "name" in result
        assert "slug" not in result

    def test_override_sets_value(self, factories):
        user_id = uuid.uuid4()
        collection = factories.collection.build()
        result = to_dict(collection, override={"created_by_id": user_id})
        assert result["created_by_id"] == user_id

    def test_override_can_set_none(self, factories):
        import datetime

        collection = factories.collection.build(
            reporting_period_start_date=datetime.date(2024, 1, 1),
        )
        result_without_override = to_dict(collection)
        assert result_without_override["reporting_period_start_date"] == datetime.date(2024, 1, 1)

        result_with_override = to_dict(collection, override={"reporting_period_start_date": None})
        assert result_with_override["reporting_period_start_date"] is None

    def test_override_rejects_unknown_key(self, factories):
        collection = factories.collection.build()
        with pytest.raises(ValueError, match="not_a_real_column"):
            to_dict(collection, override={"not_a_real_column": "value"})
