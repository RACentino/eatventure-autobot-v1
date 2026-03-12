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

TEMPLATES_DIR = "templates"         # Folder containing template images for matching
ASSETS_DIR = "Assets"               # Folder containing game asset sub-templates
LOGS_DIR = "logs"                   # Folder for bot logs, vision state, and learning state


###################################
###   DETECTION THRESHOLDS      ###
###################################

# General template matching confidence floor (0.0–1.0)
MATCH_THRESHOLD = 0.98              # Default threshold passed to ImageMatcher constructor

# Per-asset detection thresholds
RED_ICON_THRESHOLD = 0.94           # Minimum confidence to accept a red icon match
NEW_LEVEL_RED_ICON_THRESHOLD = 0.95 # Confidence for red-icon-based new-level detection
STATS_RED_ICON_THRESHOLD = 0.97     # Confidence for stats upgrade icon detection
UPGRADE_STATION_THRESHOLD = 0.95    # Confidence for upgrade station template match
BOX_THRESHOLD = 0.97                # Confidence for gift box template match
UNLOCK_THRESHOLD = 0.95             # Confidence for unlock button template match
NEW_LEVEL_THRESHOLD = 0.98          # Confidence for new level / travel button template match

# Red icon gate settings
RED_ICON_MIN_MATCHES = 1            # Minimum number of simultaneous red icon matches required
NEW_LEVEL_RED_ICON_MIN_MATCHES = 1  # Minimum matches for new-level red icon detection
RED_ICON_PIXEL_THRESHOLD = 65       # Minimum red pixel count in ROI to confirm a genuine red blob
RED_ICON_DILATE_KERNEL = 3          # Morphological kernel size for noise removal and blob reconnection

# Red color HSV bounds for red pixel counting
RED_HSV_LOWER1 = (0, 120, 130)      # Low-hue red band lower bound
RED_HSV_UPPER1 = (10, 255, 255)     # Low-hue red band upper bound
RED_HSV_LOWER2 = (168, 120, 130)    # High-hue red wrap-around lower bound
RED_HSV_UPPER2 = (180, 255, 255)    # High-hue red wrap-around upper bound

# Red icon color verification (BGR channel ratio check)
RED_ICON_COLOR_CHECK = True         # Enable red-dominance verification after template match
RED_ICON_COLOR_MIN_RATIO = 1.35     # Red channel must exceed max(G,B) by this factor
RED_ICON_COLOR_MIN_MEAN = 55        # Minimum absolute red channel mean intensity
RED_ICON_COLOR_SAMPLE_SIZE = 24     # Pixel ROI half-size for color verification

# Red icon position refinement
RED_ICON_VERIFY_PADDING = 24        # Pixel padding around detection point for presence verification
RED_ICON_VERIFY_TOLERANCE = 12      # Max displacement for a match to still be considered "at" position
RED_ICON_REFINE_RADIUS = 18         # Search radius for sub-pixel position refinement
RED_ICON_REFINE_THRESHOLD_DROP = 0.02  # Threshold relaxation during refinement pass

# Upgrade station detection refinement
UPGRADE_STATION_COLOR_CHECK = True  # Enable histogram color verification for upgrade station
UPGRADE_STATION_REFINE_RADIUS = 28  # Search radius for upgrade station template refinement
UPGRADE_STATION_CLICK_REFINE_RADIUS = 18  # Search radius for click-target refinement


###################################
###   MOUSE & INTERACTION       ###
###################################

# Core click timing
CLICK_DELAY = 0.055                 # Post-click delay; allows game UI to register and animate
MOUSE_MOVE_DELAY = 0.006            # Delay between mouse move segments
MOUSE_DOWN_UP_DELAY = 0.032         # Mouse button dwell time (down-to-up); ensures input registration
DOUBLE_CLICK_DELAY = 0.042          # Delay between double-click actions

# Mouse movement retry and correction
MOUSE_MOVE_RETRIES = 2              # Max retries if mouse fails to reach target position
MOUSE_MOVE_RETRY_DELAY = 0.002      # Delay between movement retry attempts
MOUSE_TARGET_SETTLE_DELAY = 0.002   # Settle time after reaching target before verification
MOUSE_TARGET_TIMEOUT = 0.045        # Max time to wait for cursor to reach target
MOUSE_TARGET_CHECK_INTERVAL = 0.003 # Polling interval during target verification
MOUSE_TARGET_HOVER_DELAY = 0.002    # Delay after hover before click
MOUSE_STABILIZE_DURATION = 0.012    # Stabilization time at target before click input
MOUSE_TARGET_RETRIES = 3            # Max retries for target position verification
MOUSE_TARGET_CORRECTION_DELAY = 0.002  # Delay between correction attempts

