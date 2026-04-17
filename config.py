from pathlib import Path


# =========================
# Automatic project paths
# =========================

# This is the bot's home folder on disk. The other file paths below are built from it automatically.
BASE_DIR = Path(__file__).resolve().parent

# This is the folder that stores the PNG images the bot looks for on screen.
ASSETS_DIR = str(BASE_DIR / "Assets")

# This is the folder where the bot writes its log files.
LOGS_DIR = str(BASE_DIR / "logs")


# =========================
# Window, logging, and optional visuals
# =========================

# This is the exact scrcpy window title the bot tries to bind to.
WINDOW_TITLE = "EatventureAuto"

# This is the width the bot asks Windows to resize the game window to.
WINDOW_WIDTH = 300 * 1.2

# This is the height the bot asks Windows to resize the game window to.
WINDOW_HEIGHT = 650 * 1.2

# This turns extra console logging on when you need deeper troubleshooting details.
DEBUG = False

# This is the biggest size one log file is allowed to reach before the bot rolls over to a fresh file.
LOG_FILE_MAX_BYTES = 5 * 1024 * 1024

# This is how many old rolled-over log files the bot keeps.
LOG_FILE_BACKUP_COUNT = 5

# This turns the forbidden-zone overlay on so you can see the blocked click areas on top of the game window.
SHOW_FORBIDDEN_AREA = False


# =========================
# Core template confidence
# =========================

# This is the default confidence floor for ordinary one-off template matches.
MATCH_THRESHOLD = 0.975

# This is the normal confidence floor for regular red icon detection.
RED_ICON_THRESHOLD = 0.924

# This is the confidence floor for the special red icon that means a new level is ready.
NEW_LEVEL_RED_ICON_THRESHOLD = 0.942

# This is the confidence floor for the red icon used to decide whether the stats menu should be opened.
STATS_RED_ICON_THRESHOLD = 0.973

# This is the confidence floor for finding the upgrade station.
UPGRADE_STATION_THRESHOLD = 0.944

# This is the confidence floor for gift box detection.
BOX_THRESHOLD = 0.973

# This is the confidence floor for spotting the unlock button after a level transition.
UNLOCK_THRESHOLD = 0.958

# This is the confidence floor for spotting the main new-level button.
NEW_LEVEL_THRESHOLD = 0.984


# =========================
# Red icon color filter
# =========================

# This is how many separate template hits must agree before a red icon is treated as real.
RED_ICON_MIN_MATCHES = 1

# This is the minimum number of red pixels a candidate must contain before the bot trusts it.
RED_ICON_PIXEL_THRESHOLD = 50

# This is the cleanup kernel size used to remove tiny red specks before the bot counts red pixels.
RED_ICON_DILATE_KERNEL = 3

# This is the first lower HSV bound the bot uses to isolate red pixels.
RED_HSV_LOWER1 = (0, 110, 120)

# This is the first upper HSV bound the bot uses to isolate red pixels.
RED_HSV_UPPER1 = (12, 255, 255)

# This is the second lower HSV bound the bot uses to catch the other side of red in HSV space.
RED_HSV_LOWER2 = (166, 110, 120)

# This is the second upper HSV bound the bot uses to catch the other side of red in HSV space.
RED_HSV_UPPER2 = (179, 255, 255)

# This is the minimum red-dominance ratio a candidate must have before it counts as a real red icon.
RED_ICON_COLOR_MIN_RATIO = 1.35

# This is the maximum red-dominance ratio allowed before the color balance looks suspicious and gets rejected.
RED_ICON_COLOR_MAX_RATIO = 3.35

# This is the minimum average strength of the red channel inside the sampled square.
RED_ICON_COLOR_MIN_MEAN = 56

# This is the size of the square sample the bot checks around a red icon candidate.
RED_ICON_COLOR_SAMPLE_SIZE = 24


# =========================
# Red icon shape filter
# =========================

# This is how many pixels the bot is allowed to slide the template gate while fine-aligning a red icon candidate.
RED_ICON_TEMPLATE_VERIFY_MAX_OFFSET = 2

# This is the minimum amount of the template area that must still look red for the candidate to pass.
RED_ICON_TEMPLATE_MIN_COVERAGE = 0.32

# This is the minimum precision score the candidate must reach against the saved red icon template.
RED_ICON_TEMPLATE_MIN_PRECISION = 0.97

