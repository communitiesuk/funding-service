from unittest.mock import patch

import pytest

from app.common.data.interfaces.collections import copy_collection
from app.common.data.models import (
    Collection,
    Component,
    ComponentReference,
    DataSource,
    DataSourceItem,
    Expression,
    Form,
)
from app.common.data.types import (
    CollectionStatusEnum,
    DataSourceType,
    ExpressionType,
    GrantRecipientModeEnum,
    QuestionDataType,
    SubmissionModeEnum,
)
from app.common.expressions.custom import CustomExpression
from app.common.expressions.managed import GreaterThan
from app.common.expressions.references import ExpressionReference
from app.extensions import db


@pytest.fixture()
def source_collection(factories):
    grant = factories.grant.create()
    user = factories.user.create()
    collection = factories.collection.create(grant=grant, name="Source Collection")

    form = factories.form.create(collection=collection, title="Section One")
    q1 = factories.question.create(
        form=form,
        name="How many staff",
        data_type=QuestionDataType.NUMBER,
        text="How many staff do you employ?",
    )
    q1_ref = ExpressionReference.from_question(q1)
    factories.question.create(
        form=form,
        name="Staff detail",
        data_type=QuestionDataType.TEXT_SINGLE_LINE,
        text=f"Tell us about {q1_ref.wrapped}",
        hint=f"Reference hint {q1_ref.wrapped}",
        expressions=[
            Expression.from_evaluatable_expression(
                GreaterThan(subject_reference=ExpressionReference.from_question(q1), minimum_value=5),
                ExpressionType.CONDITION,
                user,
            )
        ],
    )

    factories.question.create(
        form=form,
        name="Favourite colour",
        data_type=QuestionDataType.RADIOS,
    )

    group = factories.group.create(
        form=form,
        name="Staff group",
        add_another=True,
        add_another_guidance_body=f"Add another entry referencing {q1_ref.wrapped}",
    )
    factories.question.create(
        form=form,
        parent=group,
        name="Group child question",
        data_type=QuestionDataType.TEXT_SINGLE_LINE,
        text="A child question",
    )

    grant_recipient = factories.grant_recipient.create(grant=grant)
    grant_recipient = factories.grant_recipient.create(
        grant=grant, organisation=grant_recipient.organisation, mode=GrantRecipientModeEnum.TEST
    )
    gr_data_source = factories.data_source.create(
        type=DataSourceType.GRANT_RECIPIENT,
        collection=collection,
        grant=grant,
    )
    factories.data_source_organisation_item.create(
        data_source=gr_data_source,
        external_id=grant_recipient.organisation.external_id,
        _data={"c_allocation": 100},
    )
    factories.data_source_organisation_item.create(
        data_source=gr_data_source, external_id="other-org", _data={"c_allocation": 200}
    )

    ds_ref = ExpressionReference.from_data_source_column(gr_data_source, "c_allocation")
    factories.question.create(
        form=form,
        name="Allocation display",
        data_type=QuestionDataType.NUMBER,
        text=f"Your allocation is {ds_ref.wrapped}",
        expressions=[
            Expression.from_evaluatable_expression(
                CustomExpression(
                    custom_expression=f"(({q1_ref.unwrapped})) <= (({ds_ref.unwrapped}))",
                    custom_message=f"Must not exceed {ds_ref.wrapped}",
                ),
                ExpressionType.VALIDATION,
                user,
            )
        ],
    )

    q3 = factories.question.create(
        form=form,
        name="Budget amount",
        data_type=QuestionDataType.NUMBER,
        text="What is your budget?",
    )
    factories.question.create(
        form=form,
        name="Spend amount",
        data_type=QuestionDataType.NUMBER,
        text="How much did you spend?",
        expressions=[
            Expression.from_evaluatable_expression(
                GreaterThan(
                    subject_reference=ExpressionReference.from_question(q3),
                    minimum_value=None,
                    minimum_expression=ExpressionReference.from_question(q1),
                ),
                ExpressionType.VALIDATION,
                user,
            )
        ],
    )

    factories.submission.create(collection=collection, mode=SubmissionModeEnum.TEST, grant_recipient=grant_recipient)

    return collection


@pytest.fixture()
def copy_user(factories):
    return factories.user.create()


