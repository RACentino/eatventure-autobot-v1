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


###################################
###   MOUSE & INTERACTION       ###
###################################

# Aggressive fast-path timing envelope: keep every interaction above the scrcpy
# tap-registration floor, but remove the previous extra post-click idle window.
CLICK_DELAY = 0.030

# Cursor travel only needs a tiny scheduler gap once the target is verified.
MOUSE_MOVE_DELAY = 0.0025

# Standard taps keep a deliberate dwell, but no longer wait longer than the
# rapid-click path needs for reliable game-side registration.
MOUSE_DOWN_UP_DELAY = 0.016

# Preserve distinct double-clicks while shrinking the idle gap between them.
DOUBLE_CLICK_DELAY = 0.020

# Mouse movement retry and correction
MOUSE_MOVE_RETRIES = 2              # Max retries if mouse fails to reach target position
MOUSE_MOVE_RETRY_DELAY = 0.0008     # Delay between movement retry attempts
MOUSE_TARGET_SETTLE_DELAY = 0.0005  # Final micro-settle once the cursor lands on target
MOUSE_TARGET_TIMEOUT = 0.022        # Max time to wait for cursor to reach target
MOUSE_TARGET_CHECK_INTERVAL = 0.001 # Polling interval during target verification
MOUSE_TARGET_HOVER_DELAY = 0.0005   # Minimal hover beat before click dispatch
MOUSE_STABILIZE_DURATION = 0.003    # Require only a brief stable cursor dwell before clicking
MOUSE_TARGET_RETRIES = 3            # Max retries for target position verification
MOUSE_TARGET_CORRECTION_DELAY = 0.0008  # Delay between correction attempts

# Pre-click stabilization (distance-adaptive)
MOUSE_PRE_CLICK_STABILIZE_BASE = 0.0025    # Base stabilization delay before any click
MOUSE_PRE_CLICK_STABILIZE_MAX = 0.008      # Maximum stabilization delay cap
MOUSE_PRE_CLICK_STABILIZE_DISTANCE_FACTOR = 0.000012  # Additional delay per pixel of mouse travel

# Click retry logic
MOUSE_CLICK_RETRY_COUNT = 2         # Max click retries on registration failure
MOUSE_CLICK_RETRY_SETTLE_DELAY = 0.0015  # Settle delay between click retries


###################################
###    SCROLLING BEHAVIOR       ###
###################################

# Scroll origin for oscillating drag operations
SCROLL_START_POS = (170, 380)       # (x, y) relative to window client area

# Scroll distance parameters
SCROLL_PIXEL_STEP = 100              # Pixels per single scroll step
SCROLL_DISTANCE_RATIO = 1           # Multiplier applied to scroll distance
SCROLL_VERIFICATION_DISTANCE = 125  # Pixel distance for new-level verification scroll

# Incremental Oscillating Search strategy
MAX_SCROLL_CYCLES = 6              # Maximum oscillation cycles per search invocation
SCROLL_INCREMENT_STEP = 2           # Amplitude increment per cycle pair

# This is the first post-drag "thinking" micro-pause. It only covers the tiny
# release-and-stop moment after the pointer finishes the drag, before CV should
# trust the next frame at all.
SCROLL_RELEASE_THINK_DELAY = 0.008

# This is the main visual settle buffer after any scroll. It gives the emulator
# and game one clean frame to stop smearing so the next scan sees settled assets.
POST_SCROLL_VISION_THINK_DELAY = 0.038

# This second micro-pause is intentionally separate so later tuning can widen or
# shrink the final confirmation window without touching the raw drag settle time.
POST_SCROLL_CONFIRM_THINK_DELAY = 0.010

# Reversal scans happen when the content is already near-stationary, so they need
# less waiting than a full scroll settle, but still benefit from one deliberate beat.
OSCILLATION_REVERSAL_THINK_DELAY = 0.012

# The oscillating search already waits through POST_SCROLL_SETTLE after every drag.
# Keep this extra gap tiny; it is only there to avoid scanning on the exact release tick.
SCROLL_INTERVAL_PAUSE = 0.004

