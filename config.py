import os
from pathlib import Path

# --- Runtime paths ---

# Directory that contains the PNG template assets loaded by the bot.
ASSETS_DIR = str(Path(__file__).resolve().parent / "Assets")

# Directory where rotating runtime logs are written.
LOGS_DIR = str(Path(__file__).resolve().parent / "logs")

# JSON file used to persist adaptive vision threshold state.
AI_VISION_STATE_FILE = str(Path(__file__).resolve().parent / "memory" / "vision_state.json")

# JSON file used to persist historical learning state.
AI_LEARNING_STATE_FILE = str(Path(__file__).resolve().parent / "memory" / "learning_state_stable.json")


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


# --- Supervision non-max suppression ---

# Enables the optional supervision-backed NMS layer globally.
SUPERVISION_ENABLED = True

# Enables supervision NMS for box candidates.
SUPERVISION_BOX_NMS_ENABLED = True

# Enables supervision NMS for red-icon candidates.
SUPERVISION_RED_ICON_NMS_ENABLED = True

# Enables supervision NMS for upgrade-station candidates.
SUPERVISION_UPGRADE_STATION_NMS_ENABLED = True

# Applies supervision NMS without separating candidates by class.
SUPERVISION_CLASS_AGNOSTIC_NMS = True

# IOU threshold used when supervision NMS merges box candidates.
SUPERVISION_BOX_NMS_IOU_THRESHOLD = 0.25

# IOU threshold used when supervision NMS merges red-icon candidates.
SUPERVISION_RED_ICON_NMS_IOU_THRESHOLD = 0.20

# IOU threshold used when supervision NMS merges upgrade-station candidates.
SUPERVISION_UPGRADE_STATION_NMS_IOU_THRESHOLD = 0.20


# --- SCRCPY frame recovery ---

# Enables one delayed retry after likely scrcpy frame misses.
SCRCPY_MISS_RECOVERY_ENABLED = True

# Delay before retrying a red-icon scan after an empty frame.
SCRCPY_RED_ICON_MISS_RECOVERY_DELAY = 0.140

# Delay before retrying a box scan after an empty frame.
SCRCPY_BOX_MISS_RECOVERY_DELAY = 0.120

# Delay before retrying an upgrade-station scan after an empty frame.
SCRCPY_UPGRADE_MISS_RECOVERY_DELAY = 0.160


# --- Template matching thresholds ---

# Default confidence threshold for ImageMatcher instances.
MATCH_THRESHOLD = 0.98

# Confidence threshold for regular red-icon detection.
RED_ICON_THRESHOLD = 0.931

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


# --- Box detection gates ---

# Enables legacy color-histogram verification for box candidates.
BOX_COLOR_CHECK = False

# Minimum color-histogram similarity required when box color checks are enabled.
BOX_COLOR_THRESHOLD = 0.5

# Enables HSV pixel-ratio verification for box candidates.
BOX_HSV_COLOR_GATE_ENABLED = True

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


# --- Upgrade-station detection gates ---

# Enables legacy color-histogram verification for upgrade-station candidates.
UPGRADE_STATION_COLOR_CHECK = False

# Enables HSV pixel-ratio verification for upgrade-station candidates.
UPGRADE_STATION_HSV_COLOR_GATE_ENABLED = True

# HSV ranges accepted as valid upgrade-station-colored pixels.
UPGRADE_STATION_HSV_RANGES = (
    ((12, 88, 185), (29, 199, 252)),
    ((100, 135, 204), (103, 191, 255)),
)

# Minimum active-template pixel ratio that must match UPGRADE_STATION_HSV_RANGES.
UPGRADE_STATION_HSV_MIN_MATCH_RATIO = 0.50


# --- Red-icon matching ---

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
CLICK_DELAY = 0.017

# Delay after moving the cursor before sending click input.
MOUSE_MOVE_DELAY = 0.017

# Duration to hold the left mouse button down for normal clicks.
MOUSE_DOWN_DURATION = 0.117

# Delay after releasing the left mouse button for normal clicks.
MOUSE_UP_DURATION = 0.117

# Enables a short hover delay before click input.
HOVER_ENABLED = False

# Hover delay used before click input when hover is enabled.
HOVER_DURATION = 0.0

# Delay between upgrade-station search attempts.
UPGRADE_SEARCH_INTERVAL = 0.100

# General state-settle delay after selected UI actions.
STATE_DELAY = 0.0