# Pre-click stabilization (distance-adaptive)
MOUSE_PRE_CLICK_STABILIZE_BASE = 0.008     # Base stabilization delay before any click
MOUSE_PRE_CLICK_STABILIZE_MAX = 0.020      # Maximum stabilization delay cap
MOUSE_PRE_CLICK_STABILIZE_DISTANCE_FACTOR = 0.00004  # Additional delay per pixel of mouse travel

# Click retry logic
MOUSE_CLICK_RETRY_COUNT = 2         # Max click retries on registration failure
MOUSE_CLICK_RETRY_SETTLE_DELAY = 0.004  # Settle delay between click retries


###################################
###    SCROLLING BEHAVIOR       ###
###################################

# Scroll origin for oscillating drag operations
SCROLL_START_POS = (170, 380)       # (x, y) relative to window client area

# Scroll distance parameters
SCROLL_PIXEL_STEP = 125              # Pixels per single scroll step
SCROLL_DISTANCE_RATIO = 1           # Multiplier applied to scroll distance
SCROLL_VERIFICATION_DISTANCE = 300  # Pixel distance for new-level verification scroll

# Incremental Oscillating Search strategy
MAX_SCROLL_CYCLES = 12              # Maximum oscillation cycles per search invocation
SCROLL_INCREMENT_STEP = 1           # Amplitude increment per cycle pair
SCROLL_INTERVAL_PAUSE = 0.06        # Inter-scroll pause for frame stability between steps
POST_SCROLL_SETTLE = 0.22           # Post-scroll settle time; ensures rendered frame before scan
CYCLE_PAUSE_DURATION = 0.08         # Pause at direction reversal to prevent momentum artifacts

# Drag smoothness parameters
SCROLL_DURATION = 0.25              # Total duration of a single drag operation
SCROLL_STEP_COUNT = 20              # Interpolation steps per drag; controls smoothness
SCROLL_MIN_INTERVAL = 0.004         # Minimum interval between consecutive scroll commands
SCROLL_SETTLE_DELAY = 0.03          # Explicit post-drag stabilization buffer


###################################
###    FSM & STATE TIMING       ###
###################################

# Main loop tick rate
MAIN_LOOP_DELAY = 0.016             # Sleep between main loop iterations (~62 ticks/sec)

# State handler execution timing
STATE_DELAY = 0.035                 # General inter-state settle delay
STATE_MIN_INTERVAL_DEFAULT = 0.020  # Default minimum interval between handler executions
STATE_MIN_INTERVALS = {             # Per-state minimum interval overrides
    "FIND_RED_ICONS": 0.060,        # Full frame capture + debounce before re-scan
    "OPEN_BOXES": 0.025,            # Allows box UI open/close animations to complete
    "SCROLL": 0.035,                # Scroll input + settle must complete before next handler
}

# Red icon click offset (applied after detection)
RED_ICON_OFFSET_X = 10              # Horizontal offset from detected center to click point
RED_ICON_OFFSET_Y = 10              # Vertical offset from detected center to click point

# Fixed UI click positions (relative to window client area)
NEW_LEVEL_POS = (171, 434)          # Travel / new level confirmation button
LEVEL_TRANSITION_POS = (174, 520)   # Level transition confirmation button
IDLE_CLICK_POS = (4, 390)           # Safe idle click position (keeps game awake)
STATS_UPGRADE_POS = (270, 304)      # Stats upgrade tap target during stat boost loop
STATS_UPGRADE_BUTTON_POS = (310, 698)  # Stats upgrade menu open button
NEW_LEVEL_BUTTON_POS = (30, 692)    # New level acknowledgement button

