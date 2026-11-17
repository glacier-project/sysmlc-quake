from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sismic.interpreter import Interpreter
from sysmlc.sysml.loading import load_model

from sysmlc_quake import build_statechart
from tests import _load_inline_model
from tests.conftest import (
    SM_EXAMPLES_BY_DIR,
    transition_between,
)

if TYPE_CHECKING:
    from pathlib import Path

    import syside

EXAMPLE = SM_EXAMPLES_BY_DIR["sm18-enum-literals"]


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_model(EXAMPLE.model_dir)


def test_string_enum_default_projects_to_value(model: syside.Model) -> None:
    """A String-valued literal default projects to its declared value."""
    sc = build_statechart(model, "SM18::MachineStringEnum")
    assert 'c = "red"' in sc.preamble.splitlines()


def test_string_enum_effect_projects_to_value(model: syside.Model) -> None:
    """A String-valued literal in an effect projects to its value."""
    sc = build_statechart(model, "SM18::MachineStringEnum")
    assert transition_between(sc, "idle", "green").action == 'c = "green"'


def test_string_enum_guard_projects_and_gates_at_runtime(
    model: syside.Model,
) -> None:
    """A String-valued literal in a guard projects and gates the fire.

    The guard string carries the projected value; at runtime it lets
    the machine reach ``matched`` once the effect wrote that value.
    """
    sc = build_statechart(model, "SM18::MachineStringEnum")
    assert 'c == "green"' in sc.state_for("green").on_entry
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "matched" in interpreter.configuration
    assert interpreter.context["c"] == "green"


def test_real_enum_default_projects_to_float(model: syside.Model) -> None:
    """A Real-valued literal default projects to its float value."""
    sc = build_statechart(model, "SM18::MachineRealEnum")
    assert "g = 4.0" in sc.preamble.splitlines()


def test_real_enum_guard_projects_and_gates_at_runtime(
    model: syside.Model,
) -> None:
    """A Real-valued literal in a numeric guard projects and gates.

    The guard string carries the projected float; at runtime it lets
    the machine reach ``passed``.
    """
    sc = build_statechart(model, "SM18::MachineRealEnum")
    assert "g >= 3.0" in sc.state_for("grading").on_entry
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "passed" in interpreter.configuration


def test_plain_enum_default_is_a_generated_enum_member(
    model: syside.Model,
) -> None:
    """A plain symbolic literal default is a member of a generated class."""
    sc = build_statechart(model, "SM18::MachinePlainEnum")
    assert "from SM18_MachinePlainEnum_types import Mode" in sc.preamble
    assert "m = Mode.idle" in sc.preamble.splitlines()


def test_plain_enum_effect_assigns_the_member(model: syside.Model) -> None:
    """A plain symbolic literal in an effect is the enum member."""
    sc = build_statechart(model, "SM18::MachinePlainEnum")
    assert transition_between(sc, "ready", "working").action == "m = Mode.busy"


def test_plain_enum_guard_compares_members_and_gates_at_runtime(
    model: syside.Model,
) -> None:
    """A plain symbolic literal in a guard projects and gates the fire.

    The guard compares enum members; at runtime it lets the machine reach
    ``checked`` once the effect wrote that member.
    """
    sc = build_statechart(model, "SM18::MachinePlainEnum")
    assert "m == Mode.busy" in sc.state_for("working").on_entry
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "checked" in interpreter.configuration
    assert interpreter.context["m"].name == "busy"
    assert interpreter.context["m"] != "busy"


def test_enum_payload_send_projects_and_drives_accept(
    model: syside.Model,
) -> None:
    """A literal send payload projects and self-delivers end to end.

    The ``send()`` kwarg carries the projected declared value; the
    enum-payload self-send drives the same-machine accept.
    """
    sc = build_statechart(model, "SM18::MachineEnumPayload")
    assert (
        transition_between(sc, "idle", "armed").action
        == 'send("Announce", _sysmlc_payload=_sysmlc_new_Announce(color="yellow"))'
    )
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "fired" in interpreter.configuration


COMPUTED_VALUE_MODEL = """
package ComputedEnum {
    private import ScalarValues::*;

    enum def K :> Real {
        N = 2.0 + 2.0;
    }

    state def Machine {
        attribute x : Real := 3.0;
        entry;
            then s1;
        state s1;
        state s2;
        transition first s1 if x * K::N == 12.0 then s2;
    }
}
"""


