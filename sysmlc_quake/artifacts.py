from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sismic.model import Statechart
    from sysmlc.codegen.structured import GeneratedPythonModule


@dataclass(frozen=True)
class QuakeStatechartArtifact:
    """A statechart and its optional generated Python types module."""

    statechart: Statechart
    types_module: GeneratedPythonModule | None = None