# Upgrade station interaction timing
UPGRADE_HOLD_DURATION = 6           # Duration (seconds) to hold upgrade station button
UPGRADE_CLICK_INTERVAL = 0.018      # Tap cadence during upgrade hold loop
UPGRADE_SEARCH_INTERVAL = 0.12      # Delay between upgrade station search attempts
STATS_UPGRADE_CLICK_DURATION = 2    # Duration (seconds) of rapid stat upgrade tap loop
STATS_UPGRADE_CLICK_DELAY = 0.035   # Delay between individual stat upgrade taps
STATS_ICON_PADDING = 20             # Pixel padding for stats icon bounding box

# Idle click behavior
IDLE_CLICK_SETTLE_DELAY = 0.08      # Post-idle settle; prevents immediate scans from reading blur
IDLE_CLICK_COOLDOWN = 0.20          # Minimum interval between consecutive idle clicks

# Red icon spatial deduplication
RED_ICON_MIN_DISTANCE = 80          # Minimum pixel distance between distinct red icon detections
RED_ICON_MERGE_PROXIMITY = 10       # Distance within which detections are merged as duplicates
RED_ICON_MERGE_BUCKET_SIZE = 10     # Bucket width for spatial hashing during merge

# Upgrade station search retries
UPGRADE_STATION_SEARCH_MAX_ATTEMPTS = 5     # Max attempts per upgrade station search cycle
UPGRADE_STATION_RELAXED_THRESHOLD_DROP = 0.04  # Threshold reduction for relaxed retry attempts
UPGRADE_STATION_RELAXED_ATTEMPT_TRIGGER = 2    # Attempt number at which relaxed threshold activates

# Performance caching
CAPTURE_CACHE_TTL = 0.040           # Screenshot cache lifetime; shared between consecutive handlers
NEW_LEVEL_RED_ICON_CACHE_TTL = 0.04 # Cache TTL for new-level red icon detection frames

# Red icon stability filter (temporal consistency gate)
RED_ICON_STABILITY_CACHE_TTL = 1.5  # Time window for stability history retention
RED_ICON_STABILITY_RADIUS = 14      # Max pixel displacement to consider same icon across frames
RED_ICON_STABILITY_MIN_HITS = 4     # Required consistent detections within TTL to confirm stable
RED_ICON_STABILITY_MAX_HISTORY = 12  # Maximum history entries per spatial bucket


###################################
###  FORBIDDEN ZONE ENFORCEMENT ###
###################################

# Forbidden-zone debounced arbitration (safe vs. forbidden icon classification)
FORBIDDEN_ZONE_DETECTION_PRE_DELAY = 0.020   # Settle time before taking zone snapshot
FORBIDDEN_ZONE_DETECTION_POST_DELAY = 0.025  # Inter-tick pause for debounce consensus
FORBIDDEN_ZONE_DEBOUNCE_TICKS = 1            # Number of snapshot ticks for consensus
FORBIDDEN_ZONE_DEBOUNCE_REQUIRED_CONSENSUS = 1  # Ticks that must agree for decision
FORBIDDEN_ZONE_SCROLL_REENTRY_COOLDOWN = 0.25   # Cooldown before re-entering scroll after forbidden redirect
FORBIDDEN_BLACKOUT_DURATION = 5.0            # Duration to suppress re-detection of blacklisted coordinates

# Pre-click boundary validation delays
FORBIDDEN_ZONE_PRECLICK_VALIDATION_DELAY = 0.015  # Validation window before click execution
FORBIDDEN_ZONE_DOUBLE_CHECK_DELAY = 0.010          # Second-pass verification delay
ASSET_BOUNDARY_PRECHECK_DELAY = 0.020              # Pre-click boundary check delay
ASSET_BOUNDARY_CONFIRM_DELAY = 0.012               # Confirmation delay after boundary check
ASSET_SEGREGATION_DELAY = 0.030                    # Delay for asset category classification


###################################
###    LEVEL TRANSITIONS        ###
###################################

# Level transition timing
LEVEL_TRANSITION_MAX_ATTEMPTS = 5   # Max attempts to find and click new level button
LEVEL_COMPLETION_RECENCY_WINDOW = 5.0  # Seconds within which a recent completion is considered valid
NEW_LEVEL_FAIL_COOLDOWN = 15.0      # Cooldown after failed level transition before retrying

# Transition click timing
NEW_LEVEL_BUTTON_DELAY = 0.45       # Delay between transition sequence clicks
NEW_LEVEL_FOLLOWUP_DELAY = 0.45     # Post-transition load stabilization delay
TRANSITION_POST_CLICK_DELAY = 1.5   # Animation buffer after transition click (menu + travel)
TRANSITION_RETRY_DELAY = 0.15       # Delay between transition retry attempts

