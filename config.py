from pathlib import Path

###################################
###    WINDOW & UI SETTINGS     ###
###################################

# Exact title of the scrcpy window used for window handle detection
WINDOW_TITLE = "EatventureAuto"

# Target window dimensions for capturing and relative coordinate positioning
WINDOW_WIDTH = 300 * 1.2
WINDOW_HEIGHT = 650 * 1.2

# Debug and visualization toggles
DEBUG = True
DEBUG_VISION = False                # Enables on-screen masked view for red pixel density tuning
ShowForbiddenArea = False           # Enables a transparent red overlay showing forbidden zones


###################################
###   DIRECTORY & FILE PATHS    ###
###################################

PROJECT_ROOT = Path(__file__).resolve().parent
TEMPLATES_DIR = str(PROJECT_ROOT / "templates")  # Folder containing template images for matching
ASSETS_DIR = str(PROJECT_ROOT / "Assets")        # Folder containing game asset sub-templates
LOGS_DIR = str(PROJECT_ROOT / "logs")            # Folder for bot logs and transient diagnostics
MEMORY_DIR = str(PROJECT_ROOT / "memory")        # Folder for persistent AI vision/history state


###################################
###   DETECTION THRESHOLDS      ###
###################################

# General template matching confidence floor (0.0–1.0)
MATCH_THRESHOLD = 0.98              # Default threshold passed to ImageMatcher constructor

# Per-asset detection thresholds
RED_ICON_THRESHOLD = 0.92           # Runtime probe frames cluster near 0.92-0.934, so keep the floor low enough to admit valid icons before structural gates decide
NEW_LEVEL_RED_ICON_THRESHOLD = 0.94 # Confidence for red-icon-based new-level detection
STATS_RED_ICON_THRESHOLD = 0.97     # Confidence for stats upgrade icon detection
UPGRADE_STATION_THRESHOLD = 0.95    # Confidence for upgrade station template match
BOX_THRESHOLD = 0.97                # Confidence for gift box template match
UNLOCK_THRESHOLD = 0.95             # Confidence for unlock button template match
NEW_LEVEL_THRESHOLD = 0.98          # Confidence for new level / travel button template match

# Red icon gate settings
RED_ICON_MIN_MATCHES = 1            # Minimum number of simultaneous red icon matches required
NEW_LEVEL_RED_ICON_MIN_MATCHES = 1  # Minimum matches for new-level red icon detection
RED_ICON_PIXEL_THRESHOLD = 52       # Minimum masked red pixel count in ROI to confirm a genuine red blob
                                    # Kept just above the smallest true template footprint so structural filters, not a blunt pixel floor, do the false-positive rejection
RED_ICON_DILATE_KERNEL = 3          # Morphological kernel size for noise removal and blob reconnection

# Red color HSV bounds for red pixel counting
# Derived from programmatic HSV extraction of all 16 RedIcon asset PNGs.
# 78.2% of red icon pixels fall in H:0-10, 8.6% wrap at H:160-179.
# S floor raised to 120 and V floor to 130 to reject low-saturation
# environmental reds (rooftops, faded textures) that previously passed.
RED_HSV_LOWER1 = (0, 120, 130)      # Low-hue red band lower bound
RED_HSV_UPPER1 = (10, 255, 255)     # Low-hue red band upper bound
RED_HSV_LOWER2 = (165, 120, 130)    # High-hue red wrap-around lower bound
RED_HSV_UPPER2 = (179, 255, 255)    # High-hue red wrap-around upper bound

# Red icon color verification (BGR channel ratio check)
RED_ICON_COLOR_CHECK = True         # Enable red-dominance verification after template match
RED_ICON_COLOR_MIN_RATIO = 1.35     # Red channel must exceed max(G,B) by this factor
RED_ICON_COLOR_MAX_RATIO = 3.60     # Reject overly solid-red badges that lack the icon family's white/red balance
RED_ICON_COLOR_MIN_MEAN = 55        # Minimum absolute red channel mean intensity
RED_ICON_COLOR_SAMPLE_SIZE = 24     # Pixel ROI half-size for color verification

