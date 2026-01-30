from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from app.common.data.models import Component, Form, Group, Question


def questions_in_same_page_group(c1: Question, c2: Component) -> bool:
    """
    Check if two components are in the same group and that group shows on the same page.
    If they are then they shouldn't reference each other.

    Note: this relies on a current tech/product constraint that the "same page" setting can only be turned on for the
    leaf group in a set of nested groups (so we don't have to check parent groups for the same-page setting).
    """
    c2_parent: Group | None = cast("Group", c2) if c2.is_group else cast("Group | None", c2.parent)

    return True if c1.parent and c2_parent and c1.parent == c2_parent and c2_parent.same_page else False


def questions_in_same_add_another_container(q1: Component, q2: Component) -> bool:
    """
    Check if two components are both in the same add another group.
    """
    return (
        q1.add_another_container is not None
        and q2.add_another_container is not None
        and q1.add_another_container == q2.add_another_container
    )


def get_referenceable_questions(
    form: Form, current_component: Component | None = None, parent_component: Group | None = None
) -> list[Question]:
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

    # Can't reference questions from later sections
    elif current_component and form.order > current_component.form.order:
        return []

    # If referencing an earlier form, all questions are visible
    elif current_component and form.order < current_component.form.order:
        return questions

    # Adding a question within a group
    elif current_component is None and parent_component is not None:
        limit_to_components_before = (
            parent_component
            if parent_component.same_page or len(parent_component.cached_questions) == 0
            else parent_component.cached_questions[-1]
        )

    assert limit_to_components_before is not None
    questions = [
        q
        for q in questions
        if (
            (not current_component or q != limit_to_components_before)
            and form.global_component_index(q) <= form.global_component_index(limit_to_components_before)
            and not questions_in_same_page_group(q, limit_to_components_before)
            and (questions_in_same_add_another_container(q, limit_to_components_before) or not q.add_another_container)
        )
    ]
    return questions
