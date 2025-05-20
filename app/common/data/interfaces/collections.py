import uuid
from typing import Any, List
from uuid import UUID

from pydantic import UUID4
from slugify import slugify
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, NoResultFound

from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.models import (
    CollectionSchema,
    Condition,
    Form,
    Grant,
    Question,
    QuestionGroup,
    Section,
    Submission,
    User,
    Validation,
)
from app.common.data.types import DataType, SubmissionType
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


def save_submission(submission: Submission) -> Submission | None:
    db.session.add(submission)
    try:
        db.session.flush()
        db.session.commit()
        return submission
    except Exception as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e


def get_submission(submission_id: UUID4) -> Submission | None:
    stmt = select(Submission).filter_by(id=submission_id)
    try:
        return db.session.execute(stmt).scalar_one()
    except NoResultFound:
        return None


def get_submission_by_id(submission_id: uuid.UUID):
    if submission_id is None:
        return None
    return db.session.get_one(Submission, submission_id)


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


def add_test_grant_schema() -> dict:
    """Creates a test grant schema with flush/fetch per entity. No loops for questions."""

    # --- User ---
    user = db.session.query(User).filter_by(email="nuwan.samarasinghe@communities.gov.uk").first()
    if not user:
        user = User(email="nuwan.samarasinghe@communities.gov.uk")
        db.session.add(user)
        db.session.flush()
        user = db.session.query(User).filter_by(email=user.email).first()

    # --- Grant ---
    grant = db.session.query(Grant).filter_by(name="Community Ownership Fund").first()
    if not grant:
        grant = Grant(name="Community Ownership Fund")
        db.session.add(grant)
        db.session.flush()
        grant = db.session.query(Grant).filter_by(name=grant.name).first()

    # --- Schema ---
    existing = (
        db.session.query(CollectionSchema).filter_by(name="Community Ownership Funding Collection", version=1).first()
    )
    if existing:
        db.session.delete(existing)
        db.session.flush()

    schema = CollectionSchema(
        name="Community Ownership Funding Collection",
        version=1,
        created_by_id=user.id,
        grant_id=grant.id,
        slug=slugify("Community Ownership Funding Collection"),
    )
    db.session.add(schema)
    db.session.flush()
    schema = db.session.query(CollectionSchema).filter_by(id=schema.id).first()

    # -------------------------------
    # Section 1: Applicant Information
    # -------------------------------
    section_1 = Section(
        title="Applicant information", order=1, collection_schema_id=schema.id, slug=slugify("Applicant information")
    )
    db.session.add(section_1)
    db.session.flush()

    form_1 = Form(
        title="Applicant information", order=1, slug=slugify("Applicant information"), section_id=section_1.id
    )
    db.session.add(form_1)
    db.session.flush()

    q1 = Question(
        title="Name of lead contact ?",
        name="Lead Contact Name",
        slug=slugify("Name of lead contact"),
        hint="Enter the full name of the lead contact",
        data_source={},
        data_type=DataType.TEXT,
        order=1,
        form_id=form_1.id,
    )
    db.session.add(q1)
    db.session.flush()
    q1 = db.session.query(Question).filter_by(id=q1.id).first()

    validation_f1_q1_1 = Validation(
        question=q1,
        expression=f"bool({q1.id})",
        message="Name of the lead contact cannot be empty",
    )
    db.session.add(validation_f1_q1_1)
    db.session.flush()

    q2 = Question(
        title="Lead contact job title ?",
        name="Lead Contact Job Title",
        slug=slugify("Lead contact job title"),
        hint="Enter the job title of the lead contact",
        data_source={},
        data_type=DataType.TEXT,
        order=2,
        form_id=form_1.id,
    )
    db.session.add(q2)
    db.session.flush()
    q2 = db.session.query(Question).filter_by(id=q2.id).first()

    condition_f1_q2_1 = Condition(
        question=q2,
        expression=f"bool({q1.id})",
        depends_on=q1,
        description="If the first question empty this should not show up",
    )
    db.session.add(condition_f1_q2_1)
    db.session.flush()

    validation_f1_q2_1 = Validation(
        question=q2,
        expression=f"bool({q2.id})",
        message="Lead contact job title cannot be empty",
    )
    db.session.add(validation_f1_q2_1)
    db.session.flush()

    q3 = Question(
        title="Lead contact email address ?",
        name="Lead Contact Email Address",
        slug=slugify("Lead contact email address"),
        hint="Enter the email address of the lead contact",
        data_source={},
        data_type=DataType.EMAIL,
        order=3,
        form_id=form_1.id,
    )
    db.session.add(q3)
    db.session.flush()
    q3 = db.session.query(Question).filter_by(id=q3.id).first()

    condition_f1_q3_1 = Condition(
        question=q3,
        expression=f"bool({q2.id})",
        depends_on=q2,
        description="If the second question empty this should not show up",
    )
    db.session.add(condition_f1_q3_1)
    db.session.flush()

    validation_f1_q3_1 = Validation(
        question=q3,
        expression=f"bool({q3.id})",
        message="Lead contact email address cannot be empty",
    )
    db.session.add(validation_f1_q3_1)
    db.session.flush()

    q4 = Question(
        title="Lead contact telephone number ?",
        name="Lead Contact Telephone Number",
        slug=slugify("Lead contact telephone number"),
        hint="Enter the telephone number of the lead contact",
        data_source={},
        data_type=DataType.PHONE_NUMBER,
        order=4,
        form_id=form_1.id,
    )
    db.session.add(q4)
    db.session.flush()
    q4 = db.session.query(Question).filter_by(id=q4.id).first()

    condition_f1_q4_1 = Condition(
        question=q4,
        expression=f"bool({q3.id})",
        depends_on=q3,
        description="If the third question empty this should not show up",
    )
    db.session.add(condition_f1_q4_1)
    db.session.flush()

    validation_f1_q4_1 = Validation(
        question=q4,
        expression=f"bool({q4.id})",
        message="Lead contact email address cannot be empty",
    )
    db.session.add(validation_f1_q4_1)
    db.session.flush()

    # -------------------------------
    # Section 2: Risk and Deliverability
    # -------------------------------
    section_2 = Section(
        title="Risk and deliverability",
        order=2,
        collection_schema_id=schema.id,
        slug=slugify("Risk and deliverability"),
    )
    db.session.add(section_2)
    db.session.flush()

    form_2 = Form(
        title="Risk and deliverability", order=1, slug=slugify("Risk and deliverability"), section_id=section_2.id
    )
    db.session.add(form_2)
    db.session.flush()

    group_2 = QuestionGroup(
        title="Your proposal risks",
        slug="your-proposal-risks",
        allow_add_another=True,
        show_all_on_same_page=False,
        item_limit=3,
        form_id=form_2.id,
        order=1,
    )
    db.session.add(group_2)
    db.session.flush()
    group_2 = db.session.query(QuestionGroup).filter_by(id=group_2.id).first()

    q5 = Question(
        title="What is the risk?",
        name="proposal_risk",
        slug=slugify("proposal_risk"),
        hint="Describe a specific risk",
        data_source={},
        data_type=DataType.TEXT,
        order=1,
        form_id=form_2.id,
        group_id=group_2.id,
    )
    db.session.add(q5)
    db.session.flush()
    q5 = db.session.query(Question).filter_by(id=q5.id).first()

    condition_f2_q5_1 = Condition(
        question=q5,
        expression=f"bool({form_1.id}.{q4.id})",
        depends_on=q4,
        description="This second section will be depend on the first form data and all the answers should be given before coming into this section",
    )
    db.session.add(condition_f2_q5_1)
    db.session.flush()

    validation_f2_q5_1 = Validation(
        question=q5,
        expression=f"bool({q5.id})",
        message="What is the risk cannot be empty",
    )
    db.session.add(validation_f2_q5_1)
    db.session.flush()

    q6 = Question(
        title="What is the likelihood?",
        name="proposal_likelihood",
        slug=slugify("proposal_likelihood"),
        hint="What is the likelihood?",
        data_source={},
        data_type=DataType.NUMBER,
        order=2,
        form_id=form_2.id,
        group_id=group_2.id,
    )
    db.session.add(q6)
    db.session.flush()
    q6 = db.session.query(Question).filter_by(id=q6.id).first()

    condition_f2_q6_1 = Condition(
        question=q6,
        expression=f"bool({q5.id})",
        depends_on=q5,
        description="This second section will be depend on the first question of the form",
    )
    db.session.add(condition_f2_q6_1)
    db.session.flush()

    validation_f2_q6_1 = Validation(
        question=q6,
        expression=f"bool({q6.id})",
        message="What is the likelihood cannot be empty",
    )
    db.session.add(validation_f2_q6_1)
    db.session.flush()

    q7 = Question(
        title="How will you mitigate this risk?",
        name="proposal_mitigation",
        slug=slugify("proposal_mitigation"),
        hint="How will you mitigate this risk?",
        data_source={},
        data_type=DataType.TEXT,
        order=3,
        form_id=form_2.id,
        group_id=group_2.id,
    )
    db.session.add(q7)
    db.session.flush()
    q7 = db.session.query(Question).filter_by(id=q7.id).first()

    condition_f2_q7_1 = Condition(
        question=q7,
        expression=f"bool({q6.id})",
        depends_on=q6,
        description="This second section will be depend on the second question of the form",
    )
    db.session.add(condition_f2_q7_1)
    db.session.flush()

    validation_f2_q7_1 = Validation(
        question=q7,
        expression=f"bool({q7.id})",
        message="How will you mitigate this risk cannot be empty",
    )
    db.session.add(validation_f2_q7_1)
    db.session.flush()

    # -------------------------------
    # Section 3: Funding Required
    # -------------------------------
    section_3 = Section(
        title="Funding required",
        order=3,
        collection_schema_id=schema.id,
        slug=slugify("Funding required"),
    )
    db.session.add(section_3)
    db.session.flush()

    form_3 = Form(title="Funding required", order=1, slug=slugify("Funding required"), section_id=section_3.id)
    db.session.add(form_3)
    db.session.flush()

    group_3 = QuestionGroup(
        title="Funding required",
        slug="funding-required",
        allow_add_another=False,
        show_all_on_same_page=True,
        item_limit=None,
        form_id=form_3.id,
        order=1,
    )
    db.session.add(group_3)
    db.session.flush()
    group_3 = db.session.query(QuestionGroup).filter_by(id=group_3.id).first()

    q8 = Question(
        title="What is the cost?",
        name="cost",
        slug=slugify("cost"),
        hint="Describe the cost",
        data_source={},
        data_type=DataType.TEXT,
        order=1,
        form_id=form_3.id,
        group_id=group_3.id,
    )
    db.session.add(q8)
    db.session.flush()
    q8 = db.session.query(Question).filter_by(id=q8.id).first()

    q9 = Question(
        title="Amount",
        name="amount",
        slug=slugify("amount"),
        hint="Amount",
        data_source={},
        data_type=DataType.NUMBER,
        order=2,
        form_id=form_3.id,
        group_id=group_3.id,
    )
    db.session.add(q9)
    db.session.flush()
    q9 = db.session.query(Question).filter_by(id=q9.id).first()

    condition_f3_q9_1 = Condition(
        question=q9,
        expression=f"bool({q8.id})",
        depends_on=q8,
        description="This third section will be depend on the previous question",
    )
    db.session.add(condition_f3_q9_1)
    db.session.flush()

    q10 = Question(
        title="How much money from the COF grant will you use to pay for this cost?",
        name="grant",
        slug=slugify("grant"),
        hint="How much money from the COF grant will you use to pay for this cost?",
        data_source={},
        data_type=DataType.TEXT,
        order=3,
        form_id=form_3.id,
        group_id=group_3.id,
    )
    db.session.add(q10)
    db.session.flush()
    q10 = db.session.query(Question).filter_by(id=q10.id).first()

    condition_f3_q10_1 = Condition(
        question=q10,
        expression=f"bool({q9.id})",
        depends_on=q9,
        description="This third section will be depend on the previous question",
    )
    db.session.add(condition_f3_q10_1)
    db.session.flush()

    condition_f3_q10_2 = Condition(
        question=q10,
        expression=f"{q9.id} > 1000",
        depends_on=q9,
        description="This third section will be depend on the previous question that asked but should not exceed that amount",
    )
    db.session.add(condition_f3_q10_2)
    db.session.flush()

    # -------------------------------
    # Section 4: About Your Organization
    # -------------------------------
    section_4 = Section(
        title="About your organization",
        order=4,
        collection_schema_id=schema.id,
        slug=slugify("About your organization"),
    )
    db.session.add(section_4)
    db.session.flush()

    form_4 = Form(
        title="About your organization", order=1, slug=slugify("About your organization"), section_id=section_4.id
    )
    db.session.add(form_4)
    db.session.flush()

    group_4 = QuestionGroup(
        title="About your organization",
        slug="about-your-organization",
        allow_add_another=False,
        show_all_on_same_page=True,
        item_limit=None,
        form_id=form_4.id,
        order=1,
    )
    db.session.add(group_4)
    db.session.flush()
    group_4 = db.session.query(QuestionGroup).filter_by(id=group_4.id).first()

    q11 = Question(
        title="What is the name of your organization?",
        name="organization_name",
        slug=slugify("organization_name"),
        hint="Enter the name of your organization",
        data_source={},
        data_type=DataType.TEXT,
        order=1,
        form_id=form_4.id,
    )
    db.session.add(q11)
    db.session.flush()
    q11 = db.session.query(Question).filter_by(id=q11.id).first()

    condition_f4_q11_1 = Condition(
        question=q11,
        expression=f"bool({q10.id})",
        depends_on=q10,
        description="This second section will be depend on the second question of the form",
    )
    db.session.add(condition_f4_q11_1)
    db.session.flush()

    q12 = Question(
        title="Website and social media",
        name="website_and_social_media",
        slug=slugify("website_and_social_media"),
        hint="Enter the website and social media links",
        data_source={},
        data_type=DataType.URL,
        order=2,
        form_id=form_4.id,
        group_id=group_4.id,
    )
    db.session.add(q12)
    db.session.flush()
    q12 = db.session.query(Question).filter_by(id=q12.id).first()

    condition_f4_q12_1 = Condition(
        question=q12,
        expression=f"bool({q11.id})",
        depends_on=q11,
        description="This second section will be depend on the second question of the form",
    )
    db.session.add(condition_f4_q12_1)
    db.session.flush()

    q13 = Question(
        title="Are you a human?",
        name="are_you_a_human",
        slug=slugify("are_you_a_human"),
        hint="Are you a human?",
        data_source={},
        data_type=DataType.TEXT,
        order=3,
        form_id=form_4.id,
        group_id=group_4.id,
    )
    db.session.add(q13)
    db.session.flush()
    q13 = db.session.query(Question).filter_by(id=q13.id).first()

    condition_f4_q13_1 = Condition(
        question=q13,
        expression=f"bool({q12.id})",
        depends_on=q12,
        description="This second section will be depend on the second question of the form",
    )
    db.session.add(condition_f4_q13_1)
    db.session.flush()

    q14 = Question(
        title="Organization address",
        name="organization_address",
        slug=slugify("organization_address"),
        hint="Enter the organization address",
        data_source={},
        data_type=DataType.ADDRESS,
        order=4,
        form_id=form_4.id,
    )
    db.session.add(q14)
    db.session.flush()
    q14 = db.session.query(Question).filter_by(id=q14.id).first()

    condition_f4_q14_1 = Condition(
        question=q14,
        expression=f"bool({q13.id})",
        depends_on=q13,
        description="This second section will be depend on the second question of the form",
    )
    db.session.add(condition_f4_q14_1)
    db.session.flush()

    # Done
    return {"schema_id": str(schema.id)}


