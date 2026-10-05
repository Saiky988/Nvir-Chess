"""Slash commands for chess. Thin layer: parse input -> ChessService -> Discord response."""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from packages.chess import GameStatus

from ..services.chess_service import ChessService
from ..views.chess_board import board_message_payload, handle_interaction_error, update_board_message

log = logging.getLogger(__name__)

GAME_ID_HELP = "Game id, e.g. ABC123 (optional if you have one active game)"


class ChessCog(commands.Cog):
    chess = app_commands.Group(name="chess", description="Play chess against another member")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def service(self) -> ChessService:
        return self.bot.chess_service  # type: ignore[attr-defined]

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        await handle_interaction_error(interaction, getattr(error, "original", error))

    @chess.command(name="create", description="Create a game; you play White")
    @app_commands.describe(theme="Board theme (1-5)")
    async def create(self, interaction: discord.Interaction, theme: Optional[app_commands.Range[int, 1, 5]] = None) -> None:
        stored = await self.service.create_game(
            interaction.user.id, theme, interaction.guild_id, interaction.channel_id
        )
        payload = await board_message_payload(stored, self.service)
        payload["files"] = payload.pop("attachments")
        await interaction.response.send_message(**payload)
        message = await interaction.original_response()
        await self.service.set_message(stored.game.game_id, message.channel.id, message.id)

    @chess.command(name="join", description="Join a waiting game as Black")
    @app_commands.describe(game_id="Game id, e.g. ABC123")
    async def join(self, interaction: discord.Interaction, game_id: str) -> None:
        await interaction.response.defer(ephemeral=True)
        stored = await self.service.join(game_id, interaction.user.id)
        await update_board_message(interaction, stored)
        await interaction.followup.send(f"⚔️ You joined **#{stored.game.game_id}** as Black.", ephemeral=True)

    @chess.command(name="resign", description="Resign a game")
    @app_commands.describe(game_id=GAME_ID_HELP)
    async def resign(self, interaction: discord.Interaction, game_id: Optional[str] = None) -> None:
        await interaction.response.defer(ephemeral=True)
        stored = await self.service.resolve_player_game(interaction.user.id, game_id)
        stored = await self.service.resign(stored.game.game_id, interaction.user.id)
        await update_board_message(interaction, stored)
        await interaction.followup.send(f"🏳️ You resigned **#{stored.game.game_id}**.", ephemeral=True)

    @chess.command(name="draw", description="Offer a draw, or accept your opponent's offer")
    @app_commands.describe(game_id=GAME_ID_HELP)
    async def draw(self, interaction: discord.Interaction, game_id: Optional[str] = None) -> None:
        await interaction.response.defer(ephemeral=True)
        stored = await self.service.resolve_player_game(interaction.user.id, game_id)
        stored, ended = await self.service.offer_draw(stored.game.game_id, interaction.user.id)
        await update_board_message(interaction, stored)
        text = "🤝 Draw agreed." if ended else "🤝 Draw offered. It stands until the next move."
        await interaction.followup.send(text, ephemeral=True)

    @chess.command(name="board", description="Re-post a game's board in this channel")
    @app_commands.describe(game_id=GAME_ID_HELP)
    async def board(self, interaction: discord.Interaction, game_id: Optional[str] = None) -> None:
        stored = await self.service.resolve_player_game(interaction.user.id, game_id)
        payload = await board_message_payload(stored, self.service)
        payload["files"] = payload.pop("attachments")
        await interaction.response.send_message(**payload)
        if not stored.game.is_over:
            message = await interaction.original_response()
            await self.service.set_message(stored.game.game_id, message.channel.id, message.id)

    @chess.command(name="games", description="List your waiting and active games")
    async def games(self, interaction: discord.Interaction) -> None:
        games = await self.service.games_for(interaction.user.id)
        if not games:
            await interaction.response.send_message("You have no open games.", ephemeral=True)
            return
        lines = []
        for stored in games:
            game = stored.game
            if game.status is GameStatus.WAITING:
                state = "waiting for opponent"
            else:
                yours = game.current_player_id == interaction.user.id
                state = "**your turn**" if yours else "opponent's turn"
            color = game.color_of(interaction.user.id)
            lines.append(f"`{game.game_id}` — {color.value if color else '?'} — {state}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ChessCog(bot))
