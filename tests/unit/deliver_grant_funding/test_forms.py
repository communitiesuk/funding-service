from unittest import mock
from unittest.mock import patch

import pytest
from flask import Flask, request
from werkzeug.datastructures import MultiDict
from wtforms import ValidationError

from app.common.data.types import QuestionDataType, QuestionPresentationOptions, RoleEnum
from app.common.helpers.collections import SubmissionHelper
from app.deliver_grant_funding.forms import (
    GrantAddUserForm,
    GrantGGISForm,
    GrantNameForm,
    QuestionForm,
    SelectDataSourceQuestionForm,
    _validate_no_blank_lines,
    _validate_no_duplicates,
    strip_string_if_not_empty,
)


class TestFilters:
    def test_strip_string_if_not_empty(self):
        assert strip_string_if_not_empty("  blah ") == "blah"


class TestValidators:
    def test_validate_no_blank_lines(self):
        _validate_no_blank_lines(mock.Mock(), mock.Mock(data="  blah  "))

        with pytest.raises(ValidationError):
            _validate_no_blank_lines(mock.Mock(), mock.Mock(data="    "))

    def test_validate_no_duplicates(self):
        _validate_no_duplicates(mock.Mock(), mock.Mock(data="a\nb\nc"))

        with pytest.raises(ValidationError):
            _validate_no_duplicates(mock.Mock(), mock.Mock(data="a\na\na"))


def test_grant_name_form_passes_when_name_does_not_exist():
    form = GrantNameForm()
    form.name.data = "New Grant"

    with patch("app.deliver_grant_funding.forms.grant_name_exists", return_value=False):
        assert form.validate() is True
        assert len(form.name.errors) == 0


def test_grant_name_form_fails_when_name_exists():
    form = GrantNameForm()
    form.name.data = "Existing Grant"

    with patch("app.deliver_grant_funding.forms.grant_name_exists", return_value=True):
        assert form.validate() is False
        assert "Grant name already in use" in form.name.errors


def test_grant_ggis_form_validates_when_no_selected(app: Flask):
    print(request)
    form = GrantGGISForm(data={"has_ggis": "no", "ggis_number": ""})

    # Should return True when "no" is selected and GGIS number can be empty
    assert form.validate() is True
    assert len(form.ggis_number.errors) == 0


def test_grant_ggis_form_validates_when_yes_selected_with_ggis_number(app: Flask):
    form = GrantGGISForm(data={"has_ggis": "yes", "ggis_number": "GGIS123456"})

    # Should return True when "yes" is selected and GGIS number is provided
    assert form.validate() is True
    assert len(form.ggis_number.errors) == 0


def test_grant_ggis_form_fails_when_yes_selected_and_empty(app: Flask):
    form = GrantGGISForm(data={"has_ggis": "yes", "ggis_number": ""})

    # Should return False when "yes" is selected but GGIS number is empty
    assert form.validate() is False
    assert "Enter your GGIS reference number" in form.ggis_number.errors


def test_user_already_in_grant_users(app: Flask, factories, mocker):
    grant = factories.grant.build(name="Test Grant")
    user = factories.user.build(email="test.user@communities.gov.uk")
    factories.user_role.build(user=user, role=RoleEnum.MEMBER, organisation=grant.organisation, grant=grant)
    mocker.patch("app.common.auth.authorisation_helper.get_grant", return_value=grant)

    form = GrantAddUserForm(grant=grant)
    form.user_email.data = "test.admin@communities.gov.uk"

    with (
        patch("app.deliver_grant_funding.forms.get_user_by_email", return_value=user),
    ):
        assert form.validate() is False
        assert "already is a member of" in form.user_email.errors[0]


def test_user_already_platform_admin(app: Flask, factories):
    grant = factories.grant.build(name="Test")
    user = factories.user.build(email="test.user@communities.gov.uk")
    factories.user_role.build(user=user, role=RoleEnum.ADMIN)

    form = GrantAddUserForm(grant=grant)
    form.user_email.data = "test.admin@communities.gov.uk"

    with patch("app.deliver_grant_funding.forms.get_user_by_email", return_value=user):
        assert form.validate() is False
        assert 'This user already is an admin of "Test" so you cannot add them' in form.user_email.errors[0]