# Red icon structural verification (template-shape gate)
RED_ICON_TEMPLATE_VERIFY = True         # Re-check matched candidates against the template's red-mask footprint
RED_ICON_TEMPLATE_VERIFY_MAX_OFFSET = 1 # Search +/- this many pixels when aligning a matched candidate to its template ROI
RED_ICON_TEMPLATE_MIN_COVERAGE = 0.28   # Runtime red coverage inside the template mask must stay above this floor
RED_ICON_TEMPLATE_MIN_PRECISION = 0.55  # Runtime red pixels must mostly land where the template expects them
RED_ICON_TEMPLATE_MIN_RECALL = 0.55     # The candidate must recover enough of the template's red footprint
RED_ICON_TEMPLATE_MIN_IOU = 0.38        # Overlap floor between runtime and template red masks
RED_ICON_TEMPLATE_COLOR_SIMILARITY = 0.42  # Lowered from the overly strict 0.72; runtime demo frames pass near 0.42-0.43 while known bad samples remain below this floor

# Red icon position refinement
RED_ICON_VERIFY_PADDING = 24        # Pixel padding around detection point for presence verification
RED_ICON_VERIFY_TOLERANCE = 12      # Max displacement for a match to still be considered "at" position
RED_ICON_REFINE_RADIUS = 18         # Search radius for sub-pixel position refinement
RED_ICON_REFINE_THRESHOLD_DROP = 0.02  # Threshold relaxation during refinement pass

# Upgrade station detection refinement
UPGRADE_STATION_COLOR_CHECK = True  # Enable histogram color verification for upgrade station
UPGRADE_STATION_REFINE_RADIUS = 28  # Search radius for upgrade station template refinement
UPGRADE_STATION_CLICK_REFINE_RADIUS = 18  # Search radius for click-target refinement

# Upgrade Station HSV color gate (derived from upgradeStation.png plus demo-frame verification)
# Windows PrintWindow capture keeps frames in BGR, but runtime station pixels still cluster
# tightly around a bright cyan band. The prior window was wide enough that pale cyan UI
# panels and background highlights could satisfy the gate with only ~40% ROI coverage.
# These tighter bounds preserve true station ROIs (~70-77% runtime pass ratio) while
# forcing mixed/background matches well below the acceptance floor.
UPGRADE_STATION_HSV_LOWER = (90, 100, 195)  # Runtime-safe lower bound for the station's cyan core
UPGRADE_STATION_HSV_UPPER = (106, 210, 255) # Tight upper hue cap to exclude greener/bluer lookalikes
UPGRADE_STATION_HSV_MIN_RATIO = 0.55        # Require majority ROI coverage from the station color band

# Color similarity threshold for histogram-based verification
# Used by upgrade station and box detection to reject background matches
# whose color distribution doesn't correlate with the template.
COLOR_SIMILARITY_THRESHOLD = 0.7    # Minimum histogram correlation (0.0–1.0)

# Explicit verification fallbacks used by a few helper paths in bot.py.
VERIFY_THRESHOLD = 0.97             # Conservative follow-up template verification floor
VERIFY_PADDING = 32                 # ROI padding for helper verification passes


###################################
###   MOUSE & INTERACTION       ###
###################################

# Cheetah pounce profile:
# The stalk phase is handled in the scan/search settings below.
# Once a target is confirmed, every post-confirmation interaction delay goes to zero.
CLICK_DELAY = 0.0
MOUSE_MOVE_DELAY = 0.0
MOUSE_DOWN_UP_DELAY = 0.0
DOUBLE_CLICK_DELAY = 0.0

# Mouse movement retry and correction
MOUSE_MOVE_RETRIES = 1              # One immediate correction pass keeps accuracy without adding dwell
MOUSE_MOVE_RETRY_DELAY = 0.0
MOUSE_TARGET_SETTLE_DELAY = 0.0
MOUSE_TARGET_TIMEOUT = 0.0
MOUSE_TARGET_CHECK_INTERVAL = 0.0
MOUSE_TARGET_HOVER_DELAY = 0.0
MOUSE_STABILIZE_DURATION = 0.0
MOUSE_TARGET_RETRIES = 1
MOUSE_TARGET_CORRECTION_DELAY = 0.0
MOUSE_POSITION_TOLERANCE = 1        # Permit a 1 px landing tolerance before forcing a hard snap

# Pre-click stabilization (distance-adaptive)
MOUSE_PRE_CLICK_STABILIZE_BASE = 0.0
MOUSE_PRE_CLICK_STABILIZE_MAX = 0.0
MOUSE_PRE_CLICK_STABILIZE_DISTANCE_FACTOR = 0.0

