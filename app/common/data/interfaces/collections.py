import uuid
from typing import Any
from uuid import UUID

from pydantic import UUID4
from slugify import slugify
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.models import (
    CollectionSchema,
    Condition,
    Form,
    Grant,
    Question,
    Section,
    Submission,
    User,
    Validation, QuestionGroup,
)
from app.common.data.types import DataType, ConditionType
from app.extensions import db


def create_collection_schema(*, name: str, user: User, grant: Grant, version: int = 1) -> CollectionSchema:
    schema = CollectionSchema(name=name, created_by=user, grant=grant, version=version, slug=slugify(name))
    db.session.add(schema)

    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return schema


def get_collection_schema(collection_id: UUID4) -> CollectionSchema:
    return db.session.get_one(CollectionSchema, collection_id)


def update_collection_schema(collection: CollectionSchema, *, name: str) -> CollectionSchema:
    collection.name = name
    collection.slug = slugify(name)
    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return collection


def create_section(*, title: str, collection_schema: CollectionSchema) -> Section:
    section = Section(title=title, collection_schema_id=collection_schema.id, slug=slugify(title))
    collection_schema.sections.append(section)
    db.session.add(section)
    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return section


def get_section_by_id(section_id: UUID) -> Section:
    return db.session.get_one(Section, section_id)


def update_section(section: Section, *, title: str) -> Section:
    section.title = title
    section.slug = slugify(title)

    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return section


def swap_elements_in_list_and_flush(containing_list: list[Any], index_a: int, index_b: int) -> list[Any]:
    """Swaps the elements at the specified indices in the supplied list.
    If either index is outside the valid range, returns the list unchanged.

    Args:
        containing_list (list): List containing the elements to swap
        index_a (int): List index (0-based) of the first element to swap
        index_b (int): List index (0-based) of the second element to swap

    Returns:
        list: The updated list
    """
    if 0 <= index_a < len(containing_list) and 0 <= index_b < len(containing_list):
        containing_list[index_a], containing_list[index_b] = containing_list[index_b], containing_list[index_a]
    db.session.execute(text("SET CONSTRAINTS uq_section_order_collection_schema, uq_form_order_section DEFERRED"))
    db.session.flush()
    return containing_list


def move_section_up(section: Section) -> Section:
    """Move a section up in the order, which means move it lower in the list."""
    swap_elements_in_list_and_flush(section.collection_schema.sections, section.order, section.order - 1)

    return section


def move_section_down(section: Section) -> Section:
    """Move a section down in the order, which means move it higher in the list."""
    swap_elements_in_list_and_flush(section.collection_schema.sections, section.order, section.order + 1)
    return section


def get_form_by_id(form_id: UUID4) -> Form:
    return db.session.get_one(Form, form_id)


def create_form(*, title: str, section: Section) -> Form:
    form = Form(title=title, section_id=section.id, slug=slugify(title))
    section.forms.append(form)
    db.session.add(form)

    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return form


def move_form_up(form: Form) -> Form:
    swap_elements_in_list_and_flush(form.section.forms, form.order, form.order - 1)
    return form


def move_form_down(form: Form) -> Form:
    swap_elements_in_list_and_flush(form.section.forms, form.order, form.order + 1)
    return form


def update_form(form: Form, *, title: str) -> Form:
    form.title = title
    form.slug = slugify(title)

    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return form


def update_form(form: Form, *, title: str) -> Form:
    form.title = title

    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return form


def get_question_by_id_for_schema(schema_id: uuid.UUID, question_id: uuid.UUID) -> Question | None:
    return (
        db.session.query(Question)
        .join(Question.form)
        .join(Form.section)
        .join(Section.collection_schema)
        .filter(CollectionSchema.id == schema_id, Question.id == question_id)
        .one_or_none()
    )


