from __future__ import annotations

import json
from dataclasses import asdict
from typing import TYPE_CHECKING, ClassVar, override

from sismic.model import Statechart
from sysmlc.backends.base import Backend, OutputOptions
from sysmlc.errors import SerializationError, UnsupportedConstructError

from sysmlc_quake import runner
from sysmlc_quake.artifacts import QuakeStatechartArtifact
from sysmlc_quake.builder import build_statechart_artifact
from sysmlc_quake.parts import QuakePartSystem, build_part_system
from sysmlc_quake.serialize import to_plantuml, to_yaml

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import syside
    from sysmlc.sysml.foreign_artifact.base import ForeignArtifact


class QuakeBackend(Backend):
    """Sismic-statechart backend for SysML state definitions."""

    _EXTENSIONS: ClassVar[dict[str, str]] = {"yaml": "yaml", "plantuml": "puml"}

    def __init__(self) -> None:
        super().__init__(
            name="quake",
            description=(
                "Generate Sismic statecharts from SysML state definitions."
            ),
            formats=(
                ("yaml", "YAML-serialized Sismic statechart"),
                ("plantuml", "PlantUML statechart diagram"),
            ),
            foreign_artifact_languages=("python",),
        )

    @override
    def build(
        self,
        model: syside.Model,
        element_qn: str,
        external: list[ForeignArtifact] | None = None,
        strict_extern: bool = False,
    ) -> QuakeStatechartArtifact:
        """Build the Sismic statechart for the given state definition."""
        return build_statechart_artifact(model, element_qn, external=external)

    @override
    def consumes_python_support(self) -> bool:
        """Quake emits Python statechart guards backed by ``--python``."""
        return True

    @override
    def defers_python_support_loading(self) -> bool:
        """Load support only after generated companion modules are installed."""
        return True

    @override
    def build_part(
        self,
        model: syside.Model,
        usage_qn: str,
        *,
        target_options: tuple[tuple[str, str], ...] = (),
        external: list[ForeignArtifact] | None = None,
        strict_extern: bool = False,
    ) -> QuakePartSystem:
        """Build a connected part system for coordinated execution."""
        if target_options:
            raise UnsupportedConstructError(
                "quake part systems do not support LF target options"
            )
        return build_part_system(model, usage_qn, external=external)

    @override
    def run_state_def(
        self,
        model: syside.Model,
        element_qn: str,
        *,
        max_steps: int = 1000,
        until: float | None = None,
        external: list[ForeignArtifact] | None = None,
        load_external: Callable[[], None] | None = None,
    ) -> runner.RunReport:
        """Execute a state definition to quiescence."""
        return runner.run_state_def(
            model,
            element_qn,
            max_steps=max_steps,
            until=until,
            external=external,
            load_external=load_external,
        )

    @override
    def run_part_system(
        self,
        model: syside.Model,
        element_qn: str,
        *,
        max_steps: int = 1000,
        until: float | None = None,
        external: list[ForeignArtifact] | None = None,
        load_external: Callable[[], None] | None = None,
    ) -> runner.RunReport:
        """Execute a connected part system to quiescence."""
        return runner.run_part_system(
            model,
            element_qn,
            max_steps=max_steps,
            until=until,
            external=external,
            load_external=load_external,
        )

    @override
    def serialize(self, artifact: object, fmt: str) -> str:
        """Serialize the Sismic statechart to the requested format."""
        statechart = _as_statechart(artifact)
        if statechart is None:
            raise SerializationError("expected a sismic Statechart artifact")
        if fmt == "yaml":
            return to_yaml(statechart)
        if fmt == "plantuml":
            return to_plantuml(statechart)
        raise SerializationError(f"unsupported format: {fmt!r}")

    @override
    def write(self, artifact: object, options: OutputOptions) -> list[Path]:
        """Write a quake artifact to disk.

        Single statecharts are written as one flat file per requested format.
        Part systems are written as ``<basename>/routing.json`` plus one
        statechart file per part instance and requested format.
        """
        if isinstance(artifact, QuakePartSystem):
            return self._write_part_system(artifact, options)
        statechart = _as_statechart(artifact)
        if statechart is None:
            raise SerializationError(
                "expected a quake statechart or part-system artifact"
            )
        formats = options.formats or tuple(self.formats())
        basename = options.basename or statechart.name
        options.output_dir.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for fmt in formats:
            text = self.serialize(artifact, fmt)
            path = options.output_dir / f"{basename}.{self._EXTENSIONS[fmt]}"
            path.write_text(text)
            written.append(path)
        if (
            isinstance(artifact, QuakeStatechartArtifact)
            and artifact.types_module is not None
        ):
            written.append(artifact.types_module.write(options.output_dir))
        return written

    def _write_part_system(
        self, artifact: QuakePartSystem, options: OutputOptions
    ) -> list[Path]:
        """Write one statechart file per instance plus a routing manifest."""
        formats = options.formats or tuple(self.formats())
        basename = options.basename or artifact.name
        system_dir = options.output_dir / basename
        system_dir.mkdir(parents=True, exist_ok=True)
        manifest = system_dir / "routing.json"
        manifest.write_text(
            json.dumps(_part_system_manifest(artifact), indent=2) + "\n"
        )
        written = [manifest]
        if artifact.types_module is not None:
            written.append(artifact.types_module.write(system_dir))
        for node in artifact.graph.parts:
            statechart = artifact.statecharts[node.usage_name]
            for fmt in formats:
                path = system_dir / f"{node.usage_name}.{self._EXTENSIONS[fmt]}"
                path.write_text(self.serialize(statechart, fmt))
                written.append(path)
        return written

    @override
    def summary(self, artifact: object) -> str:
        """Return a one-line description of the built statechart."""
        if isinstance(artifact, QuakePartSystem):
            return (
                f"part system {artifact.name!r}: "
                f"{len(artifact.graph.parts)} parts, "
                f"{len(artifact.routes)} routes"
            )
        statechart = _as_statechart(artifact)
        if statechart is None:
            return self.name
        states = len(statechart.states)
        transitions = len(statechart.transitions)
        return (
            f"statechart {statechart.name!r}: "
            f"{states} states, {transitions} transitions"
        )


def _part_system_manifest(artifact: QuakePartSystem) -> dict[str, object]:
    """Return the JSON-serializable routing manifest."""
    return {
        "name": artifact.name,
        "instances": [
            {
                "name": node.usage_name,
                "definition": node.definition_name,
                "behavior": node.behaviors[0][1],
            }
            for node in artifact.graph.parts
        ],
        "routes": [asdict(route) for route in artifact.routes],
    }


def _as_statechart(artifact: object) -> Statechart | None:
    """Return the statechart carried by a supported single-machine artifact."""
    if isinstance(artifact, QuakeStatechartArtifact):
        return artifact.statechart
    if isinstance(artifact, Statechart):
        return artifact
    return None