# Click retry logic
MOUSE_CLICK_RETRY_COUNT = 2         # Max click retries on registration failure
MOUSE_CLICK_RETRY_SETTLE_DELAY = 0.0
MIN_CLICK_INTERVAL = 0.0            # No artificial pacing between confirmed click dispatches


###################################
###    SCROLLING BEHAVIOR       ###
###################################

# Scroll origin for oscillating drag operations
SCROLL_START_POS = (170, 380)       # (x, y) relative to window client area

# Scroll distance parameters
SCROLL_PIXEL_STEP = 150              # Pixels per single scroll step
SCROLL_DISTANCE_RATIO = 1           # Multiplier applied to scroll distance
SCROLL_VERIFICATION_DISTANCE = 180  # Pixel distance for new-level verification scroll

# Incremental Oscillating Search strategy
MAX_SCROLL_CYCLES = 6              # Maximum oscillation cycles per search invocation
SCROLL_INCREMENT_STEP = 2           # Amplitude increment per cycle pair

# Stalk phase:
# Slow the scan loop down so captures happen on clean, settled frames.
SCROLL_RELEASE_THINK_DELAY = 0.020
POST_SCROLL_VISION_THINK_DELAY = 0.090
POST_SCROLL_CONFIRM_THINK_DELAY = 0.030
OSCILLATION_REVERSAL_THINK_DELAY = 0.025
SCROLL_INTERVAL_PAUSE = 0.015

# Compose the full post-scroll vision settle from two explicit micro-pause stages:
# one for frame stabilization and one for the final confirm-before-scan beat.
POST_SCROLL_SETTLE = POST_SCROLL_VISION_THINK_DELAY + POST_SCROLL_CONFIRM_THINK_DELAY

# Direction changes only need a small boundary-think pause before the next scan pass.
CYCLE_PAUSE_DURATION = OSCILLATION_REVERSAL_THINK_DELAY

# Keep drag motion smooth and readable so vision always scans after a settled glide.
SCROLL_DURATION = 0.24
SCROLL_STEP_COUNT = 24

# The drag path already includes explicit settle windows; this minimum interval only
# prevents back-to-back scroll commands from stacking on the same scheduler tick.
SCROLL_MIN_INTERVAL = 0.0
OSCILLATION_CYCLE_COOLDOWN = 0.0    # No extra cooldown once a target is found; commit immediately

# Reuse the dedicated release-think micro-pause so every scroll consumer gets the
# same short mechanical settle before any higher-level vision waits are added.
SCROLL_SETTLE_DELAY = SCROLL_RELEASE_THINK_DELAY


###################################
###    FSM & STATE TIMING       ###
###################################

# Let the FSM hand work off immediately after a state returns; the scan states below
# carry the deliberate cadence, while action states stay delay-free.
MAIN_LOOP_DELAY = 0.0
STATE_DELAY = 0.0
STATE_MIN_INTERVAL_DEFAULT = 0.0

# Only the hunting/stalk states keep deliberate pacing. Pounce states must remain immediate.
STATE_MIN_INTERVALS = {
    "FIND_RED_ICONS": 0.080,
    "OPEN_BOXES": 0.040,
    "SCROLL": 0.050,
    "SEARCH_UPGRADE_STATION": 0.085,
    "CLICK_RED_ICON": 0.0,
    "HOLD_UPGRADE_STATION": 0.0,
    "CHECK_UNLOCK": 0.0,
    "CHECK_NEW_LEVEL": 0.0,
    "UPGRADE_STATS": 0.0,
}

# Red icon click offset (applied after detection)
RED_ICON_OFFSET_X = 10              # Horizontal offset from detected center to click point
RED_ICON_OFFSET_Y = 10              # Vertical offset from detected center to click point

# Fixed UI click positions (relative to window client area)
NEW_LEVEL_POS = (171, 434)          # Travel / new level confirmation button
LEVEL_TRANSITION_POS = (174, 520)   # Level transition confirmation button
IDLE_CLICK_POS = (2, 390)           # Safe idle click position (keeps game awake)
STATS_UPGRADE_POS = (270, 304)      # Stats upgrade tap target during stat boost loop
STATS_UPGRADE_BUTTON_POS = (310, 698)  # Stats upgrade menu open button
NEW_LEVEL_BUTTON_POS = (30, 692)    # New level acknowledgement button

