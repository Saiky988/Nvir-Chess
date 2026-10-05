"""Tests for Board representation and coordinate conversions."""
import pytest

from packages.chess.board import (
    Board,
    algebraic_to_coordinate,
    algebraic_to_square,
    coordinate_to_algebraic,
    make_square,
    on_board,
    square_file,
    square_rank,
    square_to_algebraic,
)
from packages.chess.constants import Color, PieceType
from packages.chess.pieces import Piece


def test_square_conversions():
    assert algebraic_to_square("a1") == 0
    assert algebraic_to_square("h1") == 7
    assert algebraic_to_square("a8") == 56
    assert algebraic_to_square("h8") == 63
    assert algebraic_to_square("e4") == 28

    assert square_to_algebraic(0) == "a1"
    assert square_to_algebraic(7) == "h1"
    assert square_to_algebraic(56) == "a8"
    assert square_to_algebraic(63) == "h8"
    assert square_to_algebraic(28) == "e4"


def test_coordinate_conversions():
    assert algebraic_to_coordinate("a1") == (0, 0)
    assert algebraic_to_coordinate("e4") == (4, 3)
    assert algebraic_to_coordinate("h8") == (7, 7)

    assert coordinate_to_algebraic(0, 0) == "a1"
    assert coordinate_to_algebraic(4, 3) == "e4"
    assert coordinate_to_algebraic(7, 7) == "h8"


def test_invalid_conversions():
    with pytest.raises(ValueError):
        algebraic_to_square("i1")
    with pytest.raises(ValueError):
        algebraic_to_square("a9")
    with pytest.raises(ValueError):
        algebraic_to_square("xyz")
    with pytest.raises(ValueError):
        square_to_algebraic(-1)
    with pytest.raises(ValueError):
        square_to_algebraic(64)
    with pytest.raises(ValueError):
        coordinate_to_algebraic(8, 0)


def test_initial_board():
    board = Board.initial()
    assert board.get(algebraic_to_square("e1")) == Piece(Color.WHITE, PieceType.KING)
    assert board.get(algebraic_to_square("d1")) == Piece(Color.WHITE, PieceType.QUEEN)
    assert board.get(algebraic_to_square("e8")) == Piece(Color.BLACK, PieceType.KING)
    assert board.get(algebraic_to_square("d8")) == Piece(Color.BLACK, PieceType.QUEEN)

    assert board.get(algebraic_to_square("a1")) == Piece(Color.WHITE, PieceType.ROOK)
    assert board.get(algebraic_to_square("h1")) == Piece(Color.WHITE, PieceType.ROOK)
    assert board.get(algebraic_to_square("e2")) == Piece(Color.WHITE, PieceType.PAWN)
    assert board.get(algebraic_to_square("e7")) == Piece(Color.BLACK, PieceType.PAWN)

    # Empty squares in the center
    assert board.get(algebraic_to_square("e4")) is None
    assert board.get(algebraic_to_square("d5")) is None


def test_fen_placement_roundtrip():
    board = Board.initial()
    fen = board.to_fen_placement()
    assert fen == "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"

    loaded = Board.from_fen_placement(fen)
    assert loaded == board


def test_find_king():
    board = Board.initial()
    assert board.find_king(Color.WHITE) == algebraic_to_square("e1")
    assert board.find_king(Color.BLACK) == algebraic_to_square("e8")

    # Board with no white king
    empty_board = Board()
    assert empty_board.find_king(Color.WHITE) is None
