"""Team and team-membership persistence — the `teams`/`team_members` tables.

Purpose: the only place that writes SQL against these two tables; every
consumer of this library calls these methods instead of embedding queries.
Current state: fully implemented.
TODO: none open.
Notes: `normalize_team_name` lives here (not in a consuming app) because it
defines what `name_normalized` means — `get_by_name`/`create` apply it
internally so every caller gets case/whitespace-insensitive matching for
free instead of having to remember to normalize first. The WCRL Discord
bot re-exports it (`from wcrl_db.teams import normalize_team_name`) since
display-name validation and channel-name slugifying are UI concerns that
belong in that app, not here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import aiosqlite

if TYPE_CHECKING:
    from .connection import Database


def normalize_team_name(name: str) -> str:
    """Case/whitespace-insensitive key stored in `teams.name_normalized`."""
    return " ".join(name.split()).casefold()


def _escape_like(text: str) -> str:
    """Escape LIKE wildcards so typed `%`/`_` match literally."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class TeamRepository:
    """Queries and writes against `teams` and `team_members`."""

    def __init__(self, db: "Database") -> None:
        self._db = db

    async def get_by_id(self, team_id: int) -> aiosqlite.Row | None:
        return await self._db.fetch_one("SELECT * FROM teams WHERE team_id = ?", (team_id,))

    async def get_for_member(self, discord_id: int) -> aiosqlite.Row | None:
        """The team a competitor belongs to, or None if they aren't on one."""
        return await self._db.fetch_one(
            """
            SELECT teams.* FROM teams
            JOIN team_members ON team_members.team_id = teams.team_id
            WHERE team_members.discord_id = ?
            """,
            (discord_id,),
        )

    async def get_by_name(self, name: str) -> aiosqlite.Row | None:
        """Look up a team by display name (case/whitespace-insensitive)."""
        return await self._db.fetch_one(
            "SELECT * FROM teams WHERE name_normalized = ?", (normalize_team_name(name),)
        )

    async def get_by_channel(self, channel_id: int) -> aiosqlite.Row | None:
        return await self._db.fetch_one(
            "SELECT * FROM teams WHERE channel_id = ?", (channel_id,)
        )

    async def create(
        self, name: str, role_id: int, channel_id: int, created_by: int
    ) -> aiosqlite.Row:
        """Insert a new team; returns the resulting row."""
        cursor = await self._db.execute(
            """
            INSERT INTO teams (name, name_normalized, role_id, channel_id, created_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, normalize_team_name(name), role_id, channel_id, created_by),
        )
        return await self.get_by_id(cursor.lastrowid)

    async def delete(self, team_id: int) -> None:
        await self._db.execute("DELETE FROM teams WHERE team_id = ?", (team_id,))

    async def add_member(self, team_id: int, discord_id: int) -> None:
        await self._db.execute(
            "INSERT INTO team_members (team_id, discord_id) VALUES (?, ?)",
            (team_id, discord_id),
        )

    async def remove_member(self, discord_id: int) -> None:
        await self._db.execute(
            "DELETE FROM team_members WHERE discord_id = ?", (discord_id,)
        )

    async def count_members(self, team_id: int) -> int:
        row = await self._db.fetch_one(
            "SELECT COUNT(*) AS n FROM team_members WHERE team_id = ?", (team_id,)
        )
        return row["n"]

    async def list_members(self, team_id: int) -> list[aiosqlite.Row]:
        """A team's roster, oldest member first."""
        return await self._db.fetch_all(
            """
            SELECT competitors.discord_id, competitors.full_name
            FROM team_members
            JOIN competitors ON competitors.discord_id = team_members.discord_id
            WHERE team_members.team_id = ?
            ORDER BY team_members.joined_at
            """,
            (team_id,),
        )

    async def list_with_member_counts(self, order: str = "name") -> list[aiosqlite.Row]:
        """Every team with its member count, ordered by `name` or `size` (largest first)."""
        order_clause = {
            "name": "teams.name COLLATE NOCASE",
            "size": "member_count DESC, teams.name COLLATE NOCASE",
        }[order]
        return await self._db.fetch_all(
            f"""
            SELECT teams.name, COUNT(team_members.discord_id) AS member_count
            FROM teams
            LEFT JOIN team_members ON team_members.team_id = teams.team_id
            GROUP BY teams.team_id
            ORDER BY {order_clause}
            """
        )

    async def search_by_name(self, fragment: str, limit: int = 25) -> list[aiosqlite.Row]:
        """Teams whose name contains `fragment`, for autocomplete."""
        return await self._db.fetch_all(
            """
            SELECT name FROM teams
            WHERE name LIKE ? ESCAPE '\\'
            ORDER BY name COLLATE NOCASE
            LIMIT ?
            """,
            (f"%{_escape_like(fragment)}%", limit),
        )

    async def count(self) -> int:
        row = await self._db.fetch_one("SELECT COUNT(*) AS n FROM teams")
        return row["n"]

    async def count_distinct_members(self) -> int:
        row = await self._db.fetch_one(
            "SELECT COUNT(DISTINCT discord_id) AS n FROM team_members"
        )
        return row["n"]