@pytest.fixture()
def target_grant(factories):
    grant = factories.grant.create()
    grs = factories.grant_recipient.create_batch(2, grant=grant)

    for gr in grs:
        factories.grant_recipient.create_batch(
            2, grant=grant, organisation=gr.organisation, mode=SubmissionModeEnum.TEST
        )
    return grant


@pytest.fixture()
def copied(source_collection, copy_user, target_grant):
    with patch("app.deliver_grant_funding.data_sets.s3_service"):
        result = copy_collection(
            source_collection,
            name="Copied Collection",
            user=copy_user,
            grant=target_grant,
        )
        db.session.flush()
        return result


class TestCopyCollectionCollection:
    def test_creates_new_collection_with_new_id(self, db_session, source_collection, copied):
        assert copied.id != source_collection.id
        assert db_session.get(Collection, copied.id) is not None

    def test_assigns_given_name(self, db_session, source_collection, copied):
        assert copied.name == "Copied Collection"

    def test_assigns_to_target_grant(self, db_session, source_collection, copied, target_grant):
        assert copied.grant_id == target_grant.id

    def test_assigns_user_as_created_by(self, db_session, source_collection, copied, copy_user):
        assert copied.created_by_id == copy_user.id

    def test_starts_in_draft_status(self, db_session, source_collection, copied):
        assert copied.status == CollectionStatusEnum.DRAFT

    def test_nulls_date_fields(self, db_session, factories, copy_user, target_grant):
        import datetime

        source = factories.collection.create(
            reporting_period_start_date=datetime.date(2024, 1, 1),
            reporting_period_end_date=datetime.date(2024, 3, 31),
            submission_period_start_date=datetime.date(2024, 2, 1),
            submission_period_end_date=datetime.date(2024, 4, 30),
        )
        with patch("app.deliver_grant_funding.data_sets.s3_service"):
            result = copy_collection(source, name="Date Test", user=copy_user, grant=target_grant)
            db.session.flush()
        assert result.reporting_period_start_date is None
        assert result.reporting_period_end_date is None
        assert result.submission_period_start_date is None
        assert result.submission_period_end_date is None

    def test_original_collection_unchanged(self, db_session, source_collection, copied):
        original = db_session.get(Collection, source_collection.id)
        assert original.name == "Source Collection"
        assert original.grant_id == source_collection.grant_id

    def test_does_not_copy_other_collections_in_grant(self, db_session, factories, source_collection, copied):
        other_collection = factories.collection.create(grant=source_collection.grant, name="Other Collection")
        target_grant_collections = [c for c in copied.grant.collections]
        assert other_collection not in target_grant_collections


class TestCopyCollectionForms:
    def test_copies_forms_with_new_ids(self, db_session, source_collection, copied):
        source_form_ids = {f.id for f in source_collection.forms}
        copied_form_ids = {f.id for f in copied.forms}
        assert len(copied.forms) == len(source_collection.forms)
        assert copied_form_ids.isdisjoint(source_form_ids)

    def test_preserves_form_titles(self, db_session, source_collection, copied):
        source_titles = [f.title for f in source_collection.forms]
        copied_titles = [f.title for f in copied.forms]
        assert copied_titles == source_titles

    def test_forms_belong_to_new_collection(self, db_session, copied):
        for form in copied.forms:
            assert form.collection_id == copied.id

    def test_original_forms_unchanged(self, db_session, source_collection, copied):
        for form in source_collection.forms:
            from_db = db_session.get(Form, form.id)
            assert from_db.collection_id == source_collection.id


class TestCopyCollectionComponents:
    def test_copies_components_with_new_ids(self, db_session, source_collection, copied):
        source_components = source_collection.forms[0]._all_components
        copied_components = copied.forms[0]._all_components
        source_ids = {c.id for c in source_components}
        copied_ids = {c.id for c in copied_components}
        assert len(copied_components) == len(source_components)
        assert copied_ids.isdisjoint(source_ids)

    def test_preserves_component_attributes(self, db_session, source_collection, copied):
        source_q = next(c for c in source_collection.forms[0]._all_components if c.name == "How many staff")
        copied_q = next(c for c in copied.forms[0]._all_components if c.name == "How many staff")
        assert copied_q.data_type == source_q.data_type
        assert copied_q.name == source_q.name

    def test_components_belong_to_new_form(self, db_session, copied):
        copied_form = copied.forms[0]
        for component in copied_form._all_components:
            assert component.form_id == copied_form.id

    def test_original_components_unchanged(self, db_session, source_collection, copied):
        source_form = source_collection.forms[0]
        for component in source_form._all_components:
            from_db = db_session.get(Component, component.id)
            assert from_db.form_id == source_form.id


