from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import pytest
import syside
from sysmlc.codegen.python import PythonCodeGenContext

from sysmlc_quake.codegen import SismicCodeGen
from tests import _load_inline_model, _single_element


def _get_sismic_py_codegen(
    quote: str, *, part_system_mode: bool = False
) -> SismicCodeGen:
    context = PythonCodeGenContext(string_delimiter=quote)
    return SismicCodeGen(context, part_system_mode=part_system_mode)


_SEND_VIA_MODEL = """
package Test {
    item def Ping;

    state def Machine {
        port commPort;

        entry;
            then idle;
        state idle;
        state running;

        transition first idle
            do send new Ping() via commPort
            then running;
    }
}
"""


class TestSismicCodeGen:
    def test_send_action_via_is_dropped_without_routing(
        self, string_delimiter: str, tmp_path: Path
    ) -> None:
        # A send through a port delivers only over the port's connections;
        # without a part system there are none, so nothing is emitted.
        code_gen = _get_sismic_py_codegen(string_delimiter)
        model = _load_inline_model(tmp_path, _SEND_VIA_MODEL)

        send = _single_element(model, syside.SendActionUsage)
        emitted = code_gen.render_action(send)

        assert emitted == ""

    def test_send_action_via_routes_in_part_mode(
        self, string_delimiter: str, tmp_path: Path
    ) -> None:
        code_gen = _get_sismic_py_codegen(
            string_delimiter, part_system_mode=True
        )
        model = _load_inline_model(tmp_path, _SEND_VIA_MODEL)

        send = _single_element(model, syside.SendActionUsage)
        emitted = code_gen.render_action(send)

        assert emitted == (
            f"_sysmlc_route({string_delimiter}Ping{string_delimiter}, "
            f"{string_delimiter}commPort{string_delimiter})"
        )


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("equipment.flag", "equipment.flag"),
        ("(plant.equipment).flag", "plant.equipment.flag"),
    ],
)
def test_member_assignment_mutates_the_resolved_receiver(
    tmp_path: Path, target: str, expected: str
) -> None:
    source = """package Targets {
    private import ScalarValues::*;
    part def Equipment { attribute flag : Boolean; }
    part def Plant { part equipment : Equipment; }
    state def Machine {
        in ref equipment : Equipment;
        in ref plant : Plant;
        entry; then idle;
        state idle { entry assign TARGET := true; }
    }
}"""
    model = _load_inline_model(tmp_path, source.replace("TARGET", target))
    assign = _single_element(model, syside.AssignmentActionUsage)
    gen = SismicCodeGen()
    equipment = SimpleNamespace(flag=False)
    plant = SimpleNamespace(equipment=SimpleNamespace(flag=False))
    context = {"equipment": equipment, "plant": plant, "flag": False}
    assert gen.render_assignment_target(assign) == expected
    exec(gen.render_action(assign), context)
    assert equipment.flag is (target == "equipment.flag")
    assert plant.equipment.flag is (target != "equipment.flag")
    assert context["flag"] is False