# Upgrade station interaction timing
# DEPRECATED: UPGRADE_HOLD_DURATION is no longer used for the primary
# upgrade interaction. Retained as fallback for hold_at() if needed elsewhere.
UPGRADE_HOLD_DURATION = 6           # (Deprecated) Duration (seconds) for legacy hold
UPGRADE_CLICK_INTERVAL = 0.001      # Learning/tuner mirror of the fastest safe rapid-click cadence

# Spam-click configuration for upgrade station interaction
# Replaces the old click-and-hold mechanic with rapid sequential left clicks.
# These are scheduler intervals, not post-action waits; keep them barely above zero
# because mouse_controller.spam_click_at() rejects <= 0.
SPAM_CLICK_DURATION = 4.0           # Total duration (seconds) to spam-click the upgrade station
SPAM_CLICK_DELAY = 0.011            # Smallest functional positive interval accepted by the rapid-click scheduler
SPAM_CLICK_JITTER = 0               # Max random pixel offset to vary click position (0 = disabled)
RAPID_CLICK_DOWN_UP_DELAY = 0.11     # No dwell between down/up on the precise click path
RAPID_CLICK_SPIN_THRESHOLD = 0.11    # No extra spin wait before each scheduled rapid click

# Upgrade-station retries must wait long enough to beat the capture cache, but not
# so long that the bot stares at a settled screen without refreshing its search.
UPGRADE_SEARCH_INTERVAL = 0.090     # Deliberate re-scan cadence during the stalk/search phase

STATS_UPGRADE_CLICK_DURATION = 2    # Duration (seconds) of rapid stat upgrade tap loop
STATS_UPGRADE_CLICK_DELAY = 0.001   # Same near-zero scheduler interval used for pounce-stage stat taps
STATS_ICON_PADDING = 20             # Pixel padding for stats icon bounding box

# Idle clicks are only there to keep the UI awake, so they should never stall the next scan.
IDLE_CLICK_SETTLE_DELAY = 0.0

# A slightly shorter cooldown keeps the keep-alive tap available sooner in sparse
# screens without turning it into a noisy extra action on every pass.
IDLE_CLICK_COOLDOWN = 0.0

# Red icon spatial deduplication
RED_ICON_MIN_DISTANCE = 80          # Minimum pixel distance between distinct red icon detections
RED_ICON_MERGE_PROXIMITY = 10       # Distance within which detections are merged as duplicates
RED_ICON_MERGE_BUCKET_SIZE = 10     # Bucket width for spatial hashing during merge

# Upgrade station search retries
UPGRADE_STATION_SEARCH_MAX_ATTEMPTS = 5     # Max attempts per upgrade station search cycle
UPGRADE_STATION_RELAXED_THRESHOLD_DROP = 0.04  # Threshold reduction for relaxed retry attempts
UPGRADE_STATION_RELAXED_ATTEMPT_TRIGGER = 1    # Attempt number at which relaxed threshold activates

# Performance caching
# The screenshot cache should only coalesce calls that happen on the same visual
# frame. Keep it close to one 60 FPS frame so CV sees fresh imagery instead of
# spinning on stale captures while still deduplicating same-tick requests.
CAPTURE_CACHE_TTL = 0.016

# New-level red icon checks benefit from the same policy: keep tiny same-frame reuse,
# but force a new capture quickly once the UI has had time to change.
NEW_LEVEL_RED_ICON_CACHE_TTL = 0.012

# Keep the temporal stability window long enough to ride out short CV flicker and
# force a more deliberate confirm-before-pounce rhythm.
RED_ICON_STABILITY_CACHE_TTL = 1.6

# Tighten the spatial radius slightly so confirmation stays decisive and tied to the
# same on-screen icon instead of blending nearby red noise into one track.
RED_ICON_STABILITY_RADIUS = 10

# Require one more temporal confirmation than before so the scan phase remains deliberate.
RED_ICON_STABILITY_MIN_HITS = 4

# A smaller history buffer matches the shorter TTL and keeps the temporal gate focused
# on recent evidence instead of carrying too much already-obsolete icon state.
RED_ICON_STABILITY_MAX_HISTORY = 10

# Queue discipline: evaluate only the best target per scan so the bot commits decisively.
RED_ICON_MAX_PER_SCAN = 1
RED_ICON_PRIORITY_TEMPLATE_LIMIT = 6
WAIT_FOR_UNLOCK_MAX_ATTEMPTS = 50


