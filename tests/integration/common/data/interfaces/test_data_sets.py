import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm.exc import NoResultFound

from app.common.collections.types import DecimalAnswer, TextSingleLineAnswer
from app.common.data.interfaces.collections import (
    DataSourceHasReferencesException,
    _validate_and_sync_component_references,
)
from app.common.data.interfaces.data_sets import (
    create_uploaded_data_source,
    delete_data_source,
    get_collection_ids_with_missing_data_data_sets,
    get_data_source,
    get_data_source_list_for_collection,
    replace_uploaded_data_source,
)
from app.common.data.models import ComponentReference, DataSource, DataSourceItem, DataSourceOrganisationItem
from app.common.data.types import (
    DataSourceFileMetadata,
    DataSourceType,
    NumberTypeEnum,
    QuestionDataType,
)
from app.common.expressions import ExpressionContext
from app.common.expressions.references import InterpolationStatement
from app.constants import DATA_SET_EXTERNAL_ID_COLUMN_HEADER, DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER
from app.deliver_grant_funding.session_models import DataSetColumnMapping


class TestCreateUploadedDataSourceGrantRecipient:
    def test_creates_data_source(self, db_session, factories):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        user = factories.user.create()

        column_mappings = [
            DataSetColumnMapping(
                column_name="Capital allocation",
                column_type="INTEGER",
            ),
        ]
        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: "E123",
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "Rivendell",
                "Capital allocation": "500000",
            },
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: "E456",
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "Lothlorien",
                "Capital allocation": "300000",
            },
        ]

        data_source = create_uploaded_data_source(
            name="Test GR Data Set",
            data_source_type=DataSourceType.GRANT_RECIPIENT,
            grant_id=grant.id,
            collection_id=collection.id,
            column_mappings=column_mappings,
            all_rows=all_rows,
            user=user,
            data_source_id=uuid.uuid4(),
            original_filename="test.csv",
            s3_key="data-set-uploads/test.csv",
        )

        assert data_source.id is not None
        assert data_source.name == "Test GR Data Set"
        assert data_source.type == DataSourceType.GRANT_RECIPIENT
        assert data_source.grant_id == grant.id
        assert data_source.collection_id == collection.id
        assert data_source.file_metadata.s3_key == "data-set-uploads/test.csv"
        assert data_source.file_metadata.original_filename == "test.csv"

        from_db = db_session.get(DataSource, data_source.id)
        assert from_db is not None

    def test_creates_schema(self, db_session, factories):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        user = factories.user.create()

        column_mappings = [
            DataSetColumnMapping(column_name="Capital allocation", column_type="INTEGER", prefix="£"),
            DataSetColumnMapping(column_name="Additional info", column_type="TEXT"),
        ]
        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: "E123",
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "Rivendell",
                "Capital allocation": "£500000",
                "Additional info": "Notes",
            },
        ]

        data_source = create_uploaded_data_source(
            name="Test Schema Data Set",
            data_source_type=DataSourceType.GRANT_RECIPIENT,
            grant_id=grant.id,
            collection_id=collection.id,
            column_mappings=column_mappings,
            all_rows=all_rows,
            user=user,
            data_source_id=uuid.uuid4(),
            original_filename="test.csv",
            s3_key="data-set-uploads/test.csv",
        )

        allocation_column = data_source.schema.root["c_capital_allocation"]
        assert allocation_column.data_type == QuestionDataType.NUMBER
        assert allocation_column.original_column_name == "Capital allocation"
        assert allocation_column.presentation_options.prefix == "£"

        info_column = data_source.schema.root["c_additional_info"]
        assert info_column.data_type == QuestionDataType.TEXT_SINGLE_LINE

    def test_creates_organisation_items_one_per_grant_recipient(self, db_session, factories):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        user = factories.user.create()

        column_mappings = [
            DataSetColumnMapping(column_name="Capital allocation", column_type="INTEGER"),
        ]
        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: "E123",
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "Rivendell",
                "Capital allocation": "500000",
            },
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: "E456",
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "Lothlorien",
                "Capital allocation": "300000",
            },
        ]

        data_source = create_uploaded_data_source(
            name="Test GR Data Set",
            data_source_type=DataSourceType.GRANT_RECIPIENT,
            grant_id=grant.id,
            collection_id=collection.id,
            column_mappings=column_mappings,
            all_rows=all_rows,
            user=user,
            data_source_id=uuid.uuid4(),
            original_filename="test.csv",
            s3_key="data-set-uploads/test.csv",
        )

        org_items = (
            db_session.query(DataSourceOrganisationItem)
            .filter_by(data_source_id=data_source.id)
            .order_by(DataSourceOrganisationItem.external_id)
            .all()
        )

        assert len(org_items) == 2
        assert org_items[0].external_id == "E123"
        assert org_items[1].external_id == "E456"

    def test_data_blob_is_dict_for_grant_recipient(self, db_session, factories):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        user = factories.user.create()

        column_mappings = [
            DataSetColumnMapping(column_name="Capital allocation", column_type="INTEGER"),
            DataSetColumnMapping(column_name="Description", column_type="TEXT"),
        ]
        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: "E123",
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "Rivendell",
                "Capital allocation": "500000",
                "Description": "A fine place",
            },
        ]

        data_source = create_uploaded_data_source(
            name="Test GR Blob",
            data_source_type=DataSourceType.GRANT_RECIPIENT,
            grant_id=grant.id,
            collection_id=collection.id,
            column_mappings=column_mappings,
            all_rows=all_rows,
            user=user,
            data_source_id=uuid.uuid4(),
            original_filename="test.csv",
            s3_key="data-set-uploads/test.csv",
        )

        org_item = db_session.query(DataSourceOrganisationItem).filter_by(data_source_id=data_source.id).one()
        assert isinstance(org_item.data, dict)
        assert org_item._data["c_capital_allocation"] == 500000
        assert org_item._data["c_description"] == "A fine place"

    def test_cleans_prefix_and_suffix_from_number_values(self, db_session, factories):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        user = factories.user.create()

        column_mappings = [
            DataSetColumnMapping(
                column_name="Amount", column_type="DECIMAL", prefix="£", suffix="m", max_decimal_places=2
            ),
        ]
        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: "E123",
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "Rivendell",
                "Amount": "£1.50m",
            },
        ]

        data_source = create_uploaded_data_source(
            name="Test Clean Values",
            data_source_type=DataSourceType.GRANT_RECIPIENT,
            grant_id=grant.id,
            collection_id=collection.id,
            column_mappings=column_mappings,
            all_rows=all_rows,
            user=user,
            data_source_id=uuid.uuid4(),
            original_filename="test.csv",
            s3_key="data-set-uploads/test.csv",
        )

        org_item = db_session.query(DataSourceOrganisationItem).filter_by(data_source_id=data_source.id).one()
        assert org_item._data["c_amount"] == "1.50"

    def test_excludes_identifier_columns_from_data_blob(self, db_session, factories):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        user = factories.user.create()

        column_mappings = [
            DataSetColumnMapping(column_name="Capital allocation", column_type="INTEGER"),
        ]
        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: "E123",
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "Rivendell",
                "Capital allocation": "500000",
            },
        ]

        data_source = create_uploaded_data_source(
            name="Test Exclude Identifiers",
            data_source_type=DataSourceType.GRANT_RECIPIENT,
            grant_id=grant.id,
            collection_id=collection.id,
            column_mappings=column_mappings,
            all_rows=all_rows,
            user=user,
            data_source_id=uuid.uuid4(),
            original_filename="test.csv",
            s3_key="data-set-uploads/test.csv",
        )

        org_item = db_session.query(DataSourceOrganisationItem).filter_by(data_source_id=data_source.id).one()
        assert "ons-code" not in org_item._data
        assert "grant-recipient" not in org_item._data

    def test_empty_string_values_saved_as_none(self, db_session, factories):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        user = factories.user.create()

        column_mappings = [
            DataSetColumnMapping(column_name="Notes", column_type="TEXT"),
        ]
        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: "E123",
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "Rivendell",
                "Notes": "",
            },
        ]

        data_source = create_uploaded_data_source(
            name="Test Empty Values",
            data_source_type=DataSourceType.GRANT_RECIPIENT,
            grant_id=grant.id,
            collection_id=collection.id,
            column_mappings=column_mappings,
            all_rows=all_rows,
            user=user,
            data_source_id=uuid.uuid4(),
            original_filename="test.csv",
            s3_key="data-set-uploads/test.csv",
        )

        org_item = db_session.query(DataSourceOrganisationItem).filter_by(data_source_id=data_source.id).one()
        assert org_item._data["c_notes"] is None


