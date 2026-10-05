"""Move representation, attack detection and pseudo-legal move generation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .board import Board, Square, algebraic_to_square, offset_square, square_rank, square_to_algebraic
from .constants import (
    BISHOP_DIRECTIONS,
    BOARD_SIZE,
    KING_OFFSETS,
    KNIGHT_OFFSETS,
    PROMOTION_TYPES,
    QUEEN_DIRECTIONS,
    ROOK_DIRECTIONS,
    Color,
    PieceType,
)
from .pieces import piece_type_from_letter, piece_type_letter


@dataclass(frozen=True, slots=True)
class Move:
    from_square: Square
    to_square: Square
    promotion: Optional[PieceType] = None

    @property
    def uci(self) -> str:
        suffix = piece_type_letter(self.promotion) if self.promotion else ""
        return square_to_algebraic(self.from_square) + square_to_algebraic(self.to_square) + suffix

    @classmethod
    def from_uci(cls, text: str) -> "Move":
        if len(text) not in (4, 5):
            raise ValueError(f"Invalid UCI move: {text!r}")
        promotion = piece_type_from_letter(text[4]) if len(text) == 5 else None
        if promotion is not None and promotion not in PROMOTION_TYPES:
            raise ValueError(f"Invalid promotion piece: {text!r}")
        return cls(algebraic_to_square(text[:2]), algebraic_to_square(text[2:4]), promotion)


def pawn_direction(color: Color) -> int:
    return 1 if color is Color.WHITE else -1


def pawn_start_rank(color: Color) -> int:
    return 1 if color is Color.WHITE else BOARD_SIZE - 2


def promotion_rank(color: Color) -> int:
    return BOARD_SIZE - 1 if color is Color.WHITE else 0


def _ray_hits(board: Board, square: Square, directions, by: Color, kinds: tuple[PieceType, ...]) -> bool:
    for d_file, d_rank in directions:
        target = offset_square(square, d_file, d_rank)
        while target is not None:
            piece = board.get(target)
            if piece is not None:
                if piece.color is by and piece.kind in kinds:
                    return True
                break
            target = offset_square(target, d_file, d_rank)
    return False


def _offset_hits(board: Board, square: Square, offsets, by: Color, kind: PieceType) -> bool:
    for d_file, d_rank in offsets:
        target = offset_square(square, d_file, d_rank)
        if target is not None:
            piece = board.get(target)
            if piece is not None and piece.color is by and piece.kind is kind:
                return True
    return False


def is_square_attacked(board: Board, square: Square, by: Color) -> bool:
    """True if any piece of color `by` attacks `square`."""
    # A pawn of `by` attacks diagonally forward, so it sits one rank "behind" the target.
    back = -pawn_direction(by)
    if _offset_hits(board, square, ((-1, back), (1, back)), by, PieceType.PAWN):
        return True
    if _offset_hits(board, square, KNIGHT_OFFSETS, by, PieceType.KNIGHT):
        return True
    if _offset_hits(board, square, KING_OFFSETS, by, PieceType.KING):
        return True
    if _ray_hits(board, square, BISHOP_DIRECTIONS, by, (PieceType.BISHOP, PieceType.QUEEN)):
        return True
    return _ray_hits(board, square, ROOK_DIRECTIONS, by, (PieceType.ROOK, PieceType.QUEEN))


def _pawn_moves(board: Board, square: Square, color: Color, en_passant: Optional[Square]) -> list[Move]:
    moves: list[Move] = []
    direction = pawn_direction(color)

    def add(target: Square) -> None:
        if square_rank(target) == promotion_rank(color):
            moves.extend(Move(square, target, kind) for kind in PROMOTION_TYPES)
        else:
            moves.append(Move(square, target))

    one = offset_square(square, 0, direction)
    if one is not None and board.get(one) is None:
        add(one)
        if square_rank(square) == pawn_start_rank(color):
            two = offset_square(square, 0, 2 * direction)
            if two is not None and board.get(two) is None:
                moves.append(Move(square, two))

    for d_file in (-1, 1):
        target = offset_square(square, d_file, direction)
        if target is None:
            continue
        victim = board.get(target)
        if victim is not None and victim.color is not color:
            add(target)
        elif target == en_passant and victim is None:
            moves.append(Move(square, target))
    return moves


def _step_moves(board: Board, square: Square, color: Color, offsets) -> list[Move]:
    moves = []
    for d_file, d_rank in offsets:
        target = offset_square(square, d_file, d_rank)
        if target is None:
            continue
        occupant = board.get(target)
        if occupant is None or occupant.color is not color:
            moves.append(Move(square, target))
    return moves


def _slide_moves(board: Board, square: Square, color: Color, directions) -> list[Move]:
    moves = []
    for d_file, d_rank in directions:
        target = offset_square(square, d_file, d_rank)
        while target is not None:
            occupant = board.get(target)
            if occupant is None:
                moves.append(Move(square, target))
            else:
                if occupant.color is not color:
                    moves.append(Move(square, target))
                break
            target = offset_square(target, d_file, d_rank)
    return moves


def pseudo_legal_moves_from(board: Board, square: Square, en_passant: Optional[Square] = None) -> list[Move]:
    """Moves ignoring king safety and castling."""
    piece = board.get(square)
    if piece is None:
        return []
    color = piece.color
    if piece.kind is PieceType.PAWN:
        return _pawn_moves(board, square, color, en_passant)
    if piece.kind is PieceType.KNIGHT:
        return _step_moves(board, square, color, KNIGHT_OFFSETS)
    if piece.kind is PieceType.KING:
        return _step_moves(board, square, color, KING_OFFSETS)
    if piece.kind is PieceType.BISHOP:
        return _slide_moves(board, square, color, BISHOP_DIRECTIONS)
    if piece.kind is PieceType.ROOK:
        return _slide_moves(board, square, color, ROOK_DIRECTIONS)
    return _slide_moves(board, square, color, QUEEN_DIRECTIONS)


def pseudo_legal_moves(board: Board, color: Color, en_passant: Optional[Square] = None) -> list[Move]:
    moves: list[Move] = []
    for square, piece in board.pieces():
        if piece.color is color:
            moves.extend(pseudo_legal_moves_from(board, square, en_passant))
    return moves
