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
SCRCPY_RED_ICON_MISS_RECOVERY_DELAY = 0.115

# Delay before retrying a box scan after an empty frame.
SCRCPY_BOX_MISS_RECOVERY_DELAY = 0.035

# Delay before retrying an upgrade-station scan after an empty frame.
SCRCPY_UPGRADE_MISS_RECOVERY_DELAY = 0.140

# Minimum wait after a state-changing input before trusting the next scrcpy frame.
SCRCPY_ACTION_SETTLE_DELAY = 0.800


# --- Template matching thresholds ---

# Default confidence threshold for ImageMatcher instances.
MATCH_THRESHOLD = 0.98

# Confidence threshold for regular red-icon detection. 0.93 (v2's value): at 0.94 real badges (delivery
# truck, profile, footer new-level and stats icons) scoring 0.93-0.94 were silently dropped.
RED_ICON_THRESHOLD = 0.93

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

# Confidence threshold for the red X that closes boot and event popups. Matched against
# Assets/redX.png, whose mask covers only the white X glyph plus 2 px of red face.
CLOSE_BUTTON_THRESHOLD = 0.980


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

# Box template names matched on every OPEN_BOXES scan.
BOX_TEMPLATE_NAMES = ("box1", "box2", "box3", "box4")

# Minimum distinct box templates that must agree on a spot (1 = any single template suffices).
BOX_MIN_MATCHES = 1

# Local-minimum search window in pixels used when clustering box matches for one template.
BOX_MIN_DISTANCE = 12

# Overlap (IoU) above which two box matches are the same box and the weaker one is dropped.
BOX_NMS_IOU_THRESHOLD = 0.144


# --- Upgrade-station HSV gate ---

# HSV ranges accepted as valid upgrade-station-colored pixels.
UPGRADE_STATION_HSV_RANGES = (
    ((12, 88, 185), (29, 199, 252)),
    ((100, 135, 204), (103, 191, 255)),
)

# Minimum active-template pixel ratio that must match UPGRADE_STATION_HSV_RANGES.
UPGRADE_STATION_HSV_MIN_MATCH_RATIO = 0.50


# --- Upgrade-station matching ---

# Local-minimum search window in pixels used when scanning for upgrade-station candidates.
UPGRADE_STATION_CANDIDATE_MIN_DISTANCE = 15

# Overlap (IoU) above which two upgrade-station candidates are the same station.
UPGRADE_STATION_CANDIDATE_NMS_IOU_THRESHOLD = 0.20

# Amount subtracted from UPGRADE_STATION_THRESHOLD on later search and verify attempts.
UPGRADE_STATION_THRESHOLD_RELAXATION = 0.05

# While holding a station, a match farther than this many pixels from the held spot is rejected as a
# different station. Once a station reaches its MAX state the relaxed threshold can false-positive on
# an unrelated button at a confidence too high for threshold tuning alone to exclude.
UPGRADE_STATION_DISAPPEAR_POSITION_TOLERANCE_PX = 60


# --- Red-icon matching ---

# HSV ranges accepted as valid red-icon pixels.
RED_ICON_HSV_RANGES = (
    ((0, 45, 120), (12, 255, 255)),
    ((166, 45, 120), (179, 255, 255)),
)

# Minimum active-template pixel ratio that must match RED_ICON_HSV_RANGES.
RED_ICON_HSV_MIN_MATCH_RATIO = 0.65

# Minimum number of red-icon template variants required for consensus mode.
RED_ICON_MIN_MATCHES = 2

# Enables fast red-icon detection using the configured fast template set.
RED_ICON_FAST_MODE_ENABLED = True

# Red-icon template names used when fast detection is enabled.
RED_ICON_FAST_TEMPLATE_NAMES = ("RedIcon5",)

# Minimum pixel spacing between fast-mode red-icon candidates.
RED_ICON_FAST_MIN_DISTANCE = 30

# Red-icon template names matched when fast mode is off (consensus mode).
RED_ICON_NORMAL_TEMPLATE_NAMES = ("RedIcon4", "RedIcon5", "RedIcon6", "RedIcon8", "RedIcon14")

# Overlap (IoU) above which two red-icon matches are the same icon and the weaker one is dropped.
RED_ICON_NMS_IOU_THRESHOLD = 0.20

