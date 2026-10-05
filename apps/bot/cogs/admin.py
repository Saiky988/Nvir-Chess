"""Admin utilities: command sync and abandoning stuck games."""
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from ..services.chess_service import ChessService
from ..views.chess_board import handle_interaction_error, update_board_message

log = logging.getLogger(__name__)


class AdminCog(commands.Cog):
    admin = app_commands.Group(
        name="chessadmin",
        description="Chess bot administration",
        default_permissions=discord.Permissions(manage_guild=True),
        guild_only=True,
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def service(self) -> ChessService:
        return self.bot.chess_service  # type: ignore[attr-defined]

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        await handle_interaction_error(interaction, getattr(error, "original", error))

    @admin.command(name="abandon", description="Mark a game as abandoned")
    @app_commands.describe(game_id="Game id, e.g. ABC123")
    async def abandon(self, interaction: discord.Interaction, game_id: str) -> None:
        await interaction.response.defer(ephemeral=True)
        stored = await self.service.abandon(game_id)
        log.info("Admin %s abandoned game %s", interaction.user.id, stored.game.game_id)
        await update_board_message(interaction, stored)
        await interaction.followup.send(f"Game **#{stored.game.game_id}** abandoned.", ephemeral=True)

    @commands.command(name="sync")
    @commands.is_owner()
    async def sync(self, ctx: commands.Context) -> None:
        """Owner-only: re-sync slash commands globally."""
        synced = await self.bot.tree.sync()
        log.info("Synced %d application command(s) on request", len(synced))
        await ctx.reply(f"Synced {len(synced)} command(s).")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCog(bot))
