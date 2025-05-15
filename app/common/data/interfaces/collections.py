from typing import Any, List
from uuid import UUID

from pydantic import UUID4
from slugify import slugify
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, NoResultFound

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


def get_form_by_slug(form_slug: str) -> Form | None:
    stmt = select(Form).filter_by(slug=form_slug)
    try:
        return db.session.execute(stmt).scalar_one()
    except NoResultFound:
        return None


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


def get_question_by_id_for_form_and_question(form_slug: str, question_slug: str) -> Question | None:
    return (
        db.session.query(Question)
        .join(Question.form)
        .filter(Form.slug == form_slug)
        .filter(Question.slug == question_slug)
        .one_or_none()
    )


def get_all_questions_with_higher_order_from_current(current_question) -> List[Question] | None:
    subsequent_questions = (
        db.session.query(Question)
        .filter(Question.form_id == current_question.form_id, Question.order > current_question.order)
        .order_by(Question.order)
        .all()
    )
    return subsequent_questions


def add_test_grant_schema() -> Question | None:
    """Add a test grant schema to the database."""
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
        # Delete the existing schema
        db.session.delete(schema)
        db.session.flush()

    schema = CollectionSchema(name="Community Ownership Funding Collection", version=1, created_by=user, grant=grant)

    # --- Section 1 ---
    section_1 = Section(title="Applicant information", order=1)
    form_1 = Form(title="Applicant information", order=1, slug=slugify("Applicant information"))
    # Single question examples
    form_1.questions.extend(
        [
            Question(
                title="Name of lead contact",
                name="lead_contact_name",
                slug=slugify("lead_contact_name"),
                hint="Enter the full name of the lead contact",
                data_source={},
                data_type=DataType.TEXT,
                order=1,
            ),
            Question(
                title="Lead contact job title",
                name="lead_contact_job_title",
                slug=slugify("lead_contact_job_title"),
                hint="Enter the job title of the lead contact",
                data_source={},
                data_type=DataType.TEXT,
                order=2,
            ),
            Question(
                title="Lead contact email address",
                name="lead_contact_email",
                slug=slugify("lead_contact_email"),
                hint="Enter the email address of the lead contact",
                data_source={},
                data_type=DataType.EMAIL,
                order=3,
            ),
            Question(
                title="Lead contact telephone number",
                name="lead_contact_phone",
                slug=slugify("lead_contact_phone"),
                hint="Enter the telephone number of the lead contact",
                data_source={},
                data_type=DataType.PHONE_NUMBER,
                order=4,
            ),
        ]
    )

    # --- Section 2 ---
    section_2 = Section(title="Risk and deliverability", order=2)
    form_2 = Form(title="Risk and deliverability", order=1, slug=slugify("Risk and deliverability"))
    question_group = QuestionGroup(
        title="Your proposal risks",
        slug="your-proposal-risks",
        allow_add_another=True,
        show_all_on_same_page=False,
        item_limit=3,
        form=form_2,
    )
    # Group question with add another
    form_2.questions.extend(
        [
            Question(
                title="What is the risk?",
                name="proposal_risk",
                slug=slugify("proposal_risk"),
                hint="Describe a specific risk",
                data_source={},
                data_type=DataType.TEXT,
                order=1,
                group=question_group,
            ),
            Question(
                title="What is the likelihood?",
                name="proposal_likelihood",
                slug=slugify("proposal_likelihood"),
                hint="What is the likelihood?",
                data_source={},
                data_type=DataType.NUMBER,
                order=2,
                group=question_group,
            ),
            Question(
                title="How will you mitigate this risk?",
                name="proposal_mitigation",
                slug=slugify("proposal_mitigation"),
                hint="How will you mitigate this risk?",
                data_source={},
                data_type=DataType.TEXT,
                order=3,
                group=question_group,
            ),
        ]
    )

    # --- Section 3 ---
    section_3 = Section(title="Funding required", order=3)
    form_3 = Form(title="Funding required", order=1, slug=slugify("Funding required"))
    question_group_3 = QuestionGroup(
        title="Funding required",
        slug="funding-required",
        allow_add_another=False,
        show_all_on_same_page=True,
        item_limit=None,
        form=form_3,
    )
    # Group question with logical group & show on same page
    form_3.questions.extend(
        [
            Question(
                title="What is the cost?",
                name="cost",
                slug=slugify("cost"),
                hint="Describe the cost",
                data_source={},
                data_type=DataType.TEXT,
                order=1,
                group=question_group_3,
            ),
            Question(
                title="Amount",
                name="amount",
                slug=slugify("amount"),
                hint="Amount",
                data_source={},
                data_type=DataType.NUMBER,
                order=2,
                group=question_group_3,
            ),
            Question(
                title="How much money from the COF grant will you use to pay for this cost?",
                name="grant",
                slug=slugify("grant"),
                hint="How much money from the COF grant will you use to pay for this cost?",
                data_source={},
                data_type=DataType.TEXT,
                order=3,
                group=question_group_3,
            ),
        ]
    )

    # --- Section 4 ---
    section_4 = Section(title="About your organization", order=4)
    form_4 = Form(title="About your organization", order=1, slug=slugify("About your organization"))
    question_group_4 = QuestionGroup(
        title="About your organization",
        slug="about-your-organization",
        allow_add_another=False,
        show_all_on_same_page=True,
        item_limit=None,
        form=form_4,
    )
    # Group question with logical group and normal questions
    form_4.questions.extend(
        [
            Question(
                title="What is the name of your organization?",
                name="organization_name",
                slug=slugify("organization_name"),
                hint="Enter the name of your organization",
                data_source={},
                data_type=DataType.TEXT,
                order=1,
            ),
            Question(
                title="Website and social media",
                name="website_and_social_media",
                slug=slugify("website_and_social_media"),
                hint="Enter the website and social media links",
                data_source={},
                data_type=DataType.URL,
                order=2,
                group=question_group_4,
            ),
            Question(
                title="Are you a human?",
                name="are_you_a_human",
                slug=slugify("are_you_a_human"),
                hint="Are you a human?",
                data_source={},
                data_type=DataType.TEXT,
                order=3,
                group=question_group_4,
            ),
            Question(
                title="Organization address",
                name="organization_address",
                slug=slugify("organization_address"),
                hint="Enter the organization address",
                data_source={},
                data_type=DataType.ADDRESS,
                order=4,
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
