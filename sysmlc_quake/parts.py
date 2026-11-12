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
from sysmlc.semantics.parts.graph import PartGraph, PartNode, part_graph
from sysmlc.semantics.parts.routing import PortSignalRoute, validated_routes
from sysmlc.semantics.statemachine.interface import machine_interface
from sysmlc.semantics.statemachine.signals import SignalCatalog

from sysmlc_quake.artifacts import (
    external_channel_names,
    resolve_external_channel,
)
from sysmlc_quake.builder import build_statechart_with_needs
from sysmlc_quake.codegen import QuakeRenderNeeds, types_module_for

if TYPE_CHECKING:
    from collections.abc import Mapping

    import syside
    from sismic.model import Statechart
    from sysmlc.sysml.foreign_artifact.base import ForeignArtifact


@dataclass(frozen=True)
class PartInstance:
    """One executable machine of a part system.

    A single-exhibit part is one instance named after its usage; each
    exhibit of a multi-exhibit part is one instance named
    ``<usage>.<exhibit>``.
    """

    name: str
    definition: str
    behavior: str


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
    instances: tuple[PartInstance, ...] = ()
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

    singles = tuple(node for node in graph.parts if len(node.behaviors) == 1)
    multis = tuple(node for node in graph.parts if len(node.behaviors) > 1)
    instances: list[PartInstance] = []
    for node in graph.parts:
        if len(node.behaviors) == 1:
            instances.append(
                PartInstance(
                    node.usage_name, node.definition_name, node.behaviors[0][1]
                )
            )
        else:
            instances.extend(
                PartInstance(
                    f"{node.usage_name}.{exhibit}",
                    node.definition_name,
                    behavior,
                )
                for exhibit, behavior in node.behaviors
            )

    catalog = SignalCatalog(
        model, [instance.behavior for instance in instances]
    )
    _, single_routes = validated_routes(model, graph, singles, catalog=catalog)
    routes = single_routes + tuple(
        edge
        for node in multis
        for edge in _exhibit_routes(model, node, catalog)
    )

    module_name = types_module_name(usage_qn)
    shared_types = DataclassRegistry(catalog.definition_symbols)
    built_behaviors: dict[str, Statechart] = {}
    statecharts: dict[str, Statechart] = {}
    for instance in instances:
        behavior_qn = instance.behavior
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
        statecharts[instance.name] = built_behaviors[behavior_qn]

    return QuakePartSystem(
        name=graph.name,
        graph=graph,
        statecharts=statecharts,
        routes=routes,
        instances=tuple(instances),
        qualified_channels=dict(catalog.qualified_channels),
        external_names=external_channel_names(catalog),
        types_module=types_module_for(module_name, shared_types),
    )


def _exhibit_routes(
    model: syside.Model, node: PartNode, catalog: SignalCatalog
) -> tuple[PortSignalRoute, ...]:
    """Wire the exhibits of one multi-exhibit part to each other by signal.

    The exhibits of a part share it (a testbench rig), so a signal one
    exhibit sends reaches every other exhibit that accepts it, over the
    port the accepter names. Declared ports and interfaces are not needed.

    Raises:
        UnsupportedConstructError: If the part exhibits one state def
            twice, a signal flows both ways between two exhibits, or one
            ``(target, signal)`` input has two sources.
    """
    behaviors = [behavior for _, behavior in node.behaviors]
    if len(set(behaviors)) != len(behaviors):
        raise UnsupportedConstructError(
            f"part def {node.definition_name!r} exhibits the same state def "
            "twice; a multi-exhibit part combines distinct machines"
        )
    faces = {
        exhibit: machine_interface(model, behavior, catalog=catalog)
        for exhibit, behavior in node.behaviors
    }
    routes: list[PortSignalRoute] = []
    sources: dict[tuple[str, str], str] = {}
    for source, source_face in faces.items():
        for target, target_face in faces.items():
            if source == target:
                continue
            for signal in sorted(source_face.sent & target_face.accepted):
                if (
                    signal in faces[target].sent
                    and signal in faces[source].accepted
                ):
                    raise UnsupportedConstructError(
                        f"signal {signal!r} is sent by both {source!r} and "
                        f"{target!r}; bidirectional same-name signals are "
                        "not supported"
                    )
                key = (target, signal)
                if key in sources:
                    raise UnsupportedConstructError(
                        f"signal {signal!r} has two sources "
                        f"({sources[key]!r} and {source!r}) into {target!r}"
                    )
                sources[key] = source
                for source_port in _ports_carrying(
                    source_face.sent_via, signal
                ):
                    for target_port in _ports_carrying(
                        target_face.accepted_via, signal
                    ):
                        routes.append(
                            PortSignalRoute(
                                f"{node.usage_name}.{source}",
                                source_port,
                                signal,
                                f"{node.usage_name}.{target}",
                                target_port,
                            )
                        )
    return tuple(routes)


def _ports_carrying(
    by_port: Mapping[str | None, frozenset[str]], signal: str
) -> list[str]:
    """Return the ports a signal travels over; a portless use has none."""
    return sorted(
        port
        for port, signals in by_port.items()
        if port is not None and signal in signals
    )
