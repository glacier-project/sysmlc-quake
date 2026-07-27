from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sysmlc.codegen.structured import GeneratedPythonModule, types_module_name

if TYPE_CHECKING:
    from sismic.model import Statechart

__all__ = [
    "GeneratedPythonModule",
    "QuakeStatechartArtifact",
    "types_module_name",
]


@dataclass(frozen=True)
class QuakeStatechartArtifact:
    """A statechart and its optional generated Python types module."""

    statechart: Statechart
    types_module: GeneratedPythonModule | None = None
