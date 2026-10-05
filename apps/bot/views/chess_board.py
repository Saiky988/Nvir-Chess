"""Discord UI for chess games.

The rendered PNG is display-only (Discord can't report pixel clicks). Interaction is:
public board message [Move] -> ephemeral piece select -> destination select (with a
highlighted board preview) -> optional promotion buttons -> public board message is edited.
"""
from __future__ import annotations

import functools
import io
import logging
import re
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional

import discord

from packages.chess import ChessError, Color, GameResult, GameStatus, Piece, PieceType
from packages.chess.board import algebraic_to_square, square_rank, square_to_algebraic

from ..services.board_renderer import RenderError
from ..storage import DatabaseError, StoredGame

if TYPE_CHECKING:
    from ..services.chess_service import ChessService

log = logging.getLogger(__name__)

BOARD_FILENAME = "board.png"
SELECTION_TIMEOUT = 180
SELECT_OPTION_LIMIT = 25

GLYPHS = {
    (Color.WHITE, PieceType.KING): "♔", (Color.WHITE, PieceType.QUEEN): "♕",
    (Color.WHITE, PieceType.ROOK): "♖", (Color.WHITE, PieceType.BISHOP): "♗",
    (Color.WHITE, PieceType.KNIGHT): "♘", (Color.WHITE, PieceType.PAWN): "♙",
    (Color.BLACK, PieceType.KING): "♚", (Color.BLACK, PieceType.QUEEN): "♛",
    (Color.BLACK, PieceType.ROOK): "♜", (Color.BLACK, PieceType.BISHOP): "♝",
    (Color.BLACK, PieceType.KNIGHT): "♞", (Color.BLACK, PieceType.PAWN): "♟",
}
PIECE_ORDER = [PieceType.KING, PieceType.QUEEN, PieceType.ROOK, PieceType.BISHOP, PieceType.KNIGHT, PieceType.PAWN]
TERMINATION_TEXT = {
    "checkmate": "checkmate",
    "stalemate": "stalemate",
    "resignation": "resignation",
    "agreement": "agreement",
    "timeout": "timeout",
    "insufficient_material": "insufficient material",
    "fifty_move_rule": "the fifty-move rule",
    "threefold_repetition": "threefold repetition",
    "abandoned": "abandonment",
}


def service_of(interaction: discord.Interaction) -> "ChessService":
    return interaction.client.chess_service  # type: ignore[attr-defined]


# ---- error handling ----------------------------------------------------


async def reply_ephemeral(interaction: discord.Interaction, message: str) -> None:
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException:
        log.warning("Could not deliver error message to user %s", interaction.user.id)


async def handle_interaction_error(interaction: discord.Interaction, exc: BaseException) -> None:
    if isinstance(exc, ChessError):
        await reply_ephemeral(interaction, f"⚠️ {exc}")
    elif isinstance(exc, DatabaseError):
        log.exception("Database error", exc_info=exc)
        await reply_ephemeral(interaction, "⚠️ Database error. Please try again.")
    elif isinstance(exc, RenderError):
        log.exception("Renderer error", exc_info=exc)
        await reply_ephemeral(interaction, "⚠️ Could not render the board.")
    elif isinstance(exc, discord.NotFound) and exc.code == 10062:
        log.warning("Interaction expired for user %s", interaction.user.id)
    else:
        log.exception("Unhandled interaction error", exc_info=exc)
        await reply_ephemeral(interaction, "⚠️ Something went wrong.")


