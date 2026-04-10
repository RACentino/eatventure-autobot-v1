from pathlib import Path


# =========================
# Paths and window setup
# =========================

# This is the project folder that every other relative path is built from.
BASE_DIR = Path(__file__).resolve().parent

# This is the folder that stores the PNG templates the bot searches for on screen.
ASSETS_DIR = str(BASE_DIR / "Assets")

# This is the folder where the bot writes its runtime logs.
LOGS_DIR = str(BASE_DIR / "logs")

# This is the exact scrcpy window title the bot must find before it can start.
WINDOW_TITLE = "EatventureAuto"

# This is the width the bot asks Windows to resize the game window to.
WINDOW_WIDTH = 300 * 1.2

# This is the height the bot asks Windows to resize the game window to.
WINDOW_HEIGHT = 650 * 1.2


# =========================
# Debugging and visibility
# =========================

# This turns verbose console logging on when you need to troubleshoot behavior.
DEBUG = False

# This shows the internal red-mask debug view so you can see what the bot thinks is "red."
DEBUG_VISION = False

# This draws the red forbidden-zone overlay on top of the game window.
ShowForbiddenArea = False

# This lets the bot request a sharper Windows timer for tighter sleep timing.
ENABLE_WINDOWS_TIMER_RESOLUTION = True

# This is the timer precision the bot asks Windows for, in milliseconds.
WINDOWS_TIMER_RESOLUTION_MS = 1


# =========================
# Base vision thresholds
# =========================

# This is the general confidence floor for single-template matches.
MATCH_THRESHOLD = 0.975

# This is the normal confidence floor for regular red icon detection.
RED_ICON_THRESHOLD = 0.92

# This is the confidence floor for the special red icon that signals a new level.
NEW_LEVEL_RED_ICON_THRESHOLD = 0.942

# This is the confidence floor for the red stats icon near the upgrade menu.
STATS_RED_ICON_THRESHOLD = 0.973

# This is the confidence floor for the main upgrade-station template.
UPGRADE_STATION_THRESHOLD = 0.944

# This is the confidence floor for gift box detection.
BOX_THRESHOLD = 0.973

# This is the confidence floor for the unlock button after a transition.
UNLOCK_THRESHOLD = 0.958

# This is the confidence floor for the main "new level" button.
NEW_LEVEL_THRESHOLD = 0.984

# This is how many matching red-icon hits must agree before a normal red icon is accepted.
RED_ICON_MIN_MATCHES = 1

# This is how many matching hits must agree before the new-level red icon is accepted.
NEW_LEVEL_RED_ICON_MIN_MATCHES = 1

# This is the minimum number of red pixels a candidate needs before it is treated as real.
RED_ICON_PIXEL_THRESHOLD = 50

# This is the kernel size used to clean up red-mask noise before counting pixels.
RED_ICON_DILATE_KERNEL = 3


# =========================
# Red icon color gates
# =========================

# This is the first lower HSV bound for red pixels.
RED_HSV_LOWER1 = (0, 110, 120)

# This is the first upper HSV bound for red pixels.
RED_HSV_UPPER1 = (12, 255, 255)

# This is the second lower HSV bound for red pixels.
RED_HSV_LOWER2 = (166, 110, 120)

# This is the second upper HSV bound for red pixels.
RED_HSV_UPPER2 = (179, 255, 255)

# This turns the extra red-color safety gate on before the bot trusts a red icon.
RED_ICON_COLOR_CHECK = True

# This is the minimum red-dominance ratio a candidate must have to count as a real red icon.
RED_ICON_COLOR_MIN_RATIO = 1.35

# This is the maximum red-dominance ratio allowed before a candidate looks suspicious and gets rejected.
RED_ICON_COLOR_MAX_RATIO = 3.35

# This is the minimum average strength of the red channel inside the sampled area.
RED_ICON_COLOR_MIN_MEAN = 56

# This is the square sample size, in pixels, used for the red-color check.
RED_ICON_COLOR_SAMPLE_SIZE = 24


