"""aiosqlite connection management and repository wiring — the only path to the database."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

import aiosqlite

from .bot_state import BotStateRepository
from .competitors import CompetitorRepository
from .teams import TeamRepository

log = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


class Database:
    """Owns the app's aiosqlite connection and exposes domain repositories."""

    def __init__(self, path: str, *, readonly: bool = False) -> None:
        self.path = path
        self.readonly = readonly
        self._conn: aiosqlite.Connection | None = None

        self.competitors = CompetitorRepository(self)
        self.teams = TeamRepository(self)
        self.bot_state = BotStateRepository(self)

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database.connect() has not been awaited yet")
        return self._conn

    async def connect(self) -> None:
        """Open the connection. Writable mode also applies pragmas and replays the schema."""
        if self.readonly:
            # mode=ro for a second, read-only consumer of the same file (e.g. a
            # Flask API reading alongside the bot); never touches the schema or
            # WAL pragma, and any write attempted through it raises straight
            # from SQLite, not from anything in this class.
            resolved = Path(self.path).resolve()
            if not resolved.exists():
                raise FileNotFoundError(f"no database at {resolved}")
            self._conn = await aiosqlite.connect(f"file:{resolved}?mode=ro", uri=True)
            self._conn.row_factory = aiosqlite.Row
            log.info("database opened read-only at %s", self.path)
            return

        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)

        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row

        # A writable connection is meant for exactly one writer process at a
        # time. ON DELETE CASCADE (team disband) depends on foreign_keys here.
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.execute("PRAGMA journal_mode = WAL")
        await self._conn.commit()

        await self.apply_schema()
        log.info("database ready at %s", self.path)

    async def apply_schema(self) -> None:
        await self.conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        await self.conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # The one place aiosqlite.Row gets converted to a plain dict — repositories
    # layer datetime parsing for known timestamp columns on top of this.
    async def fetch_one(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        async with self.conn.execute(sql, tuple(params)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row is not None else None

    async def fetch_all(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        async with self.conn.execute(sql, tuple(params)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def execute(self, sql: str, params: Iterable[Any] = ()) -> aiosqlite.Cursor:
        cursor = await self.conn.execute(sql, tuple(params))
        await self.conn.commit()
        return cursor
