import pytest
from psycopg.errors import ForeignKeyViolation
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlalchemy.orm import joinedload

from app import QuestionDataType
from app.common.data.models import ComponentReference, Expression, GrantRecipient, Group
from app.common.data.types import ExpressionType, QuestionPresentationOptions, RoleEnum, SubmissionModeEnum
from app.common.expressions.managed import GreaterThan, Specifically


class TestSubmissionModel:
    def test_test_submission_property_only_includes_test_submissions(self, factories):
        # what a test name
        collection = factories.collection.create()
        test_submission = factories.submission.create(collection=collection, mode=SubmissionModeEnum.TEST)
        live_submission = factories.submission.create(collection=collection, mode=SubmissionModeEnum.LIVE)

        assert collection.test_submissions == [test_submission]
        assert collection.live_submissions == [live_submission]

    def test_test_submissions_can_be_created_without_grant_recipient(self, factories):
        collection = factories.collection.create()
        test_submission = factories.submission.create(
            collection=collection, mode=SubmissionModeEnum.TEST, grant_recipient=None
        )

        assert test_submission.grant_recipient_id is None
        assert test_submission.grant_recipient is None

    def test_live_submissions_cannot_be_created_without_grant_recipient(self, factories, db_session):
        from sqlalchemy.exc import IntegrityError

        from app.common.data.models import Submission

        collection = factories.collection.create()
        user = factories.user.create()

        submission = Submission(
            collection_id=collection.id,
            mode=SubmissionModeEnum.LIVE,
            created_by_id=user.id,
            grant_recipient_id=None,
            data={},
        )
        db_session.add(submission)

        with pytest.raises(IntegrityError, match="ck_grant_recipient_if_live"):
            db_session.flush()

    def test_live_submissions_can_be_created_with_grant_recipient(self, factories):
        collection = factories.collection.create()
        grant_recipient = factories.grant_recipient.create()
        live_submission = factories.submission.create(
            collection=collection, mode=SubmissionModeEnum.LIVE, grant_recipient=grant_recipient
        )

        assert live_submission.grant_recipient_id == grant_recipient.id
        assert live_submission.grant_recipient == grant_recipient

    def test_grant_recipient_submissions_relationship(self, factories):
        collection = factories.collection.create()
        grant_recipient = factories.grant_recipient.create()
        live_submission_1 = factories.submission.create(
            collection=collection, mode=SubmissionModeEnum.LIVE, grant_recipient=grant_recipient
        )
        live_submission_2 = factories.submission.create(
            collection=collection, mode=SubmissionModeEnum.LIVE, grant_recipient=grant_recipient
        )
        test_submission = factories.submission.create(
            collection=collection, mode=SubmissionModeEnum.TEST, grant_recipient=None
        )

        assert set(grant_recipient.submissions) == {live_submission_1, live_submission_2}
        assert test_submission not in grant_recipient.submissions


class TestGrantModel:
    def test_grant_recipients_relationship(self, factories):
        grant = factories.grant.create()
        grant_recipient_1 = factories.grant_recipient.create(grant=grant)
        grant_recipient_2 = factories.grant_recipient.create(grant=grant)
        other_grant = factories.grant.create()
        other_grant_recipient = factories.grant_recipient.create(grant=other_grant)

        assert set(grant.grant_recipients) == {grant_recipient_1, grant_recipient_2}
        assert other_grant_recipient not in grant.grant_recipients


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

    def test_add_another_summary_questions_none_selected(self, factories):
        top_group = factories.group.create(add_another=True)
        q1 = factories.question.create(parent=top_group)
        sub_group = factories.group.create(parent=top_group)
        q2 = factories.question.create(parent=sub_group)
        factories.question.create(form=q1.form, order=0)

        result = top_group.questions_in_add_another_summary
        assert result == [q1, q2]

    def test_add_another_summary_questions_some_selected(self, factories):
        top_group = factories.group.create(add_another=True)
        q1 = factories.question.create(parent=top_group)
        sub_group = factories.group.create(parent=top_group)
        q2 = factories.question.create(parent=sub_group)
        _ = factories.question.create(parent=sub_group)
        q4 = factories.question.create(parent=top_group)
        factories.question.create(form=q1.form, order=0)
        top_group.presentation_options = QuestionPresentationOptions(
            add_another_summary_line_question_ids=[q1.id, q2.id, q4.id]
        )

        result = top_group.questions_in_add_another_summary
        assert result == [q1, q2, q4]

    def test_add_another_summary_questions_group_is_not_add_another(self, factories):
        top_group = factories.group.create(add_another=False)
        q1 = factories.question.create(parent=top_group)
        sub_group = factories.group.create(parent=top_group)
        q2 = factories.question.create(parent=sub_group)
        _ = factories.question.create(parent=sub_group)
        q4 = factories.question.create(parent=top_group)
        factories.question.create(form=q1.form, order=0)
        top_group.presentation_options = QuestionPresentationOptions(
            add_another_summary_line_question_ids=[q1.id, q2.id, q4.id]
        )

        result = top_group.questions_in_add_another_summary
        assert result == []


