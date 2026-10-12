# wcrl_db API Reference

`wcrl_db` is a small async library for reading and writing the WCRL club's
SQLite database. It has three parts: a `Database` object that manages the
connection, and three **repositories** (`competitors`, `teams`, `bot_state`)
attached to it, each a collection of methods for one group of tables.

This page documents every public class and method, with its parameters,
return value, and a short example. If you just want to get something
working, start with the Quickstart below.

## Quickstart

### Install

See `README.md` for the current install command.

### Basic usage

Every method in this library is a coroutine — you must `await` it, and
your code must be inside an `async def` function:

```python
import asyncio
from wcrl_db import Database

async def main():
    db = Database("wcrl.db")   # path to the SQLite file
    await db.connect()

    competitor = await db.competitors.get(123456789012345678)
    if competitor is None:
        print("Not registered yet.")
    else:
        print(competitor["full_name"])

    await db.close()

asyncio.run(main())
```

### Using it from a synchronous app

Wrap one `await` call in `asyncio.run(...)`, and open the database
**read-only** — a sync caller like this should only read, never write,
while another process holds the writable connection:

```python
import asyncio
from wcrl_db import Database

def get_team_list():
    async def fetch():
        db = Database("wcrl.db", readonly=True)
        await db.connect()
        try:
            return await db.teams.list_with_member_counts()
        finally:
            await db.close()

    return asyncio.run(fetch())
```

### What you get back

You never see raw SQL types from this library — every method returns
ordinary Python values:

| SQL column type | What you get in Python |
|---|---|
| `INTEGER` | `int` |
| `TEXT` | `str` |
| a timestamp column (`registered_at`, `created_at`, `updated_at`, `joined_at`) | `datetime.datetime` (timezone-aware, UTC) |

A row is a plain `dict`, so you read a field with `row["column_name"]`. A
query that can return nothing (e.g. "find this competitor") gives you
`None` instead of raising an error — always check for that before using
the result.

---

## `Database`

The object that owns the connection. Create one, `connect()` it, and it
gives you `.competitors`, `.teams`, and `.bot_state` to work with.

### `Database(path, *, readonly=False)`

Creates the object. This doesn't touch the filesystem yet — call
`connect()` next.

**Parameters**
- `path` (`str`) – path to the SQLite file, or `":memory:"` for a
  temporary in-memory database (handy for tests).
- `readonly` (`bool`, default `False`) – if `True`, opens the file
  read-only instead of read/write. Use this from any process that only
  needs to read, so it can safely read the same file while another
  process holds the writable connection.

```python
db = Database("wcrl.db")                  # read/write (the writer)
db = Database("wcrl.db", readonly=True)    # read-only (every other reader)
```

### `await db.connect()`

Opens the connection. Call this once, right after creating the `Database`.

- **Read/write** (default): creates the containing folder if it doesn't
  exist, turns on two SQLite settings the schema relies on, then creates
  any tables that don't exist yet. Safe to call every time your app
  starts — it won't touch tables that already exist.
- **Read-only** (`readonly=True`): opens the file as-is. Raises
  `FileNotFoundError` if the file doesn't exist yet — a read-only caller
  can't create the database, so a writer must have connected at least
  once first to create it.

**Raises:** `FileNotFoundError` — in read-only mode, if the file doesn't exist.

### `await db.close()`

Closes the connection. Always call this when you're done (a `finally`
block, as in the Quickstart above, makes sure it happens even on error).
Safe to call even if you never connected.

### `await db.apply_schema()`

Creates any tables that don't exist yet. `connect()` already calls this
for you in read/write mode — you'll rarely need to call it yourself.

### `await db.fetch_one(sql, params=())`

Runs a SQL query yourself and returns the first matching row. This is an
**escape hatch** — reach for a method on `db.competitors`/`db.teams`/
`db.bot_state` first; only use this for a genuinely one-off query that
doesn't already exist as a method.

**Parameters**
- `sql` (`str`) – the SQL query.
- `params` (tuple or list, optional) – values to fill in for `?`
  placeholders in the query.

**Returns:** `dict`, or `None` if nothing matched.

```python
row = await db.fetch_one("SELECT * FROM competitors WHERE discord_id = ?", (123,))
```

### `await db.fetch_all(sql, params=())`

