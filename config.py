import os
from pathlib import Path

# --- Runtime paths ---

# Directory that contains the PNG template assets loaded by the bot.
ASSETS_DIR = str(Path(__file__).resolve().parent / "Assets")

# Directory where rotating runtime logs are written.
LOGS_DIR = str(Path(__file__).resolve().parent / "logs")

# --- Window and diagnostics ---

# Exact scrcpy window title the automation attaches to.
WINDOW_TITLE = "EatventureAuto"

# Target scrcpy window width used during window resize.
WINDOW_WIDTH = 360

# Target scrcpy window height used during window resize.
WINDOW_HEIGHT = 780

# Enables DEBUG logging when True and INFO logging when False.
DEBUG = False

# Shows the forbidden-area overlay when the bot starts.
ShowForbiddenArea = False


# --- SCRCPY frame recovery ---

# Enables one delayed retry after likely scrcpy frame misses.
SCRCPY_MISS_RECOVERY_ENABLED = True

# Delay before retrying a red-icon scan after an empty frame.
SCRCPY_RED_ICON_MISS_RECOVERY_DELAY = 0.048

# Delay before retrying a box scan after an empty frame.
SCRCPY_BOX_MISS_RECOVERY_DELAY = 0.048

# Delay before retrying an upgrade-station scan after an empty frame.
SCRCPY_UPGRADE_MISS_RECOVERY_DELAY = 0.048

# Minimum wait after a state-changing input before trusting the next scrcpy frame.
SCRCPY_ACTION_SETTLE_DELAY = 0.032


# --- Template matching thresholds ---

# Default confidence threshold for ImageMatcher instances.
MATCH_THRESHOLD = 0.98

# Confidence threshold for regular red-icon detection.
RED_ICON_THRESHOLD = 0.947

# Confidence threshold for the footer red icon that indicates a new level.
NEW_LEVEL_RED_ICON_THRESHOLD = 0.942

# Confidence threshold for the stats-upgrade red icon.
STATS_RED_ICON_THRESHOLD = 0.943

# Confidence threshold for upgrade-station detection.
UPGRADE_STATION_THRESHOLD = 0.910

# Confidence threshold for gift-box detection.
BOX_THRESHOLD = 0.930

# Confidence threshold for unlock button detection.
UNLOCK_THRESHOLD = 0.905

# Confidence threshold for new-level button detection.
NEW_LEVEL_THRESHOLD = 0.965


# --- Box HSV gate ---

# HSV ranges accepted as valid box-colored pixels.
BOX_HSV_RANGES = (
    ((10, 65, 180), (13, 105, 255)),
    ((13, 90, 120), (15, 190, 245)),
    ((18, 90, 120), (18, 129, 245)),
    ((18, 130, 120), (18, 130, 229)),
    ((18, 130, 235), (18, 130, 245)),
    ((18, 131, 120), (18, 190, 245)),
    ((20, 115, 220), (20, 125, 245)),
    ((23, 65, 140), (30, 115, 255)),
)

# Minimum active-template pixel ratio that must match BOX_HSV_RANGES.
BOX_HSV_MIN_MATCH_RATIO = 0.390


# --- Upgrade-station HSV gate ---

# HSV ranges accepted as valid upgrade-station-colored pixels.
UPGRADE_STATION_HSV_RANGES = (
    ((12, 88, 185), (29, 199, 252)),
    ((100, 135, 204), (103, 191, 255)),
)

# Minimum active-template pixel ratio that must match UPGRADE_STATION_HSV_RANGES.
UPGRADE_STATION_HSV_MIN_MATCH_RATIO = 0.50


# --- Red-icon matching ---

# HSV ranges accepted as valid red-icon pixels.
RED_ICON_HSV_RANGES = (
    ((0, 85, 120), (12, 255, 255)),
    ((166, 85, 120), (179, 255, 255)),
)

# Minimum active-template pixel ratio that must match RED_ICON_HSV_RANGES.
RED_ICON_HSV_MIN_MATCH_RATIO = 0.50

# Minimum number of red-icon template variants required for consensus mode.
RED_ICON_MIN_MATCHES = 3

# Enables fast red-icon detection using the configured fast template set.
RED_ICON_FAST_MODE_ENABLED = True

# Red-icon template names used when fast detection is enabled.
RED_ICON_FAST_TEMPLATE_NAMES = ("RedIcon5",)

