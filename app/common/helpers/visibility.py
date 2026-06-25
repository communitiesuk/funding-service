from graphlib import TopologicalSorter
from typing import TYPE_CHECKING, cast
from uuid import UUID

from app.common.data.submission_data_manager import SubmissionDataManager
from app.common.data.types import ComponentVisibilityState, ConditionsOperator, ExpressionType
from app.common.expressions import (
    DisallowedExpression,
    ExpressionContext,
    UndefinedFunctionInExpression,
    UndefinedOperatorInExpression,
    UndefinedVariableInExpression,
    evaluate,
)

if TYPE_CHECKING:
    from app.common.data.models import Collection, Component, ComponentReference, Expression, Question


class CollectionDependencyGraph:
    """A directed acyclic graph of component dependencies with topological ordering.

    Built from a Collection's schema (no answers involved). Components are ordered
    such that dependencies come before dependents, enabling a single forward pass
    to resolve visibility.
    """

    def __init__(self, collection: Collection):
        self._components: dict[UUID, Component] = {}
        self._dependencies: dict[UUID, set[UUID]] = {}
        self._is_conditional_ignoring_parents: dict[UUID, bool] = {}
        self._sorted_ids: list[UUID] = []
        self._build(collection)

    def _build(self, collection: Collection) -> None:

        for form in collection.forms:
            for component in form.cached_all_components:
                self._components[component.id] = component
                self._dependencies[component.id] = set()
                self._is_conditional_ignoring_parents[component.id] = False

        for component_id, component in self._components.items():
            parent_id = component.parent_id or (component.parent.id if component.parent else None)
            if parent_id and parent_id in self._components:
                self._dependencies[component_id].add(parent_id)

            for ref in component.owned_component_references:
                # Only check references where the component is depending on another component; specifically here we are
                # ignoring where a component references a data set, which won't affect dependencies within the
                # collection itself
                dep = ref.depends_on_component
                dep_id = dep.id if dep else ref.depends_on_component_id
                if not dep_id or dep_id == component_id or dep_id not in self._components:
                    continue

                # Ignore group validation - the group comes 'before' its children, but it validates the values of its
                # children. Group validation does not affect the rendering order or dependencies of a collection in
                # any way.
                if component.is_group and ref.expression and ref.expression.type_ == ExpressionType.VALIDATION:
                    continue

                # Record that `component` has a dependency on `dep`
                self._dependencies[component_id].add(dep_id)

                # A helper cache to track whether this component itself specifically has some condition on it; this
                # powers the 'Conditional' tag in Deliver.
                self._is_conditional_ignoring_parents[component_id] = bool(
                    self._is_conditional_ignoring_parents[component_id]
                    or self._is_conditional_ignoring_parents[dep_id]
                    or (ref.expression and ref.expression.type_ == ExpressionType.CONDITION)
                )

        self._topological_sort()

    def _topological_sort(self) -> None:
        sorter = TopologicalSorter(self._dependencies)
        self._sorted_ids = list(sorter.static_order())

    @property
    def sorted_components(self) -> list[Component]:
        return [self._components[cid] for cid in self._sorted_ids]

    @property
    def components(self) -> dict[UUID, Component]:
        return self._components

    def dependencies_of(self, component: Component) -> set[UUID]:
        dependencies = set(self._dependencies[component.id])

        return dependencies

    def is_conditional_ignoring_parents(self, component: Component):
        """
        Returns True if this component has direct conditional requirements, either from self-owned
        conditions or from direct component references on components that are conditional.

        It does *not* check conditions on its parent chain. This is used to show the 'Conditional' tag on the
        `list questions` page; if we checked parents then every single question inside a conditional group would show
        the tag, which is not useful.

        This returns True if the component has conditions itself, or it references a question which is itself
        conditional.
        """
        return self._is_conditional_ignoring_parents[component.id]


