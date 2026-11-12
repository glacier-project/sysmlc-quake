from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import syside
from sismic.model import (
    BasicState,
    CompoundState,
    FinalState,
    OrthogonalState,
    Statechart,
    Transition,
)
from sysmlc.codegen.python import LIBRARY_FUNCTIONS, join_statements
from sysmlc.codegen.structured import (
    constructed_payload_definition,
    register_dataclass,
    types_module_name,
)
from sysmlc.errors import UnsupportedConstructError
from sysmlc.semantics.statemachine import actions, transitions
from sysmlc.semantics.statemachine.driver import StateMachineDriver
from sysmlc.semantics.statemachine.facts import (
    AfterTrigger,
    AttributeBinding,
    AttributeValue,
    AtTrigger,
    CompletionTarget,
    ConstraintFact,
    SignalTrigger,
    StateFact,
    StateKind,
    TransitionFact,
    Trigger,
    WhenTrigger,
)
from sysmlc.semantics.statemachine.signals import SignalCatalog
from sysmlc.sysml.queries import resolve, structured_fields

from sysmlc_quake.artifacts import (
    QuakeInvariant,
    QuakeStatechartArtifact,
    external_channel_names,
)
from sysmlc_quake.codegen import (
    PAYLOAD_READER,
    TICK_METADATA_KEY,
    VIA_DATA_KEY,
    QuakeRenderNeeds,
    SismicCodeGen,
    math_import_lines,
    payload_constructor,
    payload_reader_lines,
    types_module_for,
)

if TYPE_CHECKING:
    from sysmlc.sysml.foreign_artifact.base import ForeignArtifact

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _TimeTriggerPlan:
    """What an ``accept after`` or ``accept at`` transition references.

    Attributes:
        event_name: The synthetic internal event carrying the deadline.
        counter: Context name of the source state's activation counter.
    """

    event_name: str
    counter: str


@dataclass(frozen=True)
class _ChangeTriggerPlan:
    """How an ``accept when`` transition pair is emitted.

    Attributes:
        flag: Context name of the armed-observation flag.
        condition: The monitored boolean condition, already rendered as
            source text.
        consumer_priority: A distinct negative priority for the consumer
            transition (below the real transition's sismic default), or
            None when no ``if`` guard can reject the occurrence and no
            consumer is emitted.
    """

    flag: str
    condition: str
    consumer_priority: int | None