class TestCreateUploadedDataSourceErrors:
    def test_raises_error_for_unsupported_type(self, db_session, factories):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        user = factories.user.create()

        column_mappings = [
            DataSetColumnMapping(column_name="Code", column_type="TEXT"),
            DataSetColumnMapping(column_name="Label", column_type="TEXT"),
        ]

        with pytest.raises(ValueError, match="Unsupported data source type"):
            create_uploaded_data_source(
                name="Test Unsupported",
                data_source_type=DataSourceType.CUSTOM,
                grant_id=grant.id,
                collection_id=collection.id,
                column_mappings=column_mappings,
                all_rows=[],
                user=user,
                data_source_id=uuid.uuid4(),
                original_filename="test.csv",
                s3_key="data-set-uploads/test.csv",
            )

    def test_raises_error_for_empty_schema(self, db_session, factories):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        user = factories.user.create()

        with pytest.raises(ValueError, match="Cannot build a schema from an empty list of column mappings"):
            create_uploaded_data_source(
                name="Test Unsupported",
                data_source_type=DataSourceType.GRANT_RECIPIENT,
                grant_id=grant.id,
                collection_id=collection.id,
                column_mappings=[],
                all_rows=[],
                user=user,
                data_source_id=uuid.uuid4(),
                original_filename="test.csv",
                s3_key="data-set-uploads/test.csv",
            )


