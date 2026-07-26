from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sismic.io import import_from_yaml
from sysmlc.cli import main
from sysmlc_models.sm_examples import SM_EXAMPLES_DIR

SM01_DIR = SM_EXAMPLES_DIR / "sm01-helloworld"
RIG_DIR = Path(__file__).resolve().parent / "fixtures" / "rig-pair"


def test_rig_on_backend_without_composition_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(
        [
            "quake",
            "build",
            str(RIG_DIR),
            "-e",
            "RigPair::PlantRig",
            "-o",
            str(tmp_path),
        ]
    )
    assert exit_code == 1
    assert "cannot build a rig composition" in capsys.readouterr().err


def test_quake_build_with_python_imports_without_copying(
    tmp_path: Path,
) -> None:
    model = SM_EXAMPLES_DIR / "sm15-external"
    py = tmp_path / "ext.py"
    py.write_text(
        "def step(x, dt):\n"
        "    return x + dt\n\n"
        "def unused():\n"
        "    return None\n"
    )
    out = tmp_path / "out"
    rc = main(
        [
            "quake",
            "build",
            str(model),
            "-e",
            "SM15::Ramp",
            "-o",
            str(out),
            "-f",
            "yaml",
            "--python",
            str(py),
        ]
    )

    assert rc == 0
    yaml_path = out / "Ramp.yaml"
    yaml = yaml_path.read_text()
    sc = import_from_yaml(filepath=str(yaml_path))
    assert sc.preamble.splitlines()[:3] == [
        "from math import cos as _cos, sin as _sin, tan as _tan",
        "from types import SimpleNamespace",
        "from ext import step",
    ]
    assert "x = step(x, 0.1)" in yaml
    assert not (out / "ext.py").exists()


def test_quake_build_with_reps_imports_generated_module(
    tmp_path: Path,
) -> None:
    # quake consumes the rep-generated module through the same pipeline
    # as --python; like --python, the module is not copied beside the
    # .yaml (the run command regenerates and imports it).
    out = tmp_path / "out"
    rc = main(
        [
            "quake",
            "build",
            str(SM_EXAMPLES_DIR / "sm15-rep"),
            "-e",
            "SM15Rep::Ramp",
            "-o",
            str(out),
            "-f",
            "yaml",
        ]
    )
    assert rc == 0
    yaml = (out / "Ramp.yaml").read_text()
    assert "from Ramp_impl import step" in yaml
    assert "x = step(x, 0.1)" in yaml
    assert not (out / "Ramp_impl.py").exists()


def test_quake_build_part_system_writes_artifact_directory(
    tmp_path: Path,
) -> None:
    out = tmp_path / "out"
    rc = main(
        [
            "quake",
            "build",
            str(SM_EXAMPLES_DIR / "part01-two-parts"),
            "-o",
            str(out),
            "-f",
            "yaml",
        ]
    )
    assert rc == 0
    assert (out / "pingSystem" / "routing.json").exists()
    assert (out / "pingSystem" / "plant.yaml").exists()
    assert (out / "pingSystem" / "tb.yaml").exists()


def test_quake_build_part_system_with_python_imports_without_copying(
    tmp_path: Path,
) -> None:
    # --python for a quake part build: the per-instance YAML imports the
    # external function, and the module is not copied.
    part_ext = SM_EXAMPLES_DIR / "part-external"
    py = tmp_path / "ext.py"
    py.write_text("def bump(v):\n    return v + 1.0\n")
    out = tmp_path / "out"
    rc = main(
        [
            "quake",
            "build",
            str(part_ext),
            "-o",
            str(out),
            "-f",
            "yaml",
            "--python",
            str(py),
        ]
    )

    assert rc == 0
    assert (out / "counterSystem" / "routing.json").exists()
    yaml = (out / "counterSystem" / "c.yaml").read_text()
    assert "from ext import bump" in yaml
    assert not (out / "ext.py").exists()


