import pytest
from psycopg.errors import ForeignKeyViolation
from sqlalchemy.exc import IntegrityError

from app import QuestionDataType
from app.common.data.models import ComponentReference, Expression, Group
from app.common.data.types import ExpressionType, QuestionPresentationOptions, SubmissionModeEnum
from app.common.expressions.managed import GreaterThan, Specifically


class TestSubmissionModel:
    def test_test_submission_property_only_includes_test_submissions(self, factories):
        # what a test name
        collection = factories.collection.create()
        test_submission = factories.submission.create(collection=collection, mode=SubmissionModeEnum.TEST)
        live_submission = factories.submission.create(collection=collection, mode=SubmissionModeEnum.LIVE)

        assert collection.test_submissions == [test_submission]
        assert collection.live_submissions == [live_submission]


class TestQuestionModel:
    def test_question_property_selects_expressions(self, factories):
        question = factories.question.create()
        condition_expression = factories.expression.create(
            question=question, type_=ExpressionType.CONDITION, statement=""
        )
        validation_expression = factories.expression.create(
            question=question, type_=ExpressionType.VALIDATION, statement=""
        )
        assert question.conditions == [condition_expression]
        assert question.validations == [validation_expression]

    def test_question_gets_a_valid_expression_that_belongs_to_it(self, factories):
        question = factories.question.create()
        expression = factories.expression.create(question=question, type_=ExpressionType.CONDITION, statement="")
        assert question.get_expression(expression.id) == expression

    def test_question_does_not_get_a_valid_expression_that_does_not_belong_to_it(self, factories):
        question = factories.question.create()
        expression_on_other_question = factories.expression.create(type_=ExpressionType.CONDITION, statement="")

        with pytest.raises(ValueError) as e:
            question.get_expression(expression_on_other_question.id)

        assert (
            str(e.value)
            == f"Could not find an expression with id={expression_on_other_question.id} in question={question.id}"
        )

    def test_data_source_items(self, factories):
        factories.data_source_item.reset_sequence()
        question = factories.question.create(
            data_type=QuestionDataType.RADIOS,
            presentation_options=QuestionPresentationOptions(last_data_source_item_is_distinct_from_others=False),
        )
        other_question = factories.question.create(data_type=QuestionDataType.TEXT_MULTI_LINE)

        assert question.data_source_items == "Option 0\nOption 1\nOption 2"
        assert other_question.data_source_items is None

        assert question.separate_option_if_no_items_match is False
        assert other_question.separate_option_if_no_items_match is None
        assert question.none_of_the_above_item_text == "Other"
        assert other_question.none_of_the_above_item_text is None

    def test_data_source_items_last_item_is_distinct(self, factories):
        factories.data_source_item.reset_sequence()
        question = factories.question.create(
            data_type=QuestionDataType.RADIOS,
            presentation_options=QuestionPresentationOptions(last_data_source_item_is_distinct_from_others=True),
        )
        assert question.data_source_items == "Option 0\nOption 1"
        assert question.separate_option_if_no_items_match is True
        assert question.none_of_the_above_item_text == "Option 2"


class TestFormModel:
    def test_questions_property_filters_nested_questions(self, factories):
        form = factories.form.create()
        # asserting to a depth of 2
        question1 = factories.question.create(form=form, order=0)
        question2 = factories.question.create(form=form, order=1)
        group = factories.group.create(form=form, order=2)
        question3 = factories.question.create(form_id=form.id, parent=group, order=0)
        sub_group = factories.group.create(form_id=form.id, parent=group, order=1)
        question4 = factories.question.create(form_id=form.id, parent=sub_group, order=0)

        assert form.cached_questions == [question1, question2, question3, question4]