class TestQuestionForm:
    def test_max_data_source_items_radios(self, app):
        max_data_source_items = app.config["MAX_DATA_SOURCE_ITEMS_RADIOS"]
        form = QuestionForm(question_type=QuestionDataType.RADIOS)

        formdata = MultiDict(
            [
                ("text", "question"),
                ("hint", ""),
                ("name", "name"),
                ("data_source_items", "\n".join(str(x) for x in range(max_data_source_items))),
            ]
        )

        form.process(formdata)

        assert form.validate() is True
        assert form.errors == {}

    def test_too_many_data_source_items_radios(self, app):
        max_data_source_items = app.config["MAX_DATA_SOURCE_ITEMS_RADIOS"]
        form = QuestionForm(question_type=QuestionDataType.RADIOS)

        formdata = MultiDict(
            [
                ("text", "question"),
                ("hint", ""),
                ("name", "name"),
                ("data_source_items", "\n".join(str(x) for x in range(max_data_source_items + 1))),
            ]
        )

        form.process(formdata)

        assert form.validate() is False
        assert form.errors == {
            "data_source_items": [f"You have entered too many options. The maximum is {max_data_source_items}"]
        }

    def test_max_data_source_items_checkboxes(self, app):
        max_data_source_items = app.config["MAX_DATA_SOURCE_ITEMS_CHECKBOXES"]
        form = QuestionForm(question_type=QuestionDataType.CHECKBOXES)

        formdata = MultiDict(
            [
                ("text", "question"),
                ("hint", ""),
                ("name", "name"),
                ("data_source_items", "\n".join(str(x) for x in range(max_data_source_items))),
            ]
        )

        form.process(formdata)

        assert form.validate() is True
        assert form.errors == {}

    def test_too_many_data_source_items_checkboxes(self, app):
        max_data_source_items = app.config["MAX_DATA_SOURCE_ITEMS_CHECKBOXES"]
        form = QuestionForm(question_type=QuestionDataType.CHECKBOXES)

        formdata = MultiDict(
            [
                ("text", "question"),
                ("hint", ""),
                ("name", "name"),
                ("data_source_items", "\n".join(str(x) for x in range(max_data_source_items + 1))),
            ]
        )

        form.process(formdata)

        assert form.validate() is False
        assert form.errors == {
            "data_source_items": [f"You have entered too many options. The maximum is {max_data_source_items}"]
        }

    def test_prefixes_and_suffixes_blank_coerced_to_none(self, app):
        form = QuestionForm(question_type=QuestionDataType.INTEGER)

        formdata = MultiDict(
            [
                ("text", "question"),
                ("hint", ""),
                ("name", "name"),
                ("prefix", ""),
                ("suffix", "   "),
            ]
        )

        form.process(formdata)

        assert form.validate() is True
        assert form.prefix.data is None
        assert form.suffix.data is None

    def test_prefixes_and_suffixes_mutually_exclusive(self, app):
        form = QuestionForm(question_type=QuestionDataType.INTEGER)

        formdata = MultiDict(
            [
                ("text", "question"),
                ("hint", ""),
                ("name", "name"),
                ("prefix", "£"),
                ("suffix", "lbs"),
            ]
        )

        form.process(formdata)

        assert form.validate() is False
        assert form.errors == {
            "prefix": ["Remove the suffix if you need a prefix"],
            "suffix": ["Remove the prefix if you need a suffix"],
        }


