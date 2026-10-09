"""Public entry point for the `wcrl_db` package.

Purpose: a standalone, discord.py-free data-access library for the WCRL
club's SQLite database, shared as a pip dependency by both the Discord bot
and the club's backend API — one source of truth for the schema and every
query against it.
Current state: fully implemented. `Database` (in `connection.py`) owns the
connection and exposes `competitors`/`teams`/`bot_state`, one repository per
domain table group; each repository module holds all of the SQL for its
tables.
TODO: a future domain (inventory, parts requests, battery loans) adds its
own `wcrl_db/<domain>.py` repository alongside the existing ones, following
the same pattern.
Notes: `from wcrl_db import Database` is the supported import path for a
consumer that only needs the connection class; submodules (`wcrl_db.competitors`,
`wcrl_db.teams`, `wcrl_db.bot_state`) are importable directly too, e.g. for
`wcrl_db.teams.normalize_team_name`. See the project README for how an
async app (the bot) and a sync app (a Flask API) each use this.
"""

from __future__ import annotations

from .connection import Database

__all__ = ["Database"]
