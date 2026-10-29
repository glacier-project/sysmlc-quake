from __future__ import annotations

import re
from pathlib import Path

import pytest
from sismic.interpreter import Interpreter
from sismic.io import import_from_yaml
from sysmlc.cli import main
from sysmlc.errors import UnsupportedConstructError
from sysmlc.sysml.loading import load_model
from sysmlc.values import configure_model

from sysmlc_quake.builder import build_statechart

BINDINGS_DIR = Path(__file__).resolve().parent / "fixtures" / "bindings"


def _execute(interpreter: Interpreter) -> Interpreter:
    while interpreter.execute_once() is not None:
        pass
    return interpreter


def test_constant_bindings_stay_readable_while_initials_change() -> None:
    model = load_model(BINDINGS_DIR)
    interpreter = _execute(
        Interpreter(build_statechart(model, "Bindings::Machine"))
    )
    assert "finished" in interpreter.configuration
    context = interpreter.context
    # `a := 1` was reassigned; `once := a + k` ran once, at initialization.
    assert (context["a"], context["once"], context["seen"]) == (5, 2, 9)
    assert (context["k"], context["limit"], context["ratio"]) == (1, 3, -2.5)
    assert (context["positive"], context["holdTime"]) == (4, 2.0)
    # Symbolic literals project to their names, valued ones to their values.
    assert (context["setting"], context["light"]) == ("busy", "g")


def test_configured_bound_default_is_the_new_constant() -> None:
    model = configure_model(
        load_model(BINDINGS_DIR), "Bindings::Machine", {"limit": 4}
    )
    interpreter = _execute(
        Interpreter(build_statechart(model, "Bindings::Machine"))
    )
    # seen = 5 + 1 + 4, so the guard expecting the model's 3 rejects it.
    assert interpreter.context["limit"] == 4
    assert interpreter.context["seen"] == 10
    assert "wrong" in interpreter.configuration


@pytest.mark.parametrize(
    ("qn", "diagnostic"),
    [
        (
            "Bindings::DynamicBinding",
            "attribute 'b' is bound with '=' to an expression that is not "
            "a literal constant",
        ),
        (
            "Bindings::DynamicEnumeration",
            "attribute 'k' is bound with '=' to an expression that is not "
            "a literal constant",
        ),
        (
            "Bindings::BoundWrite",
            "the `entry` action of state 'idle' assigns "
            "'Bindings::BoundWrite::k', which is bound with '='",
        ),
    ],
)
def test_unsupported_binding_is_rejected(qn: str, diagnostic: str) -> None:
    with pytest.raises(UnsupportedConstructError, match=re.escape(diagnostic)):
        build_statechart(load_model(BINDINGS_DIR), qn)


def test_cli_build_reports_the_binding_diagnostic(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(
        [
            "quake",
            "build",
            str(BINDINGS_DIR),
            "-e",
            "Bindings::BoundWrite",
            "-o",
            str(tmp_path),
        ]
    )
    assert rc == 1
    assert "which is bound with '='" in capsys.readouterr().err


def test_cli_values_override_a_bound_default(tmp_path: Path) -> None:
    values = tmp_path / "values.yaml"
    values.write_text("Bindings:\n  Machine:\n    limit: 4\n")
    out = tmp_path / "out"
    rc = main(
        [
            "quake",
            "build",
            str(BINDINGS_DIR),
            "-e",
            "Bindings::Machine",
            "-o",
            str(out),
            "-f",
            "yaml",
            "--values",
            str(values),
        ]
    )
    assert rc == 0
    statechart = import_from_yaml(filepath=str(out / "Machine.yaml"))
    assert "limit = 4" in statechart.preamble.splitlines()