def add_data() -> Question | None:
    user = db.session.query(User).filter_by(email="nuwan.samarasinghe@communities.gov.uk").first()
    if not user:
        user = User(email="nuwan.samarasinghe@communities.gov.uk")
        db.session.add(user)
        db.session.flush()

    grant = db.session.query(Grant).filter_by(name="Community Ownership Fund").first()
    if not grant:
        grant = Grant(name="Community Ownership Fund")
        db.session.add(grant)
        db.session.flush()

    collection_schema = CollectionSchema(
        name="Community Ownership Funding Collection",
        version=1,
        created_by=user,
        grant=grant
    )

    section_1 = Section(title="Applicant information", order=1)
    form_1 = Form(title="Applicant information", order=1, slug=slugify("Applicant information"))
    form_2 = Form(title="Risk and deliverability", order=2, slug=slugify("Risk and deliverability"))

    # Questions with required fields
    question_1 = Question(
        title="Name of lead contact",
        name="lead_contact_name",
        slug=slugify("lead_contact_name"),
        hint="Enter the full name of the lead contact",
        data_source={},
        data_type=DataType.TEXT,
        order=1
    )

    question_2 = Question(
        title="Lead contact job title",
        name="lead_contact_job_title",
        slug=slugify("lead_contact_job_title"),
        hint="Enter the job title of the lead contact",
        data_source={},
        data_type=DataType.TEXT,
        order=2
    )

    question_3 = Question(
        title="Lead contact email address",
        name="lead_contact_email",
        slug=slugify("lead_contact_email"),
        hint="Enter the email address of the lead contact",
        data_source={},
        data_type=DataType.TEXT,
        order=3
    )

    question_4 = Question(
        title="Lead contact telephone number",
        name="lead_contact_phone",
        slug=slugify("lead_contact_phone"),
        hint="Enter the telephone number of the lead contact",
        data_source={},
        data_type=DataType.TEXT,
        order=4
    )

    # Validation with required fields
    validation_1 = Validation(
        expression="1=1",
        type=ConditionType.ANSWER_EQUALS,
        description="Always true validation",
        message="Sample Message",
        context="submission"
    )

    section_2 = Section(title="Risk and deliverability", order=2)
    question_g = QuestionGroup(title="Your proposal risks", allow_add_another=True, show_all_on_same_page=False,
                               item_limit=None)

    # Grouped Questions
    question_2_1 = Question(
        title="Risk",
        name="proposal_risk",
        slug=slugify("proposal_risk"),
        hint="Describe a specific risk",
        data_source={},
        data_type=DataType.TEXT,
        order=1,
        group=question_g
    )

    question_2_2 = Question(
        title="Likelihood",
        name="proposal_likelihood",
        slug=slugify("proposal_likelihood"),
        hint="What is the likelihood?",
        data_source={},
        data_type=DataType.TEXT,
        order=2,
        group=question_g
    )

    question_2_3 = Question(
        title="Proposed mitigation",
        name="proposal_mitigation",
        slug=slugify("proposal_mitigation"),
        hint="How will you mitigate this risk?",
        data_source={},
        data_type=DataType.TEXT,
        order=3,
        group=question_g
    )

    validation_2 = Validation(
        expression="1=1",
        type=ConditionType.ANSWER_EQUALS,
        description="Always true validation for group",
        message="Sample Message",
        context="submission"
    )

    # Attach validations
    for q in [question_1, question_2, question_3, question_4]:
        q.validations.append(validation_1)

    for q in [question_2_1, question_2_2, question_2_3]:
        q.validations.append(validation_2)

    # Add questions to forms
    form_1.questions.extend([question_1, question_2, question_3, question_4])
    form_2.questions.extend([question_2_1, question_2_2, question_2_3])

    # Add forms to sections
    section_1.forms.append(form_1)
    section_2.forms.append(form_2)

    # Add sections to schema
    collection_schema.sections.extend([section_1, section_2])

    # Final persist
    db.session.add(collection_schema)