def transform_submission_data(slug_data: dict, schema: CollectionSchema) -> dict:
    transformed = {}

    for section in schema.sections:
        section_data = {}
        section_slug = slugify(section.title)
        section_slug_data = slug_data.get(section_slug, {})

        for form in section.forms:
            form_data = {}
            form_slug = slugify(form.title)
            form_slug_data = section_slug_data.get(form_slug, {})

            # Map individual questions (not in a group)
            for question in form.questions:
                if question.group_id is None:
                    answer = form_slug_data.get(slugify(question.name))
                    if answer is not None:
                        form_data[str(question.id)] = answer

            # Map question groups
            for group in form.question_groups:
                group_slug = group.slug
                group_answers = form_slug_data.get(group_slug)

                if group.allow_add_another:
                    # Repeatable group: list of entries
                    if isinstance(group_answers, list):
                        form_data[str(group.id)] = []
                        for item in group_answers:
                            item_data = {
                                str(q.id): item.get(slugify(q.name)) for q in group.questions if slugify(q.name) in item
                            }
                            form_data[str(group.id)].append(item_data)
                else:
                    # Single group instance
                    if isinstance(group_answers, dict):
                        group_data = {
                            str(q.id): group_answers.get(slugify(q.name))
                            for q in group.questions
                            if slugify(q.name) in group_answers
                        }
                        form_data[str(group.id)] = group_data

            section_data[str(form.id)] = form_data

        transformed[str(section.id)] = section_data

    return transformed


