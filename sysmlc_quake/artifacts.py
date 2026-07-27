from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from types import ModuleType
from typing import TYPE_CHECKING

from sysmlc.errors import UnsupportedConstructError

if TYPE_CHECKING:
    from pathlib import Path

    from sismic.model import Statechart

_SOURCE_KEY = "__sysmlc_generated_source__"


def types_module_name(qualified_name: str) -> str:
    """Return a Python-safe generated-types module name for a SysML name."""
    stem = re.sub(r"\W+", "_", qualified_name).strip("_")
    if not stem:
        raise ValueError("qualified name has no identifier characters")
    if stem[0].isdigit():
        stem = f"_{stem}"
    return f"{stem}_types"


@dataclass(frozen=True)
class GeneratedPythonModule:
    """A generated Python support module owned by a quake artifact."""

    name: str
    lines: tuple[str, ...]

    @property
    def source(self) -> str:
        """Return the complete newline-terminated module source."""
        return "\n".join(self.lines) + "\n"

    def install(self) -> ModuleType:
        """Install the module in ``sys.modules`` for in-process execution.

        Reinstalling identical generated source is idempotent. Reusing the
        same module name for different source fails rather than silently
        replacing classes that an existing statechart may still reference.

        Returns:
            The installed module.

        Raises:
            UnsupportedConstructError: If the module name is already occupied
                by different source.
        """
        existing = sys.modules.get(self.name)
        if existing is not None:
            if existing.__dict__.get(_SOURCE_KEY) == self.source:
                return existing
            raise UnsupportedConstructError(
                f"generated types module {self.name!r} is already installed "
                "with different content"
            )

        code = compile(self.source, f"<generated {self.name}>", "exec")
        module = ModuleType(self.name)
        module.__dict__[_SOURCE_KEY] = self.source
        sys.modules[self.name] = module
        try:
            exec(code, module.__dict__)
        except Exception:
            if sys.modules.get(self.name) is module:
                del sys.modules[self.name]
            raise
        return module

    def write(self, directory: Path) -> Path:
        """Write the module into ``directory`` and return its path."""
        path = directory / f"{self.name}.py"
        path.write_text(self.source)
        return path


@dataclass(frozen=True)
class QuakeStatechartArtifact:
    """A statechart and its optional generated Python types module."""

    statechart: Statechart
    types_module: GeneratedPythonModule | None = None
