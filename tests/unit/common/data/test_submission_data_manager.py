from unittest import mock

import pytest

from app import QuestionDataType
from app.common.collections.types import TextSingleLineAnswer
from app.common.data.submission_data_manager import SubmissionDataAddAnotherIndexInvalid, SubmissionDataManager
from tests.conftest import _Factories


class TestSubmissionDataManager:
    class TestGetAnswer:
        def test_returns_none_when_no_answer(self, factories: _Factories):
            question = factories.question.build()
            data = SubmissionDataManager({})

            assert data.get(question) is None

        def test_returns_answer_for_single_question(self, factories: _Factories):
            question = factories.question.build()
            data = SubmissionDataManager({str(question.id): "hello"})

            assert data.get(question) == TextSingleLineAnswer("hello")

        def test_returns_answer_for_add_another_question(self, factories: _Factories):
            group = factories.group.build(add_another=True)
            question = factories.question.build(form=group.form, parent=group)
            data = SubmissionDataManager({str(group.id): [{str(question.id): "entry0"}, {str(question.id): "entry1"}]})

            assert data.get(question, add_another_index=0) == TextSingleLineAnswer("entry0")
            assert data.get(question, add_another_index=1) == TextSingleLineAnswer("entry1")

        def test_returns_none_for_next_add_another_group(self, factories: _Factories):
            group = factories.group.build(add_another=True)
            question = factories.question.build(form=group.form, parent=group)
            data = SubmissionDataManager({})

            assert data.get(question, add_another_index=0) is None

        def test_raises_if_no_index_for_add_another_question(self, factories):
            group = factories.group.build(add_another=True)
            question = factories.question.build(form=group.form, parent=group)

            data = SubmissionDataManager({})
            with pytest.raises(SubmissionDataAddAnotherIndexInvalid) as e:
                data.get(question)
            assert str(e.value) == "add_another_index must be provided for questions within an add another container"

        def test_raises_for_beyond_next_add_another_group(self, factories):
            group = factories.group.build(add_another=True)
            question = factories.question.build(form=group.form, parent=group)

            data = SubmissionDataManager({})
            data.get(question, add_another_index=0)
            with pytest.raises(SubmissionDataAddAnotherIndexInvalid) as e:
                data.get(question, add_another_index=1)
            assert str(e.value) == "no add another entry exists at this index"

    class TestSetAnswer:
        def test_sets_single_question_answer(self, factories: _Factories):
            question = factories.question.build()
            data = SubmissionDataManager({})

            data.set(question, TextSingleLineAnswer("hello"))

            assert data.get(question) == TextSingleLineAnswer("hello")

        def test_overwrites_existing_answer(self, factories: _Factories):
            question = factories.question.build()
            data = SubmissionDataManager({str(question.id): "old"})

            data.set(question, TextSingleLineAnswer("new"))

            assert data.get(question) == TextSingleLineAnswer("new")

        def test_sets_add_another_answer_at_existing_index(self, factories: _Factories):
            group = factories.group.build(add_another=True)
            question = factories.question.build(form=group.form, parent=group)
            data = SubmissionDataManager({str(group.id): [{}]})

            data.set(question, TextSingleLineAnswer("value"), add_another_index=0)

            assert data.get(question, add_another_index=0) == TextSingleLineAnswer("value")

        def test_appends_new_add_another_entry(self, factories: _Factories):
            group = factories.group.build(add_another=True)
            question = factories.question.build(form=group.form, parent=group)
            data = SubmissionDataManager({str(group.id): []})

            data.set(question, TextSingleLineAnswer("first"), add_another_index=0)

            assert data.get(question, add_another_index=0) == TextSingleLineAnswer("first")
            assert data.get_count_for_add_another(group) == 1

        def test_update_submission_data_validates_add_another_index_when_not_in_add_another(
            self, db_session, factories
        ):
            form = factories.form.build()
            question = factories.question.build(form=form)
            with pytest.raises(ValueError) as error:
                SubmissionDataManager({}).set(
                    question, TextSingleLineAnswer("User submitted data"), add_another_index=1
                )
            assert (
                str(error.value)
                == "add_another_index cannot be provided for questions not within an add another container"
            )

        def test_update_submission_data_validates_add_another_index_when_in_add_another(self, db_session, factories):
            form = factories.form.build()
            question = factories.question.build(form=form, add_another=True)
            with pytest.raises(ValueError) as error:
                SubmissionDataManager({}).set(
                    question, TextSingleLineAnswer("User submitted data"), add_another_index=None
                )
            assert (
                str(error.value) == "add_another_index must be provided for questions within an add another container"
            )

        def test_update_submission_data_add_another_fail_if_index_not_available(self, db_session, factories):
            form = factories.form.build()
            group = factories.group.build(form=form, add_another=True)
            question1 = factories.question.build(form=form, parent=group)
            question2 = factories.question.build(form=form, parent=group)
            q1_data1 = TextSingleLineAnswer("Group 1 - Question 1 - Answer 1")

            data_manager = SubmissionDataManager({})

            with pytest.raises(ValueError) as e:
                data_manager.set(question2, q1_data1, add_another_index=1)
            assert str(e.value) == "Cannot update answers at index 1 as there are only 0 existing answers"

            with pytest.raises(ValueError) as e:
                data_manager.set(question2, q1_data1, add_another_index=-1)
            assert str(e.value) == "Cannot update answers at index -1 as there are only 0 existing answers"

            data_manager.set(question1, q1_data1, add_another_index=0)
            entries = data_manager.data[str(group.id)]
            assert len(entries) == 1
            assert entries[0]["answers"] == {str(question1.id): "Group 1 - Question 1 - Answer 1"}

            q2_data1 = TextSingleLineAnswer("Group 1 - Question 2 - Answer 1")

            with pytest.raises(ValueError) as e:
                data_manager.set(question2, q2_data1, add_another_index=2)
            assert str(e.value) == "Cannot update answers at index 2 as there are only 1 existing answers"

    class TestRemoveAnswer:
        def test_removes_single_question_answer(self, factories: _Factories):
            question = factories.question.build(data_type=QuestionDataType.FILE_UPLOAD)
            mock_answer = mock.Mock()
            data = SubmissionDataManager({str(question.id): mock_answer})

            data.remove(question)

            assert data.get(question) is None

        def test_noop_when_answer_does_not_exist(self, factories: _Factories):
            question = factories.question.build(data_type=QuestionDataType.FILE_UPLOAD)
            data = SubmissionDataManager({})

            data.remove(question)

            assert data.get(question) is None

        def test_removes_add_another_answer(self, factories: _Factories):
            group = factories.group.build(add_another=True)
            question = factories.question.build(data_type=QuestionDataType.FILE_UPLOAD, form=group.form, parent=group)
            mock_answer = mock.Mock()
            data = SubmissionDataManager({str(group.id): [{str(question.id): mock_answer}]})

            data.remove(question, add_another_index=0)

            assert data.get(question, add_another_index=0) is None

        @pytest.mark.parametrize("data_type", QuestionDataType)
        def test_can_only_remove_file_answers(self, factories, data_type) -> None:
            question = factories.question.build(data_type=data_type)
            mock_answer = mock.Mock()
            data = SubmissionDataManager({str(question.id): mock_answer})

            if data_type != QuestionDataType.FILE_UPLOAD:
                with pytest.raises(ValueError):
                    data.remove(question)

            else:
                data.remove(question)

    class TestGetAddAnotherCount:
        def test_returns_zero_when_no_entries(self, factories: _Factories):
            group = factories.group.build(add_another=True)
            data = SubmissionDataManager({})

            assert data.get_count_for_add_another(group) == 0

        def test_returns_count(self, factories: _Factories):
            group = factories.group.build(add_another=True)
            question = factories.question.build(form=group.form, parent=group)
            data = SubmissionDataManager({str(group.id): [{str(question.id): "a"}, {str(question.id): "b"}]})

            assert data.get_count_for_add_another(group) == 2

    class TestRemoveAddAnotherEntry:
        def test_removes_entry_at_index(self, factories: _Factories):
            group = factories.group.build(add_another=True)
            question = factories.question.build(form=group.form, parent=group)
            data = SubmissionDataManager({str(group.id): [{str(question.id): "a"}, {str(question.id): "b"}]})

            data.remove_add_another_entry(group, add_another_index=0)

            assert data.get_count_for_add_another(group) == 1
            assert data.get(question, add_another_index=0) == TextSingleLineAnswer("b")

        def test_errors_removing_entry_that_doesnt_exist(self, factories: _Factories):
            group = factories.group.build(add_another=True)
            data = SubmissionDataManager({str(group.id): []})

            with pytest.raises(
                ValueError, match="Cannot remove answers at index 0 as there are only 0 existing answers"
            ):
                data.remove_add_another_entry(group, add_another_index=0)

    class TestEntryEnvelope:
        def test_set_wraps_new_entries_in_an_envelope(self, factories: _Factories):
            group = factories.group.build(add_another=True)
            question = factories.question.build(form=group.form, parent=group)
            data = SubmissionDataManager({str(group.id): []})

            data.set(question, TextSingleLineAnswer("value"), add_another_index=0)

            entries = data.data[str(group.id)]
            assert len(entries) == 1
            assert set(entries[0].keys()) == {"id", "answers"}
            assert isinstance(entries[0]["id"], str)
            assert entries[0]["answers"] == {str(question.id): "value"}

        def test_normalises_legacy_bare_dict_entries_on_load(self, factories: _Factories):
            group = factories.group.build(add_another=True)
            question = factories.question.build(form=group.form, parent=group)
            data = SubmissionDataManager({str(group.id): [{str(question.id): "entry0"}, {str(question.id): "entry1"}]})

            entries = data.get_entries(group)
            assert len(entries) == 2
            assert entries[0]["answers"] == {str(question.id): "entry0"}
            assert entries[1]["answers"] == {str(question.id): "entry1"}
            assert isinstance(entries[0]["id"], str)
            assert isinstance(entries[1]["id"], str)
            assert entries[0]["id"] != entries[1]["id"]

            # existing per-question reads still work through the normalised shape
            assert data.get(question, add_another_index=0) == TextSingleLineAnswer("entry0")

        def test_does_not_re_wrap_entries_already_in_envelope_shape(self, factories: _Factories):
            group = factories.group.build(add_another=True)
            question = factories.question.build(form=group.form, parent=group)
            data = SubmissionDataManager(
                {
                    str(group.id): [
                        {"id": "entry-id-0", "source_entry_id": "source-id-0", "answers": {str(question.id): "a"}}
                    ]
                }
            )

            entries = data.get_entries(group)
            assert entries == [
                {"id": "entry-id-0", "source_entry_id": "source-id-0", "answers": {str(question.id): "a"}}
            ]

        def test_get_entry_id_returns_stable_id(self, factories: _Factories):
            group = factories.group.build(add_another=True)
            question = factories.question.build(form=group.form, parent=group)
            data = SubmissionDataManager({str(group.id): [{str(question.id): "a"}]})

            entry_id = data.get_entry_id(group, add_another_index=0)
            assert entry_id == data.get_entries(group)[0]["id"]

        def test_index_for_source_entry_id(self, factories: _Factories):
            group = factories.group.build(add_another=True)
            data = SubmissionDataManager(
                {
                    str(group.id): [
                        {"id": "e0", "source_entry_id": "s0", "answers": {}},
                        {"id": "e1", "source_entry_id": "s1", "answers": {}},
                    ]
                }
            )

            assert data.index_for_source_entry_id(group, "s1") == 1
            assert data.index_for_source_entry_id(group, "missing") is None

        def test_append_entry_appends_empty_entry_and_returns_its_index(self, factories: _Factories):
            group = factories.group.build(add_another=True)
            data = SubmissionDataManager({})

            index = data.append_entry(group, source_entry_id="source-id")

            assert index == 0
            entries = data.get_entries(group)
            assert len(entries) == 1
            assert entries[0]["answers"] == {}
            assert entries[0]["source_entry_id"] == "source-id"
            assert isinstance(entries[0]["id"], str)

        def test_append_entry_without_source_entry_id(self, factories: _Factories):
            group = factories.group.build(add_another=True)
            data = SubmissionDataManager({str(group.id): [{"id": "e0", "answers": {}}]})

            index = data.append_entry(group)

            assert index == 1
            entries = data.get_entries(group)
            assert len(entries) == 2
            assert "source_entry_id" not in entries[1]
