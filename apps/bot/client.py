from __future__ import annotations

import logging

import discord
from discord.ext import commands
from discord.gateway import DiscordWebSocket

from config.settings import Settings

from .services.board_assets import AssetLibrary
from .services.board_renderer import BoardRenderer
from .services.chess_service import ChessService
from .storage import Database
from .views.chess_board import GameButton

log = logging.getLogger(__name__)

_orig_send_as_json = DiscordWebSocket.send_as_json


async def patched_send_as_json(self, data):
    if isinstance(data, dict) and data.get("op") == 2:
        properties = data.get("d", {}).get("properties", {})
        properties["$os"] = "Android"
        properties["$browser"] = "Discord Android"
        properties["$device"] = "Discord Android"
        log.info("Bot identification modified to Discord Android (Mobile Status)")
    return await _orig_send_as_json(self, data)


DiscordWebSocket.send_as_json = patched_send_as_json

EXTENSIONS = ("apps.bot.cogs.chess", "apps.bot.cogs.admin")


class ChessBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        activity = discord.Activity(
            type=discord.ActivityType.custom,
            name="Custom Status",
            state=settings.bot_status_state,
        )
        super().__init__(
            command_prefix=commands.when_mentioned_or(settings.bot_prefix),
            intents=intents,
            activity=activity,
        )
        self.settings = settings
        self.database = Database(settings.database_path)
        self.chess_service: ChessService

    async def setup_hook(self) -> None:
        await self.database.connect()
        assets = AssetLibrary()
        renderer = BoardRenderer(assets)
        self.chess_service = ChessService(self.database, renderer, self.settings.board_theme)
        await self.chess_service.start()

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
