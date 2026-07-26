import sys
from collections.abc import Iterator
from typing import Any

import pytest
import syside
from sismic.model import Statechart, Transition
from sysmlc.sysml.loading import load_model
from sysmlc.sysml.queries import iter_elements
from sysmlc_models.sm_examples import (  # noqa: F401  (re-exported)
    SM_EXAMPLES,
    SM_EXAMPLES_BY_DIR,
    SmExample,
)


@pytest.fixture
def fresh_external_modules() -> Iterator[None]:
    """Isolate the ``--python`` module stems the runner tests use.

    The external-backing tests import the same stems off ``sys.path``;
    dropping the entries before and after each test keeps every test on
    its own import path regardless of execution order.
    """
    for stem in ("ramp", "bump"):
        sys.modules.pop(stem, None)
    yield
    for stem in ("ramp", "bump"):
        sys.modules.pop(stem, None)


@pytest.fixture(params=["'", '"'], ids=["single-quote", "double-quote"])
def string_delimiter(request: pytest.FixtureRequest) -> Any:
    return request.param


QUAKE_PREAMBLE_IMPORTS = (
    "from math import cos as _cos, sin as _sin, tan as _tan",
    "from types import SimpleNamespace",
)


def quake_preamble(*lines: str) -> str:
    """Return expected quake preamble text with unconditional imports."""
    return "\n".join((*QUAKE_PREAMBLE_IMPORTS, *lines))


def transition_from(statechart: Statechart, source: str) -> Transition:
    """Return the single transition leaving ``source`` in ``statechart``."""
    matches = [
        transition
        for transition in statechart.transitions
        if transition.source == source
    ]
    assert len(matches) == 1, (
        f"expected exactly one transition from {source!r}, found {len(matches)}"
    )
    return matches[0]


def transition_between(
    statechart: Statechart, source: str, target: str
) -> Transition:
    """Return the transition from ``source`` to ``target``."""
    for transition in statechart.transitions:
        if transition.source == source and transition.target == target:
            return transition
    raise AssertionError(f"no transition {source} -> {target}")


def has_transition(statechart: Statechart, source: str, target: str) -> bool:
    """Whether a transition from ``source`` to ``target`` exists."""
    return any(
        transition.source == source and transition.target == target
        for transition in statechart.transitions
    )


def _discover_all_state_def_qns() -> list[tuple[SmExample, str]]:
    """Eagerly enumerate every ``StateDefinition`` QN in every sm-example.

    Used at pytest collection time to parametrize corpus-wide
    invariants over every state def declared in any example model.

    Returns:
        Pairs of ``(example, state_def_qn)`` sorted within each
        example's QN list for stable test-id ordering.
    """
    pairs: list[tuple[SmExample, str]] = []
    for example in SM_EXAMPLES:
        model = load_model(example.model_dir)
        qns = sorted(
            str(sd.qualified_name)
            for sd in iter_elements(model, syside.StateDefinition)
        )
        pairs.extend((example, qn) for qn in qns)
    return pairs


ALL_EXAMPLE_QN_PAIRS: list[tuple[SmExample, str]] = (
    _discover_all_state_def_qns()
)
