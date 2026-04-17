from pathlib import Path


# Project paths

# This is the main folder that contains the whole bot project.
# The bot uses it to build the folders below automatically, so the paths still work if you move the project.
BASE_DIR = Path(__file__).resolve().parent

# This is the folder where the bot looks for the PNG images it uses to recognize buttons, icons, and boxes.
ASSETS_DIR = str(BASE_DIR / "Assets")

# This is the folder where the bot writes its running log file.
LOGS_DIR = str(BASE_DIR / "logs")

# This is the folder where the bot saves learned AI data so it can remember things between runs.
MEMORY_DIR = BASE_DIR / "memory"


# Window targeting

# This must match the exact title of the game window the bot should find and control.
WINDOW_TITLE = "EatventureAuto"

# This is the width the bot forces the game window to use so all screen positions line up correctly.
WINDOW_WIDTH = 360

# This is the height the bot forces the game window to use so all screen positions line up correctly.
WINDOW_HEIGHT = 780


# Logging and visual helpers

# Turn this on if you want more detailed troubleshooting messages in the console and log file.
DEBUG = True

# Turn this on if you want the bot to draw a red overlay over places it is not allowed to click.
ShowForbiddenArea = False


# Base picture-matching confidence

# This is the fallback confidence score for picture matching when a search does not use its own special threshold.
MATCH_THRESHOLD = 0.98

# This is the starting confidence score for normal red-icon detection before AI vision fine-tunes it.
RED_ICON_THRESHOLD = 0.94

# This is the starting confidence score for the special red icon that means a new level button is available.
NEW_LEVEL_RED_ICON_THRESHOLD = 0.94

# This is the starting confidence score for the red icon that tells the bot a stats upgrade is ready.
STATS_RED_ICON_THRESHOLD = 0.97

# This is the starting confidence score for finding the upgrade station button.
UPGRADE_STATION_THRESHOLD = 0.94

# This is the starting confidence score for finding reward boxes.
BOX_THRESHOLD = 0.97

# This is the confidence score the bot needs before it trusts that the unlock button is really on screen.
UNLOCK_THRESHOLD = 0.90

# This is the confidence score the bot needs before it trusts that the big new-level button is really on screen.
NEW_LEVEL_THRESHOLD = 0.98

# This tells the bot how many separate red-icon matches must agree at nearly the same spot before it trusts the icon.
RED_ICON_MIN_MATCHES = 2


# Base timing and pacing

# This is the normal pause after each click so the game has time to react.
CLICK_DELAY = 0.28

# This is the short pause after moving the mouse so the cursor settles before the next action fires.
MOUSE_MOVE_DELAY = 0.04

# This is the starting wait between repeated upgrade-station searches.
# The adaptive tuner and learner can move this up or down while the bot runs.
UPGRADE_SEARCH_INTERVAL = 0.32

# This is a tiny settle pause the bot uses after important menu actions before doing the next step.
STATE_DELAY = 0.18


# Telegram notifications

# Turn this on if you want the bot to send start, stop, and level-complete messages to Telegram.
TELEGRAM_ENABLED = False

# This is your Telegram bot token.
# It is only needed if Telegram notifications or the chat ID helper script are being used.
TELEGRAM_BOT_TOKEN = ""

# This is the Telegram chat ID that receives the bot's messages.
# It is only needed when Telegram notifications are enabled.
TELEGRAM_CHAT_ID = ""


# Screen search areas

# This tells most searches to ignore everything below this Y position so the bot scans faster and avoids lower-screen noise.
MAX_SEARCH_Y = 660

# This lets a few searches look slightly lower on the screen when they need to see bottom-area UI elements too.
EXTENDED_SEARCH_Y = 710


# Main click targets

# This is the neutral safe tap the bot uses to clear focus, dismiss loose popups, and reset the screen before scanning.
IDLE_CLICK_POS = (2, 390)

# This is the button the bot taps to open the stats upgrade menu.
STATS_UPGRADE_BUTTON_POS = (310, 698)

# This is the spot inside the stats menu that the bot taps repeatedly to buy stat upgrades.
STATS_UPGRADE_POS = (270, 304)

# This is the point where the bot begins its drag gesture when it scrolls the restaurant list.
SCROLL_START_POS = (170, 380)

# This is the small button area the bot taps when the bottom red indicator says a new level is ready.
NEW_LEVEL_BUTTON_POS = (30, 692)

# This is the follow-up spot the bot taps to move through the level-transition screen after opening a new level.
LEVEL_TRANSITION_POS = (174, 520)


