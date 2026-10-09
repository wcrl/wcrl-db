"""Competitor and profile persistence — the `competitors`/`competitor_profiles` tables.

Purpose: the only place that writes SQL against these two tables; every
consumer of this library calls these methods instead of embedding queries.
Current state: fully implemented.
TODO: none open.
Notes: `upsert`/`upsert_profile` only run the write and re-read the row —
conflict/validation decisions (is this a new account? is the email already
claimed by someone else?) are app-level judgment calls, not persistence
concerns, so they stay in the consuming app (the WCRL Discord bot's
`cogs/registration.py`) and are expressed using `get`/`get_by_email`/
`exists` before the upsert runs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import aiosqlite

if TYPE_CHECKING:
    from .connection import Database


class CompetitorRepository:
    """Queries and writes against `competitors` and `competitor_profiles`."""

    def __init__(self, db: "Database") -> None:
        self._db = db

    async def get(self, discord_id: int) -> aiosqlite.Row | None:
        return await self._db.fetch_one(
            "SELECT * FROM competitors WHERE discord_id = ?", (discord_id,)
        )

    async def get_by_email(self, email: str) -> aiosqlite.Row | None:
        return await self._db.fetch_one(
            "SELECT * FROM competitors WHERE school_email = ?", (email,)
        )

    async def exists(self, discord_id: int) -> bool:
        row = await self._db.fetch_one(
            "SELECT 1 FROM competitors WHERE discord_id = ?", (discord_id,)
        )
        return row is not None

    async def upsert(self, discord_id: int, full_name: str, school_email: str) -> aiosqlite.Row:
        """Insert or refresh a competitor's row; returns the resulting row."""
        await self._db.execute(
            """
            INSERT INTO competitors (discord_id, full_name, school_email)
            VALUES (?, ?, ?)
            ON CONFLICT (discord_id) DO UPDATE
                SET full_name = excluded.full_name, school_email = excluded.school_email
            """,
            (discord_id, full_name, school_email),
        )
        return await self.get(discord_id)

    async def count(self) -> int:
        row = await self._db.fetch_one("SELECT COUNT(*) AS n FROM competitors")
        return row["n"]

    async def get_profile(self, discord_id: int) -> aiosqlite.Row | None:
        return await self._db.fetch_one(
            "SELECT * FROM competitor_profiles WHERE discord_id = ?", (discord_id,)
        )

    async def upsert_profile(self, discord_id: int, year: str, major: str) -> aiosqlite.Row:
        """Insert or refresh a competitor's year/major; returns the resulting row."""
        await self._db.execute(
            """
            INSERT INTO competitor_profiles (discord_id, year, major, updated_at)
            VALUES (?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            ON CONFLICT (discord_id) DO UPDATE
                SET year = excluded.year, major = excluded.major, updated_at = excluded.updated_at
            """,
            (discord_id, year, major),
        )
        return await self.get_profile(discord_id)

    async def count_with_profile(self) -> int:
        row = await self._db.fetch_one("SELECT COUNT(*) AS n FROM competitor_profiles")
        return row["n"]

    async def count_by_year(self) -> list[tuple[str, int]]:
        rows = await self._db.fetch_all(
            "SELECT year, COUNT(*) AS n FROM competitor_profiles GROUP BY year ORDER BY n DESC, year"
        )
        return [(row["year"], row["n"]) for row in rows]

    async def count_by_major(self) -> list[tuple[str, int]]:
        rows = await self._db.fetch_all(
            "SELECT major, COUNT(*) AS n FROM competitor_profiles GROUP BY major ORDER BY n DESC, major"
        )
        return [(row["major"], row["n"]) for row in rows]