# =========================
# Red icon template gates
# =========================

# This turns the detailed template-shape verification pass on for red icons.
RED_ICON_TEMPLATE_VERIFY = True

# This is how many pixels the template gate is allowed to shift while fine-aligning a candidate.
RED_ICON_TEMPLATE_VERIFY_MAX_OFFSET = 2

# This is the minimum amount of the template area that must contain matching red pixels.
RED_ICON_TEMPLATE_MIN_COVERAGE = 0.32

# This is the minimum precision score required for the red-template gate to pass.
RED_ICON_TEMPLATE_MIN_PRECISION = 0.58

# This is the minimum recall score required for the red-template gate to pass.
RED_ICON_TEMPLATE_MIN_RECALL = 0.62

# This is the minimum overlap score required between the live icon and the saved template.
RED_ICON_TEMPLATE_MIN_IOU = 0.48

# This is the minimum color-histogram similarity required for the final red-template check.
RED_ICON_TEMPLATE_COLOR_SIMILARITY = 0.41

# This is how much extra padding the bot includes when re-checking whether a red icon is still present.
RED_ICON_VERIFY_PADDING = 28

# This is how close the verification hit must be to the original red-icon location.
RED_ICON_VERIFY_TOLERANCE = 14

# This is how far around a red icon the bot searches when it tries to re-center the click target.
RED_ICON_REFINE_RADIUS = 20

# This is how much the red-icon threshold is relaxed during that local re-centering scan.
RED_ICON_REFINE_THRESHOLD_DROP = 0.025

# This is how much easier the backup second-pass red-icon search becomes.
RED_ICON_SECOND_PASS_THRESHOLD_DROP = 0.020

# This is the list of backup size multipliers the bot tries when a red icon looks slightly scaled.
RED_ICON_FALLBACK_SCALES = (0.94, 1.0, 1.06, 1.12)


# =========================
# Upgrade and generic color checks
# =========================

# This turns the extra color gate on for upgrade-station refinement.
UPGRADE_STATION_COLOR_CHECK = True

# This is the local search radius used to re-center the upgrade-station match.
UPGRADE_STATION_REFINE_RADIUS = 32

# This is the smaller local search radius used to refine the actual click point on the station.
UPGRADE_STATION_CLICK_REFINE_RADIUS = 22

# This is the lower HSV bound for the cyan/blue part of the upgrade station.
UPGRADE_STATION_HSV_LOWER = (90, 95, 190)

# This is the upper HSV bound for the cyan/blue part of the upgrade station.
UPGRADE_STATION_HSV_UPPER = (107, 220, 255)

# This is the minimum amount of upgrade-station color that must be present for a candidate to pass.
UPGRADE_STATION_HSV_MIN_RATIO = 0.52

# This is the minimum color-histogram similarity required for generic color verification.
COLOR_SIMILARITY_THRESHOLD = 0.32


# =========================
# Mouse movement and clicks
# =========================

# This is the normal pause after a click so the UI has time to react.
CLICK_DELAY = 0.016

# This is the normal pause after moving the cursor to a new point.
MOUSE_MOVE_DELAY = 0.010

# This is how long the left mouse button stays down during a standard click.
MOUSE_DOWN_UP_DELAY = 0.016

# This is how many times the bot retries a click if the cursor is not settled correctly.
MOUSE_CLICK_RETRY_COUNT = 2

# This is the tiny pause between click retries while the cursor settles.
MOUSE_CLICK_RETRY_SETTLE_DELAY = 0.016

# This is the minimum gap the bot enforces between separate clicks.
MIN_CLICK_INTERVAL = 0.016

# This is how many times the bot retries a cursor move before giving up on exact positioning.
MOUSE_MOVE_RETRIES = 2

# This is the pause between those move retries.
MOUSE_MOVE_RETRY_DELAY = 0.010

