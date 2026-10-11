# wcrl-db

## Goal
Shared SQLite data-access library for the WCRL club. Used by the Discord bot (`wcrl-bot`, async, read/write) and the club's backend API (planned, sync/Flask, read-only). One schema, one set of queries, written once here — both apps depend on this exact package instead of a copy that can drift.

## Architecture Principles
- Fully isolated: no dependency on discord.py, Flask, or any consuming app. The only runtime dependency is `aiosqlite`.
- `Database` (`connection.py`) owns the connection lifecycle and exposes one repository per domain table group (`competitors.py`, `teams.py`, `bot_state.py`). A future domain (inventory, parts requests, battery loans) adds its own `wcrl_db/<domain>.py` repository the same way, wired into `Database.__init__`.
- Every public method returns plain Python types — `dict`/`list[dict]` for rows (never `aiosqlite.Row`), `int`/`str`/`bool`, and timezone-aware UTC `datetime` for the four timestamp columns (`registered_at`, `created_at`, `updated_at`, `joined_at`). The database is fully abstracted; nothing outside `connection.py` touches a SQLite-specific type. The one deliberate exception is `Database.execute()`'s return value (a raw `aiosqlite.Cursor`, for `.lastrowid`) — an escape hatch for ad hoc writes.
- `readonly=True` on `Database` opens the file `mode=ro`, for a second process (the backend API) reading the same file safely alongside the bot's writable connection. See README.md for the async-app vs. sync-app usage patterns.
- Schema changes are additive only — `schema.sql` is replayed on every writable `connect()` (`CREATE TABLE IF NOT EXISTS` is idempotent; `ALTER TABLE` is not). A true modification (rename/retype a column, tighten a constraint) needs numbered migration files plus a `schema_migrations` table — don't build that preemptively, but don't bolt on another new table either if what's actually needed is a modification.
- **`API.md` is the canonical reference for every method's signature and return shape** — keep it in sync by hand whenever a method is added, removed, or its return shape changes. It exists so a developer (or an AI session) can check it instead of reading source.

## Coding Guidelines
- Minimize comments. Code should read clearly through naming and structure, not narration. A single `#` line above a genuinely non-obvious block (a workaround, a subtle ordering constraint) is fine — the exception, not the default. An open TODO lives as a one-line `# TODO: ...` comment at the relevant line.
- Every file opens with a module-level docstring, **one line**, stating the file's purpose — no `Purpose:`/`Current state:`/`TODO:`/`Notes:` sections.
- Every public method/function gets a one-line docstring: what it does, not how or why — this is a library other developers read without necessarily reading the source, so don't skip these the way an internal app function might. Internal (leading-underscore) helpers don't need one if the name makes it obvious.

## Project Structure
```
wcrl-db/
├── pyproject.toml
├── README.md           # install + usage (async app, sync app), repository index
├── API.md               # exact signature + return shape of every method
├── wcrl_db/
│   ├── __init__.py       # from wcrl_db import Database
│   ├── connection.py       # Database: connection lifecycle, readonly=True mode
│   ├── competitors.py       # CompetitorRepository
│   ├── teams.py               # TeamRepository + normalize_team_name
│   ├── bot_state.py            # BotStateRepository
│   ├── _util.py                 # internal helpers (timestamp parsing); not public API
│   └── schema.sql                 # the schema
└── tests/
```

## Data Model
- `competitors(discord_id PK, full_name, school_email UNIQUE, registered_at, created_at)`
- `competitor_profiles(discord_id PK FK -> competitors, year, major, updated_at)` — optional, absence means not yet supplied
- `teams(team_id PK, name, name_normalized UNIQUE, role_id UNIQUE, channel_id UNIQUE, created_by FK, created_at)`
- `team_members(team_id FK, discord_id FK, joined_at)` + unique index on `discord_id` (one team per competitor — a consuming app's rule, enforced here as a DB constraint)
- `bot_state(key PK, value)` — generic key/value store; the bot currently uses only `last_announced_changelog`

## Workflow
1. Implement the change (new repository method, new table in `schema.sql`, etc.).
2. Add or update tests under `tests/` — schema constraints go in `test_db.py`, repository behavior in `test_repositories.py`.
3. Update `API.md` to match the new/changed method's signature and return shape.
4. Run `pytest`; confirm the full suite passes.
5. If the change affects how a consumer uses the library, update the relevant section of `README.md` too.
6. Commit here, then in each consuming repo (`wcrl-bot`, the backend API), reinstall (`pip install -r requirements.txt`) and run that repo's own suite before considering the change done end-to-end.

## Config
None — this library takes a SQLite file path as a constructor argument (`Database(path)`); it has no env vars or config of its own. Each consuming app decides where its database file lives.
