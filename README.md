# sysmlc-quake

The **quake** backend for [sysmlc](https://github.com/glacier-project/sysmlc-core):
it compiles SysML v2 state machines into executable
[sismic](https://github.com/AlexandreDecan/sismic) statecharts, and serializes
them to YAML and PlantUML.

`docs/quake-mapping.md` is the canonical, construct-by-construct record of the
SysML-to-sismic mapping and of the boundaries of what this backend supports.

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

Installing this package beside the core registers the backend through the
`sysmlc.backends` entry-point group, which makes it available on the shared
CLI. Model arguments accept either a path to a model directory or the name of
a bundled corpus model:

```bash
uv run sysmlc quake build sm-examples/sm01-helloworld -o out/
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

## Development

```bash
uv run tox                       # tests, type checking, formatting, coverage, docs
uv run pytest tests              # tests only
uv run pyrefly check             # type checking
uv run tox run -e formatter      # ruff check --fix and ruff format
uv run tox run -e docs           # sphinx -W
uv run pre-commit install        # once after cloning
```