class TestSelectDataSourceQuestionForm:
    def test_only_includes_earlier_questions_in_the_form_if_given_a_current_question(self, app, factories, mocker):
        questions = factories.question.build_batch(5, data_type=QuestionDataType.INTEGER)

        mocker.patch.object(questions[2].form, "cached_questions", questions)
        mocker.patch.object(questions[2].form, "cached_all_components", questions)

        form = SelectDataSourceQuestionForm(
            form=questions[2].form,
            interpolate=SubmissionHelper.get_interpolator(collection=questions[2].form.collection),
            current_component=questions[2],
        )

        assert len(form.question.choices) == 3
        # '' is the default "no answer" choice
        assert {q[0] for q in form.question.choices} == {"", str(questions[0].id), str(questions[1].id)}

    def test_questions_in_a_same_page_group_excluded(self, app, factories, mocker):
        group = factories.group.build(
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=False)
        )
        questions = factories.question.build_batch(5, parent=group, data_type=QuestionDataType.INTEGER)

        mocker.patch.object(questions[2].form, "cached_questions", questions)
        mocker.patch.object(questions[2].form, "cached_all_components", [group] + questions)

        form = SelectDataSourceQuestionForm(
            form=questions[2].form,
            interpolate=SubmissionHelper.get_interpolator(collection=questions[2].form.collection),
            current_component=questions[2],
        )

        assert len(form.question.choices) == 3
        # '' is the default "no answer" choice
        assert {q[0] for q in form.question.choices} == {"", str(questions[0].id), str(questions[1].id)}

        group.presentation_options.show_questions_on_the_same_page = True
        form = SelectDataSourceQuestionForm(
            form=questions[2].form,
            interpolate=SubmissionHelper.get_interpolator(collection=questions[2].form.collection),
            current_component=questions[2],
        )

        assert len(form.question.choices) == 0
        assert form.question.choices == []

    def test_show_all_question_datatypes_if_no_expression(self, app, factories, mocker):
        text_question = factories.question.build(data_type=QuestionDataType.TEXT_SINGLE_LINE)
        yes_no_question = factories.question.build(form=text_question.form, data_type=QuestionDataType.YES_NO)
        date_question = factories.question.build(form=text_question.form, data_type=QuestionDataType.DATE)
        integer_question = factories.question.build(form=text_question.form, data_type=QuestionDataType.INTEGER)

        all_questions = [text_question, yes_no_question, date_question, integer_question]

        mocker.patch.object(text_question.form, "cached_questions", all_questions)
        mocker.patch.object(text_question.form, "cached_all_components", all_questions)

        form = SelectDataSourceQuestionForm(
            form=text_question.form,
            interpolate=SubmissionHelper.get_interpolator(collection=text_question.form.collection),
            current_component=integer_question,
        )

        assert len(form.question.choices) == 4
        # '' is the default "no answer" choice
        assert {q[0] for q in form.question.choices} == {
            "",
            str(text_question.id),
            str(yes_no_question.id),
            str(date_question.id),
        }

    def test_expressions_reference_only_show_questions_of_same_datatype(self, app, factories, mocker):
        text_question = factories.question.build(data_type=QuestionDataType.TEXT_SINGLE_LINE)
        yes_no_question = factories.question.build(form=text_question.form, data_type=QuestionDataType.YES_NO)
        integer_questions = factories.question.build_batch(
            4, form=text_question.form, data_type=QuestionDataType.INTEGER
        )

        all_questions = [text_question, yes_no_question] + integer_questions

        mocker.patch.object(text_question.form, "cached_questions", all_questions)
        mocker.patch.object(text_question.form, "cached_all_components", all_questions)

        form = SelectDataSourceQuestionForm(
            form=text_question.form,
            interpolate=SubmissionHelper.get_interpolator(collection=text_question.form.collection),
            current_component=integer_questions[2],
            expression=True,
        )

        assert len(form.question.choices) == 3
        # '' is the default "no answer" choice
        assert {q[0] for q in form.question.choices} == {"", str(integer_questions[0].id), str(integer_questions[1].id)}

    def test_expressions_reference_exclude_same_page_groups_and_other_question_datatypes(self, app, factories, mocker):
        integer_q1 = factories.question.build(data_type=QuestionDataType.INTEGER)
        integer_q2 = factories.question.build(form=integer_q1.form, data_type=QuestionDataType.INTEGER)
        text_question = factories.question.build(form=integer_q1.form, data_type=QuestionDataType.TEXT_SINGLE_LINE)

        group = factories.group.build(
            form=integer_q1.form, presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True)
        )
        integer_q3 = factories.question.build(form=integer_q1.form, parent=group, data_type=QuestionDataType.INTEGER)
        integer_q4 = factories.question.build(form=integer_q1.form, parent=group, data_type=QuestionDataType.INTEGER)

        all_questions = [integer_q1, integer_q2, text_question, integer_q3, integer_q4]

        mocker.patch.object(group.form, "cached_questions", all_questions)
        mocker.patch.object(group.form, "cached_all_components", [group] + all_questions)

        form = SelectDataSourceQuestionForm(
            form=group.form,
            interpolate=SubmissionHelper.get_interpolator(collection=group.form.collection),
            current_component=integer_q4,
            expression=True,
        )

        assert len(form.question.choices) == 3
        assert {q[0] for q in form.question.choices} == {"", str(integer_q1.id), str(integer_q2.id)}