# Horizontal click offset applied to detected red-icon centers.
RED_ICON_OFFSET_X = 10

# Vertical click offset applied to detected red-icon centers.
RED_ICON_OFFSET_Y = 10


# --- Mouse input timing ---

# Post-click delay applied after mouse click operations.
CLICK_DELAY = 0.032

# Delay after moving the cursor before sending click input.
MOUSE_MOVE_DELAY = 0.017

# Duration to hold the left mouse button down for normal clicks.
MOUSE_DOWN_DURATION = 0.117

# Delay after releasing the left mouse button for normal clicks.
MOUSE_UP_DURATION = 0.117

# Attempts and delay used to confirm low-level cursor and button input.
INPUT_RETRY_COUNT = 3
INPUT_RETRY_DELAY = 0.017

# Pixels the live cursor may differ from its target before a press or hold is aborted. 0 keeps the
# exact-equality check; raise it only if logs show "cursor moved" aborts from DPI or driver rounding.
CURSOR_DRIFT_TOLERANCE_PX = 0

# Enables a short hover delay before click input.
HOVER_ENABLED = True

# Hover delay used before click input when hover is enabled.
HOVER_DURATION = 0.117

# Delay between upgrade-station search attempts.
UPGRADE_SEARCH_INTERVAL = 0.075

# Fresh-screen attempts used to locate an upgrade station.
UPGRADE_SEARCH_ATTEMPTS = 5

# Failed upgrade-search cycles required before forcing a scroll.
FAILED_UPGRADE_SEARCHES_BEFORE_SCROLL = 3

# Successful upgrade holds required before opening stats upgrades.
UPGRADES_BEFORE_STATS = 1

# Maximum time a handler may remain in the same state before flow recovery.
STATE_STALL_TIMEOUT_SECONDS = 9.0

# Pause between state-machine steps in the main event loop.
EVENT_LOOP_INTERVAL = 0.005

# General state-settle delay after selected UI actions.
STATE_DELAY = 0.0

# Period of the INFO "metrics" line (config fingerprint, per-state time share, levels, holds,
# boxes, guard trips, idle scrolls) that makes levels/hour measurable from bot.log; 0 disables it,
# including the closing line logged when the bot stops. 300 s keeps it to ~12 lines/hour.
METRICS_LOG_INTERVAL = 300.0

# Names the state flow in effect. Bump it when the flow changes without a config change: the metrics
# fingerprint hashes config only, so lines from before and after would otherwise look identical.
FLOW_REVISION = "no-work: FIND>STATS>OPEN>SCROLL>OPEN>FIND"

# Delay used after clearing focus before screen confirmation.
FOCUS_SETTLE_DELAY = 0.800

# Delay before visually confirming an upgrade-station candidate.
UPGRADE_STATION_VERIFY_SETTLE_DELAY = 0.160

# Maximum fresh-screen searches allowed while locating the upgrade station for verification.
UPGRADE_STATION_VERIFY_SEARCH_ATTEMPTS = 4

# Delay between upgrade-station verification searches.
UPGRADE_STATION_VERIFY_SEARCH_INTERVAL = 0.075

# Consecutive missed upgrade-station frames required before releasing a hold.
UPGRADE_STATION_DISAPPEAR_CONFIRMATION_COUNT = 1

# Maximum duration for holding an upgrade station before releasing.
CLICK_HOLD_MAX_DURATION = 9.0

# Lower and upper bounds for upgrade-station hold monitoring.
UPGRADE_HOLD_CHECK_INTERVAL_MIN = 0.035
UPGRADE_HOLD_CHECK_INTERVAL_MAX = 0.100

# Duration for generic spam-click loops.
SPAM_CLICK_DURATION = 1.5

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

# Number of visual searches used to locate a new-level transition button. One search per bot step.
NEW_LEVEL_SEARCH_ATTEMPTS = 2

# Delay between new-level transition searches.
NEW_LEVEL_SEARCH_INTERVAL = 0.075