class SismicBuilder:
    """Assemble a sismic ``Statechart`` from neutral state-machine facts.

    Implements the ``TargetBuilder`` protocol. This is where every
    sismic-specific representational choice lives:

    - the flat preamble, with its name-collision policy;
    - the ``do`` -> run-once ``on_entry`` fusion;
    - the ``then done`` -> ``FinalState`` synthesis;
    - the ``_c_*`` completion-flag encoding of an eventless transition
      leaving a composite or ``parallel`` state: a flag per completing
      scope (the composite itself, or each region of a parallel state),
      conjoined into the transition's guard so it fires only once every
      scope has reached its own ``done``; a region with no ``then done``
      of its own is conjoined as a literal ``False`` once any sibling
      scope is gated, so the join can never fire on a subset;
    - the one-shot delayed-event encoding of ``accept after`` and
      ``accept at``: a
      per-activation counter bumped ``on entry``, a ``send('_tick_...',
      n=..., delay=...)`` arming call, and an event-triggered transition
      whose guard checks ``event.n``. Absolute-time triggers additionally
      use ``_d_*`` arming-delta variables and send only for non-past
      instants;
    - the armed-flag encoding of ``accept when``: a ``_w_*`` flag re-armed
      ``on entry``, an eventless transition (at sismic's default priority)
      guarded by the flag and the condition, and, with an ``if`` guard, a
      negative-priority internal consumer transition that disarms the flag
      when the occurrence is rejected;
    - concrete signal channels expanded by resolved conformance, with positive
      same-source declaration priorities and one concrete event per send;
    - same-source triggerless transitions ranked by declaration order, so the
      first one whose guard holds fires; at a source that also has an
      ``accept when``, ordinary triggerless and real change transitions
      keep their existing default priority and the change consumers keep
      their negative priorities;
    - the payload envelope: a send of a type with fields carries one
      generated-class instance, constructed through the class's reserved
      ``_sysmlc_new_<Type>`` preamble alias, under the ``_sysmlc_payload``
      event-data key, and a signal accepter that binds its payload
      (``accept reading : Measurement``) renders references to that
      binding through the preamble's ``_sysmlc_payload_of(event)`` reader,
      so ``reading.value`` becomes ``_sysmlc_payload_of(event).value``.
      Envelopes from generated sends and ``payload_event`` hold only model
      data. Any other event, such as a marker or a low-level keyword-field
      event, reads as a namespace of its raw ``event.data``; a raw
      ``Event(..., delay=...)`` deliberately keeps that ``delay`` entry
      there, while Sismic's ``name`` attribute never appears;
    - the capability rejections: non-inline ``do`` bodies, unstable
      self-loops, and model names starting with ``_``.

    Sismic's ``Statechart.preamble`` is read-only after construction, so facts
    are buffered and the whole statechart is built in :meth:`result`.
    """

    def __init__(
        self,
        name: str,
        *,
        needs: QuakeRenderNeeds,
        part_system_mode: bool = False,
    ) -> None:
        """Initialize the builder.

        Args:
            name: The sismic statechart name (the state definition's name).
            needs: The render-needs registry shared with the code
                generator; the caller configures external backing and the
                dataclass registry on it before building.
            part_system_mode: True when the machine is built inside a part
                system, where ``send ... via <port>`` renders as a call to
                the injected router; false for a standalone statechart,
                where such a send is dropped.
        """
        self._name = name
        self._part_system_mode = part_system_mode
        self._needs = needs
        self._codegen = SismicCodeGen(
            needs=self._needs, part_system_mode=part_system_mode
        )
        self._preamble: list[str] = []
        self._seen_attrs: dict[str, str] = {}
        self._constraints: list[ConstraintFact] = []
        self._invariants: list[QuakeInvariant] = []
        self._state_facts: list[StateFact] = []
        self._transition_facts: list[TransitionFact] = []
        self._planned_triggers: dict[
            int, _TimeTriggerPlan | _ChangeTriggerPlan
        ] = {}
        self._arming_by_source: dict[str, list[str]] = {}
        self._completion_flag_by_scope: dict[str, str] = {}
        self._completion_flags_by_source: dict[str, str] = {}

    def bind_attribute(self, binding: AttributeBinding) -> None:
        """Seed an attribute into sismic's flat preamble namespace.

        Raises:
            UnsupportedConstructError: If two attributes in different scopes
                share a simple name (sismic's context is flat), or if an
                attribute name starts with the reserved ``_`` prefix.
        """
        if binding.name.startswith("_"):
            raise UnsupportedConstructError(
                f"attribute {binding.name!r} starts with an underscore; "
                "that namespace is reserved for the generated machinery. "
            )
        if binding.name in _SHADOWED_BUILTINS:
            raise UnsupportedConstructError(
                f"attribute {binding.name!r} would shadow the builtin "
                "that the library-function mapping renders to; rename it."
            )
        if binding.name in self._seen_attrs:
            first = self._seen_attrs[binding.name]
            raise UnsupportedConstructError(
                f"attribute {binding.name!r} is declared in two scopes "
                f"({first!r} and {binding.scope!r}). Sismic's flat namespace "
                "cannot represent both. Rename one."
            )
        self._seen_attrs[binding.name] = binding.scope
        rendered = self._render_value(binding.value)
        if rendered is None:
            return
        self._preamble.append(f"{binding.name} = {rendered}")

    def bind_constraint(self, fact: ConstraintFact) -> None:
        """Buffer an asserted constraint for sismic invariant emission."""
        self._constraints.append(fact)

    @property
    def invariants(self) -> tuple[QuakeInvariant, ...]:
        """Source identities for the assembled statechart's invariants."""
        return tuple(self._invariants)

    def add_state(self, state: StateFact) -> None:
        """Buffer a state fact (emitted in :meth:`result`).

        Raises:
            UnsupportedConstructError: If the state is named like the
                machine's root state (sismic keys states by name), or a
                segment of its name starts with the reserved ``_`` prefix.
        """
        if state.name == self._name and state.parent is not None:
            raise UnsupportedConstructError(
                f"state {state.name!r} has the name of its state "
                "definition; sismic names the root state after the "
                "definition, so rename the state."
            )
        if any(segment.startswith("_") for segment in state.name.split("::")):
            raise UnsupportedConstructError(
                f"state {state.name!r} starts with an underscore; that "
                "namespace is reserved for the generated machinery; rename "
                "the state."
            )
        self._state_facts.append(state)

    def add_transition(self, transition: TransitionFact) -> None:
        """Buffer a transition fact (emitted in :meth:`result`)."""
        self._transition_facts.append(transition)

    def result(self) -> Statechart:
        """Build, validate, and return the assembled sismic statechart."""
        self._collect_sends()
        self._plan_triggers()
        self._plan_completions()
        if self._needs.external:
            # Assemble a scratch statechart first purely to record the calls;
            self._assemble(Statechart(name=self._name, preamble=""))
        imports = self._preamble_import_lines()
        for symbol in sorted(self._needs.payload_constructors):
            self._reject_imported(payload_constructor(symbol))
        if self._reads_payload():
            self._reject_imported(PAYLOAD_READER)
            imports.extend(payload_reader_lines())
        if imports:
            self._preamble[0:0] = imports
        statechart = self._assemble(
            Statechart(name=self._name, preamble="\n".join(self._preamble))
        )
        for event_name, port in sorted(self._needs.undeliverable_sends):
            logger.warning(
                "machine %r sends %r via %r; without a connected system "
                "context the signal is never delivered",
                self._name,
                event_name,
                port,
            )
        return statechart

    def _assemble(self, statechart: Statechart) -> Statechart:
        """Emit every buffered fact into ``statechart`` and validate it."""
        done_finals: set[str] = set()
        for state in self._state_facts:
            self._emit_state(statechart, state)
        self._emit_constraints(statechart)
        # A change trigger's real transition is eventless too, so it ranks
        # with the guarded eventless transitions of its source: one group,
        # ordered by declaration. An unguarded triggerless sibling at such a
        # source stays unranked (it is always enabled, so ranking it would
        # decide a competition the model never states); its signal ranking
        # is unaffected.
        when_sources = {
            transition.source
            for transition in self._transition_facts
            if isinstance(transition.trigger, WhenTrigger)
        }
        groups: dict[tuple[str, str], list[int]] = {}
        for index, transition in enumerate(self._transition_facts):
            trigger = transition.trigger
            if isinstance(trigger, SignalTrigger):
                groups.setdefault((transition.source, "signal"), []).append(
                    index
                )
            elif isinstance(trigger, WhenTrigger) or (
                trigger is None
                and (
                    transition.source not in when_sources
                    or transition.guard is not None
                )
            ):
                groups.setdefault((transition.source, "eventless"), []).append(
                    index
                )
        priorities: dict[int, int] = {}
        for (_, kind), indices in groups.items():
            is_signal = kind == "signal"
            orders = [
                self._transition_facts[index].declaration_order
                for index in indices
            ]
            if all(order is not None for order in orders):
                indices = [
                    index
                    for _, index in sorted(zip(orders, indices, strict=True))
                ]
            # Eventless ranks end at the default priority, so a lone
            # eventless transition keeps its default serialized form.
            lowest = 1 if is_signal else 0
            priorities.update(
                (index, len(indices) - 1 - rank + lowest)
                for rank, index in enumerate(indices)
            )
        for index, transition in enumerate(self._transition_facts):
            self._emit_transition(
                statechart,
                transition,
                self._planned_triggers.get(index),
                done_finals,
                priority=priorities.get(index, 0),
            )
        statechart.validate()
        return statechart

    def _preamble_import_lines(self) -> list[str]:
        """Return import lines before seeded context variables."""
        lines = math_import_lines()
        lines.extend(self._needs.types_import_lines())
        lines.extend(self._needs.external_import_lines())
        return lines

    def _reads_payload(self) -> bool:
        """Whether any signal accepter binds its payload to a name."""
        return any(
            isinstance(transition.trigger, SignalTrigger)
            and transition.trigger.payload_feature is not None
            for transition in self._transition_facts
        )

    def _reject_imported(self, name: str) -> None:
        """Reject a generated preamble name that an import would shadow.

        Raises:
            UnsupportedConstructError: If a generated structured type or a
                called external function is named ``name``.
        """
        imported = set(self._needs.dataclasses.names())
        for names in self._needs.used_external.values():
            imported.update(names)
        if name in imported:
            raise UnsupportedConstructError(
                f"{name!r} is reserved for quake's generated preamble; "
                "rename the structured type or external function using it."
            )

    def _collect_sends(self) -> None:
        """Register every structured payload type constructed by a send."""
        slots: list[syside.ActionUsage | None] = []
        for state in self._state_facts:
            slots.extend(state.executable_actions())
        slots.extend(transition.effect for transition in self._transition_facts)
        # Repeated sends construct the same type; resolve each definition
        # once, keyed by its qualified name.
        seen: set[str] = set()
        for slot in slots:
            for action in actions.inline_actions(slot):
                if not isinstance(action, syside.SendActionUsage):
                    continue
                definition = constructed_payload_definition(action)
                if definition is None:
                    continue
                key = str(definition.qualified_name or definition.name)
                if key in seen:
                    continue
                seen.add(key)
                # Empty payload types stay out of the companion: quake
                # transports payloads by event name, so only types whose
                # fields, owned or inherited, carry data need a class.
                if structured_fields(definition):
                    self._register_dataclass(definition)
                    self._needs.payload_constructors.add(
                        self._needs.dataclasses.symbol_for(definition)
                    )

    def _plan_triggers(self) -> None:
        """Plan the emitted machinery for time and change triggers.

        Walks the buffered transitions in declaration order, delegating
        per trigger kind.
        """
        per_source_time: dict[str, int] = {}
        per_source_when: dict[str, int] = {}
        next_consumer: dict[str, int] = {}
        for index, transition in enumerate(self._transition_facts):
            trigger = transition.trigger
            if trigger is None:
                continue
            if isinstance(trigger, (AfterTrigger, AtTrigger)):
                self._plan_time(
                    index, trigger, transition.source, per_source_time
                )
            elif isinstance(trigger, WhenTrigger):
                self._plan_when(
                    index, trigger, transition, per_source_when, next_consumer
                )

    @staticmethod
    def _ident(name: str) -> str:
        """Return ``name`` as a Python-identifier-safe fragment."""
        return name.replace("::", "__")

    def _declare_armed(
        self, source: str, name: str, initial: str, armed: str
    ) -> None:
        """Declare a preamble variable, re-armed on every entry of ``source``.

        ``name`` starts at ``initial`` in the preamble, and is set to
        ``armed`` every time ``source`` is (re-)entered, so a restart
        re-arms whatever the variable tracks.
        """
        self._preamble.append(f"{name} = {initial}")
        self._arming_by_source.setdefault(source, []).append(
            f"{name} = {armed}"
        )

    def _plan_time(
        self,
        index: int,
        trigger: AfterTrigger | AtTrigger,
        source: str,
        per_source_ordinal: dict[str, int],
    ) -> None:
        """Plan the delayed-event machinery for one time trigger.

        The counter invalidates stale ticks: sismic never cancels a
        delayed event when its state exits, so a tick armed by an earlier
        activation must match nothing when it is delivered.
        """
        ordinal = per_source_ordinal.get(source, 0) + 1
        per_source_ordinal[source] = ordinal
        ident = self._ident(source)
        counter = f"_n_{ident}"
        delay = (
            self._render_value(trigger.duration)
            if isinstance(trigger, AfterTrigger)
            else self._render_value(trigger.instant)
        )
        assert delay is not None
        event_name = f"_tick_{ident}_t{ordinal}"
        self._planned_triggers[index] = _TimeTriggerPlan(
            event_name=event_name, counter=counter
        )
        if ordinal == 1:
            self._declare_armed(source, counter, "0", f"{counter} + 1")
        # The time-trigger event self-describes which state and counter its
        # guard checks, so a runner can drop events the guard would ignore.
        stamp = f"{TICK_METADATA_KEY}=('{source}', '{counter}')"
        if isinstance(trigger, AfterTrigger):
            self._arming_by_source[source].append(
                f"send('{event_name}', n={counter}, delay={delay}, {stamp})"
            )
            return
        delta = f"_d_{ident}_t{ordinal}"
        tick_send = f"send('{event_name}', n={counter}, delay={delta}, {stamp})"
        self._arming_by_source[source].extend(
            [
                f"{delta} = ({delay}) - time",
                f"if {delta} >= 0:",
                f"    {tick_send}",
            ]
        )

    def _plan_when(
        self,
        index: int,
        trigger: WhenTrigger,
        transition: TransitionFact,
        per_source_ordinal: dict[str, int],
        next_consumer: dict[str, int],
    ) -> None:
        """Plan the armed-flag machinery for one ``accept when``.

        The real transitions of one source are ranked with its plain
        eventless transitions by declaration order (the last keeps the
        default priority, earlier ones rank above it); the consumers use
        distinct negative priorities.
        """
        source = transition.source
        ordinal = per_source_ordinal.get(source, 0) + 1
        per_source_ordinal[source] = ordinal
        ident = self._ident(source)
        flag = f"_w_{ident}_t{ordinal}"
        consumer_priority = None
        if transition.guard is not None:
            # Distinct negatives per source, from -2 down: below the real's
            # default 0, and skipping -1, which sismic serializes as the
            # named priority `low`.
            consumer_priority = next_consumer.get(source, -2)
            next_consumer[source] = consumer_priority - 1
        self._planned_triggers[index] = _ChangeTriggerPlan(
            flag=flag,
            condition=self._codegen.render_expression(trigger.condition),
            consumer_priority=consumer_priority,
        )
        self._declare_armed(source, flag, "False", "True")

    def _plan_completions(self) -> None:
        """Plan the completion-flag machinery for eventless-out composites.

        An eventless transition sourced at a composite or ``parallel``
        state may only fire once that state reaches its own ``done``, not
        the instant it is entered. Sismic has no built-in notion of this,
        so each completing scope (a parallel state's regions, or the
        composite itself) gets a flag: false on entry, true once its own
        final state is reached, conjoined into the transition's guard.

        A source with no completing scope targeted by a ``then done`` can
        never complete, so its eventless transitions are gated on a literal
        ``False``. Once any scope is gated, every scope is
        required: a region with no ``then done`` of its own is conjoined
        as a literal ``False``, so the join can never fire on a subset.
        """
        eventless_sources: set[str] = set()
        completion_scopes: set[str] = set()
        for transition in self._transition_facts:
            if transition.trigger is None:
                eventless_sources.add(transition.source)
            if isinstance(transition.target, CompletionTarget):
                completion_scopes.add(transition.target.scope)
        children_by_parent: dict[str, list[str]] = {}
        for child in self._state_facts:
            if child.parent is not None:
                children_by_parent.setdefault(child.parent, []).append(
                    child.name
                )
        for state in self._state_facts:
            if state.name not in eventless_sources:
                continue
            if state.kind is StateKind.PARALLEL:
                scopes = children_by_parent.get(state.name, [])
            elif state.kind is StateKind.COMPOSITE:
                scopes = [state.name]
            else:
                continue
            if not any(scope in completion_scopes for scope in scopes):
                # No region or body can ever complete: completion never
                # fires on entry, so the transition is gated shut.
                self._completion_flags_by_source[state.name] = "False"
                continue
            flags: list[str] = []
            for scope in scopes:
                if scope not in completion_scopes:
                    # This scope never reaches a done of its own, so the
                    # join it participates in can never legitimately fire.
                    flags.append("False")
                    continue
                flag = f"_c_{self._ident(scope)}"
                self._declare_armed(state.name, flag, "False", "False")
                self._completion_flag_by_scope[scope] = flag
                flags.append(flag)
            self._completion_flags_by_source[state.name] = " and ".join(flags)

    def _render_value(self, value: AttributeValue) -> str | None:
        return self._codegen.render_value(value, self._register_dataclass)

    def _register_dataclass(self, definition: syside.Definition) -> None:
        """Register ``definition`` on the shared dataclass registry."""
        register_dataclass(
            definition,
            self._needs.dataclasses,
            self._codegen.render_expression,
        )

    def _emit_state(self, statechart: Statechart, state: StateFact) -> None:
        on_entry = self._on_entry(state)
        on_exit = self._statements(state.exit_action)
        sismic_state: BasicState | CompoundState | OrthogonalState
        if state.kind is StateKind.LEAF:
            sismic_state = BasicState(
                state.name, on_entry=on_entry, on_exit=on_exit
            )
        elif state.kind is StateKind.PARALLEL:
            sismic_state = OrthogonalState(
                state.name, on_entry=on_entry, on_exit=on_exit
            )
        elif state.kind is StateKind.COMPOSITE:
            sismic_state = CompoundState(
                state.name,
                initial=state.initial_substate,
                on_entry=on_entry,
                on_exit=on_exit,
            )
        else:
            raise UnsupportedConstructError(
                f"cannot emit a sismic state of kind {state.kind.name}"
            )
        statechart.add_state(sismic_state, parent=state.parent)

    def _on_entry(self, state: StateFact) -> str | None:
        entry = self._statements(state.entry_action)
        do = None
        if state.do_action is not None:
            actions.require_inline_one_shot(state.do_action)
            do = self._statements(state.do_action)
        # Armed last: durations must see the values entry/do just assigned.
        arming = "\n".join(self._arming_by_source.get(state.name, []))
        parts = [part for part in (entry, do, arming) if part]
        return "\n".join(parts) or None

    def _statements(
        self,
        action: syside.ActionUsage | None,
        codegen: SismicCodeGen | None = None,
    ) -> str | None:
        generator = self._codegen if codegen is None else codegen
        rendered = join_statements(
            [
                generator.render_action(candidate)
                for candidate in actions.inline_actions(action)
            ]
        )
        return rendered or None

    def _emit_constraints(self, statechart: Statechart) -> None:
        """Attach asserted constraints to their owning sismic states."""
        self._invariants.clear()
        for check_id, fact in enumerate(self._constraints):
            state_name = self._name if fact.scope == "" else fact.scope
            rendered = self._codegen.render_expression(fact.expression)
            if fact.is_negated:
                rendered = f"not ({rendered})"
            # Sismic reports the condition, without its list index. The
            # annotation distinguishes checks with identical expressions.
            rendered = f"({rendered}) # sysmlc.constraint_id={check_id}"
            statechart.state_for(state_name).invariants.append(rendered)
            self._invariants.append(
                QuakeInvariant(
                    state_name, fact.scope, fact.name, check_id, rendered
                )
            )

    def _emit_transition(
        self,
        statechart: Statechart,
        transition: TransitionFact,
        plan: _TimeTriggerPlan | _ChangeTriggerPlan | None,
        done_finals: set[str],
        *,
        priority: int,
    ) -> None:
        if transitions.self_loop_is_unstable(transition):
            raise UnsupportedConstructError(
                "A self-loop transition would never stabilize (no event, "
                "timer, or effect to break the loop)."
            )
        target = (
            self._final_state(statechart, transition.target.scope, done_finals)
            if isinstance(transition.target, CompletionTarget)
            else transition.target
        )
        if isinstance(plan, _ChangeTriggerPlan):
            self._emit_change_transitions(
                statechart, transition, plan, target, priority
            )
            return
        codegen = self._transition_codegen(transition)
        trigger = transition.trigger
        if (
            isinstance(trigger, SignalTrigger)
            and self._needs.catalog is not None
        ):
            events = sorted(self._needs.catalog.matching_channels(trigger))
        else:
            events = [self._event(trigger, plan)]
        for event in events:
            statechart.add_transition(
                Transition(
                    source=transition.source,
                    target=target,
                    event=event,
                    guard=self._guard(transition, plan, codegen),
                    action=self._statements(transition.effect, codegen),
                    priority=priority,
                )
            )

    def _emit_change_transitions(
        self,
        statechart: Statechart,
        transition: TransitionFact,
        plan: _ChangeTriggerPlan,
        target: str,
        priority: int,
    ) -> None:
        """Emit the transition pair realizing one ``accept when``.

        The consumer disarms in its action, not in a guard side effect,
        so an aborted macro step consumes nothing; having no target, it
        consumes without re-running ``on entry`` (which would re-arm).
        """
        delivery = f"{plan.flag} and ({plan.condition})"
        codegen = self._transition_codegen(transition)
        guard = delivery
        if transition.guard is not None:
            condition = codegen.render_expression(transition.guard)
            guard = f"{delivery} and ({condition})"
        statechart.add_transition(
            Transition(
                source=transition.source,
                target=target,
                guard=guard,
                action=self._statements(transition.effect, codegen),
                priority=priority,
            )
        )
        if plan.consumer_priority is not None:
            statechart.add_transition(
                Transition(
                    source=transition.source,
                    guard=delivery,
                    action=f"{plan.flag} = False",
                    priority=plan.consumer_priority,
                )
            )

    def _event(
        self, trigger: Trigger | None, plan: _TimeTriggerPlan | None
    ) -> str | None:
        """Return the transition's sismic event name, or None.

        A signal accepter triggers on its payload type's name; a time
        trigger triggers on its planned ``_tick_*`` event.

        Raises:
            UnsupportedConstructError: If a signal name starts with the
                reserved ``_`` prefix.
        """
        if trigger is None:
            return None
        if isinstance(trigger, (AfterTrigger, AtTrigger)):
            assert plan is not None
            return plan.event_name
        assert isinstance(trigger, SignalTrigger)
        name = trigger.signal_name
        if name.startswith("_"):
            raise UnsupportedConstructError(
                f"signal {name!r} starts with an underscore; that "
                "namespace is reserved for the generated machinery. "
            )
        return name

    @staticmethod
    def _conjoin(extra: str, condition: str | None) -> str:
        """Return ``extra`` alone, or ANDed with ``condition`` when present."""
        return extra if condition is None else f"{extra} and ({condition})"

    def _guard(
        self,
        transition: TransitionFact,
        plan: _TimeTriggerPlan | None,
        codegen: SismicCodeGen,
    ) -> str | None:
        """Compose the transition's sismic guard string, or None.

        Conjoining the ``if`` condition with the ``event.n`` check is what
        makes a time trigger plus guard faithful: a deadline delivered
        while the condition is false is consumed, with no late firing.
        Conjoining the completion flags is what makes an eventless
        transition leaving a composite or parallel state wait for that
        state to reach its own ``done`` (every region, for a parallel
        state), instead of firing as soon as the state is entered.
        """
        condition = (
            codegen.render_expression(transition.guard)
            if transition.guard is not None
            else None
        )
        if transition.trigger is None:
            completion_condition = self._completion_flags_by_source.get(
                transition.source
            )
            if completion_condition is not None:
                condition = self._conjoin(completion_condition, condition)
        trigger = transition.trigger
        if isinstance(trigger, SignalTrigger) and trigger.via_port is not None:
            port = repr(trigger.via_port)
            condition = self._conjoin(
                f"getattr(event, {VIA_DATA_KEY!r}, {port}) == {port}",
                condition,
            )
        if plan is None:
            return condition
        return self._conjoin(f"event.n == {plan.counter}", condition)

    def _transition_codegen(self, transition: TransitionFact) -> SismicCodeGen:
        """Return a code generator scoped to ``transition``."""
        trigger = transition.trigger
        if (
            not isinstance(trigger, SignalTrigger)
            or trigger.payload_feature is None
        ):
            return self._codegen
        return SismicCodeGen(
            needs=self._needs,
            part_system_mode=self._part_system_mode,
            feature_aliases=(
                (trigger.payload_feature, f"{PAYLOAD_READER}(event)"),
            ),
        )

    def _final_state(
        self, statechart: Statechart, scope: str, done_finals: set[str]
    ) -> str:
        scope_name = scope or self._name
        final_name = "done" if scope == "" else f"{scope}::done"
        if final_name not in done_finals:
            completion_flag = self._completion_flag_by_scope.get(scope)
            on_entry = (
                f"{completion_flag} = True"
                if completion_flag is not None
                else None
            )
            statechart.add_state(
                FinalState(final_name, on_entry=on_entry), parent=scope_name
            )
            done_finals.add(final_name)
        return final_name


