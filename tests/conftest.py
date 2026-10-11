"""Shared pytest fixtures."""

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
