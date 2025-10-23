import datetime
import uuid
from functools import cached_property
from typing import TYPE_CHECKING, Any, Callable, Optional, Union

from flask import current_app
from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, UniqueConstraint, select, text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.orderinglist import OrderingList, ordering_list
from sqlalchemy.orm import Mapped, column_property, foreign, mapped_column, relationship
from sqlalchemy_json import mutable_json_type

from app.common.data.base import BaseModel, CIStr
from app.common.data.models_user import Invitation, User
from app.common.data.types import (
    CollectionType,
    ComponentType,
    ExpressionType,
    GrantStatusEnum,
    ManagedExpressionsEnum,
    OrganisationStatus,
    OrganisationType,
    QuestionDataType,
    QuestionPresentationOptions,
    SubmissionEventKey,
    SubmissionModeEnum,
    json_flat_scalars,
    json_scalars,
)
from app.common.expressions.managed import get_managed_expression
from app.common.qid import SafeQidMixin

if TYPE_CHECKING:
    from app.common.data.models_user import UserRole
    from app.common.expressions.managed import ManagedExpression


class Grant(BaseModel):
    __tablename__ = "grant"

    ggis_number: Mapped[str]
    name: Mapped[CIStr] = mapped_column(unique=True)
    status: Mapped[GrantStatusEnum] = mapped_column(default=GrantStatusEnum.DRAFT)
    description: Mapped[str]
    primary_contact_name: Mapped[str]
    primary_contact_email: Mapped[str]
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisation.id"), nullable=True
    )  # TODO: make non-nullable

    collections: Mapped[list["Collection"]] = relationship("Collection", lazy=True, cascade="all, delete-orphan")
    organisation: Mapped["Organisation"] = relationship("Organisation", back_populates="grants")
    grant_recipients: Mapped[list["GrantRecipient"]] = relationship("GrantRecipient", back_populates="grant")

    users: Mapped[list["User"]] = relationship(
        "User",
        secondary="user_role",
        primaryjoin="Grant.id==UserRole.grant_id",
        secondaryjoin="User.id==UserRole.user_id",
        viewonly=True,
    )
    invitations: Mapped[list["Invitation"]] = relationship(
        "Invitation",
        back_populates="grant",
        viewonly=True,
    )

    grant_team_users: Mapped[list["User"]] = relationship(
        "User",
        secondary="user_role",
        primaryjoin="Grant.id==UserRole.grant_id",
        secondaryjoin="and_(User.id==UserRole.user_id, UserRole.organisation_id==foreign(Grant.organisation_id))",
        viewonly=True,
        lazy="select",
    )

    @property
    def reports(self) -> list["Collection"]:
        return [collection for collection in self.collections if collection.type == CollectionType.MONITORING_REPORT]


class Organisation(BaseModel):
    __tablename__ = "organisation"

    # For Central Government departments, this is an IATI organisation identifier
    # from: https://www.gov.uk/government/publications/iati-organisation-identifiers-for-uk-government-organisations
    #
    # For local government, this uses the Local Authority District (December 2024) [LAD24] boundaries dataset:
    # https://geoportal.statistics.gov.uk/datasets/6a05f93297cf4a438d08e972099f54b9_0/explore
    external_id: Mapped[str | None] = mapped_column(unique=True)
    name: Mapped[CIStr] = mapped_column(unique=True)

    # TODO: switch this to a computed column?
    status: Mapped[OrganisationStatus] = mapped_column(default=OrganisationStatus.ACTIVE)

    type: Mapped[OrganisationType | None]
    active_date: Mapped[datetime.date | None] = mapped_column(nullable=True)
    retirement_date: Mapped[datetime.date | None] = mapped_column(nullable=True)
    can_manage_grants: Mapped[bool] = mapped_column(default=False)

    roles: Mapped[list["UserRole"]] = relationship(
        "UserRole", back_populates="organisation", cascade="all, delete-orphan"
    )
    grants: Mapped[list["Grant"]] = relationship("Grant", back_populates="organisation")

    __table_args__ = (
        # NOTE: make it so that only a single organisation can manage grants in the platform at the moment. When we come
        #       to onboard other government departments as grant owners, we'll need to release this constraint and
        #       ensure that Deliver grant funding has appropriate designs to understand and handle multiple grant
        #       owning orgs. For now this lets us keep the idea of org switching out of Deliver grant funding, and our
        #       queries can just find the only organisation with 'can_manage_grants=true'.
        Index(
            "uq_organisation_name_can_manage_grants",
            "can_manage_grants",
            unique=True,
            postgresql_where=can_manage_grants.is_(True),
        ),
        CheckConstraint("status = 'retired' OR retirement_date IS NULL", name="ck_retirement"),
    )