# Action behavior

# Turn this on if you want upgrade-station matching to double-check colors as well as shape.
# This can reduce false matches, but it can also miss real matches if the colors on screen look different.
UPGRADE_STATION_COLOR_CHECK = False

# This is how many upgrade taps the bot sends inside the stats menu each time it opens that menu.
STATS_UPGRADE_CLICK_COUNT = 12

# This is the tiny pause between those repeated stat-upgrade taps.
STATS_UPGRADE_CLICK_DELAY = 0.05


# Red-icon click adjustments

# This shifts the red-icon click a little to the right from the matched picture center.
RED_ICON_OFFSET_X = 10

# This shifts the red-icon click a little downward from the matched picture center.
RED_ICON_OFFSET_Y = 10


# New-level red-icon zone

# This is the left edge of the screen zone where a red icon counts as the "new level ready" marker.
NEW_LEVEL_RED_ICON_X_MIN = 40

# This is the right edge of the screen zone where a red icon counts as the "new level ready" marker.
NEW_LEVEL_RED_ICON_X_MAX = 60

# This is the top edge of the screen zone where a red icon counts as the "new level ready" marker.
NEW_LEVEL_RED_ICON_Y_MIN = 665

# This is the bottom edge of the screen zone where a red icon counts as the "new level ready" marker.
NEW_LEVEL_RED_ICON_Y_MAX = 680


# Stats-upgrade red-icon zone

# This is the left edge of the screen zone where a red icon counts as the "stats upgrade available" marker.
UPGRADE_RED_ICON_X_MIN = 280

# This is the right edge of the screen zone where a red icon counts as the "stats upgrade available" marker.
UPGRADE_RED_ICON_X_MAX = 310

# This is the top edge of the screen zone where a red icon counts as the "stats upgrade available" marker.
UPGRADE_RED_ICON_Y_MIN = 665

# This is the bottom edge of the screen zone where a red icon counts as the "stats upgrade available" marker.
UPGRADE_RED_ICON_Y_MAX = 680


# Oscillating scroll behavior

# This is the base vertical drag distance the bot uses for one scroll move before any multiplier is applied.
SCROLL_PIXEL_STEP = 125

# This multiplies the base scroll distance if you want each drag to be shorter or longer without changing the base step.
SCROLL_DISTANCE_RATIO = 1.0

# This is how many outward oscillation cycles the bot completes before the pattern resets back to the beginning.
MAX_SCROLL_CYCLES = 7

# This controls how long the bot stays moving in one direction before the oscillation expands and flips direction.
SCROLL_INCREMENT_STEP = 1

# This is the short pause after a scroll drag finishes before the bot starts scanning again.
SCROLL_INTERVAL_PAUSE = 0.22

# This is extra settling time to let the list stop moving after the drag.
POST_SCROLL_SETTLE = 0.60

# This is how long the drag gesture itself lasts.
SCROLL_DURATION = 0.32


# High-speed clicking

# This is how long the bot keeps machine-gun clicking an upgrade station during one spam-click burst.
SPAM_CLICK_DURATION = 3.2

# This is the gap between clicks during a spam-click burst.
SPAM_CLICK_DELAY = 0.05

# This adds random pixel wiggle to spam-clicking so the pointer can vary slightly around the target.
# Set this to 0 if you want every spam click to land in exactly the same place.
SPAM_CLICK_JITTER = 0

# This is how long the mouse button stays down during one very fast click before it is released again.
RAPID_CLICK_DOWN_UP_DELAY = 0.018


# Adaptive tuner

# Turn this on if you want the bot to automatically speed up or slow down based on recent success rates.
ADAPTIVE_TUNER_ENABLED = False

# This controls how strongly the tuner reacts to fresh success and failure data.
ADAPTIVE_TUNER_ALPHA = 0.12

# If the recent click success score falls below this line, the tuner slows clicking down.
ADAPTIVE_TUNER_CLICK_LOW_THRESHOLD = 0.94

# If the recent click success score rises above this line, the tuner speeds clicking up.
ADAPTIVE_TUNER_CLICK_HIGH_THRESHOLD = 0.999

# If the recent search success score falls below this line, the tuner waits longer between searches.
ADAPTIVE_TUNER_SEARCH_LOW_THRESHOLD = 0.94

# If the recent search success score rises above this line, the tuner retries searches faster.
ADAPTIVE_TUNER_SEARCH_HIGH_THRESHOLD = 0.998