# This is the minimum recall score the candidate must reach against the saved red icon template.
RED_ICON_TEMPLATE_MIN_RECALL = 0.62

# This is the minimum overlap score the live candidate must share with the saved red icon template.
RED_ICON_TEMPLATE_MIN_IOU = 0.48

# This is the minimum color-histogram similarity the candidate must have against the saved red icon template.
RED_ICON_TEMPLATE_COLOR_SIMILARITY = 0.41


# =========================
# Upgrade station color filter
# =========================

# This is the lower HSV bound used to isolate the cyan-blue part of the upgrade station.
UPGRADE_STATION_HSV_LOWER = (90, 95, 190)

# This is the upper HSV bound used to isolate the cyan-blue part of the upgrade station.
UPGRADE_STATION_HSV_UPPER = (107, 220, 255)

# This is the minimum amount of that cyan-blue color that must be present for the station match to count.
UPGRADE_STATION_HSV_MIN_RATIO = 0.52

# This is the minimum general color-match score needed when the bot compares live pixels to a saved template.
COLOR_SIMILARITY_THRESHOLD = 0.32


# =========================
# Mouse movement and click timing
# =========================

# This is the normal pause after a click so the game has time to react.
CLICK_DELAY = 0.043

# This is the normal pause after moving the cursor to a new point.
MOUSE_MOVE_DELAY = 0.017

# This is how long the left mouse button stays held down during a standard click.
MOUSE_DOWN_UP_DELAY = 0.034

# This is how many times the bot retries a click if the cursor is not quite settled on target.
MOUSE_CLICK_RETRY_COUNT = 2

# This is the tiny pause between those click retries.
MOUSE_CLICK_RETRY_SETTLE_DELAY = 0.033

# This is the minimum gap the bot enforces between separate clicks.
MIN_CLICK_INTERVAL = 0.042

# This is how many times the bot retries a cursor move before giving up on exact placement.
MOUSE_MOVE_RETRIES = 2

# This is the pause between cursor move retries.
MOUSE_MOVE_RETRY_DELAY = 0.033

# This is the pause after the cursor first reaches the target before the bot trusts it is settled.
MOUSE_TARGET_SETTLE_DELAY = 0.038

# This is the longest time the bot will wait for the cursor to settle on a target.
MOUSE_TARGET_TIMEOUT = 0.110

# This is how often the bot re-checks the cursor while waiting for it to settle.
MOUSE_TARGET_CHECK_INTERVAL = 0.018

# This is the extra hover pause once the cursor appears to be in the right place.
MOUSE_TARGET_HOVER_DELAY = 0.018

# This is the final stable-hold window the cursor must survive before the click is allowed.
MOUSE_STABILIZE_DURATION = 0.038

# This is how many correction nudges the bot is allowed to make if the cursor is still slightly off.
MOUSE_TARGET_RETRIES = 2

# This is the pause between those correction nudges.
MOUSE_TARGET_CORRECTION_DELAY = 0.036

# This is how many pixels of cursor error still count as "close enough."
MOUSE_POSITION_TOLERANCE = 1

# This is the minimum pre-click settle time the bot always waits even for tiny cursor moves.
MOUSE_PRE_CLICK_STABILIZE_BASE = 0.034

# This is the longest pre-click settle time allowed for longer cursor travel.
MOUSE_PRE_CLICK_STABILIZE_MAX = 0.052

# This is how much extra pre-click settle time gets added as cursor travel distance grows.
MOUSE_PRE_CLICK_STABILIZE_DISTANCE_FACTOR = 0.000023


# =========================
# Scroll search motion
# =========================

# This is the window-relative point where each drag scroll starts.
SCROLL_START_POS = (170, 380)

# This is the base drag distance used for one scroll move.
SCROLL_PIXEL_STEP = 125

# This is the multiplier applied to that base drag distance.
SCROLL_DISTANCE_RATIO = 1

# This is the highest oscillation cycle number the search pattern will reach before wrapping back around.
MAX_SCROLL_CYCLES = 7

# This is how many extra drag legs each wider oscillation cycle adds.
SCROLL_INCREMENT_STEP = 1

# This is the short pause after a scroll before the bot continues the rest of the state.
SCROLL_INTERVAL_PAUSE = 0.080

# This is the settle time after a scroll so the game screen can stop moving.
POST_SCROLL_SETTLE = 0.350