class TestCopyCollectionExpressions:
    def test_copies_expressions_with_new_ids(self, db_session, source_collection, copied):
        source_exprs = [e for f in source_collection.forms for c in f._all_components for e in c.expressions]
        copied_exprs = [e for f in copied.forms for c in f._all_components for e in c.expressions]
        assert len(copied_exprs) == len(source_exprs)
        assert {e.id for e in copied_exprs}.isdisjoint({e.id for e in source_exprs})

    def test_expression_statement_references_rewritten_to_new_ids(self, db_session, source_collection, copied):
        source_q1 = next(c for c in source_collection.forms[0]._all_components if c.name == "How many staff")
        copied_q1 = next(c for c in copied.forms[0]._all_components if c.name == "How many staff")
        copied_q2 = next(c for c in copied.forms[0]._all_components if c.name == "Staff detail")

        source_ref = ExpressionReference.from_question(source_q1)
        copied_ref = ExpressionReference.from_question(copied_q1)
        expr = copied_q2.expressions[0]
        assert copied_ref.unwrapped in expr.statement
        assert source_ref.unwrapped not in expr.statement

    def test_expression_context_references_rewritten_to_new_ids(self, db_session, source_collection, copied):
        source_q1 = next(c for c in source_collection.forms[0]._all_components if c.name == "How many staff")
        copied_q1 = next(c for c in copied.forms[0]._all_components if c.name == "How many staff")
        copied_q2 = next(c for c in copied.forms[0]._all_components if c.name == "Staff detail")

        source_ref = ExpressionReference.from_question(source_q1)
        copied_ref = ExpressionReference.from_question(copied_q1)
        expr = copied_q2.expressions[0]
        assert copied_ref.unwrapped in str(expr.context)
        assert source_ref.unwrapped not in str(expr.context)

    def test_expression_statement_data_source_references_rewritten(self, db_session, source_collection, copied):
        source_gr_ds = next(ds for ds in source_collection.data_sources if ds.type == DataSourceType.GRANT_RECIPIENT)
        copied_gr_ds = next(ds for ds in copied.data_sources if ds.type == DataSourceType.GRANT_RECIPIENT)
        copied_alloc_q = next(c for c in copied.forms[0]._all_components if c.name == "Allocation display")

        source_ds_ref = ExpressionReference.from_data_source_column(source_gr_ds, "c_allocation")
        copied_ds_ref = ExpressionReference.from_data_source_column(copied_gr_ds, "c_allocation")
        expr = copied_alloc_q.expressions[0]
        assert copied_ds_ref.unwrapped in expr.statement
        assert source_ds_ref.unwrapped not in expr.statement

    def test_expression_context_data_source_references_rewritten(self, db_session, source_collection, copied):
        source_gr_ds = next(ds for ds in source_collection.data_sources if ds.type == DataSourceType.GRANT_RECIPIENT)
        copied_gr_ds = next(ds for ds in copied.data_sources if ds.type == DataSourceType.GRANT_RECIPIENT)
        copied_alloc_q = next(c for c in copied.forms[0]._all_components if c.name == "Allocation display")

        source_ds_ref = ExpressionReference.from_data_source_column(source_gr_ds, "c_allocation")
        copied_ds_ref = ExpressionReference.from_data_source_column(copied_gr_ds, "c_allocation")
        expr = copied_alloc_q.expressions[0]
        assert copied_ds_ref.unwrapped in str(expr.context)
        assert source_ds_ref.unwrapped not in str(expr.context)

    def test_original_expressions_unchanged(self, db_session, source_collection, copied):
        source_q1 = next(c for c in source_collection.forms[0]._all_components if c.name == "How many staff")
        source_q2 = next(c for c in source_collection.forms[0]._all_components if c.name == "Staff detail")
        source_ref = ExpressionReference.from_question(source_q1)
        expr = source_q2.expressions[0]
        assert source_ref.unwrapped in expr.statement

    def test_overrides_created_by(self, db_session, source_collection, copied, copy_user):
        source_exprs = [e for f in source_collection.forms for c in f._all_components for e in c.expressions]
        copied_exprs = [e for f in copied.forms for c in f._all_components for e in c.expressions]
        assert all(e.created_by == copy_user for e in copied_exprs)
        assert all(e.created_by != copy_user for e in source_exprs)


