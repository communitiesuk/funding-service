from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.common.data.models import Component, Form, Question


def questions_in_same_page_group(c1: "Component", c2: "Component") -> bool:
    """
    Check if two components are in the same group and that group shows on the same page.
    If they are then they shouldn't reference each other.

    Note: this relies on a current tech/product constraint that the "same page" setting can only be turned on for the
    leaf group in a set of nested groups (so we don't have to check parent groups for the same-page setting).
    """
    return True if c1.parent and c2.parent and c1.parent == c2.parent and c1.parent.same_page else False


def get_referenceable_questions(form: "Form", current_component: "Component | None" = None) -> list["Question"]:
    """
    Return a list of questions from the current form that could be referenced from the current component, determined by:
    - Question comes before the current component in the form
    - Question is not in the same 'same page' page group as the current component

    If current component is None then return all cached questions in the form.
    """
    questions = form.cached_questions

    if current_component is None:
        return questions
    else:
        return [
            q
            for q in questions
            if (
                form.global_component_index(q) < form.global_component_index(current_component)
                and not questions_in_same_page_group(q, current_component)
            )
        ]
