from datetime import date
from decimal import Decimal

import pytest

from app import CollectionStatusEnum
from app.common.collections.types import DecimalAnswer, IntegerAnswer, TextSingleLineAnswer
from app.common.data.models import get_ordered_nested_components
from app.common.data.types import (
    DataSourceSchema,
    DataSourceSchemaColumn,
    DataSourceType,
    NumberTypeEnum,
    QuestionDataOptions,
    QuestionDataType,
    QuestionPresentationOptions,
)


class TestNestedComponents:
    def test_get_components_empty(self):
        assert get_ordered_nested_components([]) == []

    def test_get_components_flat(self, factories):
        form = factories.form.build()
        questions = factories.question.build_batch(3, form=form)
        assert get_ordered_nested_components(form.components) == questions

    def test_get_components_nested(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form)
        group = factories.group.build(form=form)
        nested_questions = factories.question.build_batch(3, parent=group)
        g2 = factories.group.build(parent=group)
        nested_questions2 = factories.question.build_batch(3, parent=g2)
        q2 = factories.question.build(form=form)

        assert get_ordered_nested_components(form.components) == [
            q1,
            group,
            *nested_questions,
            g2,
            *nested_questions2,
            q2,
        ]

    def test_get_components_filters_nested(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form)
        group = factories.group.build(form=form)
        nested_questions = factories.question.build_batch(3, parent=group)
        g2 = factories.group.build(parent=group)
        nested_questions2 = factories.question.build_batch(3, parent=g2)
        q2 = factories.question.build(form=form)

        assert form.cached_questions == [q1, *nested_questions, *nested_questions2, q2]
        assert group.cached_questions == [*nested_questions, *nested_questions2]

    def test_get_components_nested_orders(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, order=2)
        group = factories.group.build(form=form, order=0)
        nested_q = factories.question.build(parent=group, order=0)
        q2 = factories.question.build(form=form, order=1)

        assert get_ordered_nested_components(form.components) == [group, nested_q, q2, q1]
        assert form.cached_questions == [nested_q, q2, q1]

    def test_get_components_nested_depth_5(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form)
        group1 = factories.group.build(form=form)
        group2 = factories.group.build(parent=group1)
        group3 = factories.group.build(parent=group2)
        group4 = factories.group.build(parent=group3)
        group5 = factories.group.build(parent=group4)
        nested_q = factories.question.build(parent=group5)
        q2 = factories.question.build(form=form)

        assert get_ordered_nested_components(form.components) == [
            q1,
            group1,
            group2,
            group3,
            group4,
            group5,
            nested_q,
            q2,
        ]
        assert form.cached_questions == [q1, nested_q, q2]


class TestAddAnother:
    def test_add_another_false(self, factories):
        question = factories.question.build()
        assert question.add_another is False

    def test_add_another_true(self, factories):
        question = factories.question.build(add_another=True)
        assert question.add_another is True

    def test_no_add_another_container(self, factories):
        form = factories.form.build()
        question1 = factories.question.build(form=form)

        assert question1.add_another is False
        assert question1.add_another_container is None

        group1 = factories.group.build(form=form)
        question2 = factories.question.build(parent=group1)
        assert question2.add_another is False
        assert question2.add_another_container is None
        assert group1.add_another is False
        assert group1.add_another_container is None

        group2 = factories.group.build(parent=group1)
        question3 = factories.question.build(parent=group2)
        assert question3.add_another is False
        assert question3.add_another_container is None
        assert group2.add_another is False
        assert group2.add_another_container is None

    def test_add_another_container_is_self(self, factories):
        form = factories.form.build()
        question = factories.question.build(form=form, add_another=True)

        assert question.add_another_container == question

    def test_add_another_container_is_immediate_group_parent(self, factories):
        form = factories.form.build()
        group = factories.group.build(form=form, add_another=True)
        question = factories.question.build(parent=group)

        assert question.add_another is False
        assert group.add_another is True
        assert question.add_another_container == group
        assert group.add_another_container == group

    def test_add_another_container_is_ancestor_group(self, factories):
        form = factories.form.build()
        group1 = factories.group.build(form=form, add_another=True)
        group2 = factories.group.build(parent=group1)
        question = factories.question.build(parent=group2)

        assert question.add_another is False
        assert group1.add_another is True
        assert group2.add_another is False
        assert question.add_another_container == group1
        assert group2.add_another_container == group1
        assert group1.add_another_container == group1