class TestCreateUploadedDataSourceSchemaOptions:
    def test_number_columns_have_presentation_and_data_options(self, db_session, factories):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        user = factories.user.create()

        column_mappings = [
            DataSetColumnMapping(
                column_name="Amount",
                column_type="BRITISH_POUNDS",
            ),
        ]
        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: "E123",
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "Rivendell",
                "Amount": "£100.50",
            },
        ]

        data_source = create_uploaded_data_source(
            name="Test Schema Options",
            data_source_type=DataSourceType.GRANT_RECIPIENT,
            grant_id=grant.id,
            collection_id=collection.id,
            column_mappings=column_mappings,
            all_rows=all_rows,
            user=user,
            data_source_id=uuid.uuid4(),
            original_filename="test.csv",
            s3_key="data-set-uploads/test.csv",
        )

        schema_col = data_source.schema.root["c_amount"]
        assert schema_col.presentation_options.prefix == "£"
        assert schema_col.presentation_options.suffix == ""
        assert schema_col.data_options.number_type == NumberTypeEnum.DECIMAL
        assert schema_col.data_options.max_decimal_places == 2

    def test_text_columns_have_none_presentation_and_data_options(self, db_session, factories):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        user = factories.user.create()

        column_mappings = [
            DataSetColumnMapping(column_name="Description", column_type="TEXT"),
        ]
        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: "E123",
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "Rivendell",
                "Description": "Notes",
            },
        ]

        data_source = create_uploaded_data_source(
            name="Test Text Schema",
            data_source_type=DataSourceType.GRANT_RECIPIENT,
            grant_id=grant.id,
            collection_id=collection.id,
            column_mappings=column_mappings,
            all_rows=all_rows,
            user=user,
            data_source_id=uuid.uuid4(),
            original_filename="test.csv",
            s3_key="data-set-uploads/test.csv",
        )

        schema_col = data_source.schema.root["c_description"]
        assert schema_col.data_type == QuestionDataType.TEXT_SINGLE_LINE
        assert schema_col.original_column_name == "Description"
        assert schema_col.presentation_options.prefix is None
        assert schema_col.presentation_options.suffix is None
        assert schema_col.data_options.number_type is None
        assert schema_col.data_options.max_decimal_places is None

    def test_schema_keys_use_safe_identifiers(self, db_session, factories):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        user = factories.user.create()

        column_mappings = [
            DataSetColumnMapping(column_name="Capital Allocation (£)", column_type="BRITISH_POUNDS"),
        ]
        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: "E123",
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "Rivendell",
                "Capital Allocation (£)": "500000",
            },
        ]

        data_source = create_uploaded_data_source(
            name="Test Slugified Keys",
            data_source_type=DataSourceType.GRANT_RECIPIENT,
            grant_id=grant.id,
            collection_id=collection.id,
            column_mappings=column_mappings,
            all_rows=all_rows,
            user=user,
            data_source_id=uuid.uuid4(),
            original_filename="test.csv",
            s3_key="data-set-uploads/test.csv",
        )

        assert "c_capital_allocation" in data_source.schema.root
        assert "Capital Allocation (£)" not in data_source.schema.root


