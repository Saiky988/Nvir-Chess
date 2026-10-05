"""Position state, legal move generation, move application and end-of-game detection."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Optional

from .board import (
    Board,
    Square,
    algebraic_to_square,
    make_square,
    offset_square,
    square_file,
    square_rank,
    square_to_algebraic,
)
from .constants import STARTING_FEN, Color, PieceType
from .moves import (
    Move,
    is_square_attacked,
    pawn_direction,
    promotion_rank,
    pseudo_legal_moves,
    pseudo_legal_moves_from,
)
from .pieces import Piece

# (king_from, king_to, rook_from, rook_to, squares that must be empty, squares the king passes)
_CASTLING_LAYOUT = {
    "K": ("e1", "g1", "h1", "f1", ("f1", "g1"), ("e1", "f1", "g1")),
    "Q": ("e1", "c1", "a1", "d1", ("b1", "c1", "d1"), ("e1", "d1", "c1")),
    "k": ("e8", "g8", "h8", "f8", ("f8", "g8"), ("e8", "f8", "g8")),
    "q": ("e8", "c8", "a8", "d8", ("b8", "c8", "d8"), ("e8", "d8", "c8")),
}
_ROOK_HOME = {algebraic_to_square(layout[2]): right for right, layout in _CASTLING_LAYOUT.items()}


@dataclass(frozen=True, slots=True)
class CastlingRights:
    white_kingside: bool = True
    white_queenside: bool = True
    black_kingside: bool = True
    black_queenside: bool = True

    def to_fen(self) -> str:
        text = "".join(
            flag
            for flag, enabled in zip(
                "KQkq",
                (self.white_kingside, self.white_queenside, self.black_kingside, self.black_queenside),
            )
            if enabled
        )
        return text or "-"

    @classmethod
    def from_fen(cls, text: str) -> "CastlingRights":
        if text != "-" and (not text or any(c not in "KQkq" for c in text)):
            raise ValueError(f"Invalid castling rights: {text!r}")
        return cls("K" in text, "Q" in text, "k" in text, "q" in text)

    def has(self, flag: str) -> bool:
        return flag in self.to_fen()

    def without(self, flags: str) -> "CastlingRights":
        return CastlingRights.from_fen("".join(c for c in self.to_fen() if c not in flags) or "-")


@dataclass(slots=True)
class Position:
    board: Board = field(default_factory=Board.initial)
    turn: Color = Color.WHITE
    castling: CastlingRights = field(default_factory=CastlingRights)
    en_passant: Optional[Square] = None
    halfmove_clock: int = 0
    fullmove_number: int = 1

    @classmethod
    def initial(cls) -> "Position":
        return cls.from_fen(STARTING_FEN)

    @classmethod
    def from_fen(cls, fen: str) -> "Position":
        parts = fen.split()
        if len(parts) != 6:
            raise ValueError(f"Invalid FEN: {fen!r}")
        placement, turn, castling, ep, halfmove, fullmove = parts
        if turn not in ("w", "b"):
            raise ValueError(f"Invalid FEN turn: {fen!r}")
        return cls(
            board=Board.from_fen_placement(placement),
            turn=Color.WHITE if turn == "w" else Color.BLACK,
            castling=CastlingRights.from_fen(castling),
            en_passant=None if ep == "-" else algebraic_to_square(ep),
            halfmove_clock=int(halfmove),
            fullmove_number=int(fullmove),
        )

    def to_fen(self) -> str:
        ep = square_to_algebraic(self.en_passant) if self.en_passant is not None else "-"
        turn = "w" if self.turn is Color.WHITE else "b"
        return (
            f"{self.board.to_fen_placement()} {turn} {self.castling.to_fen()} {ep} "
            f"{self.halfmove_clock} {self.fullmove_number}"
        )

    def repetition_key(self) -> str:
        """Identity used for threefold repetition (placement, turn, castling, en passant)."""
        return " ".join(self.to_fen().split()[:4])

    def copy(self) -> "Position":
        return replace(self, board=self.board.copy())


def is_in_check(position: Position, color: Optional[Color] = None) -> bool:
    color = color or position.turn
    king = position.board.find_king(color)
    return king is not None and is_square_attacked(position.board, king, color.opponent)


def _castling_moves(position: Position) -> list[Move]:
    color = position.turn
    board = position.board
    flags = "KQ" if color is Color.WHITE else "kq"
    moves = []
    for flag in flags:
        if not position.castling.has(flag):
            continue
        king_from, king_to, rook_from, _, empty, passed = _CASTLING_LAYOUT[flag]
        king = board.get(algebraic_to_square(king_from))
        rook = board.get(algebraic_to_square(rook_from))
        if king != Piece(color, PieceType.KING) or rook != Piece(color, PieceType.ROOK):
            continue
        if any(board.get(algebraic_to_square(sq)) is not None for sq in empty):
            continue
        # Covers: not castling out of check, through check, or into check.
        if any(is_square_attacked(board, algebraic_to_square(sq), color.opponent) for sq in passed):
            continue
        moves.append(Move(algebraic_to_square(king_from), algebraic_to_square(king_to)))
    return moves


def is_castling_move(board: Board, move: Move) -> bool:
    piece = board.get(move.from_square)
    return (
        piece is not None
        and piece.kind is PieceType.KING
        and abs(square_file(move.to_square) - square_file(move.from_square)) == 2
    )


def is_en_passant_move(position: Position, move: Move) -> bool:
    piece = position.board.get(move.from_square)
    return (
        piece is not None
        and piece.kind is PieceType.PAWN
        and move.to_square == position.en_passant
        and square_file(move.from_square) != square_file(move.to_square)
        and position.board.get(move.to_square) is None
    )


def is_promotion_move(position: Position, move: Move) -> bool:
    piece = position.board.get(move.from_square)
    return (
        piece is not None
        and piece.kind is PieceType.PAWN
        and square_rank(move.to_square) == promotion_rank(piece.color)
    )


def captured_piece(position: Position, move: Move) -> Optional[Piece]:
    if is_en_passant_move(position, move):
        return Piece(position.turn.opponent, PieceType.PAWN)
    return position.board.get(move.to_square)


def _is_legal(position: Position, move: Move) -> bool:
    after = apply_move(position, move)
    return not is_in_check(after, position.turn)


def legal_moves(position: Position) -> list[Move]:
    candidates = pseudo_legal_moves(position.board, position.turn, position.en_passant)
    candidates += _castling_moves(position)
    return [move for move in candidates if _is_legal(position, move)]


def legal_moves_from(position: Position, square: Square) -> list[Move]:
    piece = position.board.get(square)
    if piece is None or piece.color is not position.turn:
        return []
    candidates = pseudo_legal_moves_from(position.board, square, position.en_passant)
    if piece.kind is PieceType.KING:
        candidates += [m for m in _castling_moves(position) if m.from_square == square]
    return [move for move in candidates if _is_legal(position, move)]


def is_legal_move(position: Position, move: Move) -> bool:
    return move in legal_moves_from(position, move.from_square)


def _en_passant_target(board: Board, move: Move, color: Color) -> Optional[Square]:
    """Set target only if an enemy pawn could actually capture (keeps repetition keys honest)."""
    target = offset_square(move.from_square, 0, pawn_direction(color))
    for d_file in (-1, 1):
        neighbor = offset_square(move.to_square, d_file, 0)
        if neighbor is not None and board.get(neighbor) == Piece(color.opponent, PieceType.PAWN):
            return target
    return None


def apply_move(position: Position, move: Move) -> Position:
    """Return a new position with `move` played. Does not validate legality."""
    board = position.board.copy()
    piece = board.get(move.from_square)
    if piece is None:
        raise ValueError(f"No piece on {square_to_algebraic(move.from_square)}")
    color = piece.color
    capture = captured_piece(position, move)

    if is_en_passant_move(position, move):
        board.set(make_square(square_file(move.to_square), square_rank(move.from_square)), None)

    if is_castling_move(position.board, move):
        kingside = square_file(move.to_square) > square_file(move.from_square)
        flag = ("K" if kingside else "Q") if color is Color.WHITE else ("k" if kingside else "q")
        _, _, rook_from, rook_to, _, _ = _CASTLING_LAYOUT[flag]
        board.set(algebraic_to_square(rook_to), board.get(algebraic_to_square(rook_from)))
        board.set(algebraic_to_square(rook_from), None)

    board.set(move.from_square, None)
    board.set(move.to_square, Piece(color, move.promotion) if move.promotion else piece)

    castling = position.castling
    if piece.kind is PieceType.KING:
        castling = castling.without("KQ" if color is Color.WHITE else "kq")
    for square in (move.from_square, move.to_square):
        if square in _ROOK_HOME:
            castling = castling.without(_ROOK_HOME[square])

    en_passant = None
    if piece.kind is PieceType.PAWN and abs(square_rank(move.to_square) - square_rank(move.from_square)) == 2:
        en_passant = _en_passant_target(board, move, color)

    reset_clock = piece.kind is PieceType.PAWN or capture is not None
    return Position(
        board=board,
        turn=color.opponent,
        castling=castling,
        en_passant=en_passant,
        halfmove_clock=0 if reset_clock else position.halfmove_clock + 1,
        fullmove_number=position.fullmove_number + (1 if color is Color.BLACK else 0),
    )


def is_checkmate(position: Position) -> bool:
    return is_in_check(position) and not legal_moves(position)


def is_stalemate(position: Position) -> bool:
    return not is_in_check(position) and not legal_moves(position)


def has_insufficient_material(board: Board) -> bool:
    """K vs K, K+minor vs K, and K+B vs K+B with same-colored bishops."""
    minors: list[tuple[Square, Piece]] = []
    for square, piece in board.pieces():
        if piece.kind is PieceType.KING:
            continue
        if piece.kind in (PieceType.PAWN, PieceType.ROOK, PieceType.QUEEN):
            return False
        minors.append((square, piece))
    if len(minors) <= 1:
        return True
    if all(piece.kind is PieceType.BISHOP for _, piece in minors):
        square_colors = {(square_file(sq) + square_rank(sq)) % 2 for sq, _ in minors}
        return len(square_colors) == 1
    return False
