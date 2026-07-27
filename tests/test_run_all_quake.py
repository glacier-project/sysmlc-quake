from __future__ import annotations

from typing import TYPE_CHECKING

from examples import run_all_quake

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _configure_corpus(monkeypatch: pytest.MonkeyPatch, root: Path) -> Path:
    showcase = root / "showcase"
    monkeypatch.setattr(
        run_all_quake,
        "CORPUS_DIRS",
        {"showcase": showcase},
    )
    monkeypatch.setattr(run_all_quake, "SHARED_PYTHON_SUPPORT", {})
    return showcase


def test_model_dirs_discovers_nested_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    showcase = _configure_corpus(monkeypatch, tmp_path)
    direct = showcase / "thermostat"
    nested = showcase / "furuta-pendulum" / "deterministic"
    direct.mkdir(parents=True)
    nested.mkdir(parents=True)
    (direct / "thermostat.sysml").touch()
    (nested / "furuta.sysml").touch()

    assert run_all_quake._model_dirs(None) == [nested, direct]
    assert run_all_quake._model_name(nested) == (
        "showcase/furuta-pendulum/deterministic"
    )


def test_model_dirs_accepts_nested_aliases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    showcase = _configure_corpus(monkeypatch, tmp_path)
    nested = showcase / "furuta-pendulum" / "deterministic"
    nested.mkdir(parents=True)
    (nested / "furuta.sysml").touch()

    assert run_all_quake._model_dirs(["furuta-pendulum/deterministic"]) == [
        nested
    ]
    assert run_all_quake._model_dirs(
        ["showcase/furuta-pendulum/deterministic"]
    ) == [nested]


def test_python_arguments_selects_shared_support(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    showcase = _configure_corpus(monkeypatch, tmp_path)
    nested = showcase / "furuta-pendulum" / "deterministic"
    reference = showcase / "furuta-pendulum" / "nondeterministic"
    nested.mkdir(parents=True)
    reference.mkdir()
    support = nested.parent / "furuta_physics.py"
    support.touch()
    monkeypatch.setattr(
        run_all_quake,
        "SHARED_PYTHON_SUPPORT",
        {"showcase/furuta-pendulum/deterministic": support},
    )

    assert run_all_quake._python_arguments(nested) == [
        "--python",
        str(support),
    ]
    assert run_all_quake._python_arguments(reference) == []


def test_expected_failure_targets_are_discoverable() -> None:
    # Runs against the real bundled corpora on purpose: an entry whose
    # model directory was renamed or moved would otherwise never be
    # consulted by the sweep and rot silently.
    labels = {
        run_all_quake._model_name(directory)
        for directory in run_all_quake._model_dirs(None)
    }
    for target in run_all_quake.EXPECTED_FAILURES:
        model_label = target.split("::", maxsplit=1)[0]
        assert model_label in labels, (
            f"EXPECTED_FAILURES names {target!r}, but no swept model "
            f"directory is labelled {model_label!r}"
        )
