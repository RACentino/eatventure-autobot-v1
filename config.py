###############################
###    WINDOW & UI SETTINGS   ###
###############################

# WINDOW_TITLE: The exact title of the scrcpy window (visible at the top of the window)
WINDOW_TITLE = "EatventureAuto"

# Window dimensions used for capturing and relative positioning
WINDOW_WIDTH = 300 * 1.2
WINDOW_HEIGHT = 650 * 1.2

# Debug and Visualization Settings
DEBUG = True
DEBUG_VISION = False  # Enables masked view for tuning pixel density
ShowForbiddenArea = False  # Enables a visual overlay showing forbidden zones in red


###############################
###  DIRECTORY & FILE PATHS ###
###############################

TEMPLATES_DIR = "templates"
ASSETS_DIR = "Assets"
LOGS_DIR = "logs"


###############################
###   DETECTION THRESHOLDS  ###
###############################

# General template matching confidence (0.0 - 1.0)
MATCH_THRESHOLD = 0.98

# Specific thresholds for different game assets
RED_ICON_THRESHOLD = 0.94
NEW_LEVEL_RED_ICON_THRESHOLD = 0.95
STATS_RED_ICON_THRESHOLD = 0.97
UPGRADE_STATION_THRESHOLD = 0.94
BOX_THRESHOLD = 0.97
UNLOCK_THRESHOLD = 0.95
NEW_LEVEL_THRESHOLD = 0.98

# Detection gate settings
RED_ICON_MIN_MATCHES = 1
NEW_LEVEL_RED_ICON_MIN_MATCHES = 1
RED_ICON_PIXEL_THRESHOLD = 50  # Min red pixels in ROI to trigger
RED_ICON_DILATE_KERNEL = 3     # Size of dilation kernel to 'inflate' red pixels

# Red Color HSV bounds (wider range for better detection)
RED_HSV_LOWER1 = (0, 100, 100)
RED_HSV_UPPER1 = (15, 255, 255)
RED_HSV_LOWER2 = (165, 100, 100)
RED_HSV_UPPER2 = (180, 255, 255)

# Color verification for Red Icons
RED_ICON_COLOR_CHECK = True
RED_ICON_COLOR_MIN_RATIO = 1.15
RED_ICON_COLOR_MIN_MEAN = 35
RED_ICON_COLOR_SAMPLE_SIZE = 24

# Position refinement and verification
RED_ICON_VERIFY_PADDING = 24
RED_ICON_VERIFY_TOLERANCE = 12
RED_ICON_REFINE_RADIUS = 18
RED_ICON_REFINE_THRESHOLD_DROP = 0.02

# Upgrade station specific detection
UPGRADE_STATION_COLOR_CHECK = False
UPGRADE_STATION_REFINE_RADIUS = 28
UPGRADE_STATION_CLICK_REFINE_RADIUS = 18


###############################
###  MOUSE & INTERACTION    ###
###############################

# Base interaction timings
CLICK_DELAY = 0.045        # Padded handoff for UI consistency
MOUSE_MOVE_DELAY = 0.006   
CLICK_DURATION = 0.026     # Padded dwell ensures registration on all systems
MOUSE_DOWN_UP_DELAY = CLICK_DURATION
DOUBLE_CLICK_DELAY = 0.042

# Mouse movement retry and correction logic
MOUSE_MOVE_RETRIES = 2
MOUSE_MOVE_RETRY_DELAY = 0.002
MOUSE_TARGET_SETTLE_DELAY = 0.002
MOUSE_TARGET_TIMEOUT = 0.045
MOUSE_TARGET_CHECK_INTERVAL = 0.003
MOUSE_TARGET_HOVER_DELAY = 0.002
MOUSE_STABILIZE_DURATION = 0.008  # Longer stabilization at target before click
MOUSE_TARGET_RETRIES = 3
MOUSE_TARGET_CORRECTION_DELAY = 0.002

# Stability delays before clicking
MOUSE_PRE_CLICK_STABILIZE_BASE = 0.004
MOUSE_PRE_CLICK_STABILIZE_MAX = 0.015
MOUSE_PRE_CLICK_STABILIZE_DISTANCE_FACTOR = 0.00004

# Click retry logic for robustness
MOUSE_CLICK_RETRY_COUNT = 2
MOUSE_CLICK_RETRY_SETTLE_DELAY = 0.004


###############################
###    SCROLLING BEHAVIOR   ###
###############################

# Start position for search scrolls (relative to window)
SCROLL_START_POS = (180, 390)