class Collection(BaseModel):
    __tablename__ = "collection"

    # NOTE: The ID provided by the BaseModel should *NOT CHANGE* when incrementing the version. That part is a stable
    #       identifier for linked collection/versioning.
    version: Mapped[int] = mapped_column(default=1, primary_key=True)

    type: Mapped[CollectionType] = mapped_column(SqlEnum(CollectionType, name="collection_type", validate_strings=True))

    # Name will be superseded by domain specific application contexts but allows us to
    # try out different collections and scenarios
    name: Mapped[str]
    slug: Mapped[str]

    grant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("grant.id"))
    grant: Mapped[Grant] = relationship("Grant", back_populates="collections")

    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    created_by: Mapped[User] = relationship("User")

    # NOTE: Don't use this relationship directly; use either `test_submissions` or `live_submissions`.
    _submissions: Mapped[list["Submission"]] = relationship(
        "Submission",
        lazy=True,
        order_by="Submission.created_at_utc",
        back_populates="collection",
        cascade="all, delete-orphan",
    )
    forms: Mapped[OrderingList["Form"]] = relationship(
        "Form",
        lazy=True,
        order_by="Form.order",
        collection_class=ordering_list("order"),
        # Importantly we don't `delete-orphan` here; when we move forms up/down, we remove them from the collection,
        # which would trigger the delete-orphan rule
        cascade="all",
    )

    __table_args__ = (UniqueConstraint("name", "grant_id", "version", name="uq_collection_name_version_grant_id"),)

    @property
    def test_submissions(self) -> list["Submission"]:
        return list(submission for submission in self._submissions if submission.mode == SubmissionModeEnum.TEST)

    @property
    def live_submissions(self) -> list["Submission"]:
        return list(submission for submission in self._submissions if submission.mode == SubmissionModeEnum.LIVE)


class Submission(BaseModel):
    __tablename__ = "submission"

    data: Mapped[json_scalars] = mapped_column(mutable_json_type(dbtype=JSONB, nested=True))  # type: ignore[no-untyped-call]
    mode: Mapped[SubmissionModeEnum] = mapped_column(
        SqlEnum(SubmissionModeEnum, name="submission_mode_enum", validate_strings=True)
    )

    # TODO: generated and persisted human readable references for submissions
    #       these will likely want to fit the domain need
    @property
    def reference(self) -> str:
        return str(self.id)[:8]

    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    grant_recipient_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("grant_recipient.id"))

    collection_id: Mapped[uuid.UUID]
    collection_version: Mapped[int]
    collection: Mapped[Collection] = relationship("Collection")

    events: Mapped[list["SubmissionEvent"]] = relationship(
        "SubmissionEvent", back_populates="submission", cascade="all, delete-orphan"
    )
    created_by: Mapped[User] = relationship("User", back_populates="submissions")
    grant_recipient: Mapped["GrantRecipient"] = relationship("GrantRecipient", back_populates="submissions")

    __table_args__ = (
        ForeignKeyConstraint(["collection_id", "collection_version"], ["collection.id", "collection.version"]),
        CheckConstraint(
            "mode = 'TEST' OR grant_recipient_id IS NOT NULL",
            name="ck_grant_recipient_if_live",
        ),
    )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(reference={self.reference}, mode={self.mode})"


