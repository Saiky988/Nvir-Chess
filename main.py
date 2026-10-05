"""Root entry point for shared hosting (Pterodactyl, Wispbyte, cPanel, Docker, VPS).

Default behavior: starts the Discord bot.
If ENABLE_API=true is set in .env, starts both the bot and the FastAPI health/web server concurrently.
"""
from __future__ import annotations

import asyncio
import os
import sys

from apps.bot.main import main as run_bot


async def _run_combined() -> None:
    import uvicorn
    from config.settings import load_settings
    from apps.bot.client import ChessBot
    from apps.api.main import app

    settings = load_settings()
    bot = ChessBot(settings)

    config = uvicorn.Config(app=app, host=settings.api_host, port=settings.api_port, log_level="warning")
    server = uvicorn.Server(config)

    # Run both bot and uvicorn concurrently
    await asyncio.gather(
        bot.start(settings.discord_token),
        server.serve(),
    )


def main() -> None:
    # Check if combined mode is requested
    enable_api = os.getenv("ENABLE_API", "").strip().lower() in ("1", "true", "yes") or "--with-api" in sys.argv
    if enable_api:
        from apps.bot.main import setup_logging
        from config.settings import load_settings

        settings = load_settings()
        setup_logging(settings.log_level)
        asyncio.run(_run_combined())
    else:
        run_bot()


if __name__ == "__main__":
    main()
