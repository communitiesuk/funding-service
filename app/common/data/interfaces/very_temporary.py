import uuid
from typing import Dict, Optional

from sqlalchemy import func
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Session

from app import db
from app.common.data.models import (
    Component,
    DataSource,
    DataSourceItem,
    DataSourceItemReference,
    Expression,
    Group,
    Question,
)


def deep_copy_component(
    component: Component,
    session: Session = None,
    parent_id: Optional[uuid.UUID] = None,
    form_id: Optional[uuid.UUID] = None,
    preserve_order: bool = True,
) -> Component:
    """
    Deep copy a Component (Question or Group) with all its nested relationships,
    generating new PKs for all entities.

    Args:
        component: The Component instance to copy (Question or Group)
        session: SQLAlchemy session for adding new entities
        parent_id: Optional parent_id for the new component (for nested components)
        form_id: Optional form_id to assign to the new component
        preserve_order: Whether to preserve the order field values

    Returns:
        The newly created Component with all nested relationships copied
    """
    if session is None:
        session = db.session

    # Create mapping to track old->new IDs for fixing references
    id_mapping: Dict[uuid.UUID, uuid.UUID] = {}

    def copy_component_recursive(
        comp: Component, parent_id: Optional[uuid.UUID] = None, form_id: Optional[uuid.UUID] = None
    ) -> Component:
        """Recursively copy a component and all its children."""

        # Get the component's attributes, excluding relationships and PKs
        mapper = inspect(comp.__class__)
        attrs = {}

        for column in mapper.columns:
            key = column.key
            # Skip primary key, foreign keys we're changing, and relationship backrefs
            if key not in ["id", "created_at_utc", "updated_at_utc"]:
                value = getattr(comp, key)
                if value is not None:
                    attrs[key] = value

        # Set the new parent and form relationships
        if parent_id is not None:
            attrs["parent_id"] = parent_id
        if form_id is not None:
            attrs["form_id"] = form_id
        elif comp.form_id and parent_id is None:
            # If this is a top-level component and form_id wasn't provided, preserve it
            attrs["form_id"] = comp.form_id

        # Preserve order unless specified otherwise
        if not preserve_order and "order" in attrs:
            # You might want to reset or adjust order here
            pass

        # Create new component instance based on type
        if isinstance(comp, Question):
            new_component = Question(**attrs)
        elif isinstance(comp, Group):
            new_component = Group(**attrs)
        else:
            new_component = Component(**attrs)

        for x in range(1, 10):
            if f" {x}" in new_component.text:
                new_component.text = new_component.text.replace(f" {x}", f" {x + 1}")
                new_component.name = new_component.text.replace(f" {x}", f" {x + 1}")
                new_component.slug = new_component.text.replace(f"-{x}", f"-{x + 1}")
                break

        # Track ID mapping
        old_id = comp.id
        session.add(new_component)
        session.flush()  # Get the new ID
        id_mapping[old_id] = new_component.id
        print(f"copying {old_id} -> {new_component.id}: {new_component}")

        # Copy expressions
        for expression in comp.expressions:
            expression_question_id = uuid.UUID(expression.context["question_id"])
            new_expression_question_id = id_mapping.get(expression_question_id, expression_question_id)
            copy_expression(expression, new_component.id, new_expression_question_id=new_expression_question_id)

        # Copy data source (for Questions)
        if hasattr(comp, "data_source") and comp.data_source:
            copy_data_source(comp.data_source, new_component.id)

        # Copy nested components (for Groups)
        if hasattr(comp, "components") and comp.components:
            for child_comp in comp.components:
                copy_component_recursive(child_comp, parent_id=new_component.id, form_id=new_component.form_id)

        return new_component

    def copy_expression(
        expr: Expression, new_question_id: uuid.UUID, new_expression_question_id: uuid.UUID
    ) -> Expression:
        """Copy an expression and its references."""

        # Copy expression attributes
        attrs = {
            "statement": expr.statement,
            "context": expr.context.copy() if expr.context else {},
            "type": expr.type,
            "managed_name": expr.managed_name,
            "question_id": new_question_id,
            "created_by_id": expr.created_by_id,
        }
        old_expression_question_id = uuid.UUID(attrs["context"]["question_id"])
        attrs["statement"] = attrs["statement"].replace(
            f"q_{old_expression_question_id.hex}", f"q_{new_expression_question_id.hex}"
        )
        attrs["context"]["question_id"] = str(new_expression_question_id)

        new_expr = Expression(**attrs)
        session.add(new_expr)
        session.flush()

        # Copy data source item references
        for ref in expr.data_source_item_references:
            # We'll need to update these after all data source items are created
            # Store them for later processing
            if not hasattr(copy_expression, "pending_refs"):
                copy_expression.pending_refs = []
            copy_expression.pending_refs.append((new_expr.id, ref.data_source_item_id))

        return new_expr

    def copy_data_source(ds: DataSource, new_question_id: uuid.UUID) -> DataSource:
        """Copy a data source and all its items."""

        new_ds = DataSource(question_id=new_question_id)
        session.add(new_ds)
        session.flush()

        # Copy data source items
        item_id_mapping = {}
        for item in ds.items:
            new_item = DataSourceItem(data_source_id=new_ds.id, order=item.order, key=item.key, label=item.label)
            session.add(new_item)
            session.flush()
            item_id_mapping[item.id] = new_item.id

        # Now process any pending expression references
        if hasattr(copy_expression, "pending_refs"):
            for expr_id, old_item_id in copy_expression.pending_refs:
                if old_item_id in item_id_mapping:
                    new_ref = DataSourceItemReference(
                        expression_id=expr_id, data_source_item_id=item_id_mapping[old_item_id]
                    )
                    session.add(new_ref)

        return new_ds

    # Start the recursive copy
    new_component = copy_component_recursive(component, parent_id, form_id)

    # Clean up any temporary attributes
    if hasattr(copy_expression, "pending_refs"):
        del copy_expression.pending_refs

    session.flush()
    return new_component


