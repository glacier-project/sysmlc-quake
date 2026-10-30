from pathlib import Path

import pytest
from sismic.clock import SimulatedClock
from sismic.interpreter import Interpreter
from sysmlc.semantics.statemachine.facts import (
    SignalTrigger,
    StateFact,
    StateKind,
    TransitionFact,
)
from sysmlc.sysml.loading import load_model

from sysmlc_quake.builder import SismicBuilder, build_statechart_artifact
from sysmlc_quake.codegen import QuakeRenderNeeds
from sysmlc_quake.coordinator import PartSystemCoordinator
from sysmlc_quake.parts import build_part_system

FIXTURE = Path(__file__).parent / "fixtures" / "typed-dispatch"


@pytest.mark.parametrize(
    "signal",
    ["ExternalOnly", "TypedDispatch::A::Twin", "TypedDispatch::B::Twin"],
)
def test_external_concrete_types(signal: str) -> None:
    artifact = build_statechart_artifact(
        load_model(FIXTURE), "TypedDispatch::External"
    )
    interpreter = Interpreter(artifact.statechart)
    interpreter.execute()
    interpreter.queue(artifact.resolve_external(signal), value=73)
    interpreter.execute()
    assert interpreter.configuration == ["External", "received"]
    assert interpreter.context["captured"] == 73
    assert "TypedDispatch::ExternalOnly" in artifact.qualified_channels
    assert artifact.resolve_external(
        "TypedDispatch::A::Twin"
    ) != artifact.resolve_external("TypedDispatch::B::Twin")
    with pytest.raises(ValueError, match="ambiguous"):
        artifact.resolve_external("Twin")


def test_raw_unambiguous_queue_remains_compatible() -> None:
    artifact = build_statechart_artifact(
        load_model(FIXTURE), "TypedDispatch::External"
    )
    interpreter = Interpreter(artifact.statechart)
    interpreter.execute()
    interpreter.queue("Child", value=57)
    interpreter.execute()
    assert interpreter.context["captured"] == 57


def test_peer_routing_delivers_once_only_to_compatible_receiver() -> None:
    system = build_part_system(load_model(FIXTURE), "TypedDispatch::system")
    if system.types_module is not None:
        system.types_module.install()
    coordinator = PartSystemCoordinator(system)
    trace, _ = coordinator.run()
    compatible = coordinator.interpreters["compatible"]
    unrelated = coordinator.interpreters["unrelated"]
    assert compatible.context["count"] == 1
    assert compatible.context["captured"] == 41
    assert unrelated.context["count"] == 0
    assert unrelated.configuration == ["OtherSink", "waiting"]
    consumed = [
        entry.instance
        for entry in trace
        if entry.step.event is not None
        and entry.step.event.name == system.resolve_external("Child")
    ]
    assert consumed == ["compatible"]


def test_typed_inner_source_precedes_outer_source() -> None:
    artifact = build_statechart_artifact(
        load_model(FIXTURE), "TypedDispatch::InnerFirst"
    )
    interpreter = Interpreter(artifact.statechart)
    interpreter.execute()
    interpreter.queue(artifact.resolve_external("Child"), value=89)
    interpreter.execute()
    assert interpreter.configuration == [
        "InnerFirst",
        "outer",
        "outer::received",
    ]
    assert interpreter.context["captured"] == 89


def test_nested_payload_uses_distinct_definition_symbols() -> None:
    artifact = build_statechart_artifact(
        load_model(FIXTURE), "TypedDispatch::NestedPayload"
    )
    assert artifact.types_module is not None
    artifact.types_module.install()
    interpreter = Interpreter(artifact.statechart)
    interpreter.execute()
    assert interpreter.configuration == ["NestedPayload", "received"]
    assert interpreter.context["captured"] == 46


@pytest.mark.parametrize(
    ("machine", "expected"),
    [("NestedFirst", 1), ("ParentFirst", 2), ("NestedFalseGuard", 2)],
)
def test_declaration_order_across_nested_declaration_scopes(
    machine: str, expected: int
) -> None:
    artifact = build_statechart_artifact(
        load_model(FIXTURE), f"TypedDispatch::{machine}"
    )
    interpreter = Interpreter(artifact.statechart)
    interpreter.execute()
    interpreter.queue(artifact.resolve_external("Child"))
    interpreter.execute()
    assert interpreter.context["chosen"] == expected
    assert interpreter.configuration == [machine, "outer", "outer::b"]


def test_user_signal_does_not_consume_synthetic_timer() -> None:
    artifact = build_statechart_artifact(
        load_model(FIXTURE), "TypedDispatch::TimerChannel"
    )
    clock = SimulatedClock()
    interpreter = Interpreter(artifact.statechart, clock=clock)
    interpreter.execute()
    assert artifact.resolve_external("_tick_s_t1") != "_tick_s_t1"
    assert interpreter.configuration == ["TimerChannel", "s"]
    clock.time = 1
    interpreter.execute()
    assert interpreter.configuration == ["TimerChannel", "timed"]
    assert interpreter.context["chosen"] == 2


@pytest.mark.parametrize("targets", [("first", "second"), ("second", "first")])
@pytest.mark.parametrize("orders", [(None, None), (100, None), (None, 0)])
def test_manual_facts_preserve_supplied_order(
    targets: tuple[str, str], orders: tuple[int | None, int | None]
) -> None:
    builder = SismicBuilder("Manual", needs=QuakeRenderNeeds())
    builder.add_state(
        StateFact(
            "Manual", StateKind.COMPOSITE, None, "waiting", None, None, None
        )
    )
    for name in ("waiting", "first", "second"):
        builder.add_state(
            StateFact(name, StateKind.LEAF, "Manual", None, None, None, None)
        )
    for target, order in zip(targets, orders, strict=True):
        builder.add_transition(
            TransitionFact(
                "waiting",
                target,
                SignalTrigger("E"),
                None,
                None,
                declaration_order=order,
            )
        )
    interpreter = Interpreter(builder.result())
    interpreter.execute()
    interpreter.queue("E")
    interpreter.execute()
    assert interpreter.configuration == ["Manual", targets[0]]
