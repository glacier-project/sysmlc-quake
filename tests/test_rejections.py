from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sysmlc.errors import UnsupportedConstructError
from sysmlc.sysml.loading import load_model

from sysmlc_quake import build_statechart

if TYPE_CHECKING:
    import syside

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "rejections"


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_model(FIXTURES_DIR)


def test_eventless_self_loop_is_rejected(model: syside.Model) -> None:
    """An eventless self-loop transition would never stabilize."""
    with pytest.raises(UnsupportedConstructError, match=r"never stabilize"):
        build_statechart(model, "Rejections::MachineSelfLoop")


def test_send_to_peer_is_rejected(model: syside.Model) -> None:
    """A `to` receiver naming another occurrence is cross-machine
    addressing, which a single statechart cannot deliver."""
    with pytest.raises(UnsupportedConstructError, match="own port"):
        build_statechart(model, "Rejections::MachineSendToPeer")


def test_send_to_peer_port_is_rejected(model: syside.Model) -> None:
    """A chained `to` receiver (another machine's port) is rejected too."""
    with pytest.raises(UnsupportedConstructError, match="own port"):
        build_statechart(model, "Rejections::MachineSendToPeerPort")


def test_negative_after_duration_is_rejected(model: syside.Model) -> None:
    """An `accept after` duration must be finite and non-negative."""
    with pytest.raises(ValueError, match=r"finite, non-negative"):
        build_statechart(model, "Rejections::MachineNegDuration")


def test_missing_initial_state_is_rejected(model: syside.Model) -> None:
    """A state definition without an initial substate fails loudly."""
    with pytest.raises(ValueError, match="No initial state for"):
        build_statechart(model, "Rejections::MachineNoInitial")


@pytest.mark.parametrize(
    "machine_qn",
    [
        "Rejections::MachineDeepInitialQualifiedName",
        "Rejections::MachineDeepInitialFeatureChain",
        "Rejections::MachineDeepInitialConflict",
    ],
)
def test_deep_initial_targets_are_rejected(
    model: syside.Model,
    machine_qn: str,
) -> None:
    """Initial targets must resolve to direct substates."""
    with pytest.raises(UnsupportedConstructError, match="direct substate"):
        build_statechart(model, machine_qn)


def test_structured_enum_literal_is_rejected(model: syside.Model) -> None:
    """A structured enum literal has no single primitive projection."""
    with pytest.raises(UnsupportedConstructError, match="is structured"):
        build_statechart(model, "Rejections::MachineStructuredEnum")


@pytest.mark.parametrize(
    ("machine_qn", "message"),
    [
        ("Rejections::MachineEntryReference", "`entry` action that references"),
        ("Rejections::MachineExitReference", "`exit` action that references"),
        ("Rejections::MachineEffectReference", "effect that references"),
        (
            "Rejections::MachineStandaloneSuccession",
            "standalone `first A then B;` succession",
        ),
        ("Rejections::MachineSubmachineUsage", "submachine reuse"),
        ("Rejections::MachineRootNamedState", "name of its state definition"),
        ("Rejections::MachineUnderscoreState", "starts with an underscore"),
        ("Rejections::MachineShadowsMax", "shadow the builtin"),
        (
            "Rejections::MachineTransitionConstraint",
            "asserted constraint in a transition body",
        ),
    ],
)
def test_unmapped_construct_is_rejected_not_dropped(
    model: syside.Model, machine_qn: str, message: str
) -> None:
    """Constructs without a mapping fail loudly instead of vanishing."""
    with pytest.raises(UnsupportedConstructError, match=message):
        build_statechart(model, machine_qn)


def test_c_only_textual_representation_names_its_cause() -> None:
    """A calc def with only a C representation cannot run in quake."""
    from tests.test_parts import MULTI

    model = load_model(MULTI.parent / "sm15-rep-c")
    with pytest.raises(UnsupportedConstructError, match="only C textual"):
        build_statechart(model, "SM15RepC::Ramp")
