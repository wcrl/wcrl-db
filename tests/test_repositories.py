"""Tests for the `wcrl_db` repositories — this library's whole public surface.

Current state: fully implemented — covers `CompetitorRepository`,
`TeamRepository`, `BotStateRepository`, and `Database`'s read-only mode.
TODO: none open.
Notes: schema-constraint tests (uniqueness, cascades, foreign keys) live in
`tests/test_db.py` and deliberately bypass this layer with raw SQL; these
tests instead check that each repository method runs the right query and
returns the right shape.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from wcrl_db import Database

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "wcrl_db" / "schema.sql"


async def add_competitor(db, discord_id: int, email: str, name: str = "Test User") -> None:
    await db.execute(
        "INSERT INTO competitors (discord_id, full_name, school_email) VALUES (?, ?, ?)",
        (discord_id, name, email),
    )


class TestCompetitorRepository:
    async def test_get_returns_none_when_missing(self, db):
        assert await db.competitors.get(1) is None

    async def test_upsert_creates_then_updates(self, db):
        row = await db.competitors.upsert(1, "Jane Doe", "jane@uwaterloo.ca")
        assert row["full_name"] == "Jane Doe"

        row = await db.competitors.upsert(1, "Jane D. Doe", "jane.doe@uwaterloo.ca")
        assert row["full_name"] == "Jane D. Doe"
        assert await db.competitors.count() == 1

    async def test_get_by_email_finds_the_owner(self, db):
        await add_competitor(db, 1, "jane@uwaterloo.ca")
        row = await db.competitors.get_by_email("jane@uwaterloo.ca")
        assert row["discord_id"] == 1

    async def test_exists(self, db):
        assert await db.competitors.exists(1) is False
        await add_competitor(db, 1, "jane@uwaterloo.ca")
        assert await db.competitors.exists(1) is True

    async def test_profile_round_trip(self, db):
        await add_competitor(db, 1, "jane@uwaterloo.ca")
        assert await db.competitors.get_profile(1) is None

        row = await db.competitors.upsert_profile(1, "Junior", "Computer Science")
        assert row["year"] == "Junior"

        row = await db.competitors.upsert_profile(1, "Senior", "Harpur")
        assert row["year"] == "Senior"
        assert await db.competitors.count_with_profile() == 1

    async def test_count_by_year_and_major(self, db):
        await add_competitor(db, 1, "a@x.edu")
        await add_competitor(db, 2, "b@x.edu")
        await db.competitors.upsert_profile(1, "Junior", "Computer Science")
        await db.competitors.upsert_profile(2, "Junior", "Harpur")

        assert dict(await db.competitors.count_by_year()) == {"Junior": 2}
        assert dict(await db.competitors.count_by_major()) == {
            "Computer Science": 1,
            "Harpur": 1,
        }


class TestTeamRepository:
    async def _seed_competitor(self, db, discord_id: int = 1) -> None:
        await add_competitor(db, discord_id, f"{discord_id}@x.edu")

    async def test_create_returns_the_full_row_via_lastrowid(self, db):
        await self._seed_competitor(db)
        team = await db.teams.create("Bot Squad", role_id=1, channel_id=2, created_by=1)
        assert team["name"] == "Bot Squad"
        assert team["name_normalized"] == "bot squad"
        assert team["team_id"] is not None

    async def test_get_by_name_is_case_and_whitespace_insensitive(self, db):
        await self._seed_competitor(db)
        await db.teams.create("Bot Squad", role_id=1, channel_id=2, created_by=1)
        assert (await db.teams.get_by_name("bot   squad"))["name"] == "Bot Squad"
        assert await db.teams.get_by_name("Nonexistent") is None

    async def test_get_by_channel(self, db):
        await self._seed_competitor(db)
        team = await db.teams.create("Alpha", role_id=1, channel_id=42, created_by=1)
        assert (await db.teams.get_by_channel(42))["team_id"] == team["team_id"]
        assert await db.teams.get_by_channel(9999) is None

    async def test_add_and_remove_member(self, db):
        await self._seed_competitor(db)
        team = await db.teams.create("Alpha", role_id=1, channel_id=2, created_by=1)

        await db.teams.add_member(team["team_id"], 1)
        assert await db.teams.count_members(team["team_id"]) == 1
        assert (await db.teams.get_for_member(1))["team_id"] == team["team_id"]

        await db.teams.remove_member(1)
        assert await db.teams.count_members(team["team_id"]) == 0
        assert await db.teams.get_for_member(1) is None

    async def test_delete_removes_the_team(self, db):
        await self._seed_competitor(db)
        team = await db.teams.create("Alpha", role_id=1, channel_id=2, created_by=1)
        await db.teams.delete(team["team_id"])
        assert await db.teams.get_by_id(team["team_id"]) is None

    async def test_list_members_ordered_by_joined_at(self, db):
        await self._seed_competitor(db, 1)
        await self._seed_competitor(db, 2)
        team = await db.teams.create("Alpha", role_id=1, channel_id=2, created_by=1)
        await db.teams.add_member(team["team_id"], 1)
        await db.teams.add_member(team["team_id"], 2)

        members = await db.teams.list_members(team["team_id"])
        assert [row["discord_id"] for row in members] == [1, 2]

    async def test_list_with_member_counts_both_orderings(self, db):
        await self._seed_competitor(db, 1)
        await self._seed_competitor(db, 2)
        small = await db.teams.create("Bravo", role_id=1, channel_id=2, created_by=1)
        big = await db.teams.create("Alpha", role_id=3, channel_id=4, created_by=2)
        await db.teams.add_member(big["team_id"], 1)
        await db.teams.add_member(big["team_id"], 2)

        by_name = await db.teams.list_with_member_counts(order="name")
        assert [row["name"] for row in by_name] == ["Alpha", "Bravo"]

        by_size = await db.teams.list_with_member_counts(order="size")
        assert [row["name"] for row in by_size] == ["Alpha", "Bravo"]
        assert by_size[0]["member_count"] == 2

    async def test_search_by_name_matches_fragment_and_escapes_wildcards(self, db):
        await self._seed_competitor(db)
        await db.teams.create("Bot Squad", role_id=1, channel_id=2, created_by=1)

        assert [row["name"] for row in await db.teams.search_by_name("bot")] == ["Bot Squad"]
        assert await db.teams.search_by_name("%") == []

    async def test_count_and_count_distinct_members(self, db):
        await self._seed_competitor(db, 1)
        await self._seed_competitor(db, 2)
        team = await db.teams.create("Alpha", role_id=1, channel_id=2, created_by=1)
        await db.teams.add_member(team["team_id"], 1)
        await db.teams.add_member(team["team_id"], 2)

        assert await db.teams.count() == 1
        assert await db.teams.count_distinct_members() == 2


class TestBotStateRepository:
    async def test_get_returns_none_when_missing(self, db):
        assert await db.bot_state.get("last_announced_changelog") is None

    async def test_set_then_get_round_trips(self, db):
        await db.bot_state.set("last_announced_changelog", "v1.0")
        assert await db.bot_state.get("last_announced_changelog") == "v1.0"

    async def test_set_is_an_upsert(self, db):
        await db.bot_state.set("last_announced_changelog", "v1.0")
        await db.bot_state.set("last_announced_changelog", "v1.1")
        assert await db.bot_state.get("last_announced_changelog") == "v1.1"


class TestReadonlyDatabase:
    @pytest.fixture
    def db_path(self, tmp_path) -> Path:
        path = tmp_path / "wcrl.db"
        conn = sqlite3.connect(path)
        try:
            conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO competitors (discord_id, full_name, school_email) VALUES (1, 'Jane Doe', 'jane@uwaterloo.ca')"
            )
            conn.commit()
        finally:
            conn.close()
        return path

    async def test_missing_file_raises(self, tmp_path):
        db = Database(str(tmp_path / "does-not-exist.db"), readonly=True)
        with pytest.raises(FileNotFoundError):
            await db.connect()

    async def test_can_read_existing_data(self, db_path):
        db = Database(str(db_path), readonly=True)
        try:
            await db.connect()
            row = await db.competitors.get(1)
            assert row["full_name"] == "Jane Doe"
        finally:
            await db.close()

    async def test_writes_are_rejected(self, db_path):
        db = Database(str(db_path), readonly=True)
        try:
            await db.connect()
            with pytest.raises(sqlite3.OperationalError):
                await db.competitors.upsert(2, "John Doe", "john@uwaterloo.ca")
        finally:
            await db.close()

    async def test_schema_is_not_reapplied(self, db_path, monkeypatch):
        calls: list[None] = []
        original = Database.apply_schema

        async def spy(self):
            calls.append(None)
            return await original(self)

        monkeypatch.setattr(Database, "apply_schema", spy)

        db = Database(str(db_path), readonly=True)
        try:
            await db.connect()
        finally:
            await db.close()

        assert calls == []
