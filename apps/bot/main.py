"""Entry point: python -m apps.bot.main"""
from __future__ import annotations

import logging
import sys

from config.settings import ConfigurationError, load_settings


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.getLogger("discord.http").setLevel(logging.WARNING)


def main() -> None:
    try:
        settings = load_settings()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)

    setup_logging(settings.log_level)
    log = logging.getLogger("apps.bot")
    if not settings.discord_token:
        log.error("DISCORD_TOKEN is not set. Copy .env.example to .env and fill it in.")
        sys.exit(1)

    from .client import ChessBot
    from .storage import DatabaseError

    log.info("Starting chess bot (database=%s, theme=%d)", settings.database_path, settings.board_theme)
    bot = ChessBot(settings)
    try:
        bot.run(settings.discord_token, log_handler=None)
    except (ConfigurationError, DatabaseError) as exc:
        log.error("Startup failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
