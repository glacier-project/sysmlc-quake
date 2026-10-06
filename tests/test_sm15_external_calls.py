from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sysmlc.errors import UnsupportedConstructError
from sysmlc.sysml.foreign_artifact.base import ForeignArtifact
from sysmlc.sysml.loading import load_model
from sysmlc_models.sm_examples import SM_EXAMPLES_DIR

from sysmlc_quake import build_statechart
from tests.conftest import transition_from

if TYPE_CHECKING:
    from pathlib import Path

SM15_DIR = SM_EXAMPLES_DIR / "sm15-external"
RAMP_ARTIFACT = ForeignArtifact(SM15_DIR / "ramp.py", "python")


def test_external_call_builds_sm15_ramp() -> None:
    model = load_model(SM15_DIR)
    sc = build_statechart(model, "SM15::Ramp", external=[RAMP_ARTIFACT])

    assert transition_from(sc, "run").action == "x = step(x, 0.1)"
    assert "from ramp import step" in sc.preamble.splitlines()


def test_unused_external_names_are_not_imported() -> None:
    # Importing a function the machine never calls would make the emitted
    # statechart depend on the module for no reason.
    model = load_model(SM15_DIR)
    sc = build_statechart(
        model,
        "SM15::Ramp",
        external=[RAMP_ARTIFACT],
    )

    lines = sc.preamble.splitlines()
    assert "from ramp import step" in lines
    assert "from ramp import unused" not in lines


def test_missing_external_function_names_function_and_module(
    tmp_path: Path,
) -> None:
    model = load_model(SM15_DIR)
    support = tmp_path / "phys.py"
    support.write_text("def unrelated():\n    return 0\n")
    with pytest.raises(UnsupportedConstructError, match=r"step"):
        build_statechart(
            model,
            "SM15::Ramp",
            external=[ForeignArtifact(support, "python")],
        )


def test_entry_import_survives_named_payload_transition_at_runtime(
    tmp_path: Path,
) -> None:
    from sismic.interpreter import Interpreter
    from sysmlc.cli import _load_external_modules

    (tmp_path / "model.sysml").write_text("""
        package PayloadTracking {
            private import ScalarValues::*;
            item def Reading { attribute value : Real; }
            calc def step { in x : Real; in dt : Real; return : Real; }
            state def Machine {
                attribute x : Real := 0.0;
                entry; then idle;
                state idle { entry assign x := step(x, 0.1); }
                state running;
                transition first idle accept reading : Reading
                    do assign x := reading.value then running;
            }
        }
    """)
    support = tmp_path / "payload_support.py"
    support.write_text("def step(x, dt): return x + dt\n")
    external = [ForeignArtifact(support, "python")]
    statechart = build_statechart(
        load_model(tmp_path), "PayloadTracking::Machine", external=external
    )
    assert (
        "from payload_support import step" in statechart.preamble.splitlines()
    )
    _load_external_modules(external)
    interpreter = Interpreter(statechart)
    interpreter.execute()
    assert interpreter.context["x"] == pytest.approx(0.1)
    interpreter.queue("Reading", value=2.0)
    interpreter.execute()
    assert interpreter.context["x"] == pytest.approx(2.0)


def test_python_symbol_ambiguity_fails_before_generating_imports(
    tmp_path: Path,
) -> None:
    from sysmlc.sysml.foreign_artifact.base import ForeignArtifactError

    files = []
    for name in ("first", "second"):
        path = tmp_path / f"{name}.py"
        path.write_text("def step(x, dt): return x + dt\n")
        files.append(ForeignArtifact(path, "python"))
    for ordered in (files, files[::-1]):
        with pytest.raises(
            ForeignArtifactError, match="ambiguous python function 'step'"
        ):
            build_statechart(
                load_model(SM15_DIR), "SM15::Ramp", external=ordered
            )