# Delay used after clearing focus before screen confirmation.
FOCUS_SETTLE_DELAY = 0.05

# Delay after the upgrade-station verification click before rescanning.
UPGRADE_STATION_VERIFY_SETTLE_DELAY = 0.134

# Number of upgrade-station verification searches before holding.
UPGRADE_STATION_VERIFY_SEARCH_ATTEMPTS = 2

# Delay between upgrade-station verification searches.
UPGRADE_STATION_VERIFY_SEARCH_INTERVAL = 0.067

# Maximum duration for holding an upgrade station before releasing.
CLICK_HOLD_MAX_DURATION = 9.5

# Lower and upper bounds for upgrade-station hold monitoring.
UPGRADE_HOLD_CHECK_INTERVAL_MIN = 0.025
UPGRADE_HOLD_CHECK_INTERVAL_MAX = 0.2

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
NEW_LEVEL_SEARCH_INTERVAL = 0.20

# Delay after a new-level button click before unlock confirmation starts.
LEVEL_TRANSITION_SETTLE_DELAY = 1.0

# Delay between the verified footer action and its secondary transition click.
NEW_LEVEL_CONFIRMATION_DELAY = 0.30

# Delay after the verified secondary transition click.
LEVEL_TRANSITION_SECONDARY_SETTLE_DELAY = 0.20

# Number of visual searches used to confirm the next-level unlock button.
UNLOCK_SEARCH_ATTEMPTS = 4

# Delay between unlock-button searches.
UNLOCK_SEARCH_INTERVAL = 0.30

# Delay after a confirmed unlock click.
UNLOCK_SETTLE_DELAY = 0.50


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
MAX_SCROLL_CYCLES = 1

# Additional scroll steps added per oscillation cycle.
SCROLL_INCREMENT_STEP = 5 

# Pause between repeated scroll attempts.
SCROLL_INTERVAL_PAUSE = 0.1

# Settle delay after each completed scroll.
POST_SCROLL_SETTLE = 0.1

# Drag duration used for scroll gestures.
SCROLL_DURATION = 0.3


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
TELEGRAM_CLOSE_TIMEOUT = 6.5


# --- Adaptive input tuner ---

# Enables adaptive runtime adjustment of click and search timing.
ADAPTIVE_TUNER_ENABLED = False

# Exponential moving-average weight for adaptive tuner success rates.
ADAPTIVE_TUNER_ALPHA = 0.18

# Click success rate below which click and move delays are increased.
ADAPTIVE_TUNER_CLICK_LOW_THRESHOLD = 0.96

# Click success rate above which click and move delays are decreased.
ADAPTIVE_TUNER_CLICK_HIGH_THRESHOLD = 0.995

# Search success rate below which the search interval is increased.
ADAPTIVE_TUNER_SEARCH_LOW_THRESHOLD = 0.90

# Search success rate above which the search interval is decreased.
ADAPTIVE_TUNER_SEARCH_HIGH_THRESHOLD = 0.985

# Amount added to click delay after low click success.
ADAPTIVE_TUNER_CLICK_DELAY_STEP = 0.008

# Amount added to move delay after low click success.
ADAPTIVE_TUNER_MOVE_DELAY_STEP = 0.004

# Amount removed from click delay after high click success.
ADAPTIVE_TUNER_CLICK_DECREMENT = 0.0040

# Amount removed from move delay after high click success.
ADAPTIVE_TUNER_MOVE_DECREMENT = 0.002

# Amount added to search interval after low search success.
ADAPTIVE_TUNER_SEARCH_INTERVAL_STEP = 0.025

# Amount removed from search interval after high search success.
ADAPTIVE_TUNER_SEARCH_DECREMENT = 0.0100

# Lowest click delay the adaptive tuner may apply.
ADAPTIVE_TUNER_MIN_CLICK_DELAY = 0.008

# Highest click delay the adaptive tuner may apply.
ADAPTIVE_TUNER_MAX_CLICK_DELAY = 0.080

# Lowest move delay the adaptive tuner may apply.
ADAPTIVE_TUNER_MIN_MOVE_DELAY = 0.008

# Highest move delay the adaptive tuner may apply.
ADAPTIVE_TUNER_MAX_MOVE_DELAY = 0.050

# Lowest upgrade search interval the adaptive tuner may apply.
ADAPTIVE_TUNER_MIN_SEARCH_INTERVAL = 0.075

