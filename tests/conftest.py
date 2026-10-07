import sys
from collections.abc import Iterator
from typing import Any

import pytest
from sismic.model import Statechart, Transition
from sysmlc_models.sm_examples import (  # noqa: F401  (re-exported)
    SM_EXAMPLES,
    SM_EXAMPLES_BY_DIR,
    SmExample,
)


@pytest.fixture
def fresh_external_modules() -> Iterator[None]:
    """Isolate the ``--python`` module stems the runner and CLI tests use.

    Several external-backing tests import the same stems from different
    files. Dropping those entries from ``sys.modules`` before and after
    each test stops one test's cached module from satisfying another
    test's import, regardless of execution order.
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