class TestGetDataSource:
    def test_get_data_source(self, db_session, factories):
        data_source = factories.data_source.create()
        from_db = get_data_source(data_source.id)
        assert from_db is not None
        assert from_db.id == data_source.id

    def test_get_data_source_not_found(self, db_session):
        with pytest.raises(NoResultFound):
            get_data_source(uuid.uuid4())

    def test_get_data_source_with_organisation_items(self, db_session, factories, track_sql_queries):
        grant = factories.grant.create()
        factories.grant_recipient.create_batch(2, grant=grant)
        data_source = factories.data_source.create(
            grant=grant,
            collection=factories.collection.create(grant=grant),
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
        )
        db_session.expire_all()

        from_db = get_data_source(data_source.id, with_organisation_items=True)

        with track_sql_queries() as queries:
            items = from_db.organisation_items
            assert len(items) == 2

        assert len(queries) == 0

    def test_get_data_source_without_flags_does_not_eagerly_load_items(self, db_session, factories, track_sql_queries):
        grant = factories.grant.create()
        factories.grant_recipient.create(grant=grant)
        data_source = factories.data_source.create(
            grant=grant,
            collection=factories.collection.create(grant=grant),
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
        )
        db_session.expire_all()

        get_data_source(data_source.id)

        with track_sql_queries() as queries:
            _ = db_session.get(DataSource, data_source.id).organisation_items
        assert len(queries) > 0


