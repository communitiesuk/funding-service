import uuid
from typing import Any, List
from uuid import UUID

from pydantic import UUID4
from slugify import slugify
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.models import (
    CollectionSchema,
    Form,
    Grant,
    Question,
    QuestionGroup,
    Section,
    User,
)
from app.common.data.types import DataType
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


def get_question_by_id_for_form_and_question(form_id: uuid.UUID, question_id: uuid.UUID) -> Question | None:
    return db.session.query(Question).filter(Question.form_id == form_id, Question.id == question_id).one_or_none()


def get_all_questions_with_higher_order_from_current(current_question) -> List[Question] | None:
    subsequent_questions = (
        db.session.query(Question)
        .filter(Question.form_id == current_question.form_id, Question.order > current_question.order)
        .order_by(Question.order)
        .all()
    )
    return subsequent_questions


def add_test_grant_schema() -> Question | None:
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

    schema = (
        db.session.query(CollectionSchema).filter_by(name="Community Ownership Funding Collection", version=1).first()
    )
    if schema:
        return None  # Data already exists, do nothing or handle update logic here

    schema = CollectionSchema(name="Community Ownership Funding Collection", version=1, created_by=user, grant=grant)

    # --- Section 1 ---
    section_1 = Section(title="Applicant information", order=1)
    form_1 = Form(title="Applicant information", order=1, slug=slugify("Applicant information"))
    # Single question examples
    form_1.questions.extend(
        [
            create_question(
                "Name of lead contact", "lead_contact_name", "Enter the full name of the lead contact", 1, DataType.TEXT
            ),
            create_question(
                "Lead contact job title",
                "lead_contact_job_title",
                "Enter the job title of the lead contact",
                2,
                DataType.TEXT,
            ),
            create_question(
                "Lead contact email address",
                "lead_contact_email",
                "Enter the email address of the lead contact",
                3,
                DataType.EMAIL,
            ),
            create_question(
                "Lead contact telephone number",
                "lead_contact_phone",
                "Enter the telephone number of the lead contact",
                4,
                DataType.PHONE_NUMBER,
            ),
        ]
    )

    # --- Section 2 ---
    section_2 = Section(title="Risk and deliverability", order=2)
    form_2 = Form(title="Risk and deliverability", order=1, slug=slugify("Risk and deliverability"))
    question_group = QuestionGroup(
        title="Your proposal risks", allow_add_another=True, show_all_on_same_page=False, item_limit=3
    )
    # Group question with add another
    form_2.questions.extend(
        [
            create_group_question(
                "Risk", "proposal_risk", "Describe a specific risk", 1, question_group, DataType.NUMBER
            ),
            create_group_question(
                "Likelihood", "proposal_likelihood", "What is the likelihood?", 2, question_group, DataType.NUMBER
            ),
            create_group_question(
                "Proposed mitigation",
                "proposal_mitigation",
                "How will you mitigate this risk?",
                3,
                question_group,
                DataType.TEXT,
            ),
        ]
    )

    # --- Section 3 ---
    section_3 = Section(title="Funding required", order=3)
    form_3 = Form(title="Funding required", order=1, slug=slugify("Funding required"))
    question_group_3 = QuestionGroup(
        title="Funding required", allow_add_another=False, show_all_on_same_page=True, item_limit=None
    )
    # Group question with logical group & show on same page
    form_3.questions.extend(
        [
            create_group_question(
                "Describe the cost",
                "cost",
                "Describe the cost",
                1,
                question_group_3,
                DataType.TEXT,
            ),
            create_group_question("Amount", "amount", "Amount", 2, question_group_3, DataType.NUMBER),
            create_group_question(
                "How much money from the COF grant will you use to pay for this cost?",
                "grant",
                "How much money from the COF grant will you use to pay for this cost?",
                3,
                question_group_3,
                DataType.TEXT,
            ),
        ]
    )

    # --- Section 4 ---
    section_4 = Section(title="About your organization", order=4)
    form_4 = Form(title="About your organization", order=1, slug=slugify("About your organization"))
    question_group_4 = QuestionGroup(
        title="About your organization", allow_add_another=False, show_all_on_same_page=True, item_limit=None
    )
    # Group question with logical group and normal questions
    form_4.questions.extend(
        [
            create_question("Organization name", "organization_name", "Enter the organization name", 1, DataType.TEXT),
            create_group_question(
                "Website and social media", "URL", "Website and social media", 2, question_group_4, DataType.URL
            ),
            create_group_question("Are you a human?", "amount", "Are you a human?", 3, question_group_4, DataType.TEXT),
            create_question(
                "Organization address", "organization_address", "Enter the organization address", 4, DataType.ADDRESS
            ),
        ]
    )

    # --- Final ---
    section_1.forms.append(form_1)
    section_2.forms.append(form_2)
    section_3.forms.append(form_3)
    section_4.forms.append(form_4)

    schema.sections.extend([section_1, section_2, section_3, section_4])
    db.session.add(schema)
    db.session.flush()

    schema = (
        db.session.query(CollectionSchema).filter_by(name="Community Ownership Funding Collection", version=1).first()
    )

    return {"schema": schema.id}


def create_question(title, name, hint, order, data_type):
    return Question(
        title=title,
        name=name,
        slug=slugify(name),
        hint=hint,
        data_source={},
        data_type=data_type,
        order=order,
    )


def create_group_question(title, name, hint, order, question_group, data_type):
    return Question(
        title=title,
        name=name,
        slug=slugify(name),
        hint=hint,
        data_source={},
        data_type=data_type,
        order=order,
        group=question_group,
    )