# Compose the full post-scroll vision settle from two explicit micro-pause stages:
# one for frame stabilization and one for the final confirm-before-scan beat.
POST_SCROLL_SETTLE = POST_SCROLL_VISION_THINK_DELAY + POST_SCROLL_CONFIRM_THINK_DELAY

# Direction changes only need a small boundary-think pause before the next scan pass.
CYCLE_PAUSE_DURATION = OSCILLATION_REVERSAL_THINK_DELAY

# A more aggressive drag cuts exploration latency sharply, but 110 ms is still
# long enough for the interpolated movement to remain smooth instead of flicking.
SCROLL_DURATION = 0.16

# Twelve steps preserves a smooth linear glide at the shorter duration while
# reducing overhead compared with the original wider, slower motion profile.
SCROLL_STEP_COUNT = 16

# The drag path already includes explicit settle windows; this minimum interval only
# prevents back-to-back scroll commands from stacking on the same scheduler tick.
SCROLL_MIN_INTERVAL = 0.001

# Reuse the dedicated release-think micro-pause so every scroll consumer gets the
# same short mechanical settle before any higher-level vision waits are added.
SCROLL_SETTLE_DELAY = SCROLL_RELEASE_THINK_DELAY


###################################
###    FSM & STATE TIMING       ###
###################################

# Main loop tick rate
# Tighten the outer scheduler so the FSM can react almost immediately once a handler
# finishes. The state-specific floors below still prevent blind over-polling.
MAIN_LOOP_DELAY = 0.004

# This is the steady-state "think" pause between handlers when no larger asset-specific
# settle window is already in effect. It stays small because scrolls and transitions
# now carry their own dedicated micro-pause budgets.
STATE_DELAY = 0.008

# Lower the default handler floor so lightweight states can recycle quickly, while
# still avoiding wasteful zero-gap state churn on identical frames.
STATE_MIN_INTERVAL_DEFAULT = 0.006

# FIND_RED_ICONS is the primary scan loop, so it gets the fastest deliberate cadence.
# OPEN_BOXES and SCROLL keep small guards only because those states already perform
# heavier work internally before returning control to the scheduler.
STATE_MIN_INTERVALS = {
    "FIND_RED_ICONS": 0.022,
    "OPEN_BOXES": 0.010,
    "SCROLL": 0.012,
    # Upgrade-phase floors: prevent the priority resolver from firing mid-interaction.
    # The resolver runs before each handler tick via state_machine.update(), so a 200ms
    # floor ensures the active upgrade flow completes without a second red icon interrupting.
    "SEARCH_UPGRADE_STATION": 0.200,
    "HOLD_UPGRADE_STATION": 0.200,
    "CHECK_UNLOCK": 0.150,
}

# Red icon click offset (applied after detection)
RED_ICON_OFFSET_X = 10              # Horizontal offset from detected center to click point
RED_ICON_OFFSET_Y = 10              # Vertical offset from detected center to click point

# Fixed UI click positions (relative to window client area)
NEW_LEVEL_POS = (171, 434)          # Travel / new level confirmation button
LEVEL_TRANSITION_POS = (174, 520)   # Level transition confirmation button
IDLE_CLICK_POS = (3, 390)           # Safe idle click position (keeps game awake)
STATS_UPGRADE_POS = (270, 304)      # Stats upgrade tap target during stat boost loop
STATS_UPGRADE_BUTTON_POS = (310, 698)  # Stats upgrade menu open button
NEW_LEVEL_BUTTON_POS = (30, 692)    # New level acknowledgement button

# Upgrade station interaction timing
# DEPRECATED: UPGRADE_HOLD_DURATION is no longer used for the primary
# upgrade interaction. Retained as fallback for hold_at() if needed elsewhere.
UPGRADE_HOLD_DURATION = 6           # (Deprecated) Duration (seconds) for legacy hold
UPGRADE_CLICK_INTERVAL = 0.012      # Tap cadence during upgrade hold loop