class Form(BaseModel):
    __tablename__ = "form"

    title: Mapped[str]
    order: Mapped[int]
    slug: Mapped[str]

    collection_id: Mapped[uuid.UUID]
    collection_version: Mapped[int]
    collection: Mapped[Collection] = relationship("Collection", back_populates="forms")

    __table_args__ = (
        UniqueConstraint(
            "order", "collection_id", "collection_version", name="uq_form_order_collection", deferrable=True
        ),
        UniqueConstraint("title", "collection_id", "collection_version", name="uq_form_title_collection"),
        UniqueConstraint("slug", "collection_id", "collection_version", name="uq_form_slug_collection"),
        ForeignKeyConstraint(["collection_id", "collection_version"], ["collection.id", "collection.version"]),
    )

    # support fetching all of a forms components so that the selectin loading strategy can make one
    # round trip to the database to optimise this further only load components flat like this and
    # manage nesting through properties rather than subsequent declarative queries
    _all_components: Mapped[OrderingList["Component"]] = relationship(
        "Component",
        viewonly=True,
        order_by="Component.order",
        collection_class=ordering_list("order"),
        cascade="all, save-update, merge",
    )

    components: Mapped[OrderingList["Component"]] = relationship(
        "Component",
        order_by="Component.order",
        collection_class=ordering_list("order"),
        primaryjoin="and_(Component.form_id==Form.id, Component.parent_id.is_(None))",
        cascade="all, save-update, merge",
    )

    @cached_property
    def cached_questions(self) -> list["Question"]:
        """Consistently returns all questions in the form, respecting order and any level of nesting."""
        return [q for q in get_ordered_nested_components(self.components) if isinstance(q, Question)]

    @cached_property
    def cached_all_components(self) -> list["Component"]:
        return get_ordered_nested_components(self.components)

    def global_component_index(self, component: "Component") -> int:
        return self.cached_all_components.index(component)


def get_ordered_nested_components(components: list["Component"]) -> list["Component"]:
    """Recursively collects all components from a list of components, including nested components."""
    flat_components = []
    ordered_components = sorted(components, key=lambda c: c.order)
    for component in ordered_components:
        flat_components.append(component)
        if isinstance(component, Group):
            flat_components.extend(get_ordered_nested_components(component.components))
    return flat_components


class Component(BaseModel):
    __tablename__ = "component"

    text: Mapped[str]
    slug: Mapped[str]
    order: Mapped[int]
    hint: Mapped[Optional[str]]
    data_type: Mapped[Optional[QuestionDataType]] = mapped_column(
        SqlEnum(
            QuestionDataType,
            name="question_data_type_enum",
            validate_strings=True,
        )
    )
    name: Mapped[str]
    form_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("form.id"))
    presentation_options: Mapped[QuestionPresentationOptions] = mapped_column(
        default=QuestionPresentationOptions, server_default="{}"
    )
    type: Mapped[ComponentType] = mapped_column(
        SqlEnum(ComponentType, name="component_type_enum", validate_strings=True), default=ComponentType.QUESTION
    )
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("component.id"))
    guidance_heading: Mapped[Optional[str]]
    guidance_body: Mapped[Optional[str]]
    add_another_guidance_body: Mapped[Optional[str]]
    add_another: Mapped[bool] = mapped_column(default=False)

    # Relationships
    # todo: reason about if this should actually back populate _all_components as they might not
    #       back populate the join condition
    form: Mapped[Form] = relationship("Form", back_populates="components")

    # todo: decide if these should be lazy loaded, eagerly joined or eagerly selectin
    expressions: Mapped[list["Expression"]] = relationship(
        "Expression", back_populates="question", cascade="all, delete-orphan", order_by="Expression.created_at_utc"
    )
    data_source: Mapped["DataSource"] = relationship(
        "DataSource", cascade="all, delete-orphan", back_populates="question"
    )
    parent: Mapped["Group"] = relationship("Component", remote_side="Component.id", back_populates="components")
    components: Mapped[OrderingList["Component"]] = relationship(
        "Component",
        back_populates="parent",
        cascade="all, save-update, merge",
        order_by="Component.order",
        collection_class=ordering_list("order"),
    )

    owned_component_references: Mapped[list["ComponentReference"]] = relationship(
        "ComponentReference",
        back_populates="component",
        cascade="all, delete-orphan",
        foreign_keys="ComponentReference.component_id",
        order_by=lambda: (
            ComponentReference._sort_form_id,
            ComponentReference._sort_parent_id,
            ComponentReference._sort_order,
        ),
    )
    depended_on_by: Mapped[list["ComponentReference"]] = relationship(
        "ComponentReference",
        back_populates="depends_on_component",
        # explicitly disable cascading deletes so that ComponentReference can protect the Component
        passive_deletes="all",
        foreign_keys="ComponentReference.depends_on_component_id",
        order_by=lambda: (
            ComponentReference._sort_form_id,
            ComponentReference._sort_parent_id,
            ComponentReference._sort_order,
        ),
    )

    @property
    def conditions(self) -> list["Expression"]:
        return [expression for expression in self.expressions if expression.type_ == ExpressionType.CONDITION]

    @property
    def validations(self) -> list["Expression"]:
        return [expression for expression in self.expressions if expression.type_ == ExpressionType.VALIDATION]

    def get_expression(self, id: uuid.UUID) -> "Expression":
        try:
            return next(expression for expression in self.expressions if expression.id == id)
        except StopIteration as e:
            raise ValueError(f"Could not find an expression with id={id} in question={self.id}") from e

    @property
    def container(self) -> Union["Group", "Form"]:
        return self.parent or self.form

    @property
    def is_group(self) -> bool:
        return isinstance(self, Group)

    __table_args__ = (
        UniqueConstraint("order", "parent_id", "form_id", name="uq_component_order_form", deferrable=True),
        UniqueConstraint("slug", "form_id", name="uq_component_slug_form"),
        UniqueConstraint("text", "form_id", name="uq_component_text_form"),
        UniqueConstraint("name", "form_id", name="uq_component_name_form"),
        CheckConstraint(
            f"data_type IS NOT NULL OR type != '{ComponentType.QUESTION.value}'",
            name="ck_component_type_question_requires_data_type",
        ),
    )

    __mapper_args__ = {"polymorphic_on": type}

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(text={self.text}, is_group={self.is_group}, add_another={self.add_another})"

    # todo: this returns a question or a group or none and the types should reflect that
    #       the cleanest way to do this is probably to implement it on question and group models separately
    @property
    def add_another_container(self) -> "Component | None":
        if self.add_another:
            return self

        add_another_parent = self.parent
        while add_another_parent and not add_another_parent.add_another:
            add_another_parent = add_another_parent.parent

        if add_another_parent and add_another_parent.add_another:
            return add_another_parent

        return None


