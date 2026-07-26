# API Reference

The quake backend: the sismic statechart builder, the Python expression
emitter, serialization, part systems, and execution. The shared front-end and
plugin contract are documented in the core package.

<!-- The autodoc directives below are wrapped in `{eval-rst}` fences on
purpose: a bare `{automodule}` MyST fence renders autodoc's generated
reStructuredText as literal text, so the RST escape hatch is required for the
API reference to render. -->

## Backend entry point

```{eval-rst}
.. automodule:: sysmlc_quake.backend
```

## Statechart construction

```{eval-rst}
.. automodule:: sysmlc_quake.builder
.. automodule:: sysmlc_quake.codegen
```

## Serialization

```{eval-rst}
.. automodule:: sysmlc_quake.serialize
```

## Part systems and execution

```{eval-rst}
.. automodule:: sysmlc_quake.parts
.. automodule:: sysmlc_quake.coordinator
.. automodule:: sysmlc_quake.runner
```
