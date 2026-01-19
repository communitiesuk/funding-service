from typing import TYPE_CHECKING, cast

from app.common.qid import SafeQidMixin

if TYPE_CHECKING:
    from app.common.data.models import Collection, Component, Form, Group, Question


def questions_in_same_page_group(c1: "Question", c2: "Component") -> bool:
    """
    Check if two components are in the same group and that group shows on the same page.
    If they are then they shouldn't reference each other.

    Note: this relies on a current tech/product constraint that the "same page" setting can only be turned on for the
    leaf group in a set of nested groups (so we don't have to check parent groups for the same-page setting).
    """
    c2_parent: "Group | None" = cast("Group", c2) if c2.is_group else cast("Group | None", c2.parent)

    return True if c1.parent and c2_parent and c1.parent == c2_parent and c2_parent.same_page else False


def questions_in_same_add_another_container(q1: "Component", q2: "Component") -> bool:
    """
    Check if two components are both in the same add another group.
    """
    return (
        q1.add_another_container is not None
        and q2.add_another_container is not None
        and q1.add_another_container == q2.add_another_container
    )


def get_earlier_forms(form: "Form") -> list["Form"]:
    """Return a list of forms that come before the given form in the collection, ordered by their order field."""
    return sorted(
        [f for f in form.collection.forms if f.order < form.order],
        key=lambda f: f.order,
    )


def get_earlier_collections(collection: "Collection") -> list["Collection"]:
    """Return a list of forms that come before the given form in the collection, ordered by their submission closing date."""
    return sorted(
        [
            c
            for c in collection.grant.collections
            if c.submission_period_end_date < collection.submission_period_end_date
        ],
        key=lambda c: c.submission_period_end_date,
    )


def get_referenceable_questions_from_form(source_form: "Form") -> list["Question"]:
    """Return all questions from a source form that can be referenced (excludes add another questions)."""
    return [q for q in source_form.cached_questions if not q.add_another_container]


def get_referenceable_questions(
    form: "Form", current_component: "Component | None" = None, parent_component: "Group | None" = None
) -> list["Question"]:
    """
    Return a list of questions from the current form that could be referenced from the current component, determined by:
    - Question comes before the current component in the form
    - Question is not in the same 'same page' page group as the current component
    - Question is not in an add another group, or if it is it's in the same add another group as the current component

    If current component is None then return all cached questions in the form. Current component will be none when the
    user is trying to reference questions while in the *add question* flow, ie that question hasn't yet been persisted
    to the DB at all.

    If parent component is None then we're adding a question to the top-level of the section, which will add it to the
    end and therefore all questions are initially in-scope. If parent component is not None, then it's being added to a
    group and only questions before that in the global order should be available).
    """
    questions = form.cached_questions
    limit_to_components_before = current_component

    # Adding a question directly within a section
    if current_component is None and parent_component is None:
        return questions

    # Adding a question within a group
    elif current_component is None and parent_component is not None:
        limit_to_components_before = (
            parent_component
            if parent_component.same_page or len(parent_component.cached_questions) == 0
            else parent_component.cached_questions[-1]
        )

    assert limit_to_components_before is not None
    id_of_referenced_add_another_container = (
        SafeQidMixin.safe_qid_to_id(current_component.add_another_container.add_another_iterate_ref)
        if current_component
        and current_component.add_another_container
        and current_component.add_another_container.add_another_iterate_ref
        else None
    )
    questions = [
        q
        for q in questions
        if (
            (not current_component or q != limit_to_components_before)
            and form.global_component_index(q) <= form.global_component_index(limit_to_components_before)
            and not questions_in_same_page_group(q, limit_to_components_before)
            and (questions_in_same_add_another_container(q, limit_to_components_before) or not q.add_another_container)
            or (q.add_another_container and q.add_another_container.id == id_of_referenced_add_another_container)
        )
    ]
    return questions