# This is the drag duration for a normal search scroll.
SCROLL_DURATION = 0.200

# This is how many cursor waypoints the bot uses while dragging a scroll.
SCROLL_STEP_COUNT = 16

# This is the minimum gap between one drag gesture and the next.
SCROLL_MIN_INTERVAL = 0.080

# This is the settle time after the drag helper releases the mouse button.
SCROLL_SETTLE_DELAY = 0.250


# =========================
# Main loop and state pacing
# =========================

# This is the idle sleep used by the launcher loop while the bot is not busy doing work.
MAIN_LOOP_DELAY = 0.016

# This is the short pause inserted after certain major state actions.
STATE_DELAY = 0.068

# This is the fallback minimum gap between two runs of the same state handler.
STATE_MIN_INTERVAL_DEFAULT = 0.058

# This table lets each state have its own minimum re-run delay.
STATE_MIN_INTERVALS = {
    # This is the minimum gap between red-icon scan passes.
    "FIND_RED_ICONS": 0.068,
    # This is the minimum gap between box-opening passes.
    "OPEN_BOXES": 0.068,
    # This is the minimum gap between scroll handlers.
    "SCROLL": 0.205,
    # This is the minimum gap between upgrade-station search attempts.
    "SEARCH_UPGRADE_STATION": 0.058,
    # This is the minimum gap between red-icon click handlers.
    "CLICK_RED_ICON": 0.050,
    # This is the minimum gap between upgrade-station spam-click handlers.
    "HOLD_UPGRADE_STATION": 0.050,
    # This is the minimum gap between unlock checks.
    "CHECK_UNLOCK": 0.056,
    # This is the minimum gap between manual new-level acknowledgement passes.
    "CHECK_NEW_LEVEL": 0.068,
    # This is the minimum gap between stats-upgrade passes.
    "UPGRADE_STATS": 0.068,
    # This is the minimum gap between level-transition attempts.
    "TRANSITION_LEVEL": 0.064,
    # This is the minimum gap between unlock waiting polls.
    "WAIT_FOR_UNLOCK": 0.044,
}


# =========================
# Fixed screen targets
# =========================

# This is the horizontal offset from a red icon to the station behind it that the bot actually wants to click.
RED_ICON_OFFSET_X = 10

# This is the vertical offset from a red icon to the station behind it that the bot actually wants to click.
RED_ICON_OFFSET_Y = 10

# This is the backup position used for the second travel-confirmation click during a level transition.
LEVEL_TRANSITION_POS = (174, 520)

# This is the harmless idle click position the bot uses to clear hover states and reset focus.
IDLE_CLICK_POS = (2, 390)

# This is the point the bot rapid-clicks inside the stats menu after opening it.
STATS_UPGRADE_POS = (270, 304)

# This is the button position used to open the stats menu.
STATS_UPGRADE_BUTTON_POS = (310, 698)

# This is the fixed position used to confirm the "new level" button in the manual acknowledgement path.
NEW_LEVEL_BUTTON_POS = (30, 692)


# =========================
# High-speed click loops
# =========================

# This is how long the main upgrade-station rapid-click burst lasts.
SPAM_CLICK_DURATION = 4.0

# This is the gap between individual clicks during that main rapid-click burst.
SPAM_CLICK_DELAY = 0.016

# This is the random wiggle range added to each rapid click. Zero keeps every click perfectly still.
SPAM_CLICK_JITTER = 0

# This is how long the mouse button stays held down during each high-speed rapid click.
RAPID_CLICK_DOWN_UP_DELAY = 0.008

# This is the point where the rapid-click scheduler stops sleeping and starts fine spinning for tighter timing.
RAPID_CLICK_SPIN_THRESHOLD = 0.004

# This is the wait between upgrade-station search attempts when the station is not found immediately.
UPGRADE_SEARCH_INTERVAL = 0.072

# This is how long the stats-menu rapid-click burst lasts.
STATS_UPGRADE_CLICK_DURATION = 2.0

# This is the gap between individual clicks during the stats-menu rapid-click burst.
STATS_UPGRADE_CLICK_DELAY = 0.016

# This is the pause after the bot taps its idle point and before it continues.
IDLE_CLICK_SETTLE_DELAY = 0.052


# =========================
# Detection merge and retry rules
# =========================

