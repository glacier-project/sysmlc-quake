from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sismic.model import Statechart
    from sysmlc.codegen.structured import GeneratedPythonModule
    from sysmlc.semantics.statemachine.signals import SignalCatalog


@dataclass(frozen=True)
class QuakeInvariant:
    """Source identity of one generated Sismic invariant.

    Attributes:
        state: Generated Sismic state owning the invariant.
        scope: Neutral SysML state path, empty for the behavior root.
        name: Declared constraint name, or ``None`` for an anonymous check.
        check_id: Constraint ordinal within the compiled behavior.
        condition: Exact annotated Python expression returned on failure.
    """

    state: str
    scope: str
    name: str | None
    check_id: int
    condition: str


@dataclass(frozen=True)
class QuakeStatechartArtifact:
    """A statechart and its optional generated Python types module."""

    statechart: Statechart
    types_module: GeneratedPythonModule | None = None
    invariants: tuple[QuakeInvariant, ...] = ()
    qualified_channels: Mapping[str, str] = field(default_factory=dict)
    external_names: Mapping[str, str] = field(default_factory=dict)

    def resolve_external(self, name: str) -> str:
        """Resolve an input type name, rejecting unknown or ambiguous names.

        Raises:
            ValueError: If the name is unknown or ambiguous.
        """
        return resolve_external_channel(
            name, self.qualified_channels, self.external_names
        )


def external_channel_names(catalog: SignalCatalog) -> dict[str, str]:
    """Freeze unambiguous simple aliases from resolved signal definitions."""
    names = {
        channel: catalog.definition_for(channel).name
        for channel in catalog.qualified_channels.values()
    }
    counts = Counter(names.values())
    return {
        name: channel
        for channel, name in names.items()
        if name is not None and counts[name] == 1
    }


def resolve_external_channel(
    name: str,
    qualified_channels: Mapping[str, str],
    external_names: Mapping[str, str],
) -> str:
    """Resolve a frozen external signal identity without a loaded model.

    Raises:
        ValueError: If the input name is unknown or ambiguous.
    """
    channel = qualified_channels.get(name, external_names.get(name))
    if channel is None:
        raise ValueError(
            f"external signal name {name!r} is unknown or ambiguous; "
            "use a qualified type name"
        )
    return channel
