# Discord Chess Bot

A clean, production-ready Discord Chess Bot built with Python 3.11, discord.py 2.x, Pillow, and SQLite. Features 2.5D pixel-art board rendering, interactive UI-driven gameplay, and concurrent game management.

---

## Features

- **1v1 Chess**: Play head-to-head against any Discord server member.
- **Pixel-Art Board Rendering**: Custom Pillow-based board renderer preserving full 142×142 board assets, frames, and borders with 5 selectable themes.
- **2.5D Sprite Anchoring**: Pieces use bottom-center alignment (`anchor_x`, `anchor_y`, `bottom_offset_px`) allowing sprites to extend upwards outside the 16×16 grid without clipping.
- **Full Standard Chess Rules**:
  - Pawn double-advance, diagonal capture, en passant
  - Knight, Bishop, Rook, Queen, and King moves
  - Castling (kingside and queenside) with attack-path checks
  - Pawn promotion (Queen, Rook, Bishop, Knight) via Discord buttons
  - Absolute pins & check validation (cannot move into check)
  - Checkmate, stalemate, insufficient material, 3-fold repetition, 50-move rule
- **Discord Interaction Flow**:
  - Slash commands (`/chess create`, `/chess join`, `/chess resign`, `/chess draw`, `/chess board`, `/chess games`)
  - Ephemeral Piece Selection → Ephemeral Destination Selection with visual board highlights
  - In-place message edits for public board updates (no channel spam)
  - Persistent Dynamic buttons surviving bot restarts
- **SQLite Persistence**:
  - Async persistence using `aiosqlite` with WAL mode
  - Stores FEN positions, JSON move history, timestamps, and Discord message references
  - Automatic game recovery and session restoration after bot restarts
- **Extensible Architecture**: Clean separation between standalone `packages/chess` core, Discord UI, and storage. Includes a minimal FastAPI health endpoint foundation.

---

## Architecture Overview

```
discord-chess/
├── apps/
│   ├── bot/
│   │   ├── cogs/
│   │   │   ├── chess.py          # /chess slash commands
│   │   │   └── admin.py          # /chessadmin abandon & sync
│   │   ├── services/
│   │   │   ├── board_assets.py   # Asset library & 2.5D sprite metadata
│   │   │   ├── board_renderer.py # Pillow canvas, highlights & pixel-art renderer
│   │   │   └── chess_service.py  # Concurrency locks, orchestration & cache
│   │   ├── storage/
│   │   │   └── database.py       # aiosqlite SQLite persistence
│   │   ├── views/
│   │   │   └── chess_board.py    # Persistent & ephemeral Discord UI views
│   │   ├── client.py             # ChessBot client & startup lifecycle
│   │   └── main.py               # Bot entry point
│   └── api/
│       ├── main.py               # FastAPI application
│       └── routes/
│           └── health.py         # GET /api/v1/health
├── packages/
│   └── chess/                    # Pure Python core chess engine (no discord.py)
│       ├── board.py              # 8x8 Board & coordinate conversions (a1..h8)
│       ├── constants.py          # Enums & geometry offsets
│       ├── game.py               # Game aggregate, permissions & history
│       ├── moves.py              # Move dataclass, rays & attack detection
│       ├── notation.py           # Standard Algebraic Notation (SAN)
│       ├── pieces.py             # Piece dataclass & FEN symbols
│       └── rules.py              # Legal moves, castling, checkmate, stalemate
├── assets/
│   ├── boards/                   # 5 board assets (142x142 pixel art)
│   └── pieces/                   # 12 piece sprites (16x32 pixel art)
├── config/
│   └── settings.py               # Environment configuration & validation
├── data/                         # SQLite database storage (git-ignored)
└── tests/                        # Comprehensive pytest suite
```

---

## Requirements

- Python 3.11+
- Discord Bot Token with Application Commands permissions

---

## Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Saiky988/Nvir-Chess.git
   cd Nvir-Chess
   ```

2. **Create and activate a virtual environment**:
   ```bash
   # Windows PowerShell
   python -m venv .venv
   .venv\Scripts\Activate.ps1

   # Linux / macOS
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -e ".[dev]"
   ```

---

## Configuration (`.env`)

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Edit `.env` and fill in your Discord Bot Token:

```dotenv
# Discord Bot Token from Discord Developer Portal
DISCORD_TOKEN=your_bot_token_here

# Database path (relative to repo root or absolute)
DATABASE_PATH=data/chess.db

# Command prefix for owner utilities
BOT_PREFIX=!

# Default board theme (1-5)
BOARD_THEME=1

# Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
LOG_LEVEL=INFO
```

---

## Asset Structure

All board and piece assets are located in `assets/`:

- `assets/boards/`:
  - `board_plain_01.png` through `board_plain_05.png` (Dimensions: 142×142 px)
  - Playable grid: 128×128 px, offset X: 7 px, offset Y: 7 px, square size: 16×16 px.
  - Border and coordinate labels are preserved intact.
- `assets/pieces/`:
  - `W_King.png`, `W_Queen.png`, `W_Rook.png`, `W_Bishop.png`, `W_Knight.png`, `W_Pawn.png`
  - `B_King.png`, `B_Queen.png`, `B_Rook.png`, `B_Bishop.png`, `B_Knight.png`, `B_Pawn.png`
  - Sprites are 16×32 px with 2.5D height. Centered and anchored by bottom edge with safe padding.

---

## Running the Project

### 1. Run Discord Bot

```bash
python -m apps.bot.main
```

### 2. Run API Server

```bash
uvicorn apps.api.main:app --host 0.0.0.0 --port 8000
```

Verify health check:
```bash
curl http://localhost:8000/api/v1/health
# Response: {"status":"ok"}
```

### 3. Run Tests

```bash
pytest -v
```

---

## Discord Setup & Commands

### Discord Application Setup

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Create an Application and add a Bot.
3. In **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Send Messages`, `Attach Files`, `Embed Links`, `Use External Emojis`, `Read Message History`
4. Copy the invite URL and add the bot to your test server.

### Commands

| Command | Description |
|---|---|
| `/chess create [theme]` | Creates a new game. The creator plays White. Optional theme (1-5). |
| `/chess join <game_id>` | Joins a waiting game as Black. Can also join by clicking the button. |
| `/chess resign [game_id]` | Resigns the current game. |
| `/chess draw [game_id]` | Offers a draw or accepts an opponent's pending draw offer. |
| `/chess board [game_id]` | Re-posts the game's current board in the active channel. |
| `/chess games` | Lists all your waiting and active games. |
| `/chessadmin abandon <game_id>` | Server admins (`Manage Server`) can abandon stuck games. |
| `!sync` | Bot owner only: triggers immediate global command tree sync. |

---

## Gameplay Flow

1. **Create Game**: Player A runs `/chess create`. Bot sends the board message with **Join Game** and **Cancel** buttons.
2. **Join Game**: Player B clicks **Join Game**. Bot assigns Black, updates the board to active, and enables **Move**, **Draw**, and **Resign** buttons.
3. **Move Piece**:
   - Player clicks **Move** (or `/chess move`).
   - Bot opens an ephemeral menu showing available pieces to move.
   - Player picks a piece (e.g. `e2`).
   - Bot renders a highlighted destination preview showing legal moves and capture targets.
   - Player selects the target square (e.g. `e4`).
   - If a pawn reaches the 8th rank, a promotion selection view appears (Queen, Rook, Bishop, Knight).
   - Public board message edits in place with the newly rendered position and updated turn status.
4. **End Game**: When checkmate, stalemate, resignation, or draw occurs, the board displays the final position and game outcome.

---

## License

This project is licensed under the [MIT License](LICENSE).