# This is how much extra wait time gets added when the tuner decides clicks are too aggressive.
ADAPTIVE_TUNER_CLICK_DELAY_STEP = 0.015

# This is how much extra mouse-settle time gets added when the tuner decides movement is too aggressive.
ADAPTIVE_TUNER_MOVE_DELAY_STEP = 0.004

# This is how much click wait time gets removed when the tuner decides the bot can safely go faster.
ADAPTIVE_TUNER_CLICK_DECREMENT = 0.002

# This is how much mouse-settle time gets removed when the tuner decides the bot can safely go faster.
ADAPTIVE_TUNER_MOVE_DECREMENT = 0.001

# This is how much extra wait time gets added between searches when search results are poor.
ADAPTIVE_TUNER_SEARCH_INTERVAL_STEP = 0.04

# This is how much wait time gets removed between searches when search results are strong.
ADAPTIVE_TUNER_SEARCH_DECREMENT = 0.005

# This is the fastest click delay the tuner is allowed to use.
ADAPTIVE_TUNER_MIN_CLICK_DELAY = 0.22

# This is the slowest click delay the tuner is allowed to use.
ADAPTIVE_TUNER_MAX_CLICK_DELAY = 0.40

# This is the fastest mouse-settle delay the tuner is allowed to use.
ADAPTIVE_TUNER_MIN_MOVE_DELAY = 0.03

# This is the slowest mouse-settle delay the tuner is allowed to use.
ADAPTIVE_TUNER_MAX_MOVE_DELAY = 0.08

# This is the fastest search retry interval the tuner is allowed to use.
ADAPTIVE_TUNER_MIN_SEARCH_INTERVAL = 0.28

# This is the slowest search retry interval the tuner is allowed to use.
ADAPTIVE_TUNER_MAX_SEARCH_INTERVAL = 0.55


# AI vision general behavior

# Turn this on if you want picture-matching thresholds to learn and adjust themselves while the bot runs.
AI_VISION_ENABLED = True

# This is the normal learning speed AI vision uses when updating a threshold from new evidence.
AI_VISION_ALPHA = 0.12

# This is the fastest learning speed AI vision is ever allowed to use.
AI_VISION_ALPHA_MAX = 0.24

# This adds extra learning speed when the bot sees very confident matches.
AI_VISION_CONFIDENCE_BOOST = 0.10

# A detection must beat this confidence before AI vision starts applying that extra learning boost.
AI_VISION_CONFIDENCE_THRESHOLD = 0.94


# AI vision box tuning

# This is the lowest box-detection threshold AI vision is allowed to relax down to.
AI_BOX_THRESHOLD_MIN = 0.90

# This is the highest box-detection threshold AI vision is allowed to tighten up to.
AI_BOX_THRESHOLD_MAX = 0.992

# This is how many missed box checks in a row it takes before AI vision loosens the box threshold.
AI_BOX_MISS_WINDOW = 4

# This is how much the box threshold is loosened when that miss window is reached.
AI_BOX_MISS_STEP = 0.0025


# AI vision normal red-icon tuning

# This is the lowest normal red-icon threshold AI vision is allowed to relax down to.
AI_RED_ICON_THRESHOLD_MIN = 0.90

# This is the highest normal red-icon threshold AI vision is allowed to tighten up to.
AI_RED_ICON_THRESHOLD_MAX = 0.95

# This is the safety gap AI vision subtracts from the average red-icon confidence so it keeps a little breathing room.
AI_RED_ICON_MARGIN = 0.018

# This is how many missed normal red-icon scans in a row it takes before AI vision loosens the threshold.
AI_RED_ICON_MISS_WINDOW = 4

# This is how much the normal red-icon threshold is loosened when that miss window is reached.
AI_RED_ICON_MISS_STEP = 0.0020


# AI vision big new-level button tuning

# This is the lowest big new-level button threshold AI vision is allowed to relax down to.
AI_NEW_LEVEL_THRESHOLD_MIN = 0.95

# This is the highest big new-level button threshold AI vision is allowed to tighten up to.
AI_NEW_LEVEL_THRESHOLD_MAX = 0.992

# This is how many missed big new-level button checks in a row it takes before AI vision loosens the threshold.
AI_NEW_LEVEL_MISS_WINDOW = 4

# This is how much the big new-level button threshold is loosened when that miss window is reached.
AI_NEW_LEVEL_MISS_STEP = 0.0020


# AI vision new-level red-icon tuning

