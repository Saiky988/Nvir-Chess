"""Pixel-art board renderer.

Layer order: background -> full 142x142 board -> square highlights -> move indicators -> pieces.
Pieces are anchored bottom-center and may extend above their square; the canvas is padded so
nothing is clipped. Final upscaling uses nearest-neighbor only.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Iterable, Literal, Optional

from PIL import Image, ImageDraw

from packages.chess import Board, Square
from packages.chess.board import square_file, square_rank

from .board_assets import (
    BOARD_IMAGE_HEIGHT,
    BOARD_IMAGE_WIDTH,
    BOARD_OFFSET_X,
    BOARD_OFFSET_Y,
    GRID_SIZE,
    SQUARE_SIZE,
    AssetLibrary,
)

Perspective = Literal["white", "black"]

DEFAULT_OUTPUT_SCALE = 4

LAST_MOVE_COLOR = (255, 230, 90, 70)
SELECTED_COLOR = (255, 214, 0, 130)
CHECK_COLOR = (235, 50, 50, 130)
MOVE_DOT_COLOR = (30, 30, 30, 120)
CAPTURE_COLOR = (220, 50, 50, 170)
MOVE_DOT_SIZE = SQUARE_SIZE // 4
CAPTURE_CORNER = SQUARE_SIZE // 4


class RenderError(RuntimeError):
    pass


@dataclass(frozen=True)
class Highlights:
    selected: Optional[Square] = None
    destinations: frozenset[Square] = field(default_factory=frozenset)
    captures: frozenset[Square] = field(default_factory=frozenset)
    last_move: tuple[Square, ...] = ()
    check: Optional[Square] = None


def square_origin(square: Square, perspective: Perspective = "white") -> tuple[int, int]:
    """Top-left pixel of a square inside the 142x142 board image."""
    file, rank = square_file(square), square_rank(square)
    if perspective == "white":
        column, row = file, GRID_SIZE - 1 - rank
    else:
        column, row = GRID_SIZE - 1 - file, rank
    return BOARD_OFFSET_X + column * SQUARE_SIZE, BOARD_OFFSET_Y + row * SQUARE_SIZE


class BoardRenderer:
    def __init__(self, assets: AssetLibrary, output_scale: int = DEFAULT_OUTPUT_SCALE) -> None:
        if output_scale < 1:
            raise ValueError("output_scale must be >= 1")
        self.assets = assets
        self.output_scale = output_scale
        self.padding = self._compute_padding()

    def _compute_padding(self) -> tuple[int, int, int, int]:
        """(left, top, right, bottom) padding so any sprite on any square fits on the canvas."""
        left = top = right = bottom = 0
        first, last = 0, (GRID_SIZE - 1) * SQUARE_SIZE
        for sprite in self.assets.pieces.values():
            w, h = sprite.image.size
            dx = SQUARE_SIZE // 2 - sprite.anchor_x
            dy = SQUARE_SIZE - sprite.bottom_offset_px - sprite.anchor_y
            left = max(left, -(BOARD_OFFSET_X + first + dx))
            top = max(top, -(BOARD_OFFSET_Y + first + dy))
            right = max(right, BOARD_OFFSET_X + last + dx + w - BOARD_IMAGE_WIDTH)
            bottom = max(bottom, BOARD_OFFSET_Y + last + dy + h - BOARD_IMAGE_HEIGHT)
        return left, top, right, bottom

    @property
    def base_size(self) -> tuple[int, int]:
        left, top, right, bottom = self.padding
        return BOARD_IMAGE_WIDTH + left + right, BOARD_IMAGE_HEIGHT + top + bottom

    def board_origin(self) -> tuple[int, int]:
        """Where the board image's top-left corner lands on the unscaled canvas."""
        return self.padding[0], self.padding[1]

    def render_board(
        self,
        board: Board,
        theme: int = 1,
        perspective: Perspective = "white",
        highlights: Optional[Highlights] = None,
    ) -> Image.Image:
        try:
            return self._render(board, theme, perspective, highlights or Highlights())
        except Exception as exc:
            raise RenderError(f"Failed to render board: {exc}") from exc

    def render_png(
        self,
        board: Board,
        theme: int = 1,
        perspective: Perspective = "white",
        highlights: Optional[Highlights] = None,
    ) -> bytes:
        image = self.render_board(board, theme, perspective, highlights)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()

    def _render(self, board: Board, theme: int, perspective: Perspective, hl: Highlights) -> Image.Image:
        ox, oy = self.board_origin()
        canvas = Image.new("RGBA", self.base_size, (0, 0, 0, 0))
        canvas.alpha_composite(self.assets.board(theme), dest=(ox, oy))

        overlay = Image.new("RGBA", self.base_size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        def square_box(square: Square) -> tuple[int, int, int, int]:
            x, y = square_origin(square, perspective)
            return ox + x, oy + y, ox + x + SQUARE_SIZE - 1, oy + y + SQUARE_SIZE - 1

        for square in hl.last_move:
            draw.rectangle(square_box(square), fill=LAST_MOVE_COLOR)
        if hl.check is not None:
            draw.rectangle(square_box(hl.check), fill=CHECK_COLOR)
        if hl.selected is not None:
            draw.rectangle(square_box(hl.selected), fill=SELECTED_COLOR)
        canvas.alpha_composite(overlay)

        indicators = Image.new("RGBA", self.base_size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(indicators)
        for square in hl.destinations:
            x0, y0, _, _ = square_box(square)
            if square in hl.captures:
                self._draw_capture_corners(draw, x0, y0)
            else:
                start = (SQUARE_SIZE - MOVE_DOT_SIZE) // 2
                draw.rectangle(
                    (x0 + start, y0 + start, x0 + start + MOVE_DOT_SIZE - 1, y0 + start + MOVE_DOT_SIZE - 1),
                    fill=MOVE_DOT_COLOR,
                )
        canvas.alpha_composite(indicators)

        self._draw_pieces(canvas, board, perspective, ox, oy)

        if self.output_scale != 1:
            w, h = canvas.size
            canvas = canvas.resize((w * self.output_scale, h * self.output_scale), Image.Resampling.NEAREST)
        return canvas

    @staticmethod
    def _draw_capture_corners(draw: ImageDraw.ImageDraw, x0: int, y0: int) -> None:
        last = SQUARE_SIZE - 1
        for cx, cy, sx, sy in ((0, 0, 1, 1), (last, 0, -1, 1), (0, last, 1, -1), (last, last, -1, -1)):
            for i in range(CAPTURE_CORNER):
                # Small right-angle triangle in each corner, drawn pixel by pixel.
                draw.line(
                    (x0 + cx, y0 + cy + sy * i, x0 + cx + sx * (CAPTURE_CORNER - 1 - i), y0 + cy + sy * i),
                    fill=CAPTURE_COLOR,
                )

    def _draw_pieces(self, canvas: Image.Image, board: Board, perspective: Perspective, ox: int, oy: int) -> None:
        # Back-to-front (top row first) so taller sprites in front overlap the ones behind them.
        placed = sorted(board.pieces(), key=lambda item: square_origin(item[0], perspective)[1])
        for square, piece in placed:
            sprite = self.assets.piece(piece)
            x, y = square_origin(square, perspective)
            anchor_x = ox + x + SQUARE_SIZE // 2
            anchor_y = oy + y + SQUARE_SIZE - sprite.bottom_offset_px
            canvas.alpha_composite(sprite.image, dest=(anchor_x - sprite.anchor_x, anchor_y - sprite.anchor_y))


def highlights_for(
    selected: Optional[Square] = None,
    destinations: Iterable[Square] = (),
    captures: Iterable[Square] = (),
    last_move: Iterable[Square] = (),
    check: Optional[Square] = None,
) -> Highlights:
    return Highlights(selected, frozenset(destinations), frozenset(captures), tuple(last_move), check)
