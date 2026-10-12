# wcrl-db

Internal library to manage the WCRL aiosqlite database. 

**Check [`API.md`](./API.md) for documentation on all available functions.**

## Install

Either install from command line:
```bash
pip install git+https://github.com/wcrl/wcrl-db.git
```

Or add the following line to your requirements.txt:
```
wcrl-db @ git+https://github.com/wcrl/wcrl-db.git
```

## Repositories

Each repository is a thin wrapper around its tables — no business logic, just persistence. Decisions like "is this a new registration?" or "is this email already claimed by someone else?" belong in the consuming app, built
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
- **`db.bot_state`** — `get`, `set`. A generic key/value store for whatever
  small values a consuming app needs to persist.

## Adding a new domain

A new feature gets its own `wcrl_db/<domain>.py` repository, following the
pattern above, plus its own tables added to `schema.sql`. Wire the new
repository into `Database.__init__` in `connection.py` the same way the
existing three are.

## Tests

```bash
pip install -e .[dev]
pytest
```

`tests/test_db.py` tests schema constraints directly with raw SQL (on
purpose — it's checking the database itself, not this library's code).
`tests/test_repositories.py` tests every repository method.