# This is the minimum spacing between separate red-icon matches so duplicates do not pile up.
RED_ICON_MIN_DISTANCE = 80

# This is how close two red-icon hits can be before the bot merges them into one target.
RED_ICON_MERGE_PROXIMITY = 10

# This is the grid size used when the bot groups nearby red-icon matches together.
RED_ICON_MERGE_BUCKET_SIZE = 10

# This is how many times the bot will search for the upgrade station before giving up for that red icon.
UPGRADE_STATION_SEARCH_MAX_ATTEMPTS = 3

# This is how much easier the upgrade-station threshold becomes after repeated misses.
UPGRADE_STATION_RELAXED_THRESHOLD_DROP = 0.028

# This is the attempt number where the relaxed upgrade-station threshold starts being used.
UPGRADE_STATION_RELAXED_ATTEMPT_TRIGGER = 1


# =========================
# Click safety checks
# =========================

# This is the pause before the first forbidden-zone safety check right before a click.
FORBIDDEN_ZONE_PRECLICK_VALIDATION_DELAY = 0.016

# This is the pause between the first and second forbidden-zone safety checks.
FORBIDDEN_ZONE_DOUBLE_CHECK_DELAY = 0.016


# =========================
# Transition and search regions
# =========================

# This is how many times the bot will look for the new-level button before abandoning the transition.
LEVEL_TRANSITION_MAX_ATTEMPTS = 5

# This turns the dedicated new-level interrupt system on.
NEW_LEVEL_INTERRUPT_ENABLED = True

# This is the minimum gap between one interrupt scan and the next.
NEW_LEVEL_INTERRUPT_POLL_INTERVAL = 0.050

# This is how many consecutive button detections are required before the bot trusts a button-based interrupt.
NEW_LEVEL_INTERRUPT_BUTTON_CONFIRMATIONS = 1

# This is how many consecutive red-icon detections are required before the bot trusts a red-icon-based interrupt.
NEW_LEVEL_INTERRUPT_RED_ICON_CONFIRMATIONS = 2

# This is the short pause between those confirmation checks.
NEW_LEVEL_INTERRUPT_CONFIRMATION_DELAY = 0.040

# This is the cooldown after an interrupt fires so the same event does not immediately fire again.
NEW_LEVEL_INTERRUPT_COOLDOWN = 0.250

# This is the pause after clicking the "new level" button in the manual acknowledgement path.
NEW_LEVEL_BUTTON_DELAY = 0.105

# This is the animation buffer after a successful travel-confirmation click.
TRANSITION_POST_CLICK_DELAY = 0.240

# This is the wait between repeated transition attempts when the button is not found right away.
TRANSITION_RETRY_DELAY = 0.100

# This is the left edge of the small screen area where the new-level red icon is expected.
NEW_LEVEL_RED_ICON_X_MIN = 40

# This is the right edge of the small screen area where the new-level red icon is expected.
NEW_LEVEL_RED_ICON_X_MAX = 60

# This is the top edge of the small screen area where the new-level red icon is expected.
NEW_LEVEL_RED_ICON_Y_MIN = 665

# This is the bottom edge of the small screen area where the new-level red icon is expected.
NEW_LEVEL_RED_ICON_Y_MAX = 680

# This is the left edge of the small screen area where the new-level button is expected during interrupt polling.
NEW_LEVEL_INTERRUPT_BUTTON_X_MIN = 0

# This is the right edge of the small screen area where the new-level button is expected during interrupt polling.
NEW_LEVEL_INTERRUPT_BUTTON_X_MAX = 85

# This is the top edge of the small screen area where the new-level button is expected during interrupt polling.
NEW_LEVEL_INTERRUPT_BUTTON_Y_MIN = 620

# This is the bottom edge of the small screen area where the new-level button is expected during interrupt polling.
NEW_LEVEL_INTERRUPT_BUTTON_Y_MAX = 720

# This is the left edge of the small screen area where the stats red icon is expected.
UPGRADE_RED_ICON_X_MIN = 280

# This is the right edge of the small screen area where the stats red icon is expected.
UPGRADE_RED_ICON_X_MAX = 310

# This is the top edge of the small screen area where the stats red icon is expected.
UPGRADE_RED_ICON_Y_MIN = 665

# This is the bottom edge of the small screen area where the stats red icon is expected.
UPGRADE_RED_ICON_Y_MAX = 680