# This is the lowest special new-level red-icon threshold AI vision is allowed to relax down to.
AI_NEW_LEVEL_RED_ICON_THRESHOLD_MIN = 0.90

# This is the highest special new-level red-icon threshold AI vision is allowed to tighten up to.
AI_NEW_LEVEL_RED_ICON_THRESHOLD_MAX = 0.98

# This is how many missed special new-level red-icon checks in a row it takes before AI vision loosens the threshold.
AI_NEW_LEVEL_RED_ICON_MISS_WINDOW = 4

# This is how much the special new-level red-icon threshold is loosened when that miss window is reached.
AI_NEW_LEVEL_RED_ICON_MISS_STEP = 0.0015


# AI vision upgrade-station tuning

# This is the lowest upgrade-station threshold AI vision is allowed to relax down to.
AI_UPGRADE_STATION_THRESHOLD_MIN = 0.90

# This is the highest upgrade-station threshold AI vision is allowed to tighten up to.
AI_UPGRADE_STATION_THRESHOLD_MAX = 0.97

# This is how many missed upgrade-station searches in a row it takes before AI vision loosens the threshold.
AI_UPGRADE_STATION_MISS_WINDOW = 3

# This is how much the upgrade-station threshold is loosened when that miss window is reached.
AI_UPGRADE_STATION_MISS_STEP = 0.0035


# AI vision stats-upgrade tuning

# This is the lowest stats-upgrade threshold AI vision is allowed to relax down to.
AI_STATS_UPGRADE_THRESHOLD_MIN = 0.90

# This is the highest stats-upgrade threshold AI vision is allowed to tighten up to.
AI_STATS_UPGRADE_THRESHOLD_MAX = 0.99

# This is how many missed stats-upgrade checks in a row it takes before AI vision loosens the threshold.
AI_STATS_UPGRADE_MISS_WINDOW = 4

# This is how much the stats-upgrade threshold is loosened when that miss window is reached.
AI_STATS_UPGRADE_MISS_STEP = 0.0020


# AI vision saved state

# This is the file where AI vision saves its learned threshold values.
AI_VISION_STATE_FILE = str(MEMORY_DIR / "vision_state.json")

# This is the minimum wait between automatic saves of AI vision memory.
AI_VISION_SAVE_INTERVAL = 15.0


# AI learning general behavior

# Turn this on if you want the bot to learn from previous completion times and reuse better timing profiles later.
AI_LEARNING_ENABLED = False

# This is the file where the learning system stores its history and best-known timing profile.
AI_LEARNING_STATE_FILE = str(MEMORY_DIR / "learning_state_stable.json")

# This is the minimum wait between automatic saves of the learning system's memory.
AI_LEARNING_SAVE_INTERVAL = 5.0

# This is the maximum number of past completion records the learning system keeps.
AI_LEARNING_RECORDS_LIMIT = 256

# This is how long bot shutdown waits for the learning thread to stop cleanly.
AI_LEARNING_THREAD_JOIN_TIMEOUT = 0.5

# This is how often the learning thread wakes up to see whether it should build a better timing profile.
AI_LEARNING_THREAD_INTERVAL = 0.75

# This is the small recent-run window used for quick learning passes.
AI_LEARNING_PAIR_WINDOW = 5

# This is the larger recent-run window used for slower, broader learning passes.
AI_LEARNING_BATCH_WINDOW = 15

# This controls how strongly the learner moves toward a better timing profile instead of jumping there all at once.
AI_LEARNING_EMA_ALPHA = 0.10

# This is how many of the best recent runs are averaged together when the learner builds a new timing profile.
AI_LEARNING_PROFILE_BLEND_TOP_K = 3

# The best run must beat the recent average by at least this much before the learner is allowed to apply new settings.
AI_LEARNING_MIN_IMPROVEMENT_RATIO = 0.08

# This is the cooldown time after a learning update before the learner is allowed to apply another one.
AI_LEARNING_APPLY_COOLDOWN = 30.0

# This is the fastest click delay the learner is allowed to apply.
AI_LEARNING_MIN_CLICK_DELAY = 0.22

# This is the slowest click delay the learner is allowed to apply.
AI_LEARNING_MAX_CLICK_DELAY = 0.40

# This is the fastest mouse-settle delay the learner is allowed to apply.
AI_LEARNING_MIN_MOVE_DELAY = 0.03

# This is the slowest mouse-settle delay the learner is allowed to apply.
AI_LEARNING_MAX_MOVE_DELAY = 0.08

