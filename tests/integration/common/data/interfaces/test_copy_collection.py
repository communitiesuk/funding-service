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


def test_copy_collection_copies_collection_forms_and_components(
    db_session, source_collection, copied, target_grant, copy_user
):
    assert copied.id != source_collection.id
    assert db_session.get(Collection, copied.id) is not None
    assert copied.name == "Copied Collection"
    assert copied.grant_id == target_grant.id
    assert copied.created_by_id == copy_user.id
    assert copied.status == CollectionStatusEnum.DRAFT

    original = db_session.get(Collection, source_collection.id)
    assert original.name == "Source Collection"
    assert original.grant_id == source_collection.grant_id

    source_form_ids = {f.id for f in source_collection.forms}
    copied_form_ids = {f.id for f in copied.forms}
    assert len(copied.forms) == len(source_collection.forms)
    assert copied_form_ids.isdisjoint(source_form_ids)
    assert [f.title for f in copied.forms] == [f.title for f in source_collection.forms]
    assert all(form.collection_id == copied.id for form in copied.forms)
    assert all(db_session.get(Form, form.id).collection_id == source_collection.id for form in source_collection.forms)

    source_components = source_collection.forms[0]._all_components
    copied_components = copied.forms[0]._all_components
    assert len(copied_components) == len(source_components)
    assert {c.id for c in copied_components}.isdisjoint({c.id for c in source_components})
    assert all(component.form_id == copied.forms[0].id for component in copied_components)
    assert all(
        db_session.get(Component, component.id).form_id == source_collection.forms[0].id
        for component in source_components
    )

    source_q = next(c for c in source_components if c.name == "How many staff")
    copied_q = next(c for c in copied_components if c.name == "How many staff")
    assert copied_q.data_type == source_q.data_type
    assert copied_q.name == source_q.name


def test_copy_collection_rewrites_expressions_and_text(db_session, source_collection, copied, copy_user):
    source_q1 = next(c for c in source_collection.forms[0]._all_components if c.name == "How many staff")
    source_q2 = next(c for c in source_collection.forms[0]._all_components if c.name == "Staff detail")
    source_q3 = next(c for c in source_collection.forms[0]._all_components if c.name == "Budget amount")
    source_gr_ds = next(ds for ds in source_collection.data_sources if ds.type == DataSourceType.GRANT_RECIPIENT)

    copied_q1 = next(c for c in copied.forms[0]._all_components if c.name == "How many staff")
    copied_q2 = next(c for c in copied.forms[0]._all_components if c.name == "Staff detail")
    copied_q3 = next(c for c in copied.forms[0]._all_components if c.name == "Budget amount")
    copied_spend = next(c for c in copied.forms[0]._all_components if c.name == "Spend amount")
    copied_alloc_q = next(c for c in copied.forms[0]._all_components if c.name == "Allocation display")
    copied_group = next(c for c in copied.forms[0]._all_components if c.name == "Staff group")
    copied_gr_ds = next(ds for ds in copied.data_sources if ds.type == DataSourceType.GRANT_RECIPIENT)

    source_exprs = [e for f in source_collection.forms for c in f._all_components for e in c.expressions]
    copied_exprs = [e for f in copied.forms for c in f._all_components for e in c.expressions]
    assert len(copied_exprs) == len(source_exprs)
    assert {e.id for e in copied_exprs}.isdisjoint({e.id for e in source_exprs})
    assert all(e.created_by == copy_user for e in copied_exprs)
    assert all(e.created_by != copy_user for e in source_exprs)

    source_q1_ref = ExpressionReference.from_question(source_q1)
    copied_q1_ref = ExpressionReference.from_question(copied_q1)
    source_q3_ref = ExpressionReference.from_question(source_q3)
    copied_q3_ref = ExpressionReference.from_question(copied_q3)
    source_ds_ref = ExpressionReference.from_data_source_column(source_gr_ds, "c_allocation")
    copied_ds_ref = ExpressionReference.from_data_source_column(copied_gr_ds, "c_allocation")

    staff_detail_expr = copied_q2.expressions[0]
    assert copied_q1_ref.unwrapped in staff_detail_expr.statement
    assert source_q1_ref.unwrapped not in staff_detail_expr.statement
    assert copied_q1_ref.unwrapped in str(staff_detail_expr.context)
    assert source_q1_ref.unwrapped not in str(staff_detail_expr.context)

    allocation_expr = copied_alloc_q.expressions[0]
    assert copied_ds_ref.unwrapped in allocation_expr.statement
    assert source_ds_ref.unwrapped not in allocation_expr.statement
    assert copied_ds_ref.unwrapped in str(allocation_expr.context)
    assert source_ds_ref.unwrapped not in str(allocation_expr.context)
    assert copied_ds_ref.wrapped in allocation_expr.evaluatable_expression.message
    assert source_ds_ref.wrapped not in allocation_expr.evaluatable_expression.message
    assert copied_q1_ref.unwrapped in allocation_expr.evaluatable_expression.statement
    assert source_q1_ref.unwrapped not in allocation_expr.evaluatable_expression.statement
    assert copied_ds_ref.unwrapped in allocation_expr.evaluatable_expression.statement
    assert source_ds_ref.unwrapped not in allocation_expr.evaluatable_expression.statement

    spend_expr = copied_spend.expressions[0].evaluatable_expression
    assert spend_expr.minimum_expression == copied_q1_ref
    assert spend_expr.minimum_expression != source_q1_ref
    assert spend_expr.subject_reference == copied_q3_ref
    assert spend_expr.subject_reference != source_q3_ref

    assert copied_q1_ref.unwrapped in copied_q2.text
    assert source_q1_ref.unwrapped not in copied_q2.text
    assert copied_q1_ref.unwrapped in copied_q2.hint
    assert source_q1_ref.unwrapped not in copied_q2.hint
    assert copied_q1_ref.unwrapped in copied_group.add_another_guidance_body
    assert source_q1_ref.unwrapped not in copied_group.add_another_guidance_body
    assert copied_ds_ref.unwrapped in copied_alloc_q.text
    assert source_ds_ref.unwrapped not in copied_alloc_q.text
    assert source_q1_ref.unwrapped in source_q2.text


