# Eatventure Autobot V1

Eatventure Autobot is a deterministic Python screen-automation tool for the mobile game *Eatventure*. It combines OpenCV template matching, explicit state transitions, and guarded Windows mouse input.

## Bot Description

The Eatventure Autobot is a sophisticated screen automation tool that interacts with an Android device via `scrcpy`. It uses OpenCV-based image recognition to identify game assets—such as Station Unlocks (Red Icons), upgrade stations, and gift boxes—and executes precise mouse actions to progress through the game. The bot is designed to be resilient, featuring a robust state machine that handles everything from basic gameplay to complex level transitions and reward collection.

## Features

### State Handlers

The bot runs a complete **Finite State Machine (FSM)**: every state has one handler and every handler returns an explicit next state. A 15-second same-state watchdog resets stalled flows to `FIND_RED_ICONS`.

* **FIND_RED_ICONS**: Scans the screen for actionable red icons.
* **CLICK_RED_ICON**: Executes precise clicks on detected targets with sub-pixel refinement.
* **CHECK_UNLOCK**: Handles an unlock prompt after a red-icon action.
* **SEARCH_UPGRADE_STATION**: Locates the active cooking station to apply upgrades.
* **HOLD_UPGRADE_STATION**: Simulates a "long-press" to rapidly purchase upgrades.
* **OPEN_BOXES**: Automatically detects and collects gift box rewards.
* **UPGRADE_STATS**: Manages the secondary stat-boost menu to maximize efficiency.
* **SCROLL**: Executes intelligent, oscillating search patterns when no targets are visible.
* **CHECK_NEW_LEVEL / TRANSITION_LEVEL**: Detects restaurant completion and handles the travel sequence to the next city.
* **WAIT_FOR_UNLOCK**: Confirms the next restaurant is ready before restarting the scan.

Normal flow: `FIND_RED_ICONS → CLICK_RED_ICON → CHECK_UNLOCK → SEARCH_UPGRADE_STATION → HOLD_UPGRADE_STATION → OPEN_BOXES → FIND_RED_ICONS/SCROLL`. Level-complete detections preempt that loop through `CHECK_NEW_LEVEL/TRANSITION_LEVEL → WAIT_FOR_UNLOCK → FIND_RED_ICONS`.

### Priority and Interrupts

The bot gives level transitions priority during normal state processing. Before it commits to most upgrade, box, and red-icon actions, it re-checks for the large **New Level** button or the bottom **Level Complete** indicator so completed restaurants are handled before the next search cycle continues.

### Better Computer Vision

The vision system is built around masked OpenCV template matching with a few practical safeguards:

* **Masked Template Matching**: Uses transparent PNG masks so icon shape matching stays stable.
* **Multi-Template Consensus**: Red icons are only trusted after enough template variants agree on roughly the same location.
* **HSV-Only Color Verification**: Red-icon, box, and upgrade-station candidates pass one HSV pixel-ratio gate.
* **Fixed Calibrated Thresholds**: Detection behavior comes directly from `config.py`, so the same frame produces the same decision.

### Better Logging System

A comprehensive logging system tracks every decision the bot makes. It includes:

* **Structured Tracebacks**: Detailed exception handling to prevent crashes.
* **Performance Metrics**: With `DEBUG = True`, logs include per-capture and per-template-match timings.

### Visual Debugging

The bot provides tools for real-time calibration and transparency:

* **Forbidden Zone Overlay**: When enabled, the bot draws a **semi-transparent red overlay** directly over the game window. This visualizes the "Dead Zones" where the bot is forbidden from clicking (e.g., ad menus, settings buttons), allowing for pixel-perfect configuration of the `FORBIDDEN_ZONES`.

### Forbidden Zone Configuration

The bot utilizes a refactored **Forbidden Zone Handling** system. Zones are defined in `config.py` using relative coordinates. The bot automatically:

1. Filters out any detections located inside these zones.
2. If a critical asset (like an Upgrade Station) is trapped in a forbidden zone, the bot triggers an **Oscillating Scroll** to move the asset into a safe, clickable area.
3. Prioritizes previously successful red-icon rows so the search tends to revisit productive regions first.

## Requirements

* **Operating System**: Windows 10/11
* **Python**: Use a version supported by the pinned packages in `requirements.txt`; the project has been verified locally with Python 3.14.
* **Android Device**: Connected via USB or Wireless ADB, with **Developer Options** and **USB Debugging** enabled.

## Installation Instructions

### Step 1: Install Dependencies

Open your terminal in the project directory and run:

```bash
pip install -r requirements.txt
```

### Step 2: Configure scrcpy

1. Download **scrcpy**: [https://github.com/Genymobile/scrcpy](https://github.com/Genymobile/scrcpy)
2. Extract the files and add the folder to your System PATH.
3. Connect your Android device and ensure it is recognized (`adb devices`).
4. Run scrcpy with the specific title used in `config.py`:

```bash
scrcpy --window-title "EatventureAuto"
```

*(Note: Ensure the window title matches the `WINDOW_TITLE` variable in `config.py`)*

Keep the scrcpy window in the foreground while automation is running. The bot
rejects global cursor and mouse input whenever another window owns the
foreground.

Starting the bot takes two `Z` presses:

1. Press `Z`, choose the number of active events, and press Enter. The bot is
   now primed but is not running.
2. Focus the scrcpy window, then press `Z` again to start automation.

If startup fails, the selection remains primed. Resolve the reported error,
focus scrcpy, and press `Z` again to retry. Pressing `Z` while the bot is
running stops it; the next run will ask for the active-event count again.

Runtime hotkeys:

* `Z`: prime, start, retry, or stop automation according to its current state.
* `X`: log the cursor position relative to the scrcpy client.
* `P`: exit cleanly.

## Coming Soon

* **Graphical User Interface (GUI)**: A dedicated control panel for easier operation, allowing real-time monitoring, visual threshold adjustment, and one-click start/stop functionality without terminal interaction.

## Telegram Notification

### Step 1: Create a Telegram Bot

1. Search for `@BotFather` on Telegram.
2. Send `/newbot` and follow the instructions to name your bot.
3. Copy the provided **API Token**.

### Step 2: Get Chat ID

1. Start a chat with your new bot and send any message.
2. Set the token in the PowerShell session used to run the helper:

```powershell
$env:EATVENTURE_TELEGRAM_BOT_TOKEN = "your-token"
python get_chat_id.py
```

3. Copy one of the reported chat IDs, then configure notifications in the same
   PowerShell session before starting the bot:

```powershell
$env:EATVENTURE_TELEGRAM_CHAT_ID = "your-chat-id"
$env:EATVENTURE_TELEGRAM_ENABLED = "true"
python main.py
```

Do not paste the bot token into `config.py` or commit it to source control.

## Disclaimer

This bot is developed for **educational purposes only**. Using automation tools or scripts may violate the game's Terms of Service and could result in account suspension or banning. Use this software at your own risk. The developers are not responsible for any consequences resulting from the use of this bot.

## License

Eatventure Autobot is open-source software. It is free to use, modify, and distribute for personal and educational use.

Keywords: [eatventure bot, python automation, opencv, scrcpy, mobile game bot, image recognition, state machine, android automation, game botting]
