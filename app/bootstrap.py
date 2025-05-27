# set up some collections/ forms for the time being - for integration tests
# this would use factoryboy. For now I'll just use the models directly
from flask import current_app
from sqlalchemy import text

from app.common.collections import Collection
from app.common.data.interfaces import collections, grants, user
from app.common.data.models import (
    CollectionSchema,
    DataType,
    Expression,
    ExpressionType,
    Form,
    Question,
    QuestionDependsOn,
    QuestionType,
    Section,
    Submission,
)
from app.extensions import db

# anywhere it seems like this is doing too much, add something to interface to make
# doing that simpler

# after setting up a schema, it should then be possible to use, create it a submission and start
# answering questions


def set_up_user():
    a_user = user.get_or_create_user("steven.fountain@communities.gov.uk")
    db.session.commit()
    return a_user


# either pick the first grant that already exists or create a new one
def set_up_grant():
    all_grants = grants.get_all_grants()
    grant = all_grants[0] if all_grants else grants.create_grant("Schema v1 grant")
    db.session.commit()
    return grant


# if the schema created here already exists we should just return that avoid conflicts or a huge
# local db
def set_up_schema():
    grant = set_up_grant()
    user = set_up_user()

    collection = an_application(grant, user)

    current_app.logger.info(f"Grant: {grant.id}")
    return collection


def scenario_swap():
    all = db.session.query(CollectionSchema).all()
    load_collection = collections._get_collection_schema(all[0].id)
    group = load_collection.sections[0].forms[0].questions[2]
    current_app.logger.info(group.questions[2].name)

    # proves moving questions
    _move_questions(group.questions, 2, 3)
    db.session.commit()


# note - loading all of the depends on combinations seems expensive - are we OK to only
# lazy load depends on if we need it - depends when it will be used
def scenario_form():
    all = db.session.query(CollectionSchema).all()
    schema = collections._get_collection_schema(all[0].id)

    # create an empty submission for the form
    # for future scenarios use _get_submission and make sure the joins for getting the associated collection
    # are appropriately configured
    submission = Submission(collection=schema)

    # create a new "application" or collection instance/ submission
    db.session.commit()

    instance = Collection(submission=submission)

    # selecting the form based on its name which gives us a rough approximation for the user
    form_id = next(form.id for form in instance.forms if form.title == "Check eligibility")
    form = instance.form(form_id)

    current_app.logger.info([question.name for question in form.visible_questions])

    question = form.next_question()

    current_app.logger.info(f"Starting with question: {question.name}: {question.text}")

    # routing will want to factor in if we're coming from the summary page, that probably happens outside
    # of the collections helper (in forms handler logic) but there may be an argument for moving it inside
    next_question = form.next_question(question)
    current_app.logger.info(f"Next question: {next_question.name}: {next_question.text}")

    # start on the current form, if you're routing to a form and there's no submission event for having
    # you should create one when the first bit of data is added for the first question

    # select the first "visible" question - the questions in the list should be run against their conditions which
    # will require loading the context at the top and then eval'ing

    # answer the first question by saving data against it, as if its come in from the form, that should be serialised
    # by the model used for the question type - this could go back and refer to what I did for validation from the proto

    # pick the next question following that question

    # also be ready to present the current available questions and any answers so far (i.e the summary page)
    # - need to decide at what order or stage I'm showing a temporary task list page with all the available forms and their
    #   statuses somewhat based on data available and somewhat based on the submission events

    # this is what the router would be asking - without passing anything in it should default to the first question
    # - subsequent questions might be a helper on the question model, i.e question.next_question()
    # - that would call form.next_question(self)
    # it's likely that I want something else deciding if I should be showing the summary page rather than this helper
    question = form.next_question()


#### temporary methods so simplify not needed


