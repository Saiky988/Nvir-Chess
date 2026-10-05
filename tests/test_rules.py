"""Tests for standard chess rules: checks, pins, castling, en passant, promotion, mate, stalemate."""
import pytest

from packages.chess.board import algebraic_to_square, square_to_algebraic
from packages.chess.constants import Color, PieceType
from packages.chess.moves import Move
from packages.chess.rules import (
    CastlingRights,
    Position,
    apply_move,
    has_insufficient_material,
    is_checkmate,
    is_in_check,
    is_stalemate,
    legal_moves,
    legal_moves_from,
)


def targets(moves: list[Move]) -> set[str]:
    return {square_to_algebraic(m.to_square) for m in moves}


def test_fools_mate():
    # 1. f3 e5 2. g4 Qh4#
    pos = Position.initial()
    pos = apply_move(pos, Move(algebraic_to_square("f2"), algebraic_to_square("f3")))
    pos = apply_move(pos, Move(algebraic_to_square("e7"), algebraic_to_square("e5")))
    pos = apply_move(pos, Move(algebraic_to_square("g2"), algebraic_to_square("g4")))
    pos = apply_move(pos, Move(algebraic_to_square("d8"), algebraic_to_square("h4")))

    assert pos.turn == Color.WHITE
    assert is_in_check(pos)
    assert is_checkmate(pos)
    assert len(legal_moves(pos)) == 0


def test_scholars_mate():
    # 1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7#
    pos = Position.initial()
    moves = [("e2", "e4"), ("e7", "e5"), ("f1", "c4"), ("b8", "c6"), ("d1", "h5"), ("g8", "f6"), ("h5", "f7")]
    for src, dst in moves:
        pos = apply_move(pos, Move(algebraic_to_square(src), algebraic_to_square(dst)))

    assert pos.turn == Color.BLACK
    assert is_in_check(pos)
    assert is_checkmate(pos)


