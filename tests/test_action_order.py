from pathlib import Path

import pytest
import syside
from sismic.interpreter import Interpreter
from sysmlc.errors import UnsupportedConstructError
from sysmlc.sysml.loading import load_model

from sysmlc_quake import build_statechart

FIXTURES = Path(__file__).parent / "fixtures" / "action-order"


@pytest.fixture(scope="module")
def order_model() -> syside.Model:
    return load_model(FIXTURES)


@pytest.mark.parametrize(
    "phase",
    [
        "Entry",
        "Exit",
        "Do",
        "Effect",
        "Declaration",
        "Then",
        "Boundaries",
        "Send",
    ],
)
def test_action_order_executes(order_model: syside.Model, phase: str) -> None:
    chart = build_statechart(order_model, f"ActionOrder::Runtime{phase}")
    interpreter = Interpreter(chart)
    interpreter.execute()
    assert interpreter.context["c"] == (1 if phase == "Declaration" else 10)
    assert "success" in interpreter.configuration
    assert "failure" not in interpreter.configuration


@pytest.mark.parametrize(
    "name",
    [
        "Partial",
        "Disconnected",
        "WrongStart",
        "WrongDone",
        "Branch",
        "Merge",
        "Cycle",
        "Guarded",
        "Chained",
        "Foreign",
        "ShadowStart",
        "Multiplicity",
        "EndMultiplicity",
        "ActionMultiplicity",
        "SuccessionFlow",
    ],
)
def test_unsupported_sequence_is_rejected(
    order_model: syside.Model, name: str
) -> None:
    with pytest.raises(
        UnsupportedConstructError, match=r"succession|sequence|multiplicity"
    ) as error:
        build_statechart(order_model, f"ActionOrder::{name}")
    assert error.value.node is not None
