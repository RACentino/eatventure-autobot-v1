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
UPGRADE_STATION_THRESHOLD = 0.95  # Raised 0.80â†’0.90: eliminates weak partial-shape matches
BOX_THRESHOLD = 0.97
UNLOCK_THRESHOLD = 0.95
NEW_LEVEL_THRESHOLD = 0.98

# Detection gate settings
RED_ICON_MIN_MATCHES = 1
NEW_LEVEL_RED_ICON_MIN_MATCHES = 1
RED_ICON_PIXEL_THRESHOLD = 65  # Raised 50â†’65: requires a more substantial red blob
RED_ICON_DILATE_KERNEL = 3     # Size of dilation kernel to 'inflate' red pixels

# Red Color HSV bounds â€” tightened to reduce false positives
# Hue upper ceiling lowered (15â†’10) to exclude orange-leaning pixels
# Saturation/Value floors raised (100â†’120/130) to exclude washed-out/dim non-reds
RED_HSV_LOWER1 = (0, 120, 130)
RED_HSV_UPPER1 = (10, 255, 255)
RED_HSV_LOWER2 = (168, 120, 130)  # Wrap-around lower bound narrowed (165â†’168)
RED_HSV_UPPER2 = (180, 255, 255)

# Color verification for Red Icons â€” thresholds tightened
RED_ICON_COLOR_CHECK = True
RED_ICON_COLOR_MIN_RATIO = 1.35  # Raised 1.15â†’1.35: red must be 35% brighter than max(G,B)
RED_ICON_COLOR_MIN_MEAN = 55    # Raised 35â†’55: minimum absolute red channel intensity
RED_ICON_COLOR_SAMPLE_SIZE = 24

# Position refinement and verification
RED_ICON_VERIFY_PADDING = 24
RED_ICON_VERIFY_TOLERANCE = 12
RED_ICON_REFINE_RADIUS = 18
RED_ICON_REFINE_THRESHOLD_DROP = 0.02

# Upgrade station specific detection
UPGRADE_STATION_COLOR_CHECK = True
UPGRADE_STATION_REFINE_RADIUS = 28
UPGRADE_STATION_CLICK_REFINE_RADIUS = 18


###############################
###  MOUSE & INTERACTION    ###
###############################

# Base interaction timings - Optimized for "Slow is Smooth, Smooth is Fast"
CLICK_DELAY = 0.080        # Raised 0.050â†’0.080: Steadier handoff for UI consistency
MOUSE_MOVE_DELAY = 0.012   # Raised 0.007â†’0.012: Smoother cursor travel
CLICK_DURATION = 0.050     # Raised 0.030â†’0.050: Guaranteed registration on all systems
MOUSE_DOWN_UP_DELAY = CLICK_DURATION
DOUBLE_CLICK_DELAY = 0.080 # Raised 0.050â†’0.080

# Mouse movement retry and correction logic
MOUSE_MOVE_RETRIES = 2
MOUSE_MOVE_RETRY_DELAY = 0.005 # Raised 0.003â†’0.005
MOUSE_TARGET_SETTLE_DELAY = 0.005 # Raised 0.003â†’0.005
MOUSE_TARGET_TIMEOUT = 0.080 # Raised 0.060â†’0.080
MOUSE_TARGET_CHECK_INTERVAL = 0.005 # Raised 0.004â†’0.005
MOUSE_TARGET_HOVER_DELAY = 0.005 # Raised 0.003â†’0.005
MOUSE_STABILIZE_DURATION = 0.025 # Raised 0.010â†’0.025: Deliberate stabilization at target before click
MOUSE_TARGET_RETRIES = 3
MOUSE_TARGET_CORRECTION_DELAY = 0.005 # Raised 0.003â†’0.005