def guarded(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """Wrap an interaction callback so errors become short ephemeral messages."""

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        interaction = next(a for a in args if isinstance(a, discord.Interaction))
        try:
            return await func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - mapped to user-facing message
            await handle_interaction_error(interaction, exc)

    return wrapper


# ---- embeds and public message -----------------------------------------


def mention(user_id: Optional[int]) -> str:
    return f"<@{user_id}>" if user_id else "*waiting…*"


def result_text(stored: StoredGame) -> str:
    game = stored.game
    how = TERMINATION_TEXT.get(game.termination.value, game.termination.value) if game.termination else ""
    if game.status is GameStatus.ABANDONED:
        return "Game abandoned."
    if game.result is GameResult.DRAW:
        return f"Draw by {how}."
    if game.result is not None:
        winner = Color(game.result.value)
        return f"{winner.value.title()} ({mention(game.player_id_for(winner))}) wins by {how}."
    return ""


def build_embed(stored: StoredGame, with_image: bool = True) -> discord.Embed:
    game = stored.game
    lines = [f"⬜ White: {mention(game.white_player_id)}", f"⬛ Black: {mention(game.black_player_id)}", ""]
    color = discord.Color.blurple()
    if game.status is GameStatus.WAITING:
        lines.append("Waiting for an opponent… press **Join Game**.")
    elif game.status is GameStatus.ACTIVE:
        turn = game.current_turn
        lines.append(f"Turn: **{turn.value.title()}** ({mention(game.current_player_id)})")
        if game.in_check:
            lines.append("⚠️ **Check!**")
            color = discord.Color.orange()
        if game.draw_offer:
            lines.append(f"🤝 {game.draw_offer.value.title()} offers a draw — opponent can press **Draw** to accept.")
    else:
        lines.append(f"🏁 **{result_text(stored)}**")
        color = discord.Color.dark_grey()
    last = game.last_move
    if last:
        dots = "." if last.player == Color.WHITE.value else "..."
        lines.append(f"Last move: {last.move_number}{dots} {last.san}")

    embed = discord.Embed(title=f"Chess #{game.game_id}", description="\n".join(lines), color=color)
    if with_image:
        embed.set_image(url=f"attachment://{BOARD_FILENAME}")
    embed.set_footer(text=f"Move {game.position.fullmove_number} • Theme {stored.theme}")
    return embed


def board_file(png: bytes) -> discord.File:
    return discord.File(io.BytesIO(png), filename=BOARD_FILENAME)


class GameButton(discord.ui.DynamicItem[discord.ui.Button], template=r"chess:(?P<action>join|cancel|move|draw|resign):(?P<game_id>[A-Z0-9]{6})"):
    """Persistent button on the public board message; survives bot restarts."""

    STYLES = {
        "join": ("Join Game", discord.ButtonStyle.success, "⚔️"),
        "cancel": ("Cancel", discord.ButtonStyle.secondary, None),
        "move": ("Move", discord.ButtonStyle.primary, "♟️"),
        "draw": ("Draw", discord.ButtonStyle.secondary, "🤝"),
        "resign": ("Resign", discord.ButtonStyle.danger, "🏳️"),
    }

    def __init__(self, action: str, game_id: str) -> None:
        label, style, emoji = self.STYLES[action]
        super().__init__(
            discord.ui.Button(label=label, style=style, emoji=emoji, custom_id=f"chess:{action}:{game_id}")
        )
        self.action = action
        self.game_id = game_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match[str], /):
        return cls(match["action"], match["game_id"])

    async def callback(self, interaction: discord.Interaction) -> None:
        handler = {
            "join": on_join,
            "cancel": on_cancel,
            "move": on_move,
            "draw": on_draw,
            "resign": on_resign,
        }[self.action]
        await guarded(handler)(interaction, self.game_id)


def board_view(stored: StoredGame) -> Optional[discord.ui.View]:
    game = stored.game
    if game.status is GameStatus.WAITING:
        actions = ("join", "cancel")
    elif game.status is GameStatus.ACTIVE:
        actions = ("move", "draw", "resign")
    else:
        return None
    view = discord.ui.View(timeout=None)
    for action in actions:
        view.add_item(GameButton(action, game.game_id))
    return view


async def board_message_payload(stored: StoredGame, service: "ChessService") -> dict[str, Any]:
    png = await service.render_async(stored)
    return {"embed": build_embed(stored), "attachments": [board_file(png)], "view": board_view(stored)}


async def update_board_message(
    interaction: discord.Interaction, stored: StoredGame, fallback_channel: Optional[discord.abc.Messageable] = None
) -> None:
    """Edit the game's public board message in place; repost only if it was deleted."""
    service = service_of(interaction)
    payload = await board_message_payload(stored, service)
    if stored.channel_id and stored.message_id:
        try:
            channel = interaction.client.get_channel(stored.channel_id) or await interaction.client.fetch_channel(
                stored.channel_id
            )
            await channel.get_partial_message(stored.message_id).edit(**payload)  # type: ignore[union-attr]
            return
        except (discord.NotFound, discord.Forbidden, AttributeError):
            log.warning("Board message for game %s unavailable; reposting", stored.game.game_id)
    channel = fallback_channel or interaction.channel
    if channel is None:
        return
    payload["files"] = payload.pop("attachments")
    message = await channel.send(**payload)  # type: ignore[union-attr]
    await service.set_message(stored.game.game_id, message.channel.id, message.id)


async def sync_message_pointer(interaction: discord.Interaction, stored: StoredGame) -> None:
    message = interaction.message
    if message is not None and (stored.message_id != message.id or stored.channel_id != message.channel.id):
        await service_of(interaction).set_message(stored.game.game_id, message.channel.id, message.id)
        stored.channel_id, stored.message_id = message.channel.id, message.id


