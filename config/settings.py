"""Settings loaded from environment variables (optionally via a .env file)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"
THEME_COUNT = 5
LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}


class ConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    discord_token: str
    database_path: Path
    bot_prefix: str
    board_theme: int
    log_level: str
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    bot_status_state: str = "nvirya.com ..."


def _resolve_path(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env")

    theme_raw = os.getenv("BOARD_THEME", "1").strip()
    try:
        theme = int(theme_raw)
    except ValueError as exc:
        raise ConfigurationError(f"BOARD_THEME must be an integer, got {theme_raw!r}") from exc
    if not 1 <= theme <= THEME_COUNT:
        raise ConfigurationError(f"BOARD_THEME must be between 1 and {THEME_COUNT}")

    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    if log_level not in LOG_LEVELS:
        raise ConfigurationError(f"LOG_LEVEL must be one of {sorted(LOG_LEVELS)}")

    port_raw = os.getenv("PORT", os.getenv("API_PORT", "8000")).strip()
    try:
        api_port = int(port_raw)
    except ValueError as exc:
        raise ConfigurationError(f"PORT must be an integer, got {port_raw!r}") from exc
    if not (1 <= api_port <= 65535):
        raise ConfigurationError(f"PORT must be between 1 and 65535, got {api_port}")

    api_host = os.getenv("HOST", os.getenv("API_HOST", "0.0.0.0")).strip() or "0.0.0.0"
    bot_status_state = os.getenv("BOT_STATUS_STATE", "nvirya.com ...").strip() or "nvirya.com ..."

    return Settings(
        discord_token=os.getenv("DISCORD_TOKEN", "").strip(),
        database_path=_resolve_path(os.getenv("DATABASE_PATH", "data/chess.db").strip()),
        bot_prefix=os.getenv("BOT_PREFIX", "!").strip() or "!",
        board_theme=theme,
        log_level=log_level,
        api_host=api_host,
        api_port=api_port,
        bot_status_state=bot_status_state,
    )
