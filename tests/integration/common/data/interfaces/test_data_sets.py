import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm.exc import NoResultFound

from app.common.data.interfaces.data_sets import create_uploaded_data_source, delete_data_source, get_data_source
from app.common.data.models import DataSource, DataSourceItem, DataSourceOrganisationItem
from app.common.data.types import DataSourceType, NumberTypeEnum, QuestionDataType
from app.deliver_grant_funding.session_models import DataSetColumnMapping


class TestCreateUploadedDataSourceGrantRecipient:
    def test_creates_data_source(self, db_session, factories):
        grant = factories.grant.create()
        report = factories.collection.create(grant=grant)
        user = factories.user.create()

        column_mappings = [
            DataSetColumnMapping(
                column_name="Capital allocation",
                data_type=QuestionDataType.NUMBER,
                number_type=NumberTypeEnum.INTEGER,
            ),
        ]
        all_rows = [
            {"ONS code": "E123", "Grant recipient": "Rivendell", "Capital allocation": "500000"},
            {"ONS code": "E456", "Grant recipient": "Lothlorien", "Capital allocation": "300000"},
        ]

        data_source = create_uploaded_data_source(
            name="Test GR Data Set",
            data_source_type=DataSourceType.GRANT_RECIPIENT,
            grant_id=grant.id,
            collection_id=report.id,
            column_mappings=column_mappings,
            all_rows=all_rows,
            user=user,
        )

        assert data_source.id is not None
        assert data_source.name == "Test GR Data Set"
        assert data_source.type == DataSourceType.GRANT_RECIPIENT
        assert data_source.grant_id == grant.id
        assert data_source.collection_id == report.id

        from_db = db_session.get(DataSource, data_source.id)
        assert from_db is not None

    def test_creates_schema(self, db_session, factories):
        grant = factories.grant.create()
        report = factories.collection.create(grant=grant)
        user = factories.user.create()

        column_mappings = [
            DataSetColumnMapping(
                column_name="Capital allocation",
                data_type=QuestionDataType.NUMBER,
                number_type=NumberTypeEnum.INTEGER,
                prefix="£",
            ),
            DataSetColumnMapping(
                column_name="Additional info",
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
            ),
        ]
        all_rows = [
            {
                "ONS code": "E123",
                "Grant recipient": "Rivendell",
                "Capital allocation": "£500000",
                "Additional info": "Notes",
            },
        ]

        data_source = create_uploaded_data_source(
            name="Test Schema Data Set",
            data_source_type=DataSourceType.GRANT_RECIPIENT,
            grant_id=grant.id,
            collection_id=report.id,
            column_mappings=column_mappings,
            all_rows=all_rows,
            user=user,
        )

        schema = data_source.schema
        assert "capital-allocation" in schema
        assert schema["capital-allocation"]["data_type"] == QuestionDataType.NUMBER
        assert schema["capital-allocation"]["original_column_name"] == "Capital allocation"
        assert "additional-info" in schema
        assert schema["additional-info"]["data_type"] == QuestionDataType.TEXT_SINGLE_LINE

    def test_creates_organisation_items_one_per_grant_recipient(self, db_session, factories):
        grant = factories.grant.create()
        report = factories.collection.create(grant=grant)
        user = factories.user.create()

        column_mappings = [
            DataSetColumnMapping(
                column_name="Capital allocation",
                data_type=QuestionDataType.NUMBER,
                number_type=NumberTypeEnum.INTEGER,
            ),
        ]
        all_rows = [
            {"ONS code": "E123", "Grant recipient": "Rivendell", "Capital allocation": "500000"},
            {"ONS code": "E456", "Grant recipient": "Lothlorien", "Capital allocation": "300000"},
        ]

        data_source = create_uploaded_data_source(
            name="Test GR Data Set",
            data_source_type=DataSourceType.GRANT_RECIPIENT,
            grant_id=grant.id,
            collection_id=report.id,
            column_mappings=column_mappings,
            all_rows=all_rows,
            user=user,
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
        report = factories.collection.create(grant=grant)
        user = factories.user.create()

        column_mappings = [
            DataSetColumnMapping(
                column_name="Capital allocation",
                data_type=QuestionDataType.NUMBER,
                number_type=NumberTypeEnum.INTEGER,
            ),
            DataSetColumnMapping(
                column_name="Description",
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
            ),
        ]
        all_rows = [
            {
                "ONS code": "E123",
                "Grant recipient": "Rivendell",
                "Capital allocation": "500000",
                "Description": "A fine place",
            },
        ]

        data_source = create_uploaded_data_source(
            name="Test GR Blob",
            data_source_type=DataSourceType.GRANT_RECIPIENT,
            grant_id=grant.id,
            collection_id=report.id,
            column_mappings=column_mappings,
            all_rows=all_rows,
            user=user,
        )

        org_item = db_session.query(DataSourceOrganisationItem).filter_by(data_source_id=data_source.id).one()
        assert isinstance(org_item.data, dict)
        assert org_item.data["capital-allocation"] == 500000
        assert org_item.data["description"] == "A fine place"

    def test_cleans_prefix_and_suffix_from_number_values(self, db_session, factories):
        grant = factories.grant.create()
        report = factories.collection.create(grant=grant)
        user = factories.user.create()

        column_mappings = [
            DataSetColumnMapping(
                column_name="Amount",
                data_type=QuestionDataType.NUMBER,
                number_type=NumberTypeEnum.DECIMAL,
                prefix="£",
                suffix="m",
                max_decimal_places=2,
            ),
        ]
        all_rows = [
            {"ONS code": "E123", "Grant recipient": "Rivendell", "Amount": "£1.50m"},
        ]

        data_source = create_uploaded_data_source(
            name="Test Clean Values",
            data_source_type=DataSourceType.GRANT_RECIPIENT,
            grant_id=grant.id,
            collection_id=report.id,
            column_mappings=column_mappings,
            all_rows=all_rows,
            user=user,
        )

        org_item = db_session.query(DataSourceOrganisationItem).filter_by(data_source_id=data_source.id).one()
        assert org_item.data["amount"] == "1.50"

    def test_excludes_identifier_columns_from_data_blob(self, db_session, factories):
        grant = factories.grant.create()
        report = factories.collection.create(grant=grant)
        user = factories.user.create()

        column_mappings = [
            DataSetColumnMapping(
                column_name="Capital allocation",
                data_type=QuestionDataType.NUMBER,
                number_type=NumberTypeEnum.INTEGER,
            ),
        ]
        all_rows = [
            {"ONS code": "E123", "Grant recipient": "Rivendell", "Capital allocation": "500000"},
        ]

        data_source = create_uploaded_data_source(
            name="Test Exclude Identifiers",
            data_source_type=DataSourceType.GRANT_RECIPIENT,
            grant_id=grant.id,
            collection_id=report.id,
            column_mappings=column_mappings,
            all_rows=all_rows,
            user=user,
        )

        org_item = db_session.query(DataSourceOrganisationItem).filter_by(data_source_id=data_source.id).one()
        assert "ons-code" not in org_item.data
        assert "grant-recipient" not in org_item.data

    def test_empty_string_values_saved_as_empty_string(self, db_session, factories):
        grant = factories.grant.create()
        report = factories.collection.create(grant=grant)
        user = factories.user.create()

        column_mappings = [
            DataSetColumnMapping(
                column_name="Notes",
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
            ),
        ]
        all_rows = [
            {"ONS code": "E123", "Grant recipient": "Rivendell", "Notes": ""},
        ]

        data_source = create_uploaded_data_source(
            name="Test Empty Values",
            data_source_type=DataSourceType.GRANT_RECIPIENT,
            grant_id=grant.id,
            collection_id=report.id,
            column_mappings=column_mappings,
            all_rows=all_rows,
            user=user,
        )

        org_item = db_session.query(DataSourceOrganisationItem).filter_by(data_source_id=data_source.id).one()
        assert org_item.data["notes"] == ""


class TestCreateUploadedDataSourceProjectLevel:
    def test_creates_organisation_items_grouped_by_external_id(self, db_session, factories):
        grant = factories.grant.create()
        report = factories.collection.create(grant=grant)
        user = factories.user.create()

        column_mappings = [
            DataSetColumnMapping(
                column_name="Project name",
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
            ),
            DataSetColumnMapping(
                column_name="Allocation",
                data_type=QuestionDataType.NUMBER,
                number_type=NumberTypeEnum.INTEGER,
            ),
        ]
        all_rows = [
            {"ONS code": "E123", "Grant recipient": "Rivendell", "Project name": "Roads", "Allocation": "5"},
            {"ONS code": "E123", "Grant recipient": "Rivendell", "Project name": "Trees", "Allocation": "10"},
            {"ONS code": "E456", "Grant recipient": "Lothlorien", "Project name": "Bridges", "Allocation": "15"},
        ]

        data_source = create_uploaded_data_source(
            name="Test PL Data Set",
            data_source_type=DataSourceType.PROJECT_LEVEL,
            grant_id=grant.id,
            collection_id=report.id,
            column_mappings=column_mappings,
            all_rows=all_rows,
            user=user,
        )

        org_items = (
            db_session.query(DataSourceOrganisationItem)
            .filter_by(data_source_id=data_source.id)
            .order_by(DataSourceOrganisationItem.external_id)
            .all()
        )

        assert len(org_items) == 2

    def test_data_blob_is_list_for_project_level(self, db_session, factories):
        grant = factories.grant.create()
        report = factories.collection.create(grant=grant)
        user = factories.user.create()

        column_mappings = [
            DataSetColumnMapping(
                column_name="Project name",
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
            ),
            DataSetColumnMapping(
                column_name="Allocation",
                data_type=QuestionDataType.NUMBER,
                number_type=NumberTypeEnum.INTEGER,
            ),
        ]
        all_rows = [
            {"ONS code": "E123", "Grant recipient": "Rivendell", "Project name": "Roads", "Allocation": "5"},
            {"ONS code": "E123", "Grant recipient": "Rivendell", "Project name": "Trees", "Allocation": "10"},
        ]

        data_source = create_uploaded_data_source(
            name="Test PL Blob",
            data_source_type=DataSourceType.PROJECT_LEVEL,
            grant_id=grant.id,
            collection_id=report.id,
            column_mappings=column_mappings,
            all_rows=all_rows,
            user=user,
        )

        org_item = db_session.query(DataSourceOrganisationItem).filter_by(data_source_id=data_source.id).one()
        assert isinstance(org_item.data, list)
        assert len(org_item.data) == 2
        assert org_item.data[0]["project-name"] == "Roads"
        assert org_item.data[0]["allocation"] == 5
        assert org_item.data[1]["project-name"] == "Trees"
        assert org_item.data[1]["allocation"] == 10

    def test_single_row_per_grant_recipient_is_still_list(self, db_session, factories):
        grant = factories.grant.create()
        report = factories.collection.create(grant=grant)
        user = factories.user.create()

        column_mappings = [
            DataSetColumnMapping(
                column_name="Project name",
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
            ),
        ]
        all_rows = [
            {"ONS code": "E123", "Grant recipient": "Rivendell", "Project name": "Roads"},
        ]

        data_source = create_uploaded_data_source(
            name="Test PL Single",
            data_source_type=DataSourceType.PROJECT_LEVEL,
            grant_id=grant.id,
            collection_id=report.id,
            column_mappings=column_mappings,
            all_rows=all_rows,
            user=user,
        )

        org_item = db_session.query(DataSourceOrganisationItem).filter_by(data_source_id=data_source.id).one()
        assert isinstance(org_item.data, list)
        assert len(org_item.data) == 1


class TestCreateUploadedDataSourceStatic:
    def test_creates_data_source_items(self, db_session, factories):
        grant = factories.grant.create()
        report = factories.collection.create(grant=grant)
        user = factories.user.create()

        column_mappings = [
            DataSetColumnMapping(
                column_name="Code",
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
            ),
            DataSetColumnMapping(
                column_name="Label",
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
            ),
        ]
        all_rows = [
            {"Code": "UK", "Label": "United Kingdom"},
            {"Code": "FR", "Label": "France"},
            {"Code": "DE", "Label": "Germany"},
        ]

        data_source = create_uploaded_data_source(
            name="Test Static Data Set",
            data_source_type=DataSourceType.STATIC,
            grant_id=grant.id,
            collection_id=report.id,
            column_mappings=column_mappings,
            all_rows=all_rows,
            user=user,
        )

        assert data_source.type == DataSourceType.STATIC

        items = (
            db_session.query(DataSourceItem)
            .filter_by(data_source_id=data_source.id)
            .order_by(DataSourceItem.order)
            .all()
        )

        assert len(items) == 3
        assert items[0].key == "UK"
        assert items[0].label == "United Kingdom"
        assert items[0].order == 0
        assert items[1].key == "FR"
        assert items[1].label == "France"
        assert items[1].order == 1
        assert items[2].key == "DE"
        assert items[2].label == "Germany"
        assert items[2].order == 2

    def test_no_organisation_items_created_for_static(self, db_session, factories):
        grant = factories.grant.create()
        report = factories.collection.create(grant=grant)
        user = factories.user.create()

        column_mappings = [
            DataSetColumnMapping(column_name="Code", data_type=QuestionDataType.TEXT_SINGLE_LINE),
            DataSetColumnMapping(column_name="Label", data_type=QuestionDataType.TEXT_SINGLE_LINE),
        ]
        all_rows = [{"Code": "UK", "Label": "United Kingdom"}]

        data_source = create_uploaded_data_source(
            name="Test Static No Org Items",
            data_source_type=DataSourceType.STATIC,
            grant_id=grant.id,
            collection_id=report.id,
            column_mappings=column_mappings,
            all_rows=all_rows,
            user=user,
        )

        org_items = db_session.query(DataSourceOrganisationItem).filter_by(data_source_id=data_source.id).all()
        assert len(org_items) == 0

    def test_raises_error_for_wrong_number_of_columns(self, db_session, factories):
        grant = factories.grant.create()
        report = factories.collection.create(grant=grant)
        user = factories.user.create()

        column_mappings = [
            DataSetColumnMapping(column_name="Code", data_type=QuestionDataType.TEXT_SINGLE_LINE),
            DataSetColumnMapping(column_name="Label", data_type=QuestionDataType.TEXT_SINGLE_LINE),
            DataSetColumnMapping(column_name="Extra", data_type=QuestionDataType.TEXT_SINGLE_LINE),
        ]
        all_rows = [{"Code": "UK", "Label": "United Kingdom", "Extra": "foo"}]

        with pytest.raises(ValueError, match="STATIC data sources must have exactly two columns"):
            create_uploaded_data_source(
                name="Test Static Wrong Columns",
                data_source_type=DataSourceType.STATIC,
                grant_id=grant.id,
                collection_id=report.id,
                column_mappings=column_mappings,
                all_rows=all_rows,
                user=user,
            )


class TestCreateUploadedDataSourceUnsupportedType:
    def test_raises_error_for_unsupported_type(self, db_session, factories):
        grant = factories.grant.create()
        report = factories.collection.create(grant=grant)
        user = factories.user.create()

        with pytest.raises(ValueError, match="Unsupported data source type"):
            create_uploaded_data_source(
                name="Test Unsupported",
                data_source_type=DataSourceType.CUSTOM,
                grant_id=grant.id,
                collection_id=report.id,
                column_mappings=[],
                all_rows=[],
                user=user,
            )


class TestCreateUploadedDataSourceSchemaOptions:
    def test_number_columns_have_presentation_and_data_options(self, db_session, factories):
        grant = factories.grant.create()
        report = factories.collection.create(grant=grant)
        user = factories.user.create()

        column_mappings = [
            DataSetColumnMapping(
                column_name="Amount",
                data_type=QuestionDataType.NUMBER,
                number_type=NumberTypeEnum.DECIMAL,
                prefix="£",
                suffix="",
                max_decimal_places=2,
            ),
        ]
        all_rows = [
            {"ONS code": "E123", "Grant recipient": "Rivendell", "Amount": "£100.50"},
        ]

        data_source = create_uploaded_data_source(
            name="Test Schema Options",
            data_source_type=DataSourceType.GRANT_RECIPIENT,
            grant_id=grant.id,
            collection_id=report.id,
            column_mappings=column_mappings,
            all_rows=all_rows,
            user=user,
        )

        schema_col = data_source.schema["amount"]
        assert schema_col["presentation_options"]["prefix"] == "£"
        assert schema_col["presentation_options"]["suffix"] == ""
        assert schema_col["data_options"]["number_type"] == NumberTypeEnum.DECIMAL
        assert schema_col["data_options"]["max_decimal_places"] == 2

    def test_text_columns_have_empty_presentation_and_data_options(self, db_session, factories):
        grant = factories.grant.create()
        report = factories.collection.create(grant=grant)
        user = factories.user.create()

        column_mappings = [
            DataSetColumnMapping(
                column_name="Description",
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
            ),
        ]
        all_rows = [
            {"ONS code": "E123", "Grant recipient": "Rivendell", "Description": "Notes"},
        ]

        data_source = create_uploaded_data_source(
            name="Test Text Schema",
            data_source_type=DataSourceType.GRANT_RECIPIENT,
            grant_id=grant.id,
            collection_id=report.id,
            column_mappings=column_mappings,
            all_rows=all_rows,
            user=user,
        )

        schema_col = data_source.schema["description"]
        assert schema_col["data_type"] == QuestionDataType.TEXT_SINGLE_LINE
        assert schema_col["original_column_name"] == "Description"

    def test_schema_keys_are_slugified(self, db_session, factories):
        grant = factories.grant.create()
        report = factories.collection.create(grant=grant)
        user = factories.user.create()

        column_mappings = [
            DataSetColumnMapping(
                column_name="Capital Allocation (£)",
                data_type=QuestionDataType.NUMBER,
                number_type=NumberTypeEnum.INTEGER,
            ),
        ]
        all_rows = [
            {"ONS code": "E123", "Grant recipient": "Rivendell", "Capital Allocation (£)": "500000"},
        ]

        data_source = create_uploaded_data_source(
            name="Test Slugified Keys",
            data_source_type=DataSourceType.GRANT_RECIPIENT,
            grant_id=grant.id,
            collection_id=report.id,
            column_mappings=column_mappings,
            all_rows=all_rows,
            user=user,
        )

        assert "capital-allocation" in data_source.schema
        assert "Capital Allocation (£)" not in data_source.schema


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
        data_source = factories.data_source.create(items=None)
        factories.data_source_organisation_item.create(data_source=data_source, external_id="E123")
        factories.data_source_organisation_item.create(data_source=data_source, external_id="E456")
        db_session.expire_all()

        from_db = get_data_source(data_source.id, with_organisation_items=True)

        with track_sql_queries() as queries:
            items = from_db.organisation_items
            assert len(items) == 2

        assert len(queries) == 0

    def test_get_data_source_with_data_source_items(self, db_session, factories, track_sql_queries):
        data_source = factories.data_source.create()
        db_session.expire_all()

        from_db = get_data_source(data_source.id, with_data_source_items=True)

        with track_sql_queries() as queries:
            items = from_db.items
            assert len(items) == 3

        assert len(queries) == 0

    def test_get_data_source_with_both_flags(self, db_session, factories, track_sql_queries):
        data_source = factories.data_source.create(items=None)
        factories.data_source_organisation_item.create(data_source=data_source, external_id="E123")
        db_session.expire_all()

        from_db = get_data_source(data_source.id, with_organisation_items=True, with_data_source_items=True)

        with track_sql_queries() as queries:
            assert len(from_db.organisation_items) == 1
            assert len(from_db.items) == 0

        assert len(queries) == 0

    def test_get_data_source_without_flags_does_not_eagerly_load_items(self, db_session, factories, track_sql_queries):
        data_source = factories.data_source.create(items=None)
        factories.data_source_organisation_item.create(data_source=data_source, external_id="E123")
        db_session.expire_all()

        get_data_source(data_source.id)

        with track_sql_queries() as queries:
            _ = db_session.get(DataSource, data_source.id).organisation_items
        assert len(queries) > 0


class TestDeleteDataSource:
    def test_delete_data_source(self, db_session, factories):
        data_source = factories.data_source.create()
        assert db_session.scalar(select(func.count()).select_from(DataSourceItem)) == 3

        delete_data_source(data_source)
        db_session.flush()

        assert db_session.get(DataSource, data_source.id) is None
        assert db_session.scalar(select(func.count()).select_from(DataSourceItem)) == 0
        assert db_session.scalar(select(func.count()).select_from(DataSourceOrganisationItem)) == 0

    def test_delete_data_source_cascades_organisation_items(self, db_session, factories):
        data_source = factories.data_source.create(items=None)
        factories.data_source_organisation_item.create(data_source=data_source, external_id="E123")
        factories.data_source_organisation_item.create(data_source=data_source, external_id="E456")

        delete_data_source(data_source)
        db_session.flush()

        assert db_session.scalar(select(func.count()).select_from(DataSourceOrganisationItem)) == 0

    def test_delete_only_deletes_target_data_source(self, db_session, factories):
        data_source_1 = factories.data_source.create(items=None)
        data_source_2 = factories.data_source.create(items=None)
        org_item_1 = factories.data_source_organisation_item.create(data_source=data_source_1, external_id="E123")
        org_item_2 = factories.data_source_organisation_item.create(data_source=data_source_2, external_id="E456")

        delete_data_source(data_source_1)
        db_session.flush()

        assert db_session.get(DataSource, data_source_1.id) is None
        assert db_session.get(DataSource, data_source_2.id) is not None

        assert db_session.scalar(select(func.count()).select_from(DataSourceOrganisationItem)) == 1
        assert db_session.get(DataSourceOrganisationItem, org_item_1.id) is None
        assert db_session.get(DataSourceOrganisationItem, org_item_2.id) is not None
