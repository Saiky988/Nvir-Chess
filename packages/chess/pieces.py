from __future__ import annotations

from dataclasses import dataclass

from .constants import Color, PieceType

_TYPE_TO_LETTER = {
    PieceType.PAWN: "p",
    PieceType.KNIGHT: "n",
    PieceType.BISHOP: "b",
    PieceType.ROOK: "r",
    PieceType.QUEEN: "q",
    PieceType.KING: "k",
}
_LETTER_TO_TYPE = {letter: kind for kind, letter in _TYPE_TO_LETTER.items()}


@dataclass(frozen=True, slots=True)
class Piece:
    color: Color
    kind: PieceType

    @property
    def symbol(self) -> str:
        """FEN letter: uppercase for White, lowercase for Black."""
        letter = _TYPE_TO_LETTER[self.kind]
        return letter.upper() if self.color is Color.WHITE else letter

    @property
    def san_letter(self) -> str:
        return "" if self.kind is PieceType.PAWN else _TYPE_TO_LETTER[self.kind].upper()

    @classmethod
    def from_symbol(cls, symbol: str) -> "Piece":
        kind = _LETTER_TO_TYPE.get(symbol.lower())
        if kind is None:
            raise ValueError(f"Invalid piece symbol: {symbol!r}")
        color = Color.WHITE if symbol.isupper() else Color.BLACK
        return cls(color, kind)


def piece_type_from_letter(letter: str) -> PieceType:
    kind = _LETTER_TO_TYPE.get(letter.lower())
    if kind is None:
        raise ValueError(f"Invalid piece letter: {letter!r}")
    return kind


def piece_type_letter(kind: PieceType) -> str:
    return _TYPE_TO_LETTER[kind]