# Builtins that the shared library-function mapping renders calls to; an
# attribute of the same name would shadow them in the flat preamble context.
_SHADOWED_BUILTINS = frozenset(
    target
    for target in LIBRARY_FUNCTIONS.values()
    if not target.startswith("math.")
)


def _reject_unmapped_members(
    container: syside.StateDefinition | syside.StateUsage,
) -> None:
    """Reject state-body members that have no mapping, recursively.

    The shared driver reads transitions from ``transition`` usages and the
    initial substate from ``entry``/``start`` successions only, so two valid
    spellings would otherwise vanish without a trace.

    Raises:
        UnsupportedConstructError: If a standalone ``first A then B;``
            succession (no ``transition`` keyword), an asserted constraint
            in a transition body, or a state usage typed by
            a ``state def`` (submachine reuse) is found.
    """
    for transition in transitions.container_transitions(container):
        for member in transition.owned_features.collect():
            if isinstance(member, syside.ConstraintUsage):
                raise UnsupportedConstructError(
                    "an asserted constraint in a transition body is "
                    "unsupported; assert it in a state instead.",
                    node=member,
                )
    entry = container.entry_action
    for feature in container.owned_features.collect():
        if isinstance(feature, syside.SuccessionAsUsage):
            source = feature.source_feature
            is_initial = source is not None and (
                source == entry
                or str(source.qualified_name) == "States::StateAction::start"
            )
            if not is_initial:
                raise UnsupportedConstructError(
                    "a standalone `first A then B;` succession is "
                    "unsupported; spell the transition with the "
                    "`transition` keyword.",
                    node=feature,
                )
        elif isinstance(feature, syside.StateUsage):
            if feature.owned_typings.collect():
                raise UnsupportedConstructError(
                    f"state usage {feature.name!r} typed by a state "
                    "definition (submachine reuse) is unsupported; "
                    "flattening it would drop the definition's content.",
                    node=feature,
                )
            _reject_unmapped_members(feature)