###################################
###  FORBIDDEN ZONE ENFORCEMENT ###
###################################

# Forbidden-zone debounced arbitration (safe vs. forbidden icon classification)
FORBIDDEN_ZONE_DETECTION_PRE_DELAY = 0.015   # Let the frame settle before classifying safe vs. forbidden assets
FORBIDDEN_ZONE_DETECTION_POST_DELAY = 0.015  # Second deliberate read before trusting the arbitration result
FORBIDDEN_ZONE_DEBOUNCE_TICKS = 2            # Two reads avoid one-frame forbidden-zone mistakes
FORBIDDEN_ZONE_DEBOUNCE_REQUIRED_CONSENSUS = 2
FORBIDDEN_ZONE_SCROLL_REENTRY_COOLDOWN = 0.15
FORBIDDEN_BLACKOUT_DURATION = 6.0            # Keep rejected coordinates suppressed long enough to avoid thrash

# Pre-click boundary validation delays
FORBIDDEN_ZONE_PRECLICK_VALIDATION_DELAY = 0.0
FORBIDDEN_ZONE_DOUBLE_CHECK_DELAY = 0.0
ASSET_BOUNDARY_PRECHECK_DELAY = 0.0
ASSET_BOUNDARY_CONFIRM_DELAY = 0.0
ASSET_SEGREGATION_DELAY = 0.020                   # Keep the sort/segregation beat in the scan phase, not the click phase


###################################
###    LEVEL TRANSITIONS        ###
###################################

# Level transition timing
LEVEL_TRANSITION_MAX_ATTEMPTS = 5   # Max attempts to find and click new level button
LEVEL_COMPLETION_RECENCY_WINDOW = 5.0  # Seconds within which a recent completion is considered valid
NEW_LEVEL_FAIL_COOLDOWN = 15.0      # Cooldown after failed level transition before retrying

# Transition click timing
NEW_LEVEL_BUTTON_DELAY = 0.0
NEW_LEVEL_FOLLOWUP_DELAY = 0.0
TRANSITION_POST_CLICK_DELAY = 0.0
TRANSITION_RETRY_DELAY = 0.0

# Faster interrupt polling lets long sleeps break sooner when a new level appears,
# which reduces dead time without changing the priority logic itself.
NEW_LEVEL_INTERRUPT_INTERVAL = 0.010

# The background watcher should sample often enough to notice the travel button early,
# but not so fast that it competes with the active FSM for every frame.
NEW_LEVEL_MONITOR_INTERVAL = 0.020

# A shorter override cooldown makes repeated, legitimate transition signals respond
# faster while still blocking accidental double-trigger echoes from the same event.
NEW_LEVEL_OVERRIDE_COOLDOWN = 0.05

# Scan regions for new-level and upgrade red icons (pixel coordinates)
NEW_LEVEL_RED_ICON_X_MIN = 40
NEW_LEVEL_RED_ICON_X_MAX = 60
NEW_LEVEL_RED_ICON_Y_MIN = 665
NEW_LEVEL_RED_ICON_Y_MAX = 680

UPGRADE_RED_ICON_X_MIN = 280
UPGRADE_RED_ICON_X_MAX = 310
UPGRADE_RED_ICON_Y_MIN = 665
UPGRADE_RED_ICON_Y_MAX = 680

# Coordinate limits for red icon search region
MAX_SEARCH_Y = 660                  # Maximum Y for standard red icon / template scans
EXTENDED_SEARCH_Y = 710             # Extended Y for stats icon and full-view captures


###################################
###  PRIORITY RESOLVER FLAGS    ###
###################################

# Interrupt toggles for the FSM priority resolver
ENABLE_NEW_LEVEL_INTERRUPT = True       # Allow priority resolver to trigger level transitions
ENABLE_NO_ICON_SCROLL_INTERRUPT = False  # Allow priority resolver to force scroll when no icons found


###################################
###  ADAPTIVE TUNER SETTINGS    ###
###################################

# Keep the adaptive tuner enabled so the scan cadence can learn faster over time while
# hard-clamping all true interaction delays to zero.
ADAPTIVE_TUNER_ENABLED = True
ADAPTIVE_TUNER_ALPHA = 0.25             # Faster adaptation so search cadence converges quickly