# Minimum pixel spacing between fast-mode red-icon candidates.
RED_ICON_FAST_MIN_DISTANCE = 30

# Horizontal click offset applied to detected red-icon centers.
RED_ICON_OFFSET_X = 10

# Vertical click offset applied to detected red-icon centers.
RED_ICON_OFFSET_Y = 10


# --- Mouse input timing ---

# Post-click delay applied after mouse click operations.
CLICK_DELAY = 0.032

# Delay after moving the cursor before sending click input.
MOUSE_MOVE_DELAY = 0.016

# Duration to hold the left mouse button down for normal clicks.
MOUSE_DOWN_DURATION = 0.112

# Delay after releasing the left mouse button for normal clicks.
MOUSE_UP_DURATION = 0.112

# Attempts and delay used to confirm low-level cursor and button input.
INPUT_RETRY_COUNT = 3
INPUT_RETRY_DELAY = 0.05

# Enables a short hover delay before click input.
HOVER_ENABLED = False

# Hover delay used before click input when hover is enabled.
HOVER_DURATION = 0.0

# Delay between upgrade-station search attempts.
UPGRADE_SEARCH_INTERVAL = 0.048

# Fresh-screen attempts used to locate an upgrade station.
UPGRADE_SEARCH_ATTEMPTS = 5

# Failed upgrade-search cycles required before forcing a scroll.
FAILED_UPGRADE_SEARCHES_BEFORE_SCROLL = 3

# Successful upgrade holds required before opening stats upgrades.
UPGRADES_BEFORE_STATS = 2

# Maximum time a handler may remain in the same state before flow recovery.
STATE_STALL_TIMEOUT_SECONDS = 15.0

# General state-settle delay after selected UI actions.
STATE_DELAY = 0.0

# Delay used after clearing focus before screen confirmation.
FOCUS_SETTLE_DELAY = 0.032

# Delay before visually confirming an upgrade-station candidate.
UPGRADE_STATION_VERIFY_SETTLE_DELAY = 0.112

# Maximum fresh-screen searches allowed while locating the upgrade station for verification.
UPGRADE_STATION_VERIFY_SEARCH_ATTEMPTS = 4

# Delay between upgrade-station verification searches.
UPGRADE_STATION_VERIFY_SEARCH_INTERVAL = 0.048

# Consecutive missed upgrade-station frames required before releasing a hold.
UPGRADE_STATION_DISAPPEAR_CONFIRMATION_COUNT = 1

# Maximum duration for holding an upgrade station before releasing.
CLICK_HOLD_MAX_DURATION = 9.5

# Lower and upper bounds for upgrade-station hold monitoring.
UPGRADE_HOLD_CHECK_INTERVAL_MIN = 0.048
UPGRADE_HOLD_CHECK_INTERVAL_MAX = 0.096

# Absolute cap for the upgrade-station hold monitor.
UPGRADE_HOLD_MAX_CHECKS = 400

# Duration for generic spam-click loops.
SPAM_CLICK_DURATION = 1.75

# Delay between clicks in generic spam-click loops.
SPAM_CLICK_DELAY = 0.016


# --- Capture regions ---

# Maximum vertical capture boundary for normal top-area searches.
MAX_SEARCH_Y = 660

# Extended vertical capture boundary for footer-aware searches.
EXTENDED_SEARCH_Y = 710

# Vertical capture boundary for upgrade-station searches.
UPGRADE_STATION_SEARCH_Y = 760

# Vertical capture boundary for box searches.
BOX_SEARCH_Y = 780


# --- Click targets ---

# Safe idle click position used to clear focus and dismiss transient UI.
IDLE_CLICK_POS = (8, 390)

# Button position used to open the stats-upgrade panel.
STATS_UPGRADE_BUTTON_POS = (310, 698)

# Position spam-clicked to buy stats upgrades.
STATS_UPGRADE_POS = (270, 304)

# Drag start position used for scroll gestures.
SCROLL_START_POS = (170, 380)

# Position used for the verified new-level button path.
NEW_LEVEL_BUTTON_POS = (30, 692)

# Position used for the secondary level-transition click.
LEVEL_TRANSITION_POS = (174, 520)

# Number of visual searches used to locate a new-level transition button.
NEW_LEVEL_SEARCH_ATTEMPTS = 5

# Delay between new-level transition searches.
NEW_LEVEL_SEARCH_INTERVAL = 0.176