# This is the pause after the cursor first reaches a target, before the bot trusts it is stable.
MOUSE_TARGET_SETTLE_DELAY = 0.016

# This is the longest time the bot will wait for the cursor to settle on a target.
MOUSE_TARGET_TIMEOUT = 0.040

# This is how often the bot re-checks the cursor while waiting for it to settle.
MOUSE_TARGET_CHECK_INTERVAL = 0.010

# This is the extra hover pause once the cursor appears to be on target.
MOUSE_TARGET_HOVER_DELAY = 0.005

# This is the final stability window the cursor must survive before a click is allowed.
MOUSE_STABILIZE_DURATION = 0.010

# This is how many correction attempts are allowed if the cursor is still slightly off target.
MOUSE_TARGET_RETRIES = 2

# This is the pause between those correction nudges.
MOUSE_TARGET_CORRECTION_DELAY = 0.010

# This is how many pixels of cursor error the bot still considers "close enough."
MOUSE_POSITION_TOLERANCE = 1

# This is the shortest pre-click settle time the bot always waits, even for tiny cursor moves.
MOUSE_PRE_CLICK_STABILIZE_BASE = 0.010

# This is the longest pre-click settle time allowed for long cursor travel.
MOUSE_PRE_CLICK_STABILIZE_MAX = 0.020

# This is how much extra settle time gets added as cursor travel distance grows.
MOUSE_PRE_CLICK_STABILIZE_DISTANCE_FACTOR = 0.00002


# =========================
# Scroll motion and pacing
# =========================

# This is the window-relative coordinate where every drag-based scroll starts.
SCROLL_START_POS = (170, 380)

# This is the base scroll distance, in pixels, for one search drag.
SCROLL_PIXEL_STEP = 90

# This is the multiplier applied to the base scroll distance.
SCROLL_DISTANCE_RATIO = 1

# This is the vertical distance used by the special verification drag during level checks.
SCROLL_VERIFICATION_DISTANCE = 300

# This is the highest search-cycle number the oscillating scroll pattern will reach before wrapping.
MAX_SCROLL_CYCLES = 9

# This is how many extra drag steps each wider oscillation cycle adds.
SCROLL_INCREMENT_STEP = 1

# This is the pause after a scroll before the bot continues the rest of that search step.
SCROLL_INTERVAL_PAUSE = 0.066

# This is the settle time after a scroll so the game screen can stop moving.
POST_SCROLL_SETTLE = 0.280

# This is the pause inserted when one leg of the oscillation finishes.
CYCLE_PAUSE_DURATION = 0.120

# This is the drag duration for a normal search scroll.
SCROLL_DURATION = 0.150

# This is how many cursor waypoints the bot uses while dragging a scroll gesture.
SCROLL_STEP_COUNT = 16

# This is the minimum allowed gap between drag gestures.
SCROLL_MIN_INTERVAL = 0.066

# This is the extra pause after a full up-and-down oscillation cycle completes.
OSCILLATION_CYCLE_COOLDOWN = 0.180

# This is the settle time after the drag helper releases the mouse button.
SCROLL_SETTLE_DELAY = 0.200


# =========================
# Main loop and state pacing
# =========================

# This is the idle sleep used by the launcher loop while the bot is not actively running.
MAIN_LOOP_DELAY = 0.002

# This is the short pause between certain major state transitions.
STATE_DELAY = 0.016

# This is the fallback minimum gap between two runs of the same state handler.
STATE_MIN_INTERVAL_DEFAULT = 0.016