# Distance in pixels for a single "standard" scroll step
SCROLL_PIXEL_STEP = 100     # Tightened: Finer search resolution for better locking
SCROLL_DISTANCE_RATIO = 1

# Arithmetic Search Strategy (Numerous but Short)
MAX_SCROLL_CYCLES = 12     # Increased cycles to compensate for shorter steps
SCROLL_INCREMENT_STEP = 3   
SCROLL_INTERVAL_PAUSE = 0.08 # Rhythmic gap between swipes
POST_SCROLL_SETTLE = 0.24    # CRITICAL: Pure scan window. Guarantees a static frame.
CYCLE_PAUSE_DURATION = 0.20  # Stabilized direction flip

# Visual smoothness and stability
SCROLL_DURATION = 0.28     # Slower, more deliberate glide reduces motion blur
SCROLL_STEP_COUNT = 55     # High density linear motion
SCROLL_MIN_INTERVAL = 0.004
SCROLL_SETTLE_DELAY = 0.12  # Mechanical stabilization (Stop Inertia)


###############################
###    BOT LOGIC & TIMING   ###
###############################

# Main loop execution speed
FSM_TICK_DELAY = 0.015     # Aligned with 60FPS frame timing (16ms)
MAIN_LOOP_DELAY = FSM_TICK_DELAY

# Minimum time to wait between state handler executions
STATE_DELAY = 0.025
STATE_MIN_INTERVAL_DEFAULT = 0.02
STATE_MIN_INTERVALS = {
    "FIND_RED_ICONS": 0.05,  # Forces a "stare" before giving up and scrolling
    "OPEN_BOXES": 0.015,
    "SCROLL": 0.025,
}

# Red Icon and detection offsets
RED_ICON_OFFSET_X = 10
RED_ICON_OFFSET_Y = 10

# Fixed click positions for specific UI elements
NEW_LEVEL_POS = (171, 434)
LEVEL_TRANSITION_POS = (174, 520)
IDLE_CLICK_POS = (2, 390)
STATS_UPGRADE_POS = (270, 304)
STATS_UPGRADE_BUTTON_POS = (310, 698)
NEW_LEVEL_BUTTON_POS = (30, 692)

# Timing for interaction sequences
UPGRADE_HOLD_DURATION = 5  # How long to hold the upgrade button
UPGRADE_CLICK_INTERVAL = 0.012  # Slower hold-loop tap cadence improves upgrade registration consistency.
UPGRADE_SEARCH_INTERVAL = 0.08  # More time between upgrade scans avoids CV while UI counters are animating.
UPGRADE_CHECK_INTERVAL = 0.07  # Slower polling reduces overlap between click effects and verification reads.
STATS_UPGRADE_CLICK_DURATION = 2
STATS_UPGRADE_CLICK_DELAY = 0.02  # Added spacing between stat taps to prevent dropped clicks on low FPS moments.
STATS_ICON_PADDING = 20

# UI render and settle delays
IDLE_CLICK_SETTLE_DELAY = 0.05  # Longer idle settle prevents immediate post-idle scans from reading transition blur.
IDLE_CLICK_COOLDOWN = 0.15

# Red Icon and detection logic constants
RED_ICON_MIN_DISTANCE = 80
RED_ICON_MERGE_PROXIMITY = 10
RED_ICON_MERGE_BUCKET_SIZE = 10

# Forbidden-zone red icon arbitration (debounced 4-state matrix)
FORBIDDEN_ZONE_DETECTION_PRE_DELAY = 0.02
FORBIDDEN_ZONE_DETECTION_POST_DELAY = 0.03
FORBIDDEN_ZONE_DEBOUNCE_TICKS = 3
FORBIDDEN_ZONE_DEBOUNCE_REQUIRED_CONSENSUS = 2
FORBIDDEN_ZONE_SCROLL_REENTRY_COOLDOWN = 0.18
FORBIDDEN_BLACKOUT_DURATION = 3.5 # World-space coordinate ignore time

# Strict pre-click boundary validator timing (Slow is Smooth, Smooth is Fast)
FORBIDDEN_ZONE_PRECLICK_VALIDATION_DELAY = 0.012
FORBIDDEN_ZONE_DOUBLE_CHECK_DELAY = 0.008
ASSET_BOUNDARY_PRECHECK_DELAY = 0.02
ASSET_BOUNDARY_CONFIRM_DELAY = 0.01
ASSET_SEGREGATION_DELAY = 0.04  # Deliberate pause for coordinate categorization