# Stability delays before clicking
MOUSE_PRE_CLICK_STABILIZE_BASE = 0.010 # Raised 0.005â†’0.010
MOUSE_PRE_CLICK_STABILIZE_MAX = 0.025   # Raised 0.018â†’0.025
MOUSE_PRE_CLICK_STABILIZE_DISTANCE_FACTOR = 0.00008 # Slightly increased

# Click retry logic for robustness
MOUSE_CLICK_RETRY_COUNT = 2
MOUSE_CLICK_RETRY_SETTLE_DELAY = 0.010 # Raised 0.006â†’0.010


###############################
###    SCROLLING BEHAVIOR   ###
###############################

# Start position for search scrolls (relative to window)
SCROLL_START_POS = (170, 380)

# Distance in pixels for a single "standard" scroll step
SCROLL_PIXEL_STEP = 180     # Tightened: Finer search resolution for better locking
SCROLL_DISTANCE_RATIO = 1
SCROLL_VERIFICATION_DISTANCE = 200   # Verification scroll distance

# Arithmetic Search Strategy (Numerous but Short)
MAX_SCROLL_CYCLES = 12     
SCROLL_INCREMENT_STEP = 1   
SCROLL_INTERVAL_PAUSE = 0.05  # Adjusted for coordination with POST_SCROLL_SETTLE
POST_SCROLL_SETTLE = 0.35     # Raised 0.20â†’0.35: Total settle time (~0.4s) ensures render pipeline flush
CYCLE_PAUSE_DURATION = 0.25   # Raised 0.10â†’0.25: Clean frame buffer before direction flip

# Visual smoothness and stability
SCROLL_DURATION = 0.45    # Raised 0.27â†’0.45: Deliberately slow and smooth drag to avoid ballistic UI physics
SCROLL_STEP_COUNT = 18     # Raised 14â†’18: More steps for finer interpolation during slow drag
SCROLL_MIN_INTERVAL = 0.010 # Raised 0.006â†’0.010
SCROLL_SETTLE_DELAY = 0.05  # Raised 0.02â†’0.05: Robust post-drag stabilization buffer


###############################
###    BOT LOGIC & TIMING   ###
###############################

# Main loop execution speed
FSM_TICK_DELAY = 0.020     # Raised 0.010â†’0.020: 50Hz cycle prevents busy-spin and jitter
MAIN_LOOP_DELAY = FSM_TICK_DELAY

# Minimum time to wait between state handler executions
STATE_DELAY = 0.060        # Raised 0.040â†’0.060: Deliberate state handoff
STATE_MIN_INTERVAL_DEFAULT = 0.050 # Raised 0.030â†’0.050
STATE_MIN_INTERVALS = {
    "FIND_RED_ICONS": 0.080,  # Raised 0.060â†’0.080: Guarantees fresh frames between scans
    "OPEN_BOXES": 0.060,      # Raised 0.045â†’0.060
    "SCROLL": 0.050,          # Raised 0.035â†’0.050
}

# Red Icon and detection offsets
RED_ICON_OFFSET_X = 10
RED_ICON_OFFSET_Y = 10

# Fixed click positions for specific UI elements
NEW_LEVEL_POS = (171, 434)
LEVEL_TRANSITION_POS = (174, 520)
IDLE_CLICK_POS = (7, 390)
STATS_UPGRADE_POS = (270, 304)
STATS_UPGRADE_BUTTON_POS = (310, 698)
NEW_LEVEL_BUTTON_POS = (30, 692)

# Timing for interaction sequences
UPGRADE_HOLD_DURATION = 3  
UPGRADE_CLICK_INTERVAL = 0.015  # Raised 0.012â†’0.015: Steadier hold-loop tap cadence
UPGRADE_SEARCH_INTERVAL = 0.12  # Raised 0.09â†’0.12: More buffer for UI animation settlement
STATS_UPGRADE_CLICK_DURATION = 2
STATS_UPGRADE_CLICK_DELAY = 0.040  # Raised 0.025â†’0.040: Prevents dropped clicks on low FPS
STATS_ICON_PADDING = 20