# This table lets each state have its own minimum re-run delay.
STATE_MIN_INTERVALS = {
    # This slows down red-icon scans just enough to avoid over-polling the same frame.
    "FIND_RED_ICONS": 0.033,
    # This is the minimum gap between box-opening passes.
    "OPEN_BOXES": 0.033,
    # This is the minimum gap between scroll handlers.
    "SCROLL": 0.180,
    # This is the minimum gap between upgrade-station search attempts.
    "SEARCH_UPGRADE_STATION": 0.033,
    # This is the minimum gap between red-icon click handlers.
    "CLICK_RED_ICON": 0.033,
    # This is the minimum gap between upgrade-station spam-click handlers.
    "HOLD_UPGRADE_STATION": 0.033,
    # This is the minimum gap between unlock checks.
    "CHECK_UNLOCK": 0.033,
    # This is the minimum gap between new-level verification passes.
    "CHECK_NEW_LEVEL": 0.033,
    # This is the minimum gap between stat-upgrade handlers.
    "UPGRADE_STATS": 0.033,
    # This is the minimum gap between transition attempts.
    "TRANSITION_LEVEL": 0.050,
    # This is the minimum gap between unlock hot-loop state entries.
    "WAIT_FOR_UNLOCK": 0.016,
}


# =========================
# Fixed click targets
# =========================

# This is the horizontal offset added to a red icon before clicking the actual station behind it.
RED_ICON_OFFSET_X = 10

# This is the vertical offset added to a red icon before clicking the actual station behind it.
RED_ICON_OFFSET_Y = 10

# This is the backup position for the first travel click during a level transition.
NEW_LEVEL_POS = (171, 434)

# This is the backup position for the second travel click during a level transition.
LEVEL_TRANSITION_POS = (174, 520)

# This is the harmless idle click position the bot uses to dismiss hover states and reset focus.
IDLE_CLICK_POS = (2, 390)

# This is the point the bot rapid-clicks inside the stats menu once it is open.
STATS_UPGRADE_POS = (270, 304)

# This is the button position used to open the stats menu.
STATS_UPGRADE_BUTTON_POS = (310, 698)

# This is the fixed position for acknowledging the "new level" button.
NEW_LEVEL_BUTTON_POS = (30, 692)


# =========================
# Action timing
# =========================

# This is how long the bot rapid-clicks an upgrade station before moving on.
SPAM_CLICK_DURATION = 4

# This is the gap between those rapid upgrade clicks.
SPAM_CLICK_DELAY = 0.016

# This is the random wiggle range added to rapid clicks; zero keeps every click perfectly still.
SPAM_CLICK_JITTER = 0

# This is how long each rapid click keeps the mouse button held down.
RAPID_CLICK_DOWN_UP_DELAY = 0.010

# This is the cutoff where the rapid-click scheduler stops sleeping and spins for precision instead.
RAPID_CLICK_SPIN_THRESHOLD = 0.005

# This is the default pause between repeated upgrade-station search attempts.
UPGRADE_SEARCH_INTERVAL = 0.033

# This is how long the bot rapid-clicks inside the stats menu.
STATS_UPGRADE_CLICK_DURATION = 3.0

# This is the gap between those stat-upgrade clicks.
STATS_UPGRADE_CLICK_DELAY = 0.016

# This is the extra padding around the stat-icon search box so the bot does not crop it too tightly.
STATS_ICON_PADDING = 20

# This is the pause after the bot taps its idle spot and before it continues.
IDLE_CLICK_SETTLE_DELAY = 0.016

# This is the minimum gap between two idle clicks.
IDLE_CLICK_COOLDOWN = 0.033


# =========================
# Detection clustering and caches
# =========================

# This is the minimum spacing between separate red-icon detections so duplicates do not pile up.
RED_ICON_MIN_DISTANCE = 80

# This is how close two red-icon hits can be before the bot merges them into one target.
RED_ICON_MERGE_PROXIMITY = 10

# This is the bucket size used by the red-icon merge grid.
RED_ICON_MERGE_BUCKET_SIZE = 10

# This is how many times the bot will look for an upgrade station before giving up for that icon.
UPGRADE_STATION_SEARCH_MAX_ATTEMPTS = 3

# This is how much easier the station threshold becomes after repeated misses.
UPGRADE_STATION_RELAXED_THRESHOLD_DROP = 0.028

# This is the attempt number where that relaxed station threshold starts being used.
UPGRADE_STATION_RELAXED_ATTEMPT_TRIGGER = 1

