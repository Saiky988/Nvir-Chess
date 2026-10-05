"""Bot client: wires database, assets, renderer and service together on startup."""
from __future__ import annotations

import logging

import discord
from discord.ext import commands

from config.settings import Settings

from .services.board_assets import AssetLibrary
from .services.board_renderer import BoardRenderer
from .services.chess_service import ChessService
from .storage import Database
from .views.chess_board import GameButton

log = logging.getLogger(__name__)

EXTENSIONS = ("apps.bot.cogs.chess", "apps.bot.cogs.admin")


class ChessBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()  # no privileged intents required
        super().__init__(command_prefix=commands.when_mentioned_or(settings.bot_prefix), intents=intents)
        self.settings = settings
        self.database = Database(settings.database_path)
        self.chess_service: ChessService

    async def setup_hook(self) -> None:
        await self.database.connect()
        assets = AssetLibrary()
        renderer = BoardRenderer(assets)
        self.chess_service = ChessService(self.database, renderer, self.settings.board_theme)
        await self.chess_service.start()

        # Persistent buttons on existing board messages keep working after a restart.
        self.add_dynamic_items(GameButton)

        for extension in EXTENSIONS:
            await self.load_extension(extension)
            log.info("Loaded extension %s", extension)

        synced = await self.tree.sync()
        log.info("Registered %d application command(s): %s", len(synced), ", ".join(c.name for c in synced))

    async def on_ready(self) -> None:
        log.info("Logged in as %s (id=%s) in %d guild(s)", self.user, self.user and self.user.id, len(self.guilds))

    async def close(self) -> None:
        await super().close()
        await self.database.close()
        log.info("Shutdown complete")
