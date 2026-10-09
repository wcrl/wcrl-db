"""Shared pytest fixtures.

Current state: fully implemented (single `db` fixture).
TODO: none open.
Notes: assumes `wcrl_db` is installed (`pip install -e .[dev]`), same as any
consumer of this library — no sys.path hacking needed.
"""

from __future__ import annotations

import pytest_asyncio

from wcrl_db import Database


@pytest_asyncio.fixture
async def db():
    """A fresh in-memory database with the real schema applied."""
    database = Database(":memory:")
    await database.connect()
    try:
        yield database
    finally:
        await database.close()
