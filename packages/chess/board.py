"""8x8 board. Squares are ints 0..63: index = rank * 8 + file (a1 = 0, h8 = 63)."""
from __future__ import annotations

from typing import Iterator, Optional

from .constants import BOARD_SIZE, FILES, RANKS, Color, PieceType
from .pieces import Piece

Square = int


def make_square(file: int, rank: int) -> Square:
    return rank * BOARD_SIZE + file


def square_file(square: Square) -> int:
    return square % BOARD_SIZE


def square_rank(square: Square) -> int:
    return square // BOARD_SIZE


def on_board(file: int, rank: int) -> bool:
    return 0 <= file < BOARD_SIZE and 0 <= rank < BOARD_SIZE


def offset_square(square: Square, d_file: int, d_rank: int) -> Optional[Square]:
    file, rank = square_file(square) + d_file, square_rank(square) + d_rank
    return make_square(file, rank) if on_board(file, rank) else None


def algebraic_to_square(name: str) -> Square:
    """'e4' -> 28."""
    if not isinstance(name, str) or len(name) != 2:
        raise ValueError(f"Invalid square: {name!r}")
    file_char, rank_char = name[0].lower(), name[1]
    if file_char not in FILES or rank_char not in RANKS:
        raise ValueError(f"Invalid square: {name!r}")
    return make_square(FILES.index(file_char), RANKS.index(rank_char))


def square_to_algebraic(square: Square) -> str:
    """28 -> 'e4'."""
    if not 0 <= square < BOARD_SIZE * BOARD_SIZE:
        raise ValueError(f"Invalid square index: {square!r}")
    return FILES[square_file(square)] + RANKS[square_rank(square)]


def algebraic_to_coordinate(name: str) -> tuple[int, int]:
    """'e4' -> (file, rank) zero-based: (4, 3)."""
    square = algebraic_to_square(name)
    return square_file(square), square_rank(square)


def coordinate_to_algebraic(file: int, rank: int) -> str:
    if not on_board(file, rank):
        raise ValueError(f"Invalid coordinate: {(file, rank)!r}")
    return FILES[file] + RANKS[rank]


class Board:
    __slots__ = ("_squares",)

    def __init__(self, squares: Optional[list[Optional[Piece]]] = None) -> None:
        if squares is None:
            squares = [None] * (BOARD_SIZE * BOARD_SIZE)
        if len(squares) != BOARD_SIZE * BOARD_SIZE:
            raise ValueError("Board requires 64 squares")
        self._squares = list(squares)

    @classmethod
    def initial(cls) -> "Board":
        return cls.from_fen_placement("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR")

    @classmethod
    def from_fen_placement(cls, placement: str) -> "Board":
        rows = placement.split("/")
        if len(rows) != BOARD_SIZE:
            raise ValueError(f"Invalid FEN placement: {placement!r}")
        board = cls()
        for row_index, row in enumerate(rows):
            rank = BOARD_SIZE - 1 - row_index
            file = 0
            for char in row:
                if char.isdigit():
                    file += int(char)
                else:
                    if file >= BOARD_SIZE:
                        raise ValueError(f"Invalid FEN placement: {placement!r}")
                    board.set(make_square(file, rank), Piece.from_symbol(char))
                    file += 1
            if file != BOARD_SIZE:
                raise ValueError(f"Invalid FEN placement: {placement!r}")
        return board

    def to_fen_placement(self) -> str:
        rows = []
        for rank in range(BOARD_SIZE - 1, -1, -1):
            row, empty = "", 0
            for file in range(BOARD_SIZE):
                piece = self.get(make_square(file, rank))
                if piece is None:
                    empty += 1
                    continue
                if empty:
                    row += str(empty)
                    empty = 0
                row += piece.symbol
            if empty:
                row += str(empty)
            rows.append(row)
        return "/".join(rows)

    def get(self, square: Square) -> Optional[Piece]:
        return self._squares[square]

    def set(self, square: Square, piece: Optional[Piece]) -> None:
        self._squares[square] = piece

    def copy(self) -> "Board":
        return Board(self._squares)

    def pieces(self) -> Iterator[tuple[Square, Piece]]:
        for square, piece in enumerate(self._squares):
            if piece is not None:
                yield square, piece

    def find_king(self, color: Color) -> Optional[Square]:
        for square, piece in self.pieces():
            if piece.kind is PieceType.KING and piece.color is color:
                return square
        return None

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Board) and self._squares == other._squares

    def __repr__(self) -> str:
        return f"Board({self.to_fen_placement()!r})"
