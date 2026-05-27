# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

金铲铲智能助手 (JinChanChan Smart Assistant) — a Python desktop app that automates gameplay in the Chinese TFT mobile game (金铲铲之战). It connects to an Android emulator via ADB, captures screenshots, recognizes game state via computer vision, makes buy/position/level-up decisions, and executes actions through ADB taps and swipes. Supports semi-auto (user confirms) and fully-auto modes.

## Commands

```bash
# Run the app
python main.py

# Install dependencies
pip install -r requirements.txt
```

No test suite, linter, or CI/CD is configured yet. DESIGN.md mentions PyInstaller for future `.exe` packaging.

## Architecture

**Plugin-based with event-driven communication.** Three core abstractions in `core/`:

- **EventBus** (`core/event_bus.py`) — synchronous pub/sub (`on`/`off`/`emit`). Exceptions in handlers are logged, not propagated.
- **PluginManager** (`core/plugin_manager.py`) — registers plugin classes, drives `init()` → `start()` → `stop()` lifecycle.
- **ConfigManager** (`core/config_manager.py`) — loads `config.yaml`, supports dot-path access (`config.get("adb.host")`), manages ADB connection profiles (CRUD).

**Core pipeline (event flow):**
```
ADB connected → ScreenshotPlugin captures → RecognizerPlugin analyzes
  → DecisionEnginePlugin decides → ActionExecutorPlugin executes ADB actions
```

**Key events:** `device_connected`, `device_disconnected`, `screenshot_ready`, `game_state_updated`, `action_required`, `action_pending_confirm`, `action_executed`, `mode_changed`, `season_changed`, `app_closing`.

## Plugin Structure

Each plugin lives in `plugins/<name>/plugin.py` and extends `BasePlugin` from `core/base_plugin.py`. Plugins receive the `EventBus`, `ConfigManager`, and `PluginManager` references at init time. New plugins must be registered in `main.py`'s plugin setup block.

| Plugin | Status | Purpose |
|---|---|---|
| `adb_connector` | Working | Auto-detect emulators, heartbeat, reconnect, connection test |
| `screenshot` | Working | Periodic screenshot capture from emulator (configurable interval) |
| `recognizer` | MVP stub | Shop champion recognition via OpenCV template matching; gold/level are placeholder TODOs (PaddleOCR integration needed) |
| `decision_engine` | MVP | Auto-buy champions from a target list |
| `action_executor` | Working | ADB tap/swipe for buy, refresh, level-up, move, sell |
| `comp_analyzer` | Empty stub | Future: team composition analysis |
| `pool_predictor` | Empty stub | Future: champion pool prediction |

## UI Layer

CustomTkinter app in `ui/app.py` with sidebar navigation. Pages in `ui/pages/`:
- `status_page.py` — real-time game state display, screenshot preview, confirm/reject actions
- `log_page.py` — operation log
- `settings_page.py` — ADB emulator connection profiles (multi-profile CRUD, test, save)
- `data_page.py` — season data management (browse, download, switch, delete)

UI communicates with plugins exclusively through the EventBus.

## Data Layer

`data/fetcher/` fetches official game data from Tencent CDN (champions, traits, items). Season data lives in `data/<season>/` (e.g., `data/s18_mode4/`) with JSON files for champions, traits, items, pool, and metadata. Season directories are gitignored.

## Configuration

`config.yaml` is the single config file. Key sections:
- `season.current` — active season identifier (e.g., `"s18_mode4"`)
- `adb.profiles` — array of connection configs (host, port, device name)
- `screenshot.interval_ms` — capture interval (default 500ms)
- `emulator` — resolution (1280x720)
- `automation.mode` — `"semi_auto"` or `"full_auto"` with per-feature toggles
- `ui.theme` — `"dark"` or `"light"`

## Conventions

- Python 3.12, no type hints enforced but used in some places
- Commit messages: `feat:`, `chore:` prefix style
- The emulator resolution is fixed at 1280x720 — all coordinate-based ADB actions assume this
- DESIGN.md at the repo root is the authoritative design document — consult it for planned architecture decisions