class VisibilityResolver:
    """Resolves visibility for all components in a single topological pass.

    Walks the topological order from the graph, evaluating each component's own
    conditions and checking cached dependency visibility, to build a lookup table
    of ComponentVisibilityState for every component.

    A future optimisation might allow restricting the resolution of the graph to only a subset of questions so that
    we don't analyse the full collection dependency graph when eg we only want to render a single question on the page.
    This is left as an exercise for a future developer.
    """

    def __init__(
        self,
        graph: CollectionDependencyGraph,
        context: ExpressionContext,
        data_manager: SubmissionDataManager,
    ):
        self._graph = graph
        self._context = context
        self._data_manager = data_manager
        self._cache: dict[UUID, ComponentVisibilityState] = {}
        self._add_another_cache: dict[tuple[UUID, int], ComponentVisibilityState] = {}

        self._resolve()

    def _resolve(self) -> None:
        container_counts: dict[UUID, int] = {}
        for component in self._graph.sorted_components:
            self._resolve_component(component)

            container = component.add_another_container
            if container is None:
                continue

            if container.id not in container_counts:
                container_counts[container.id] = self._data_manager.get_count_for_add_another(container)

            for index in range(container_counts[container.id]):
                self.get_visibility_for_add_another(component.id, index)

    def _resolve_component(self, component: Component) -> ComponentVisibilityState:
        if component.id in self._cache:
            return self._cache[component.id]

        state = self._compute_visibility(component)
        self._cache[component.id] = state
        return state

    @staticmethod
    def _component_reference_is_skippable(component: Component, ref: ComponentReference):
        depends_on_component = ref.depends_on_component

        # Non-component references, eg data sources
        if depends_on_component is None:
            return True

        # There is nothing to check if a component 'depends on' itself; we no longer record these in
        # ComponentReferences, but here for extra guarantee
        if depends_on_component.id == component.id:
            return True

        # Group validation references do not affect the group's visibility; they validate the values of other
        # components. These are excluded from the dependency graph (see CollectionDependencyGraph._build), so the
        # depended-on component may not be resolved yet when we resolve the group.
        if component.is_group and ref.expression and ref.expression.type_ == ExpressionType.VALIDATION:
            return True

        # We don't check references where the depended-on thing is a child of this component; this can happen
        # where a question group has validation on its children.
        if depends_on_component.is_descendant_of(component):
            return True

        return False

    def _compute_visibility(self, component: Component) -> ComponentVisibilityState:
        parent_id = component.parent_id or (component.parent.id if component.parent else None)
        if parent_id:
            parent_state = self._cache[parent_id]
            if parent_state != ComponentVisibilityState.VISIBLE:
                return parent_state

        ref_state = self._check_references(component)

        conditions = component.conditions

        # For ALL operator (or no conditions), a HIDDEN dependency means the component is definitely
        # HIDDEN — all conditions must pass, and a condition with a HIDDEN dep can never pass.
        # For ANY operator with conditions, we can't short-circuit: a HIDDEN dep only invalidates
        # the conditions that reference it, while other conditions may still evaluate to True.
        if ref_state == ComponentVisibilityState.HIDDEN:
            if not conditions or component.conditions_operator != ConditionsOperator.ANY:
                return ComponentVisibilityState.HIDDEN

        if not conditions:
            return ref_state  # VISIBLE or UNDETERMINED based on references

        condition_result = self._evaluate_conditions(
            component.conditions_operator, conditions, self._context, component
        )

        if condition_result == ComponentVisibilityState.HIDDEN:
            return ComponentVisibilityState.HIDDEN
        if condition_result == ComponentVisibilityState.UNDETERMINED:
            return ComponentVisibilityState.UNDETERMINED

        # For ALL: an unanswered ref means a condition can't be evaluated yet → UNDETERMINED.
        # For ANY: condition evaluation already accounts for per-condition ref states, so if it
        # returned VISIBLE, the successful condition's deps are satisfied regardless of other refs.
        if (
            component.conditions_operator != ConditionsOperator.ANY
            and ref_state == ComponentVisibilityState.UNDETERMINED
        ):
            return ComponentVisibilityState.UNDETERMINED

        return ComponentVisibilityState.VISIBLE

    def _check_references(self, component: Component) -> ComponentVisibilityState:
        result = ComponentVisibilityState.VISIBLE

        for ref in component.owned_component_references:
            dep = ref.depends_on_component

            if self._component_reference_is_skippable(component, ref):
                continue

            # _component_reference_is_skipped checks that `dep` is not None
            dep = cast("Component", dep)

            if component.add_another_container:
                # We cannot check references here for anything in an 'add another' container; that needs to use
                # `_check_references_for_add_another` to check the correct index.
                continue

            dep_state = self._cache[dep.id]
            if dep_state == ComponentVisibilityState.HIDDEN:
                return ComponentVisibilityState.HIDDEN

            if not dep.is_question:
                raise RuntimeError(f"Components can only depend on questions, but got a non-question {dep.id}")

            if self._data_manager.get(cast("Question", dep)) is None:
                result = ComponentVisibilityState.UNDETERMINED

        return result

    def _evaluate_conditions(
        self,
        operator: ConditionsOperator,
        conditions: list[Expression],
        context: ExpressionContext,
        component: Component,
    ) -> ComponentVisibilityState:
        undefined_expression_ids: set[UUID] = set()
        undefined_resolution: ComponentVisibilityState | None = None
        results: list[ComponentVisibilityState] = []

        for condition in conditions:
            try:
                results.append(
                    ComponentVisibilityState.VISIBLE
                    if evaluate(condition, context)
                    else ComponentVisibilityState.HIDDEN
                )

            except (
                UndefinedVariableInExpression,
                DisallowedExpression,
                UndefinedFunctionInExpression,
                UndefinedOperatorInExpression,
            ):
                undefined_expression_ids.add(condition.id)

        if undefined_expression_ids:
            undefined_resolution = self._resolve_undetermined(component, undefined_expression_ids)
            results.append(undefined_resolution)

        if operator not in {ConditionsOperator.ALL, ConditionsOperator.ANY}:
            raise RuntimeError(f"Invalid conditions operator: {operator}")

        aggregator = all if operator == ConditionsOperator.ALL else any
        if aggregator(result == ComponentVisibilityState.VISIBLE for result in results):
            return ComponentVisibilityState.VISIBLE

        return undefined_resolution or ComponentVisibilityState.HIDDEN

    def _resolve_undetermined(
        self,
        component: Component,
        undefined_expression_ids: set[UUID],
    ) -> ComponentVisibilityState:
        for ref in component.owned_component_references:
            dep = ref.depends_on_component

            if self._component_reference_is_skippable(component, ref):
                continue

            # _component_reference_is_skipped checks that `dep` is not None
            dep = cast("Component", dep)

            ref_expr_id = ref.expression_id or (ref.expression.id if ref.expression else None)
            if ref_expr_id not in undefined_expression_ids:
                continue
            dep_state = self._cache[dep.id]
            if dep_state != ComponentVisibilityState.HIDDEN:
                return ComponentVisibilityState.UNDETERMINED
        return ComponentVisibilityState.HIDDEN

    def is_visible(self, component_or_id: Component | UUID, add_another_index: int | None = None) -> bool:
        component_id = component_or_id if isinstance(component_or_id, UUID) else component_or_id.id

        if add_another_index is not None:
            state = self.get_visibility_for_add_another(component_id, add_another_index=add_another_index)
        else:
            state = self.get_visibility(component_id)

        return state == ComponentVisibilityState.VISIBLE

    def get_visibility(self, component_or_id: Component | UUID) -> ComponentVisibilityState:
        component_id = component_or_id if isinstance(component_or_id, UUID) else component_or_id.id

        return self._cache[component_id]

    def get_visibility_for_add_another(
        self, component_or_id: Component | UUID, add_another_index: int
    ) -> ComponentVisibilityState:
        component_id = component_or_id if isinstance(component_or_id, UUID) else component_or_id.id
        cache_key = (component_id, add_another_index)
        if cache_key in self._add_another_cache:
            return self._add_another_cache[cache_key]

        component = self._graph.components.get(component_id)
        if component is None:
            return ComponentVisibilityState.UNDETERMINED

        if not component.add_another_container:
            state = self._cache[component_id]
            self._add_another_cache[cache_key] = state
            return state

        add_another_context = self._context.with_add_another_context(
            component,
            data_manager=self._data_manager,
            add_another_index=add_another_index,
        )

        state = self._compute_visibility_for_add_another(component, add_another_context, add_another_index)
        self._add_another_cache[cache_key] = state
        return state

    def _get_dep_state_for_add_another(
        self,
        dep: Component,
        add_another_index: int,
    ) -> ComponentVisibilityState:
        if dep.add_another_container:
            return self.get_visibility_for_add_another(dep.id, add_another_index)
        return self._cache[dep.id]

    def _compute_visibility_for_add_another(
        self,
        component: Component,
        context: ExpressionContext,
        add_another_index: int,
    ) -> ComponentVisibilityState:
        parent_id = component.parent_id or (component.parent.id if component.parent else None)
        parent = self._graph.components.get(parent_id) if parent_id else None
        if parent is not None:
            if parent.add_another_container is not None:
                parent_state = self.get_visibility_for_add_another(parent.id, add_another_index)
            else:
                parent_state = self._cache[parent.id]
            if parent_state == ComponentVisibilityState.HIDDEN:
                return ComponentVisibilityState.HIDDEN

        ref_state = self._check_references_for_add_another(component, add_another_index)

        conditions = component.conditions

        if ref_state == ComponentVisibilityState.HIDDEN:
            if not conditions or component.conditions_operator != ConditionsOperator.ANY:
                return ComponentVisibilityState.HIDDEN

        if not conditions:
            return ref_state

        condition_result = self._evaluate_conditions(component.conditions_operator, conditions, context, component)

        if condition_result == ComponentVisibilityState.HIDDEN:
            return ComponentVisibilityState.HIDDEN
        if condition_result == ComponentVisibilityState.UNDETERMINED:
            return ComponentVisibilityState.UNDETERMINED

        if (
            component.conditions_operator != ConditionsOperator.ANY
            and ref_state == ComponentVisibilityState.UNDETERMINED
        ):
            return ComponentVisibilityState.UNDETERMINED

        return ComponentVisibilityState.VISIBLE

    def _check_references_for_add_another(
        self,
        component: Component,
        add_another_index: int,
    ) -> ComponentVisibilityState:
        result = ComponentVisibilityState.VISIBLE

        for ref in component.owned_component_references:
            dep = ref.depends_on_component

            if self._component_reference_is_skippable(component, ref):
                continue

            # _component_reference_is_skipped checks that `dep` is not None
            dep = cast("Component", dep)

            if not dep.is_question:
                raise RuntimeError(f"Components can only depend on questions, but got a non-question {dep.id}")

            dep_state = self._get_dep_state_for_add_another(dep, add_another_index)
            if dep_state == ComponentVisibilityState.HIDDEN:
                return ComponentVisibilityState.HIDDEN

            if dep.is_question:
                if self._data_manager.get(cast("Question", dep), add_another_index=add_another_index) is None:
                    result = ComponentVisibilityState.UNDETERMINED

        return result
