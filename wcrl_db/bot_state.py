"""Small internal key/value persistence — the `bot_state` table.

Purpose: the only place that writes SQL against `bot_state`.
Current state: fully implemented.
TODO: none open.
Notes: generic get/set over text keys and values; it has no idea the only
key in use today is `last_announced_changelog` (see `bot.py`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .connection import Database


class BotStateRepository:
    """Queries and writes against `bot_state`."""

    def __init__(self, db: "Database") -> None:
        self._db = db

    async def get(self, key: str) -> str | None:
        row = await self._db.fetch_one("SELECT value FROM bot_state WHERE key = ?", (key,))
        return row["value"] if row is not None else None

    async def set(self, key: str, value: str) -> None:
        await self._db.execute(
            """
            INSERT INTO bot_state (key, value) VALUES (?, ?)
            ON CONFLICT (key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
