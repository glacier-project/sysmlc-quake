from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sysmlc_models.scenarios import SCENARIOS
from sysmlc_models.sm_examples import SM_EXAMPLES, SmExample
from sysmlc_models.validation import (
    Scenario,
    validate_quake_initialization,
    validate_scenario,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(
    "scenario",
    [s for s in SCENARIOS if "quake" in s.backends],
    ids=lambda s: s.name,
)
def test_shared_model_scenario(scenario: Scenario, tmp_path: Path) -> None:
    validate_scenario(scenario, "quake", tmp_path)


@pytest.mark.parametrize("example", SM_EXAMPLES, ids=lambda e: e.dir_name)
def test_shared_corpus_initialization(example: SmExample) -> None:
    validate_quake_initialization(f"sm-examples/{example.dir_name}")