# This is the fastest search retry interval the learner is allowed to apply.
AI_LEARNING_MIN_SEARCH_INTERVAL = 0.28

# This is the slowest search retry interval the learner is allowed to apply.
AI_LEARNING_MAX_SEARCH_INTERVAL = 0.55

# This is the hard minimum sleep time for the learner loop so it never spins too fast.
LEARNING_LOOP_MIN_SLEEP = 0.10


# Global forbidden bottom strip

# This is the left edge of the wide bottom strip where clicks are always blocked.
FORBIDDEN_CLICK_X_MIN = 60

# This is the right edge of the wide bottom strip where clicks are always blocked.
FORBIDDEN_CLICK_X_MAX = 280

# This is the top edge of the wide bottom strip where clicks are always blocked.
FORBIDDEN_CLICK_Y_MIN = 668


# Forbidden zone 1

# This is the left edge of forbidden zone 1. If a click lands inside the full zone 1 box, the bot refuses to click there.
FORBIDDEN_ZONE_1_X_MIN = 290

# This is the right edge of forbidden zone 1. If a click lands inside the full zone 1 box, the bot refuses to click there.
FORBIDDEN_ZONE_1_X_MAX = 350

# This is the top edge of forbidden zone 1. If a click lands inside the full zone 1 box, the bot refuses to click there.
FORBIDDEN_ZONE_1_Y_MIN = 93

# This is the bottom edge of forbidden zone 1. If a click lands inside the full zone 1 box, the bot refuses to click there.
FORBIDDEN_ZONE_1_Y_MAX = 270


# Forbidden zone 2

# This is the left edge of forbidden zone 2. If a click lands inside the full zone 2 box, the bot refuses to click there.
FORBIDDEN_ZONE_2_X_MIN = 0

# This is the right edge of forbidden zone 2. If a click lands inside the full zone 2 box, the bot refuses to click there.
FORBIDDEN_ZONE_2_X_MAX = 60

# This is the top edge of forbidden zone 2. If a click lands inside the full zone 2 box, the bot refuses to click there.
FORBIDDEN_ZONE_2_Y_MIN = 50

# This is the bottom edge of forbidden zone 2. If a click lands inside the full zone 2 box, the bot refuses to click there.
FORBIDDEN_ZONE_2_Y_MAX = 280


# Forbidden zone 3

# This is the left edge of forbidden zone 3. If a click lands inside the full zone 3 box, the bot refuses to click there.
FORBIDDEN_ZONE_3_X_MIN = 0

# This is the right edge of forbidden zone 3. If a click lands inside the full zone 3 box, the bot refuses to click there.
FORBIDDEN_ZONE_3_X_MAX = 60

# This is the top edge of forbidden zone 3. If a click lands inside the full zone 3 box, the bot refuses to click there.
FORBIDDEN_ZONE_3_Y_MIN = 590

# This is the bottom edge of forbidden zone 3. If a click lands inside the full zone 3 box, the bot refuses to click there.
FORBIDDEN_ZONE_3_Y_MAX = 667


# Forbidden zone 4

# This is the left edge of forbidden zone 4. If a click lands inside the full zone 4 box, the bot refuses to click there.
FORBIDDEN_ZONE_4_X_MIN = 145

# This is the right edge of forbidden zone 4. If a click lands inside the full zone 4 box, the bot refuses to click there.
FORBIDDEN_ZONE_4_X_MAX = 200

# This is the top edge of forbidden zone 4. If a click lands inside the full zone 4 box, the bot refuses to click there.
FORBIDDEN_ZONE_4_Y_MIN = 65

# This is the bottom edge of forbidden zone 4. If a click lands inside the full zone 4 box, the bot refuses to click there.
FORBIDDEN_ZONE_4_Y_MAX = 110


# Forbidden zone 5

# This is the left edge of forbidden zone 5. If a click lands inside the full zone 5 box, the bot refuses to click there.
FORBIDDEN_ZONE_5_X_MIN = 55

# This is the right edge of forbidden zone 5. If a click lands inside the full zone 5 box, the bot refuses to click there.
FORBIDDEN_ZONE_5_X_MAX = 285

# This is the top edge of forbidden zone 5. If a click lands inside the full zone 5 box, the bot refuses to click there.
FORBIDDEN_ZONE_5_Y_MIN = 660

# This is the bottom edge of forbidden zone 5. If a click lands inside the full zone 5 box, the bot refuses to click there.
FORBIDDEN_ZONE_5_Y_MAX = 725