# Highest upgrade search interval the adaptive tuner may apply.
ADAPTIVE_TUNER_MAX_SEARCH_INTERVAL = 0.250


# --- AI vision optimizer ---

# Enables adaptive vision threshold adjustment.
AI_VISION_ENABLED = False

# Base exponential moving-average weight for vision confidence updates.
AI_VISION_ALPHA = 0.18

# Maximum adaptive moving-average weight for strong confidence updates.
AI_VISION_ALPHA_MAX = 0.35

# Confidence-derived boost used when updating adaptive thresholds.
AI_VISION_CONFIDENCE_BOOST = 0.10

# Confidence threshold above which adaptive alpha is boosted.
AI_VISION_CONFIDENCE_THRESHOLD = 0.96

# Minimum adaptive threshold for box detection.
AI_BOX_THRESHOLD_MIN = 0.903

# Maximum adaptive threshold for box detection.
AI_BOX_THRESHOLD_MAX = 0.903

# Consecutive box misses required before lowering the adaptive box threshold.
AI_BOX_MISS_WINDOW = 3

# Amount subtracted from box threshold after a miss window.
AI_BOX_MISS_STEP = 0.0020

# Minimum adaptive threshold for red-icon detection.
AI_RED_ICON_THRESHOLD_MIN = 0.942

# Maximum adaptive threshold for red-icon detection.
AI_RED_ICON_THRESHOLD_MAX = 0.942

# Safety margin subtracted from averaged red-icon confidence.
AI_RED_ICON_MARGIN = 0.012

# Consecutive red-icon misses required before lowering the adaptive red-icon threshold.
AI_RED_ICON_MISS_WINDOW = 5

# Amount subtracted from red-icon threshold after a miss window.
AI_RED_ICON_MISS_STEP = 0.0010

# Minimum adaptive threshold for new-level button detection.
AI_NEW_LEVEL_THRESHOLD_MIN = 0.945

# Maximum adaptive threshold for new-level button detection.
AI_NEW_LEVEL_THRESHOLD_MAX = 0.988

# Consecutive new-level button misses required before lowering the adaptive threshold.
AI_NEW_LEVEL_MISS_WINDOW = 3

# Amount subtracted from new-level button threshold after a miss window.
AI_NEW_LEVEL_MISS_STEP = 0.0025

# Minimum adaptive threshold for footer new-level red-icon detection.
AI_NEW_LEVEL_RED_ICON_THRESHOLD_MIN = 0.942

# Maximum adaptive threshold for footer new-level red-icon detection.
AI_NEW_LEVEL_RED_ICON_THRESHOLD_MAX = 0.942

# Consecutive footer new-level red-icon misses required before lowering the adaptive threshold.
AI_NEW_LEVEL_RED_ICON_MISS_WINDOW = 5

# Amount subtracted from footer new-level red-icon threshold after a miss window.
AI_NEW_LEVEL_RED_ICON_MISS_STEP = 0.0010

# Minimum adaptive threshold for upgrade-station detection.
AI_UPGRADE_STATION_THRESHOLD_MIN = 0.918

# Maximum adaptive threshold for upgrade-station detection.
AI_UPGRADE_STATION_THRESHOLD_MAX = 0.918

# Consecutive upgrade-station misses required before lowering the adaptive threshold.
AI_UPGRADE_STATION_MISS_WINDOW = 3

# Amount subtracted from upgrade-station threshold after a miss window.
AI_UPGRADE_STATION_MISS_STEP = 0.0020

# Minimum adaptive threshold for stats-upgrade icon detection.
AI_STATS_UPGRADE_THRESHOLD_MIN = 0.942

# Maximum adaptive threshold for stats-upgrade icon detection.
AI_STATS_UPGRADE_THRESHOLD_MAX = 0.942

# Consecutive stats-upgrade misses required before lowering the adaptive threshold.
AI_STATS_UPGRADE_MISS_WINDOW = 3

# Amount subtracted from stats-upgrade threshold after a miss window.
AI_STATS_UPGRADE_MISS_STEP = 0.0010

# Minimum seconds between persisted vision state saves.
AI_VISION_SAVE_INTERVAL = 180.0


# --- Historical learner ---

# Enables historical completion-time learning.
AI_LEARNING_ENABLED = False

# Minimum seconds between persisted learning state saves.
AI_LEARNING_SAVE_INTERVAL = 180.0