# This is how long a captured screenshot stays valid in the short-term cache.
CAPTURE_CACHE_TTL = 0.016

# This is how long the special new-level red-icon result stays cached.
NEW_LEVEL_RED_ICON_CACHE_TTL = 0.016

# This is how long red-icon history is kept for stability checks and template priority decay.
RED_ICON_STABILITY_CACHE_TTL = 0.33

# This is how close two red-icon positions must be across frames to count as the same target.
RED_ICON_STABILITY_RADIUS = 14

# This is how many sightings a red icon needs across recent frames before it is treated as stable.
RED_ICON_STABILITY_MIN_HITS = 2

# This is the maximum number of recent red-icon snapshots kept in history.
RED_ICON_STABILITY_MAX_HISTORY = 12

# This is the maximum number of red icons the bot keeps from a single prioritized scan.
RED_ICON_MAX_PER_SCAN = 1

# This is how many red-icon templates are allowed to stay in the "recently successful" priority list.
RED_ICON_PRIORITY_TEMPLATE_LIMIT = 8


# =========================
# Forbidden-zone handling
# =========================

# This is the pause before the bot starts the debounced safe-vs-forbidden red-icon check.
FORBIDDEN_ZONE_DETECTION_PRE_DELAY = 0.016

# This is the pause between repeated snapshots during that debounce check.
FORBIDDEN_ZONE_DETECTION_POST_DELAY = 0.016

# This is how many safe/forbidden snapshots the bot collects before deciding.
FORBIDDEN_ZONE_DEBOUNCE_TICKS = 2

# This is how many matching snapshots must agree before the bot trusts that decision early.
FORBIDDEN_ZONE_DEBOUNCE_REQUIRED_CONSENSUS = 2

# This is the minimum gap between scroll redirects caused by forbidden-only detections.
FORBIDDEN_ZONE_SCROLL_REENTRY_COOLDOWN = 0.050

# This is how long a blocked world-space coordinate stays on the temporary blacklist.
FORBIDDEN_BLACKOUT_DURATION = 1.0

# This is the pause before the first forbidden-zone safety check right before a click.
FORBIDDEN_ZONE_PRECLICK_VALIDATION_DELAY = 0.005

# This is the pause between the first and second forbidden-zone safety checks.
FORBIDDEN_ZONE_DOUBLE_CHECK_DELAY = 0.005


# =========================
# Transition and unlock flow
# =========================

# This is how many times the bot will look for the new-level button before abandoning the transition.
LEVEL_TRANSITION_MAX_ATTEMPTS = 5

# This is how long a recent completion mark stays trusted for transition bookkeeping.
LEVEL_COMPLETION_RECENCY_WINDOW = 3.0

# This is the cooldown after a failed new-level red-icon detection so the bot does not loop on bad signals.
NEW_LEVEL_FAIL_COOLDOWN = 1.5

# This is the pause after clicking the "new level" acknowledgment button.
NEW_LEVEL_BUTTON_DELAY = 0.050

# This is the final load-stabilization wait after the bot finishes a transition.
NEW_LEVEL_FOLLOWUP_DELAY = 0.250

# This is the animation buffer after travel-confirmation clicks.
TRANSITION_POST_CLICK_DELAY = 0.250

# This is the wait between repeated transition attempts when the button is not found right away.
TRANSITION_RETRY_DELAY = 0.050

# This is how long the bot ignores repeated new-level signals right after a successful transition.
NEW_LEVEL_POST_TRANSITION_IGNORE_WINDOW = 3.0

# This is the sleep slice used by interrupt-aware loops while watching for new-level events.
NEW_LEVEL_INTERRUPT_INTERVAL = 0.016

# This is the base polling rate of the background new-level monitor thread.
NEW_LEVEL_MONITOR_INTERVAL = 0.033

# This is the cooldown that stops the bot from firing the same new-level override too quickly.
NEW_LEVEL_OVERRIDE_COOLDOWN = 0.100