class TestCopyCollectionExpressionContext:
    def test_managed_expression_minimum_expression_rewritten(self, db_session, source_collection, copied):
        source_q1 = next(c for c in source_collection.forms[0]._all_components if c.name == "How many staff")
        copied_q1 = next(c for c in copied.forms[0]._all_components if c.name == "How many staff")
        copied_spend = next(c for c in copied.forms[0]._all_components if c.name == "Spend amount")

        source_ref = ExpressionReference.from_question(source_q1)
        copied_ref = ExpressionReference.from_question(copied_q1)
        expr = copied_spend.expressions[0]
        evaluatable = expr.evaluatable_expression
        assert evaluatable.minimum_expression == copied_ref
        assert evaluatable.minimum_expression != source_ref

    def test_managed_expression_subject_reference_rewritten(self, db_session, source_collection, copied):
        source_q3 = next(c for c in source_collection.forms[0]._all_components if c.name == "Budget amount")
        copied_q3 = next(c for c in copied.forms[0]._all_components if c.name == "Budget amount")
        copied_spend = next(c for c in copied.forms[0]._all_components if c.name == "Spend amount")

        source_ref = ExpressionReference.from_question(source_q3)
        copied_ref = ExpressionReference.from_question(copied_q3)
        expr = copied_spend.expressions[0]
        evaluatable = expr.evaluatable_expression
        assert evaluatable.subject_reference == copied_ref
        assert evaluatable.subject_reference != source_ref

    def test_custom_expression_message_references_rewritten(self, db_session, source_collection, copied):
        source_gr_ds = next(ds for ds in source_collection.data_sources if ds.type == DataSourceType.GRANT_RECIPIENT)
        copied_gr_ds = next(ds for ds in copied.data_sources if ds.type == DataSourceType.GRANT_RECIPIENT)
        copied_alloc_q = next(c for c in copied.forms[0]._all_components if c.name == "Allocation display")

        source_ds_ref = ExpressionReference.from_data_source_column(source_gr_ds, "c_allocation")
        copied_ds_ref = ExpressionReference.from_data_source_column(copied_gr_ds, "c_allocation")
        expr = copied_alloc_q.expressions[0]
        evaluatable = expr.evaluatable_expression
        assert copied_ds_ref.wrapped in evaluatable.message
        assert source_ds_ref.wrapped not in evaluatable.message

    def test_custom_expression_statement_references_rewritten(self, db_session, source_collection, copied):
        source_q1 = next(c for c in source_collection.forms[0]._all_components if c.name == "How many staff")
        copied_q1 = next(c for c in copied.forms[0]._all_components if c.name == "How many staff")
        source_gr_ds = next(ds for ds in source_collection.data_sources if ds.type == DataSourceType.GRANT_RECIPIENT)
        copied_gr_ds = next(ds for ds in copied.data_sources if ds.type == DataSourceType.GRANT_RECIPIENT)
        copied_alloc_q = next(c for c in copied.forms[0]._all_components if c.name == "Allocation display")

        source_q_ref = ExpressionReference.from_question(source_q1)
        copied_q_ref = ExpressionReference.from_question(copied_q1)
        source_ds_ref = ExpressionReference.from_data_source_column(source_gr_ds, "c_allocation")
        copied_ds_ref = ExpressionReference.from_data_source_column(copied_gr_ds, "c_allocation")
        expr = copied_alloc_q.expressions[0]
        evaluatable = expr.evaluatable_expression
        assert copied_q_ref.unwrapped in evaluatable.statement
        assert source_q_ref.unwrapped not in evaluatable.statement
        assert copied_ds_ref.unwrapped in evaluatable.statement
        assert source_ds_ref.unwrapped not in evaluatable.statement