class TestGrantAccessReports:
    def test_access_reports(self, factories):
        grant = factories.grant.build()
        report1 = factories.collection.build(grant=grant, status=CollectionStatusEnum.OPEN)
        report2 = factories.collection.build(grant=grant, status=CollectionStatusEnum.CLOSED)
        _ = factories.collection.build(grant=grant, status=CollectionStatusEnum.DRAFT)

        result = grant.access_reports
        assert len(result) == 2
        assert result[0].id == report1.id
        assert result[1].id == report2.id

    def test_get_access_reports_no_collections(self, db_session, factories):
        grant = factories.grant.build()

        results_grant_has_no_collections = grant.access_reports
        assert len(results_grant_has_no_collections) == 0

    def test_get_access_reports_wrong_state(self, factories):
        grant = factories.grant.build()
        factories.collection.build(grant=grant, status=CollectionStatusEnum.DRAFT)

        results_grant_has_collections_in_wrong_state = grant.access_reports
        assert len(results_grant_has_collections_in_wrong_state) == 0

    def test_get_access_reports_sort_order_status(self, factories):
        grant = factories.grant.build()
        report1 = factories.collection.build(grant=grant, status=CollectionStatusEnum.OPEN)
        report2 = factories.collection.build(grant=grant, status=CollectionStatusEnum.CLOSED)
        report3 = factories.collection.build(grant=grant, status=CollectionStatusEnum.OPEN)

        results = grant.access_reports
        assert len(results) == 3
        assert results[0].id == report1.id
        assert results[1].id == report3.id
        assert results[2].id == report2.id

    def test_get_access_reports_sort_order_date(self, factories):
        grant = factories.grant.build()
        report1 = factories.collection.build(
            grant=grant, status=CollectionStatusEnum.OPEN, submission_period_end_date=date(2024, 1, 1)
        )
        report2 = factories.collection.build(
            grant=grant, status=CollectionStatusEnum.OPEN, submission_period_end_date=date(2023, 1, 1)
        )
        report3 = factories.collection.build(
            grant=grant, status=CollectionStatusEnum.OPEN, submission_period_end_date=date(2022, 1, 1)
        )

        results = grant.access_reports
        assert len(results) == 3
        assert results[0].id == report3.id
        assert results[1].id == report2.id
        assert results[2].id == report1.id

    def test_get_access_reports_sort_order_date_and_status(self, factories):
        grant = factories.grant.build()
        report0 = factories.collection.build(
            grant=grant, status=CollectionStatusEnum.CLOSED, submission_period_end_date=None
        )
        report1 = factories.collection.build(
            grant=grant, status=CollectionStatusEnum.OPEN, submission_period_end_date=date(2024, 1, 1)
        )
        report2 = factories.collection.build(
            grant=grant, status=CollectionStatusEnum.OPEN, submission_period_end_date=date(2023, 1, 1)
        )
        report3 = factories.collection.build(
            grant=grant, status=CollectionStatusEnum.OPEN, submission_period_end_date=date(2022, 1, 2)
        )
        report4 = factories.collection.build(
            grant=grant, status=CollectionStatusEnum.CLOSED, submission_period_end_date=date(2023, 2, 1)
        )
        report5 = factories.collection.build(
            grant=grant, status=CollectionStatusEnum.CLOSED, submission_period_end_date=date(2022, 1, 1)
        )

        results = grant.access_reports
        assert len(results) == 6
        assert results[0].id == report3.id
        assert results[1].id == report2.id
        assert results[2].id == report1.id
        assert results[3].id == report5.id
        assert results[4].id == report4.id
        assert results[5].id == report0.id


def _text_col(original_column_name: str) -> DataSourceSchemaColumn:
    return DataSourceSchemaColumn(
        data_type=QuestionDataType.TEXT_SINGLE_LINE,
        presentation_options=QuestionPresentationOptions(),
        data_options=QuestionDataOptions(),
        original_column_name=original_column_name,
    )


def _decimal_col(
    original_column_name: str, prefix: str = "", suffix: str = "", max_decimal_places: int = 2
) -> DataSourceSchemaColumn:
    return DataSourceSchemaColumn(
        data_type=QuestionDataType.NUMBER,
        presentation_options=QuestionPresentationOptions(prefix=prefix or None, suffix=suffix or None),
        data_options=QuestionDataOptions(number_type=NumberTypeEnum.DECIMAL, max_decimal_places=max_decimal_places),
        original_column_name=original_column_name,
    )


def _integer_col(original_column_name: str, prefix: str = "", suffix: str = "") -> DataSourceSchemaColumn:
    return DataSourceSchemaColumn(
        data_type=QuestionDataType.NUMBER,
        presentation_options=QuestionPresentationOptions(prefix=prefix or None, suffix=suffix or None),
        data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        original_column_name=original_column_name,
    )