# Spam-click configuration for upgrade station interaction
# Replaces the old click-and-hold mechanic with rapid sequential left clicks.
SPAM_CLICK_DURATION = 5.0           # Total duration (seconds) to spam-click the upgrade station
SPAM_CLICK_DELAY = 0.012            # Delay (seconds) between individual spam clicks
SPAM_CLICK_JITTER = 0               # Max random pixel offset to vary click position (0 = disabled)
RAPID_CLICK_DOWN_UP_DELAY = 0.0015  # Button-hold dwell for the precise rapid-click path
RAPID_CLICK_SPIN_THRESHOLD = 0.0015  # Final busy-wait window before each scheduled rapid click

# Upgrade-station retries must wait long enough to beat the capture cache, but not
# so long that the bot stares at a settled screen without refreshing its search.
UPGRADE_SEARCH_INTERVAL = 0.045     # Stay above the capture-cache floor while refreshing station scans quickly

STATS_UPGRADE_CLICK_DURATION = 2    # Duration (seconds) of rapid stat upgrade tap loop
STATS_UPGRADE_CLICK_DELAY = 0.007   # Delay between individual stat upgrade taps
STATS_ICON_PADDING = 20             # Pixel padding for stats icon bounding box

# Idle clicks are only there to keep the UI awake. This settle is shortened so the
# bot can resume scanning faster once the tap lands, while still waiting out tap blur.
IDLE_CLICK_SETTLE_DELAY = 0.035     # Idle keep-alive taps should clear quickly and return control to scanning

# A slightly shorter cooldown keeps the keep-alive tap available sooner in sparse
# screens without turning it into a noisy extra action on every pass.
IDLE_CLICK_COOLDOWN = 0.10

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

# Keep the temporal stability window long enough to ride out short CV flicker, but
# shorter than before so stale icon history does not slow reacquisition after scrolls.
RED_ICON_STABILITY_CACHE_TTL = 1.2  # Raised from 0.75 to require longer sustained presence before actionability

# Tighten the spatial radius slightly so confirmation stays decisive and tied to the
# same on-screen icon instead of blending nearby red noise into one track.
RED_ICON_STABILITY_RADIUS = 10

# Two confirmations plus the existing color/pixel gates shortens click latency
# materially while staying guarded against single-frame red noise.
RED_ICON_STABILITY_MIN_HITS = 3     # Raised from 2 to require 3 confirmations, preventing premature interrupts

# A smaller history buffer matches the shorter TTL and keeps the temporal gate focused
# on recent evidence instead of carrying too much already-obsolete icon state.
RED_ICON_STABILITY_MAX_HISTORY = 8  # Raised from 6 to support the longer stability TTL window


###################################
###  FORBIDDEN ZONE ENFORCEMENT ###
###################################

# Forbidden-zone debounced arbitration (safe vs. forbidden icon classification)
FORBIDDEN_ZONE_DETECTION_PRE_DELAY = 0.004   # Settle time before taking zone snapshot
FORBIDDEN_ZONE_DETECTION_POST_DELAY = 0.004  # Inter-tick pause for debounce consensus
FORBIDDEN_ZONE_DEBOUNCE_TICKS = 1            # Number of snapshot ticks for consensus
FORBIDDEN_ZONE_DEBOUNCE_REQUIRED_CONSENSUS = 1  # Ticks that must agree for decision
FORBIDDEN_ZONE_SCROLL_REENTRY_COOLDOWN = 0.10   # Cooldown before re-entering scroll after forbidden redirect
FORBIDDEN_BLACKOUT_DURATION = 5.0            # Duration to suppress re-detection of blacklisted coordinates

