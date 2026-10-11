"""Internal helpers shared by the repository modules.

Purpose: small conversions used when turning a SQL row into plain Python
values returned to callers.
Current state: fully implemented.
TODO: none open.
Notes: leading underscore means this is not part of the public API —
repositories use it, consumers of the library never import it directly.
Timestamp columns are stored as UTC text written by
`strftime('%Y-%m-%dT%H:%M:%SZ', 'now')` (see `schema.sql`); Python 3.11+'s
`datetime.fromisoformat` parses that trailing `Z` directly into an aware
UTC `datetime`, so no manual string surgery is needed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def parse_timestamps(row: dict[str, Any], *keys: str) -> dict[str, Any]:
    """Replace each named key in `row` with a parsed `datetime`, in place."""
    for key in keys:
        value = row.get(key)
        if isinstance(value, str):
            row[key] = datetime.fromisoformat(value)
    return row
