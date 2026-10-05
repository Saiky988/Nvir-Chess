"""Tests for Game aggregate: states, turns, player permissions, history and persistence serialization."""
import pytest

from packages.chess.constants import Color, GameResult, GameStatus, PieceType, Termination
from packages.chess.game import (
    ChessError,
    Game,
    GameAlreadyStartedError,
    GameNotActiveError,
    IllegalMoveError,
    NotAPlayerError,
    NotYourTurnError,
    PromotionRequiredError,
)


def test_game_creation_and_join():
    game = Game.create("ABC123", white_player_id=101)
    assert game.game_id == "ABC123"
    assert game.white_player_id == 101
    assert game.black_player_id is None
    assert game.status == GameStatus.WAITING

    # Creator cannot join own game
    with pytest.raises(ChessError):
        game.join(101)

    # Opponent joins
    game.join(202)
    assert game.black_player_id == 202
    assert game.status == GameStatus.ACTIVE

    # Third person cannot join started game
    with pytest.raises(GameAlreadyStartedError):
        game.join(303)


def test_turn_and_player_validation():
    game = Game.create("ABC123", white_player_id=101)
    game.join(202)

    assert game.current_turn == Color.WHITE

    # Black tries to move first -> NotYourTurnError
    with pytest.raises(NotYourTurnError):
        game.make_move(202, "e7", "e5")

    # Spectator tries to move -> NotAPlayerError
    with pytest.raises(NotAPlayerError):
        game.make_move(999, "e2", "e4")

    # White makes legal move
    rec = game.make_move(101, "e2", "e4")
    assert rec.san == "e4"
    assert rec.player == "white"
    assert game.current_turn == Color.BLACK

    # White tries to move again -> NotYourTurnError
    with pytest.raises(NotYourTurnError):
        game.make_move(101, "e4", "e5")


def test_illegal_moves():
    game = Game.create("ABC123", white_player_id=101)
    game.join(202)

    # Move piece to impossible square
    with pytest.raises(IllegalMoveError):
        game.make_move(101, "e2", "e6")

    # Move opponent's piece
    with pytest.raises(IllegalMoveError):
        game.make_move(101, "e7", "e5")


def test_promotion_handling():
    # Setup game near promotion
    game = Game.create("ABC123", white_player_id=101)
    game.join(202)
    # Put pawn on e7: set position
    from packages.chess.rules import Position
    game.position = Position.from_fen("8/4P3/8/8/8/8/8/4K2k w - - 0 1")

    # Move without specifying promotion -> PromotionRequiredError
    with pytest.raises(PromotionRequiredError):
        game.make_move(101, "e7", "e8")

    # Move with valid promotion
    rec = game.make_move(101, "e7", "e8", promotion="queen")
    assert rec.san == "e8=Q"
    assert rec.promotion == "queen"


def test_resignation():
    game = Game.create("ABC123", white_player_id=101)
    game.join(202)

    # Black resigns
    game.resign(202)
    assert game.status == GameStatus.FINISHED
    assert game.result == GameResult.WHITE
    assert game.termination == Termination.RESIGNATION

    # No more moves allowed
    with pytest.raises(GameNotActiveError):
        game.make_move(101, "e2", "e4")


def test_draw_offer_and_acceptance():
    game = Game.create("ABC123", white_player_id=101)
    game.join(202)

    # White offers draw
    ended = game.offer_draw(101)
    assert not ended
    assert game.draw_offer == Color.WHITE

    # Black accepts
    game.accept_draw(202)
    assert game.status == GameStatus.FINISHED
    assert game.result == GameResult.DRAW
    assert game.termination == Termination.AGREEMENT


def test_draw_decline():
    game = Game.create("ABC123", white_player_id=101)
    game.join(202)

    game.offer_draw(101)
    game.decline_draw(202)
    assert game.draw_offer is None
    assert game.status == GameStatus.ACTIVE


def test_serialization_roundtrip():
    game = Game.create("ABC123", white_player_id=101)
    game.join(202)
    game.make_move(101, "e2", "e4")
    game.make_move(202, "e7", "e5")

    data = game.to_dict()
    restored = Game.from_dict(data)

    assert restored.game_id == game.game_id
    assert restored.white_player_id == game.white_player_id
    assert restored.black_player_id == game.black_player_id
    assert restored.status == game.status
    assert restored.position.to_fen() == game.position.to_fen()
    assert len(restored.history) == len(game.history)
    assert restored.history[0].san == "e4"
    assert restored.history[1].san == "e5"
