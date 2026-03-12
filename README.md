# Eatventure Autobot V1

Eatventure Autobot is a Python-powered automation tool designed for the popular mobile game *Eatventure*. By leveraging advanced computer vision, state-machine logic, and adaptive AI learning, the bot autonomously manages restaurant completions with high precision and human-like interaction patterns.

## Bot Description

The Eatventure Autobot is a sophisticated screen automation tool that interacts with an Android device via `scrcpy`. It uses OpenCV-based image recognition to identify game assets—such as Station Unlocks (Red Icons), upgrade stations, and gift boxes—and executes precise mouse actions to progress through the game. The bot is designed to be resilient, featuring a robust state machine that handles everything from basic gameplay to complex level transitions and reward collection.

## Features

### State Handlers

The bot's intelligence is built upon a formal **Finite State Machine (FSM)**. Every action is encapsulated within dedicated handlers that manage transitions based on real-time visual feedback:

* **FIND_RED_ICONS**: Scans the screen for actionable red icons.
* **CLICK_RED_ICON**: Executes precise clicks on detected targets with sub-pixel refinement.
* **SEARCH_UPGRADE_STATION**: Locates the active cooking station to apply upgrades.
* **HOLD_UPGRADE_STATION**: Simulates a "long-press" to rapidly purchase upgrades.
* **OPEN_BOXES**: Automatically detects and collects gift box rewards.
* **UPGRADE_STATS**: Manages the secondary stat-boost menu to maximize efficiency.
* **SCROLL**: Executes intelligent, oscillating search patterns when no targets are visible.
* **CHECK_NEW_LEVEL / TRANSITION_LEVEL**: Detects restaurant completion and handles the travel sequence to the next city.

### Priority and Interrupts

The bot features a **Priority Resolver** that allows critical events to interrupt standard gameplay. Using **Exception-Based Control Flow**, the bot can immediately halt a long-press or a scroll operation if a "New Level" button or a critical "Level Complete" red icon is detected. This ensures that the bot never wastes time on a completed restaurant and transitions as fast as possible.

### Better Computer Vision

The vision system goes far beyond simple template matching:

* **OpenCV Integration**: Uses optimized template matching with masks to handle transparency.
* **Dual-Gate Color Verification**: Before clicking, the bot validates the **Red Channel Dominance** and **Red Pixel Density**. This prevents "false positives" caused by similar-looking background textures.
* **Temporal Consistency (Stability Check)**: The bot must "see" an icon consistently across multiple frames before it is considered a valid target, eliminating clicks on transient animations or visual noise.
* **Sub-Pixel Refinement**: After initial detection, the bot performs a localized "micro-scan" to center the click coordinate perfectly on the asset.

### Adaptive and Historical Learning

The bot features a self-optimizing AI layer that adapts to your device's performance:

* **Adaptive Tuner**: Automatically monitors success rates and adjusts `CLICK_DELAY` and `MOUSE_MOVE_DELAY` in real-time. If clicks are missing, it slows down; if successful, it speeds up to find the "sweet spot" of efficiency.
* **Vision Optimizer**: Dynamically adjusts detection thresholds based on past match confidence, ensuring reliable detection even in varying lighting or game environments.
* **Historical Learner**: Records the time taken for every restaurant completion. Over time, it identifies the most efficient timing profiles and applies them as the "Global Best" configuration, learning the optimal cadence for your specific game progress.

### Better Logging System

A comprehensive logging system tracks every decision the bot makes. It includes:

* **Structured Tracebacks**: Detailed exception handling to prevent crashes.
* **State Persistence**: AI vision and learning states are saved to JSON files, allowing the bot to retain its "knowledge" even after a restart.
* **Performance Metrics**: Logs completion times and AI "confidence" levels for debugging.

### Visual Debugging

The bot provides tools for real-time calibration and transparency:

* **Debug Vision**: Displays the bot's internal HSV masks, showing exactly what red pixels it is detecting. This is essential for tweaking `RED_ICON_PIXEL_THRESHOLD` and HSV bounds.
* **Forbidden Zone Overlay**: When enabled, the bot draws a **semi-transparent red overlay** directly over the game window. This visualizes the "Dead Zones" where the bot is forbidden from clicking (e.g., ad menus, settings buttons), allowing for pixel-perfect configuration of the `FORBIDDEN_ZONES`.

### Forbidden Zone Configuration

The bot utilizes a refactored **Forbidden Zone Handling** system. Zones are defined in `config.py` using relative coordinates. The bot automatically:

1. Filters out any detections located inside these zones.
2. If a critical asset (like an Upgrade Station) is trapped in a forbidden zone, the bot triggers an **Oscillating Scroll** to move the asset into a safe, clickable area.
3. Implements a **Blackout Cache** to temporarily ignore coordinates that have repeatedly failed safety checks.

## Requirements

* **Operating System**: Windows 10/11
* **Python**: 3.8 or higher
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

## Coming Soon

* **Graphical User Interface (GUI)**: A dedicated control panel for easier operation, allowing real-time monitoring, visual threshold adjustment, and one-click start/stop functionality without terminal interaction.

## Telegram Notification

### Step 1: Create a Telegram Bot

1. Search for `@BotFather` on Telegram.
2. Send `/newbot` and follow the instructions to name your bot.
3. Copy the provided **API Token**.

### Step 2: Get Chat ID

1. Start a chat with your new bot and send any message.
2. Visit `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates` in your browser.
3. Look for the `"chat":{"id":...}` field and copy the number.
4. Paste the **Token** and **Chat ID** into `config.py` and set `TELEGRAM_ENABLED = True`.

## Disclaimer

This bot is developed for **educational purposes only**. Using automation tools or scripts may violate the game's Terms of Service and could result in account suspension or banning. Use this software at your own risk. The developers are not responsible for any consequences resulting from the use of this bot.

## License

Eatventure Autobot is open-source software. It is free to use, modify, and distribute for personal and educational use.

Keywords: [eatventure bot, python automation, opencv, scrcpy, mobile game bot, image recognition, state machine, adaptive ai, android automation, game botting]