class TestDataSourceMakePydanticModel:
    def test_returns_empty_dict_when_no_schema_and_2d_data(self, factories):
        data_source = factories.data_source.build(
            name="Test data set", type=DataSourceType.GRANT_RECIPIENT, schema=None
        )
        assert data_source.build_typed_org_item_data({"capital-allocation": "1000"}) == {}

    def test_returns_empty_list_when_no_schema_and_3d_data(self, factories):
        data_source = factories.data_source.build(name="Test data set", type=DataSourceType.PROJECT_LEVEL, schema=None)
        assert data_source.build_typed_org_item_data([{"capital-allocation": "1000"}]) == []

    def test_text_column_returns_text_single_line_answer(self, factories):
        data_source = factories.data_source.build(
            name="Test data set",
            type=DataSourceType.STATIC,
            schema=DataSourceSchema.model_validate({"theme-name": _text_col("Theme name")}),
        )

        result = data_source.build_typed_org_item_data({"theme-name": "Electricity"})

        assert isinstance(result["theme-name"], TextSingleLineAnswer)
        assert result["theme-name"].get_value_for_interpolation() == "Electricity"

    def test_decimal_column_with_prefix_formats_correctly(self, factories):
        data_source = factories.data_source.build(
            name="Test data set",
            type=DataSourceType.GRANT_RECIPIENT,
            schema=DataSourceSchema.model_validate({"allocation": _decimal_col("Allocation", prefix="£")}),
        )

        result = data_source.build_typed_org_item_data({"allocation": "1000.00"})

        answer = result["allocation"]
        assert isinstance(answer, DecimalAnswer)
        assert answer.value == Decimal("1000.00")
        assert answer.get_value_for_interpolation() == "£1,000.00"

    def test_decimal_column_without_prefix_formats_correctly(self, factories):
        data_source = factories.data_source.build(
            name="Test data set",
            type=DataSourceType.GRANT_RECIPIENT,
            schema=DataSourceSchema.model_validate({"allocation": _decimal_col("Allocation")}),
        )

        result = data_source.build_typed_org_item_data({"allocation": "500.50"})

        assert result["allocation"].get_value_for_interpolation() == "500.50"

    def test_integer_column_with_suffix_formats_correctly(self, factories):
        data_source = factories.data_source.build(
            name="Test data set",
            type=DataSourceType.GRANT_RECIPIENT,
            schema=DataSourceSchema.model_validate({"headcount": _integer_col("Headcount", suffix=" people")}),
        )

        result = data_source.build_typed_org_item_data({"headcount": 42})

        answer = result["headcount"]
        assert isinstance(answer, IntegerAnswer)
        assert answer.value == 42
        assert answer.get_value_for_interpolation() == "42 people"

    def test_none_value_returns_none(self, factories):
        data_source = factories.data_source.build(
            name="Test data set",
            type=DataSourceType.GRANT_RECIPIENT,
            schema=DataSourceSchema.model_validate({"allocation": _decimal_col("Allocation", prefix="£")}),
        )

        result = data_source.build_typed_org_item_data({"allocation": None})
        assert result["allocation"] is None

    def test_missing_key_in_row_treated_as_none(self, factories):
        data_source = factories.data_source.build(
            name="Test data set",
            type=DataSourceType.GRANT_RECIPIENT,
            schema=DataSourceSchema.model_validate({"allocation": _decimal_col("Allocation", prefix="£")}),
        )

        result = data_source.build_typed_org_item_data({})
        assert result["allocation"] is None

    def test_multiple_columns_all_typed_correctly(self, factories):
        data_source = factories.data_source.build(
            name="Test data set",
            type=DataSourceType.GRANT_RECIPIENT,
            schema=DataSourceSchema.model_validate(
                {
                    "theme-name": _text_col("Theme name"),
                    "allocation": _decimal_col("Allocation", prefix="£"),
                    "headcount": _integer_col("Headcount"),
                }
            ),
        )

        result = data_source.build_typed_org_item_data(
            {
                "theme-name": "Electricity",
                "allocation": "1000.00",
                "headcount": 5,
            }
        )

        assert isinstance(result["theme-name"], TextSingleLineAnswer)
        assert isinstance(result["allocation"], DecimalAnswer)
        assert isinstance(result["headcount"], IntegerAnswer)

    def test_3d_project_level_returns_list_of_dicts(self, factories):
        data_source = factories.data_source.build(
            name="Test data set",
            type=DataSourceType.PROJECT_LEVEL,
            schema=DataSourceSchema.model_validate(
                {
                    "project-name": _text_col("Project name"),
                    "allocation": _decimal_col("Allocation", prefix="£", max_decimal_places=2),
                }
            ),
        )

        result = data_source.build_typed_org_item_data(
            [
                {"project-name": "Alpha", "allocation": "500.00"},
                {"project-name": "Beta", "allocation": "1500.00"},
            ]
        )

        assert isinstance(result, list)
        assert len(result) == 2
        assert isinstance(result[0]["project-name"], TextSingleLineAnswer)
        assert isinstance(result[0]["allocation"], DecimalAnswer)
        assert result[0]["allocation"].get_value_for_interpolation() == "£500.00"
        assert result[1]["allocation"].get_value_for_interpolation() == "£1,500.00"

    def test_3d_each_row_in_list_is_independently_typed(self, factories):
        data_source = factories.data_source.build(
            name="Test data set",
            type=DataSourceType.PROJECT_LEVEL,
            schema=DataSourceSchema.model_validate({"allocation": _decimal_col("Allocation", prefix="£")}),
        )

        result = data_source.build_typed_org_item_data(
            [
                {"allocation": "100.00"},
                {"allocation": None},
                {"allocation": "300.00"},
            ]
        )

        assert isinstance(result[0]["allocation"], DecimalAnswer)
        assert result[1]["allocation"] is None
        assert isinstance(result[2]["allocation"], DecimalAnswer)


