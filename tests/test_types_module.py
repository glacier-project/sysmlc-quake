from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest
from sismic.interpreter import Interpreter
from sysmlc.backends import OutputOptions
from sysmlc.errors import UnsupportedConstructError
from sysmlc.sysml.loading import load_model
from sysmlc_models.sm_examples import SM_EXAMPLES_DIR

from sysmlc_quake.artifacts import (
    GeneratedPythonModule,
    QuakeStatechartArtifact,
)
from sysmlc_quake.backend import QuakeBackend
from sysmlc_quake.builder import (
    build_statechart,
    build_statechart_artifact,
)
from sysmlc_quake.parts import QuakePartSystem, build_part_system
from sysmlc_quake.runner import run_state_def
from tests import _load_inline_model

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


STRUCTURED_MODEL = """
package TypedState {
    private import ScalarValues::*;

    attribute def Point {
        attribute x : Real = 1.0;
        attribute label : String = "origin";
    }

    state def Machine {
        attribute point : Point;
        entry; then done;
    }
}
"""

NESTED_MODEL = """
package NestedTypes {
    private import ScalarValues::*;

    attribute def Inner {
        attribute z : Real = 0.25;
    }
    attribute def Box {
        attribute inner : Inner;
    }

    state def Machine {
        attribute box : Box;
        entry; then done;
    }
}
"""

EXTERNAL_MODEL = """
package TypedRun {
    private import ScalarValues::*;

    attribute def Point {
        attribute x : Real = 1.0;
    }
    calc def shift {
        in value : Point;
        return : Point;
    }

    state def Machine {
        attribute point : Point;
        entry; then idle;
        state idle;
        transition first idle
            do assign point := TypedRun::shift(point)
            then done;
    }
}
"""

PART_MODEL = """
package TypedPart {
    private import ScalarValues::*;

    item def Data {
        attribute value : Real;
    }

    state def SenderBehavior {
        port outPort;
        entry; then ready;
        state ready;
        transition first ready
            do send new Data(2.0) via outPort
            then done;
    }
    state def ReceiverBehavior {
        port inPort;
        entry; then waiting;
        state waiting;
        transition first waiting accept Data via inPort then done;
    }

    part def Sender { port outPort; exhibit state : SenderBehavior; }
    part def Receiver { port inPort; exhibit state : ReceiverBehavior; }
    part system {
        part tx : Sender;
        part rx : Receiver;
        connect tx.outPort to rx.inPort;
    }
}
"""


@pytest.fixture(autouse=True)
def clean_generated_modules() -> Iterator[None]:
    names = (
        "NestedTypes_Machine_types",
        "RuntimeConflict_types",
        "TypedPart_system_types",
        "TypedRun_Machine_types",
        "TypedState_Machine_types",
        "typed_support",
    )
    for name in names:
        sys.modules.pop(name, None)
    yield
    for name in names:
        sys.modules.pop(name, None)


def test_statechart_artifact_owns_generated_types_module(
    tmp_path: Path,
) -> None:
    model = _load_inline_model(tmp_path, STRUCTURED_MODEL)

    artifact = build_statechart_artifact(model, "TypedState::Machine")

    assert isinstance(artifact, QuakeStatechartArtifact)
    assert artifact.types_module is not None
    assert artifact.types_module.name == "TypedState_Machine_types"
    assert artifact.types_module.source == (
        "from __future__ import annotations\n"
        "\n"
        "from dataclasses import dataclass\n"
        "\n"
        "@dataclass\n"
        "class Point:\n"
        "    x: float = 1.0\n"
        '    label: str = "origin"\n'
    )
    assert artifact.statechart.preamble.splitlines() == [
        "from math import cos as _cos, sin as _sin, tan as _tan",
        "from TypedState_Machine_types import Point",
        'point = Point(x=1.0, label="origin")',
    ]

    generated = sys.modules["TypedState_Machine_types"]
    interpreter = Interpreter(artifact.statechart)
    interpreter.execute()
    assert isinstance(interpreter.context["point"], generated.Point)