class TestDeleteDataSource:
    def test_delete_data_source(self, db_session, factories, mock_s3_service_calls):
        data_source = factories.data_source.create()
        assert db_session.scalar(select(func.count()).select_from(DataSourceItem)) == 3

        delete_data_source(data_source)
        db_session.flush()

        assert db_session.get(DataSource, data_source.id) is None
        assert db_session.scalar(select(func.count()).select_from(DataSourceItem)) == 0
        assert db_session.scalar(select(func.count()).select_from(DataSourceOrganisationItem)) == 0
        assert len(mock_s3_service_calls.delete_file_calls) == 0

    def test_delete_data_source_deletes_s3_file(self, db_session, factories, mock_s3_service_calls):
        file_metadata = DataSourceFileMetadata(s3_key="data-set-uploads/test.csv", original_filename="test.csv")
        data_source = factories.data_source.create(file_metadata=file_metadata)
        assert db_session.scalar(select(func.count()).select_from(DataSourceItem)) == 3

        delete_data_source(data_source)
        db_session.flush()

        assert db_session.get(DataSource, data_source.id) is None
        assert db_session.scalar(select(func.count()).select_from(DataSourceItem)) == 0
        assert db_session.scalar(select(func.count()).select_from(DataSourceOrganisationItem)) == 0
        assert len(mock_s3_service_calls.delete_file_calls) == 1
        assert mock_s3_service_calls.delete_file_calls[0].args[0] == "data-set-uploads/test.csv"

    def test_delete_data_source_cascades_organisation_items(self, db_session, factories):

        grant = factories.grant.create()
        factories.grant_recipient.create_batch(2, grant=grant)
        data_source = factories.data_source.create(
            grant=grant,
            collection=factories.collection.create(grant=grant),
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
            file_metadata=None,
        )
        assert db_session.scalar(select(func.count()).select_from(DataSourceOrganisationItem)) == 2

        delete_data_source(data_source)
        db_session.flush()

        assert db_session.scalar(select(func.count()).select_from(DataSourceOrganisationItem)) == 0

    def test_delete_only_deletes_target_data_source(self, db_session, factories):
        grant = factories.grant.create()
        factories.grant_recipient.create(grant=grant)
        data_source_1 = factories.data_source.create(
            grant=grant,
            collection=factories.collection.create(grant=grant),
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
            file_metadata=None,
        )
        data_source_2 = factories.data_source.create(
            name="DS 2",
            grant=grant,
            collection=factories.collection.create(grant=grant),
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
            file_metadata=None,
        )
        delete_data_source(data_source_1)
        db_session.flush()

        assert db_session.get(DataSource, data_source_1.id) is None
        assert db_session.get(DataSource, data_source_2.id) is not None

        assert db_session.scalar(select(func.count()).select_from(DataSourceOrganisationItem)) == 1
        assert db_session.get(DataSourceOrganisationItem, data_source_1.organisation_items[0].id) is None

    def test_delete_blocked_when_column_is_referenced(self, db_session, factories, mock_s3_service_calls):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        data_source = factories.data_source.create(
            grant=grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
        )
        form = factories.form.create(collection=collection)
        question = factories.question.create(
            form=form,
            text=f"Your allocation is (({data_source.safe_did}.c_allocation))",
        )
        _validate_and_sync_component_references(
            question,
            ExpressionContext.build_expression_context(collection=collection, mode="interpolation"),
        )
        db_session.flush()

        with pytest.raises(DataSourceHasReferencesException) as e:
            delete_data_source(data_source)

        assert e.value.data_source_id == data_source.id
        assert e.value.data_source_name == "Grant allocation"
        assert e.value.referenced_columns == {"c_allocation"}
        assert db_session.get(DataSource, data_source.id) is not None
        assert mock_s3_service_calls.delete_file_calls == []

    def test_delete_allowed_after_references_removed(self, db_session, factories, mock_s3_service_calls):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        data_source = factories.data_source.create(
            grant=grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
        )
        form = factories.form.create(collection=collection)
        question = factories.question.create(
            form=form,
            text=f"Your allocation is (({data_source.safe_did}.c_allocation))",
        )
        _validate_and_sync_component_references(
            question,
            ExpressionContext.build_expression_context(collection=collection, mode="interpolation"),
        )
        db_session.flush()

        question.text = InterpolationStatement("Static text with no reference")
        _validate_and_sync_component_references(
            question,
            ExpressionContext.build_expression_context(collection=collection, mode="interpolation"),
        )
        db_session.flush()

        assert db_session.query(ComponentReference).count() == 0

        delete_data_source(data_source)
        db_session.flush()

        assert db_session.get(DataSource, data_source.id) is None


