import pytest

from app import QuestionDataType
from app.common.data.types import (
    DataSourceSchemaColumn,
    ExpressionType,
    ManagedExpressionsEnum,
    NumberTypeEnum,
    QuestionDataOptions,
    QuestionPresentationOptions,
)
from app.deliver_grant_funding.session_models import (
    AddConditionDependsOnSessionModel,
    AddContextToComponentGuidanceSessionModel,
    AddContextToComponentSessionModel,
    AddContextToExpressionsModel,
    DataSetColumnMapping,
)


class TestSessionModels:
    class TestIncludeCurrentComponentWhenReferencingData:
        def test_always_false_models(self, factories):
            question = factories.question.build()
            component_session_model = AddContextToComponentSessionModel(
                data_type=QuestionDataType.NUMBER, field="component", component_form_data={}
            )
            guidance_session_model = AddContextToComponentGuidanceSessionModel(field="guidance", component_form_data={})
            condition_session_data = AddConditionDependsOnSessionModel(
                field="condition_depends_on", component_id=question.id
            )

            assert component_session_model.include_current_component_when_referencing_data(None) is False
            assert component_session_model.include_current_component_when_referencing_data(question) is False
            assert guidance_session_model.include_current_component_when_referencing_data(None) is False
            assert guidance_session_model.include_current_component_when_referencing_data(question) is False
            assert condition_session_data.include_current_component_when_referencing_data(None) is False
            assert condition_session_data.include_current_component_when_referencing_data(question) is False

        def test_should_include(self, factories):
            question = factories.question.build()

            session_data = AddContextToExpressionsModel(
                field=ExpressionType.VALIDATION,
                expression_form_data={"add_context": "custom_expression"},
                is_custom=True,
                managed_expression_name=None,
                component_id=question.id,
            )

            assert session_data.include_current_component_when_referencing_data(None) is False
            assert session_data.include_current_component_when_referencing_data(question) is True

        def test_only_custom_expressions_should_include(self, factories):
            question = factories.question.build()

            session_data = AddContextToExpressionsModel(
                field=ExpressionType.VALIDATION,
                expression_form_data={"add_context": "between"},
                is_custom=False,
                managed_expression_name=ManagedExpressionsEnum.BETWEEN,
                component_id=question.id,
            )

            assert session_data.include_current_component_when_referencing_data(None) is False
            assert session_data.include_current_component_when_referencing_data(question) is False

    class TestBuildDataSetColumnMappingFromDataSourceSchemaColumn:
        def test_text_single_line(self):
            schema_column = DataSourceSchemaColumn(
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                presentation_options=QuestionPresentationOptions(),
                data_options=QuestionDataOptions(),
                original_column_name="Grant allocation",
            )
            result = DataSetColumnMapping.build_from_data_source_schema_column(schema_column=schema_column)
            assert result.column_type == "TEXT"
            assert result.column_name == "Grant allocation"
            assert result.prefix is None
            assert result.suffix is None
            assert result.max_decimal_places is None

        @pytest.mark.parametrize("prefix,suffix", [(None, "km"), (None, None), ("$", None)])
        def test_integer(self, prefix, suffix):
            schema_column = DataSourceSchemaColumn(
                data_type=QuestionDataType.NUMBER,
                presentation_options=QuestionPresentationOptions(prefix=prefix, suffix=suffix),
                data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
                original_column_name="Grant allocation",
            )
            result = DataSetColumnMapping.build_from_data_source_schema_column(schema_column=schema_column)
            assert result.column_type == "INTEGER"
            assert result.column_name == "Grant allocation"
            assert result.prefix == prefix
            assert result.suffix == suffix
            assert result.max_decimal_places is None

        @pytest.mark.parametrize("prefix,suffix", [(None, "km"), (None, None), ("$", None), ("£", None)])
        def test_decimal(self, prefix, suffix):
            schema_column = DataSourceSchemaColumn(
                data_type=QuestionDataType.NUMBER,
                presentation_options=QuestionPresentationOptions(prefix=prefix, suffix=suffix),
                data_options=QuestionDataOptions(number_type=NumberTypeEnum.DECIMAL, max_decimal_places=3),
                original_column_name="Grant allocation",
            )
            result = DataSetColumnMapping.build_from_data_source_schema_column(schema_column=schema_column)
            assert result.column_type == "DECIMAL"
            assert result.column_name == "Grant allocation"
            assert result.prefix == prefix
            assert result.suffix == suffix
            assert result.max_decimal_places == 3

        def test_british_pounds(self):
            schema_column = DataSourceSchemaColumn(
                data_type=QuestionDataType.NUMBER,
                presentation_options=QuestionPresentationOptions(prefix="£"),
                data_options=QuestionDataOptions(number_type=NumberTypeEnum.DECIMAL, max_decimal_places=2),
                original_column_name="Grant allocation",
            )
            result = DataSetColumnMapping.build_from_data_source_schema_column(schema_column=schema_column)
            assert result.column_type == "BRITISH_POUNDS"
            assert result.column_name == "Grant allocation"
            assert result.prefix == "£"
            assert result.suffix is None
            assert result.max_decimal_places == 2

    class TestBritishPounds:
        @pytest.mark.parametrize(
            "column_type, schema_column",
            [
                (None, None),
                ("TEXT", None),
                ("INTEGER", None),
                ("DECIMAL", None),
                (
                    None,
                    DataSourceSchemaColumn(
                        data_type=QuestionDataType.TEXT_SINGLE_LINE,
                        presentation_options=QuestionPresentationOptions(),
                        data_options=QuestionDataOptions(),
                        original_column_name="col",
                    ),
                ),
                (
                    None,
                    DataSourceSchemaColumn(
                        data_type=QuestionDataType.NUMBER,
                        presentation_options=QuestionPresentationOptions(),
                        data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
                        original_column_name="col",
                    ),
                ),
                (
                    None,
                    DataSourceSchemaColumn(
                        data_type=QuestionDataType.NUMBER,
                        presentation_options=QuestionPresentationOptions(),
                        data_options=QuestionDataOptions(number_type=NumberTypeEnum.DECIMAL, max_decimal_places=3),
                        original_column_name="col",
                    ),
                ),
                (
                    None,
                    DataSourceSchemaColumn(
                        data_type=QuestionDataType.NUMBER,
                        presentation_options=QuestionPresentationOptions(),
                        data_options=QuestionDataOptions(number_type=NumberTypeEnum.DECIMAL, max_decimal_places=2),
                        original_column_name="col",
                    ),
                ),
                (
                    None,
                    DataSourceSchemaColumn(
                        data_type=QuestionDataType.NUMBER,
                        presentation_options=QuestionPresentationOptions(prefix="$"),
                        data_options=QuestionDataOptions(number_type=NumberTypeEnum.DECIMAL, max_decimal_places=2),
                        original_column_name="col",
                    ),
                ),
                (
                    None,
                    DataSourceSchemaColumn(
                        data_type=QuestionDataType.NUMBER,
                        presentation_options=QuestionPresentationOptions(prefix="£"),
                        data_options=QuestionDataOptions(number_type=NumberTypeEnum.DECIMAL, max_decimal_places=3),
                        original_column_name="col",
                    ),
                ),
            ],
        )
        def test_is_british_pounds_false(self, column_type, schema_column):
            assert DataSetColumnMapping._is_british_pounds(column_type, schema_column) is False

        @pytest.mark.parametrize(
            "column_type, schema_column",
            [
                ("BRITISH_POUNDS", None),
                (
                    None,
                    DataSourceSchemaColumn(
                        data_type=QuestionDataType.NUMBER,
                        presentation_options=QuestionPresentationOptions(prefix="£"),
                        data_options=QuestionDataOptions(number_type=NumberTypeEnum.DECIMAL, max_decimal_places=2),
                        original_column_name="col",
                    ),
                ),
            ],
        )
        def test_is_british_pounds_true(self, column_type, schema_column):
            assert DataSetColumnMapping._is_british_pounds(column_type, schema_column) is True
