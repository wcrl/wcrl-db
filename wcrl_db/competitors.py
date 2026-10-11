"""Competitor and profile persistence — the `competitors`/`competitor_profiles` tables. See API.md."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._util import parse_timestamps

if TYPE_CHECKING:
    from .connection import Database


class CompetitorRepository:
    """Queries and writes against `competitors` and `competitor_profiles`."""

    def __init__(self, db: "Database") -> None:
        self._db = db

    async def get(self, discord_id: int) -> dict[str, Any] | None:
        row = await self._db.fetch_one(
            "SELECT * FROM competitors WHERE discord_id = ?", (discord_id,)
        )
        return parse_timestamps(row, "registered_at", "created_at") if row else None

    async def get_by_email(self, email: str) -> dict[str, Any] | None:
        row = await self._db.fetch_one(
            "SELECT * FROM competitors WHERE school_email = ?", (email,)
        )
        return parse_timestamps(row, "registered_at", "created_at") if row else None

    async def exists(self, discord_id: int) -> bool:
        row = await self._db.fetch_one(
            "SELECT 1 FROM competitors WHERE discord_id = ?", (discord_id,)
        )
        return row is not None

    # Only runs the write and re-reads the row — conflict/validation decisions
    # (new account? email already claimed by someone else?) are the caller's
    # job, expressed with get/get_by_email/exists before this runs.
    async def upsert(self, discord_id: int, full_name: str, school_email: str) -> dict[str, Any]:
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

    async def get_profile(self, discord_id: int) -> dict[str, Any] | None:
        row = await self._db.fetch_one(
            "SELECT * FROM competitor_profiles WHERE discord_id = ?", (discord_id,)
        )
        return parse_timestamps(row, "updated_at") if row else None

    async def upsert_profile(self, discord_id: int, year: str, major: str) -> dict[str, Any]:
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
