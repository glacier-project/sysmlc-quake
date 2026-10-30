"""Construct external signal events for quake statecharts."""

from __future__ import annotations

from types import MappingProxyType, SimpleNamespace
from typing import TYPE_CHECKING

from sismic.model import Event

from sysmlc_quake.codegen import PAYLOAD_DATA_KEY

if TYPE_CHECKING:
    from collections.abc import Mapping


def payload_event(
    channel: str,
    fields: Mapping[str, object] = MappingProxyType({}),
    /,
) -> Event:
    """Return an external event carrying ``fields`` as its payload.

    The fields travel inside the payload envelope the generated sends use,
    so any field name works, including the ``name``, ``data`` and
    ``delay`` attributes Sismic's ``Event`` reserves or interprets. The
    event itself carries no delay or other Sismic metadata.

    Args:
        channel: The Sismic event name of the signal, as resolved by the
            artifact's ``resolve_external``.
        fields: The payload's field values keyed by field name. A nested
            structured value is any object exposing its fields as
            attributes.

    Returns:
        An event to pass to ``Interpreter.queue``.
    """
    return Event(channel, **{PAYLOAD_DATA_KEY: SimpleNamespace(**fields)})
