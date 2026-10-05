"""Game aggregate: players, status, move history and result. Independent of Discord."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .board import Square, algebraic_to_square, square_to_algebraic
from .constants import PROMOTION_TYPES, Color, GameResult, GameStatus, PieceType, Termination
from .moves import Move
from .notation import move_to_san
from .pieces import piece_type_from_letter
from .rules import (
    Position,
    apply_move,
    captured_piece,
    has_insufficient_material,
    is_castling_move,
    is_en_passant_move,
    is_in_check,
    is_promotion_move,
    legal_moves,
    legal_moves_from,
)


class ChessError(Exception):
    """Base error for user-facing rule violations."""


class GameNotFoundError(ChessError):
    pass


class GameAlreadyStartedError(ChessError):
    pass


class GameNotActiveError(ChessError):
    pass


class NotAPlayerError(ChessError):
    pass


class NotYourTurnError(ChessError):
    pass


class IllegalMoveError(ChessError):
    pass


class PromotionRequiredError(IllegalMoveError):
    pass


class InvalidPromotionError(IllegalMoveError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _validate_player_id(player_id: int) -> int:
    if isinstance(player_id, bool) or not isinstance(player_id, int) or player_id <= 0:
        raise ValueError(f"Invalid player id: {player_id!r}")
    return player_id


def _parse_promotion(value: Optional[PieceType | str]) -> Optional[PieceType]:
    if value is None or isinstance(value, PieceType):
        return value
    text = str(value).strip().lower()
    try:
        return PieceType(text)
    except ValueError:
        pass
    if len(text) == 1:
        try:
            return piece_type_from_letter(text)
        except ValueError:
            pass
    raise InvalidPromotionError("Invalid promotion piece.")


@dataclass(slots=True)
class MoveRecord:
    move_number: int
    player: str
    piece: str
    from_square: str
    to_square: str
    san: str
    uci: str
    captured: Optional[str] = None
    promotion: Optional[str] = None
    castling: Optional[str] = None
    en_passant: bool = False
    check: bool = False
    checkmate: bool = False
    timestamp: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MoveRecord":
        return cls(**data)


@dataclass(slots=True)
class Game:
    game_id: str
    white_player_id: int
    black_player_id: Optional[int] = None
    status: GameStatus = GameStatus.WAITING
    position: Position = field(default_factory=Position.initial)
    history: list[MoveRecord] = field(default_factory=list)
    repetitions: dict[str, int] = field(default_factory=dict)
    result: Optional[GameResult] = None
    termination: Optional[Termination] = None
    draw_offer: Optional[Color] = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    finished_at: Optional[str] = None

    @classmethod
    def create(cls, game_id: str, white_player_id: int) -> "Game":
        game = cls(game_id=game_id, white_player_id=_validate_player_id(white_player_id))
        game.repetitions[game.position.repetition_key()] = 1
        return game

    # ---- queries -------------------------------------------------------

    @property
    def current_turn(self) -> Color:
        return self.position.turn

    @property
    def current_player_id(self) -> Optional[int]:
        return self.player_id_for(self.current_turn)

    @property
    def is_over(self) -> bool:
        return self.status in (GameStatus.FINISHED, GameStatus.ABANDONED)

    @property
    def in_check(self) -> bool:
        return is_in_check(self.position)

    @property
    def last_move(self) -> Optional[MoveRecord]:
        return self.history[-1] if self.history else None

    def player_id_for(self, color: Color) -> Optional[int]:
        return self.white_player_id if color is Color.WHITE else self.black_player_id

    def color_of(self, player_id: int) -> Optional[Color]:
        if player_id == self.white_player_id:
            return Color.WHITE
        if self.black_player_id is not None and player_id == self.black_player_id:
            return Color.BLACK
        return None

    def legal_moves_from(self, square: str | Square) -> list[Move]:
        if self.status is not GameStatus.ACTIVE:
            return []
        sq = algebraic_to_square(square) if isinstance(square, str) else square
        return legal_moves_from(self.position, sq)

    def movable_squares(self) -> list[Square]:
        if self.status is not GameStatus.ACTIVE:
            return []
        return sorted({move.from_square for move in legal_moves(self.position)})

    # ---- commands ------------------------------------------------------

    def join(self, player_id: int) -> None:
        _validate_player_id(player_id)
        if self.status is not GameStatus.WAITING:
            raise GameAlreadyStartedError("This game has already started.")
        if player_id == self.white_player_id:
            raise ChessError("You cannot join your own game.")
        self.black_player_id = player_id
        self.status = GameStatus.ACTIVE
        self._touch()

    def _require_active_player(self, player_id: int) -> Color:
        if self.status is not GameStatus.ACTIVE:
            raise GameNotActiveError("This game is not active.")
        color = self.color_of(player_id)
        if color is None:
            raise NotAPlayerError("You are not a player in this game.")
        return color

    def make_move(
        self,
        player_id: int,
        from_square: str,
        to_square: str,
        promotion: Optional[PieceType | str] = None,
    ) -> MoveRecord:
        color = self._require_active_player(player_id)
        if color is not self.current_turn:
            raise NotYourTurnError("It is not your turn.")

        try:
            src, dst = algebraic_to_square(from_square), algebraic_to_square(to_square)
        except ValueError as exc:
            raise IllegalMoveError(str(exc)) from exc

        piece = self.position.board.get(src)
        if piece is None or piece.color is not color:
            raise IllegalMoveError("You can only move your own pieces.")

        promo = _parse_promotion(promotion)
        candidate = Move(src, dst, promo)
        if is_promotion_move(self.position, Move(src, dst)):
            if promo is None:
                raise PromotionRequiredError("Choose a promotion piece.")
            if promo not in PROMOTION_TYPES:
                raise InvalidPromotionError("Invalid promotion piece.")
        elif promo is not None:
            raise InvalidPromotionError("This move is not a promotion.")

        if candidate not in legal_moves_from(self.position, src):
            raise IllegalMoveError(f"Illegal move: {from_square}-{to_square}.")

        record = self._record(candidate, color)
        self.position = apply_move(self.position, candidate)
        self.history.append(record)
        key = self.position.repetition_key()
        self.repetitions[key] = self.repetitions.get(key, 0) + 1
        self.draw_offer = None
        self._touch()
        self._check_automatic_end(color)
        return record

    def _record(self, move: Move, color: Color) -> MoveRecord:
        pos = self.position
        piece = pos.board.get(move.from_square)
        assert piece is not None
        captured = captured_piece(pos, move)
        castling = None
        if is_castling_move(pos.board, move):
            castling = "kingside" if move.to_square > move.from_square else "queenside"
        san = move_to_san(pos, move)
        return MoveRecord(
            move_number=pos.fullmove_number,
            player=color.value,
            piece=piece.kind.value,
            from_square=square_to_algebraic(move.from_square),
            to_square=square_to_algebraic(move.to_square),
            san=san,
            uci=move.uci,
            captured=captured.kind.value if captured else None,
            promotion=move.promotion.value if move.promotion else None,
            castling=castling,
            en_passant=is_en_passant_move(pos, move),
            check=san.endswith(("+", "#")),
            checkmate=san.endswith("#"),
        )

    def _check_automatic_end(self, mover: Color) -> None:
        if not legal_moves(self.position):
            if is_in_check(self.position):
                self._finish(GameResult(mover.value), Termination.CHECKMATE)
            else:
                self._finish(GameResult.DRAW, Termination.STALEMATE)
        elif has_insufficient_material(self.position.board):
            self._finish(GameResult.DRAW, Termination.INSUFFICIENT_MATERIAL)
        elif self.repetitions.get(self.position.repetition_key(), 0) >= 3:
            self._finish(GameResult.DRAW, Termination.THREEFOLD_REPETITION)
        elif self.position.halfmove_clock >= 100:
            self._finish(GameResult.DRAW, Termination.FIFTY_MOVE_RULE)

    def resign(self, player_id: int) -> None:
        color = self._require_active_player(player_id)
        self._finish(GameResult(color.opponent.value), Termination.RESIGNATION)

    def offer_draw(self, player_id: int) -> bool:
        """Offer a draw, or accept if the opponent already offered. Returns True if the game ended."""
        color = self._require_active_player(player_id)
        if self.draw_offer is color.opponent:
            self._finish(GameResult.DRAW, Termination.AGREEMENT)
            return True
        self.draw_offer = color
        self._touch()
        return False

    def accept_draw(self, player_id: int) -> None:
        color = self._require_active_player(player_id)
        if self.draw_offer is not color.opponent:
            raise ChessError("There is no draw offer to accept.")
        self._finish(GameResult.DRAW, Termination.AGREEMENT)

    def decline_draw(self, player_id: int) -> None:
        color = self._require_active_player(player_id)
        if self.draw_offer is not color.opponent:
            raise ChessError("There is no draw offer to decline.")
        self.draw_offer = None
        self._touch()

    def abandon(self) -> None:
        if self.is_over:
            raise GameNotActiveError("This game is already over.")
        self.status = GameStatus.ABANDONED
        self.termination = Termination.ABANDONED
        self.result = None
        self.draw_offer = None
        self.finished_at = utc_now()
        self._touch()

    def _finish(self, result: GameResult, termination: Termination) -> None:
        self.status = GameStatus.FINISHED
        self.result = result
        self.termination = termination
        self.draw_offer = None
        self.finished_at = utc_now()
        self._touch()

    def _touch(self) -> None:
        self.updated_at = utc_now()

    # ---- serialization -------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "game_id": self.game_id,
            "white_player_id": self.white_player_id,
            "black_player_id": self.black_player_id,
            "status": self.status.value,
            "fen": self.position.to_fen(),
            "history": [record.to_dict() for record in self.history],
            "repetitions": dict(self.repetitions),
            "result": self.result.value if self.result else None,
            "termination": self.termination.value if self.termination else None,
            "draw_offer": self.draw_offer.value if self.draw_offer else None,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "finished_at": self.finished_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Game":
        return cls(
            game_id=str(data["game_id"]),
            white_player_id=_validate_player_id(int(data["white_player_id"])),
            black_player_id=(
                _validate_player_id(int(data["black_player_id"]))
                if data.get("black_player_id") is not None
                else None
            ),
            status=GameStatus(data["status"]),
            position=Position.from_fen(data["fen"]),
            history=[MoveRecord.from_dict(item) for item in data.get("history", [])],
            repetitions={str(k): int(v) for k, v in data.get("repetitions", {}).items()},
            result=GameResult(data["result"]) if data.get("result") else None,
            termination=Termination(data["termination"]) if data.get("termination") else None,
            draw_offer=Color(data["draw_offer"]) if data.get("draw_offer") else None,
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            finished_at=data.get("finished_at"),
        )