Same as `fetch_one`, but returns every matching row.

**Returns:** `list[dict]` — empty list if nothing matched.

### `await db.execute(sql, params=())`

Runs a SQL statement that changes data (`INSERT`/`UPDATE`/`DELETE`).
Another escape hatch, same guidance as `fetch_one`: prefer an existing
repository method first.

**Returns:** the raw database cursor (useful for `.lastrowid` after an
`INSERT`). This is the one place this library hands back a
driver-specific object instead of a plain Python value.

---

## `db.competitors`

Everything about competitors and their optional year/major profile. Backs
the `competitors` and `competitor_profiles` tables.

A **competitor** dict always looks like this:

| Key | Type | Notes |
|---|---|---|
| `discord_id` | `int` | |
| `full_name` | `str` | |
| `school_email` | `str` | always stored lowercase |
| `registered_at` | `datetime` | |
| `created_at` | `datetime` | |

A **profile** dict (year/major) always looks like this:

| Key | Type | Notes |
|---|---|---|
| `discord_id` | `int` | |
| `year` | `str` | |
| `major` | `str` | |
| `updated_at` | `datetime` | |

### `get(discord_id)`

Look up a competitor.

**Parameters**
- `discord_id` (`int`)

**Returns:** a competitor dict (shape above), or `None` if there isn't one.

```python
competitor = await db.competitors.get(123456789012345678)
```

### `get_by_email(email)`

Look up a competitor by their school email instead of their Discord ID.
Matching ignores case.

**Parameters**
- `email` (`str`)

**Returns:** a competitor dict, or `None` if no competitor has that email.

### `exists(discord_id)`

A cheap yes/no check — use this instead of `get()` when you don't actually
need the competitor's data.

**Returns:** `bool`

### `upsert(discord_id, full_name, school_email)`

Creates a competitor, or updates their name/email if they already exist.
("Upsert" = update if present, insert if not.)

This method does **not** check whether `school_email` already belongs to
someone else — call `get_by_email()` yourself first and decide what to do
if it does.

**Parameters**
- `discord_id` (`int`)
- `full_name` (`str`)
- `school_email` (`str`)

**Returns:** the resulting competitor dict (never `None`).

```python
competitor = await db.competitors.upsert(123456789012345678, "Jane Doe", "jane@uni.edu")
```

### `count()`

**Returns:** `int` – total number of competitors.

### `get_profile(discord_id)`

**Returns:** a profile dict (shape above), or `None` if this competitor
hasn't filled in their year/major yet.

### `upsert_profile(discord_id, year, major)`

Creates or updates a competitor's year/major.

**Parameters**
- `discord_id` (`int`)
- `year` (`str`)
- `major` (`str`)

**Returns:** the resulting profile dict (never `None`).

**Raises:** `IntegrityError` if `discord_id` doesn't belong to an existing
competitor — create the competitor first with `upsert()`.

### `count_with_profile()`

**Returns:** `int` – how many competitors have filled in a profile.

### `count_by_year()`

**Returns:** `list[(str, int)]` – one `(year, count)` pair per year that's
actually on file, sorted by count (most common first).

### `count_by_major()`

Same as `count_by_year()`, grouped by major instead.

---

## `db.teams`

Everything about teams and their members. Backs the `teams` and
`team_members` tables.

A **team** dict always looks like this:

| Key | Type | Notes |
|---|---|---|
| `team_id` | `int` | |
| `name` | `str` | the display name, e.g. `"Bot Squad"` |
| `name_normalized` | `str` | lowercased, whitespace-collapsed — used internally for matching |
| `role_id` | `int` | Discord role ID |
| `channel_id` | `int` | Discord channel ID |
| `created_by` | `int` | the creator's `discord_id` |
| `created_at` | `datetime` | |

### `get_by_id(team_id)`

**Returns:** a team dict, or `None` if `team_id` doesn't exist.

### `get_for_member(discord_id)`

Find the team a competitor belongs to.

**Returns:** a team dict, or `None` if they're not on a team.

### `get_by_name(name)`

Find a team by its display name. Matching ignores case and collapses
extra whitespace, so `"bot   squad"` finds `"Bot Squad"` — you don't need
to clean up `name` yourself first.

