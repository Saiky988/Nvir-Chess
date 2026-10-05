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

    @chess.command(name="help", description="Show chess bot commands and gameplay guide")
    async def chess_help(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(embed=build_help_embed(), ephemeral=True)

    @app_commands.command(name="help", description="Show chess bot commands and gameplay guide")
    async def global_help(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(embed=build_help_embed(), ephemeral=True)


def build_help_embed() -> discord.Embed:
    embed = discord.Embed(
        title="♟️ Discord Chess — Hướng dẫn cách chơi",
        description=(
            "Chào mừng bạn đến với **Nvir Chess**! Bot cờ vua pixel-art tương tác 1v1 trên Discord.\n"
            "Dưới đây là danh sách lệnh và hướng dẫn cách chơi."
        ),
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="📜 Danh sách lệnh (/chess)",
        value=(
            "• `/chess create [theme]` — Tạo bàn cờ mới (bạn cầm Trắng). Theme từ 1 đến 5.\n"
            "• `/chess join <game_id>` — Tham gia bàn cờ đang chờ (cầm Đen).\n"
            "• `/chess board [game_id]` — Hiển thị lại bàn cờ hiện tại vào kênh chat.\n"
            "• `/chess games` — Xem danh sách các ván cờ bạn đang tham gia.\n"
            "• `/chess draw [game_id]` — Đề nghị hòa hoặc chấp nhận hòa.\n"
            "• `/chess resign [game_id]` — Đầu hàng ván cờ.\n"
            "• `/chess help` — Hiển thị hướng dẫn này."
        ),
        inline=False,
    )
    embed.add_field(
        name="🎮 Cách di chuyển quân cờ",
        value=(
            "**1. Tham gia:** Người chơi thứ hai bấm nút **⚔️ Join Game** trên tin nhắn bàn cờ.\n"
            "**2. Chọn quân:** Khi đến lượt, bấm nút **♟️ Move** ➔ menu chọn quân cờ khả dĩ.\n"
            "**3. Chọn ô đến:** Bot hiển thị ảnh xem trước các ô hợp lệ ➔ chọn ô muốn đến.\n"
            "**4. Phong cấp:** Khi tốt đến hàng cuối, chọn 1 trong 4 quân: Hậu, Xe, Tượng, Mã.\n"
            "**5. Nhập thành:** Chọn Vua đi 2 ô về hướng Xe tương ứng.\n"
            "**6. Bắt tốt qua đường (En Passant):** Tự động phát hiện khi đối thủ vừa nhảy tốt 2 ô."
        ),
        inline=False,
    )
    embed.add_field(
        name="🎨 Giao diện & Chủ đề (Themes)",
        value="Có 5 theme bàn cờ pixel-art: chọn khi tạo ván cờ bằng `/chess create theme:1..5` (mặc định là theme 1).",
        inline=False,
    )
    embed.set_footer(text="Nvir Chess • Pixel Art Edition • nvirya.com")
    return embed


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ChessCog(bot))
