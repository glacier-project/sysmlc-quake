from __future__ import annotations

import dataclasses
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
from sismic.clock import SimulatedClock
from sismic.interpreter import Interpreter
from sysmlc.backends.base import OutputOptions
from sysmlc.cli import _load_external_modules
from sysmlc.errors import UnsupportedConstructError
from sysmlc.sysml.foreign_artifact.base import ForeignArtifact
from sysmlc.sysml.loading import load_model

from sysmlc_quake import (
    PAYLOAD_DATA_KEY,
    build_statechart_artifact,
    payload_event,
)
from sysmlc_quake.backend import QuakeBackend
from sysmlc_quake.coordinator import PartSystemCoordinator
from sysmlc_quake.parts import build_part_system
from tests import _load_inline_model

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import ModuleType

    import syside

    from sysmlc_quake.artifacts import QuakeStatechartArtifact

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "payload-envelope"
PROBE = [ForeignArtifact(FIXTURE / "envelope_probe.py", "python")]
CAPTURED = ("capturedName", "capturedData", "capturedDelay", "kept")


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_model(FIXTURE)


@pytest.fixture
def probe() -> Iterator[ModuleType]:
    sys.modules.pop("envelope_probe", None)
    _load_external_modules(PROBE)
    yield sys.modules["envelope_probe"]
    sys.modules.pop("envelope_probe", None)


def _start(
    model: syside.Model, name: str
) -> tuple[QuakeStatechartArtifact, Interpreter, SimulatedClock]:
    artifact = build_statechart_artifact(
        model, f"PayloadEnvelope::{name}", external=PROBE
    )
    if artifact.types_module is not None:
        artifact.types_module.install()
    clock = SimulatedClock()
    interpreter = Interpreter(artifact.statechart, clock=clock)
    interpreter.execute()
    return artifact, interpreter, clock


def _captured(interpreter: Interpreter) -> tuple[object, ...]:
    return tuple(interpreter.context[name] for name in CAPTURED)


def _field_values(payload: Any) -> dict[str, object]:
    return {
        field.name: getattr(payload, field.name)
        for field in dataclasses.fields(payload)
    }


def test_self_send_carries_reserved_names_at_current_time(
    model: syside.Model, probe: ModuleType
) -> None:
    artifact, interpreter, clock = _start(model, "SelfSend")

    assert "received" in interpreter.configuration
    assert clock.time == 0
    # data = sample(40): one evaluation, at the send, before `current`
    # changes on entering `armed`.
    assert _captured(interpreter) == ("n", 401, 2.5, True)
    assert probe.calls == 1
    (whole,) = probe.kept
    assert type(whole).__name__ == "Meta"
    assert _field_values(whole) == {"name": "n", "data": 401, "delay": 2.5}
    assert artifact.statechart.preamble is not None
    assert "_sysmlc_payload_of" in artifact.statechart.preamble


def test_inherited_and_nested_payloads_keep_field_values(
    model: syside.Model, probe: ModuleType
) -> None:
    _artifact, interpreter, clock = _start(model, "InheritedNested")

    assert "received" in interpreter.configuration
    assert clock.time == 0
    context = interpreter.context
    assert context["capturedName"] == "t"
    assert (context["innerName"], context["innerDelay"]) == ("inner", 1.5)
    assert context["wrappedData"] == 6
    (whole,) = probe.kept
    assert type(whole).__name__ == "Tagged"
    assert _field_values(whole) == {
        "name": "t",
        "data": 8,
        "delay": 0.5,
        "extra": 3,
    }


def test_named_whole_marker_payload_has_no_event_metadata(
    model: syside.Model, probe: ModuleType
) -> None:
    artifact, interpreter, _clock = _start(model, "MarkerWhole")

    assert "received" in interpreter.configuration
    (whole,) = probe.kept
    assert isinstance(whole, SimpleNamespace)
    assert vars(whole) == {}
    # Markers keep their bare-event representation.
    assert 'send("Ping")' in {
        transition.action for transition in artifact.statechart.transitions
    }


def test_payload_event_carries_only_the_envelope() -> None:
    event = payload_event("Meta", {"name": "x", "data": 5, "delay": 4.0})

    assert event.name == "Meta"
    assert list(event.data) == [PAYLOAD_DATA_KEY]
    assert vars(event.data[PAYLOAD_DATA_KEY]) == {
        "name": "x",
        "data": 5,
        "delay": 4.0,
    }
    assert getattr(event, "delay", 0) == 0
    assert list(payload_event("Ping").data) == [PAYLOAD_DATA_KEY]


