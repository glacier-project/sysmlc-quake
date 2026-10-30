from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sismic.interpreter import Interpreter
from sysmlc.cli import _load_external_modules
from sysmlc.errors import UnsupportedConstructError
from sysmlc.sysml.foreign_artifact.base import ForeignArtifact
from sysmlc.sysml.loading import load_model

from sysmlc_quake import build_statechart
from sysmlc_quake.coordinator import PartSystemCoordinator, StopReason
from sysmlc_quake.parts import build_part_system

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "payload-construction"
EVALUATIONS = ForeignArtifact(FIXTURE / "payload_evaluations.py", "python")


def _run(qn: str, external: list[ForeignArtifact]) -> Interpreter:
    statechart = build_statechart(load_model(FIXTURE), qn, external=external)
    _load_external_modules(external)
    try:
        interpreter = Interpreter(statechart)
        interpreter.execute()
    finally:
        sys.modules.pop("payload_evaluations", None)
    return interpreter


def test_arguments_are_evaluated_once_at_the_send_in_written_order() -> None:
    interpreter = _run("PayloadConstruction::EvaluationOnce", [EVALUATIONS])

    context = interpreter.context
    assert (context["capturedY"], context["capturedX"]) == (401, 402)
    assert context["capturedZ"] == 5
    assert context["calls"] == 2
    assert context["current"] == 100
    assert "verified" in interpreter.configuration


def test_inherited_structured_payload_carries_its_type_values() -> None:
    interpreter = _run("PayloadConstruction::InheritedStructured", [])

    assert interpreter.context["level"] == 3
    assert "verified" in interpreter.configuration


def test_non_constant_omitted_default_is_diagnosed() -> None:
    with pytest.raises(
        UnsupportedConstructError,
        match=r"Derived::b'.*not a literal constant",
    ):
        build_statechart(
            load_model(FIXTURE), "PayloadConstruction::NonConstantDefault"
        )


def test_connected_peer_receives_the_constructed_values() -> None:
    system = build_part_system(
        load_model(FIXTURE), "PayloadConstruction::peerSystem"
    )
    # Interpreting directly (no runner) makes this test the executing
    # consumer, so it installs the generated types module itself.
    assert system.types_module is not None
    system.types_module.install()
    coordinator = PartSystemCoordinator(system)

    _trace, stop_reason = coordinator.run(max_steps=50)

    assert stop_reason is StopReason.QUIESCENT
    assert coordinator.interpreters["tx"].context["current"] == 100
    for receiver, expected in (("rx", (7, 42, 5)), ("defaultRx", (7, 9, 5))):
        interpreter = coordinator.interpreters[receiver]
        captured = tuple(
            interpreter.context[name]
            for name in ("capturedX", "capturedY", "capturedZ")
        )
        assert captured == expected, receiver
        assert "verified" in interpreter.configuration
