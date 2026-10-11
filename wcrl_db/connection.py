"""aiosqlite connection management and repository wiring — the only path to the database.

Purpose: owns the connection lifecycle (writable or read-only) and exposes
the domain repositories (`competitors`, `teams`, `bot_state`) that hold all
of this library's SQL. Nothing outside `wcrl_db/` should write a SQL
statement — a consuming app always goes through `Database` and its
repositories, never its own queries.
Current state: fully implemented.
TODO: none open.
Notes: a writable connection (the default) is meant for exactly one writer
process at a time — today, the WCRL Discord bot. `foreign_keys` is
per-connection and off by default, and the `ON DELETE CASCADE` on team
disband depends on turning it on here. WAL's `-wal`/`-shm` sidecar files
must live on the same volume as the db file itself.

`readonly=True` opens the live file `mode=ro` instead, for a second,
read-only consumer of the same SQLite file (e.g. a Flask API reading
alongside the bot). It skips `apply_schema()` and the WAL pragma, since a
read-only connection must not create or lock anything; any write attempted
through it raises straight from SQLite (`sqlite3.OperationalError`), not
from anything in this class.

This is also how a sync caller with no persistent event loop (a plain
Flask view, say) is meant to use this async library: open a short-lived
`Database(path, readonly=True)` per request inside `asyncio.run(...)`,
rather than keeping one connection alive across requests — see the
project README for a worked example.

`fetch_one`/`fetch_all` are the one place `aiosqlite.Row` gets converted
to a plain `dict` — every repository method (and any ad hoc query a
consumer runs through these two methods directly) gets native Python
dicts back, never a SQLite-specific row type. Repositories layer
`datetime` parsing for known timestamp columns on top of that (see
`_util.parse_timestamps`); these two methods don't know which columns are
timestamps, so they can't do that part themselves.
"""

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