# Background new-level monitoring
NEW_LEVEL_INTERRUPT_INTERVAL = 0.060  # Polling interval during interruptible sleeps
NEW_LEVEL_MONITOR_INTERVAL = 0.150    # Background monitor thread capture interval
NEW_LEVEL_OVERRIDE_COOLDOWN = 0.40    # Cooldown between consecutive new-level override triggers

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
ENABLE_NEW_LEVEL_INTERRUPT = False       # Allow priority resolver to trigger level transitions
ENABLE_NO_ICON_SCROLL_INTERRUPT = False  # Allow priority resolver to force scroll when no icons found


###################################
###  ADAPTIVE TUNER SETTINGS    ###
###################################

ADAPTIVE_TUNER_ENABLED = True
ADAPTIVE_TUNER_ALPHA = 0.2              # EMA smoothing factor for success rate tracking

# Success rate thresholds that trigger delay adjustments
ADAPTIVE_TUNER_CLICK_LOW_THRESHOLD = 0.88   # Below this: increase click delay
ADAPTIVE_TUNER_CLICK_HIGH_THRESHOLD = 0.97  # Above this: decrease click delay
ADAPTIVE_TUNER_SEARCH_LOW_THRESHOLD = 0.75  # Below this: increase search interval
ADAPTIVE_TUNER_SEARCH_HIGH_THRESHOLD = 0.90 # Above this: decrease search interval

# Increment/decrement step sizes for each tunable delay
ADAPTIVE_TUNER_CLICK_DELAY_STEP = 0.005     # Click delay increment on low success
ADAPTIVE_TUNER_MOVE_DELAY_STEP = 0.0005     # Move delay increment on low success
ADAPTIVE_TUNER_CLICK_DECREMENT = 0.005      # Click delay decrement on high success
ADAPTIVE_TUNER_MOVE_DECREMENT = 0.001       # Move delay decrement on high success
ADAPTIVE_TUNER_SEARCH_INTERVAL_STEP = 0.005 # Search interval increment on low success
ADAPTIVE_TUNER_UPGRADE_INTERVAL_STEP = 0.0005  # Upgrade interval increment on low success
ADAPTIVE_TUNER_SEARCH_DECREMENT = 0.005     # Search interval decrement on high success
ADAPTIVE_TUNER_UPGRADE_DECREMENT = 0.001    # Upgrade interval decrement on high success

# Range limits for adaptive delays
ADAPTIVE_TUNER_MIN_CLICK_DELAY = 0.045      # Minimum click delay floor
ADAPTIVE_TUNER_MAX_CLICK_DELAY = 0.12       # Maximum click delay ceiling
ADAPTIVE_TUNER_MIN_MOVE_DELAY = 0.002       # Minimum move delay floor
ADAPTIVE_TUNER_MAX_MOVE_DELAY = 0.012       # Maximum move delay ceiling
ADAPTIVE_TUNER_MIN_UPGRADE_INTERVAL = 0.006 # Minimum upgrade check interval floor
ADAPTIVE_TUNER_MAX_UPGRADE_INTERVAL = 0.013 # Maximum upgrade check interval ceiling
ADAPTIVE_TUNER_MIN_SEARCH_INTERVAL = 0.020  # Minimum search interval floor
ADAPTIVE_TUNER_MAX_SEARCH_INTERVAL = 0.14   # Maximum search interval ceiling


###################################
###   AI VISION & LEARNING      ###
###################################

# Vision Optimizer (EMA-based threshold adaptation)
AI_VISION_ENABLED = True
AI_VISION_ALPHA = 0.15                  # EMA blending factor for threshold updates
AI_VISION_ALPHA_MAX = 0.35              # Maximum EMA alpha cap
AI_VISION_CONFIDENCE_BOOST = 0.2        # Threshold boost factor on high-confidence matches
AI_VISION_CONFIDENCE_THRESHOLD = 0.9    # Minimum confidence to trigger threshold boosting

# Box detection AI bounds
AI_BOX_THRESHOLD_MIN = 0.85             # Minimum adaptive threshold for box detection
AI_BOX_THRESHOLD_MAX = 0.995            # Maximum adaptive threshold for box detection
AI_BOX_MISS_WINDOW = 3                  # Consecutive misses before threshold degradation
AI_BOX_MISS_STEP = 0.005                # Threshold reduction per miss event