class TestCopyCollectionComponentText:
    def test_question_text_references_rewritten(self, db_session, source_collection, copied):
        source_q1 = next(c for c in source_collection.forms[0]._all_components if c.name == "How many staff")
        copied_q1 = next(c for c in copied.forms[0]._all_components if c.name == "How many staff")
        copied_q2 = next(c for c in copied.forms[0]._all_components if c.name == "Staff detail")

        source_ref = ExpressionReference.from_question(source_q1)
        copied_ref = ExpressionReference.from_question(copied_q1)
        assert copied_ref.unwrapped in copied_q2.text
        assert source_ref.unwrapped not in copied_q2.text

    def test_hint_references_rewritten(self, db_session, source_collection, copied):
        source_q1 = next(c for c in source_collection.forms[0]._all_components if c.name == "How many staff")
        copied_q1 = next(c for c in copied.forms[0]._all_components if c.name == "How many staff")
        copied_q2 = next(c for c in copied.forms[0]._all_components if c.name == "Staff detail")

        source_ref = ExpressionReference.from_question(source_q1)
        copied_ref = ExpressionReference.from_question(copied_q1)
        assert copied_ref.unwrapped in copied_q2.hint
        assert source_ref.unwrapped not in copied_q2.hint

    def test_add_another_guidance_body_references_rewritten(self, db_session, source_collection, copied):
        source_q1 = next(c for c in source_collection.forms[0]._all_components if c.name == "How many staff")
        copied_q1 = next(c for c in copied.forms[0]._all_components if c.name == "How many staff")
        copied_group = next(c for c in copied.forms[0]._all_components if c.name == "Staff group")

        source_ref = ExpressionReference.from_question(source_q1)
        copied_ref = ExpressionReference.from_question(copied_q1)
        assert copied_ref.unwrapped in copied_group.add_another_guidance_body
        assert source_ref.unwrapped not in copied_group.add_another_guidance_body

    def test_text_data_source_references_rewritten(self, db_session, source_collection, copied):
        source_gr_ds = next(ds for ds in source_collection.data_sources if ds.type == DataSourceType.GRANT_RECIPIENT)
        copied_gr_ds = next(ds for ds in copied.data_sources if ds.type == DataSourceType.GRANT_RECIPIENT)
        copied_alloc_q = next(c for c in copied.forms[0]._all_components if c.name == "Allocation display")

        source_ds_ref = ExpressionReference.from_data_source_column(source_gr_ds, "c_allocation")
        copied_ds_ref = ExpressionReference.from_data_source_column(copied_gr_ds, "c_allocation")
        assert copied_ds_ref.unwrapped in copied_alloc_q.text
        assert source_ds_ref.unwrapped not in copied_alloc_q.text

    def test_original_text_unchanged(self, db_session, source_collection, copied):
        source_q1 = next(c for c in source_collection.forms[0]._all_components if c.name == "How many staff")
        source_q2 = next(c for c in source_collection.forms[0]._all_components if c.name == "Staff detail")
        source_ref = ExpressionReference.from_question(source_q1)
        assert source_ref.unwrapped in source_q2.text


class TestCopyCollectionDataSources:
    def test_copies_custom_data_sources_with_new_ids(self, db_session, source_collection, copied):
        source_ds = [ds for ds in source_collection.data_sources if ds.type == DataSourceType.CUSTOM]
        copied_ds = [ds for ds in copied.data_sources if ds.type == DataSourceType.CUSTOM]
        assert len(copied_ds) == len(source_ds)
        assert {ds.id for ds in copied_ds}.isdisjoint({ds.id for ds in source_ds})

    def test_data_sources_belong_to_new_collection(self, db_session, copied):
        for ds in copied.data_sources:
            assert ds.collection_id == copied.id

    def test_radio_question_points_to_copied_data_source(self, db_session, source_collection, copied):
        source_radio = next(c for c in source_collection.forms[0]._all_components if c.name == "Favourite colour")
        copied_radio = next(c for c in copied.forms[0]._all_components if c.name == "Favourite colour")
        assert copied_radio.data_source_id is not None
        assert copied_radio.data_source_id != source_radio.data_source_id

    def test_grant_recipient_data_source_points_to_target_grant(
        self, db_session, source_collection, copied, target_grant
    ):
        copied_gr_ds = next(ds for ds in copied.data_sources if ds.type == DataSourceType.GRANT_RECIPIENT)
        assert copied_gr_ds.grant_id == target_grant.id

    def test_original_data_source_grant_id_unchanged(self, db_session, source_collection, copied):
        source_gr_ds = next(ds for ds in source_collection.data_sources if ds.type == DataSourceType.GRANT_RECIPIENT)
        from_db = db_session.get(DataSource, source_gr_ds.id)
        assert from_db.grant_id == source_collection.grant_id

    def test_original_data_sources_unchanged(self, db_session, source_collection, copied):
        for ds in source_collection.data_sources:
            from_db = db_session.get(DataSource, ds.id)
            assert from_db.collection_id == source_collection.id

    def test_overrides_created_by(self, db_session, source_collection, copied, copy_user):
        source_ds = [ds for ds in source_collection.data_sources if ds.type == DataSourceType.CUSTOM]
        copied_ds = [ds for ds in copied.data_sources if ds.type == DataSourceType.CUSTOM]
        assert all(e.created_by == copy_user for e in copied_ds)
        assert all(e.created_by != copy_user for e in source_ds)