# This is the left edge of the special bottom-screen box where the new-level red icon is expected.
NEW_LEVEL_RED_ICON_X_MIN = 40

# This is the right edge of that new-level red-icon search box.
NEW_LEVEL_RED_ICON_X_MAX = 60

# This is the top edge of that new-level red-icon search box.
NEW_LEVEL_RED_ICON_Y_MIN = 665

# This is the bottom edge of that new-level red-icon search box.
NEW_LEVEL_RED_ICON_Y_MAX = 680

# This is the left edge of the area where the stats red icon is expected.
UPGRADE_RED_ICON_X_MIN = 280

# This is the right edge of the area where the stats red icon is expected.
UPGRADE_RED_ICON_X_MAX = 310

# This is the top edge of the area where the stats red icon is expected.
UPGRADE_RED_ICON_Y_MIN = 665

# This is the bottom edge of the area where the stats red icon is expected.
UPGRADE_RED_ICON_Y_MAX = 680

# This is the normal bottom crop for most gameplay scanning.
MAX_SEARCH_Y = 660

# This is the deeper bottom crop used when the bot also needs to watch the lower UI band.
EXTENDED_SEARCH_Y = 720

# =========================
# Adaptive tuner
# =========================

# This turns the live click/search timing tuner on.
ADAPTIVE_TUNER_ENABLED = True

# This is how quickly the tuner reacts to new success and failure data.
ADAPTIVE_TUNER_ALPHA = 0.25

# This is the click success rate below which the tuner starts slowing clicks down.
ADAPTIVE_TUNER_CLICK_LOW_THRESHOLD = 0.88

# This is the click success rate above which the tuner starts speeding clicks up again.
ADAPTIVE_TUNER_CLICK_HIGH_THRESHOLD = 0.99

# This is the search success rate below which the tuner slows search retries down.
ADAPTIVE_TUNER_SEARCH_LOW_THRESHOLD = 0.86

# This is the search success rate above which the tuner speeds search retries up again.
ADAPTIVE_TUNER_SEARCH_HIGH_THRESHOLD = 0.975

# This is how much click delay increases when click reliability drops.
ADAPTIVE_TUNER_CLICK_DELAY_STEP = 0.004

# This is how much move delay increases when click reliability drops.
ADAPTIVE_TUNER_MOVE_DELAY_STEP = 0.002

# This is how much click delay decreases when reliability is excellent.
ADAPTIVE_TUNER_CLICK_DECREMENT = 0.002

# This is how much move delay decreases when reliability is excellent.
ADAPTIVE_TUNER_MOVE_DECREMENT = 0.001

# This is how much the retry gap grows when search reliability drops.
ADAPTIVE_TUNER_SEARCH_INTERVAL_STEP = 0.008

# This is how much the retry gap shrinks when search reliability is excellent.
ADAPTIVE_TUNER_SEARCH_DECREMENT = 0.004

# This is the fastest click delay the tuner is allowed to use.
ADAPTIVE_TUNER_MIN_CLICK_DELAY = 0.016

# This is the slowest click delay the tuner is allowed to use.
ADAPTIVE_TUNER_MAX_CLICK_DELAY = 0.040

# This is the fastest move delay the tuner is allowed to use.
ADAPTIVE_TUNER_MIN_MOVE_DELAY = 0.010

# This is the slowest move delay the tuner is allowed to use.
ADAPTIVE_TUNER_MAX_MOVE_DELAY = 0.020

# This is the fastest search retry interval the tuner is allowed to use.
ADAPTIVE_TUNER_MIN_SEARCH_INTERVAL = 0.033

# This is the slowest search retry interval the tuner is allowed to use.
ADAPTIVE_TUNER_MAX_SEARCH_INTERVAL = 0.066


# =========================
# Vision optimizer
# =========================

# This turns the self-adjusting vision thresholds on.
AI_VISION_ENABLED = True