def an_application(grant, user):
    collection = CollectionSchema(name="An application for funding", grant=grant, created_by=user)
    before_you_start = Section(title="Before you start")
    prepare_application = Section(title="Prepare application")

    check_eligibility = _create_form(title="Check eligibility", collection=collection)

    applicant_name = _create_question(
        title="What is your name?", name="Applicant name", data_type=DataType.SINGLE_LINE_OF_TEXT
    )

    organisation_type = _create_question(
        title="What type of organisation are you?", name="Organisation type", data_type=DataType.SINGLE_LINE_OF_TEXT
    )

    # this was the first time I came across groups not needing things like data types and therefore those being optional
    # I suspect there are integrity checks I can put on to make sure things are set given certain attributes but I'll get into that later
    # could feel sharp edge - lets get into the ORM managed ordering and algorithms to step through questions to interrogate if its worth it
    charity_information = _create_group(name="Charity information")

    # unclear if the form will propegate through to the child - I can't see any reason it would, it might need to be set
    # explicitly - when you're adding one thing at a time in the future I think this would be straight forward to reason about
    # summary: adding a question to a question might not set the form on the question appropriately
    # check_eligibility.questions.extend([ applicant_name, organisation_type, charity_information ])

    # do I get IDs at this point or should I be setting an ID to be able to then explicitly use it
    # db.session.flush()

    # move this to a helper that both creates the expression and registers the depends on
    if_charity = Expression(
        # will need to make a call on if this is generally case sensitive or not, by default it could _not_ be case sensitive
        # in which case we'll probably want to lower the values that are subbed in from answers and the context
        value=f"(({organisation_type.id})) == ((value)))",
        # get this from the fixed list, TEXT_EQUALS, NUMBER_GREATER_THAN, DATE_BEFORE, SELECT_VALUE_EQUALS
        # for now everything in the context will always be added to the context
        # ((answer)) - the answer to the current question, this could not yet be validated or persisted
        # ((value)) - a value that comes from the expressions context, this could be named anything, i.e max, min
        # different question and expression types will have different configurations and fixed values in their contexts
        context={"key": "TEXT_EQUALS", "value": "charity"},
        # having the expression but it can use the immediate expressions context for human readable simple versions should give
        # us the balance between flexibility and ease-of-configuration
        type=ExpressionType.CONDITION,
    )
    charity_information.expressions.extend([if_charity])

    # we'd be going through each of the expressions we're setting up here
    charity_information.depends_on_questions.extend(
        [QuestionDependsOn(depends_on_question=organisation_type, expression=if_charity)]
    )

    charity_number = _create_question(
        title="What is your charity number?", name="Charity number", data_type=DataType.SINGLE_LINE_OF_TEXT
    )

    how_many_employees = _create_question(
        title="How many employees does your charity have?",
        name="Number of employees",
        data_type=DataType.SINGLE_LINE_OF_TEXT,
    )

    applicant_job_title = _create_question(
        title="What is your job title?", name="Job title", data_type=DataType.SINGLE_LINE_OF_TEXT
    )

    check_eligibility.questions.extend([applicant_name, organisation_type, charity_information, applicant_job_title])

    # something to think through - I'm leaning on extending a forms questions to back populate the form value on a question
    # when you're adding the question to another question, there's nothing to link it and you'll need to be explicit

    # using the columns thats then joined can cause everything to seem flat based on the query model
    # i can either constrain the read or add a separate column for associating with the original form
    # charity_number.form = check_eligibility
    # how_many_employees.form = check_eligibility
    ######

    charity_information.questions.extend([charity_number, how_many_employees])
    # have tried moving the above below when the original questions were added - I suspect thats normally how it would work
    # figured - you have to have added the questions to the original form before you do nested
    # that would always be true for adding question at a time

    before_you_start.forms.extend([check_eligibility])

    collection.sections.extend([before_you_start, prepare_application])

    db.session.add(collection)
    # db.session.commit()

    # TODO: go through these and check the number of queries generated - I think I had it to 2 maximum before
    #       one for loading the forms and their initial questions and then the sub select for other questions
    # db.session.flush()

    # swap = new_collection[0].sections[0].forms[0].questions
    # swap = collection.sections[0].forms[0].questions
    # swap[2], swap[3] = swap[3], swap[2]

    # _move_questions(collection.sections[0].forms[0].questions, 2, 3)
    # db.session.flush()

    db.session.commit()
    return collection


def _move_questions(questions, index, new_index):
    questions[new_index], questions[index] = questions[index], questions[new_index]
    db.session.execute(
        text(
            "SET CONSTRAINTS uq_section_order_collection_schema, uq_form_order_section, uq_question_order_parent_form DEFERRED"
        )
    )
    db.session.add(questions[index])
    db.session.add(questions[new_index])
    db.session.flush()


def _create_form(title: str, collection: CollectionSchema):
    return Form(title=title, slug=_slug(title), collection_schema=collection)


def _create_question(title: str, name: str, data_type: DataType):
    return Question(
        # this should be title
        text=title,
        name=name,
        slug=_slug(title),
        question_type=QuestionType.QUESTION,
        data_type=data_type,
    )


def _create_group(name: str):
    return Question(name=name, slug=_slug(name), question_type=QuestionType.GROUP)


def _slug(value: str):
    return value.replace(" ", "-").lower()
