from pathlib import Path

import pytest
import syside
from sismic.interpreter import Interpreter
from sysmlc.semantics.statemachine.facts import (
    StateFact,
    StateKind,
    TransitionFact,
)
from sysmlc.sysml.loading import load_model

from sysmlc_quake.builder import SismicBuilder, build_statechart
from sysmlc_quake.codegen import QuakeRenderNeeds

FIXTURE = Path(__file__).parent / "fixtures" / "eventless-priority"


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_model(FIXTURE)


def _run(model: syside.Model, machine: str) -> Interpreter:
    statechart = build_statechart(model, f"EventlessPriority::{machine}")
    interpreter = Interpreter(statechart)
    interpreter.execute()
    return interpreter


@pytest.mark.parametrize(
    ("machine", "target", "chosen"),
    [
        ("FirstTrue", "left", 1),
        ("Reversed", "right", 2),
        ("FalseFirst", "right", 2),
        ("GuardlessFirst", "left", 1),
        ("GuardlessLast", "left", 1),
        ("GuardlessLastEligible", "right", 2),
    ],
)
def test_first_eligible_declaration_wins(
    model: syside.Model, machine: str, target: str, chosen: int
) -> None:
    interpreter = _run(model, machine)
    assert interpreter.configuration == [machine, target]
    assert interpreter.context["chosen"] == chosen
    assert interpreter.context["effects"] == 1
    assert interpreter.context["exits"] == 1


def test_all_false_guards_stay_in_source(model: syside.Model) -> None:
    interpreter = _run(model, "AllFalse")
    assert interpreter.configuration == ["AllFalse", "active"]
    assert interpreter.context["chosen"] == 0
    assert interpreter.context["effects"] == 0
    assert interpreter.context["exits"] == 0


@pytest.mark.parametrize(
    ("machine", "target", "chosen"),
    [("NestedFirst", "outer::b", 1), ("ParentFirst", "outer::c", 2)],
)
def test_order_across_nested_declaration_scopes(
    model: syside.Model, machine: str, target: str, chosen: int
) -> None:
    interpreter = _run(model, machine)
    assert interpreter.configuration == [machine, "outer", target]
    assert interpreter.context["chosen"] == chosen
    assert interpreter.context["effects"] == 1
    assert interpreter.context["exits"] == 1


def test_each_source_of_an_automatic_chain_chooses_independently(
    model: syside.Model,
) -> None:
    interpreter = _run(model, "Chain")
    assert interpreter.final
    assert interpreter.context["path"] == 123
    assert interpreter.context["effects"] == 3
    assert interpreter.context["exits"] == 3


@pytest.mark.parametrize(
    ("machine", "enabled", "target"),
    [
        ("WhenThenPlain", ("hot", "go"), "viaPlain"),
        ("WhenThenPlain", ("go",), "viaPlain"),
        ("WhenThenTwoPlain", ("go",), "viaPlain1"),
        ("WhenThenTwoPlain", ("hot", "go"), "viaPlain1"),
        ("MixGuardedRev", ("hot", "go"), "viaGuard"),
        ("MixGuardedRev", ("hot",), "viaChange"),
    ],
)
def test_automatic_entry_decision_precedes_accept_when(
    model: syside.Model, machine: str, enabled: tuple[str, ...], target: str
) -> None:
    interpreter = Interpreter(
        build_statechart(model, f"EventlessPriority::{machine}")
    )
    for name in enabled:
        interpreter.context[name] = True
    interpreter.execute()
    assert interpreter.configuration == [machine, target]


@pytest.mark.parametrize("machine", ["WhenThenPlain", "MixGuardedRev"])
def test_later_mutation_does_not_revive_automatic_transition(
    model: syside.Model, machine: str
) -> None:
    interpreter = _run(model, machine)
    interpreter.context["go"] = True
    interpreter.execute()
    assert interpreter.configuration == [machine, "active"]
    interpreter.context["hot"] = True
    interpreter.execute()
    target = "viaWhen" if machine == "WhenThenPlain" else "viaChange"
    assert interpreter.configuration == [machine, target]


def test_unguarded_entry_decision_precedes_accept_when(
    model: syside.Model,
) -> None:
    interpreter = _run(model, "WhenThenUnguarded")
    assert interpreter.configuration == ["WhenThenUnguarded", "viaPlain"]


@pytest.mark.parametrize("go", [False, True])
def test_entry_decision_precedes_zero_delay_timer(
    model: syside.Model, go: bool
) -> None:
    interpreter = Interpreter(
        build_statechart(model, "EventlessPriority::ZeroTimer")
    )
    interpreter.context["go"] = go
    interpreter.execute()
    target = "viaPlain" if go else "viaTimer"
    assert interpreter.configuration == ["ZeroTimer", target]


def test_reentry_reconsiders_automatic_guards(model: syside.Model) -> None:
    interpreter = _run(model, "Reentry")
    interpreter.context["go"] = True
    interpreter.execute()
    assert interpreter.configuration == ["Reentry", "active"]
    interpreter.queue("Restart")
    interpreter.execute()
    assert interpreter.configuration == ["Reentry", "viaPlain"]
    assert interpreter.context["entries"] == 2


@pytest.mark.parametrize(
    ("machine", "target"),
    [("CompositeWhenFirst", "viaWhen"), ("CompositeDoneFirst", "viaDone")],
)
def test_completed_composite_and_change_use_declaration_order(
    model: syside.Model, machine: str, target: str
) -> None:
    interpreter = _run(model, machine)
    assert interpreter.context["hot"] is True
    assert interpreter.configuration == [machine, target]


def test_completed_composite_guard_remains_live(model: syside.Model) -> None:
    interpreter = _run(model, "CompositeLateGuard")
    assert interpreter.configuration == [
        "CompositeLateGuard",
        "outer",
        "outer::done",
    ]
    interpreter.context["go"] = True
    interpreter.execute()
    assert interpreter.configuration == ["CompositeLateGuard", "finished"]


@pytest.mark.parametrize(
    ("orders", "expected"),
    [
        ((None, None), "first"),
        ((5, None), "first"),
        ((None, 0), "first"),
        ((0, 1), "first"),
        ((1, 0), "second"),
    ],
)
def test_manual_eventless_facts(
    orders: tuple[int | None, int | None], expected: str
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
    for target, order in zip(("first", "second"), orders, strict=True):
        builder.add_transition(
            TransitionFact(
                "waiting", target, None, None, None, declaration_order=order
            )
        )
    interpreter = Interpreter(builder.result())
    interpreter.execute()
    assert interpreter.configuration == ["Manual", expected]