# This is the normal blend rate for vision-threshold updates.
AI_VISION_ALPHA = 0.12

# This is the fastest blend rate the vision optimizer is allowed to use.
AI_VISION_ALPHA_MAX = 0.24

# This is the extra blend bonus applied when the bot sees a very confident match.
AI_VISION_CONFIDENCE_BOOST = 0.10

# This is the confidence level where that extra blend bonus starts to kick in.
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

# This caps a restored red-icon threshold from saved memory so startup stays conservative.
AI_RED_ICON_BOOTSTRAP_MAX = 0.932

# This is the safety margin subtracted from recent red-icon confidence before saving a new target threshold.
AI_RED_ICON_MARGIN = 0.018

# This is how many red-icon misses happen before the optimizer lowers the threshold.
AI_RED_ICON_MISS_WINDOW = 4

# This is how much the red-icon threshold is lowered when that miss window is reached.
AI_RED_ICON_MISS_STEP = 0.0020

# This is the lowest new-level button threshold the optimizer is allowed to use.
AI_NEW_LEVEL_THRESHOLD_MIN = 0.975

# This is the highest new-level button threshold the optimizer is allowed to use.
AI_NEW_LEVEL_THRESHOLD_MAX = 0.992

# This is how many missed new-level button scans happen before the threshold is lowered.
AI_NEW_LEVEL_MISS_WINDOW = 4

# This is how much the new-level button threshold is lowered after that many misses.
AI_NEW_LEVEL_MISS_STEP = 0.0020

# This is the lowest new-level red-icon threshold the optimizer is allowed to use.
AI_NEW_LEVEL_RED_ICON_THRESHOLD_MIN = 0.934

# This is the highest new-level red-icon threshold the optimizer is allowed to use.
AI_NEW_LEVEL_RED_ICON_THRESHOLD_MAX = 0.987

# This is how many missed new-level red-icon scans happen before the threshold is lowered.
AI_NEW_LEVEL_RED_ICON_MISS_WINDOW = 4

# This is how much the new-level red-icon threshold is lowered after that many misses.
AI_NEW_LEVEL_RED_ICON_MISS_STEP = 0.0015

# This is the lowest upgrade-station threshold the optimizer is allowed to use.
AI_UPGRADE_STATION_THRESHOLD_MIN = 0.924

# This is the highest upgrade-station threshold the optimizer is allowed to use.
AI_UPGRADE_STATION_THRESHOLD_MAX = 0.968

# This is how many missed upgrade-station scans happen before the threshold is lowered.
AI_UPGRADE_STATION_MISS_WINDOW = 3

# This is how much the upgrade-station threshold is lowered after that many misses.
AI_UPGRADE_STATION_MISS_STEP = 0.0035

# This is the lowest stats-icon threshold the optimizer is allowed to use.
AI_STATS_UPGRADE_THRESHOLD_MIN = 0.93

# This is the highest stats-icon threshold the optimizer is allowed to use.
AI_STATS_UPGRADE_THRESHOLD_MAX = 0.988

# This is how many missed stats-icon scans happen before the threshold is lowered.
AI_STATS_UPGRADE_MISS_WINDOW = 4

# This is how much the stats-icon threshold is lowered after that many misses.
AI_STATS_UPGRADE_MISS_STEP = 0.0020

# This is where the bot saves learned vision thresholds between sessions.
AI_VISION_STATE_FILE = str(BASE_DIR / "memory" / "vision_state.json")

# This is how often the bot is allowed to write that vision-state file.
AI_VISION_SAVE_INTERVAL = 15.0


# =========================
# Historical learner
# =========================

# This turns the background timing learner on.
AI_LEARNING_ENABLED = True

# This is where the bot saves the historical-learning memory file.
AI_LEARNING_STATE_FILE = str(BASE_DIR / "memory" / "learning_state.json")

# This is how often the learner is allowed to write its state to disk.
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