class TestCopyCollectionDataSourceItems:
    def test_copies_items_for_custom_data_sources(self, db_session, source_collection, copied):
        source_radio = next(c for c in source_collection.forms[0]._all_components if c.name == "Favourite colour")
        copied_radio = next(c for c in copied.forms[0]._all_components if c.name == "Favourite colour")
        source_items = source_radio.data_source.items
        copied_items = copied_radio.data_source.items
        assert len(copied_items) == len(source_items)
        assert {i.id for i in copied_items}.isdisjoint({i.id for i in source_items})

    def test_preserves_item_keys_and_labels(self, db_session, source_collection, copied):
        source_radio = next(c for c in source_collection.forms[0]._all_components if c.name == "Favourite colour")
        copied_radio = next(c for c in copied.forms[0]._all_components if c.name == "Favourite colour")
        source_keys = [(i.key, i.label) for i in source_radio.data_source.items]
        copied_keys = [(i.key, i.label) for i in copied_radio.data_source.items]
        assert copied_keys == source_keys

    def test_items_belong_to_copied_data_source(self, db_session, copied):
        for ds in copied.data_sources:
            for item in ds.items:
                assert item.data_source_id == ds.id

    def test_original_items_unchanged(self, db_session, source_collection, copied):
        for ds in source_collection.data_sources:
            for item in ds.items:
                from_db = db_session.get(DataSourceItem, item.id)
                assert from_db.data_source_id == ds.id


class TestCopyCollectionDataSourceOrganisationItems:
    def test_creates_empty_rows_for_target_grant_recipients(self, db_session, copied, target_grant):
        copied_gr_ds = next(ds for ds in copied.data_sources if ds.type == DataSourceType.GRANT_RECIPIENT)
        target_external_ids = {gr.organisation.external_id for gr in target_grant.grant_recipients}
        copied_external_ids = {item.external_id for item in copied_gr_ds.organisation_items}
        assert len(target_external_ids) == 2
        assert copied_external_ids == target_external_ids
        assert all(item._data == {} for item in copied_gr_ds.organisation_items)

    def test_does_not_copy_source_organisation_items(self, db_session, source_collection, copied):
        source_gr_ds = next(ds for ds in source_collection.data_sources if ds.type == DataSourceType.GRANT_RECIPIENT)
        copied_gr_ds = next(ds for ds in copied.data_sources if ds.type == DataSourceType.GRANT_RECIPIENT)
        source_external_ids = {item.external_id for item in source_gr_ds.organisation_items}
        copied_external_ids = {item.external_id for item in copied_gr_ds.organisation_items}
        assert all(item._data for item in source_gr_ds.organisation_items)
        assert copied_external_ids.isdisjoint(source_external_ids)
        source_item_ids = {item.id for item in source_gr_ds.organisation_items}
        copied_item_ids = {item.id for item in copied_gr_ds.organisation_items}
        assert copied_item_ids.isdisjoint(source_item_ids)

    def test_organisation_items_belong_to_copied_data_source(self, db_session, copied):
        copied_gr_ds = next(ds for ds in copied.data_sources if ds.type == DataSourceType.GRANT_RECIPIENT)
        for item in copied_gr_ds.organisation_items:
            assert item.data_source_id == copied_gr_ds.id

    def test_original_organisation_items_unchanged(self, db_session, source_collection, copied):
        source_gr_ds = next(ds for ds in source_collection.data_sources if ds.type == DataSourceType.GRANT_RECIPIENT)
        items_by_external_id = source_gr_ds.get_organisation_items_by_external_id()
        assert len(items_by_external_id) == 2
        assert items_by_external_id["other-org"]._data == {"c_allocation": 200}
        for item in source_gr_ds.organisation_items:
            assert item.data_source_id == source_gr_ds.id

    def test_copies_grant_recipient_data_source_with_new_id(self, db_session, source_collection, copied):
        source_gr_ds = next(ds for ds in source_collection.data_sources if ds.type == DataSourceType.GRANT_RECIPIENT)
        copied_gr_ds = next(ds for ds in copied.data_sources if ds.type == DataSourceType.GRANT_RECIPIENT)
        assert copied_gr_ds.id != source_gr_ds.id

    def test_preserves_grant_recipient_data_source_schema(self, db_session, source_collection, copied):
        source_gr_ds = next(ds for ds in source_collection.data_sources if ds.type == DataSourceType.GRANT_RECIPIENT)
        copied_gr_ds = next(ds for ds in copied.data_sources if ds.type == DataSourceType.GRANT_RECIPIENT)
        assert copied_gr_ds.schema == source_gr_ds.schema


