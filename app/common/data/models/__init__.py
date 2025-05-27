import datetime
import enum
import secrets
import uuid
from typing import Any, Optional

from pytz import utc
from sqlalchemy import Enum, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.ext.orderinglist import ordering_list
from sqlalchemy.orm import Mapped, composite, mapped_column, relationship

from app.common.data.base import BaseModel, CIStr


class Grant(BaseModel):
    __tablename__ = "grant"

    name: Mapped[CIStr] = mapped_column(unique=True)

    collection_schemas: Mapped[list["CollectionSchema"]] = relationship("CollectionSchema", lazy=True)


class User(BaseModel):
    __tablename__ = "user"

    email: Mapped[CIStr] = mapped_column(unique=True)

    magic_links: Mapped[list["MagicLink"]] = relationship("MagicLink", back_populates="user")

    # Required by Flask-Login; should be provided by UserMixin, except that breaks our type hinting
    # when using this class in SQLAlchemy queries. So we've just lifted the key attributes here directly.
    @property
    def is_active(self) -> bool:
        return True

    @property
    def is_authenticated(self) -> bool:
        return self.is_active

    @property
    def is_anonymous(self) -> bool:
        return False

    def get_id(self) -> str:
        return str(self.id)


class MagicLink(BaseModel):
    __tablename__ = "magic_link"

    code: Mapped[str] = mapped_column(unique=True, default=lambda: secrets.token_urlsafe(12))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    redirect_to_path: Mapped[str]
    expires_at_utc: Mapped[datetime.datetime]
    claimed_at_utc: Mapped[datetime.datetime | None]

    user: Mapped[User] = relationship("User", back_populates="magic_links")

    __table_args__ = (Index(None, code, unique=True, postgresql_where="claimed_at_utc IS NOT NULL"),)

    @property
    def usable(self) -> bool:
        return self.claimed_at_utc is None and self.expires_at_utc > datetime.datetime.now(utc).replace(tzinfo=None)


class CollectionSchema(BaseModel):
    __tablename__ = "collection_schema"

    # Name will be superseded by domain specific application contexts but allows us to
    # try out different schemas and scenarios
    name: Mapped[str]
    version: Mapped[int] = mapped_column(default=1)

    grant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("grant.id"))
    grant: Mapped[Grant] = relationship("Grant", back_populates="collection_schemas")

    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    created_by: Mapped[User] = relationship("User")

    sections: Mapped[list["Section"]] = relationship(
        "Section", lazy=True, order_by="Section.order", collection_class=ordering_list("order", count_from=1)
    )

    __table_args__ = (UniqueConstraint("name", "grant_id", "version", name="uq_schema_name_version_grant_id"),)


class Section(BaseModel):
    __tablename__ = "section"

    title: Mapped[str]
    order: Mapped[int]

    collection_schema_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("collection_schema.id"))
    collection_schema: Mapped[CollectionSchema] = relationship("CollectionSchema", back_populates="sections")

    forms: Mapped[list["Form"]] = relationship(
        "Form", order_by="Form.order", collection_class=ordering_list("order", count_from=1)
    )

    __table_args__ = (
        UniqueConstraint("order", "collection_schema_id", name="uq_section_order_collection_schema", deferrable=True),
        UniqueConstraint("title", "collection_schema_id", name="uq_section_title_collection_schema"),
    )


# TODO: my forms don't currently have orders, it would be good to add them to be complete


# the form being complete for a given submission is derived from all of the questions being answered
# that should be combined with the fact that the user has marked it as complete which is currently modelled
# by a submission event TBD
class Form(BaseModel):
    __tablename__ = "form"

    title: Mapped[str]
    order: Mapped[int]
    slug: Mapped[str]

    section_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("section.id"))
    section: Mapped[Section] = relationship("Section", back_populates="forms")

    is_template: Mapped[bool] = mapped_column(default=False)

    # this is denormalised intentionally to allow for a unique constraint on the parent table
    # having sections not be a heirarchical element would allow for this in a cleaner way I think
    collection_schema_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("collection_schema.id"))
    collection_schema: Mapped[CollectionSchema] = relationship("CollectionSchema")

    __table_args__ = (
        UniqueConstraint("order", "section_id", name="uq_form_order_section", deferrable=True),
        UniqueConstraint("title", "collection_schema_id", name="uq_form_title_collection_schema"),
        UniqueConstraint("slug", "section_id", name="uq_form_slug_section"),
    )

    # what did i change - reorder on append removed, starting from 0 by default now rather than 1
    questions: Mapped[list["Question"]] = relationship(
        # previously: "Question", lazy=True, order_by="Question.order", collection_class=ordering_list("order", count_from=1)
        # "Question", lazy=True, order_by="Question.order", collection_class=ordering_list("ordering_key", count_from=1)
        # "Question", lazy=True, order_by=("Question.parent_id", "Question.order"), collection_class=ordering_list("order", count_from=1, reorder_on_append=True)
        "Question",
        lazy=True,
        # cascade="all, delete-orphan",
        order_by="Question.order",
        collection_class=ordering_list("order"),
        # the alternative to this is to not set the join column form ID for nested children
        # I think there are pros and cons but having a duplicated form relationship might get confusing
        # doing this for now
        # TODO: does this work for example when you update a model locally - does it exclude children appended to questions?
        #       if not setting the form ID rather than the form would be a workaround
        # TODONE: I've checked it and it does get respected on a model that hasn't been committed
        # Update: I don't think this is doing what I'd like it to be doing, either this is being overriden by the join or something else
        # for now we're just not associating the form, I'll see if there's another route at that later - it shouldn't matter right now
        # primaryjoin="and_(Question.form_id==Form.id, Question.parent_id.is_(None))"
        # "Question", lazy=True, order_by="Question.order", collection_class=ordering_list("order", count_from=1)
    )

    # sections: Mapped[list["Section"]] = relationship(
    #     "Section", lazy=True, order_by="Section.order", collection_class=ordering_list("order", count_from=1)
    # )