# This is how many of the fastest recent runs get averaged together into a candidate profile.
AI_LEARNING_PROFILE_BLEND_TOP_K = 4

# This is the minimum improvement ratio needed before a learned profile is worth applying.
AI_LEARNING_MIN_IMPROVEMENT_RATIO = 0.025

# This is the cooldown between one learned-profile application and the next.
AI_LEARNING_APPLY_COOLDOWN = 0.9

# This is the fastest click delay the learner is allowed to save or apply.
AI_LEARNING_MIN_CLICK_DELAY = 0.016

# This is the slowest click delay the learner is allowed to save or apply.
AI_LEARNING_MAX_CLICK_DELAY = 0.040

# This is the fastest move delay the learner is allowed to save or apply.
AI_LEARNING_MIN_MOVE_DELAY = 0.010

# This is the slowest move delay the learner is allowed to save or apply.
AI_LEARNING_MAX_MOVE_DELAY = 0.020

# This is the fastest search retry interval the learner is allowed to save or apply.
AI_LEARNING_MIN_SEARCH_INTERVAL = 0.033

# This is the slowest search retry interval the learner is allowed to save or apply.
AI_LEARNING_MAX_SEARCH_INTERVAL = 0.066


# =========================
# Background timing and housekeeping
# =========================

# This is how often the forbidden-zone overlay refreshes its position on screen.
OVERLAY_UPDATE_INTERVAL = 0.033

# This is the hard minimum sleep for the learner loop so it never spins too aggressively.
LEARNING_LOOP_MIN_SLEEP = 0.016

# This is the slower backoff the monitor uses after errors or busy states.
MONITOR_YIELD_BACKOFF = 0.050

# This is the floor under monitor sleeps so polling never becomes too tight.
MONITOR_POLL_MIN_SLEEP = 0.016

# This is the short pause between the two backup clicks in the travel-confirmation sequence.
BACKUP_CLICK_GAP = 0.050

# This is how long the bot waits after clicking unlock before checking whether it disappeared.
UNLOCK_REGISTER_WAIT = 0.050

# This is how long the verification drag lasts during the two-step new-level check.
VERIFICATION_SCROLL_DURATION = 0.280

# This is the maximum time the unlock hot loop will poll after a transition.
UNLOCK_HOT_LOOP_TIMEOUT = 3.0

# This is the gap between unlock-button polls inside that hot loop.
UNLOCK_POLL_INTERVAL = 0.016

# This is how long background thread joins are allowed to block during shutdown.
THREAD_JOIN_TIMEOUT = 0.5

# This is the shortest drag duration the scroll helper is allowed to use.
DRAG_MIN_DURATION = 0.050

# This is the default drag duration used when a caller does not provide one.
DEFAULT_DRAG_DURATION = 0.250

# This is how many times the bot retries a screenshot capture before failing.
WINDOW_CAPTURE_RETRIES = 3

# This is the pause between screenshot capture retries.
WINDOW_CAPTURE_RETRY_DELAY = 0.016


# =========================
# Telegram notifications
# =========================

# Turn this on if you want Telegram start/stop/level notifications.
TELEGRAM_ENABLED = False

# Put your Telegram bot token here if you want notifications.
TELEGRAM_BOT_TOKEN = ""

# Put the target Telegram chat ID here if you want notifications.
TELEGRAM_CHAT_ID = ""


# =========================
# Forbidden click zones
# =========================

# These rectangles mark places the bot must never click because they belong to UI chrome or risky menus.
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
    # This blocks the bottom navigation row where permanent UI buttons live.
    {
        "name": "Zone 5: Bottom navigation bar",
        "coordinate_space": "image",
        "x_min": 55,
        "x_max": 285,
        "y_min": 660,
        "y_max": 725,
    },
    # This blocks the top bar where resource counters and header UI sit.
    {
        "name": "Zone 6: Top bar area",
        "coordinate_space": "image",
        "x_min": 0,
        "x_max": 360,
        "y_min": 0,
        "y_max": 70,
    },
]