# ---- public button handlers --------------------------------------------


async def on_join(interaction: discord.Interaction, game_id: str) -> None:
    service = service_of(interaction)
    stored = await service.join(game_id, interaction.user.id)
    payload = await board_message_payload(stored, service)
    await interaction.response.edit_message(**payload)
    await sync_message_pointer(interaction, stored)


async def on_cancel(interaction: discord.Interaction, game_id: str) -> None:
    service = service_of(interaction)
    stored = await service.get(game_id)
    if interaction.user.id != stored.game.white_player_id:
        raise ChessError("Only the creator can cancel this game.")
    if stored.game.status is not GameStatus.WAITING:
        raise ChessError("This game has already started.")
    stored = await service.abandon(game_id)
    await interaction.response.edit_message(embed=build_embed(stored, with_image=False), attachments=[], view=None)


async def on_move(interaction: discord.Interaction, game_id: str) -> None:
    service = service_of(interaction)
    stored = await service.get(game_id)
    pieces = service.movable_pieces(stored.game, interaction.user.id)
    await sync_message_pointer(interaction, stored)
    view = PieceSelectView(interaction, game_id, pieces)
    await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)


async def on_draw(interaction: discord.Interaction, game_id: str) -> None:
    service = service_of(interaction)
    stored, ended = await service.offer_draw(game_id, interaction.user.id)
    payload = await board_message_payload(stored, service)
    await interaction.response.edit_message(**payload)
    await sync_message_pointer(interaction, stored)
    if not ended:
        await interaction.followup.send("🤝 Draw offered. It stands until the next move.", ephemeral=True)


async def on_resign(interaction: discord.Interaction, game_id: str) -> None:
    service = service_of(interaction)
    stored = await service.get(game_id)
    if stored.game.color_of(interaction.user.id) is None:
        raise ChessError("You are not a player in this game.")
    if stored.game.status is not GameStatus.ACTIVE:
        raise ChessError("This game is not active.")
    await sync_message_pointer(interaction, stored)
    view = ResignConfirmView(interaction, game_id)
    await interaction.response.send_message("Resign this game?", view=view, ephemeral=True)


# ---- ephemeral move flow -----------------------------------------------


def piece_label(square: str, piece: Piece) -> str:
    return f"{GLYPHS[(piece.color, piece.kind)]} {piece.kind.value.title()} {square}"


class PlayerView(discord.ui.View):
    """Ephemeral view owned by one player; edits its message to 'expired' on timeout."""

    def __init__(self, origin: discord.Interaction, game_id: str) -> None:
        super().__init__(timeout=SELECTION_TIMEOUT)
        self.origin = origin
        self.game_id = game_id
        self.owner_id = origin.user.id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner_id

    async def on_timeout(self) -> None:
        try:
            await self.origin.edit_original_response(content="⌛ Selection expired.", embed=None, attachments=[], view=None)
        except discord.HTTPException:
            pass

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item[Any]) -> None:
        await handle_interaction_error(interaction, error)

    async def finish(self, interaction: discord.Interaction, content: str) -> None:
        self.stop()
        await interaction.response.edit_message(content=content, embed=None, attachments=[], view=None)

    async def go_to(self, interaction: discord.Interaction, view: "PlayerView", **kwargs: Any) -> None:
        self.stop()
        await interaction.response.edit_message(view=view, **kwargs)


