from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from sysmlc.sysml.loading import load_model

from sysmlc_quake import build_statechart
from tests.conftest import SM_EXAMPLES_BY_DIR

if TYPE_CHECKING:
    import syside

EXAMPLE = SM_EXAMPLES_BY_DIR["sm04-assignment"]

# Every sm04 state def carries its action(s) on substate ``idle`` and
# leaves substate ``running`` action free.
ACTION_STATE = "idle"
ACTION_FREE_STATE = "running"


@dataclass(frozen=True)
class AssignCase:
    """One sm04 assignment-action variation.

    Attributes:
        state_def_qn: Qualified name of the SM04 state def under test.
        expected_on_entry: Python statement string the builder must place
            in the ``idle`` state's ``on_entry`` slot, or ``None`` when
            ``idle`` declares no entry action.
        expected_on_exit: Python statement string the builder must place
            in the ``idle`` state's ``on_exit`` slot, or ``None`` when
            ``idle`` declares no exit action.
    """

    state_def_qn: str
    expected_on_entry: str | None
    expected_on_exit: str | None


CASES: list[AssignCase] = [
    # Single self-referential increment in an entry action.
    AssignCase(
        "SM04::MachineEntryIncrement",
        expected_on_entry="counter = counter + 1",
        expected_on_exit=None,
    ),
    # Single decrement in an exit action.
    AssignCase(
        "SM04::MachineExitDecrement",
        expected_on_entry=None,
        expected_on_exit="counter = counter - 1",
    ),
    # Two assigns in one entry action, joined in declaration order.
    AssignCase(
        "SM04::MachineMultiEntry",
        expected_on_entry="a = 1\nb = a + 2",
        expected_on_exit=None,
    ),
    # Entry and exit assigns on the same substate, distinct attributes.
    AssignCase(
        "SM04::MachineEntryAndExit",
        expected_on_entry="entered = entered + 1",
        expected_on_exit="exited = exited + 1",
    ),
    # Shorthand entry assign (`entry assign x := e;`, no `action { }`).
    AssignCase(
        "SM04::MachineEntryShorthand",
        expected_on_entry="counter = counter + 1",
        expected_on_exit=None,
    ),
    # Shorthand exit assign (`exit assign x := e;`).
    AssignCase(
        "SM04::MachineExitShorthand",
        expected_on_entry=None,
        expected_on_exit="counter = counter - 1",
    ),
]


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_model(EXAMPLE.model_dir)


@pytest.mark.parametrize(
    "case", CASES, ids=lambda case: case.state_def_qn.split("::", 1)[1]
)
def test_assign_actions_emitted_into_slots(
    model: syside.Model,
    case: AssignCase,
) -> None:
    """Entry and exit assignments use their respective target slots."""
    sc = build_statechart(model, case.state_def_qn)
    assert sc.state_for(ACTION_STATE).on_entry == case.expected_on_entry
    assert sc.state_for(ACTION_STATE).on_exit == case.expected_on_exit
    assert sc.state_for(ACTION_FREE_STATE).on_entry is None
    assert sc.state_for(ACTION_FREE_STATE).on_exit is None