# Upgrade station interaction settings
UPGRADE_STATION_SEARCH_MAX_ATTEMPTS = 5
UPGRADE_STATION_RELAXED_THRESHOLD_DROP = 0.05
UPGRADE_STATION_RELAXED_ATTEMPT_TRIGGER = 2

# Level transition and completion settings
LEVEL_TRANSITION_MAX_ATTEMPTS = 5
LEVEL_COMPLETION_RECENCY_WINDOW = 5.0
NEW_LEVEL_FAIL_COOLDOWN = 15.0

NEW_LEVEL_BUTTON_DELAY = 0.5
NEW_LEVEL_FOLLOWUP_DELAY = 0.3
UI_TRANSITION_PADDING = 1.1  # Unified transition padding so post-click travel/menu animations fully complete before CV.
TRANSITION_POST_CLICK_DELAY = UI_TRANSITION_PADDING  # Reuses the padded transition constant for all transition waits.
TRANSITION_RETRY_DELAY = 0.1
UNLOCK_POST_CLICK_DELAY = 0.8
WAIT_UNLOCK_RETRY_DELAY = 0.08  # Added unlock retry spacing avoids rapid-clicking while unlock modal is still opening.
PRE_UNLOCK_DELAY = 0.0
UNLOCK_BACKOFF_THRESHOLD = 5
UNLOCK_MAX_RETRY_DELAY = 0.5

# Performance caching
CAPTURE_CACHE_TTL = 0.015  # Aligned with FSM_TICK_DELAY for efficient frame sharing.
NEW_LEVEL_RED_ICON_CACHE_TTL = 0.01
RED_ICON_STABILITY_CACHE_TTL = 4.0 # Extended history for deliberate locking
RED_ICON_STABILITY_RADIUS = 16    
RED_ICON_STABILITY_MIN_HITS = 3    # INCREASED: Requires 3 frames of consistency for lock
RED_ICON_STABILITY_MAX_HISTORY = 15 # Deeper pool for hit verification

# Scan regions for Red Icons
NEW_LEVEL_RED_ICON_X_MIN = 40
NEW_LEVEL_RED_ICON_X_MAX = 60
NEW_LEVEL_RED_ICON_Y_MIN = 665
NEW_LEVEL_RED_ICON_Y_MAX = 680

UPGRADE_RED_ICON_X_MIN = 280
UPGRADE_RED_ICON_X_MAX = 310
UPGRADE_RED_ICON_Y_MIN = 665
UPGRADE_RED_ICON_Y_MAX = 680

# Background monitoring frequency
NEW_LEVEL_INTERRUPT_INTERVAL = 0.035 # 2x faster exit from sleep states
NEW_LEVEL_MONITOR_INTERVAL = 0.055   # Consistent background scan rate
NEW_LEVEL_OVERRIDE_COOLDOWN = 0.25


###############################
### ADAPTIVE TUNER SETTINGS ###
###############################

ADAPTIVE_TUNER_ENABLED = True
ADAPTIVE_TUNER_ALPHA = 0.2  # EMA smoothing factor

# Success rate thresholds for triggering delay adjustments
ADAPTIVE_TUNER_CLICK_LOW_THRESHOLD = 0.85
ADAPTIVE_TUNER_CLICK_HIGH_THRESHOLD = 0.97
ADAPTIVE_TUNER_SEARCH_LOW_THRESHOLD = 0.70
ADAPTIVE_TUNER_SEARCH_HIGH_THRESHOLD = 0.90

# Step values for delay adjustments
ADAPTIVE_TUNER_CLICK_DELAY_STEP = 0.01
ADAPTIVE_TUNER_MOVE_DELAY_STEP = 0.001
ADAPTIVE_TUNER_CLICK_DECREMENT = 0.005
ADAPTIVE_TUNER_MOVE_DECREMENT = 0.001
ADAPTIVE_TUNER_SEARCH_INTERVAL_STEP = 0.01
ADAPTIVE_TUNER_UPGRADE_INTERVAL_STEP = 0.001
ADAPTIVE_TUNER_SEARCH_DECREMENT = 0.005
ADAPTIVE_TUNER_UPGRADE_DECREMENT = 0.001