class DataType(enum.Enum):
    SINGLE_LINE_OF_TEXT = "SINGLE_LINE_OF_TEXT"
    MULTIPLE_LINES_OF_TEXT = "MULTIPLE_LINES_OF_TEXT"
    UK_ADDRESS = "UK_ADDRESS"


class QuestionType(enum.Enum):
    QUESTION = "QUESTION"
    GROUP = "GROUP"

    # I think we're going to remove this as a question type and just have it as a "question" which has a data type of presenting
    # that conceptually keeps this entry to be a question or a group of questions
    PAGE = "PAGE"


# feels like types of "Question", "Group" or "Page" (informational only)
class Question(BaseModel):
    __tablename__ = "question"

    # this reimplmenets the ID from the base model so that we can refer to it in the parent - there's probably a nicer way
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, sort_order=-100, default=uuid.uuid4)

    # this should be title
    text: Mapped[Optional[str]]
    slug: Mapped[str]
    order: Mapped[int]
    hint: Mapped[Optional[str]]
    name: Mapped[str]

    context: Mapped[dict[str, Any]] = mapped_column(default={})

    # this could be simplified by not having a question type - that could be inferred by if anything refers to this as its parent (and could be a calculated property if thats useful)
    # informational pages could then be a data type which is a bit cheeky but it would simplify the model quite a lot
    question_type: Mapped[QuestionType] = mapped_column(Enum(QuestionType))
    data_type: Mapped[Optional[DataType]] = mapped_column(Enum(DataType))

    form_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("form.id"))
    form: Mapped[Form] = relationship("Form", back_populates="questions")

    parent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("question.id"), nullable=True)
    parent: Mapped["Question"] = relationship(
        "Question",
        remote_side=[id],
        back_populates="questions",
        # lazy="joined",
        lazy="joined",
    )

    # Define a composite key for ordering
    # class OrderingKey:
    #     def __init__(self, order, parent_id):
    #         self.order = order
    #         self.parent_id = parent_id

    #     def __lt__(self, other):
    #         if self.parent_id is None and other.parent_id is not None:
    #             return True
    #         if self.parent_id is not None and other.parent_id is None:
    #             return False
    #         return self.order < other.order

    #     def __eq__(self, other):
    #          return (self.order, self.parent_id) == (other.order, other.parent_id)

    #     def __hash__(self):
    #         return hash((self.order, self.parent_id))

    # @hybrid_property
    # def ordering_key(self):
    #     return Question.OrderingKey(self.order, self.parent_id)

    # @ordering_key.expression
    # def ordering_key(cls):
    #     return composite(Question.OrderingKey, cls.order, cls.parent_id)

    questions: Mapped[list["Question"]] = relationship(
        "Question",
        back_populates="parent",
        # cascade="all, delete-orphan", # - might want to think about this,
        # order_by=("Question.parent_id", "Question.order"),
        order_by="Question.order",
        # previously: collection_class=ordering_list("order", count_from=1),
        # collection_class=ordering_list("ordering_key", count_from=1),
        collection_class=ordering_list("order"),
        # collection_class=ordering_list("order", count_from=1),
        lazy="selectin",  # - consider performance, I think this allows a balance of perf and sensible queries - will have a think
    )

    expressions: Mapped[list["Expression"]] = relationship("Expression", back_populates="question")

    # sfount:TODO: this behaviour/ ORM link needs interrogating
    depends_on_questions: Mapped[list["QuestionDependsOn"]] = relationship(
        "QuestionDependsOn", back_populates="question", foreign_keys="[QuestionDependsOn.question_id]", lazy="selectin"
    )
    questions_depend_on: Mapped[list["QuestionDependsOn"]] = relationship(
        "QuestionDependsOn",
        back_populates="depends_on_question",
        foreign_keys="[QuestionDependsOn.depends_on_question_id]",
        lazy="selectin",
    )

    # we don't currently calculate a depth, depth could be a property that traverses up through the quesitons
    # properties - if we're able to do an appropriate selectin that guarantees all questions are in that
    # feels like it should work

    @property
    def conditions(self):
        return [x for x in self.expressions if x.type == ExpressionType.CONDITION]

    @property
    def validations(self):
        return [x for x in self.expressions if x.type == ExpressionType.VALIDATION]

    __table_args__ = (
        UniqueConstraint("order", "parent_id", "form_id", name="uq_question_order_parent_form", deferrable=True),
        UniqueConstraint("slug", "form_id", name="uq_question_slug_form"),
        UniqueConstraint("name", "form_id", name="uq_question_name_form"),
    )