**Returns:** a team dict, or `None` if no team matches.

```python
team = await db.teams.get_by_name("Bot Squad")
```

### `get_by_channel(channel_id)`

Find the team whose private channel is `channel_id`.

**Returns:** a team dict, or `None` if no team matches.

### `create(name, role_id, channel_id, created_by)`

Creates a new team.

**Parameters**
- `name` (`str`) – the display name.
- `role_id` (`int`) – the Discord role already created for this team.
- `channel_id` (`int`) – the Discord channel already created for this team.
- `created_by` (`int`) – the creating competitor's `discord_id`.

**Returns:** the new team dict (never `None`).

**Raises:** `IntegrityError` if the name is already taken (ignoring case/
whitespace), if `role_id` or `channel_id` is already used by another team,
or if `created_by` isn't an existing competitor.

```python
team = await db.teams.create("Bot Squad", role_id=1111, channel_id=2222, created_by=123456789012345678)
```

### `delete(team_id)`

Deletes a team. Every member's `team_members` row is removed automatically
along with it. Does nothing (no error) if `team_id` doesn't exist.

### `add_member(team_id, discord_id)`

Adds a competitor to a team.

**Raises:** `IntegrityError` if `discord_id` is already on a team (a
competitor can only be on one team at a time), or if either ID doesn't
exist.

### `remove_member(discord_id)`

Removes a competitor from their team. Does nothing if they're not on one.

### `count_members(team_id)`

**Returns:** `int` – how many competitors are currently on this team.

### `list_members(team_id)`

Get a team's roster.

**Returns:** `list[dict]`, oldest member first, each shaped like:

| Key | Type |
|---|---|
| `discord_id` | `int` |
| `full_name` | `str` |

Empty list if the team has no members.

### `list_with_member_counts(order="name")`

Get every team, with how many members each has.

**Parameters**
- `order` (`str`, default `"name"`) – `"name"` sorts alphabetically;
  `"size"` sorts by member count, biggest team first.

**Raises:** `KeyError` if `order` is anything other than `"name"` or `"size"`.

**Returns:** `list[dict]`, each shaped like:

| Key | Type |
|---|---|
| `name` | `str` |
| `member_count` | `int` |

```python
teams = await db.teams.list_with_member_counts(order="size")
for team in teams:
    print(team["name"], team["member_count"])
```

### `search_by_name(fragment, limit=25)`

Find teams whose name contains `fragment` — built for autocomplete-style
search boxes. Matching ignores case.

**Returns:** `list[dict]`, up to `limit` results, each just `{"name": str}`.

### `count()`

**Returns:** `int` – total number of teams.

### `count_distinct_members()`

**Returns:** `int` – how many competitors are on *some* team (as opposed
to not being on any team at all).

### Helper function: `normalize_team_name(name)`

Not a method on `db.teams` — a plain function you import separately:

```python
from wcrl_db.teams import normalize_team_name

normalize_team_name("  Bot   Squad  ")   # -> "bot squad"
```

Collapses whitespace and lowercases, the same way `get_by_name()` and
`create()` do internally. You won't usually need to call this yourself —
it's exposed mainly so other code can match the library's exact rules if
it needs to.

---

## `db.bot_state`

A generic key → value store for small bits of internal bookkeeping. Backs
the `bot_state` table. It doesn't know or care what keys exist — that's up
to whatever app is using it.

### `get(key)`

**Parameters**
- `key` (`str`)

**Returns:** `str`, or `None` if that key has never been set.

```python
value = await db.bot_state.get("some_key")
```

### `set(key, value)`

Stores a value, overwriting whatever was there before.

**Parameters**
- `key` (`str`)
- `value` (`str`)

---

## Errors you might run into

| Error | When it happens |
|---|---|
| `FileNotFoundError` | You opened `Database(path, readonly=True)` but `path` doesn't exist yet. |
| `aiosqlite.IntegrityError` | A write would break a database rule — a duplicate email, a duplicate team name, a competitor already on a team, etc. Each method's **Raises** note above tells you when to expect this. |
| `sqlite3.OperationalError` | You tried to write through a read-only (`readonly=True`) connection. |

---

**Keeping this file up to date:** whenever a method is added, removed, or
its parameters/return shape change, update the matching section above in
the same commit.