# Success rate thresholds that trigger delay adjustments
ADAPTIVE_TUNER_CLICK_LOW_THRESHOLD = 0.80   # Click timing is pinned, but still track poor outcomes
ADAPTIVE_TUNER_CLICK_HIGH_THRESHOLD = 0.99
ADAPTIVE_TUNER_SEARCH_LOW_THRESHOLD = 0.82  # Below this: slow the stalk slightly for more certainty
ADAPTIVE_TUNER_SEARCH_HIGH_THRESHOLD = 0.96 # Above this: tighten toward a faster stalk cadence

# Increment/decrement step sizes for each tunable delay
ADAPTIVE_TUNER_CLICK_DELAY_STEP = 0.0
ADAPTIVE_TUNER_MOVE_DELAY_STEP = 0.0
ADAPTIVE_TUNER_CLICK_DECREMENT = 0.0
ADAPTIVE_TUNER_MOVE_DECREMENT = 0.0
ADAPTIVE_TUNER_SEARCH_INTERVAL_STEP = 0.010
ADAPTIVE_TUNER_UPGRADE_INTERVAL_STEP = 0.0
ADAPTIVE_TUNER_SEARCH_DECREMENT = 0.006
ADAPTIVE_TUNER_UPGRADE_DECREMENT = 0.0

# Range limits for adaptive delays
ADAPTIVE_TUNER_MIN_CLICK_DELAY = 0.0
ADAPTIVE_TUNER_MAX_CLICK_DELAY = 0.0
ADAPTIVE_TUNER_MIN_MOVE_DELAY = 0.0
ADAPTIVE_TUNER_MAX_MOVE_DELAY = 0.0
ADAPTIVE_TUNER_MIN_UPGRADE_INTERVAL = 0.001
ADAPTIVE_TUNER_MAX_UPGRADE_INTERVAL = 0.001
ADAPTIVE_TUNER_MIN_SEARCH_INTERVAL = 0.055
ADAPTIVE_TUNER_MAX_SEARCH_INTERVAL = 0.120


###################################
###   AI VISION & LEARNING      ###
###################################

# Vision Optimizer (EMA-based threshold adaptation)
AI_VISION_ENABLED = True
AI_VISION_ALPHA = 0.18                  # Slightly quicker threshold adaptation on stable evidence
AI_VISION_ALPHA_MAX = 0.40
AI_VISION_CONFIDENCE_BOOST = 0.25
AI_VISION_CONFIDENCE_THRESHOLD = 0.92

# Box detection AI bounds
AI_BOX_THRESHOLD_MIN = 0.85             # Minimum adaptive threshold for box detection
AI_BOX_THRESHOLD_MAX = 0.995            # Maximum adaptive threshold for box detection
AI_BOX_MISS_WINDOW = 4                  # Degrade more slowly so the scan stays accuracy-first
AI_BOX_MISS_STEP = 0.004

# Red icon detection AI bounds
AI_RED_ICON_THRESHOLD_MIN = 0.91        # Allow adaptive degradation below the base floor after repeated misses
AI_RED_ICON_THRESHOLD_MAX = 0.95        # Prevent the optimizer from ratcheting red-icon confidence back into a brittle range
AI_RED_ICON_BOOTSTRAP_MAX = 0.94        # Cap persisted startup state so stale runs cannot relaunch with an already-overstrict red threshold
AI_RED_ICON_MARGIN = 0.02               # Confidence margin subtracted during threshold update
AI_RED_ICON_MISS_WINDOW = 4
AI_RED_ICON_MISS_STEP = 0.0025

# New level detection AI bounds
AI_NEW_LEVEL_THRESHOLD_MIN = 0.965      # Minimum adaptive threshold for new level detection
AI_NEW_LEVEL_THRESHOLD_MAX = 0.995      # Maximum adaptive threshold for new level detection
AI_NEW_LEVEL_MISS_WINDOW = 4
AI_NEW_LEVEL_MISS_STEP = 0.003

# New level red icon detection AI bounds
AI_NEW_LEVEL_RED_ICON_THRESHOLD_MIN = 0.92   # Minimum adaptive threshold
AI_NEW_LEVEL_RED_ICON_THRESHOLD_MAX = 0.99   # Maximum adaptive threshold
AI_NEW_LEVEL_RED_ICON_MISS_WINDOW = 4
AI_NEW_LEVEL_RED_ICON_MISS_STEP = 0.003