# This is the normal bottom crop used for most gameplay searches.
MAX_SEARCH_Y = 660

# This is the deeper bottom crop used when the bot also needs to watch the lower user-interface band.
EXTENDED_SEARCH_Y = 720


# =========================
# Adaptive timing tuner
# =========================

# This turns the live timing tuner on.
ADAPTIVE_TUNER_ENABLED = True

# This is how quickly the tuner reacts to new click and search results.
ADAPTIVE_TUNER_ALPHA = 0.25

# This is the click success rate below which the tuner starts slowing clicks down.
ADAPTIVE_TUNER_CLICK_LOW_THRESHOLD = 0.89

# This is the click success rate above which the tuner starts speeding clicks up again.
ADAPTIVE_TUNER_CLICK_HIGH_THRESHOLD = 0.993

# This is the search success rate below which the tuner slows search retries down.
ADAPTIVE_TUNER_SEARCH_LOW_THRESHOLD = 0.89

# This is the search success rate above which the tuner speeds search retries back up.
ADAPTIVE_TUNER_SEARCH_HIGH_THRESHOLD = 0.989

# This is how much click delay increases when click reliability drops.
ADAPTIVE_TUNER_CLICK_DELAY_STEP = 0.002

# This is how much move delay increases when click reliability drops.
ADAPTIVE_TUNER_MOVE_DELAY_STEP = 0.001

# This is how much click delay decreases when click reliability is excellent.
ADAPTIVE_TUNER_CLICK_DECREMENT = 0.001

# This is how much move delay decreases when click reliability is excellent.
ADAPTIVE_TUNER_MOVE_DECREMENT = 0.001

# This is how much the retry gap grows when search reliability drops.
ADAPTIVE_TUNER_SEARCH_INTERVAL_STEP = 0.006

# This is how much the retry gap shrinks when search reliability is excellent.
ADAPTIVE_TUNER_SEARCH_DECREMENT = 0.003

# This is the fastest click delay the tuner is allowed to use.
ADAPTIVE_TUNER_MIN_CLICK_DELAY = 0.041

# This is the slowest click delay the tuner is allowed to use.
ADAPTIVE_TUNER_MAX_CLICK_DELAY = 0.049

# This is the fastest move delay the tuner is allowed to use.
ADAPTIVE_TUNER_MIN_MOVE_DELAY = 0.017

# This is the slowest move delay the tuner is allowed to use.
ADAPTIVE_TUNER_MAX_MOVE_DELAY = 0.022

# This is the fastest search retry interval the tuner is allowed to use.
ADAPTIVE_TUNER_MIN_SEARCH_INTERVAL = 0.068

# This is the slowest search retry interval the tuner is allowed to use.
ADAPTIVE_TUNER_MAX_SEARCH_INTERVAL = 0.086


# =========================
# Vision optimizer
# =========================

# This turns the self-adjusting vision thresholds on.
AI_VISION_ENABLED = True

# This is the normal blend rate for vision-threshold updates.
AI_VISION_ALPHA = 0.12

# This is the fastest blend rate the vision optimizer is allowed to use.
AI_VISION_ALPHA_MAX = 0.24

# This is the extra blend bonus added when the bot sees a very confident match.
AI_VISION_CONFIDENCE_BOOST = 0.10

# This is the confidence level where that extra blend bonus starts kicking in.
AI_VISION_CONFIDENCE_THRESHOLD = 0.94

# This is the lowest box threshold the vision optimizer is allowed to fall to.
AI_BOX_THRESHOLD_MIN = 0.90

# This is the highest box threshold the vision optimizer is allowed to rise to.
AI_BOX_THRESHOLD_MAX = 0.992

# This is how many missed box scans happen before the optimizer lowers the box threshold.
AI_BOX_MISS_WINDOW = 4

# This is how much the box threshold is lowered when that miss window is reached.
AI_BOX_MISS_STEP = 0.0025

# This is the lowest red-icon threshold the optimizer is allowed to use.
AI_RED_ICON_THRESHOLD_MIN = 0.906

# This is the highest red-icon threshold the optimizer is allowed to use.
AI_RED_ICON_THRESHOLD_MAX = 0.938

# This is the safety margin subtracted from recent red-icon confidence before saving a new target threshold.
AI_RED_ICON_MARGIN = 0.018

