"""Leaderboard persistence(storing/retrieving data)"""

from __future__ import annotations
from typing import TYPE_CHECKING, Any
from ._util import parse_timestamps

if TYPE_CHECKING:
    from .connection import Database

class LeaderboardRepository:
    def __init__(self, db: "Database") -> None:
        self._db = db

    async def add_win(self, team_id: int) -> None:
        """Add one win to a team's leaderboard total."""
        await self._db.execute(
            '''
            INSERT INTO leaderboard (team_id, wins)
            VALUES (?, 1)
            ON CONFLICT(team_id)
            DO UPDATE SET wins = wins + 1
            ''',
            (team_id,),
        )

    async def get_all(self) -> list[dict[str, Any]]:
        """Return all teams ordered by wins, most wins first first."""
        return await self._db.fetch_all(
            """
            SELECT
                teams.team_id,
                teams.name,
                COALESCE(leaderboard.wins, 0) AS wins
            FROM teams
            LEFT JOIN leaderboard
                ON leaderboard.team_id = teams.team_id
            ORDER BY wins DESC, teams.name COLLATE NOCASE
            """
        )

    async def get(self, team_id: int) -> dict[str, Any] | None:
        """Get a team's leaderboard record."""
        return await self._db.fetch_one(
            """
            SELECT
                teams.team_id,
                teams.name,
                COALESCE(leaderboard.wins, 0) AS wins
            FROM teams
            LEFT JOIN leaderboard
                ON leaderboard.team_id = teams.team_id
            WHERE teams.team_id = ?
            """,
            (team_id,),
        )