# UI render and settle delays
IDLE_CLICK_SETTLE_DELAY = 0.12  # Raised 0.08â†’0.12: Deliberate UI state settlement
IDLE_CLICK_COOLDOWN = 0.35      # Raised 0.28â†’0.35: Prevents idle click race conditions

# Red Icon and detection logic constants
RED_ICON_MIN_DISTANCE = 80
RED_ICON_MERGE_PROXIMITY = 10
RED_ICON_MERGE_BUCKET_SIZE = 10

# Forbidden-zone red icon arbitration (debounced 4-state matrix)
FORBIDDEN_ZONE_DETECTION_PRE_DELAY = 0.035  # Raised 0.020â†’0.035
FORBIDDEN_ZONE_DETECTION_POST_DELAY = 0.045 # Raised 0.030â†’0.045
FORBIDDEN_ZONE_DEBOUNCE_TICKS = 3  # Raised 2â†’3: Higher consensus required for zone arbitration
FORBIDDEN_ZONE_DEBOUNCE_REQUIRED_CONSENSUS = 2 
FORBIDDEN_ZONE_SCROLL_REENTRY_COOLDOWN = 0.45  # Raised 0.35â†’0.45
FORBIDDEN_BLACKOUT_DURATION = 4.0 # Raised 3.5â†’4.0

# Strict pre-click boundary validator timing (Slow is Smooth, Smooth is Fast)
FORBIDDEN_ZONE_PRECLICK_VALIDATION_DELAY = 0.020   # Raised 0.010â†’0.020
FORBIDDEN_ZONE_DOUBLE_CHECK_DELAY = 0.015           # Raised 0.007â†’0.015
ASSET_BOUNDARY_PRECHECK_DELAY = 0.025               # Raised 0.015â†’0.025
ASSET_BOUNDARY_CONFIRM_DELAY = 0.015                # Raised 0.008â†’0.015
ASSET_SEGREGATION_DELAY = 0.050  # Raised 0.030â†’0.050

# Upgrade station interaction settings
UPGRADE_STATION_SEARCH_MAX_ATTEMPTS = 5
UPGRADE_STATION_RELAXED_THRESHOLD_DROP = 0.04  
UPGRADE_STATION_RELAXED_ATTEMPT_TRIGGER = 2

# Level transition and completion settings
LEVEL_TRANSITION_MAX_ATTEMPTS = 5
LEVEL_COMPLETION_RECENCY_WINDOW = 5.0
NEW_LEVEL_FAIL_COOLDOWN = 15.0

NEW_LEVEL_BUTTON_DELAY = 0.50  # Raised 0.40â†’0.50
NEW_LEVEL_FOLLOWUP_DELAY = 0.55 # Raised 0.45â†’0.55
UI_TRANSITION_PADDING = 1.3  # Raised 1.1â†’1.3: Unified transition padding
TRANSITION_POST_CLICK_DELAY = UI_TRANSITION_PADDING  
TRANSITION_RETRY_DELAY = 0.20 # Raised 0.15â†’0.20
UNLOCK_POST_CLICK_DELAY = 1.2 # Raised 0.8â†’1.2: Guaranteed modal animation completion
WAIT_UNLOCK_RETRY_DELAY = 0.15 # Raised 0.08â†’0.15: Prevents rapid-clicking race conditions
PRE_UNLOCK_DELAY = 0.0
UNLOCK_BACKOFF_THRESHOLD = 5
UNLOCK_MAX_RETRY_DELAY = 0.6 # Raised 0.5â†’0.6