# Pre-click boundary validation delays
FORBIDDEN_ZONE_PRECLICK_VALIDATION_DELAY = 0.003  # Validation window before click execution
FORBIDDEN_ZONE_DOUBLE_CHECK_DELAY = 0.002         # Second-pass verification delay
ASSET_BOUNDARY_PRECHECK_DELAY = 0.003             # Pre-click boundary check delay
ASSET_BOUNDARY_CONFIRM_DELAY = 0.002              # Confirmation delay after boundary check
ASSET_SEGREGATION_DELAY = 0.006                   # Delay for asset category classification


###################################
###    LEVEL TRANSITIONS        ###
###################################

# Level transition timing
LEVEL_TRANSITION_MAX_ATTEMPTS = 5   # Max attempts to find and click new level button
LEVEL_COMPLETION_RECENCY_WINDOW = 5.0  # Seconds within which a recent completion is considered valid
NEW_LEVEL_FAIL_COOLDOWN = 15.0      # Cooldown after failed level transition before retrying

# Transition click timing
# The acknowledgment tap does not need the original half-second pause; 200 ms is
# enough for the first UI response to begin before the travel-confirm phase starts.
NEW_LEVEL_BUTTON_DELAY = 0.20

# This is the post-transition "thinking" phase for major screen changes. It is long
# enough for the new restaurant view to finish drawing, but short enough to avoid
# burning time once the transition has visibly settled.
NEW_LEVEL_FOLLOWUP_DELAY = 0.20

TRANSITION_POST_CLICK_DELAY = 1.00  # Animation buffer after transition click (menu + travel)
TRANSITION_RETRY_DELAY = 0.08       # Delay between transition retry attempts

# Faster interrupt polling lets long sleeps break sooner when a new level appears,
# which reduces dead time without changing the priority logic itself.
NEW_LEVEL_INTERRUPT_INTERVAL = 0.015

# The background watcher should sample often enough to notice the travel button early,
# but not so fast that it competes with the active FSM for every frame.
NEW_LEVEL_MONITOR_INTERVAL = 0.05

# A shorter override cooldown makes repeated, legitimate transition signals respond
# faster while still blocking accidental double-trigger echoes from the same event.
NEW_LEVEL_OVERRIDE_COOLDOWN = 0.12

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

# Keep the adaptive tuner enabled so the bot can still ease off slightly if accuracy
# drops, but tighten the allowed range so it stays inside the new fast-response envelope.
ADAPTIVE_TUNER_ENABLED = True
ADAPTIVE_TUNER_ALPHA = 0.2              # EMA smoothing factor for success rate tracking

# Success rate thresholds that trigger delay adjustments
ADAPTIVE_TUNER_CLICK_LOW_THRESHOLD = 0.88   # Below this: increase click delay
ADAPTIVE_TUNER_CLICK_HIGH_THRESHOLD = 0.97  # Above this: decrease click delay
ADAPTIVE_TUNER_SEARCH_LOW_THRESHOLD = 0.75  # Below this: increase search interval
ADAPTIVE_TUNER_SEARCH_HIGH_THRESHOLD = 0.90 # Above this: decrease search interval

# Increment/decrement step sizes for each tunable delay
ADAPTIVE_TUNER_CLICK_DELAY_STEP = 0.003     # Click delay increment on low success
ADAPTIVE_TUNER_MOVE_DELAY_STEP = 0.00025    # Move delay increment on low success
ADAPTIVE_TUNER_CLICK_DECREMENT = 0.002      # Click delay decrement on high success
ADAPTIVE_TUNER_MOVE_DECREMENT = 0.0005      # Move delay decrement on high success
ADAPTIVE_TUNER_SEARCH_INTERVAL_STEP = 0.004 # Search interval increment on low success
ADAPTIVE_TUNER_UPGRADE_INTERVAL_STEP = 0.0005  # Upgrade interval increment on low success
ADAPTIVE_TUNER_SEARCH_DECREMENT = 0.003     # Search interval decrement on high success
ADAPTIVE_TUNER_UPGRADE_DECREMENT = 0.0005   # Upgrade interval decrement on high success

# Range limits for adaptive delays
# Do not let the tuner slow clicks back to the older, more conservative envelope;
# this narrower range preserves speed while still giving it room to recover from misses.
ADAPTIVE_TUNER_MIN_CLICK_DELAY = 0.028

