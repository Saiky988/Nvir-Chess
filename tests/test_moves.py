"""Tests for move generation, attack detection and piece movement patterns."""
import pytest

from packages.chess.board import Board, algebraic_to_square, square_to_algebraic
from packages.chess.constants import Color, PieceType
from packages.chess.moves import (
    Move,
    is_square_attacked,
    pseudo_legal_moves,
    pseudo_legal_moves_from,
)
from packages.chess.pieces import Piece


def targets(moves: list[Move]) -> set[str]:
    return {square_to_algebraic(m.to_square) for m in moves}


def test_pawn_single_and_double_moves():
    board = Board()
    board.set(algebraic_to_square("e2"), Piece(Color.WHITE, PieceType.PAWN))
    moves = pseudo_legal_moves_from(board, algebraic_to_square("e2"))
    assert targets(moves) == {"e3", "e4"}


def test_pawn_blocked():
    board = Board()
    board.set(algebraic_to_square("e2"), Piece(Color.WHITE, PieceType.PAWN))
    board.set(algebraic_to_square("e3"), Piece(Color.BLACK, PieceType.PAWN))
    moves = pseudo_legal_moves_from(board, algebraic_to_square("e2"))
    assert len(moves) == 0


def test_pawn_captures():
    board = Board()
    board.set(algebraic_to_square("e4"), Piece(Color.WHITE, PieceType.PAWN))
    board.set(algebraic_to_square("d5"), Piece(Color.BLACK, PieceType.PAWN))
    board.set(algebraic_to_square("f5"), Piece(Color.BLACK, PieceType.KNIGHT))
    moves = pseudo_legal_moves_from(board, algebraic_to_square("e4"))
    assert targets(moves) == {"e5", "d5", "f5"}


def test_knight_movement():
    board = Board()
    board.set(algebraic_to_square("d4"), Piece(Color.WHITE, PieceType.KNIGHT))
    moves = pseudo_legal_moves_from(board, algebraic_to_square("d4"))
    assert targets(moves) == {"c6", "e6", "f5", "f3", "e2", "c2", "b3", "b5"}


def test_knight_blocked_by_friendly():
    board = Board()
    board.set(algebraic_to_square("b1"), Piece(Color.WHITE, PieceType.KNIGHT))
    board.set(algebraic_to_square("c3"), Piece(Color.WHITE, PieceType.PAWN))
    moves = pseudo_legal_moves_from(board, algebraic_to_square("b1"))
    # Can jump to a3, d2, but not c3 (friendly pawn)
    assert "c3" not in targets(moves)
    assert "a3" in targets(moves)
    assert "d2" in targets(moves)


def test_bishop_sliding():
    board = Board()
    board.set(algebraic_to_square("d4"), Piece(Color.WHITE, PieceType.BISHOP))
    board.set(algebraic_to_square("f6"), Piece(Color.BLACK, PieceType.PAWN))
    moves = pseudo_legal_moves_from(board, algebraic_to_square("d4"))
    t = targets(moves)
    # North-east ray stops after f6 (capture)
    assert "e5" in t and "f6" in t and "g7" not in t
    # South-west ray
    assert "c3" in t and "b2" in t and "a1" in t


def test_rook_sliding():
    board = Board()
    board.set(algebraic_to_square("d4"), Piece(Color.WHITE, PieceType.ROOK))
    board.set(algebraic_to_square("d6"), Piece(Color.WHITE, PieceType.PAWN))
    moves = pseudo_legal_moves_from(board, algebraic_to_square("d4"))
    t = targets(moves)
    # North ray blocked by friendly pawn at d6
    assert "d5" in t and "d6" not in t and "d7" not in t
    # East, West, South unobstructed
    assert "e4" in t and "f4" in t and "g4" in t and "h4" in t
    assert "c4" in t and "b4" in t and "a4" in t
    assert "d3" in t and "d2" in t and "d1" in t


def test_queen_movement():
    board = Board()
    board.set(algebraic_to_square("d4"), Piece(Color.WHITE, PieceType.QUEEN))
    moves = pseudo_legal_moves_from(board, algebraic_to_square("d4"))
    # Queen on empty board has 27 legal squares
    assert len(moves) == 27


def test_king_movement():
    board = Board()
    board.set(algebraic_to_square("e4"), Piece(Color.WHITE, PieceType.KING))
    moves = pseudo_legal_moves_from(board, algebraic_to_square("e4"))
    assert targets(moves) == {"d3", "d4", "d5", "e3", "e5", "f3", "f4", "f5"}


def test_is_square_attacked():
    board = Board()
    board.set(algebraic_to_square("e4"), Piece(Color.BLACK, PieceType.ROOK))
    board.set(algebraic_to_square("c3"), Piece(Color.BLACK, PieceType.KNIGHT))
    board.set(algebraic_to_square("a7"), Piece(Color.BLACK, PieceType.PAWN))

    # Attacked by rook
    assert is_square_attacked(board, algebraic_to_square("e1"), Color.BLACK)
    # Attacked by knight
    assert is_square_attacked(board, algebraic_to_square("b5"), Color.BLACK)
    assert is_square_attacked(board, algebraic_to_square("d5"), Color.BLACK)
    # Attacked by black pawn (moving south, attacks b6)
    assert is_square_attacked(board, algebraic_to_square("b6"), Color.BLACK)

    # Not attacked
    assert not is_square_attacked(board, algebraic_to_square("h1"), Color.BLACK)
