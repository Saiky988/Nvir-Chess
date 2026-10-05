"""Tests for SQLite database persistence with aiosqlite."""
import pytest

from apps.bot.storage.database import Database, StoredGame
from packages.chess.constants import Color, GameStatus
from packages.chess.game import Game


@pytest.mark.asyncio
async def test_database_lifecycle_and_persistence(tmp_path):
    db_file = tmp_path / "test_chess.db"
    db = Database(db_file)
    await db.connect()

    # Create a game and make moves
    game = Game.create("XYZ999", white_player_id=111)
    game.join(222)
    game.make_move(111, "e2", "e4")
    game.make_move(222, "c7", "c5")

    stored = StoredGame(game, theme=3, guild_id=1234, channel_id=5678, message_id=9012)
    await db.save(stored)

    # Check existence
    assert await db.exists("XYZ999")
    assert not await db.exists("NONEXIST")

    # Load and verify
    loaded = await db.get("XYZ999")
    assert loaded is not None
    assert loaded.game.game_id == "XYZ999"
    assert loaded.game.white_player_id == 111
    assert loaded.game.black_player_id == 222
    assert loaded.game.status == GameStatus.ACTIVE
    assert loaded.theme == 3
    assert loaded.guild_id == 1234
    assert loaded.channel_id == 5678
    assert loaded.message_id == 9012
    assert len(loaded.game.history) == 2
    assert loaded.game.history[0].san == "e4"
    assert loaded.game.history[1].san == "c5"

    # Verify query for active games
    active_games = await db.unfinished()
    assert len(active_games) == 1
    assert active_games[0].game.game_id == "XYZ999"

    # Simulate restart: close and reconnect new database instance
    await db.close()

    db_restarted = Database(db_file)
    await db_restarted.connect()
    resumed = await db_restarted.unfinished()
    assert len(resumed) == 1
    assert resumed[0].game.game_id == "XYZ999"
    assert resumed[0].game.current_turn == Color.WHITE
    await db_restarted.close()