def test_copy_collection_copies_data_sources_items_and_organisation_items(
    db_session, source_collection, copied, target_grant, copy_user
):
    source_radio = next(c for c in source_collection.forms[0]._all_components if c.name == "Favourite colour")
    copied_radio = next(c for c in copied.forms[0]._all_components if c.name == "Favourite colour")
    source_gr_ds = next(ds for ds in source_collection.data_sources if ds.type == DataSourceType.GRANT_RECIPIENT)
    copied_gr_ds = next(ds for ds in copied.data_sources if ds.type == DataSourceType.GRANT_RECIPIENT)

    source_custom_ds = [ds for ds in source_collection.data_sources if ds.type == DataSourceType.CUSTOM]
    copied_custom_ds = [ds for ds in copied.data_sources if ds.type == DataSourceType.CUSTOM]
    assert len(copied_custom_ds) == len(source_custom_ds)
    assert {ds.id for ds in copied_custom_ds}.isdisjoint({ds.id for ds in source_custom_ds})
    assert all(ds.collection_id == copied.id for ds in copied.data_sources)
    assert all(
        db_session.get(DataSource, ds.id).collection_id == source_collection.id
        for ds in source_collection.data_sources
    )
    assert copied_radio.data_source_id is not None
    assert copied_radio.data_source_id != source_radio.data_source_id
    assert copied_gr_ds.grant_id == target_grant.id
    assert db_session.get(DataSource, source_gr_ds.id).grant_id == source_collection.grant_id
    assert all(e.created_by == copy_user for e in copied_custom_ds)
    assert all(e.created_by != copy_user for e in source_custom_ds)

    assert len(copied_radio.data_source.items) == len(source_radio.data_source.items)
    assert {i.id for i in copied_radio.data_source.items}.isdisjoint({i.id for i in source_radio.data_source.items})
    assert [(i.key, i.label) for i in copied_radio.data_source.items] == [
        (i.key, i.label) for i in source_radio.data_source.items
    ]
    assert all(item.data_source_id == ds.id for ds in copied.data_sources for item in ds.items)
    assert all(
        db_session.get(DataSourceItem, item.id).data_source_id == ds.id
        for ds in source_collection.data_sources
        for item in ds.items
    )

    target_external_ids = {gr.organisation.external_id for gr in target_grant.grant_recipients}
    copied_external_ids = {item.external_id for item in copied_gr_ds.organisation_items}
    assert len(target_external_ids) == 2
    assert copied_external_ids == target_external_ids
    assert all(item._data == {} for item in copied_gr_ds.organisation_items)
    assert copied_gr_ds.id != source_gr_ds.id
    assert copied_gr_ds.schema == source_gr_ds.schema

    source_external_ids = {item.external_id for item in source_gr_ds.organisation_items}
    assert copied_external_ids.isdisjoint(source_external_ids)
    assert {item.id for item in copied_gr_ds.organisation_items}.isdisjoint(
        {item.id for item in source_gr_ds.organisation_items}
    )
    assert all(item.data_source_id == copied_gr_ds.id for item in copied_gr_ds.organisation_items)
    assert all(item.data_source_id == source_gr_ds.id for item in source_gr_ds.organisation_items)
    assert all(item._data for item in source_gr_ds.organisation_items)
    assert source_gr_ds.get_organisation_items_by_external_id()["other-org"]._data == {"c_allocation": 200}


def test_copy_collection_copies_component_references_and_omits_submissions(db_session, source_collection, copied):
    source_refs = [
        ref for f in source_collection.forms for c in f._all_components for ref in c.owned_component_references
    ]
    copied_refs = [ref for f in copied.forms for c in f._all_components for ref in c.owned_component_references]
    source_component_ids = {c.id for f in source_collection.forms for c in f._all_components}
    source_expr_ids = {e.id for f in source_collection.forms for c in f._all_components for e in c.expressions}

    assert len(copied_refs) == len(source_refs)
    assert {r.id for r in copied_refs}.isdisjoint({r.id for r in source_refs})
    for ref in copied_refs:
        assert ref.component_id not in source_component_ids
        if ref.depends_on_component_id:
            assert ref.depends_on_component_id not in source_component_ids
        if ref.expression_id:
            assert ref.expression_id not in source_expr_ids

    for f in source_collection.forms:
        for c in f._all_components:
            for ref in c.owned_component_references:
                assert db_session.get(ComponentReference, ref.id).component_id in source_component_ids

    assert copied._submissions == []
    assert len(source_collection._submissions) > 0


def test_copy_collection_uses_fresh_timestamps(source_collection, copied):
    assert copied.created_at_utc >= source_collection.created_at_utc
    assert copied.forms[0].created_at_utc >= source_collection.forms[0].created_at_utc
    assert (
        copied.forms[0]._all_components[0].created_at_utc
        >= source_collection.forms[0]._all_components[0].created_at_utc
    )


def test_copy_collection_nulls_date_fields(db_session, factories, copy_user, target_grant):
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


def test_copy_collection_does_not_copy_other_collections_in_grant(db_session, factories, source_collection, copied):
    other_collection = factories.collection.create(grant=source_collection.grant, name="Other Collection")
    assert other_collection not in list(copied.grant.collections)


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
