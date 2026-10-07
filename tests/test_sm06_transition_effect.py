from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from sysmlc.sysml.loading import load_model

from sysmlc_quake import build_statechart
from tests.conftest import SM_EXAMPLES_BY_DIR, transition_from

if TYPE_CHECKING:
    import syside

EXAMPLE = SM_EXAMPLES_BY_DIR["sm06-transition-effect"]

EFFECT_SOURCE = "idle"


@dataclass(frozen=True)
class EffectCase:
    """One sm06 transition-effect variation.

    Attributes:
        state_def_qn: Qualified name of the SM06 state def under test.
        expected_action: Python statement string the builder must place
            in the ``Transition.action`` slot of the transition leaving
            ``idle``.
    """

    state_def_qn: str
    expected_action: str


CASES: list[EffectCase] = [
    # Single increment effect on the first of two transitions; the second
    # transition (armed -> running) carries no effect.
    EffectCase(
        "SM06::MachineEffect",
        expected_action="counter = counter + 1",
    ),
    # Two assigns in one effect body, joined in declaration order.
    EffectCase(
        "SM06::MachineEffectMulti",
        expected_action="a = 1\nb = a + 2",
    ),
]


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_model(EXAMPLE.model_dir)


@pytest.mark.parametrize(
    "case", CASES, ids=lambda case: case.state_def_qn.split("::", 1)[1]
)
def test_effect_emitted_on_its_transition_only(
    model: syside.Model,
    case: EffectCase,
) -> None:
    """Only the source transition carries the generated effect."""
    sc = build_statechart(model, case.state_def_qn)
    assert transition_from(sc, EFFECT_SOURCE).action == case.expected_action
    sources_with_action = {
        t.source for t in sc.transitions if t.action is not None
    }
    assert sources_with_action == {EFFECT_SOURCE}