class Question(Component, SafeQidMixin):
    __mapper_args__ = {"polymorphic_identity": ComponentType.QUESTION}

    if TYPE_CHECKING:
        # database constraints ensure the question component will have a data_type
        # we reflect that its required on the question component but don't hook in a competing migration
        data_type: QuestionDataType

    @property
    def question_id(self) -> uuid.UUID:  # type: ignore[override]
        """A small proxy to support SafeQidMixin so that logic can be centralised."""
        return self.id

    # START: Helper properties for populating `QuestionForm` instances
    @property
    def data_source_items(self) -> str | None:
        if self.data_type not in [QuestionDataType.RADIOS, QuestionDataType.CHECKBOXES]:
            return None

        if (
            self.presentation_options is not None
            and self.presentation_options.last_data_source_item_is_distinct_from_others
        ):
            return "\n".join(item.label for item in self.data_source.items[:-1])

        return "\n".join([item.label for item in self.data_source.items])

    @property
    def separate_option_if_no_items_match(self) -> bool | None:
        if self.data_type not in [QuestionDataType.RADIOS, QuestionDataType.CHECKBOXES]:
            return None

        return (
            self.presentation_options.last_data_source_item_is_distinct_from_others
            if self.presentation_options is not None
            else None
        )

    @property
    def none_of_the_above_item_text(self) -> str | None:
        if self.data_type not in [QuestionDataType.RADIOS, QuestionDataType.CHECKBOXES]:
            return None

        if (
            self.presentation_options is not None
            and self.presentation_options.last_data_source_item_is_distinct_from_others
        ):
            return self.data_source.items[-1].label

        return "Other"

    @property
    def rows(self) -> int | None:
        return (
            self.presentation_options.rows.value
            if self.data_type == QuestionDataType.TEXT_MULTI_LINE and self.presentation_options.rows
            else None
        )

    @property
    def word_limit(self) -> int | None:
        return self.presentation_options.word_limit if self.data_type == QuestionDataType.TEXT_MULTI_LINE else None

    @property
    def prefix(self) -> str | None:
        return self.presentation_options.prefix if self.data_type == QuestionDataType.INTEGER else None

    @property
    def suffix(self) -> str | None:
        return self.presentation_options.suffix if self.data_type == QuestionDataType.INTEGER else None

    @property
    def width(self) -> str | None:
        return (
            self.presentation_options.width.value
            if self.data_type == QuestionDataType.INTEGER and self.presentation_options.width
            else None
        )

    @property
    def approximate_date(self) -> bool | None:
        return self.presentation_options.approximate_date if self.data_type == QuestionDataType.DATE else None

    # END: Helper properties for populating `QuestionForm` instances