class TestGrantRecipientModel:
    select_with_certifiers = select(GrantRecipient).options(joinedload(GrantRecipient._all_certifiers))
    select_with_data_providers = select(GrantRecipient).options(joinedload(GrantRecipient.data_providers))

    def test_certifiers_property_raises_by_default(self, factories):
        grant_recipient = factories.grant_recipient.create()

        with pytest.raises(InvalidRequestError):
            _ = grant_recipient.certifiers

    def test_certifiers_returns_empty_list_when_no_certifiers(self, factories, db_session):
        factories.grant_recipient.create()
        from_db = db_session.scalar(self.select_with_certifiers)

        assert from_db.certifiers == []

    def test_certifiers_returns_global_certifiers_only(self, factories, db_session):
        grant_recipient = factories.grant_recipient.create()
        user = factories.user.create()
        factories.user_role.create(
            user=user, organisation=grant_recipient.organisation, grant=None, permissions=[RoleEnum.CERTIFIER]
        )

        from_db = db_session.scalar(self.select_with_certifiers)

        assert len(from_db.certifiers) == 1
        assert from_db.certifiers[0].id == user.id

    def test_certifiers_returns_grant_specific_certifiers_only(self, factories, db_session):
        grant_recipient = factories.grant_recipient.create()
        user = factories.user.create()
        factories.user_role.create(
            user=user,
            organisation=grant_recipient.organisation,
            grant=grant_recipient.grant,
            permissions=[RoleEnum.CERTIFIER],
        )
        from_db = db_session.scalar(self.select_with_certifiers)

        assert len(from_db.certifiers) == 1
        assert from_db.certifiers[0].id == user.id

    def test_certifiers_prefers_grant_specific_over_global(self, factories, db_session):
        grant_recipient = factories.grant_recipient.create()
        global_certifier = factories.user.create()
        grant_specific_certifier = factories.user.create()

        factories.user_role.create(
            user=global_certifier,
            organisation=grant_recipient.organisation,
            grant=None,
            permissions=[RoleEnum.CERTIFIER],
        )
        factories.user_role.create(
            user=grant_specific_certifier,
            organisation=grant_recipient.organisation,
            grant=grant_recipient.grant,
            permissions=[RoleEnum.CERTIFIER],
        )
        from_db = db_session.scalar(self.select_with_certifiers)

        assert len(from_db.certifiers) == 1
        assert from_db.certifiers[0].id == grant_specific_certifier.id

    def test_certifiers_returns_all_global_certifiers_when_no_grant_specific(self, factories, db_session):
        grant_recipient = factories.grant_recipient.create()
        user1 = factories.user.create()
        user2 = factories.user.create()
        user3 = factories.user.create()

        factories.user_role.create(
            user=user1, organisation=grant_recipient.organisation, grant=None, permissions=[RoleEnum.CERTIFIER]
        )
        factories.user_role.create(
            user=user2, organisation=grant_recipient.organisation, grant=None, permissions=[RoleEnum.CERTIFIER]
        )
        factories.user_role.create(
            user=user3, organisation=grant_recipient.organisation, grant=None, permissions=[RoleEnum.CERTIFIER]
        )
        from_db = db_session.scalar(self.select_with_certifiers)

        assert len(from_db.certifiers) == 3
        assert {u.id for u in (from_db.certifiers)} == {user1.id, user2.id, user3.id}

    def test_certifiers_returns_all_grant_specific_certifiers(self, factories, db_session):
        grant_recipient = factories.grant_recipient.create()
        user1 = factories.user.create()
        user2 = factories.user.create()

        factories.user_role.create(
            user=user1,
            organisation=grant_recipient.organisation,
            grant=grant_recipient.grant,
            permissions=[RoleEnum.CERTIFIER],
        )
        factories.user_role.create(
            user=user2,
            organisation=grant_recipient.organisation,
            grant=grant_recipient.grant,
            permissions=[RoleEnum.CERTIFIER],
        )
        from_db = db_session.scalar(self.select_with_certifiers)

        assert len(from_db.certifiers) == 2
        assert {u.id for u in (from_db.certifiers)} == {user1.id, user2.id}

    def test_certifiers_excludes_certifiers_from_different_organisation(self, factories, db_session):
        factories.grant_recipient.create()
        other_org = factories.organisation.create()
        other_org_certifier = factories.user.create()

        factories.user_role.create(
            user=other_org_certifier, organisation=other_org, grant=None, permissions=[RoleEnum.CERTIFIER]
        )
        from_db = db_session.scalar(self.select_with_certifiers)

        assert len(from_db.certifiers) == 0

    def test_certifiers_excludes_certifiers_from_different_grant(self, factories, db_session):
        grant_recipient = factories.grant_recipient.create()
        other_grant = factories.grant.create()
        other_grant_certifier = factories.user.create()

        factories.user_role.create(
            user=other_grant_certifier,
            organisation=grant_recipient.organisation,
            grant=other_grant,
            permissions=[RoleEnum.CERTIFIER],
        )
        from_db = db_session.scalar(self.select_with_certifiers)

        assert len(from_db.certifiers) == 0

    def test_certifiers_excludes_non_certifier_roles(self, factories, db_session):
        grant_recipient = factories.grant_recipient.create()
        member_user = factories.user.create()
        admin_user = factories.user.create()

        factories.user_role.create(
            user=member_user,
            organisation=grant_recipient.organisation,
            grant=grant_recipient.grant,
            permissions=[RoleEnum.MEMBER],
        )
        factories.user_role.create(
            user=admin_user, organisation=grant_recipient.organisation, grant=None, permissions=[RoleEnum.ADMIN]
        )
        from_db = db_session.scalar(self.select_with_certifiers)

        assert len(from_db.certifiers) == 0

    def test_certifiers_with_multiple_permissions_including_certifier(self, factories, db_session):
        grant_recipient = factories.grant_recipient.create()
        user = factories.user.create()

        factories.user_role.create(
            user=user,
            organisation=grant_recipient.organisation,
            grant=grant_recipient.grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.CERTIFIER],
        )
        from_db = db_session.scalar(self.select_with_certifiers)

        assert len(from_db.certifiers) == 1
        assert from_db.certifiers[0].id == user.id

    def test_certifiers_user_with_both_global_and_grant_specific_roles(self, factories, db_session):
        grant_recipient = factories.grant_recipient.create()
        user = factories.user.create()

        factories.user_role.create(
            user=user, organisation=grant_recipient.organisation, grant=None, permissions=[RoleEnum.CERTIFIER]
        )
        factories.user_role.create(
            user=user,
            organisation=grant_recipient.organisation,
            grant=grant_recipient.grant,
            permissions=[RoleEnum.CERTIFIER],
        )
        from_db = db_session.scalar(self.select_with_certifiers)

        assert len(from_db.certifiers) == 1
        assert from_db.certifiers[0].id == user.id

    def test_data_providers_returns_empty_list_when_no_data_providers(self, factories, db_session):
        factories.grant_recipient.create()
        from_db = db_session.scalar(self.select_with_data_providers)

        assert from_db.data_providers == []

    def test_data_providers_returns_global_data_providers_only(self, factories, db_session):
        grant_recipient = factories.grant_recipient.create()
        user = factories.user.create()
        factories.user_role.create(
            user=user, organisation=grant_recipient.organisation, grant=None, permissions=[RoleEnum.DATA_PROVIDER]
        )
        from_db = db_session.scalar(self.select_with_data_providers)

        assert len(from_db.data_providers) == 1
        assert from_db.data_providers[0].id == user.id

    def test_data_providers_returns_grant_specific_data_providers_only(self, factories, db_session):
        grant_recipient = factories.grant_recipient.create()
        user = factories.user.create()
        factories.user_role.create(
            user=user,
            organisation=grant_recipient.organisation,
            grant=grant_recipient.grant,
            permissions=[RoleEnum.DATA_PROVIDER],
        )
        from_db = db_session.scalar(self.select_with_data_providers)

        assert len(from_db.data_providers) == 1
        assert from_db.data_providers[0].id == user.id

    def test_data_providers_returns_both_global_and_grant_specific(self, factories, db_session):
        grant_recipient = factories.grant_recipient.create()
        global_data_provider = factories.user.create()
        grant_specific_data_provider = factories.user.create()

        factories.user_role.create(
            user=global_data_provider,
            organisation=grant_recipient.organisation,
            grant=None,
            permissions=[RoleEnum.DATA_PROVIDER],
        )
        factories.user_role.create(
            user=grant_specific_data_provider,
            organisation=grant_recipient.organisation,
            grant=grant_recipient.grant,
            permissions=[RoleEnum.DATA_PROVIDER],
        )
        from_db = db_session.scalar(self.select_with_data_providers)

        assert len(from_db.data_providers) == 2
        assert {u.id for u in (from_db.data_providers)} == {
            global_data_provider.id,
            grant_specific_data_provider.id,
        }

    def test_data_providers_returns_all_global_data_providers(self, factories, db_session):
        grant_recipient = factories.grant_recipient.create()
        user1 = factories.user.create()
        user2 = factories.user.create()
        user3 = factories.user.create()

        factories.user_role.create(
            user=user1, organisation=grant_recipient.organisation, grant=None, permissions=[RoleEnum.DATA_PROVIDER]
        )
        factories.user_role.create(
            user=user2, organisation=grant_recipient.organisation, grant=None, permissions=[RoleEnum.DATA_PROVIDER]
        )
        factories.user_role.create(
            user=user3, organisation=grant_recipient.organisation, grant=None, permissions=[RoleEnum.DATA_PROVIDER]
        )
        from_db = db_session.scalar(self.select_with_data_providers)

        assert len(from_db.data_providers) == 3
        assert {u.id for u in (from_db.data_providers)} == {user1.id, user2.id, user3.id}

    def test_data_providers_returns_all_grant_specific_data_providers(self, factories, db_session):
        grant_recipient = factories.grant_recipient.create()
        user1 = factories.user.create()
        user2 = factories.user.create()

        factories.user_role.create(
            user=user1,
            organisation=grant_recipient.organisation,
            grant=grant_recipient.grant,
            permissions=[RoleEnum.DATA_PROVIDER],
        )
        factories.user_role.create(
            user=user2,
            organisation=grant_recipient.organisation,
            grant=grant_recipient.grant,
            permissions=[RoleEnum.DATA_PROVIDER],
        )
        from_db = db_session.scalar(self.select_with_data_providers)

        assert len(from_db.data_providers) == 2
        assert {u.id for u in (from_db.data_providers)} == {user1.id, user2.id}

    def test_data_providers_excludes_data_providers_from_different_organisation(self, factories, db_session):
        factories.grant_recipient.create()
        other_org = factories.organisation.create()
        other_org_data_provider = factories.user.create()

        factories.user_role.create(
            user=other_org_data_provider, organisation=other_org, grant=None, permissions=[RoleEnum.DATA_PROVIDER]
        )
        from_db = db_session.scalar(self.select_with_data_providers)

        assert len(from_db.data_providers) == 0

    def test_data_providers_excludes_data_providers_from_different_grant(self, factories, db_session):
        grant_recipient = factories.grant_recipient.create()
        other_grant = factories.grant.create()
        other_grant_data_provider = factories.user.create()

        factories.user_role.create(
            user=other_grant_data_provider,
            organisation=grant_recipient.organisation,
            grant=other_grant,
            permissions=[RoleEnum.DATA_PROVIDER],
        )
        from_db = db_session.scalar(self.select_with_data_providers)

        assert len(from_db.data_providers) == 0

    def test_data_providers_excludes_non_data_provider_roles(self, factories, db_session):
        grant_recipient = factories.grant_recipient.create()
        member_user = factories.user.create()
        admin_user = factories.user.create()

        factories.user_role.create(
            user=member_user,
            organisation=grant_recipient.organisation,
            grant=grant_recipient.grant,
            permissions=[RoleEnum.MEMBER],
        )
        factories.user_role.create(
            user=admin_user, organisation=grant_recipient.organisation, grant=None, permissions=[RoleEnum.CERTIFIER]
        )
        from_db = db_session.scalar(self.select_with_data_providers)

        assert len(from_db.data_providers) == 0

    def test_data_providers_with_multiple_permissions_including_data_provider(self, factories, db_session):
        grant_recipient = factories.grant_recipient.create()
        user = factories.user.create()

        factories.user_role.create(
            user=user,
            organisation=grant_recipient.organisation,
            grant=grant_recipient.grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )
        from_db = db_session.scalar(self.select_with_data_providers)

        assert len(from_db.data_providers) == 1
        assert from_db.data_providers[0].id == user.id

    def test_data_providers_user_with_both_global_and_grant_specific_roles(self, factories, db_session):
        grant_recipient = factories.grant_recipient.create()
        user = factories.user.create()

        factories.user_role.create(
            user=user, organisation=grant_recipient.organisation, grant=None, permissions=[RoleEnum.DATA_PROVIDER]
        )
        factories.user_role.create(
            user=user,
            organisation=grant_recipient.organisation,
            grant=grant_recipient.grant,
            permissions=[RoleEnum.DATA_PROVIDER],
        )
        from_db = db_session.scalar(self.select_with_data_providers)

        assert len(from_db.data_providers) == 1
        assert from_db.data_providers[0].id == user.id


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