def test_quake_run_part_system(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(["quake", "run", str(SM_EXAMPLES_DIR / "part01-two-parts")])

    assert rc == 0
    assert "status=" in capsys.readouterr().out


def test_quake_run_respects_max_steps(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(
        [
            "quake",
            "run",
            str(SM_EXAMPLES_DIR / "part01-two-parts"),
            "--max-steps",
            "1",
        ]
    )

    assert rc == 1
    assert "status=hit step cap" in capsys.readouterr().out


INCOMPLETE_GUARD_MODEL = """\
package Incomplete {
    private import ScalarValues::*;
    state def Machine {
        attribute threshold : Integer;
        entry; then waiting;
        state waiting;
        transition waiting if threshold > 0 then done;
    }
}
"""


def test_quake_run_reports_code_evaluation_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "m.sysml").write_text(INCOMPLETE_GUARD_MODEL)

    rc = main(["quake", "run", str(model_dir)])

    assert rc == 1
    assert "not defined" in capsys.readouterr().err


NONTERMINATING_MODEL = """\
package Loop {
    private import SI::*;
    state def Machine {
        entry; then running;
        state running;
        transition running accept after 1 [s] then running;
    }
}
"""


def test_quake_run_until_bounds_a_nonterminating_model(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "m.sysml").write_text(NONTERMINATING_MODEL)

    rc = main(["quake", "run", str(model_dir), "--until", "3"])

    out = capsys.readouterr().out
    assert rc == 0
    assert "clock=3.0" in out
    assert "status=reached time bound" in out


@pytest.mark.usefixtures("fresh_external_modules")
def test_quake_run_state_def_with_python(
    capsys: pytest.CaptureFixture[str],
) -> None:
    model = SM_EXAMPLES_DIR / "sm15-external"
    rc = main(
        [
            "quake",
            "run",
            str(model),
            "--python",
            str(model / "ramp.py"),
            "--until",
            "0.25",
        ]
    )

    assert rc == 0
    assert "status=reached time bound" in capsys.readouterr().out


@pytest.mark.usefixtures("fresh_external_modules")
def test_quake_run_part_system_with_python(
    capsys: pytest.CaptureFixture[str],
) -> None:
    part_ext = SM_EXAMPLES_DIR / "part-external"
    rc = main(
        [
            "quake",
            "run",
            str(part_ext),
            "--python",
            str(part_ext / "bump.py"),
            "--until",
            "0.25",
        ]
    )

    assert rc == 0
    assert "status=reached time bound" in capsys.readouterr().out


NONDETERMINISTIC_MODEL = """\
package Nondet {
    private import ScalarValues::*;
    state def Machine {
        attribute x : Integer := 1;
        entry; then idle;
        state idle;
        state left;
        state right;
        transition first idle if x > 0 then left;
        transition first idle if x < 2 then right;
    }
}
"""


def test_quake_run_reports_nondeterminism_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "m.sysml").write_text(NONDETERMINISTIC_MODEL)

    rc = main(["quake", "run", str(model_dir)])

    assert rc == 1
    assert "on-determinis" in capsys.readouterr().err


def test_quake_run_with_missing_python_file_fails_cleanly(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(
        [
            "quake",
            "run",
            str(SM01_DIR),
            "-e",
            "SM01::Machine",
            "--python",
            "/nonexistent/typo.py",
        ]
    )

    assert rc == 1
    assert "typo.py" in capsys.readouterr().err


def test_quake_run_with_invalid_python_file_fails_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "bad.py"
    bad.write_text("def broken(:\n")

    rc = main(
        [
            "quake",
            "run",
            str(SM01_DIR),
            "-e",
            "SM01::Machine",
            "--python",
            str(bad),
        ]
    )

    assert rc == 1
    assert "bad.py" in capsys.readouterr().err


def test_quake_run_unregisters_failed_python_module(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    boom = tmp_path / "boom.py"
    boom.write_text("def f():\n    return 1\nraise RuntimeError('exploded')\n")

    rc = main(
        [
            "quake",
            "run",
            str(SM01_DIR),
            "-e",
            "SM01::Machine",
            "--python",
            str(boom),
        ]
    )

    assert rc == 1
    assert "exploded" in capsys.readouterr().err
    # The broken half-executed module must not stay importable.
    assert "boom" not in sys.modules
