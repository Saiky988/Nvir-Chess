"""Discord-independent chess core."""
from .board import (
    Board,
    Square,
    algebraic_to_coordinate,
    algebraic_to_square,
    coordinate_to_algebraic,
    square_to_algebraic,
)
from .constants import Color, GameResult, GameStatus, PieceType, Termination
from .game import (
    ChessError,
    Game,
    GameAlreadyStartedError,
    GameNotActiveError,
    GameNotFoundError,
    IllegalMoveError,
    InvalidPromotionError,
    MoveRecord,
    NotAPlayerError,
    NotYourTurnError,
    PromotionRequiredError,
)
from .moves import Move
from .notation import move_to_san
from .pieces import Piece
from .rules import CastlingRights, Position, is_in_check, legal_moves, legal_moves_from

__all__ = [
    "Board",
    "CastlingRights",
    "ChessError",
    "Color",
    "Game",
    "GameAlreadyStartedError",
    "GameNotActiveError",
    "GameNotFoundError",
    "GameResult",
    "GameStatus",
    "IllegalMoveError",
    "InvalidPromotionError",
    "Move",
    "MoveRecord",
    "NotAPlayerError",
    "NotYourTurnError",
    "Piece",
    "PieceType",
    "Position",
    "PromotionRequiredError",
    "Square",
    "Termination",
    "algebraic_to_coordinate",
    "algebraic_to_square",
    "coordinate_to_algebraic",
    "is_in_check",
    "legal_moves",
    "legal_moves_from",
    "move_to_san",
    "square_to_algebraic",
]
