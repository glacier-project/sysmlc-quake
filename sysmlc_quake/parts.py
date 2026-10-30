"""Build quake artifacts for connected SysML part systems."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sysmlc.codegen.structured import (
    DataclassRegistry,
    GeneratedPythonModule,
    types_module_name,
)
from sysmlc.errors import UnsupportedConstructError
from sysmlc.semantics.parts.graph import PartGraph, part_graph
from sysmlc.semantics.parts.routing import PortSignalRoute, validated_routes
from sysmlc.semantics.statemachine.signals import SignalCatalog

from sysmlc_quake.artifacts import (
    external_channel_names,
    resolve_external_channel,
)
from sysmlc_quake.builder import build_statechart_with_needs
from sysmlc_quake.codegen import QuakeRenderNeeds

if TYPE_CHECKING:
    from collections.abc import Mapping

    import syside
    from sismic.model import Statechart
    from sysmlc.sysml.foreign_artifact.base import ForeignArtifact


@dataclass(frozen=True)
class QuakePartSystem:
    """A compiled multi-machine quake artifact.

    Attributes:
        statecharts: The executable statechart of each part instance, keyed
            by usage name. Usages exhibiting the same behavior share one
            statechart object.
    """

    name: str
    graph: PartGraph
    statecharts: dict[str, Statechart]
    routes: tuple[PortSignalRoute, ...]
    types_module: GeneratedPythonModule | None = None
    qualified_channels: Mapping[str, str] = field(default_factory=dict)
    external_names: Mapping[str, str] = field(default_factory=dict)

    def resolve_external(self, name: str) -> str:
        """Resolve a qualified or unambiguous input type name.

        Raises:
            ValueError: If the name is unknown or ambiguous.
        """
        return resolve_external_channel(
            name, self.qualified_channels, self.external_names
        )


def build_part_system(
    model: syside.Model,
    usage_qn: str,
    *,
    external: list[ForeignArtifact] | None = None,
) -> QuakePartSystem:
    """Build a quake part-system artifact for a top-level part usage.

    Args:
        model: Loaded syside model containing the part usage.
        usage_qn: Qualified name of the top-level part usage to build.
        external: Optional ``list[ForeignArtifact]`` for
            external calc-def backing.

    Returns:
        A quake part-system artifact ready to feed into a coordinator.

    Raises:
        UnsupportedConstructError: If the usage composes no parts, two
            parts share a usage name, a part def does not exhibit exactly
            one state, or a connection fails routing validation.
    """
    graph = part_graph(model, usage_qn)

    # Keyed by usage name, so a repeated name would silently drop a machine.
    seen_usage_names: set[str] = set()
    for node in graph.parts:
        if node.usage_name in seen_usage_names:
            raise UnsupportedConstructError(
                f"part usage {usage_qn!r} composes two parts named "
                f"{node.usage_name!r}; quake part systems require uniquely "
                "named part usages"
            )
        seen_usage_names.add(node.usage_name)

    for node in graph.parts:
        if len(node.behaviors) != 1:
            raise UnsupportedConstructError(
                f"part def {node.definition_name!r} has "
                f"{len(node.behaviors)} exhibits; quake part systems require "
                "exactly one exhibit per part"
            )

    catalog = SignalCatalog(
        model, [node.behaviors[0][1] for node in graph.parts]
    )
    _, routes = validated_routes(model, graph, graph.parts, catalog=catalog)

    module_name = types_module_name(usage_qn)
    shared_types = DataclassRegistry(catalog.definition_symbols)
    built_behaviors: dict[str, Statechart] = {}
    statecharts: dict[str, Statechart] = {}
    for node in graph.parts:
        behavior_qn = node.behaviors[0][1]
        if behavior_qn not in built_behaviors:
            # Each machine gets fresh per-build needs; only the dataclass
            # registry and the companion name are shared across machines.
            needs = QuakeRenderNeeds(
                types_module=module_name,
                dataclasses=shared_types,
                external=external,
                catalog=catalog,
            )
            built_behaviors[behavior_qn] = build_statechart_with_needs(
                model,
                behavior_qn,
                needs=needs,
                part_system_mode=True,
            )
        statecharts[node.usage_name] = built_behaviors[behavior_qn]

    return QuakePartSystem(
        name=graph.name,
        graph=graph,
        statecharts=statecharts,
        routes=routes,
        qualified_channels=dict(catalog.qualified_channels),
        external_names=external_channel_names(catalog),
        types_module=GeneratedPythonModule.from_registry(
            module_name, shared_types
        ),
    )