class TestDataSourceOrganisationItemDataProperty:
    def test_2d_data_property_returns_typed_answers_after_db_round_trip(self, db_session, factories):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        user = factories.user.create()

        data_source = create_uploaded_data_source(
            name="Test data source",
            data_source_type=DataSourceType.GRANT_RECIPIENT,
            grant_id=grant.id,
            collection_id=collection.id,
            column_mappings=[
                DataSetColumnMapping(column_name="Capital allocation", column_type="BRITISH_POUNDS"),
                DataSetColumnMapping(column_name="Additional notes", column_type="TEXT"),
            ],
            all_rows=[
                {
                    DATA_SET_EXTERNAL_ID_COLUMN_HEADER: "E123",
                    DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "Rivendell",
                    "Capital allocation": "£1,000.00",
                    "Additional notes": "Nice place",
                }
            ],
            user=user,
            s3_key="data-set-uploads/test.csv",
            original_filename="test.csv",
            data_source_id=uuid.uuid4(),
        )

        db_datasource = get_data_source(data_source.id, with_organisation_items=True)
        org_item = db_datasource.organisation_items[0]
        typed_data = org_item.data

        assert isinstance(typed_data, dict)
        allocation = typed_data["c_capital_allocation"]
        assert isinstance(allocation, DecimalAnswer)
        assert allocation.value == Decimal("1000.00")
        assert allocation.get_value_for_interpolation() == "£1,000.00"

        notes = typed_data["c_additional_notes"]
        assert isinstance(notes, TextSingleLineAnswer)
        assert notes.get_value_for_interpolation() == "Nice place"

    def test_none_values_in_db_return_none_from_data_property(self, db_session, factories):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        user = factories.user.create()

        data_source = create_uploaded_data_source(
            name="Test Data Set",
            data_source_type=DataSourceType.GRANT_RECIPIENT,
            grant_id=grant.id,
            collection_id=collection.id,
            column_mappings=[
                DataSetColumnMapping(column_name="Notes", column_type="TEXT"),
                DataSetColumnMapping(column_name="Capital allocation", column_type="BRITISH_POUNDS"),
            ],
            all_rows=[
                {
                    DATA_SET_EXTERNAL_ID_COLUMN_HEADER: "E123",
                    DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "Rivendell",
                    "Notes": "",
                    "Capital allocation": "",
                }
            ],
            user=user,
            s3_key="data-set-uploads/test.csv",
            original_filename="test.csv",
            data_source_id=uuid.uuid4(),
        )

        db_datasource = get_data_source(data_source.id, with_organisation_items=True)
        org_item = db_datasource.organisation_items[0]

        # Confirm raw _data stores None
        assert org_item._data["c_notes"] is None
        assert org_item._data["c_capital_allocation"] is None

        # Confirm typed .data returns None
        assert org_item.data["c_notes"] is None
        assert org_item.data["c_capital_allocation"] is None