# Maximum historical completion records retained.
AI_LEARNING_RECORDS_LIMIT = 256

# Maximum seconds to wait for the learner thread to join during stop.
AI_LEARNING_THREAD_JOIN_TIMEOUT = 1.50

# Seconds between historical learner background cycles.
AI_LEARNING_THREAD_INTERVAL = 1.50

# Minimum sleep used by the historical learner loop.
LEARNING_LOOP_MIN_SLEEP = 1.50

# Time-window size used to pair completion records for profile analysis.
AI_LEARNING_PAIR_WINDOW = 5

# Batch size used when selecting historical records for profile analysis.
AI_LEARNING_BATCH_WINDOW = 12

# Exponential moving-average weight for learned behavior profiles.
AI_LEARNING_EMA_ALPHA = 0.14

# Number of top historical profiles blended into learned behavior.
AI_LEARNING_PROFILE_BLEND_TOP_K = 3

# Minimum improvement ratio required before applying learned behavior.
AI_LEARNING_MIN_IMPROVEMENT_RATIO = 0.05

# Cooldown in seconds between learned behavior applications.
AI_LEARNING_APPLY_COOLDOWN = 45.0

# Minimum learned click delay allowed.
AI_LEARNING_MIN_CLICK_DELAY = 0.008

# Maximum learned click delay allowed.
AI_LEARNING_MAX_CLICK_DELAY = 0.080

# Minimum learned mouse move delay allowed.
AI_LEARNING_MIN_MOVE_DELAY = 0.008

# Maximum learned mouse move delay allowed.
AI_LEARNING_MAX_MOVE_DELAY = 0.050

# Minimum learned upgrade search interval allowed.
AI_LEARNING_MIN_SEARCH_INTERVAL = 0.075

# Maximum learned upgrade search interval allowed.
AI_LEARNING_MAX_SEARCH_INTERVAL = 0.250


# --- Forbidden click zones ---

# Left boundary for the broad footer click block zone.
FORBIDDEN_CLICK_X_MIN = 60

# Right boundary for the broad footer click block zone.
FORBIDDEN_CLICK_X_MAX = 260

# Top boundary for the broad footer click block zone.
FORBIDDEN_CLICK_Y_MIN = 668

# Left boundary for forbidden zone 1.
FORBIDDEN_ZONE_1_X_MIN = 290

# Right boundary for forbidden zone 1.
FORBIDDEN_ZONE_1_X_MAX = 350

# Top boundary for forbidden zone 1.
FORBIDDEN_ZONE_1_Y_MIN = 93

# Bottom boundary for forbidden zone 1.
FORBIDDEN_ZONE_1_Y_MAX = 270

# Left boundary for forbidden zone 2.
FORBIDDEN_ZONE_2_X_MIN = 0

# Right boundary for forbidden zone 2.
FORBIDDEN_ZONE_2_X_MAX = 60

# Top boundary for forbidden zone 2.
FORBIDDEN_ZONE_2_Y_MIN = 50

# Bottom boundary for forbidden zone 2.
FORBIDDEN_ZONE_2_Y_MAX = 280

# Left boundary for forbidden zone 3.
FORBIDDEN_ZONE_3_X_MIN = 0

# Right boundary for forbidden zone 3.
FORBIDDEN_ZONE_3_X_MAX = 60

# Top boundary for forbidden zone 3.
FORBIDDEN_ZONE_3_Y_MIN = 600

# Bottom boundary for forbidden zone 3.
FORBIDDEN_ZONE_3_Y_MAX = 667

# Left boundary for forbidden zone 4.
FORBIDDEN_ZONE_4_X_MIN = 145

# Right boundary for forbidden zone 4.
FORBIDDEN_ZONE_4_X_MAX = 200

# Top boundary for forbidden zone 4.
FORBIDDEN_ZONE_4_Y_MIN = 65

# Bottom boundary for forbidden zone 4.
FORBIDDEN_ZONE_4_Y_MAX = 110

# Left boundary for forbidden zone 5.
FORBIDDEN_ZONE_5_X_MIN = 55

# Right boundary for forbidden zone 5.
FORBIDDEN_ZONE_5_X_MAX = 285

# Top boundary for forbidden zone 5.
FORBIDDEN_ZONE_5_Y_MIN = 660

# Bottom boundary for forbidden zone 5.
FORBIDDEN_ZONE_5_Y_MAX = 725
