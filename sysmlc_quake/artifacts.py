from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sismic.model import Statechart
    from sysmlc.codegen.structured import GeneratedPythonModule


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
