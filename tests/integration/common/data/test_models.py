import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from app.common.data.models import CollectionSchema, Form, Grant, Question, Section
from app.common.data.models_user import User


class TestCollectionSchema:
    def test_deleting_collection_schema_is_blocked_through_orm_if_collections_exist(self, db_session, factories):
        """
        If any collections exist, deleting a collection schema should fail. We should need to explicitly code in
        deleting the collections to make it very clear that we are intentionally dropping submitted data.

        When using `db_session.delete` and passing an instance, the ORM itself (python code) has logic to run through
        any related objects and delete them. We want to make sure the ORM does not do that automatically - we should
        do this explicitly if we want to.
        """
        collection = factories.collection.create()
        schema = collection.collection_schema

        with pytest.raises(IntegrityError) as e:
            db_session.delete(schema)
            db_session.commit()

        assert (
            '(psycopg.errors.NotNullViolation) null value in column "collection_schema_id" of relation "collection" violates not-null constraint'
            in str(e.value)
        )

    def test_deleting_collection_schema_is_blocked_through_db_if_collections_exist(self, db_session, factories):
        """
        If any collections exist, deleting a collection schema should fail. We should need to explicitly code in
        deleting the collections to make it very clear that we are intentionally dropping submitted data.

        This test checks that directly-executed SQL queries (which bypass the ORM layer) are still unable to delete
        collection schemas if they have related collections. The DB should not cascade this automatically for us, and
        we should deal with it explicitly.
        """
        collection = factories.collection.create()
        schema = collection.collection_schema

        with pytest.raises(IntegrityError) as e:
            db_session.execute(delete(CollectionSchema).where(CollectionSchema.id == schema.id))
            db_session.commit()

        assert (
            'update or delete on table "collection_schema" violates foreign key constraint "fk_collection_collection_schema_id_collection_schema"'
            in str(e.value)
        )

    def test_deleting_collection_schema_cascades_to_sections_forms_and_questions(self, db_session, factories):
        """
        If we're explicitly deleting a collection schema, then we're OK with automatically cascading deletes down into
        the schema that defines that collection: its sections, forms and questions.
        """
        question = factories.question.create()
        question_id, form_id, section_id = question.id, question.form_id, question.form.section_id
        schema = question.form.section.collection_schema

        db_session.delete(schema)
        db_session.commit()

        assert db_session.get(Question, question_id) is None
        assert db_session.get(Form, form_id) is None
        assert db_session.get(Section, section_id) is None


class TestSection:
    def test_reordering_sections_in_a_collection_schema_does_not_trigger_sqlalchemy_cascade_delete_orphan(
        self, db_session, factories
    ):
        """
        If the `delete-orphan` rule is set on the `cascade` property of the `sections` relationship, then when
        we do reordering of sections (which removes them from the collection schema temporarily), sqlalchemy might
        automatically delete the section. We need that to not happen.
        :param db_session:
        :param factories:
        :return:
        """
        pass


class TestUser:
    def test_deleting_user_is_blocked_through_orm_if_magic_links_exist(self, db_session, factories):
        magic_link = factories.magic_link.create()
        user = magic_link.user

        with pytest.raises(IntegrityError) as e:
            db_session.delete(user)
            db_session.commit()

        assert (
            '(psycopg.errors.NotNullViolation) null value in column "user_id" of relation "magic_link" violates not-null constraint'
            in str(e.value)
        )

    def test_deleting_user_is_blocked_through_db_if_magic_link_exists(self, db_session, factories):
        magic_link = factories.magic_link.create()
        user = magic_link.user

        with pytest.raises(IntegrityError) as e:
            db_session.execute(delete(User).where(User.id == user.id))
            db_session.commit()

        assert (
            'update or delete on table "user" violates foreign key constraint "fk_magic_link_user_id_user" on table "magic_link"'
            in str(e.value)
        )


class TestGrant:
    def test_deleting_grant_is_blocked_through_orm_if_collection_schemas_exist(self, db_session, factories):
        schema = factories.collection_schema.create()
        grant = schema.grant

        with pytest.raises(IntegrityError) as e:
            db_session.delete(grant)
            db_session.commit()

        assert (
            '(psycopg.errors.NotNullViolation) null value in column "grant_id" of relation "collection_schema" violates not-null constraint'
            in str(e.value)
        )

    def test_deleting_user_is_blocked_through_db_if_magic_link_exists(self, db_session, factories):
        schema = factories.collection_schema.create()
        grant = schema.grant

        with pytest.raises(IntegrityError) as e:
            db_session.execute(delete(Grant).where(Grant.id == grant.id))
            db_session.commit()

        assert (
            'update or delete on table "grant" violates foreign key constraint "fk_collection_schema_grant_id_grant" on table "collection_schema"'
            in str(e.value)
        )
