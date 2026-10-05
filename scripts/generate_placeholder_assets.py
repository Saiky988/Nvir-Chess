"""Generate PLACEHOLDER pixel-art assets with the exact geometry the renderer expects.

Use only when the real art is not available. Existing files are never overwritten
unless --force is passed. Replace the outputs with the real assets for production.

    python scripts/generate_placeholder_assets.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from apps.bot.services.board_assets import (  # noqa: E402
    BOARD_FILES,
    BOARD_IMAGE_HEIGHT,
    BOARD_IMAGE_WIDTH,
    BOARD_OFFSET_X,
    BOARD_OFFSET_Y,
    GRID_SIZE,
    PIECE_ASSETS,
    SQUARE_SIZE,
)
from config.settings import ASSETS_DIR  # noqa: E402

SPRITE_SIZE = (16, 32)

# (frame, frame_shadow, light_square, dark_square)
PALETTES = {
    1: ((110, 72, 44), (74, 46, 28), (238, 216, 176), (176, 124, 82)),
    2: ((60, 70, 60), (38, 45, 38), (226, 232, 206), (118, 150, 86)),
    3: ((58, 64, 92), (36, 40, 60), (214, 222, 236), (110, 128, 168)),
    4: ((92, 52, 60), (60, 32, 38), (240, 218, 214), (176, 104, 110)),
    5: ((70, 70, 70), (44, 44, 44), (210, 210, 210), (120, 120, 120)),
}

SHAPES = {
    "Pawn": [("ellipse", (5, 14, 10, 19)), ("rect", (6, 19, 9, 25))],
    "Rook": [
        ("rect", (4, 10, 5, 12)), ("rect", (7, 10, 8, 12)), ("rect", (10, 10, 11, 12)),
        ("rect", (4, 12, 11, 15)), ("rect", (5, 15, 10, 25)),
    ],
    "Bishop": [("rect", (7, 7, 8, 9)), ("ellipse", (5, 9, 10, 18)), ("rect", (6, 18, 9, 25))],
    "Knight": [("poly", [(5, 25), (5, 16), (4, 13), (6, 9), (9, 8), (12, 12), (12, 15), (9, 14), (10, 25)])],
    "Queen": [
        ("rect", (4, 6, 5, 9)), ("rect", (7, 4, 8, 9)), ("rect", (10, 6, 11, 9)),
        ("rect", (4, 9, 11, 13)), ("poly", [(4, 13), (11, 13), (10, 25), (5, 25)]),
    ],
    "King": [
        ("rect", (7, 2, 8, 7)), ("rect", (5, 4, 10, 5)), ("rect", (4, 8, 11, 12)),
        ("poly", [(4, 12), (11, 12), (10, 25), (5, 25)]),
    ],
}
BASE = [("rect", (4, 25, 11, 26)), ("rect", (3, 27, 12, 30))]

COLORS = {"W": ((236, 230, 214), (36, 28, 28)), "B": ((64, 56, 74), (12, 8, 14))}


def make_board(palette) -> Image.Image:
    frame, shadow, light, dark = palette
    img = Image.new("RGBA", (BOARD_IMAGE_WIDTH, BOARD_IMAGE_HEIGHT), frame + (255,))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, BOARD_IMAGE_WIDTH - 1, BOARD_IMAGE_HEIGHT - 1), outline=shadow + (255,))
    inner = (BOARD_OFFSET_X - 1, BOARD_OFFSET_Y - 1,
             BOARD_OFFSET_X + GRID_SIZE * SQUARE_SIZE, BOARD_OFFSET_Y + GRID_SIZE * SQUARE_SIZE)
    draw.rectangle(inner, outline=shadow + (255,))
    for row in range(GRID_SIZE):
        for col in range(GRID_SIZE):
            color = dark if (row + col) % 2 else light
            x, y = BOARD_OFFSET_X + col * SQUARE_SIZE, BOARD_OFFSET_Y + row * SQUARE_SIZE
            draw.rectangle((x, y, x + SQUARE_SIZE - 1, y + SQUARE_SIZE - 1), fill=color + (255,))
    return img


def make_piece(kind: str, side: str) -> Image.Image:
    mask = Image.new("L", SPRITE_SIZE, 0)
    draw = ImageDraw.Draw(mask)
    for shape, coords in SHAPES[kind] + BASE:
        if shape == "rect":
            draw.rectangle(coords, fill=255)
        elif shape == "ellipse":
            draw.ellipse(coords, fill=255)
        else:
            draw.polygon(coords, fill=255)
    outline_mask = mask.filter(ImageFilter.MaxFilter(3))
    fill, outline = COLORS[side]
    img = Image.new("RGBA", SPRITE_SIZE, (0, 0, 0, 0))
    img.paste(outline + (255,), mask=outline_mask)
    img.paste(fill + (255,), mask=mask)
    return img


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="overwrite existing files")
    parser.add_argument("--out", type=Path, default=ASSETS_DIR)
    args = parser.parse_args()

    outputs: dict[str, Image.Image] = {rel: make_board(PALETTES[t]) for t, rel in BOARD_FILES.items()}
    for meta in PIECE_ASSETS.values():
        name = Path(meta["file"]).stem  # e.g. W_Knight
        side, kind = name.split("_")
        outputs[meta["file"]] = make_piece(kind, side)

    for rel, img in outputs.items():
        path = args.out / rel
        if path.exists() and not args.force:
            print(f"skip (exists): {path}")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(path)
        print(f"wrote: {path}")


if __name__ == "__main__":
    main()