# Upgrade station detection AI bounds
AI_UPGRADE_STATION_THRESHOLD_MIN = 0.91      # Minimum adaptive threshold
AI_UPGRADE_STATION_THRESHOLD_MAX = 0.99      # Maximum adaptive threshold
AI_UPGRADE_STATION_MISS_WINDOW = 4
AI_UPGRADE_STATION_MISS_STEP = 0.003

# Stats upgrade detection AI bounds
AI_STATS_UPGRADE_THRESHOLD_MIN = 0.9         # Minimum adaptive threshold
AI_STATS_UPGRADE_THRESHOLD_MAX = 0.99        # Maximum adaptive threshold
AI_STATS_UPGRADE_MISS_WINDOW = 4
AI_STATS_UPGRADE_MISS_STEP = 0.003

# Vision state persistence
AI_VISION_STATE_FILE = str(Path(MEMORY_DIR) / "vision_state.json")  # File path for saving vision optimizer state
AI_VISION_SAVE_INTERVAL = 10.0         # Persist often enough to keep the memory profile current

# Historical Learning system
# Historical learning stays fully enabled. It should mine recent fast wins, keep
# the interaction delays pinned to zero, and only adapt the stalk/search cadence.
AI_LEARNING_ENABLED = True

# All persisted AI memory stays inside the isolated memory/ directory.
AI_LEARNING_STATE_FILE = str(Path(MEMORY_DIR) / "learning_state.json")
AI_LEARNING_SAVE_INTERVAL = 1.0        # Save often so newly learned fast profiles are not lost
AI_LEARNING_RECORDS_LIMIT = 160        # Keep enough runs to blend recent winners without unbounded growth
AI_LEARNING_THREAD_JOIN_TIMEOUT = 1.0  # Timeout for learning thread shutdown
AI_LEARNING_THREAD_INTERVAL = 0.25     # Background learner wake cadence
AI_LEARNING_PAIR_WINDOW = 2            # Apply quick pairwise comparisons for fast early learning
AI_LEARNING_BATCH_WINDOW = 6           # Blend over a slightly wider recent sample for stability
AI_LEARNING_EMA_ALPHA = 0.40           # Favor new winning profiles more aggressively
AI_LEARNING_PROFILE_BLEND_TOP_K = 3    # Average the top recent performers instead of a single spike
AI_LEARNING_MIN_IMPROVEMENT_RATIO = 0.02
AI_LEARNING_APPLY_COOLDOWN = 0.5       # Let the learner tighten search cadence quickly after a better run

# Learning range limits (clamping bounds for learned timing values)
# Pin true interaction delays to zero even when learning is active.
AI_LEARNING_MIN_CLICK_DELAY = 0.0
AI_LEARNING_MAX_CLICK_DELAY = 0.0
AI_LEARNING_MIN_MOVE_DELAY = 0.0
AI_LEARNING_MAX_MOVE_DELAY = 0.0
AI_LEARNING_MIN_UPGRADE_INTERVAL = 0.001
AI_LEARNING_MAX_UPGRADE_INTERVAL = 0.001

# Search cadence is the only learned pace variable: start deliberate, then learn faster.
AI_LEARNING_MIN_SEARCH_INTERVAL = 0.050
AI_LEARNING_MAX_SEARCH_INTERVAL = 0.110


###################################
###  TELEGRAM NOTIFICATIONS     ###
###################################

TELEGRAM_ENABLED = False            # Enable Telegram bot notifications
TELEGRAM_BOT_TOKEN = ""             # Telegram bot API token
TELEGRAM_CHAT_ID = ""               # Target Telegram chat ID for notifications


###################################
###      FORBIDDEN ZONES        ###
###################################