# Cap the upper click delay lower than before so the tuner cannot drift into visibly
# sluggish input timing after a few bad samples.
ADAPTIVE_TUNER_MAX_CLICK_DELAY = 0.055

# Movement correction still needs a small floor for cursor verification to remain stable.
ADAPTIVE_TUNER_MIN_MOVE_DELAY = 0.0015

# Reduce the maximum movement delay so the tuner keeps cursor travel responsive.
ADAPTIVE_TUNER_MAX_MOVE_DELAY = 0.0035

ADAPTIVE_TUNER_MIN_UPGRADE_INTERVAL = 0.0045 # Minimum upgrade check interval floor
ADAPTIVE_TUNER_MAX_UPGRADE_INTERVAL = 0.009  # Maximum upgrade check interval ceiling

# The search interval floor must stay above the capture-cache TTL so retry scans see
# fresh frames, but it should still be aggressive once the screen is static.
ADAPTIVE_TUNER_MIN_SEARCH_INTERVAL = 0.028

# Prevent the tuner from climbing back to the previously observed 140 ms search pace,
# which materially slows upgrade-station reacquisition after a red-icon click.
ADAPTIVE_TUNER_MAX_SEARCH_INTERVAL = 0.055


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
AI_RED_ICON_THRESHOLD_MIN = 0.91        # Allow adaptive degradation below the base floor after repeated misses
AI_RED_ICON_THRESHOLD_MAX = 0.95        # Prevent the optimizer from ratcheting red-icon confidence back into a brittle range
AI_RED_ICON_BOOTSTRAP_MAX = 0.94        # Cap persisted startup state so stale runs cannot relaunch with an already-overstrict red threshold
AI_RED_ICON_MARGIN = 0.02               # Confidence margin subtracted during threshold update
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
AI_VISION_SAVE_INTERVAL = 15.0         # Batch persistence more coarsely to keep the hot path focused on CV/input

# Historical Learning system
# Disable historical timing replay while manual performance tuning is active. Persisted
# learned profiles are applied on startup and can silently restore slower search values.
AI_LEARNING_ENABLED = False

# Blank the learning-state path so no old timing profile is reloaded over the tuned
# config defaults, and no new runtime profile is saved while benchmarking these values.
AI_LEARNING_STATE_FILE = ""

AI_LEARNING_SAVE_INTERVAL = 2.5        # Seconds between learning state saves to disk
AI_LEARNING_RECORDS_LIMIT = 80         # Maximum historical records retained
AI_LEARNING_THREAD_JOIN_TIMEOUT = 1.0  # Timeout for learning thread shutdown

# Learning range limits (clamping bounds for learned timing values)
# Keep the learning clamps aligned with the new fast-response timing envelope so, if
# learning is re-enabled later, it cannot immediately expand back into slow defaults.
AI_LEARNING_MIN_CLICK_DELAY = 0.028

# Cap any future learned click delay near the same upper bound used by the tuner.
AI_LEARNING_MAX_CLICK_DELAY = 0.055

AI_LEARNING_MIN_MOVE_DELAY = 0.0015    # Minimum learned move delay

# Match the adaptive-tuner movement ceiling so future learning stays within the same feel.
AI_LEARNING_MAX_MOVE_DELAY = 0.0035

AI_LEARNING_MIN_UPGRADE_INTERVAL = 0.0045  # Minimum learned upgrade interval
AI_LEARNING_MAX_UPGRADE_INTERVAL = 0.009   # Maximum learned upgrade interval

# Keep future learned search timings above the fresh-frame threshold but well below
# the sluggish 140 ms profile currently stored in the old learning state.
AI_LEARNING_MIN_SEARCH_INTERVAL = 0.028

# Mirror the tuned upper ceiling so future learning cannot silently undo the faster scan loop.
AI_LEARNING_MAX_SEARCH_INTERVAL = 0.055


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