# One-shot down-drag performed before the first new-level red-icon rescan each cycle, forcing a
# fresh render before trusting a miss. v1 originally had this (73f5db0/eccd810) but lost it as an
# incidental bundle in 12e397a alongside an unrelated upgrade-station fix; restored per v2's port.
# Reuses SCROLL_START_POS as its origin; kept separate from the SCROLL_* family (the oscillating
# search scroll used by handle_scroll) since that config is independently tuned and must not be
# conflated with this one-shot verification step.
NEW_LEVEL_VERIFICATION_SCROLL_DISTANCE = 200
NEW_LEVEL_VERIFICATION_SCROLL_DURATION = 0.300
NEW_LEVEL_VERIFICATION_SCROLL_SETTLE_DELAY = 0.800
NEW_LEVEL_VERIFICATION_SCROLL_INTERVAL_PAUSE = 0.300

# Delay after a new-level button click before unlock confirmation starts.
LEVEL_TRANSITION_SETTLE_DELAY = 0.800

# Delay between the verified footer action and its secondary transition click.
NEW_LEVEL_CONFIRMATION_DELAY = 0.800

# Delay after the verified secondary transition click.
LEVEL_TRANSITION_SECONDARY_SETTLE_DELAY = 0.800

# Number of visual searches used to confirm the next-level unlock button.
UNLOCK_SEARCH_ATTEMPTS = 4

# Delay between unlock-button searches.
UNLOCK_SEARCH_INTERVAL = 0.075

# Delay after a confirmed unlock click.
UNLOCK_SETTLE_DELAY = 0.800


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

# Dead-loop guard: after this many box-opening passes with no scroll and no completed upgrade
# hold in between, OPEN_BOXES forces a SCROLL. v2's live logs (Sep 8-25) held streaks of hundreds
# to thousands of consecutive box passes with zero level completions, where a stuck "box" was
# re-clicked forever and the search never scrolled. Healthy runs peak at 3-4 box passes between
# scrolls, so 8 leaves 2x headroom before it interleaves.
MAX_BOX_ONLY_PASSES = 8

# Stall alert: after this many completed scrolls in a row with no box opened, upgrade held,
# stats upgrade or level completed, log a WARNING and probe box detection on the next scan.
# Repeats every multiple. 0 disables.
STALL_SCROLLS_BEFORE_ALERT = 150

# Early log-only probe: once per idle streak, at this many completed scrolls, one INFO line says what
# box and red-icon detection saw on the next scan. It never alerts and never relaunches the game
# (that stays at STALL_SCROLLS_BEFORE_ALERT). 0 disables.
STALL_PROBE_SCROLLS = 30

# Pause between repeated scroll attempts.
SCROLL_INTERVAL_PAUSE = 0.300

# Settle delay after each completed scroll.
POST_SCROLL_SETTLE = 0.300

# Drag duration used for scroll gestures.
SCROLL_DURATION = 0.300


# --- Stats upgrades ---

# Duration of the stats-upgrade spam-click action.
STATS_UPGRADE_CLICK_DURATION = 1.5

# Delay between stats-upgrade clicks.
STATS_UPGRADE_CLICK_DELAY = 0.032

# Mouse-down and mouse-up durations for the stats-upgrade spam-click loop only. This is the one click
# path that must fit many clicks inside STATS_UPGRADE_CLICK_DURATION, so it stays independent of
# MOUSE_DOWN_DURATION and MOUSE_UP_DURATION. A starting point, not a measured minimum.
STATS_UPGRADE_MOUSE_DOWN_DURATION = 0.017
STATS_UPGRADE_MOUSE_UP_DURATION = 0.017


# --- Close-button (red X) rule ---

# Runs before every state handler except the New Level states: taps the red X that closes boot and
# event popups (for example the Offline Earnings dialog after a game relaunch).
CLOSE_BUTTON_ENABLED = True

# Template names matched for the close button.
CLOSE_BUTTON_TEMPLATE_NAMES = ("redX",)

# HSV ranges accepted as valid close-button pixels: coral-red face, then the white glyph.
CLOSE_BUTTON_HSV_RANGES = (
    ((0, 90, 180), (12, 255, 255)),
    ((166, 90, 180), (179, 255, 255)),
    ((0, 0, 225), (179, 70, 255)),
)

# Minimum active-template pixel ratio that must match CLOSE_BUTTON_HSV_RANGES.
CLOSE_BUTTON_HSV_MIN_MATCH_RATIO = 0.85

# Local-minimum search window in pixels used when clustering close-button matches.
CLOSE_BUTTON_MIN_DISTANCE = 20

# Overlap (IoU) above which two close-button matches are the same button.
CLOSE_BUTTON_NMS_IOU_THRESHOLD = 0.20