class TestCopyCollectionComponentReferences:
    def test_copies_component_references_with_new_ids(self, db_session, source_collection, copied):
        source_refs = [
            ref for f in source_collection.forms for c in f._all_components for ref in c.owned_component_references
        ]
        copied_refs = [ref for f in copied.forms for c in f._all_components for ref in c.owned_component_references]
        assert len(copied_refs) == len(source_refs)
        assert {r.id for r in copied_refs}.isdisjoint({r.id for r in source_refs})

    def test_component_references_point_to_copied_entities(self, db_session, source_collection, copied):
        source_component_ids = {c.id for f in source_collection.forms for c in f._all_components}
        for ref in (ref for f in copied.forms for c in f._all_components for ref in c.owned_component_references):
            assert ref.component_id not in source_component_ids
            if ref.depends_on_component_id:
                assert ref.depends_on_component_id not in source_component_ids

    def test_expression_component_references_point_to_copied_expressions(self, db_session, source_collection, copied):
        source_expr_ids = {e.id for f in source_collection.forms for c in f._all_components for e in c.expressions}
        for ref in (ref for f in copied.forms for c in f._all_components for ref in c.owned_component_references):
            if ref.expression_id:
                assert ref.expression_id not in source_expr_ids

    def test_original_component_references_unchanged(self, db_session, source_collection, copied):
        source_component_ids = {c.id for f in source_collection.forms for c in f._all_components}
        for f in source_collection.forms:
            for c in f._all_components:
                for ref in c.owned_component_references:
                    from_db = db_session.get(ComponentReference, ref.id)
                    assert from_db.component_id in source_component_ids


class TestCopyCollectionSubmissions:
    def test_does_not_copy_submissions(self, db_session, source_collection, copied):
        assert copied._submissions == []
        assert len(source_collection._submissions) > 0


class TestCopyCollectionDataSourceHeaderFile:
    def test_uploads_header_file_for_grant_recipient_data_source(
        self, db_session, source_collection, copy_user, target_grant
    ):
        with patch("app.common.data.interfaces.collections.upload_header_only_data_set_files") as mock_upload:
            result = copy_collection(
                source_collection,
                name="Copied Collection",
                user=copy_user,
                grant=target_grant,
            )
            db.session.flush()

        copied_gr_ds = next(ds for ds in result.data_sources if ds.type == DataSourceType.GRANT_RECIPIENT)
        mock_upload.assert_called_once_with(copied_gr_ds)


class TestCopyCollectionTimestamps:
    def test_copied_collection_has_fresh_created_at(self, db_session, source_collection, copied):
        assert copied.created_at_utc >= source_collection.created_at_utc

    def test_copied_forms_have_fresh_created_at(self, db_session, source_collection, copied):
        source_form = source_collection.forms[0]
        copied_form = copied.forms[0]
        assert copied_form.created_at_utc >= source_form.created_at_utc

    def test_copied_components_have_fresh_created_at(self, db_session, source_collection, copied):
        source_component = source_collection.forms[0]._all_components[0]
        copied_component = copied.forms[0]._all_components[0]
        assert copied_component.created_at_utc >= source_component.created_at_utc