class TestGetDataSourceListForCollection:
    def test_returns_data_sources_for_collection(self, factories, track_sql_queries):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        collection_id = collection.id
        factories.grant_recipient.create_batch(3, grant=grant)
        user_1 = factories.user.create()
        user_2 = factories.user.create()
        data_source = factories.data_source.create(
            name="First data set",
            grant=grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
            create_gr_org_items__data=[111, 222, 333],
            created_by=user_1,
        )
        data_source_2 = factories.data_source.create(
            name="Second data set",
            grant=grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
            create_gr_org_items__data=[111, 222, 333],
            created_by=user_1,
            updated_by=user_2,
        )

        with track_sql_queries() as queries:
            rows = get_data_source_list_for_collection(collection_id)
        assert len(queries) == 1

        assert len(rows) == 2
        assert [(row.name, row.uploaded_by_name) for row in rows] == [
            (data_source.name, data_source.created_by.name),
            (data_source_2.name, data_source_2.updated_by.name),
        ]

    def test_has_missing_data_true_when_org_item_has_null(self, factories):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        factories.grant_recipient.create_batch(3, grant=grant)
        data_source = factories.data_source.create(
            name="First data set",
            grant=grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
            create_gr_org_items__data=[111, 222, None],
        )
        data_source_2 = factories.data_source.create(
            name="Second data set",
            grant=grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
            create_gr_org_items__data=[111, 222, 333],
        )
        rows = get_data_source_list_for_collection(collection.id)
        rows_by_id = {row.id: row for row in rows}
        assert rows_by_id[data_source.id].has_missing_data is True
        assert rows_by_id[data_source_2.id].has_missing_data is False

    def test_excludes_data_sources_from_other_collections(self, factories):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        collection_2 = factories.collection.create(grant=grant)

        factories.grant_recipient.create_batch(3, grant=grant)

        data_source = factories.data_source.create(
            name="First data set",
            grant=grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
            create_gr_org_items__data=[111, 222, None],
        )
        factories.data_source.create(
            name="Second data set",
            grant=grant,
            collection=collection_2,
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
            create_gr_org_items__data=[111, 222, 333],
        )

        rows = get_data_source_list_for_collection(collection.id)
        assert len(rows) == 1
        assert rows[0].name == data_source.name

    def test_ordering_is_by_name(self, factories):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        factories.grant_recipient.create_batch(3, grant=grant)
        data_source = factories.data_source.create(
            name="Zzzz data set",
            grant=grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
            create_gr_org_items__data=[111, 222, None],
        )

        data_source_2 = factories.data_source.create(
            name="Mmmm data set",
            grant=grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
            create_gr_org_items__data=[111, 222, 333],
        )
        data_source_3 = factories.data_source.create(
            name="Aaaa data set",
            grant=grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
            create_gr_org_items__data=[111, 222, 333],
        )
        rows = get_data_source_list_for_collection(collection.id)
        assert [row.name for row in rows] == [
            data_source_3.name,
            data_source_2.name,
            data_source.name,
        ]


class TestGetCollectionIdsWithMissingDataDataSets:
    def test_returns_collection_id_when_data_source_has_missing_data(self, factories, track_sql_queries):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        collection_2 = factories.collection.create(grant=grant)

        factories.grant_recipient.create_batch(3, grant=grant)

        factories.data_source.create(
            grant=grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
            create_gr_org_items__data=[111, 222, None],
        )
        factories.data_source.create(
            name="Second data set",
            grant=grant,
            collection=collection_2,
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
            create_gr_org_items__data=[111, 222, 333],
        )

        grant_id = grant.id

        with track_sql_queries() as queries:
            result = get_collection_ids_with_missing_data_data_sets(grant_id)
        assert len(queries) == 1

        assert collection.id in result
        assert collection_2.id not in result

    def test_excludes_collections_from_other_grants(self, factories):
        grant = factories.grant.create()
        grant_2 = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        collection_2 = factories.collection.create(grant=grant_2)

        factories.grant_recipient.create_batch(3, grant=grant)

        factories.data_source.create(
            grant=grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
            create_gr_org_items__data=[111, 222, None],
        )
        factories.data_source.create(
            name="Second data set",
            grant=grant_2,
            collection=collection_2,
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
            create_gr_org_items__data=[111, 222, 333],
        )
        result = get_collection_ids_with_missing_data_data_sets(grant.id)
        assert collection.id in result
        assert collection_2.id not in result

    def test_returns_empty_set_when_no_data_sources(self, factories):
        grant = factories.grant.create()
        factories.collection.create(grant=grant)
        factories.grant_recipient.create_batch(3, grant=grant)

        result = get_collection_ids_with_missing_data_data_sets(grant.id)

        assert result == set()


class TestReplaceUploadedDataSource:
    def test_update_name(self, factories):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        data_source = factories.data_source.create(
            grant=grant, collection=collection, name="Popular Cheeses", type=DataSourceType.GRANT_RECIPIENT
        )
        replace_uploaded_data_source(
            data_source=data_source,
            new_columns=[],
            all_headers=[],
            all_rows=[],
            name="Most popular cheeses",
        )
        from_db = get_data_source(data_source.id, with_organisation_items=False)
        assert from_db.name == "Most popular cheeses"