def test_public_builder_keeps_returning_a_runnable_statechart(
    tmp_path: Path,
) -> None:
    model = _load_inline_model(tmp_path, STRUCTURED_MODEL)

    statechart = build_statechart(model, "TypedState::Machine")

    Interpreter(statechart).execute()


def test_backend_writes_companion_module(tmp_path: Path) -> None:
    model = _load_inline_model(tmp_path, STRUCTURED_MODEL)
    backend = QuakeBackend()
    artifact = backend.build(model, "TypedState::Machine")
    out = tmp_path / "out"

    written = backend.write(
        artifact,
        OutputOptions(output_dir=out, formats=("yaml",)),
    )

    assert sorted(path.name for path in written) == [
        "Machine.yaml",
        "TypedState_Machine_types.py",
    ]
    assert artifact.types_module is not None
    assert (
        out / "TypedState_Machine_types.py"
    ).read_text() == artifact.types_module.source


def test_nested_composites_register_every_dataclass(tmp_path: Path) -> None:
    model = _load_inline_model(tmp_path, NESTED_MODEL)

    artifact = build_statechart_artifact(model, "NestedTypes::Machine")

    assert artifact.types_module is not None
    assert "class Box:" in artifact.types_module.source
    assert "    inner: Inner = None" in artifact.types_module.source
    assert "class Inner:" in artifact.types_module.source
    interpreter = Interpreter(artifact.statechart)
    interpreter.execute()
    box = interpreter.context["box"]
    generated = sys.modules["NestedTypes_Machine_types"]
    assert isinstance(box, generated.Box)
    assert isinstance(box.inner, generated.Inner)
    assert box.inner.z == 0.25


def test_external_module_can_import_generated_type_at_top_level(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = _load_inline_model(tmp_path, EXTERNAL_MODEL)
    support = tmp_path / "typed_support.py"
    support.write_text(
        "from TypedRun_Machine_types import Point\n"
        "\n"
        "def shift(value):\n"
        "    assert isinstance(value, Point)\n"
        "    return Point(x=value.x + 1.0)\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    report = run_state_def(
        model,
        "TypedRun::Machine",
        external=("typed_support", frozenset({"shift"})),
    )

    assert report.all_final
    support_module = sys.modules["typed_support"]
    generated = sys.modules["TypedRun_Machine_types"]
    assert support_module.Point is generated.Point


def test_part_system_shares_one_generated_types_module(
    tmp_path: Path,
) -> None:
    model = _load_inline_model(tmp_path, PART_MODEL)

    system = build_part_system(model, "TypedPart::system")

    assert isinstance(system, QuakePartSystem)
    assert system.types_module is not None
    assert system.types_module.name == "TypedPart_system_types"
    assert "class Data:" in system.types_module.source
    assert "    value: float = None" in system.types_module.source
    for statechart in system.statecharts.values():
        assert (
            "from TypedPart_system_types import Data"
            in statechart.preamble.splitlines()
        )
    backend = QuakeBackend()
    written = backend.write(
        system,
        OutputOptions(
            output_dir=tmp_path / "out",
            formats=("yaml",),
            basename="system",
        ),
    )
    assert "system/TypedPart_system_types.py" in {
        path.relative_to(tmp_path / "out").as_posix() for path in written
    }


def test_scalar_statechart_has_no_generated_types_module() -> None:
    backend = QuakeBackend()
    model = load_model(SM_EXAMPLES_DIR / "sm01-helloworld")

    artifact = backend.build(model, "SM01::Machine")

    assert isinstance(artifact, QuakeStatechartArtifact)
    assert artifact.types_module is None


def test_generated_module_install_is_idempotent_but_rejects_collision() -> None:
    original = GeneratedPythonModule(
        name="RuntimeConflict_types",
        lines=("value = 1",),
    )
    same = GeneratedPythonModule(
        name="RuntimeConflict_types",
        lines=("value = 1",),
    )
    conflicting = GeneratedPythonModule(
        name="RuntimeConflict_types",
        lines=("value = 2",),
    )

    assert original.install() is same.install()
    with pytest.raises(UnsupportedConstructError, match="different content"):
        conflicting.install()