# Performance caching
CAPTURE_CACHE_TTL = 0.020  # Deliberate: spans ~1.8 frames â€” cache serves both priority resolver and state handler within one tick
NEW_LEVEL_RED_ICON_CACHE_TTL = 0.015
RED_ICON_STABILITY_CACHE_TTL = 3.0 # Extended history for deliberate locking
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
NEW_LEVEL_INTERRUPT_INTERVAL = 0.050 # Deliberate: reduces polling overhead 40% â€” still catches interrupts within 120ms
# Monitor thread captures at ~4.5fps and still reacts well within transition windows.
# Well within the multi-second transition animation window, massively reduces _capture_lock contention.
NEW_LEVEL_MONITOR_INTERVAL = 0.220   # Deliberate: ~6.7fps monitoring; reduces lock contention vs main thread
NEW_LEVEL_OVERRIDE_COOLDOWN = 0.40


###############################
### PRIORITY RESOLVER FLAGS ###
###############################

# Toggle for the New Level priority resolver interrupt.
# When False (default), the resolver will NOT initiate level transitions.
# The background monitor thread still detects new levels, but the resolver
# skips acting on them. check_critical_interrupts() remains active as a safety net.
ENABLE_NEW_LEVEL_INTERRUPT = True

# Toggle for the No Icon Scroll priority resolver interrupt.
# When False (default), the resolver will NOT force a SCROLL transition
# after fallback asset clicks when no red icons were found.
# Standard scrolling from the main state flow is unaffected.
ENABLE_NO_ICON_SCROLL_INTERRUPT = False


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
ADAPTIVE_TUNER_SEARCH_INTERVAL_STEP = 0.008
ADAPTIVE_TUNER_UPGRADE_INTERVAL_STEP = 0.001
ADAPTIVE_TUNER_SEARCH_DECREMENT = 0.003
ADAPTIVE_TUNER_UPGRADE_DECREMENT = 0.001

# Range limits for adaptive delays
ADAPTIVE_TUNER_MIN_CLICK_DELAY = 0.045  # Deliberate: 5ms above learner min prevents tug-of-war oscillation
ADAPTIVE_TUNER_MAX_CLICK_DELAY = 0.12   # Unified with learner max to prevent tug-of-war oscillation (was 0.11)
ADAPTIVE_TUNER_MIN_MOVE_DELAY = 0.003   # Unified with learner min to prevent tug-of-war oscillation (was 0.003)
ADAPTIVE_TUNER_MAX_MOVE_DELAY = 0.012
ADAPTIVE_TUNER_MIN_UPGRADE_INTERVAL = 0.008  # Deliberate: 2ms buffer above learner min for stable convergence
ADAPTIVE_TUNER_MAX_UPGRADE_INTERVAL = 0.013  # Unified with learner max to prevent tug-of-war oscillation (was 0.012)
ADAPTIVE_TUNER_MIN_SEARCH_INTERVAL = 0.040  # Deliberate: 3ms buffer above learner min prevents racing
ADAPTIVE_TUNER_MAX_SEARCH_INTERVAL = 0.11  # Must stay above UPGRADE_SEARCH_INTERVAL so low-success tuning can only slow scans, never snap faster.


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

# Conflict 6 fix: floor raised from 0.90 to 0.91 to align with new relaxed threshold (0.95 - 0.04 = 0.91).
# Previously the optimizer floor equalled the relaxed retry floor â€” the optimizer had no independent recovery gap.
AI_UPGRADE_STATION_THRESHOLD_MIN = 0.91  # Was 0.90; now tracks relaxed floor exactly
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
AI_LEARNING_MIN_CLICK_DELAY = 0.045
AI_LEARNING_MAX_CLICK_DELAY = 0.12
AI_LEARNING_MIN_MOVE_DELAY = 0.003
AI_LEARNING_MAX_MOVE_DELAY = 0.012
AI_LEARNING_MIN_UPGRADE_INTERVAL = 0.006
AI_LEARNING_MAX_UPGRADE_INTERVAL = 0.013
AI_LEARNING_MIN_SEARCH_INTERVAL = 0.040
AI_LEARNING_MAX_SEARCH_INTERVAL = 0.11  # Keep learner clamp aligned with tuner max to preserve monotonic reliability-focused search pacing.


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

