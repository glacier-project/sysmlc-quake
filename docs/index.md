# sysmlc-quake

`sysmlc-quake` is the **quake** backend for
[sysmlc](https://github.com/glacier-project/sysmlc-core): it compiles SysML v2
state machines into executable [sismic](https://sismic.readthedocs.io/)
statecharts and serializes them to YAML and PlantUML.

The backend registers through the `sysmlc.backends` entry-point group, so
installing this package beside the core makes `sysmlc quake build` available.

```{toctree}
:maxdepth: 2
:caption: Contents

quake-mapping
api
```

## Development

Install the documentation dependencies and run the live documentation server:

```bash
uv sync --extra dev --extra docs
uv run sphinx-autobuild docs docs/_build/html
```

Build the static site with:

```bash
uv run tox -e docs
```

## Construct mapping

`quake-mapping` is the canonical, construct-by-construct record of how each
SysML v2 state-machine construct becomes sismic, including the boundaries of
what the backend supports.
