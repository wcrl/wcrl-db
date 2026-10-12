# wcrl-db

Internal library to manage the WCRL aiosqlite database. 

**Check [`API.md`](./API.md) for documentation on all available functions.

## Install

Either install from command line:
```bash
pip install git+https://github.com/wcrl/wcrl-db.git
```

Or add the following line to your requirements.txt:
```
wcrl-db @ git+https://github.com/wcrl/wcrl-db.git
```

## Usage from an async app (the Discord bot)

The bot already has a running event loop, so it just holds one connection
for its whole lifetime:

```python
from wcrl_db import Database

db = Database("data/wcrl.db")
await db.connect()

competitor = await db.competitors.get(discord_id)
team = await db.teams.get_by_name("Bot Squad")

await db.close()
```

## Usage from a sync app (a Flask API)

Flask views are plain sync functions. Rather than keeping one aiosqlite
connection alive across requests (which needs a persistent event loop this
app doesn't have), open a short-lived **read-only** connection per request
and wrap the one async call in `asyncio.run(...)`:

```python
import asyncio
from flask import jsonify
from wcrl_db import Database

DB_PATH = "data/wcrl.db"

@app.route("/api/teams")
def list_teams():
    async def fetch():
        db = Database(DB_PATH, readonly=True)
        await db.connect()
        try:
            return await db.teams.list_with_member_counts()
        finally:
            await db.close()

    rows = asyncio.run(fetch())
    return jsonify(rows)
```

Every repository method already returns plain `dict`s (see `API.md`), so
there's no `dict(row)` conversion to do here — the only thing to watch is
that any `datetime` value (there isn't one in this particular result) needs
`.isoformat()` before `jsonify` if you're on a Flask/Werkzeug version whose
default JSON encoder doesn't handle `datetime` for you.

`readonly=True` opens the file with SQLite's `mode=ro` — it never calls
`apply_schema()` or touches WAL pragmas, and any write attempted through it
raises `sqlite3.OperationalError` straight from SQLite itself. This is what
makes it safe to read from a second process while the bot's writable
connection is open elsewhere.

**One deployment constraint to remember**: SQLite's read/write concurrency
(including this `mode=ro` trick) only works when both processes share the
same file on the same machine/volume. There's no multi-host story here — if
the API ever moves to its own host, this stops working and the API needs a
different way to reach the data (e.g. talking to the bot over a small HTTP
endpoint instead of opening the file directly).

## Repositories

Each repository is a thin wrapper around its tables — no business logic,
just persistence. Decisions like "is this a new registration?" or "is this
email already claimed by someone else?" belong in the consuming app, built
on top of these primitives (`get`, `exists`, `get_by_email`, etc.), not in
the library. **See [`API.md`](./API.md) for every method's signature and
exact return shape** — this section is just an index:

- **`db.competitors`** — `get`, `get_by_email`, `exists`, `upsert`, `count`,
  `get_profile`, `upsert_profile`, `count_with_profile`, `count_by_year`,
  `count_by_major`.
- **`db.teams`** — `get_by_id`, `get_for_member`, `get_by_name`,
  `get_by_channel`, `create`, `delete`, `add_member`, `remove_member`,
  `count_members`, `list_members`, `list_with_member_counts`,
  `search_by_name`, `count`, `count_distinct_members`. Also exports
  `normalize_team_name` (`wcrl_db.teams.normalize_team_name`), which defines
  what `teams.name_normalized` means.
- **`db.bot_state`** — `get`, `set`. A generic key/value store; currently
  holds `last_announced_changelog`.

## Adding a new domain

A future feature (inventory, parts requests, battery loans) gets its own
`wcrl_db/<domain>.py` repository, following the pattern above, plus its own
tables added to `schema.sql`. Wire the new repository into `Database.__init__`
in `connection.py` the same way the existing three are.

## Tests

```bash
pip install -e .[dev]
pytest
```

`tests/test_db.py` tests schema constraints directly with raw SQL (on
purpose — it's checking the database itself, not this library's code).
`tests/test_repositories.py` tests every repository method.
