from app import QuestionDataType
from app.common.data.types import ExpressionType, ManagedExpressionsEnum
from app.deliver_grant_funding.session_models import (
    AddConditionDependsOnSessionModel,
    AddContextToComponentGuidanceSessionModel,
    AddContextToComponentSessionModel,
    AddContextToExpressionsModel,
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