# Red icon detection AI bounds
AI_RED_ICON_THRESHOLD_MIN = 0.92        # Minimum adaptive threshold for red icon detection
AI_RED_ICON_THRESHOLD_MAX = 0.985       # Maximum adaptive threshold for red icon detection
AI_RED_ICON_MARGIN = 0.01               # Confidence margin subtracted during threshold update
AI_RED_ICON_MISS_WINDOW = 3             # Consecutive misses before threshold degradation
AI_RED_ICON_MISS_STEP = 0.004           # Threshold reduction per miss event

# New level detection AI bounds
AI_NEW_LEVEL_THRESHOLD_MIN = 0.965      # Minimum adaptive threshold for new level detection
AI_NEW_LEVEL_THRESHOLD_MAX = 0.995      # Maximum adaptive threshold for new level detection
AI_NEW_LEVEL_MISS_WINDOW = 3            # Consecutive misses before threshold degradation
AI_NEW_LEVEL_MISS_STEP = 0.004          # Threshold reduction per miss event

# New level red icon detection AI bounds
AI_NEW_LEVEL_RED_ICON_THRESHOLD_MIN = 0.92   # Minimum adaptive threshold
AI_NEW_LEVEL_RED_ICON_THRESHOLD_MAX = 0.99   # Maximum adaptive threshold
AI_NEW_LEVEL_RED_ICON_MISS_WINDOW = 3        # Consecutive misses before threshold degradation
AI_NEW_LEVEL_RED_ICON_MISS_STEP = 0.005      # Threshold reduction per miss event

# Upgrade station detection AI bounds
AI_UPGRADE_STATION_THRESHOLD_MIN = 0.91      # Minimum adaptive threshold
AI_UPGRADE_STATION_THRESHOLD_MAX = 0.99      # Maximum adaptive threshold
AI_UPGRADE_STATION_MISS_WINDOW = 3           # Consecutive misses before threshold degradation
AI_UPGRADE_STATION_MISS_STEP = 0.005         # Threshold reduction per miss event

# Stats upgrade detection AI bounds
AI_STATS_UPGRADE_THRESHOLD_MIN = 0.9         # Minimum adaptive threshold
AI_STATS_UPGRADE_THRESHOLD_MAX = 0.99        # Maximum adaptive threshold
AI_STATS_UPGRADE_MISS_WINDOW = 3             # Consecutive misses before threshold degradation
AI_STATS_UPGRADE_MISS_STEP = 0.005           # Threshold reduction per miss event

# Vision state persistence
AI_VISION_STATE_FILE = f"{LOGS_DIR}/vision_state.json"  # File path for saving vision optimizer state
AI_VISION_SAVE_INTERVAL = 2.0          # Seconds between vision state saves to disk

# Historical Learning system
AI_LEARNING_ENABLED = True
AI_LEARNING_STATE_FILE = f"{LOGS_DIR}/learning_state.json"  # File path for learning state persistence
AI_LEARNING_SAVE_INTERVAL = 2.5        # Seconds between learning state saves to disk
AI_LEARNING_RECORDS_LIMIT = 80         # Maximum historical records retained
AI_LEARNING_THREAD_JOIN_TIMEOUT = 1.0  # Timeout for learning thread shutdown

# Learning range limits (clamping bounds for learned timing values)
AI_LEARNING_MIN_CLICK_DELAY = 0.045    # Minimum learned click delay
AI_LEARNING_MAX_CLICK_DELAY = 0.12     # Maximum learned click delay
AI_LEARNING_MIN_MOVE_DELAY = 0.002     # Minimum learned move delay
AI_LEARNING_MAX_MOVE_DELAY = 0.012     # Maximum learned move delay
AI_LEARNING_MIN_UPGRADE_INTERVAL = 0.006  # Minimum learned upgrade interval
AI_LEARNING_MAX_UPGRADE_INTERVAL = 0.013  # Maximum learned upgrade interval
AI_LEARNING_MIN_SEARCH_INTERVAL = 0.020   # Minimum learned search interval
AI_LEARNING_MAX_SEARCH_INTERVAL = 0.14    # Maximum learned search interval


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
