"""Standing guard: every shared-corpus run is non-vacuous and deterministic.

A run that fires no transition proves nothing, and sismic's
``NonDeterminismError`` marks two enabled transitions with no priority
between them. Both must stay impossible across the whole shared corpus
(positive models only: the rejection fixtures are expected failures).
"""

from __future__ import annotations

import pytest
from sysmlc.sysml.loading import load_model
from sysmlc.sysml.queries import top_level_part_usages

from examples import run_all_quake
from sysmlc_quake import runner


def _targets() -> list[tuple[str, str, str]]:
    found: list[tuple[str, str, str]] = []
    for directory in run_all_quake._model_dirs(None):
        name = run_all_quake._model_name(directory)
        if (
            list(directory.glob("*.py"))
            or run_all_quake._python_arguments(directory)
            or "sm15-rep" in name
        ):
            # External-calc and textual-rep models need foreign artifacts
            # resolved by the CLI; the CLI sweep (examples/run_all_quake.py)
            # covers them.
            continue
        for target in run_all_quake._targets(directory):
            label = f"{name}::{target.split('::')[-1]}"
            if label not in run_all_quake.EXPECTED_FAILURES:
                found.append((label, str(directory), target))
    return found


@pytest.mark.parametrize(
    ("directory", "target"),
    [(d, t) for _, d, t in _targets()],
    ids=[label for label, _, _ in _targets()],
)
def test_corpus_run_fires_and_stays_deterministic(
    directory: str, target: str
) -> None:
    model = load_model(directory)
    is_part = any(
        str(usage.qualified_name) == target
        for usage in top_level_part_usages(model)
    )
    run = runner.run_part_system if is_part else runner.run_state_def
    # ExecutionError carries sismic's NonDeterminismError text.
    report = run(model, target, max_steps=1000, until=100.0)
    assert report.trace, f"{target} fired no transition"