def build_statechart_with_needs(
    model: syside.Model,
    state_def_qn: str,
    *,
    needs: QuakeRenderNeeds,
    part_system_mode: bool = False,
) -> Statechart:
    """Build one statechart using the supplied render-needs registry."""
    _reject_unmapped_members(
        resolve(model, syside.StateDefinition, state_def_qn)
    )
    name = state_def_qn.split("::")[-1]
    return StateMachineDriver(model).run(
        state_def_qn,
        SismicBuilder(
            name,
            needs=needs,
            part_system_mode=part_system_mode,
        ),
    )


def build_statechart_artifact(
    model: syside.Model,
    state_def_qn: str,
    *,
    external: list[ForeignArtifact] | None = None,
    part_system_mode: bool = False,
) -> QuakeStatechartArtifact:
    """Build a statechart together with its generated support module."""
    module_name = types_module_name(state_def_qn)
    _reject_unmapped_members(
        resolve(model, syside.StateDefinition, state_def_qn)
    )
    catalog = SignalCatalog(model, [state_def_qn])
    needs = QuakeRenderNeeds(
        types_module=module_name, external=external, catalog=catalog
    )
    builder = SismicBuilder(
        state_def_qn.split("::")[-1],
        needs=needs,
        part_system_mode=part_system_mode,
    )
    statechart = StateMachineDriver(model).run(state_def_qn, builder)
    # The module is only rendered here, not installed: executing consumers
    # install right before execution, so a write-only build has no
    # process-global side effect.
    return QuakeStatechartArtifact(
        statechart=statechart,
        types_module=types_module_for(module_name, needs.dataclasses),
        invariants=builder.invariants,
        qualified_channels=dict(catalog.qualified_channels),
        external_names=external_channel_names(catalog),
    )


def build_statechart(
    model: syside.Model,
    state_def_qn: str,
    *,
    external: list[ForeignArtifact] | None = None,
    part_system_mode: bool = False,
) -> Statechart:
    """Build a runnable sismic Statechart from a SysML state definition.

    Wires the generic :class:`StateMachineDriver` to a :class:`SismicBuilder`.

    Args:
        model: Loaded syside model containing the SysML state def.
        state_def_qn: Qualified name of the SysML ``state def`` to translate.
        external: Optional list of foreign artifacts for external calc-def
            backing.
        part_system_mode: True when the machine is built inside a part
            system, where ``send ... via <port>`` renders as a call to
            the injected router; false for a standalone statechart,
            where such a send is dropped.

    Returns:
        A sismic ``Statechart`` ready to feed into ``Interpreter``.
    """
    artifact = build_statechart_artifact(
        model,
        state_def_qn,
        external=external,
        part_system_mode=part_system_mode,
    )
    # "Ready for Interpreter" includes the preamble's generated-types
    # import resolving, so this convenience wrapper installs the module;
    # artifact-returning builds leave installation to the runner.
    if artifact.types_module is not None:
        artifact.types_module.install()
    return artifact.statechart
