"""Game orchestration between the chess core, SQLite and the renderer. No Discord imports."""
from __future__ import annotations

import asyncio
import logging
import secrets
from typing import Optional

from packages.chess import (
    Game,
    GameNotActiveError,
    GameNotFoundError,
    GameStatus,
    Move,
    MoveRecord,
    NotAPlayerError,
    NotYourTurnError,
    Piece,
    Square,
    algebraic_to_square,
    square_to_algebraic,
)
from packages.chess.rules import is_en_passant_move

from ..storage import Database, StoredGame
from .board_renderer import BoardRenderer, Perspective, RenderError, highlights_for

log = logging.getLogger(__name__)

GAME_ID_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
GAME_ID_LENGTH = 6


def normalize_game_id(raw: str) -> str:
    game_id = raw.strip().lstrip("#").upper()
    if len(game_id) != GAME_ID_LENGTH or any(c not in GAME_ID_ALPHABET for c in game_id):
        raise GameNotFoundError(f"Game `{raw}` not found.")
    return game_id


class ChessService:
    def __init__(self, database: Database, renderer: BoardRenderer, default_theme: int = 1) -> None:
        self.db = database
        self.renderer = renderer
        self.default_theme = default_theme
        self._cache: dict[str, StoredGame] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def start(self) -> list[StoredGame]:
        """Resume unfinished games from SQLite after a restart."""
        games = await self.db.unfinished()
        for stored in games:
            self._cache[stored.game.game_id] = stored
        log.info("Resumed %d unfinished game(s) from database", len(games))
        return games

    def _lock(self, game_id: str) -> asyncio.Lock:
        return self._locks.setdefault(game_id, asyncio.Lock())

    async def _new_game_id(self) -> str:
        for _ in range(20):
            game_id = "".join(secrets.choice(GAME_ID_ALPHABET) for _ in range(GAME_ID_LENGTH))
            if game_id not in self._cache and not await self.db.exists(game_id):
                return game_id
        raise RuntimeError("Could not allocate a unique game id")

    # ---- reads ---------------------------------------------------------

    async def get(self, game_id: str) -> StoredGame:
        game_id = normalize_game_id(game_id)
        stored = self._cache.get(game_id) or await self.db.get(game_id)
        if stored is None:
            raise GameNotFoundError(f"Game `{game_id}` not found.")
        if not stored.game.is_over:
            self._cache[game_id] = stored
        return stored

    async def games_for(self, player_id: int) -> list[StoredGame]:
        return await self.db.for_player(player_id, (GameStatus.WAITING, GameStatus.ACTIVE))

    async def resolve_player_game(self, player_id: int, game_id: Optional[str]) -> StoredGame:
        """Explicit id, or the player's only active game."""
        if game_id:
            return await self.get(game_id)
        active = [s for s in await self.games_for(player_id) if s.game.status is GameStatus.ACTIVE]
        if not active:
            raise GameNotFoundError("You have no active game.")
        if len(active) > 1:
            ids = ", ".join(f"`{s.game.game_id}`" for s in active[:10])
            raise GameNotFoundError(f"You have several active games ({ids}). Please pass a game id.")
        return await self.get(active[0].game.game_id)

    @staticmethod
    def require_turn(game: Game, player_id: int) -> None:
        if game.status is not GameStatus.ACTIVE:
            raise GameNotActiveError("This game is not active.")
        color = game.color_of(player_id)
        if color is None:
            raise NotAPlayerError("You are not a player in this game.")
        if color is not game.current_turn:
            raise NotYourTurnError("It is not your turn.")

    def movable_pieces(self, game: Game, player_id: int) -> list[tuple[str, Piece]]:
        self.require_turn(game, player_id)
        result = []
        for square in game.movable_squares():
            piece = game.position.board.get(square)
            assert piece is not None
            result.append((square_to_algebraic(square), piece))
        return result

    def destinations(self, game: Game, player_id: int, from_square: str) -> list[Move]:
        self.require_turn(game, player_id)
        moves = game.legal_moves_from(from_square)
        unique: dict[Square, Move] = {}
        for move in moves:  # collapse the 4 promotion variants into one destination
            unique.setdefault(move.to_square, Move(move.from_square, move.to_square))
        return sorted(unique.values(), key=lambda m: m.to_square)

    def is_capture(self, game: Game, move: Move) -> bool:
        return game.position.board.get(move.to_square) is not None or is_en_passant_move(game.position, move)

    # ---- writes --------------------------------------------------------

    async def _mutate(self, game_id: str, action) -> tuple[StoredGame, object]:
        """Apply `action` to a copy, persist, then swap into the cache (cache never diverges from DB)."""
        game_id = normalize_game_id(game_id)
        async with self._lock(game_id):
            current = await self.get(game_id)
            working = Game.from_dict(current.game.to_dict())
            outcome = action(working)
            updated = StoredGame(working, current.theme, current.guild_id, current.channel_id, current.message_id)
            await self.db.save(updated)
            if working.is_over:
                self._cache.pop(game_id, None)
                self._locks.pop(game_id, None)
                log.info(
                    "Game %s finished: result=%s termination=%s",
                    game_id, working.result and working.result.value, working.termination and working.termination.value,
                )
            else:
                self._cache[game_id] = updated
            return updated, outcome

    async def create_game(
        self,
        player_id: int,
        theme: Optional[int] = None,
        guild_id: Optional[int] = None,
        channel_id: Optional[int] = None,
    ) -> StoredGame:
        theme = theme or self.default_theme
        self.renderer.assets.board(theme)  # validates theme
        game = Game.create(await self._new_game_id(), player_id)
        stored = StoredGame(game, theme, guild_id, channel_id)
        await self.db.save(stored)
        self._cache[game.game_id] = stored
        log.info("Game %s created by %s (theme %d)", game.game_id, player_id, theme)
        return stored

    async def join(self, game_id: str, player_id: int) -> StoredGame:
        stored, _ = await self._mutate(game_id, lambda g: g.join(player_id))
        log.info("Player %s joined game %s as Black", player_id, stored.game.game_id)
        return stored

    async def make_move(
        self, game_id: str, player_id: int, from_square: str, to_square: str, promotion: Optional[str] = None
    ) -> tuple[StoredGame, MoveRecord]:
        stored, record = await self._mutate(
            game_id, lambda g: g.make_move(player_id, from_square, to_square, promotion)
        )
        log.info("Game %s: %s played %s", stored.game.game_id, player_id, record.san)
        return stored, record  # type: ignore[return-value]

    async def resign(self, game_id: str, player_id: int) -> StoredGame:
        stored, _ = await self._mutate(game_id, lambda g: g.resign(player_id))
        return stored

    async def offer_draw(self, game_id: str, player_id: int) -> tuple[StoredGame, bool]:
        stored, ended = await self._mutate(game_id, lambda g: g.offer_draw(player_id))
        log.info("Game %s: draw %s by %s", stored.game.game_id, "accepted" if ended else "offered", player_id)
        return stored, bool(ended)

    async def decline_draw(self, game_id: str, player_id: int) -> StoredGame:
        stored, _ = await self._mutate(game_id, lambda g: g.decline_draw(player_id))
        return stored

    async def abandon(self, game_id: str) -> StoredGame:
        stored, _ = await self._mutate(game_id, lambda g: g.abandon())
        log.info("Game %s abandoned", stored.game.game_id)
        return stored

    async def set_message(self, game_id: str, channel_id: int, message_id: int) -> None:
        game_id = normalize_game_id(game_id)
        async with self._lock(game_id):
            stored = await self.get(game_id)
            stored.channel_id, stored.message_id = channel_id, message_id
            await self.db.save(stored)

    # ---- rendering -----------------------------------------------------

    def render(
        self,
        stored: StoredGame,
        selected: Optional[str] = None,
        perspective: Perspective = "white",
    ) -> bytes:
        game = stored.game
        selected_sq = algebraic_to_square(selected) if selected else None
        destinations: list[Square] = []
        captures: list[Square] = []
        if selected_sq is not None:
            for move in game.legal_moves_from(selected_sq):
                destinations.append(move.to_square)
                if self.is_capture(game, move):
                    captures.append(move.to_square)
        last = game.last_move
        last_squares = [algebraic_to_square(last.from_square), algebraic_to_square(last.to_square)] if last else []
        check = game.position.board.find_king(game.current_turn) if game.in_check else None
        highlights = highlights_for(selected_sq, destinations, captures, last_squares, check)
        try:
            return self.renderer.render_png(game.position.board, stored.theme, perspective, highlights)
        except RenderError:
            log.exception("Render failed for game %s", game.game_id)
            raise

    async def render_async(self, stored: StoredGame, selected: Optional[str] = None) -> bytes:
        return await asyncio.to_thread(self.render, stored, selected)
