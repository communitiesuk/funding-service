from typing import TYPE_CHECKING, cast

from app.common.data.types import QuestionDataType

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
    Check if two components are both in the same add another group, or if q2's container repeats over
    q1's container - which makes q1 referenceable from within q2's container, since q2's container is
    materialised with exactly one entry per entry of q1's container (see
    `SubmissionHelper.reconcile_repeating_entries`).
    """
    if q1.add_another_container is None or q2.add_another_container is None:
        return False

    if q1.add_another_container == q2.add_another_container:
        return True

    q2_container = q2.add_another_container
    return q2_container.is_group and cast("Group", q2_container).repeats_over == q1.add_another_container


def components_in_valid_add_another_combination(
    attached_to_component: Component, referenced_components: list[Component | None]
) -> bool:
    filtered_components = [c for c in referenced_components if c is not None]
    if not any(c.add_another_container for c in filtered_components):
        return True

    all_add_another_containers = set(c.add_another_container for c in filtered_components if c.add_another_container)

    attached_container = attached_to_component.add_another_container
    if not attached_container:
        return len(all_add_another_containers) == 0

    all_add_another_containers.add(attached_container)

    allowed_containers = {attached_container}
    if attached_container.is_group:
        source = cast("Group", attached_container).repeats_over
        if source is not None:
            allowed_containers.add(source)

    return all_add_another_containers <= allowed_containers


def get_referenceable_questions(
    form: Form,
    current_component: Component | None = None,
    parent_component: Group | None = None,
    limit_to_data_type: set[QuestionDataType] | None = None,
    include_this_component: bool | None = None,
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

    If limit_to_data_type is provided, only questions with a data type in the given set will be returned.
    """
    questions = form.cached_questions
    limit_to_components_before = current_component

    # Adding a question directly within a section
    if current_component is None and parent_component is None:
        limit_to_components_before = None

    # Can't reference questions from later sections
    elif current_component and form.order > current_component.form.order:
        return []

    # If referencing an earlier form, all questions are visible
    elif current_component and form.order < current_component.form.order:
        limit_to_components_before = None

    # Adding a question within a group
    elif current_component is None and parent_component is not None:
        limit_to_components_before = (
            parent_component
            if parent_component.same_page or len(parent_component.cached_questions) == 0
            else parent_component.cached_questions[-1]
        )

    include_this_component_and_descendents = (
        True if include_this_component is True and current_component is not None else False
    )

    if limit_to_components_before is not None:
        questions = [
            q
            for q in questions
            if (
                include_this_component_and_descendents
                and current_component
                and (
                    (current_component.is_question and q == current_component)
                    or (current_component.is_group and q.is_descendant_of(current_component))
                )
            )
            or (
                (not current_component or q != limit_to_components_before)
                and form.global_component_index(q) <= form.global_component_index(limit_to_components_before)
                and not questions_in_same_page_group(q, limit_to_components_before)
                and (
                    questions_in_same_add_another_container(q, limit_to_components_before)
                    or not q.add_another_container
                )
            )
        ]
    else:
        # A repeating container's questions may still reference its source container's questions even
        # when the source lives in an earlier section (so `limit_to_components_before` above is None).
        repeats_over_source = (
            cast("Group", current_component.add_another_container).repeats_over
            if current_component
            and current_component.add_another_container
            and current_component.add_another_container.is_group
            else None
        )
        questions = [
            q for q in questions if not q.add_another_container or q.add_another_container == repeats_over_source
        ]

    if limit_to_data_type is not None:
        questions = [q for q in questions if q.data_type in limit_to_data_type]

    return questions