class TestGroupModel:
    def test_questions_property_filters_nested_questions(self, factories):
        form = factories.form.create()
        _question1 = factories.question.create(form=form, order=0)
        group = factories.group.create(form_id=form.id, order=1)
        question2 = factories.question.create(form_id=group.form_id, parent=group, order=0)
        question3 = factories.question.create(form_id=group.form_id, parent=group, order=1)
        sub_group = factories.group.create(form_id=group.form_id, parent=group, order=2)
        question4 = factories.question.create(form_id=group.form_id, parent=sub_group, order=0)

        assert group.cached_questions == [question2, question3, question4]
        assert sub_group.cached_questions == [question4]

    @pytest.mark.parametrize("show_questions_on_the_same_page", [True, False])
    def test_same_page_property(self, factories, show_questions_on_the_same_page):
        form = factories.form.create()
        group = factories.group.create(
            form_id=form.id,
            presentation_options=QuestionPresentationOptions(
                show_questions_on_the_same_page=show_questions_on_the_same_page
            ),
        )

        assert group.same_page is show_questions_on_the_same_page

    def test_max_levels_of_nesting_not_changed(self, app):
        assert app.config["MAX_NESTED_GROUP_LEVELS"] == 1, (
            "If changing the max level of nested groups, ensure you add tests to that level of nesting"
        )

    def test_count_nested_group_levels(self, factories):
        top_group = factories.group.create()
        middle_group = factories.group.create(parent=top_group)
        bottom_group = factories.group.create(parent=middle_group)

        assert Group._count_nested_group_levels(group=top_group) == 0
        assert Group._count_nested_group_levels(group=middle_group) == 1
        assert Group._count_nested_group_levels(group=bottom_group) == 2

    def test_contains_add_another_components(self, factories):
        g1 = factories.group.create()
        g2 = factories.group.create()
        g3 = factories.group.create()
        g4 = factories.group.create(parent=g3, add_another=True)
        factories.question.create(parent=g1, add_another=True)
        assert g1.contains_add_another_components is True
        assert g2.contains_add_another_components is False
        assert g3.contains_add_another_components is True
        assert g4.contains_add_another_components is False


class TestComponentReferenceModel:
    def test_deleting_a_component_with_a_reference_is_blocked(self, factories, db_session):
        q1 = factories.question.create()
        factories.question.create(form=q1.form, text=f"Reference to (({q1.safe_qid}))")

        with pytest.raises(IntegrityError) as e:
            db_session.delete(q1)
            db_session.commit()

        assert isinstance(e.value.__cause__, ForeignKeyViolation)
        assert 'update or delete on table "component" violates foreign key constraint' in str(e.value.__cause__)

    def test_deleting_a_component_holding_a_reference_is_allowed(self, factories, db_session):
        q1 = factories.question.create()
        q2 = factories.question.create(form=q1.form, text=f"Reference to (({q1.safe_qid}))")

        db_session.delete(q2)
        db_session.commit()

        assert db_session.query(ComponentReference).count() == 0

    def test_deleting_a_component_with_an_expression_reference_is_blocked(self, factories, db_session):
        user = factories.user.create()
        q1 = factories.question.create()
        factories.question.create(
            form=q1.form,
            expressions=[Expression.from_managed(GreaterThan(question_id=q1.id, minimum_value=3000), user)],
        )

        with pytest.raises(IntegrityError) as e:
            db_session.delete(q1)
            db_session.commit()

        assert isinstance(e.value.__cause__, ForeignKeyViolation)
        assert 'update or delete on table "component" violates foreign key constraint' in str(e.value.__cause__)

    def test_deleting_an_expression_holding_a_reference_is_allowed(self, factories, db_session):
        user = factories.user.create()
        q1 = factories.question.create()
        q2 = factories.question.create(
            form=q1.form,
            expressions=[Expression.from_managed(GreaterThan(question_id=q1.id, minimum_value=3000), user)],
        )

        db_session.delete(q2.expressions[0])
        db_session.commit()

        assert db_session.query(ComponentReference).count() == 0

    def test_deleting_a_data_source_item_with_an_expression_reference_is_blocked(self, factories, db_session):
        user = factories.user.create()
        q1 = factories.question.create(data_type=QuestionDataType.RADIOS)
        factories.question.create(
            form=q1.form,
            expressions=[
                Expression.from_managed(
                    Specifically(
                        question_id=q1.id,
                        item={
                            "key": q1.data_source.items[0].key,
                            "label": q1.data_source.items[0].label,
                        },
                    ),
                    created_by=user,
                ),
            ],
        )

        with pytest.raises(IntegrityError) as e:
            db_session.delete(q1.data_source.items[0])
            db_session.commit()

        assert isinstance(e.value.__cause__, ForeignKeyViolation)
        assert 'update or delete on table "data_source_item" violates foreign key constraint' in str(e.value.__cause__)

    def test_deleting_an_expression_holding_a_data_source_item_reference_is_allowed(self, factories, db_session):
        user = factories.user.create()
        q1 = factories.question.create(data_type=QuestionDataType.RADIOS)
        q2 = factories.question.create(
            form=q1.form,
            expressions=[
                Expression.from_managed(
                    Specifically(
                        question_id=q1.id,
                        item={
                            "key": q1.data_source.items[0].key,
                            "label": q1.data_source.items[0].label,
                        },
                    ),
                    created_by=user,
                ),
            ],
        )

        db_session.delete(q2.expressions[0])
        db_session.commit()

        assert db_session.query(ComponentReference).count() == 0
