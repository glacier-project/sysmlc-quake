from pathlib import Path

import pytest
import syside
from sismic.exceptions import InvariantError
from sismic.interpreter import Interpreter
from sismic.io import import_from_yaml
from sysmlc.sysml.loading import load_model

from sysmlc_quake.builder import build_statechart_artifact
from sysmlc_quake.serialize import to_yaml

_FIXTURE = Path(__file__).parent / "fixtures" / "constraint-identity"


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_model(_FIXTURE)


@pytest.mark.parametrize(
    "machine,scope,name,check_id",
    [
        ("DuplicateConditions", "", "firstLimit", 0),
        ("ScopedNames", "idle", "limit", 0),
        ("Anonymous", "", None, 0),
    ],
)
def test_serialized_failure_identifies_one_original_constraint(
    model: syside.Model,
    machine: str,
    scope: str,
    name: str | None,
    check_id: int,
) -> None:
    artifact = build_statechart_artifact(
        model, f"ConstraintIdentity::{machine}"
    )
    assert len({i.condition for i in artifact.invariants}) == 2
    restored = import_from_yaml(to_yaml(artifact.statechart))
    with pytest.raises(InvariantError) as raised:
        Interpreter(restored).execute()
    matches = [
        i
        for i in artifact.invariants
        if i.state == raised.value.obj.name
        and i.condition == raised.value.condition
    ]
    assert len(matches) == 1
    assert (matches[0].scope, matches[0].name, matches[0].check_id) == (
        scope,
        name,
        check_id,
    )


def test_late_violation_preserves_a_quoted_constraint_name(
    model: syside.Model,
) -> None:
    artifact = build_statechart_artifact(model, "ConstraintIdentity::Delayed")
    interpreter = Interpreter(artifact.statechart)
    interpreter.execute()
    interpreter.queue("Tick")
    with pytest.raises(InvariantError) as raised:
        interpreter.execute()
    (invariant,) = artifact.invariants
    assert invariant.name == 'limit "quoted"'
    assert raised.value.condition == invariant.condition
