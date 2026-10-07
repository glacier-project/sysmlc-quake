# 🌋 sysmlc-quake

The **quake** backend for [sysmlc](https://github.com/glacier-project/sysmlc-core):
it compiles SysML v2 state machines into executable
[sismic](https://github.com/AlexandreDecan/sismic) statecharts, and serializes
them to YAML and PlantUML.

**Status:** in progress.

## Overview

Quake turns the paradigm-neutral facts produced by the core's state-machine
driver into a `sismic.model.Statechart`: states, transitions, guards,
attribute initializers and action bodies become the statechart's preamble,
`on_entry`/`on_exit` blocks and transition actions. The result is executable
by a sismic `Interpreter`.

For connected multi-machine systems it also supplies a coordinator that runs
one interpreter per part on a shared logical clock, routing signals between
ports.

[`docs/quake-mapping.md`](docs/quake-mapping.md) is the canonical,
construct-by-construct record of the SysML-to-sismic mapping and of the
boundaries of what this backend supports.

## Prerequisites

The core parses SysML v2 with
[Syside Automator](https://docs.sensmetry.com/automator/index.html), which
requires a license key. Create a `.env` file in the project root:

```
SYSIDE_LICENSE_KEY=your-key-here
```

## Installation

```bash
uv sync --extra dev
```

This installs the core (`sysmlc`) and the model corpora
([sysmlc-models](https://github.com/glacier-project/sysmlc-models)) that the
tests and examples use.

## Usage

Installed beside the core, the backend registers itself on the shared CLI.
Model arguments take either a path or a bundled corpus name:

```bash
uv run sysmlc quake build sm-examples/sm01-helloworld -o out/
```

Two output formats are available, and both are written unless `-f` selects
one:

| Format     | Contents                          |
| ---------- | --------------------------------- |
| `yaml`     | YAML-serialized sismic statechart |
| `plantuml` | PlantUML statechart diagram       |

Execute a model to quiescence without writing artifacts:

```bash
uv run sysmlc quake run sm-examples/sm01-helloworld -e SM01::Machine
```

Build and execute a statechart from one of the bundled state-machine examples
(accepts `01`, `sm01`, or the full folder name):

```bash
uv run python examples/run_quake.py sm01
```

Or use the API directly:

```python
from sysmlc.sysml.loading import load_model
from sysmlc_models.sm_examples import SM_EXAMPLES_DIR
from sysmlc_quake import build_statechart

model = load_model(SM_EXAMPLES_DIR / "sm01-helloworld")
statechart = build_statechart(model, "SM01::Machine")
```

`examples/run_all_quake.py` sweeps the bundled showcase and sm-examples
corpora through the CLI and reports a per-model verdict.

## Layout

```
sysmlc_quake/
├── backend.py       # QuakeBackend: the sysmlc plugin entry point
├── artifacts.py     # statecharts plus generated Python companion modules
├── builder.py       # SismicBuilder: neutral facts -> Statechart
├── codegen.py       # SismicCodeGen: expressions -> Python source
├── parts.py         # multi-machine part systems
├── coordinator.py   # shared-clock interpreter orchestration
├── runner.py        # execution to quiescence
└── serialize.py     # YAML and PlantUML output
```

## Development

Bundled model behavior is owned by [sysmlc-models](https://github.com/glacier-project/sysmlc-models). The scenario wrapper in this repository runs those shared contracts with this backend.

Local tests verify Sismic statechart structure and runtime integration, using small fixtures for target-specific behavior. Shared parsing and neutral semantic checks belong in [sysmlc-core](https://github.com/glacier-project/sysmlc-core).

```bash
uv run tox                       # tests, type checking, formatting, coverage, docs
uv run pytest tests              # tests only
uv run pyrefly check             # type checking
uv run tox run -e formatter      # ruff check --fix and ruff format
uv run tox run -e docs           # sphinx -W
uv run pre-commit install        # once after cloning
```
