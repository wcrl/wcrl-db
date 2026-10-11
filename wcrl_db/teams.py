"""Team and team-membership persistence — the `teams`/`team_members` tables. See API.md."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._util import parse_timestamps

if TYPE_CHECKING:
    from .connection import Database


# get_by_name/create apply this internally so every caller gets
# case/whitespace-insensitive matching for free.
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

    async def get_by_id(self, team_id: int) -> dict[str, Any] | None:
        row = await self._db.fetch_one("SELECT * FROM teams WHERE team_id = ?", (team_id,))
        return parse_timestamps(row, "created_at") if row else None

    async def get_for_member(self, discord_id: int) -> dict[str, Any] | None:
        """The team a competitor belongs to, or None if they aren't on one."""
        row = await self._db.fetch_one(
            """
            SELECT teams.* FROM teams
            JOIN team_members ON team_members.team_id = teams.team_id
            WHERE team_members.discord_id = ?
            """,
            (discord_id,),
        )
        return parse_timestamps(row, "created_at") if row else None

    async def get_by_name(self, name: str) -> dict[str, Any] | None:
        """Look up a team by display name (case/whitespace-insensitive)."""
        row = await self._db.fetch_one(
            "SELECT * FROM teams WHERE name_normalized = ?", (normalize_team_name(name),)
        )
        return parse_timestamps(row, "created_at") if row else None

    async def get_by_channel(self, channel_id: int) -> dict[str, Any] | None:
        row = await self._db.fetch_one(
            "SELECT * FROM teams WHERE channel_id = ?", (channel_id,)
        )
        return parse_timestamps(row, "created_at") if row else None

    async def create(
        self, name: str, role_id: int, channel_id: int, created_by: int
    ) -> dict[str, Any]:
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

    async def list_members(self, team_id: int) -> list[dict[str, Any]]:
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

    async def list_with_member_counts(self, order: str = "name") -> list[dict[str, Any]]:
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

    async def search_by_name(self, fragment: str, limit: int = 25) -> list[dict[str, Any]]:
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