# This is how many missed red-icon scans happen before the optimizer lowers the red-icon threshold.
AI_RED_ICON_MISS_WINDOW = 4

# This is how much the red-icon threshold is lowered when that miss window is reached.
AI_RED_ICON_MISS_STEP = 0.0020

# This is the lowest new-level button threshold the optimizer is allowed to use.
AI_NEW_LEVEL_THRESHOLD_MIN = 0.975

# This is the highest new-level button threshold the optimizer is allowed to use.
AI_NEW_LEVEL_THRESHOLD_MAX = 0.992

# This is how many missed new-level button scans happen before the threshold is lowered.
AI_NEW_LEVEL_MISS_WINDOW = 4

# This is how much the new-level button threshold is lowered when that miss window is reached.
AI_NEW_LEVEL_MISS_STEP = 0.0020

# This is the lowest new-level red-icon threshold the optimizer is allowed to use.
AI_NEW_LEVEL_RED_ICON_THRESHOLD_MIN = 0.934

# This is the highest new-level red-icon threshold the optimizer is allowed to use.
AI_NEW_LEVEL_RED_ICON_THRESHOLD_MAX = 0.987

# This is how many missed new-level red-icon scans happen before that threshold is lowered.
AI_NEW_LEVEL_RED_ICON_MISS_WINDOW = 4

# This is how much the new-level red-icon threshold is lowered when that miss window is reached.
AI_NEW_LEVEL_RED_ICON_MISS_STEP = 0.0015

# This is the lowest upgrade-station threshold the optimizer is allowed to use.
AI_UPGRADE_STATION_THRESHOLD_MIN = 0.924

# This is the highest upgrade-station threshold the optimizer is allowed to use.
AI_UPGRADE_STATION_THRESHOLD_MAX = 0.968

# This is how many missed upgrade-station scans happen before the threshold is lowered.
AI_UPGRADE_STATION_MISS_WINDOW = 3

# This is how much the upgrade-station threshold is lowered when that miss window is reached.
AI_UPGRADE_STATION_MISS_STEP = 0.0035

# This is the lowest stats-icon threshold the optimizer is allowed to use.
AI_STATS_UPGRADE_THRESHOLD_MIN = 0.93

# This is the highest stats-icon threshold the optimizer is allowed to use.
AI_STATS_UPGRADE_THRESHOLD_MAX = 0.988

# This is how many missed stats-icon scans happen before the threshold is lowered.
AI_STATS_UPGRADE_MISS_WINDOW = 4

# This is how much the stats-icon threshold is lowered when that miss window is reached.
AI_STATS_UPGRADE_MISS_STEP = 0.0020

# This is the file where the bot saves learned vision thresholds between runs.
AI_VISION_STATE_FILE = str(BASE_DIR / "memory" / "vision_state.json")

# This is how often the bot is allowed to write the vision-state file.
AI_VISION_SAVE_INTERVAL = 15.0


# =========================
# Historical timing learner
# =========================

# This turns the background timing learner on.
AI_LEARNING_ENABLED = True

# This is the file where the bot saves its historical timing memory.
AI_LEARNING_STATE_FILE = str(BASE_DIR / "memory" / "learning_state.json")

# This is how often the learner is allowed to write its memory file.
AI_LEARNING_SAVE_INTERVAL = 5.0

# This is the maximum number of past completion records the learner keeps.
AI_LEARNING_RECORDS_LIMIT = 256

# This is how long shutdown waits for the learner thread to stop cleanly.
AI_LEARNING_THREAD_JOIN_TIMEOUT = 0.5

# This is how often the learner thread wakes up to review recent results.
AI_LEARNING_THREAD_INTERVAL = 0.15

# This is the small recent-run window used for quicker learning updates.
AI_LEARNING_PAIR_WINDOW = 3

# This is the larger recent-run window used for broader learning updates.
AI_LEARNING_BATCH_WINDOW = 10

# This is the blend rate used when the learner applies a better timing profile.
AI_LEARNING_EMA_ALPHA = 0.22

# This is how many of the fastest recent runs get blended together into one candidate profile.
AI_LEARNING_PROFILE_BLEND_TOP_K = 4

# This is the minimum improvement ratio required before a learned profile is worth applying.
AI_LEARNING_MIN_IMPROVEMENT_RATIO = 0.025