# Zones prevent the bot from clicking on critical UI elements.
# Each zone is defined by name and bounding box (min/max X and Y).
# coordinate_space: "image" = relative to emulator client area; "monitor" = absolute desktop
FORBIDDEN_ZONES = [
    {
        "name": "General bottom bar",
        "coordinate_space": "image",
        "x_min": 60, "x_max": 280, "y_min": 668, "y_max": 1000
    },
    {
        "name": "Zone 1: Right side menu area",
        "coordinate_space": "image",
        "x_min": 290, "x_max": 350, "y_min": 93, "y_max": 320
    },
    {
        "name": "Zone 2: Left side top menu area",
        "coordinate_space": "image",
        "x_min": 0, "x_max": 60, "y_min": 50, "y_max": 280
    },
    {
        "name": "Zone 3: Left side bottom menu area",
        "coordinate_space": "image",
        "x_min": 0, "x_max": 60, "y_min": 590, "y_max": 667
    },
    {
        "name": "Zone 4: Top center notification area",
        "coordinate_space": "image",
        "x_min": 145, "x_max": 200, "y_min": 65, "y_max": 110
    },
    {
        "name": "Zone 5: Bottom navigation bar",
        "coordinate_space": "image",
        "x_min": 55, "x_max": 285, "y_min": 660, "y_max": 725
    },
    {
        "name": "Zone 6: Top bar area",
        "coordinate_space": "image",
        "x_min": 0, "x_max": 360, "y_min": 0, "y_max": 70
    }
]


def build_scroll_timing_report():
    release_ms = float(SCROLL_SETTLE_DELAY) * 1000.0
    vision_ms = float(POST_SCROLL_VISION_THINK_DELAY) * 1000.0
    confirm_ms = float(POST_SCROLL_CONFIRM_THINK_DELAY) * 1000.0
    interval_ms = float(SCROLL_INTERVAL_PAUSE) * 1000.0
    cache_ttl_ms = float(CAPTURE_CACHE_TTL) * 1000.0
    drag_ms = float(SCROLL_DURATION) * 1000.0
    step_count = int(SCROLL_STEP_COUNT)

    post_scroll_ms = float(POST_SCROLL_SETTLE) * 1000.0
    pre_scan_budget_ms = release_ms + post_scroll_ms + interval_ms
    fresh_frame_margin_ms = pre_scan_budget_ms - cache_ttl_ms
    ms_per_step = drag_ms / step_count if step_count > 0 else 0.0

    return {
        "drag_duration_ms": round(drag_ms, 2),
        "drag_step_count": step_count,
        "drag_ms_per_step": round(ms_per_step, 2),
        "release_settle_ms": round(release_ms, 2),
        "vision_settle_ms": round(vision_ms, 2),
        "confirm_settle_ms": round(confirm_ms, 2),
        "interval_pause_ms": round(interval_ms, 2),
        "post_scroll_settle_ms": round(post_scroll_ms, 2),
        "pre_scan_budget_ms": round(pre_scan_budget_ms, 2),
        "capture_cache_ttl_ms": round(cache_ttl_ms, 2),
        "fresh_frame_margin_ms": round(fresh_frame_margin_ms, 2),
        "fresh_frame_safe": fresh_frame_margin_ms > 0.0,
    }


def run_scroll_timing_report_cli(argv=None):
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Report effective scroll settle timing for the CV scan path")
    parser.add_argument("--json", action="store_true", help="Print the report as JSON")
    args = parser.parse_args(argv)

    report = build_scroll_timing_report()

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["fresh_frame_safe"] else 1

    print("=" * 72)
    print("SCROLL TIMING REPORT")
    print("=" * 72)
    print(f"Drag duration:           {report['drag_duration_ms']:.2f} ms")
    print(f"Drag steps:              {report['drag_step_count']}")
    print(f"Drag ms per step:        {report['drag_ms_per_step']:.2f} ms")
    print(f"Release settle:          {report['release_settle_ms']:.2f} ms")
    print(f"Vision settle:           {report['vision_settle_ms']:.2f} ms")
    print(f"Confirm settle:          {report['confirm_settle_ms']:.2f} ms")
    print(f"Interval pause:          {report['interval_pause_ms']:.2f} ms")
    print(f"Total post-scroll wait:  {report['pre_scan_budget_ms']:.2f} ms")
    print(f"Capture cache TTL:       {report['capture_cache_ttl_ms']:.2f} ms")
    print(f"Fresh-frame margin:      {report['fresh_frame_margin_ms']:.2f} ms")
    print()
    if report["fresh_frame_safe"]:
        print("PASS: Post-scroll wait exceeds capture-cache TTL, so the next scan can request a fresh frame.")
        return 0

    print("FAIL: Post-scroll wait does not exceed capture-cache TTL; the next scan may reuse a stale frame.")
    return 1


if __name__ == "__main__":
    raise SystemExit(run_scroll_timing_report_cli())

