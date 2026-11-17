from pathlib import Path

import pytest
import syside
from sismic.interpreter import Interpreter
from sysmlc.sysml.loading import load_model

from sysmlc_quake.builder import build_statechart

FIXTURE = Path(__file__).parent / "fixtures" / "state-names"


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_model(FIXTURE)


def test_timed_states_keep_source_names_and_independent_counters(
    model: syside.Model,
) -> None:
    chart = build_statechart(model, "StateNames::Timed")
    first, second = chart.transitions
    assert first.event != second.event
    interpreter = Interpreter(chart)
    interpreter.execute()
    assert interpreter.configuration == ["Timed", "'S.1'"]
    interpreter.clock.time = 1
    interpreter.execute()
    assert interpreter.configuration == ["Timed", "'S-1'"]
    counters = {
        name: value
        for name, value in interpreter.context.items()
        if name.startswith("_n_")
    }
    assert len(counters) == 2
    assert list(counters.values()) == [1, 1]
    interpreter.clock.time = 1.5
    interpreter.execute()
    assert interpreter.configuration == ["Timed", "'S-1'"]
    interpreter.clock.time = 2
    interpreter.execute()
    assert interpreter.configuration == ["Timed", "finished"]


def test_change_flags_remain_distinct_after_name_normalization(
    model: syside.Model,
) -> None:
    chart = build_statechart(model, "StateNames::Changed")
    interpreter = Interpreter(chart)
    interpreter.execute()
    assert interpreter.configuration == ["Changed", "'S.1'"]
    interpreter.context["ready"] = True
    interpreter.execute()
    assert interpreter.configuration == ["Changed", "'S-1'"]
    flags = {name for name in interpreter.context if name.startswith("_w_")}
    assert len(flags) == 2
    interpreter.context["ready"] = False
    interpreter.execute()
    assert interpreter.configuration == ["Changed", "finished"]


def test_composite_completion_flags_do_not_share_state(
    model: syside.Model,
) -> None:
    chart = build_statechart(model, "StateNames::Completed")
    interpreter = Interpreter(chart)
    interpreter.execute()
    assert "'S.1'::waiting" in interpreter.configuration
    interpreter.clock.time = 1
    interpreter.execute()
    assert "'S-1'::waiting" in interpreter.configuration
    flags = {
        name: value
        for name, value in interpreter.context.items()
        if name.startswith("_c_")
    }
    assert len(flags) == 2
    assert sorted(flags.values()) == [False, True]
    interpreter.clock.time = 2
    interpreter.execute()
    assert interpreter.configuration == ["Completed", "finished"]