def add_test_grant_submission():
    """Add a test grant submission to the database, with data structured by section and form."""
    try:
        schema = (
            db.session.query(CollectionSchema).filter_by(name="Community Ownership Funding Collection", version=1).one()
        )
    except NoResultFound:
        raise ValueError(
            "Test collection schema 'Community Ownership Funding Collection v1' not found. "
            "Please ensure add_test_grant_schema() has been run successfully before calling this function."
        ) from None

    submission_data = {
        "applicant-information": {
            "applicant-information": {
                "lead-contact-name": "Maria Jones",
                "lead-contact-job-title": "Project Lead",
                "lead-contact-email": "maria.jones@example.org.uk",
                "lead-contact-phone": "07123456789",
            }
        },
        "risk-and-deliverability": {
            "risk-and-deliverability": {
                "your-proposal-risks": [
                    {
                        "proposal-risk": "Key supplier may not deliver materials on time.",
                        "proposal-likelihood": 3,
                        "proposal-mitigation": "Identify alternative suppliers and confirm lead times. Build buffer into project timeline.",
                    },
                    {
                        "proposal-risk": "Lower than expected community engagement for fundraising events.",
                        "proposal-likelihood": 2,
                        "proposal-mitigation": "Broaden marketing efforts, partner with local community groups, offer early bird incentives.",
                    },
                ]
            }
        },
        "funding-required": {
            "funding-required": {
                "funding-required": {
                    "cost": "Renovation of main hall lighting system to LED.",
                    "amount": 8500,
                    "grant": "Seeking £6000 from COF, remaining £2500 from existing reserves.",
                }
            }
        },
        "about-your-organization": {
            "about-your-organization": {
                "organization-name": "The Community Hearth Association",
                "about-your-organization": {
                    "website-and-social-media": "https://www.communityhearth.example.com",
                    "are-you-a-human": "Our organisation is run by humans, for humans.",
                },
                "organization-address": "Oakwell House, 45 Chestnut Avenue, Little Whinging, Surrey, LW1 5PQ",
            }
        },
    }

    submission_data_type_2 = {"applicant-information": {"applicant-information": {"lead-contact-name": "Maria Jones"}}}

    submission_data_type_3 = {
        "applicant-information": {
            "applicant-information": {
                "lead-contact-name": "Maria Jones",
                "lead-contact-job-title": "Project Lead",
                "lead-contact-email": "maria.jones@example.org.uk",
                "lead-contact-phone": "07123456789",
            }
        },
        "risk-and-deliverability": {
            "risk-and-deliverability": {
                "your-proposal-risks": [
                    {
                        "proposal-risk": "Key supplier may not deliver materials on time.",
                        "proposal-likelihood": 3,
                    }
                ]
            }
        },
    }

    submission_1 = Submission(
        data=transform_submission_data(submission_data, schema),
        status=SubmissionType.COMPLETED,
        collection_schema_id=schema.id,
        collection_schema=schema,
    )

    submission_2 = Submission(
        data=transform_submission_data(submission_data, schema),
        status=SubmissionType.CREATED,
        collection_schema_id=schema.id,
        collection_schema=schema,
    )

    submission_3 = Submission(
        data=transform_submission_data(submission_data_type_2, schema),
        status=SubmissionType.CREATED,
        collection_schema_id=schema.id,
        collection_schema=schema,
    )

    submission_4 = Submission(
        data=transform_submission_data(submission_data_type_3, schema),
        status=SubmissionType.CREATED,
        collection_schema_id=schema.id,
        collection_schema=schema,
    )

    db.session.add_all([submission_1, submission_2, submission_3, submission_4])

    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise RuntimeError(f"Failed to add test grant submission due to an integrity error: {e}") from e