class Group(Component):
    __mapper_args__ = {"polymorphic_identity": ComponentType.GROUP}

    if TYPE_CHECKING:
        # reflect that groups will never have a data type but don't hook in a competing migration
        data_type: None

    # todo: rename to something that makes it clear this is processed, something like all_nested_questions
    @cached_property
    def cached_questions(self) -> list["Question"]:
        return [q for q in get_ordered_nested_components(self.components) if isinstance(q, Question)]

    @cached_property
    def cached_all_components(self) -> list["Component"]:
        return get_ordered_nested_components(self.components)

    @property
    def same_page(self) -> bool:
        return bool(self.presentation_options.show_questions_on_the_same_page) if self.presentation_options else False

    @cached_property
    def has_nested_groups(self) -> bool:
        return any([q for q in self.components if q.is_group])

    @classmethod
    def _count_nested_group_levels(cls, group: "Group") -> int:
        if not group.parent:
            return 0
        return 1 + group._count_nested_group_levels(group=group.parent)

    @cached_property
    def nested_group_levels(self) -> int:
        return Group._count_nested_group_levels(group=self)

    @cached_property
    def can_have_child_group(self) -> bool:
        """Whether or not this groups is allowed to have a child group,
        based on the maximum number of levels of nested groups"""
        return bool(self.nested_group_levels < current_app.config["MAX_NESTED_GROUP_LEVELS"])

    @property
    def contains_add_another_components(self) -> bool:
        """Whether or not this group contains any components that have add_another set to True"""
        for component in self.cached_all_components:
            if component.add_another:
                return True
        return False

    @property
    def contains_questions_depended_on_elsewhere(self) -> bool:
        """Whether or not any questions in this group (or nested groups) are depended on elsewhere"""
        for component in self.cached_all_components:
            if len(component.depended_on_by) > 0:
                return True

        return False

    @property
    def questions_in_add_another_summary(self) -> list["Question"]:
        if not self.add_another:
            return []
        if self.presentation_options.add_another_summary_line_question_ids:
            return [
                question
                for question in self.cached_questions
                if question.id in self.presentation_options.add_another_summary_line_question_ids
            ] or self.cached_questions
        return self.cached_questions


class SubmissionEvent(BaseModel):
    __tablename__ = "submission_event"

    key: Mapped[SubmissionEventKey] = mapped_column(
        SqlEnum(SubmissionEventKey, name="submission_event_key_enum", validate_strings=True)
    )

    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submission.id"))
    submission: Mapped[Submission] = relationship("Submission", back_populates="events")

    form_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("form.id"))
    form: Mapped[Optional[Form]] = relationship("Form")

    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    created_by: Mapped[User] = relationship("User")


class Expression(BaseModel):
    __tablename__ = "expression"

    statement: Mapped[str]

    context: Mapped[json_flat_scalars] = mapped_column(mutable_json_type(dbtype=JSONB, nested=True))  # type: ignore[no-untyped-call]

    type_: Mapped[ExpressionType] = mapped_column(
        "type", SqlEnum(ExpressionType, name="expression_type_enum", validate_strings=True)
    )

    managed_name: Mapped[Optional[ManagedExpressionsEnum]] = mapped_column(
        SqlEnum(ManagedExpressionsEnum, name="managed_expression_enum", validate_strings=True, nullable=True)
    )

    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("component.id"))
    question: Mapped[Component] = relationship("Component", back_populates="expressions")

    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    created_by: Mapped[User] = relationship("User")

    component_references: Mapped[list["ComponentReference"]] = relationship(
        "ComponentReference",
        back_populates="expression",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index(
            "uq_type_validation_unique_key",
            "type",
            "question_id",
            "managed_name",
            postgresql_where=f"type = '{ExpressionType.VALIDATION.value}'::expression_type_enum",
            unique=True,
        ),
        Index(
            "uq_type_condition_unique_question",
            "type",
            "question_id",
            "managed_name",
            text("(context ->> 'question_id')"),
            postgresql_where=f"type = '{ExpressionType.CONDITION.value}'::expression_type_enum",
            unique=True,
        ),
    )

    @property
    def is_managed(self) -> bool:
        return bool(self.managed_name)

    @property
    def managed(self) -> "ManagedExpression":
        return get_managed_expression(self)

    @classmethod
    def from_managed(
        cls,
        managed_expression: "ManagedExpression",
        created_by: "User",
    ) -> "Expression":
        return Expression(
            statement=managed_expression.statement,
            context=managed_expression.model_dump(mode="json"),
            created_by=created_by,
            type_=ExpressionType.CONDITION,
            managed_name=managed_expression._key,
        )

    @property
    def required_functions(self) -> dict[str, Union[Callable[[Any], Any], type[Any]]]:
        if self.managed_name:
            return self.managed.required_functions

        # In future, make this return a default list of functions for non-managed expressions
        return {}