def test_stalemate():
    # Famous stalemate: Ka8 with black pawn at a7, white king at c7, white queen at b6 -> stalemate if Black's turn
    # FEN: k7/8/1K6/8/8/8/8/8 w - - 0 1 -> setup position: k7/8/1K6/8/8/8/8/7Q b - - 0 1 would be check,
    # Standard: 7k/5Q2/6K1/8/8/8/8/8 b - - 0 1 (Kh8, Qf7, Kg6) -> Kh8 has no moves, not in check.
    pos = Position.from_fen("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
    assert not is_in_check(pos)
    assert is_stalemate(pos)
    assert len(legal_moves(pos)) == 0


def test_cannot_move_into_check_pinned_piece():
    # Absolute pin: White king at e1, White knight at e2, Black rook at e8.
    # Knight on e2 cannot move because it would expose king to check.
    pos = Position.from_fen("4r3/8/8/8/8/8/4N3/4K3 w - - 0 1")
    knight_sq = algebraic_to_square("e2")
    moves = legal_moves_from(pos, knight_sq)
    assert len(moves) == 0


def test_castling_kingside_and_queenside():
    # Empty squares between King and Rooks
    pos = Position.from_fen("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    king_moves = targets(legal_moves_from(pos, algebraic_to_square("e1")))
    # Can castle kingside (g1) and queenside (c1)
    assert "g1" in king_moves
    assert "c1" in king_moves

    # Perform kingside castle
    after_k = apply_move(pos, Move(algebraic_to_square("e1"), algebraic_to_square("g1")))
    assert after_k.board.get(algebraic_to_square("g1")).kind == PieceType.KING
    assert after_k.board.get(algebraic_to_square("f1")).kind == PieceType.ROOK
    assert after_k.board.get(algebraic_to_square("h1")) is None

    # Perform queenside castle
    after_q = apply_move(pos, Move(algebraic_to_square("e1"), algebraic_to_square("c1")))
    assert after_q.board.get(algebraic_to_square("c1")).kind == PieceType.KING
    assert after_q.board.get(algebraic_to_square("d1")).kind == PieceType.ROOK
    assert after_q.board.get(algebraic_to_square("a1")) is None


def test_castling_blocked_by_attack():
    # Attack on king (in check) -> cannot castle
    pos_check = Position.from_fen("r3k2r/8/8/8/4r3/8/8/R3K2R w KQkq - 0 1")
    king_moves = targets(legal_moves_from(pos_check, algebraic_to_square("e1")))
    assert "g1" not in king_moves
    assert "c1" not in king_moves

    # Attack on f1 (passing through check) -> cannot castle kingside
    pos_through = Position.from_fen("r3k2r/8/8/8/5r2/8/8/R3K2R w KQkq - 0 1")
    km = targets(legal_moves_from(pos_through, algebraic_to_square("e1")))
    assert "g1" not in km
    assert "c1" in km

    # Attack on g1 (landing in check) -> cannot castle kingside
    pos_into = Position.from_fen("r3k2r/8/8/8/6r1/8/8/R3K2R w KQkq - 0 1")
    km = targets(legal_moves_from(pos_into, algebraic_to_square("e1")))
    assert "g1" not in km
    assert "c1" in km


def test_en_passant():
    # White pawn on e5, Black pawn advances d7 -> d5. White can capture on d6.
    pos = Position.from_fen("rnbqkbnr/pppppppp/8/4P3/8/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1")
    # Black plays d7-d5
    pos = apply_move(pos, Move(algebraic_to_square("d7"), algebraic_to_square("d5")))
    assert pos.en_passant == algebraic_to_square("d6")

    # White can capture en passant e5-d6
    ep_move = Move(algebraic_to_square("e5"), algebraic_to_square("d6"))
    assert ep_move in legal_moves(pos)

    # Apply move
    after = apply_move(pos, ep_move)
    assert after.board.get(algebraic_to_square("d6")).kind == PieceType.PAWN
    assert after.board.get(algebraic_to_square("d6")).color == Color.WHITE
    # Captured black pawn on d5 is gone
    assert after.board.get(algebraic_to_square("d5")) is None


def test_pawn_promotion():
    # White pawn on e7, can advance to e8 and promote
    pos = Position.from_fen("8/4P3/8/8/8/8/8/4K2k w - - 0 1")
    moves = legal_moves_from(pos, algebraic_to_square("e7"))
    # Must offer 4 promotion pieces
    promos = {m.promotion for m in moves}
    assert promos == {PieceType.QUEEN, PieceType.ROOK, PieceType.BISHOP, PieceType.KNIGHT}

    # Promote to Queen
    q_move = Move(algebraic_to_square("e7"), algebraic_to_square("e8"), PieceType.QUEEN)
    after = apply_move(pos, q_move)
    promoted = after.board.get(algebraic_to_square("e8"))
    assert promoted.kind == PieceType.QUEEN
    assert promoted.color == Color.WHITE


def test_insufficient_material():
    # K vs K
    assert has_insufficient_material(Position.from_fen("8/8/4k3/8/8/4K3/8/8 w - - 0 1").board)
    # K+B vs K
    assert has_insufficient_material(Position.from_fen("8/8/4k3/8/2B5/4K3/8/8 w - - 0 1").board)
    # K+N vs K
    assert has_insufficient_material(Position.from_fen("8/8/4k3/8/2N5/4K3/8/8 w - - 0 1").board)
    # K+P vs K -> NOT insufficient
    assert not has_insufficient_material(Position.from_fen("8/8/4k3/8/2P5/4K3/8/8 w - - 0 1").board)


def test_perft_accuracy():
    """Verify legal move generation count against standard perft reference values."""
    def perft(position: Position, depth: int) -> int:
        if depth == 0:
            return 1
        return sum(perft(apply_move(position, m), depth - 1) for m in legal_moves(position))

    # Initial position depth 1: 20, depth 2: 400
    init = Position.initial()
    assert perft(init, 1) == 20
    assert perft(init, 2) == 400

    # Kiwipete position (complex castling, pins, en-passant)
    kiwipete = Position.from_fen("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1")
    assert perft(kiwipete, 1) == 48