# Cheap prefilter so the rule can run every step: HSV ranges of the solid red block the X sits on.
CLOSE_BUTTON_BLOCK_HSV_RANGES = (
    ((0, 90, 180), (12, 255, 255)),
    ((166, 90, 180), (179, 255, 255)),
)

# On-screen size in pixels of the X button's red block (the window the prefilter scans with).
CLOSE_BUTTON_BLOCK_WINDOW = 38

# Share of that window that must be red for the frame to be handed to the full template match.
CLOSE_BUTTON_BLOCK_MIN_FRACTION = 0.60

# Blind wait after the tap: the same modal-settle constant as every other popup dismissal.
CLOSE_BUTTON_SETTLE_DELAY = 0.800

# Guard for the rule's absolute priority: the same spot tapped this many times in a row means the tap
# is not closing anything, so the rule stands down instead of starving every other behavior.
CLOSE_BUTTON_MAX_CONSECUTIVE_CLICKS = 6

# How long the rule stays off after standing down.
CLOSE_BUTTON_SUPPRESS_SECONDS = 60.0

# Hard-lock layer two: after any step in a New Level state the rule stays off this long, so a dialog
# still open is left to the New Level flow.
CLOSE_BUTTON_NEW_LEVEL_LOCK_SECONDS = 10.0


# --- Game recovery over adb ---

# Revives a dead game: when a long idle streak ends on a frozen screen, force-stops and relaunches the
# game over adb, then runs only the close-button rule for GAME_RECOVERY_RELAUNCH_SETTLE_SECONDS.
# Off by default because it acts on the phone: it needs adb on PATH and checks the package at start.
GAME_RECOVERY_ENABLED = False

# adb executable used for recovery.
GAME_RECOVERY_ADB_PATH = "adb"

# The game's package is the single installed package whose id contains this (case-insensitive). Zero
# or several matches disable relaunch rather than guess.
GAME_RECOVERY_PACKAGE_HINT = "idlefastfood"

# Mean absolute difference on a 64x36 gray thumbnail between the first scan of an idle streak and the
# scan at the stall alert. A live farm animates; a measured frozen frame scored 0.86.
GAME_RECOVERY_STATIC_FRAME_DELTA = 1.5

# Length of the recovery window after the launch command (cold start plus any popups).
GAME_RECOVERY_RELAUNCH_SETTLE_SECONDS = 60.0

# Pause between close-button scans inside the recovery window when no X is on screen.
GAME_RECOVERY_POLL_SECONDS = 0.3

# Timeout for each adb command.
GAME_RECOVERY_COMMAND_TIMEOUT = 10.0


# --- Auto-resume ---

# Restarts the bot after it stopped itself on a window or focus error, once nobody has touched the
# keyboard or mouse for RESUME_IDLE_SECONDS. While False it only LOGS what it would do (shadow mode),
# so the downtime it could recover is measured before it is allowed to act.
RESUME_ENABLED = False

# Seconds between readiness checks; also the first backoff step after a failed live attempt.
RESUME_CHECK_SECONDS = 60.0

# No key press and no cursor movement for this long before the bot may start itself.
RESUME_IDLE_SECONDS = 600.0

# Failed live attempts in one stop before the bot gives up and waits for a person.
RESUME_MAX_ATTEMPTS = 20


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
TELEGRAM_CLOSE_TIMEOUT = 5.0


# --- Forbidden click zones ---

# Left boundary for the broad footer click block zone.
FORBIDDEN_CLICK_X_MIN = 60

# Right boundary for the broad footer click block zone.
FORBIDDEN_CLICK_X_MAX = 260

# Top boundary for the broad footer click block zone.
FORBIDDEN_CLICK_Y_MIN = 668

# Map active event counts to (x_min, x_max, y_min, y_max) menu choices.
# Add, change, or remove entries here to update the menu automatically.
EVENT_FORBIDDEN_ZONE_OPTIONS: dict[int, tuple[int, int, int, int]] = {
    1: (290, 350, 93, 260),
    2: (290, 350, 93, 320),
    3: (290, 350, 93, 370),
}

NUMBERED_FORBIDDEN_ZONE_BOUNDS = (
    (0, 55, 50, 255),
    (0, 56, 610, 667),
    (150, 193, 70, 109),
    (55, 285, 670, 725),
)