class PieceSelectView(PlayerView):
    def __init__(self, origin: discord.Interaction, game_id: str, pieces: list[tuple[str, Piece]]) -> None:
        super().__init__(origin, game_id)
        ordered = sorted(pieces, key=lambda p: (PIECE_ORDER.index(p[1].kind), p[0]))
        select = discord.ui.Select(
            placeholder="Select a piece…",
            options=[discord.SelectOption(label=piece_label(sq, piece), value=sq) for sq, piece in ordered][
                :SELECT_OPTION_LIMIT
            ],
        )
        select.callback = functools.partial(self.on_select, select=select)
        self.add_item(select)

    @staticmethod
    def embed() -> discord.Embed:
        return discord.Embed(description="**Step 1/2** — choose the piece to move.", color=discord.Color.blurple())

    @guarded
    async def on_select(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        await show_destinations(self, interaction, select.values[0])


async def show_destinations(current: PlayerView, interaction: discord.Interaction, square: str) -> None:
    service = service_of(interaction)
    stored = await service.get(current.game_id)
    moves = service.destinations(stored.game, interaction.user.id, square)
    if not moves:
        raise ChessError(f"The piece on {square} has no legal moves.")
    png = await service.render_async(stored, selected=square)
    piece = stored.game.position.board.get(algebraic_to_square(square))
    view = DestinationView(current.origin, current.game_id, square, stored, moves)
    embed = discord.Embed(
        description=f"**Step 2/2** — move {piece_label(square, piece)} to…",  # type: ignore[arg-type]
        color=discord.Color.blurple(),
    )
    embed.set_image(url=f"attachment://{BOARD_FILENAME}")
    await current.go_to(interaction, view, content=None, embed=embed, attachments=[board_file(png)])


class DestinationView(PlayerView):
    def __init__(self, origin: discord.Interaction, game_id: str, from_square: str, stored: StoredGame, moves) -> None:
        super().__init__(origin, game_id)
        self.from_square = from_square
        service = service_of(origin)
        board = stored.game.position.board
        options = []
        for move in moves:
            target = move.to_square
            name = square_to_algebraic(target)
            if service.is_capture(stored.game, move):
                victim = board.get(target)
                label = f"✖ {name} — capture {victim.kind.value}" if victim else f"✖ {name} — en passant"
            else:
                label = f"→ {name}"
            options.append(discord.SelectOption(label=label, value=name))
        for index in range(0, len(options), SELECT_OPTION_LIMIT):  # queens can exceed 25 targets
            chunk = options[index : index + SELECT_OPTION_LIMIT]
            select = discord.ui.Select(placeholder="Select destination…", options=chunk, row=index // SELECT_OPTION_LIMIT)
            select.callback = functools.partial(self.on_select, select=select)
            self.add_item(select)
        back = discord.ui.Button(label="Back", style=discord.ButtonStyle.secondary, row=2)
        back.callback = self.on_back
        self.add_item(back)

    @guarded
    async def on_select(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        to_square = select.values[0]
        stored = await service_of(interaction).get(self.game_id)
        piece = stored.game.position.board.get(algebraic_to_square(self.from_square))
        last_rank = 7 if piece and piece.color is Color.WHITE else 0
        if piece and piece.kind is PieceType.PAWN and square_rank(algebraic_to_square(to_square)) == last_rank:
            view = PromotionView(self.origin, self.game_id, self.from_square, to_square)
            embed = discord.Embed(
                description=f"Promote pawn {self.from_square} → {to_square} to:", color=discord.Color.gold()
            )
            await self.go_to(interaction, view, embed=embed, attachments=[])
            return
        await commit_move(self, interaction, self.from_square, to_square)

    @guarded
    async def on_back(self, interaction: discord.Interaction) -> None:
        service = service_of(interaction)
        stored = await service.get(self.game_id)
        pieces = service.movable_pieces(stored.game, interaction.user.id)
        view = PieceSelectView(self.origin, self.game_id, pieces)
        await self.go_to(interaction, view, embed=view.embed(), attachments=[])


class PromotionView(PlayerView):
    CHOICES = (("Queen", "queen", "♛"), ("Rook", "rook", "♜"), ("Bishop", "bishop", "♝"), ("Knight", "knight", "♞"))

    def __init__(self, origin: discord.Interaction, game_id: str, from_square: str, to_square: str) -> None:
        super().__init__(origin, game_id)
        self.from_square, self.to_square = from_square, to_square
        for label, value, emoji in self.CHOICES:
            button = discord.ui.Button(label=label, emoji=emoji, style=discord.ButtonStyle.primary)
            button.callback = functools.partial(self.on_choose, promotion=value)
            self.add_item(button)

    @guarded
    async def on_choose(self, interaction: discord.Interaction, promotion: str) -> None:
        await commit_move(self, interaction, self.from_square, self.to_square, promotion)


async def commit_move(
    view: PlayerView, interaction: discord.Interaction, from_square: str, to_square: str, promotion: Optional[str] = None
) -> None:
    service = service_of(interaction)
    stored, record = await service.make_move(view.game_id, interaction.user.id, from_square, to_square, promotion)
    await view.finish(interaction, f"✅ You played **{record.san}**.")
    await update_board_message(interaction, stored)


class ResignConfirmView(PlayerView):
    @discord.ui.button(label="Confirm resign", style=discord.ButtonStyle.danger, emoji="🏳️")
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await guarded(self._confirm)(interaction)

    async def _confirm(self, interaction: discord.Interaction) -> None:
        stored = await service_of(interaction).resign(self.game_id, interaction.user.id)
        await self.finish(interaction, "🏳️ You resigned.")
        await update_board_message(interaction, stored)

    @discord.ui.button(label="Keep playing", style=discord.ButtonStyle.secondary)
    async def keep(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.finish(interaction, "Resignation cancelled.")