def test_computed_enum_value_is_parenthesized(tmp_path: Path) -> None:
    """A non-atomic declared value keeps its grouping at the reference site.

    The projected value substitutes into the literal reference's atom
    position, so a computed value must be parenthesized: without parens,
    ``x * K::N`` with ``N = 2.0 + 2.0`` would emit ``x * 2.0 + 2.0`` and
    silently regroup the arithmetic.
    """
    model = _load_inline_model(tmp_path, COMPUTED_VALUE_MODEL)
    sc = build_statechart(model, "ComputedEnum::Machine")
    assert "x * (2.0 + 2.0) == 12.0" in sc.state_for("s1").on_entry
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "s2" in interpreter.configuration


IDENTITY_MODEL = """
package EnumIdentity {
    enum def Mode { enum idle; }
    enum def Phase { enum idle; }

    state def Machine {
        attribute m : Mode := Mode::idle;
        entry;
            then a;
        state a;
        state same;
        state other;
        transition first a if m == Phase::idle then other;
        transition first a if m == Mode::idle then same;
    }
}
"""


def test_same_named_literals_of_different_enums_stay_distinct(
    tmp_path: Path,
) -> None:
    """Members of two plain enums never compare equal."""
    model = _load_inline_model(tmp_path, IDENTITY_MODEL)
    sc = build_statechart(model, "EnumIdentity::Machine")
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "same" in interpreter.configuration
    assert "other" not in interpreter.configuration


SNIPPET_ONLY_MODEL = """
package EnumSnippetOnly {
    private import ScalarValues::*;
    enum def Mode { enum idle; }
    item def Go;
    state def GuardOnly {
        entry; then waiting;
        state waiting;
        state matched;
        transition first waiting accept Go if Mode::idle == Mode::idle
            then matched;
    }
    state def EffectOnly {
        attribute matched : Boolean := false;
        entry; then waiting;
        state waiting;
        state finished;
        transition first waiting accept Go
            do assign matched := Mode::idle == Mode::idle
            then finished;
    }
}
"""


@pytest.mark.parametrize("machine", ["GuardOnly", "EffectOnly"])
def test_enum_used_only_in_signal_transition_is_imported(
    tmp_path: Path, machine: str
) -> None:
    model = _load_inline_model(tmp_path, SNIPPET_ONLY_MODEL)
    interpreter = Interpreter(
        build_statechart(model, f"EnumSnippetOnly::{machine}")
    )
    interpreter.execute()
    interpreter.queue("Go")
    interpreter.execute()
    if machine == "GuardOnly":
        assert "matched" in interpreter.configuration
    else:
        assert "finished" in interpreter.configuration
        assert interpreter.context["matched"] is True


MEMBER_NAMES_MODEL = """
package EnumMemberNames {
    enum def Mode {
        enum mro;
        enum member_mro;
        enum '_value_';
        enum '__members__';
        enum '__init__';
        enum 'class';
        enum 'a-b';
        enum a_b;
        enum ordinary;
    }
    state def Machine {
        attribute a : Mode := Mode::mro;
        attribute b : Mode := Mode::member_mro;
        attribute c : Mode := Mode::'_value_';
        attribute d : Mode := Mode::'__members__';
        attribute e : Mode := Mode::'__init__';
        attribute f : Mode := Mode::'class';
        attribute g : Mode := Mode::'a-b';
        attribute h : Mode := Mode::a_b;
        attribute i : Mode := Mode::ordinary;
        entry; then idle;
        state idle;
        state matched;
        transition first idle if a == Mode::mro and g == Mode::'a-b'
            then matched;
    }
}
"""


def test_plain_enum_member_names_preserve_source_labels(
    tmp_path: Path,
) -> None:
    model = _load_inline_model(tmp_path, MEMBER_NAMES_MODEL)
    interpreter = Interpreter(
        build_statechart(model, "EnumMemberNames::Machine")
    )
    interpreter.execute()
    assert "matched" in interpreter.configuration
    members = [interpreter.context[name] for name in "abcdefghi"]
    assert [member.value for member in members] == [
        "mro",
        "member_mro",
        "_value_",
        "__members__",
        "__init__",
        "class",
        "a-b",
        "a_b",
        "ordinary",
    ]
    assert len(set(members)) == len(members)
    assert members[-1].name == "ordinary"