class DataSource(BaseModel):
    __tablename__ = "data_source"

    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("component.id"))
    question: Mapped[Question] = relationship("Question", back_populates="data_source", uselist=False)

    items: Mapped[list["DataSourceItem"]] = relationship(
        "DataSourceItem",
        back_populates="data_source",
        order_by="DataSourceItem.order",
        collection_class=ordering_list("order"),
        lazy="selectin",
        # Importantly we don't `delete-orphan` here; when we move choices around, we remove them from the collection,
        # which would trigger the delete-orphan rule
        cascade="all, save-update, merge",
    )

    __table_args__ = (UniqueConstraint("question_id", name="uq_question_id"),)


class DataSourceItem(BaseModel):
    __tablename__ = "data_source_item"

    data_source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_source.id"))
    order: Mapped[int]
    key: Mapped[CIStr]
    label: Mapped[str]

    data_source: Mapped[DataSource] = relationship("DataSource", back_populates="items", uselist=False)
    component_references: Mapped[list["ComponentReference"]] = relationship(
        "ComponentReference",
        back_populates="depends_on_data_source_item",
        # explicitly disable cascading deletes so that ComponentReference can protect the DataSourceItems
        passive_deletes="all",
    )

    __table_args__ = (
        UniqueConstraint("data_source_id", "order", name="uq_data_source_id_order", deferrable=True),
        UniqueConstraint("data_source_id", "key", name="uq_data_source_id_key"),
    )


class ComponentReference(BaseModel):
    """A table to track when components (and their expressions) create a dependency upon another component.

    As of creating this table, the common examples are:

    q2 has a condition (c) that checks the answer to q1 to decide if q2 should be shown:
      => ComponentReference(component_id=q2.id, expression_id=c.id, depends_on_component_id=q1.id)

    q2 has text that shows the answer to q1:
      => ComponentReference(component_id=q2.id, expression_id=None, depends_on_component_id=q1.id)
    """

    __tablename__ = "component_reference"

    component_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("component.id"))
    component: Mapped[Component] = relationship(
        "Component", foreign_keys=[component_id], back_populates="owned_component_references"
    )

    expression_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("expression.id"))
    expression: Mapped[Expression | None] = relationship("Expression")

    depends_on_component_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("component.id"))
    depends_on_component: Mapped[Component] = relationship(
        "Component", foreign_keys=[depends_on_component_id], back_populates="depended_on_by"
    )

    depends_on_data_source_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("data_source_item.id"))
    depends_on_data_source_item: Mapped[DataSourceItem | None] = relationship("DataSourceItem")

    # Mirror columns from the referenced component for ordering the Component.component_references relationship
    _sort_form_id: Mapped[uuid.UUID] = column_property(
        select(Component.form_id).where(Component.id == foreign(depends_on_component_id)).scalar_subquery()
    )
    _sort_parent_id: Mapped[uuid.UUID | None] = column_property(
        select(Component.parent_id).where(Component.id == foreign(depends_on_component_id)).scalar_subquery()
    )
    _sort_order: Mapped[int] = column_property(
        select(Component.order).where(Component.id == foreign(depends_on_component_id)).scalar_subquery()
    )


class GrantRecipient(BaseModel):
    __tablename__ = "grant_recipient"

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisation.id"))
    grant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("grant.id"))

    organisation: Mapped[Organisation] = relationship("Organisation")
    grant: Mapped[Grant] = relationship("Grant", back_populates="grant_recipients")

    submissions: Mapped[list[Submission]] = relationship("Submission", back_populates="grant_recipient")