class TestDataSourceBuildAnswerForColumn:
    def test_none_value_always_returns_none_regardless_of_column_type(self, factories):
        data_source = factories.data_source.build(
            name="Test data set",
            type=DataSourceType.GRANT_RECIPIENT,
            schema=DataSourceSchema.model_validate({"allocation": _decimal_col("Allocation", prefix="£")}),
        )

        result = data_source._build_answer_for_column(None, data_source.schema.root["allocation"])
        assert result is None

    def test_decimal_value_stored_as_string_is_correctly_parsed(self, factories):
        data_source = factories.data_source.build(
            name="Test data set",
            type=DataSourceType.GRANT_RECIPIENT,
            schema=DataSourceSchema.model_validate({"allocation": _decimal_col("Allocation", prefix="£")}),
        )

        result = data_source._build_answer_for_column("1234.56", data_source.schema.root["allocation"])

        assert isinstance(result, DecimalAnswer)
        assert result.value == Decimal("1234.56")

    def test_integer_value_stored_as_int_is_correctly_parsed(self, factories):
        data_source = factories.data_source.build(
            name="Test data set",
            type=DataSourceType.GRANT_RECIPIENT,
            schema=DataSourceSchema.model_validate({"allocation": _integer_col("Allocation")}),
        )

        result = data_source._build_answer_for_column(42, data_source.schema.root["allocation"])

        assert isinstance(result, IntegerAnswer)
        assert result.value == 42

    def test_prefix_and_suffix_set_when_present_on_column(self, factories):
        data_source = factories.data_source.build(
            name="Test data set",
            type=DataSourceType.GRANT_RECIPIENT,
            schema=DataSourceSchema.model_validate(
                {
                    "allocation": _decimal_col("Allocation", prefix="£"),
                    "distance": _integer_col("Distance", suffix="km"),
                }
            ),
        )

        prefix_column = data_source._build_answer_for_column("1.5", data_source.schema.root["allocation"])
        assert isinstance(prefix_column, DecimalAnswer)
        assert prefix_column.prefix == "£"

        suffix_column = data_source._build_answer_for_column("1000", data_source.schema.root["distance"])
        assert isinstance(suffix_column, IntegerAnswer)
        assert suffix_column.suffix == "km"

    def test_no_prefix_or_suffix_when_not_set_on_column(self, factories):
        data_source = factories.data_source.build(
            name="Test data set",
            type=DataSourceType.GRANT_RECIPIENT,
            schema=DataSourceSchema.model_validate({"allocation": _decimal_col("Allocation")}),
        )

        result = data_source._build_answer_for_column("100.5", data_source.schema.root["allocation"])

        assert result.prefix is None
        assert result.suffix is None

    def test_unsupported_number_type_logs_error_and_raises(self, factories, caplog):
        data_source = factories.data_source.build(
            name="Test data set",
            type=DataSourceType.GRANT_RECIPIENT,
            schema=DataSourceSchema.model_validate({"column": _decimal_col("Bad column")}),
        )
        column = data_source.schema.root["column"]
        column.data_options.number_type = None

        with pytest.raises(ValueError, match="Unsupported number_type"):
            data_source._build_answer_for_column("123", column)

        assert len(caplog.messages) == 1
        assert "Unsupported number_type" in caplog.messages[0]
        assert "Bad column" in caplog.messages[0]

    def test_unsupported_data_type_logs_error_and_raises(self, factories, caplog):
        data_source = factories.data_source.build(
            name="Test data set",
            type=DataSourceType.GRANT_RECIPIENT,
            schema=DataSourceSchema.model_validate({"column": _text_col("Bad column")}),
        )
        column = data_source.schema.root["column"]
        column.data_type = QuestionDataType.DATE

        with pytest.raises(ValueError, match="Unsupported data_type"):
            data_source._build_answer_for_column("2024-01-01", column)

        assert len(caplog.messages) == 1
        assert "Unsupported data_type" in caplog.messages[0]
        assert "Bad column" in caplog.messages[0]
