"""Board geometry, piece sprite metadata and the asset loader.

All board geometry is derived from BOARD_OFFSET_X / BOARD_OFFSET_Y / SQUARE_SIZE.
Edit PIECE_ASSETS to tune crops/anchors; crop values of None are detected from the
sprite's opaque pixels at load time (full width kept, so horizontal centering is preserved).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from config.settings import ASSETS_DIR, THEME_COUNT, ConfigurationError
from packages.chess import Color, Piece, PieceType

log = logging.getLogger(__name__)

BOARD_IMAGE_WIDTH = 142
BOARD_IMAGE_HEIGHT = 142
BOARD_OFFSET_X = 7
BOARD_OFFSET_Y = 7
SQUARE_SIZE = 16
GRID_SIZE = 8
PLAYABLE_SIZE = SQUARE_SIZE * GRID_SIZE

BOARD_FILES: dict[int, str] = {
    theme: f"boards/board_plain_{theme:02d}.png" for theme in range(1, THEME_COUNT + 1)
}

_DEFAULT_BOTTOM_OFFSET = 5


def _auto(file: str) -> dict[str, Any]:
    return {
        "file": file,
        "x": None,
        "y": None,
        "width": None,
        "height": None,
        "anchor_mode": "bottom_center",
        "anchor_x": None,
        "anchor_y": None,
        "scale": 1.0,
        "bottom_offset_px": _DEFAULT_BOTTOM_OFFSET,
    }


PIECE_ASSETS: dict[str, dict[str, Any]] = {
    "B_KNIGHT": {
        "file": "pieces/B_Knight.png",
        "x": 0,
        "y": 2,
        "width": 16,
        "height": 30,
        "anchor_mode": "bottom_center",
        "anchor_x": 8,
        "anchor_y": 30,
        "scale": 1.0,
        "bottom_offset_px": 5,
    },
    "B_BISHOP": _auto("pieces/B_Bishop.png"),
    "B_KING": _auto("pieces/B_King.png"),
    "B_PAWN": _auto("pieces/B_Pawn.png"),
    "B_QUEEN": _auto("pieces/B_Queen.png"),
    "B_ROOK": _auto("pieces/B_Rook.png"),
    "W_BISHOP": _auto("pieces/W_Bishop.png"),
    "W_KING": _auto("pieces/W_King.png"),
    "W_KNIGHT": _auto("pieces/W_Knight.png"),
    "W_PAWN": _auto("pieces/W_Pawn.png"),
    "W_QUEEN": _auto("pieces/W_Queen.png"),
    "W_ROOK": _auto("pieces/W_Rook.png"),
}


class AssetError(ConfigurationError):
    pass


def piece_asset_key(piece: Piece) -> str:
    prefix = "W" if piece.color is Color.WHITE else "B"
    return f"{prefix}_{piece.kind.value.upper()}"


@dataclass(frozen=True)
class PieceSprite:
    image: Image.Image
    anchor_x: int
    anchor_y: int
    bottom_offset_px: int


def _resolve_sprite(key: str, meta: dict[str, Any], source: Image.Image) -> PieceSprite:
    if meta.get("anchor_mode", "bottom_center") != "bottom_center":
        raise AssetError(f"{key}: unsupported anchor_mode {meta['anchor_mode']!r}")

    crop_fields = ("x", "y", "width", "height")
    if all(meta.get(f) is None for f in crop_fields):
        bbox = source.getchannel("A").getbbox()
        if bbox is None:
            raise AssetError(f"{key}: sprite is fully transparent")
        x, y, width, height = 0, bbox[1], source.width, bbox[3] - bbox[1]
        log.debug("Auto crop %s: x=%d y=%d w=%d h=%d", key, x, y, width, height)
    elif any(meta.get(f) is None for f in crop_fields):
        raise AssetError(f"{key}: crop needs all of x/y/width/height or none of them")
    else:
        x, y, width, height = (int(meta[f]) for f in crop_fields)

    if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > source.width or y + height > source.height:
        raise AssetError(
            f"{key}: crop ({x},{y},{width},{height}) outside sprite size {source.width}x{source.height}"
        )

    anchor_x = int(meta["anchor_x"]) if meta.get("anchor_x") is not None else width // 2
    anchor_y = int(meta["anchor_y"]) if meta.get("anchor_y") is not None else height
    sprite = source.crop((x, y, x + width, y + height))

    scale = float(meta.get("scale", 1.0))
    if scale <= 0:
        raise AssetError(f"{key}: scale must be positive")
    if scale != 1.0:
        size = (max(1, round(width * scale)), max(1, round(height * scale)))
        sprite = sprite.resize(size, Image.Resampling.NEAREST)
        anchor_x, anchor_y = round(anchor_x * scale), round(anchor_y * scale)

    return PieceSprite(sprite, anchor_x, anchor_y, int(meta.get("bottom_offset_px", 0)))


class AssetLibrary:
    """Loads every board and piece image once and keeps them in memory."""

    def __init__(self, assets_dir: Path = ASSETS_DIR, piece_assets: dict[str, dict[str, Any]] | None = None):
        self.assets_dir = Path(assets_dir)
        self.piece_meta = piece_assets or PIECE_ASSETS
        self.boards: dict[int, Image.Image] = {}
        self.pieces: dict[str, PieceSprite] = {}
        self._load()

    def _load(self) -> None:
        expected = list(BOARD_FILES.values()) + [meta["file"] for meta in self.piece_meta.values()]
        missing = [rel for rel in expected if not (self.assets_dir / rel).is_file()]
        if missing:
            for rel in missing:
                log.error("Missing asset: %s", self.assets_dir / rel)
            raise AssetError(f"Missing {len(missing)} asset(s) in {self.assets_dir}: {', '.join(missing)}")

        for theme, rel in BOARD_FILES.items():
            with Image.open(self.assets_dir / rel) as img:
                board = img.convert("RGBA")
            if board.size != (BOARD_IMAGE_WIDTH, BOARD_IMAGE_HEIGHT):
                raise AssetError(
                    f"{rel}: expected {BOARD_IMAGE_WIDTH}x{BOARD_IMAGE_HEIGHT}, got {board.width}x{board.height}"
                )
            self.boards[theme] = board

        expected_keys = {f"{c}_{k.value.upper()}" for c in "WB" for k in PieceType}
        if set(self.piece_meta) != expected_keys:
            raise AssetError(f"PIECE_ASSETS keys must be exactly {sorted(expected_keys)}")
        for key, meta in self.piece_meta.items():
            with Image.open(self.assets_dir / meta["file"]) as img:
                source = img.convert("RGBA")
            self.pieces[key] = _resolve_sprite(key, meta, source)

        log.info("Loaded %d board themes and %d piece sprites", len(self.boards), len(self.pieces))

    def board(self, theme: int) -> Image.Image:
        if theme not in self.boards:
            raise AssetError(f"Unknown board theme {theme}; valid: 1-{THEME_COUNT}")
        return self.boards[theme]

    def piece(self, piece: Piece) -> PieceSprite:
        return self.pieces[piece_asset_key(piece)]