def test_external_helper_injects_reserved_names_without_delay(
    model: syside.Model, probe: ModuleType
) -> None:
    artifact, interpreter, clock = _start(model, "External")

    interpreter.queue(
        payload_event(
            artifact.resolve_external("Meta"),
            {"name": "x", "data": 5, "delay": 4.0},
        )
    )
    interpreter.execute()

    assert "received" in interpreter.configuration
    assert clock.time == 0
    assert _captured(interpreter) == ("x", 5, 4.0, True)
    (whole,) = probe.kept
    assert vars(whole) == {"name": "x", "data": 5, "delay": 4.0}


def test_routed_peer_receives_one_event_with_send_time_values(
    model: syside.Model, probe: ModuleType
) -> None:
    system = build_part_system(
        model, "PayloadEnvelope::peerSystem", external=PROBE
    )
    assert system.types_module is not None
    system.types_module.install()
    coordinator = PartSystemCoordinator(system)

    trace, _reason = coordinator.run(max_steps=50)

    received = [
        entry
        for entry in trace
        if entry.instance == "rx" and entry.step.event is not None
    ]
    assert [entry.step.time for entry in received] == [0]
    assert list(received[0].step.event.data) == [PAYLOAD_DATA_KEY]
    rx = coordinator.interpreters["rx"]
    assert "received" in rx.configuration
    assert _captured(rx) == ("peer", 401, 9.0, True)
    assert probe.calls == 1
    assert _field_values(probe.kept[0]) == {
        "name": "peer",
        "data": 401,
        "delay": 9.0,
    }


def test_written_yaml_and_companion_reload_in_a_clean_process(
    model: syside.Model, tmp_path: Path
) -> None:
    backend = QuakeBackend()
    artifact = build_statechart_artifact(
        model, "PayloadEnvelope::SelfSend", external=PROBE
    )
    backend.write(
        artifact, OutputOptions(output_dir=tmp_path, formats=("yaml",))
    )
    shutil.copy(FIXTURE / "envelope_probe.py", tmp_path)
    script = (
        "import json, sys\n"
        "sys.path.insert(0, '.')\n"
        "from sismic.io import import_from_yaml\n"
        "from sismic.interpreter import Interpreter\n"
        "import envelope_probe\n"
        "chart = import_from_yaml(filepath='SelfSend.yaml')\n"
        "interpreter = Interpreter(chart)\n"
        "interpreter.execute()\n"
        "whole = envelope_probe.kept[0]\n"
        "print(json.dumps({\n"
        "    'configuration': sorted(interpreter.configuration),\n"
        "    'captured': [interpreter.context[n] for n in\n"
        f"                 {list(CAPTURED)!r}],\n"
        "    'calls': envelope_probe.calls,\n"
        "    'whole': [type(whole).__name__, vars(whole)],\n"
        "}))\n"
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )

    assert json.loads(completed.stdout) == {
        "configuration": ["SelfSend", "received"],
        "captured": ["n", 401, 2.5, True],
        "calls": 1,
        "whole": ["Meta", {"name": "n", "data": 401, "delay": 2.5}],
    }


READER_COLLISION_MODEL = """
package ReaderCollision {
    private import ScalarValues::*;
    attribute def '_sysmlc_payload_of' { attribute x : Integer default 1; }
    item def Carrier { attribute inner : '_sysmlc_payload_of'; }
    state def Machine {
        attribute captured : Integer := 0;
        port p;
        entry; then idle;
        state idle;
        state armed;
        state received;
        transition first idle do send new Carrier() to p then armed;
        transition first armed accept c : Carrier
            do assign captured := c.inner.x then received;
    }
}
"""


def test_generated_type_named_like_the_reader_keeps_a_distinct_symbol(
    tmp_path: Path,
) -> None:
    model = _load_inline_model(tmp_path, READER_COLLISION_MODEL)

    artifact = build_statechart_artifact(model, "ReaderCollision::Machine")
    assert artifact.types_module is not None
    artifact.types_module.install()
    interpreter = Interpreter(artifact.statechart)
    interpreter.execute()

    assert "received" in interpreter.configuration
    assert interpreter.context["captured"] == 1


