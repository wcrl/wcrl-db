"""Internal helpers shared by the repository modules; not part of the public API."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def parse_timestamps(row: dict[str, Any], *keys: str) -> dict[str, Any]:
    """Replace each named key in `row` with a parsed `datetime`, in place."""
    # schema.sql writes UTC text via strftime('%Y-%m-%dT%H:%M:%SZ', 'now');
    # Python 3.11+'s fromisoformat parses that trailing Z directly.
    for key in keys:
        value = row.get(key)
        if isinstance(value, str):
            row[key] = datetime.fromisoformat(value)
    return row