# Example usage:
def duplicate_component_example(session: Session, component_id: uuid.UUID) -> Component:
    """
    Example function showing how to use deep_copy_component.

    Args:
        session: SQLAlchemy session
        component_id: ID of the component to duplicate

    Returns:
        The newly created duplicate component
    """
    # Fetch the original component
    original = session.query(Component).filter_by(id=component_id).first()

    if not original:
        raise ValueError(f"Component with id {component_id} not found")

    # Create a deep copy
    # You can optionally specify a different form_id or parent_id
    duplicate = deep_copy_component(
        component=original,
        session=session,
        parent_id=original.parent_id,  # Keep same parent, or change as needed
        form_id=original.form_id,  # Keep same form, or change as needed
        preserve_order=True,
    )

    # Commit the changes
    session.commit()

    return duplicate


# Alternative: If you want to duplicate and add to the same form at a different position
def duplicate_component_in_form(
    session: Session, component_id: uuid.UUID, new_order: Optional[int] = None
) -> Component:
    """
    Duplicate a component and add it to the same form at a new position.

    Args:
        session: SQLAlchemy session
        component_id: ID of the component to duplicate
        new_order: Optional order position for the duplicate (defaults to end)

    Returns:
        The newly created duplicate component
    """
    original = session.query(Component).filter_by(id=component_id).first()

    if not original:
        raise ValueError(f"Component with id {component_id} not found")

    # If no new order specified, add at the end
    if new_order is None:
        if original.parent_id:
            # Get max order of siblings
            max_order = (
                session.query(func.max(Component.order))
                .filter_by(parent_id=original.parent_id, form_id=original.form_id)
                .scalar()
            )
        else:
            # Get max order in form
            max_order = (
                session.query(func.max(Component.order)).filter_by(form_id=original.form_id, parent_id=None).scalar()
            )
        new_order = (max_order or 0) + 1

    # Create the duplicate
    duplicate = deep_copy_component(
        component=original,
        session=session,
        parent_id=original.parent_id,
        form_id=original.form_id,
        preserve_order=False,  # We'll set order manually
    )

    # Set the new order
    duplicate.order = new_order

    # If inserting in middle, shift other components
    if new_order is not None:
        siblings = (
            session.query(Component)
            .filter(
                Component.form_id == original.form_id,
                Component.parent_id == original.parent_id,
                Component.order >= new_order,
                Component.id != duplicate.id,
            )
            .all()
        )

        for sibling in siblings:
            sibling.order += 1

    session.commit()
    return duplicate