# Delay after a new-level button click before unlock confirmation starts.
LEVEL_TRANSITION_SETTLE_DELAY = 0.5

# Delay between the verified footer action and its secondary transition click.
NEW_LEVEL_CONFIRMATION_DELAY = 0.5

# Delay after the verified secondary transition click.
LEVEL_TRANSITION_SECONDARY_SETTLE_DELAY = 0.5

# Number of visual searches used to confirm the next-level unlock button.
UNLOCK_SEARCH_ATTEMPTS = 4

# Delay between unlock-button searches.
UNLOCK_SEARCH_INTERVAL = 0.176

# Delay after a confirmed unlock click.
UNLOCK_SETTLE_DELAY = 0.176


# --- Red-icon target zones ---

# Left boundary for the footer new-level red icon zone.
NEW_LEVEL_RED_ICON_X_MIN = 40

# Right boundary for the footer new-level red icon zone.
NEW_LEVEL_RED_ICON_X_MAX = 60

# Top boundary for the footer new-level red icon zone.
NEW_LEVEL_RED_ICON_Y_MIN = 665

# Bottom boundary for the footer new-level red icon zone.
NEW_LEVEL_RED_ICON_Y_MAX = 680

# Left boundary for the stats-upgrade red icon zone.
UPGRADE_RED_ICON_X_MIN = 280

# Right boundary for the stats-upgrade red icon zone.
UPGRADE_RED_ICON_X_MAX = 310

# Top boundary for the stats-upgrade red icon zone.
UPGRADE_RED_ICON_Y_MIN = 665

# Bottom boundary for the stats-upgrade red icon zone.
UPGRADE_RED_ICON_Y_MAX = 680


# --- Scroll behavior ---

# Base pixel distance for one scroll gesture.
SCROLL_PIXEL_STEP = 180

# Multiplier applied to SCROLL_PIXEL_STEP before each drag.
SCROLL_DISTANCE_RATIO = 1.0

# Maximum oscillation cycle count before scroll progress wraps.
MAX_SCROLL_CYCLES = 6

# Additional scroll steps added per oscillation cycle.
SCROLL_INCREMENT_STEP = 1

# Maximum consecutive no-work box cycles before the bot scrolls to a new area.
MAX_IDLE_PASS_ATTEMPTS = 1

# Pause between repeated scroll attempts.
SCROLL_INTERVAL_PAUSE = 0.100

# Settle delay after each completed scroll.
POST_SCROLL_SETTLE = 0.100

# Drag duration used for scroll gestures.
SCROLL_DURATION = 0.300


# --- Stats upgrades ---

# Duration of the stats-upgrade spam-click action.
STATS_UPGRADE_CLICK_DURATION = 1.75

# Delay between stats-upgrade clicks and the mouse down duration for that loop.
STATS_UPGRADE_CLICK_DELAY = 0.016


# --- Telegram notifications ---

# Enables Telegram notification delivery when set to a recognized true value.
TELEGRAM_ENABLED = os.environ.get("EATVENTURE_TELEGRAM_ENABLED", "").strip().casefold() in {
    "1",
    "true",
    "yes",
    "on",
}

# Telegram bot token supplied outside source control.
TELEGRAM_BOT_TOKEN = os.environ.get("EATVENTURE_TELEGRAM_BOT_TOKEN", "").strip()

# Telegram chat ID supplied outside source control.
TELEGRAM_CHAT_ID = os.environ.get("EATVENTURE_TELEGRAM_CHAT_ID", "").strip()

# Maximum queued Telegram messages before new messages are dropped.
TELEGRAM_QUEUE_MAXSIZE = 100

# Maximum time to wait for the Telegram worker to stop.
TELEGRAM_CLOSE_TIMEOUT = 5.5


# --- Forbidden click zones ---

# Left boundary for the broad footer click block zone.
FORBIDDEN_CLICK_X_MIN = 60

# Right boundary for the broad footer click block zone.
FORBIDDEN_CLICK_X_MAX = 260

# Top boundary for the broad footer click block zone.
FORBIDDEN_CLICK_Y_MIN = 668

NUMBERED_FORBIDDEN_ZONE_BOUNDS = (
    (290, 350, 93, 330),
    (0, 60, 50, 280),
    (0, 60, 600, 667),
    (145, 200, 65, 110),
    (55, 285, 660, 725),
)
