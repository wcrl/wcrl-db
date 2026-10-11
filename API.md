# wcrl_db API reference

The exact signature and return shape of every public call in this library.
If you're writing code against `wcrl_db` and want to know what you'll get
back without reading the source, this is the file to check.

**Keep this in sync by hand** whenever a method is added, removed, or its
return shape changes — there's no generator producing this from the code.

## Conventions used below

- All methods are `async def` unless noted otherwise, and must be awaited.
- Every method that returns row data returns a plain `dict` (or `list[dict]`)
  — never `aiosqlite.Row` — with these column types:
  - `INTEGER` columns → `int`
  - `TEXT` columns → `str`
  - the four timestamp columns (`registered_at`, `created_at`, `updated_at`,
    `joined_at`) → a timezone-aware `datetime.datetime` in UTC, parsed from
    the stored ISO-8601 text.
- "Returns `None`" means exactly that — no exception, just `None` — unless
  stated otherwise.

---

## `Database` (`from wcrl_db import Database`)

### `Database(path: str, *, readonly: bool = False)`
Constructs the object; does not touch the filesystem or open a connection.
`path` is the SQLite file path (or `:memory:`). Sets up `.competitors`,
`.teams`, `.bot_state` as attributes immediately.

### `await db.connect() -> None`
Opens the connection.
- **Writable (default, `readonly=False`)**: creates the parent directory if
  needed, turns on `foreign_keys` and `journal_mode=WAL`, then replays
  `schema.sql` (idempotent — safe on every startup).
- **Read-only (`readonly=True`)**: opens the file with SQLite's `mode=ro`.
  Raises `FileNotFoundError` if the file doesn't already exist. Never
  touches pragmas or the schema.

### `await db.close() -> None`
Closes the connection. Safe to call even if never connected.

### `await db.apply_schema() -> None`
Replays `schema.sql` against the current connection. Called automatically
by `connect()` in writable mode; you shouldn't normally need to call it
yourself.