EXTERNAL_COLLISION_MODEL = """
package ExternalCollision {
    private import ScalarValues::*;
    calc def '_sysmlc_payload_of' { in v : Integer; return : Integer; }
    item def Reading { attribute value : Integer default 2; }
    state def Machine {
        attribute captured : Integer := 0;
        port p;
        entry; then idle;
        state idle;
        state armed;
        state received;
        transition first idle do send new Reading() to p then armed;
        transition first armed accept r : Reading
            do assign captured := '_sysmlc_payload_of'(r.value)
            then received;
    }
}
"""


def test_external_function_named_like_the_reader_is_rejected(
    tmp_path: Path,
) -> None:
    model = _load_inline_model(tmp_path, EXTERNAL_COLLISION_MODEL)
    support = tmp_path / "collision_support.py"
    support.write_text("def _sysmlc_payload_of(v):\n    return v\n")

    with pytest.raises(UnsupportedConstructError, match="_sysmlc_payload_of"):
        build_statechart_artifact(
            model,
            "ExternalCollision::Machine",
            external=[ForeignArtifact(support, "python")],
        )


SHADOW_MODEL = """
package Shadow {
    private import ScalarValues::*;
    item def Reading { attribute value : Integer default 41; }
    state def Machine {
        attribute Reading : Integer := 7;
        attribute captured : Integer := 0;
        port comm;
        entry; then idle;
        state idle;
        state armed;
        state received;
        transition first idle do send new Shadow::Reading() to comm then armed;
        transition first armed accept packet : Shadow::Reading via comm
            do assign captured := packet.value + Reading then received;
    }
}
"""


def test_attribute_named_like_the_payload_type_keeps_the_constructor(
    tmp_path: Path,
) -> None:
    model = _load_inline_model(tmp_path, SHADOW_MODEL)

    artifact = build_statechart_artifact(model, "Shadow::Machine")
    assert artifact.types_module is not None
    artifact.types_module.install()
    interpreter = Interpreter(artifact.statechart)
    interpreter.execute()

    assert sorted(interpreter.configuration) == ["Machine", "received"]
    # The payload default 41 plus the machine attribute Reading = 7.
    assert interpreter.context["captured"] == 48


def test_shadowing_attribute_model_reloads_from_yaml_in_a_clean_process(
    tmp_path: Path,
) -> None:
    (tmp_path / "model").mkdir()
    model = _load_inline_model(tmp_path / "model", SHADOW_MODEL)
    artifact = build_statechart_artifact(model, "Shadow::Machine")
    QuakeBackend().write(
        artifact, OutputOptions(output_dir=tmp_path, formats=("yaml",))
    )
    script = (
        "import json, sys\n"
        "sys.path.insert(0, '.')\n"
        "from sismic.io import import_from_yaml\n"
        "from sismic.interpreter import Interpreter\n"
        "chart = import_from_yaml(filepath='Machine.yaml')\n"
        "interpreter = Interpreter(chart)\n"
        "interpreter.execute()\n"
        "print(json.dumps([sorted(interpreter.configuration),\n"
        "                  interpreter.context['captured']]))\n"
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )

    assert json.loads(completed.stdout) == [["Machine", "received"], 48]


CONSTRUCTOR_COLLISION_MODEL = """
package ConstructorCollision {
    private import ScalarValues::*;
    calc def '_sysmlc_new_Reading' { in v : Integer; return : Integer; }
    item def Reading { attribute value : Integer default 2; }
    state def Machine {
        attribute captured : Integer := 0;
        port p;
        entry; then idle;
        state idle;
        state armed;
        state received;
        transition first idle do send new Reading() to p then armed;
        transition first armed accept Reading
            do assign captured := '_sysmlc_new_Reading'(1) then received;
    }
}
"""


def test_external_function_named_like_a_constructor_alias_is_rejected(
    tmp_path: Path,
) -> None:
    model = _load_inline_model(tmp_path, CONSTRUCTOR_COLLISION_MODEL)
    support = tmp_path / "constructor_support.py"
    support.write_text("def _sysmlc_new_Reading(v):\n    return v\n")

    with pytest.raises(UnsupportedConstructError, match="_sysmlc_new_Reading"):
        build_statechart_artifact(
            model,
            "ConstructorCollision::Machine",
            external=[ForeignArtifact(support, "python")],
        )