# This is the cooldown between one learned-profile application and the next.
AI_LEARNING_APPLY_COOLDOWN = 0.9

# This is the fastest click delay the learner is allowed to save or apply.
AI_LEARNING_MIN_CLICK_DELAY = 0.041

# This is the slowest click delay the learner is allowed to save or apply.
AI_LEARNING_MAX_CLICK_DELAY = 0.049

# This is the fastest move delay the learner is allowed to save or apply.
AI_LEARNING_MIN_MOVE_DELAY = 0.017

# This is the slowest move delay the learner is allowed to save or apply.
AI_LEARNING_MAX_MOVE_DELAY = 0.022

# This is the fastest search retry interval the learner is allowed to save or apply.
AI_LEARNING_MIN_SEARCH_INTERVAL = 0.068

# This is the slowest search retry interval the learner is allowed to save or apply.
AI_LEARNING_MAX_SEARCH_INTERVAL = 0.086


# =========================
# Background helper timing
# =========================

# This is how often the forbidden-zone overlay refreshes its position on screen.
OVERLAY_UPDATE_INTERVAL = 0.033

# This is the minimum sleep the learner loop uses so it never spins too aggressively.
LEARNING_LOOP_MIN_SLEEP = 0.033

# This is how long a freshly captured screenshot stays reusable before the bot grabs a new one.
CAPTURE_CACHE_TTL = 0.033

# This is how long the bot waits after clicking unlock before checking whether it disappeared.
UNLOCK_REGISTER_WAIT = 0.072

# This is the gap between unlock-button polls while the bot waits for the next level to fully open.
UNLOCK_POLL_INTERVAL = 0.036

# This is the shortest drag duration the scroll helper is allowed to use.
DRAG_MIN_DURATION = 0.050

# This is the default drag duration used when a caller does not provide one.
DEFAULT_DRAG_DURATION = 0.250


# =========================
# Telegram notifications
# =========================

# Turn this on if you want Telegram start, stop, and level notifications.
TELEGRAM_ENABLED = False

# Put your Telegram bot token here if you want notifications.
TELEGRAM_BOT_TOKEN = ""

# Put the Telegram chat ID here if you want notifications.
TELEGRAM_CHAT_ID = ""


# =========================
# Forbidden click zones
# =========================

# This is the list of rectangles the bot must never click.
# Each zone uses image-space coordinates:
# x_min and x_max are the left and right edges.
# y_min and y_max are the top and bottom edges.
FORBIDDEN_ZONES = [
    # This blocks the wide lower bar where taps are likely to hit menus instead of restaurant targets.
    {
        "name": "General bottom bar",
        "coordinate_space": "image",
        "x_min": 60,
        "x_max": 280,
        "y_min": 668,
        "y_max": 1000,
    },
    # This blocks the vertical menu stack on the right side of the screen.
    {
        "name": "Zone 1: Right side menu area",
        "coordinate_space": "image",
        "x_min": 290,
        "x_max": 350,
        "y_min": 93,
        "y_max": 320,
    },
    # This blocks the upper-left utility area where non-gameplay buttons can appear.
    {
        "name": "Zone 2: Left side top menu area",
        "coordinate_space": "image",
        "x_min": 0,
        "x_max": 60,
        "y_min": 50,
        "y_max": 280,
    },
    # This blocks the lower-left utility area near side controls and menu buttons.
    {
        "name": "Zone 3: Left side bottom menu area",
        "coordinate_space": "image",
        "x_min": 0,
        "x_max": 60,
        "y_min": 590,
        "y_max": 667,
    },
    # This blocks the top-center notification strip so pop-ups do not get clicked by mistake.
    {
        "name": "Zone 4: Top center notification area",
        "coordinate_space": "image",
        "x_min": 145,
        "x_max": 200,
        "y_min": 65,
        "y_max": 110,
    },
    # This blocks the bottom navigation row where permanent user-interface buttons live.
    {
        "name": "Zone 5: Bottom navigation bar",
        "coordinate_space": "image",
        "x_min": 55,
        "x_max": 285,
        "y_min": 660,
        "y_max": 725,
    },
    # This blocks the top bar where the header and resource counters sit.
    {
        "name": "Zone 6: Top bar area",
        "coordinate_space": "image",
        "x_min": 0,
        "x_max": 360,
        "y_min": 0,
        "y_max": 70,
    },
]
