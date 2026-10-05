"""Standard Algebraic Notation (SAN)."""
from __future__ import annotations

from .board import square_file, square_rank, square_to_algebraic
from .constants import FILES, RANKS, PieceType
from .moves import Move
from .pieces import piece_type_letter
from .rules import (
    Position,
    apply_move,
    captured_piece,
    is_castling_move,
    is_in_check,
    legal_moves,
)


def move_to_san(position: Position, move: Move) -> str:
    """SAN for a legal `move` in `position` (before it is played), including +/# suffix."""
    board = position.board
    piece = board.get(move.from_square)
    if piece is None:
        raise ValueError("No piece on source square")

    if is_castling_move(board, move):
        san = "O-O" if square_file(move.to_square) > square_file(move.from_square) else "O-O-O"
    else:
        is_capture = captured_piece(position, move) is not None
        target = square_to_algebraic(move.to_square)
        if piece.kind is PieceType.PAWN:
            prefix = FILES[square_file(move.from_square)] if is_capture else ""
        else:
            prefix = piece.san_letter + _disambiguation(position, move)
        san = prefix + ("x" if is_capture else "") + target
        if move.promotion:
            san += "=" + piece_type_letter(move.promotion).upper()

    after = apply_move(position, move)
    if is_in_check(after):
        san += "#" if not legal_moves(after) else "+"
    return san


def _disambiguation(position: Position, move: Move) -> str:
    piece = position.board.get(move.from_square)
    rivals = [
        other.from_square
        for other in legal_moves(position)
        if other.to_square == move.to_square
        and other.from_square != move.from_square
        and position.board.get(other.from_square) == piece
    ]
    if not rivals:
        return ""
    from_file, from_rank = square_file(move.from_square), square_rank(move.from_square)
    if all(square_file(sq) != from_file for sq in rivals):
        return FILES[from_file]
    if all(square_rank(sq) != from_rank for sq in rivals):
        return RANKS[from_rank]
    return FILES[from_file] + RANKS[from_rank]