# Range limits for adaptive delays
ADAPTIVE_TUNER_MIN_CLICK_DELAY = 0.035
ADAPTIVE_TUNER_MAX_CLICK_DELAY = 0.11
ADAPTIVE_TUNER_MIN_MOVE_DELAY = 0.003
ADAPTIVE_TUNER_MAX_MOVE_DELAY = 0.012
ADAPTIVE_TUNER_MIN_UPGRADE_INTERVAL = 0.006
ADAPTIVE_TUNER_MAX_UPGRADE_INTERVAL = 0.012
ADAPTIVE_TUNER_MIN_SEARCH_INTERVAL = 0.015
ADAPTIVE_TUNER_MAX_SEARCH_INTERVAL = 0.09  # Must stay above UPGRADE_SEARCH_INTERVAL so low-success tuning can only slow scans, never snap faster.


###############################
###  AI VISION & LEARNING   ###
###############################

AI_VISION_ENABLED = True
AI_VISION_ALPHA = 0.2
AI_VISION_ALPHA_MAX = 0.45
AI_VISION_CONFIDENCE_BOOST = 0.3
AI_VISION_CONFIDENCE_THRESHOLD = 0.9  # Higher confidence gate avoids over-boosting thresholds from transient/blurred matches.

# Box detection specific AI settings
AI_BOX_THRESHOLD_MIN = 0.85
AI_BOX_THRESHOLD_MAX = 0.995
AI_BOX_MISS_WINDOW = 3
AI_BOX_MISS_STEP = 0.005

# Threshold limits for AI-driven detection
AI_RED_ICON_THRESHOLD_MIN = 0.92
AI_RED_ICON_THRESHOLD_MAX = 0.985
AI_RED_ICON_MARGIN = 0.01
AI_RED_ICON_MISS_WINDOW = 2
AI_RED_ICON_MISS_STEP = 0.006

AI_NEW_LEVEL_THRESHOLD_MIN = 0.965
AI_NEW_LEVEL_THRESHOLD_MAX = 0.995
AI_NEW_LEVEL_MISS_WINDOW = 2
AI_NEW_LEVEL_MISS_STEP = 0.004

AI_NEW_LEVEL_RED_ICON_THRESHOLD_MIN = 0.92
AI_NEW_LEVEL_RED_ICON_THRESHOLD_MAX = 0.99
AI_NEW_LEVEL_RED_ICON_MISS_WINDOW = 2
AI_NEW_LEVEL_RED_ICON_MISS_STEP = 0.005

AI_UPGRADE_STATION_THRESHOLD_MIN = 0.9
AI_UPGRADE_STATION_THRESHOLD_MAX = 0.99
AI_UPGRADE_STATION_MISS_WINDOW = 2
AI_UPGRADE_STATION_MISS_STEP = 0.005

AI_STATS_UPGRADE_THRESHOLD_MIN = 0.9
AI_STATS_UPGRADE_THRESHOLD_MAX = 0.99
AI_STATS_UPGRADE_MISS_WINDOW = 2
AI_STATS_UPGRADE_MISS_STEP = 0.005

# Persistence files
AI_VISION_STATE_FILE = f"{LOGS_DIR}/vision_state.json"
AI_VISION_SAVE_INTERVAL = 1.0

# Historical Learning
AI_LEARNING_ENABLED = True
AI_LEARNING_STATE_FILE = f"{LOGS_DIR}/learning_state.json"
AI_LEARNING_SAVE_INTERVAL = 1.5
AI_LEARNING_RECORDS_LIMIT = 120
AI_LEARNING_THREAD_JOIN_TIMEOUT = 1.0

# Learning range limits
AI_LEARNING_MIN_CLICK_DELAY = 0.035
AI_LEARNING_MAX_CLICK_DELAY = 0.12
AI_LEARNING_MIN_MOVE_DELAY = 0.002
AI_LEARNING_MAX_MOVE_DELAY = 0.012
AI_LEARNING_MIN_UPGRADE_INTERVAL = 0.006
AI_LEARNING_MAX_UPGRADE_INTERVAL = 0.013
AI_LEARNING_MIN_SEARCH_INTERVAL = 0.012
AI_LEARNING_MAX_SEARCH_INTERVAL = 0.09  # Keep learner clamp aligned with tuner max to preserve monotonic reliability-focused search pacing.


###############################
###  TELEGRAM NOTIFICATIONS ###
###############################

TELEGRAM_ENABLED = False
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""


###############################
###     FORBIDDEN ZONES     ###
###############################

# Zones prevent the bot from clicking on critical UI elements
# Each zone is defined by name and bounding box (min/max X and Y)
# Optional field: "coordinate_space"
# - "image" (default): x/y are relative to emulator client area (same space as template matching output)
# - "monitor": x/y are absolute desktop coordinates
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

# Coordinate limits for searching Red Icons
MAX_SEARCH_Y = 660
EXTENDED_SEARCH_Y = 710