# some questions around how this will work across collections and versions but I think as long as
# you're duplicating these when you're creating a new version it should be OK
# extension question about coming from templates
class QuestionDependsOn(BaseModel):
    __tablename__ = "question_depends_on"

    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("question.id"), primary_key=True)
    depends_on_question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("question.id"), primary_key=True)

    # should we also identify which expression uses this?
    # the alogorithm for replacing it will then be to remove anything this expression currently sets and add them again
    expression_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("expression.id"))
    expression: Mapped["Expression"] = relationship("Expression")

    # could back populate questions that this depends on and what depends on it (should definitely be lazy loaded)
    # sfount:TODO: this behaviour/ ORM link needs interrogating
    question: Mapped[Question] = relationship(
        "Question", foreign_keys=[question_id], back_populates="depends_on_questions"
    )
    depends_on_question: Mapped[Question] = relationship(
        "Question", foreign_keys=[depends_on_question_id], back_populates="questions_depend_on"
    )

    # question: Mapped[Question] = relationship("Question")
    # depends_on_question: Mapped[Question] = relationship("Question")


# questions could still have "conditions", "validations" which would
# having other calculated values from expressions maybe even output as a "personalisation" that could
# be used in the context
class ExpressionType(enum.Enum):
    CONDITION = "CONDITION"
    VALIDATION = "VALIDATION"


# this might go up near somewhere where data types are described/ serialised/ deserialised
# things like CONDITION_SELECT_EQUALS, VALIDATION_NUMBER_GREATER_THAN (might not need the condition/ validation prefix)
# class ConditionKeys
class Expression(BaseModel):
    __tablename__ = "expression"
    type: Mapped[ExpressionType]
    value: Mapped[str]

    # context wants to store things like human readable keys
    context: Mapped[dict[str, Any]] = mapped_column(default={})

    # this will only be set if the expression is custom and isn't otherwise setting a context to be read
    # for conditions this could be used to explain why it will be shown on the all questions page and
    # for validations it will be shown to the user when it fails this validation
    human_readable_message: Mapped[Optional[str]]

    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("question.id"), nullable=False)
    question: Mapped[Question] = relationship("Question", back_populates="expressions")


###
###


# the details for this will likely end up domain specific, is there a broad level we want to keep track of
# and then let the domain set its specific status workflow
# you can only move through to submitted if all of the forms within a collection have been marked as complete
# they can only be marked as complete if all of the questions have been answered
# meta - should this be derived from submission events as well as forms being complete? I think its probably helpful
#        have it for things like searching and filtering
class SubmissionStatus(enum.Enum):
    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    # APPROVED="APPROVED"
    # REJECTED="REJECTED"
    # ARCHIVED="ARCHIVED"


# submission for a collection, data should be deterministically produced from the schema and current state
# will likely need an events table to serialise the metadata (which could also be read from directly, will want to see how thats feeling)
# i.e an even
class Submission(BaseModel):
    __tablename__ = "submission"

    collection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("collection_schema.id"))
    collection: Mapped[CollectionSchema] = relationship("CollectionSchema")

    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    created_by_user: Mapped[User] = relationship("User")

    data: Mapped[dict[str, Any]] = mapped_column(default={})

    status: Mapped[SubmissionStatus] = mapped_column(default=SubmissionStatus.CREATED)

    events: Mapped[list["SubmissionEvent"]] = relationship("SubmissionEvent", back_populates="submission")


# collection schema id
# form id - nullable, if its set its about the form, if not the collection/ submission
# event - started, marked as complete
# created at
# created by

# any time a the submission data attribute is updated or overwritten with the current state, events
# should be written in that same transaction

# FORM_STARTED
# FORM_UPDATED? - unfortuantely we've agreed things are persisted as you press continue in a form so this would be called quite a lot
#                 we could only record this when you press continue on the check your answers page or we could just record a lot of them!
# FORM_MARKED_COMPLETE

# I presume a submission will come with all of its events, I think it will be fine for this to be done
# in one joined journey


class SubmissionEventKey(enum.Enum):
    FORM_STARTED = "FORM_STARTED"
    FORM_MARKED_COMPLETE = "FORM_MARKED_COMPLETE"
    SUBMISSION_COMPLETED = "SUBMISSION_COMPLETED"


class SubmissionEvent(BaseModel):
    __tablename__ = "submission_event"

    key: Mapped[SubmissionEventKey]

    created_by: Mapped[User] = mapped_column(ForeignKey("user.id"))
    created_by_user: Mapped[User] = relationship("User")

    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submission.id"))

    # optional - only applicable if this event relates specifically to a form
    form_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("form.id"), nullable=True)

    submission: Mapped[Submission] = relationship("Submission", back_populates="events")
