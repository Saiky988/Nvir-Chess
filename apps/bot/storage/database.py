"""SQLite persistence for games (JSON/FEN only, never pickled objects)."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import aiosqlite

from packages.chess import Game, GameStatus

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    id                TEXT PRIMARY KEY,
    white_player_id   INTEGER NOT NULL,
    black_player_id   INTEGER,
    status            TEXT NOT NULL,
    current_turn      TEXT NOT NULL,
    board_state       TEXT NOT NULL,
    move_history      TEXT NOT NULL DEFAULT '[]',
    castling_rights   TEXT NOT NULL,
    en_passant_target TEXT,
    halfmove_clock    INTEGER NOT NULL DEFAULT 0,
    fullmove_number   INTEGER NOT NULL DEFAULT 1,
    repetitions       TEXT NOT NULL DEFAULT '{}',
    draw_offer        TEXT,
    result            TEXT,
    termination       TEXT,
    theme             INTEGER NOT NULL DEFAULT 1,
    guild_id          INTEGER,
    channel_id        INTEGER,
    message_id        INTEGER,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    finished_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_games_status ON games(status);
CREATE INDEX IF NOT EXISTS idx_games_white ON games(white_player_id);
CREATE INDEX IF NOT EXISTS idx_games_black ON games(black_player_id);
"""

_COLUMNS = (
    "id, white_player_id, black_player_id, status, current_turn, board_state, move_history, "
    "castling_rights, en_passant_target, halfmove_clock, fullmove_number, repetitions, draw_offer, "
    "result, termination, theme, guild_id, channel_id, message_id, created_at, updated_at, finished_at"
)


class DatabaseError(RuntimeError):
    pass


@dataclass
class StoredGame:
    """A game plus the Discord-side metadata needed to find its board message."""

    game: Game
    theme: int = 1
    guild_id: Optional[int] = None
    channel_id: Optional[int] = None
    message_id: Optional[int] = None


class Database:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = await aiosqlite.connect(self.path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.executescript(SCHEMA)
            await self._conn.commit()
        except (aiosqlite.Error, OSError) as exc:
            raise DatabaseError(f"Could not open database at {self.path}: {exc}") from exc
        log.info("Database ready at %s", self.path)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise DatabaseError("Database is not connected")
        return self._conn

    async def save(self, stored: StoredGame) -> None:
        data = stored.game.to_dict()
        fen_parts = data["fen"].split()
        values = (
            data["game_id"], data["white_player_id"], data["black_player_id"], data["status"],
            stored.game.current_turn.value, data["fen"], json.dumps(data["history"]),
            fen_parts[2], None if fen_parts[3] == "-" else fen_parts[3], int(fen_parts[4]), int(fen_parts[5]),
            json.dumps(data["repetitions"]), data["draw_offer"], data["result"], data["termination"],
            stored.theme, stored.guild_id, stored.channel_id, stored.message_id,
            data["created_at"], data["updated_at"], data["finished_at"],
        )
        placeholders = ", ".join("?" * len(values))
        try:
            await self.conn.execute(f"INSERT OR REPLACE INTO games ({_COLUMNS}) VALUES ({placeholders})", values)
            await self.conn.commit()
        except aiosqlite.Error as exc:
            raise DatabaseError(f"Failed to save game {data['game_id']}: {exc}") from exc

    async def get(self, game_id: str) -> Optional[StoredGame]:
        rows = await self._query(f"SELECT {_COLUMNS} FROM games WHERE id = ?", (game_id,))
        return rows[0] if rows else None

    async def exists(self, game_id: str) -> bool:
        try:
            async with self.conn.execute("SELECT 1 FROM games WHERE id = ?", (game_id,)) as cursor:
                return await cursor.fetchone() is not None
        except aiosqlite.Error as exc:
            raise DatabaseError(str(exc)) from exc

    async def unfinished(self) -> list[StoredGame]:
        return await self._query(
            f"SELECT {_COLUMNS} FROM games WHERE status IN (?, ?)",
            (GameStatus.WAITING.value, GameStatus.ACTIVE.value),
        )

    async def for_player(self, player_id: int, statuses: tuple[GameStatus, ...]) -> list[StoredGame]:
        marks = ", ".join("?" * len(statuses))
        return await self._query(
            f"SELECT {_COLUMNS} FROM games WHERE (white_player_id = ? OR black_player_id = ?) "
            f"AND status IN ({marks}) ORDER BY updated_at DESC LIMIT 25",
            (player_id, player_id, *(s.value for s in statuses)),
        )

    async def _query(self, sql: str, params: tuple) -> list[StoredGame]:
        try:
            async with self.conn.execute(sql, params) as cursor:
                rows = await cursor.fetchall()
        except aiosqlite.Error as exc:
            raise DatabaseError(str(exc)) from exc
        return [self._row_to_stored(row) for row in rows]

    @staticmethod
    def _row_to_stored(row: aiosqlite.Row) -> StoredGame:
        game = Game.from_dict(
            {
                "game_id": row["id"],
                "white_player_id": row["white_player_id"],
                "black_player_id": row["black_player_id"],
                "status": row["status"],
                "fen": row["board_state"],
                "history": json.loads(row["move_history"]),
                "repetitions": json.loads(row["repetitions"]),
                "result": row["result"],
                "termination": row["termination"],
                "draw_offer": row["draw_offer"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "finished_at": row["finished_at"],
            }
        )
        return StoredGame(game, row["theme"], row["guild_id"], row["channel_id"], row["message_id"])
