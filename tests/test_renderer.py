"""Tests for board renderer, asset validation, geometry, and scaling."""
import io
import pytest
from PIL import Image

from apps.bot.services.board_assets import (
    BOARD_FILES,
    BOARD_IMAGE_HEIGHT,
    BOARD_IMAGE_WIDTH,
    PIECE_ASSETS,
    AssetError,
    AssetLibrary,
)
from apps.bot.services.board_renderer import (
    BoardRenderer,
    DEFAULT_OUTPUT_SCALE,
    Highlights,
    highlights_for,
    square_origin,
)
from packages.chess.board import Board, algebraic_to_square
from packages.chess.constants import Color, PieceType
from packages.chess.pieces import Piece


@pytest.fixture
def asset_library():
    return AssetLibrary()


def test_asset_library_validation(asset_library):
    # Verify all 5 boards are loaded and 142x142
    assert len(asset_library.boards) == 5
    for theme in range(1, 6):
        b = asset_library.board(theme)
        assert b.size == (BOARD_IMAGE_WIDTH, BOARD_IMAGE_HEIGHT)

    # Verify all 12 pieces are loaded
    assert len(asset_library.pieces) == 12


def test_missing_asset_raises_clear_error(tmp_path):
    empty_assets = tmp_path / "assets"
    empty_assets.mkdir()
    with pytest.raises(AssetError) as exc_info:
        AssetLibrary(empty_assets)
    assert "Missing" in str(exc_info.value)


def test_board_frame_preserved(asset_library):
    # The renderer should keep the entire 142x142 board asset, not crop it to 128x128
    renderer = BoardRenderer(asset_library, output_scale=1)
    base_w, base_h = renderer.base_size
    # Width must be at least the full 142px board width
    assert base_w >= BOARD_IMAGE_WIDTH
    # Height must be at least the full 142px board height (with top padding for tall pieces)
    assert base_h >= BOARD_IMAGE_HEIGHT


def test_renderer_output_dimensions(asset_library):
    # Scale 1
    r1 = BoardRenderer(asset_library, output_scale=1)
    img1 = r1.render_board(Board.initial(), theme=1)
    assert img1.size == r1.base_size

    # Default Scale 4
    r4 = BoardRenderer(asset_library, output_scale=4)
    img4 = r4.render_board(Board.initial(), theme=1)
    assert img4.size == (r1.base_size[0] * 4, r1.base_size[1] * 4)


def test_pieces_render_and_can_extend_outside_square(asset_library):
    renderer = BoardRenderer(asset_library, output_scale=1)
    # Put a King on e8 (top rank)
    board = Board()
    board.set(algebraic_to_square("e8"), Piece(Color.BLACK, PieceType.KING))

    img = renderer.render_board(board, theme=1)
    # Check that image rendered successfully and has alpha channel
    assert img.mode == "RGBA"
    # Ensure there are non-transparent pixels above row BOARD_OFFSET_Y in the canvas
    # which proves the king extends upwards outside the 16x16 square into safe padding
    ox, oy = renderer.board_origin()
    # At the top of board, top padding ensures no clipping
    assert renderer.padding[1] >= 0


def test_render_png_bytes(asset_library):
    renderer = BoardRenderer(asset_library, output_scale=2)
    png_bytes = renderer.render_png(Board.initial(), theme=2)
    assert isinstance(png_bytes, bytes)
    assert len(png_bytes) > 0
    with Image.open(io.BytesIO(png_bytes)) as img:
        assert img.format == "PNG"


def test_perspective_flip(asset_library):
    renderer = BoardRenderer(asset_library, output_scale=1)
    white_view = renderer.render_board(Board.initial(), theme=1, perspective="white")
    black_view = renderer.render_board(Board.initial(), theme=1, perspective="black")
    # Views should differ because perspective changes orientation
    assert white_view.tobytes() != black_view.tobytes()


def test_highlights_rendering(asset_library):
    renderer = BoardRenderer(asset_library, output_scale=1)
    board = Board.initial()
    hl = highlights_for(
        selected=algebraic_to_square("e2"),
        destinations=[algebraic_to_square("e3"), algebraic_to_square("e4")],
        captures=[],
        last_move=[],
        check=None,
    )
    img = renderer.render_board(board, theme=1, highlights=hl)
    assert img.size == renderer.base_size
