from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sysmlc.sysml.loading import load_model

from sysmlc_quake import build_statechart
from tests.conftest import SM_EXAMPLES_BY_DIR

if TYPE_CHECKING:
    import syside

EXAMPLE = SM_EXAMPLES_BY_DIR["sm03-guard"]


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_model(EXAMPLE.model_dir)


def test_only_idle_to_running_transition_is_declared(
    model: syside.Model,
) -> None:
    """One ``Transition`` from ``idle`` to ``running``.

    Every SM03 machine shares this shape; only the guard expression
    varies, so one machine stands for all of them.
    """
    sc = build_statechart(model, "SM03::MachineRef")
    assert len(sc.transitions) == 1
    only = sc.transitions[0]
    assert only.source == "idle"
    assert only.target == "running"


def test_transition_event_is_none(model: syside.Model) -> None:
    """A guarded-but-not-accept-ed transition has ``event is None``.

    Per KerML §9.2.11.1, the ``trigger [0..1]`` slot on a
    StateTransitionPerformance is populated only when an accepter is
    present. SM03's transitions carry an ``if`` clause but no
    ``accept``, so ``Transition.event`` must be ``None``. Every SM03
    machine shares this shape, so one machine stands for all of them.
    """
    sc = build_statechart(model, "SM03::MachineRef")
    assert sc.transitions[0].event is None


def test_transition_guard_is_emitted_python_source(
    model: syside.Model,
) -> None:
    """The transition's guard is the emitted Python source.

    One representative expression pins the wiring of the expression
    emitter's output into ``Transition.guard``. The full operator
    grammar is covered per shape by ``render_expression`` tests in
    tests/codegen/test_python.py, and every SM03 machine still builds
    and executes through the corpus-wide invariant in
    test_model_scenarios.py.
    """
    sc = build_statechart(model, "SM03::MachineLogicalChain")
    assert sc.transitions[0].guard == "a and b or c"