### `await db.fetch_one(sql: str, params: Iterable = ()) -> dict | None`
Escape hatch for an ad hoc read `wcrl_db` doesn't already provide a method
for. Returns the first matching row as a `dict` (column name → Python
value, per the conventions above — **no timestamp parsing**, since this
generic method doesn't know which columns are timestamps), or `None` if no
row matched.

### `await db.fetch_all(sql: str, params: Iterable = ()) -> list[dict]`
Same as `fetch_one`, but every matching row, each as a `dict`. Empty list
if nothing matched.

### `await db.execute(sql: str, params: Iterable = ()) -> aiosqlite.Cursor`
Escape hatch for an ad hoc write. **This is the one place `aiosqlite` isn't
hidden** — you get the raw cursor back (e.g. for `.lastrowid`). Commits
automatically. Prefer a repository method over this and `fetch_one`/
`fetch_all` wherever one already exists; they exist mainly for tests and
for genuinely one-off queries.

---

## `db.competitors` (`CompetitorRepository`)

Backs the `competitors` and `competitor_profiles` tables.

### `get(discord_id: int) -> dict | None`
`None` if no competitor has that Discord id. Otherwise:

| key | type |
|---|---|
| `discord_id` | `int` |
| `full_name` | `str` |
| `school_email` | `str` (stored lowercase) |
| `registered_at` | `datetime` |
| `created_at` | `datetime` |

### `get_by_email(email: str) -> dict | None`
Same shape as `get()`. Matches case-insensitively (the column is
`COLLATE NOCASE`). `None` if no competitor has that email.

### `exists(discord_id: int) -> bool`
Whether a `competitors` row exists for `discord_id`.

### `upsert(discord_id: int, full_name: str, school_email: str) -> dict`
Inserts a new row, or updates `full_name`/`school_email` in place if
`discord_id` already exists. Always returns a dict (never `None`) — same
shape as `get()`. Does **not** check whether `school_email` is already
claimed by a different `discord_id`; that's the caller's job (see
`get_by_email` above).

### `count() -> int`
Total rows in `competitors`.

### `get_profile(discord_id: int) -> dict | None`
`None` if the competitor has no `competitor_profiles` row (i.e. hasn't
supplied year/major yet). Otherwise:

| key | type |
|---|---|
| `discord_id` | `int` |
| `year` | `str` |
| `major` | `str` |
| `updated_at` | `datetime` |

### `upsert_profile(discord_id: int, year: str, major: str) -> dict`
Inserts or updates the profile row. Always returns a dict — same shape as
`get_profile()`. Raises a foreign-key `IntegrityError` if `discord_id`
has no `competitors` row at all.

### `count_with_profile() -> int`
Total rows in `competitor_profiles`.

### `count_by_year() -> list[tuple[str, int]]`
`(year, count)` pairs, one per distinct `year` value, ordered by count
descending then year ascending. Empty list if no profiles exist.

### `count_by_major() -> list[tuple[str, int]]`
Same shape as `count_by_year()`, grouped by `major` instead.

---

## `db.teams` (`TeamRepository`)

Backs the `teams` and `team_members` tables.

A full "team row" (returned by `get_by_id`, `get_for_member`, `get_by_name`,
`get_by_channel`, and `create`) always has this shape:

| key | type |
|---|---|
| `team_id` | `int` |
| `name` | `str` |
| `name_normalized` | `str` |
| `role_id` | `int` |
| `channel_id` | `int` |
| `created_by` | `int` (a `discord_id`) |
| `created_at` | `datetime` |

### `get_by_id(team_id: int) -> dict | None`
Full team row, or `None` if `team_id` doesn't exist.

### `get_for_member(discord_id: int) -> dict | None`
The full team row for the team `discord_id` belongs to, or `None` if
they're not on a team.

### `get_by_name(name: str) -> dict | None`
Full team row, matched case/whitespace-insensitively (normalizes `name`
internally — you don't need to pre-normalize). `None` if no team matches.

### `get_by_channel(channel_id: int) -> dict | None`
Full team row for the team whose private channel is `channel_id`. `None`
if no team matches.

### `create(name: str, role_id: int, channel_id: int, created_by: int) -> dict`
Inserts a new team (normalizing `name` into `name_normalized` internally)
and returns the full team row — always a dict, never `None`. Raises
`IntegrityError` if `name_normalized`, `role_id`, or `channel_id` collides
with an existing team, or if `created_by` isn't an existing competitor.

### `delete(team_id: int) -> None`
Deletes the team row. `team_members` rows for it cascade-delete
automatically (`ON DELETE CASCADE`, enforced since `connect()` turns on
`foreign_keys`). No-op if `team_id` doesn't exist.

### `add_member(team_id: int, discord_id: int) -> None`
Inserts a `team_members` row. Raises `IntegrityError` if `discord_id` is
already on a team (the one-team-per-competitor unique index), or if
either id doesn't reference an existing row.

### `remove_member(discord_id: int) -> None`
Deletes `discord_id`'s `team_members` row, if any. No-op if they're not on
a team.

### `count_members(team_id: int) -> int`
Number of members currently on `team_id`.

### `list_members(team_id: int) -> list[dict]`
A team's roster, oldest member first. Each dict:

| key | type |
|---|---|
| `discord_id` | `int` |
| `full_name` | `str` |

Empty list if the team has no members (or doesn't exist).

### `list_with_member_counts(order: str = "name") -> list[dict]`
Every team in the database. Each dict:

| key | type |
|---|---|
| `name` | `str` |
| `member_count` | `int` |

`order="name"` sorts alphabetically (case-insensitive); `order="size"`
sorts by `member_count` descending, then name. Raises `KeyError` if
`order` is anything else.

### `search_by_name(fragment: str, limit: int = 25) -> list[dict]`
Teams whose name contains `fragment` (case-insensitive substring match;
literal `%`/`_` in `fragment` are matched literally, not as SQL wildcards).
Each dict has just one key:

| key | type |
|---|---|
| `name` | `str` |

Ordered alphabetically, capped at `limit`. Empty list if nothing matches.

### `count() -> int`
Total rows in `teams`.

### `count_distinct_members() -> int`
Number of distinct competitors who are on *some* team.

### `normalize_team_name(name: str) -> str` (module-level function, not a method)
`wcrl_db.teams.normalize_team_name` — collapses internal whitespace and
casefolds. This is a plain sync function, not a repository method; import
it directly (`from wcrl_db.teams import normalize_team_name`) rather than
through `db.teams`.

---

## `db.bot_state` (`BotStateRepository`)

Backs the `bot_state` key/value table. Generic — has no built-in notion of
what keys exist (today, only `last_announced_changelog` is used, by the
Discord bot).

### `get(key: str) -> str | None`
The stored value for `key`, or `None` if that key has never been set.

### `set(key: str, value: str) -> None`
Inserts or overwrites the value for `key`.
