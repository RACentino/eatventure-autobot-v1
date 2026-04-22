import json
import logging
import os
import tempfile
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import config
import pywintypes
from image_matcher import ImageMatcher
from mouse_controller import MouseController
from state_machine import State, StateMachine
from telegram_notifier import TelegramNotifier
from window_capture import (
    ForbiddenAreaOverlay,
    WindowCapture,
    WindowCaptureError,
    WindowNotAvailableError,
)

logger = logging.getLogger(__name__)


class AdaptiveTuner:
    def __init__(self):
        self.enabled = bool(config.ADAPTIVE_TUNER_ENABLED)
        self.alpha = float(config.ADAPTIVE_TUNER_ALPHA)
        self.click_success_rate = 1.0
        self.search_success_rate = 1.0
        self.click_delay = float(config.CLICK_DELAY)
        self.move_delay = float(config.MOUSE_MOVE_DELAY)
        self.search_interval = float(config.UPGRADE_SEARCH_INTERVAL)

    def _ema(self, current, new_value):
        return (1.0 - self.alpha) * current + self.alpha * new_value

    def record_click_result(self, success):
        if not self.enabled:
            return
        self.click_success_rate = self._ema(self.click_success_rate, 1.0 if success else 0.0)
        if self.click_success_rate < config.ADAPTIVE_TUNER_CLICK_LOW_THRESHOLD:
            self.click_delay = min(
                self.click_delay + config.ADAPTIVE_TUNER_CLICK_DELAY_STEP,
                config.ADAPTIVE_TUNER_MAX_CLICK_DELAY,
            )
            self.move_delay = min(
                self.move_delay + config.ADAPTIVE_TUNER_MOVE_DELAY_STEP,
                config.ADAPTIVE_TUNER_MAX_MOVE_DELAY,
            )
        elif self.click_success_rate > config.ADAPTIVE_TUNER_CLICK_HIGH_THRESHOLD:
            self.click_delay = max(
                self.click_delay - config.ADAPTIVE_TUNER_CLICK_DECREMENT,
                config.ADAPTIVE_TUNER_MIN_CLICK_DELAY,
            )
            self.move_delay = max(
                self.move_delay - config.ADAPTIVE_TUNER_MOVE_DECREMENT,
                config.ADAPTIVE_TUNER_MIN_MOVE_DELAY,
            )

    def record_search_result(self, success):
        if not self.enabled:
            return
        self.search_success_rate = self._ema(self.search_success_rate, 1.0 if success else 0.0)
        if self.search_success_rate < config.ADAPTIVE_TUNER_SEARCH_LOW_THRESHOLD:
            self.search_interval = min(
                self.search_interval + config.ADAPTIVE_TUNER_SEARCH_INTERVAL_STEP,
                config.ADAPTIVE_TUNER_MAX_SEARCH_INTERVAL,
            )
        elif self.search_success_rate > config.ADAPTIVE_TUNER_SEARCH_HIGH_THRESHOLD:
            self.search_interval = max(
                self.search_interval - config.ADAPTIVE_TUNER_SEARCH_DECREMENT,
                config.ADAPTIVE_TUNER_MIN_SEARCH_INTERVAL,
            )

    def reset(self):
        self.click_success_rate = 1.0
        self.search_success_rate = 1.0
        self.click_delay = float(config.CLICK_DELAY)
        self.move_delay = float(config.MOUSE_MOVE_DELAY)
        self.search_interval = float(config.UPGRADE_SEARCH_INTERVAL)


class VisionPersistence:
    def __init__(self, path, save_interval):
        self.path = path
        self.save_interval = float(save_interval)
        self._last_save_time = 0.0
        self._lock = threading.RLock()

    def load(self):
        if not self.path:
            return {}
        with self._lock:
            if not os.path.exists(self.path):
                return {}
            try:
                with open(self.path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
            except (OSError, TypeError, ValueError) as exc:
                logger.warning("Failed to load persisted state from %s: %s", self.path, exc)
                return {}
        return data if isinstance(data, dict) else {}

    def save(self, state, force=False):
        if not self.path:
            return False

        now = time.monotonic()
        with self._lock:
            if not force and self.save_interval > 0 and (now - self._last_save_time) < self.save_interval:
                return False

            directory = os.path.dirname(self.path)
            target_dir = directory or "."
            temp_path = None
            try:
                if directory:
                    os.makedirs(directory, exist_ok=True)

                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=target_dir,
                    prefix=".state-",
                    suffix=".tmp",
                    delete=False,
                ) as handle:
                    temp_path = handle.name
                    json.dump(state, handle, indent=2, sort_keys=True)

                os.replace(temp_path, self.path)
                self._last_save_time = now
                return True
            except (OSError, TypeError, ValueError) as exc:
                logger.error("Failed to persist state to %s: %s", self.path, exc)
                if temp_path:
                    try:
                        os.remove(temp_path)
                    except OSError:
                        pass
                return False


class VisionOptimizer:
    def __init__(self, persistence=None):
        self.enabled = bool(config.AI_VISION_ENABLED)
        self.alpha = float(config.AI_VISION_ALPHA)
        self.alpha_max = float(config.AI_VISION_ALPHA_MAX)
        self.confidence_boost = float(config.AI_VISION_CONFIDENCE_BOOST)
        self.red_icon_threshold = float(config.RED_ICON_THRESHOLD)
        self.new_level_threshold = float(config.NEW_LEVEL_THRESHOLD)
        self.new_level_red_icon_threshold = float(config.NEW_LEVEL_RED_ICON_THRESHOLD)
        self.upgrade_station_threshold = float(config.UPGRADE_STATION_THRESHOLD)
        self.stats_upgrade_threshold = float(config.STATS_RED_ICON_THRESHOLD)
        self.box_threshold = float(config.BOX_THRESHOLD)
        self.persistence = persistence
        self._miss_counts = {
            "red_icon": 0,
            "new_level": 0,
            "new_level_red_icon": 0,
            "upgrade_station": 0,
            "stats_upgrade": 0,
            "box": 0,
        }

    def _ema(self, current, new_value, alpha=None):
        blend = self.alpha if alpha is None else alpha
        return (1.0 - blend) * current + blend * new_value

    def _adaptive_alpha(self, confidence):
        if confidence <= 0:
            return self.alpha
        boost = (
            max(0.0, min(1.0, confidence - config.AI_VISION_CONFIDENCE_THRESHOLD))
            * self.confidence_boost
        )
        return min(self.alpha + boost, self.alpha_max)

    def _update_threshold(self, name, confidence, minimum, maximum):
        if not self.enabled or confidence <= 0:
            return
        self._miss_counts[name] = 0
        current = getattr(self, f"{name}_threshold")
        target = max(minimum, min(maximum, confidence))
        setattr(self, f"{name}_threshold", self._ema(current, target, self._adaptive_alpha(confidence)))
        self._persist()

    def _update_miss(self, name, minimum, step, window):
        if not self.enabled:
            return
        self._miss_counts[name] += 1
        if self._miss_counts[name] < window:
            return
        self._miss_counts[name] = 0
        current = getattr(self, f"{name}_threshold")
        target = max(minimum, current - step)
        setattr(self, f"{name}_threshold", self._ema(current, target, self.alpha_max))
        self._persist()

    def update_red_icon_scan(self, confidences):
        if not self.enabled:
            return
        if confidences:
            self._miss_counts["red_icon"] = 0
            average = sum(confidences) / len(confidences)
            target = max(
                config.AI_RED_ICON_THRESHOLD_MIN,
                min(average - config.AI_RED_ICON_MARGIN, config.AI_RED_ICON_THRESHOLD_MAX),
            )
            self.red_icon_threshold = self._ema(
                self.red_icon_threshold,
                target,
                self._adaptive_alpha(average),
            )
            self._persist()
            return
        self._update_miss(
            "red_icon",
            config.AI_RED_ICON_THRESHOLD_MIN,
            config.AI_RED_ICON_MISS_STEP,
            config.AI_RED_ICON_MISS_WINDOW,
        )

    def update_new_level_confidence(self, confidence):
        self._update_threshold(
            "new_level",
            confidence,
            config.AI_NEW_LEVEL_THRESHOLD_MIN,
            config.AI_NEW_LEVEL_THRESHOLD_MAX,
        )

    def update_new_level_miss(self):
        self._update_miss(
            "new_level",
            config.AI_NEW_LEVEL_THRESHOLD_MIN,
            config.AI_NEW_LEVEL_MISS_STEP,
            config.AI_NEW_LEVEL_MISS_WINDOW,
        )

    def update_new_level_red_icon_confidence(self, confidence):
        self._update_threshold(
            "new_level_red_icon",
            confidence,
            config.AI_NEW_LEVEL_RED_ICON_THRESHOLD_MIN,
            config.AI_NEW_LEVEL_RED_ICON_THRESHOLD_MAX,
        )

    def update_new_level_red_icon_miss(self):
        self._update_miss(
            "new_level_red_icon",
            config.AI_NEW_LEVEL_RED_ICON_THRESHOLD_MIN,
            config.AI_NEW_LEVEL_RED_ICON_MISS_STEP,
            config.AI_NEW_LEVEL_RED_ICON_MISS_WINDOW,
        )

    def update_upgrade_station_confidence(self, confidence):
        self._update_threshold(
            "upgrade_station",
            confidence,
            config.AI_UPGRADE_STATION_THRESHOLD_MIN,
            config.AI_UPGRADE_STATION_THRESHOLD_MAX,
        )

    def update_upgrade_station_miss(self):
        self._update_miss(
            "upgrade_station",
            config.AI_UPGRADE_STATION_THRESHOLD_MIN,
            config.AI_UPGRADE_STATION_MISS_STEP,
            config.AI_UPGRADE_STATION_MISS_WINDOW,
        )

    def update_stats_upgrade_confidence(self, confidence):
        self._update_threshold(
            "stats_upgrade",
            confidence,
            config.AI_STATS_UPGRADE_THRESHOLD_MIN,
            config.AI_STATS_UPGRADE_THRESHOLD_MAX,
        )

    def update_stats_upgrade_miss(self):
        self._update_miss(
            "stats_upgrade",
            config.AI_STATS_UPGRADE_THRESHOLD_MIN,
            config.AI_STATS_UPGRADE_MISS_STEP,
            config.AI_STATS_UPGRADE_MISS_WINDOW,
        )

    def update_box_confidence(self, confidence):
        self._update_threshold(
            "box",
            confidence,
            config.AI_BOX_THRESHOLD_MIN,
            config.AI_BOX_THRESHOLD_MAX,
        )

    def update_box_miss(self):
        self._update_miss(
            "box",
            config.AI_BOX_THRESHOLD_MIN,
            config.AI_BOX_MISS_STEP,
            config.AI_BOX_MISS_WINDOW,
        )

    def apply_persisted_state(self, state):
        if not state:
            return
        clamps = {
            "red_icon_threshold": (config.AI_RED_ICON_THRESHOLD_MIN, config.AI_RED_ICON_THRESHOLD_MAX),
            "new_level_threshold": (config.AI_NEW_LEVEL_THRESHOLD_MIN, config.AI_NEW_LEVEL_THRESHOLD_MAX),
            "new_level_red_icon_threshold": (
                config.AI_NEW_LEVEL_RED_ICON_THRESHOLD_MIN,
                config.AI_NEW_LEVEL_RED_ICON_THRESHOLD_MAX,
            ),
            "upgrade_station_threshold": (
                config.AI_UPGRADE_STATION_THRESHOLD_MIN,
                config.AI_UPGRADE_STATION_THRESHOLD_MAX,
            ),
            "stats_upgrade_threshold": (
                config.AI_STATS_UPGRADE_THRESHOLD_MIN,
                config.AI_STATS_UPGRADE_THRESHOLD_MAX,
            ),
            "box_threshold": (config.AI_BOX_THRESHOLD_MIN, config.AI_BOX_THRESHOLD_MAX),
        }
        for key, bounds in clamps.items():
            if key not in state:
                continue
            minimum, maximum = bounds
            value = float(state[key])
            setattr(self, key, max(minimum, min(maximum, value)))

    def reset(self):
        self.red_icon_threshold = float(config.RED_ICON_THRESHOLD)
        self.new_level_threshold = float(config.NEW_LEVEL_THRESHOLD)
        self.new_level_red_icon_threshold = float(config.NEW_LEVEL_RED_ICON_THRESHOLD)
        self.upgrade_station_threshold = float(config.UPGRADE_STATION_THRESHOLD)
        self.stats_upgrade_threshold = float(config.STATS_RED_ICON_THRESHOLD)
        self.box_threshold = float(config.BOX_THRESHOLD)
        for key in self._miss_counts:
            self._miss_counts[key] = 0
        self._persist(force=True)

    def _persist(self, force=False):
        if self.persistence is None:
            return
        state = {
            "red_icon_threshold": float(self.red_icon_threshold),
            "new_level_threshold": float(self.new_level_threshold),
            "new_level_red_icon_threshold": float(self.new_level_red_icon_threshold),
            "upgrade_station_threshold": float(self.upgrade_station_threshold),
            "stats_upgrade_threshold": float(self.stats_upgrade_threshold),
            "box_threshold": float(self.box_threshold),
        }
        self.persistence.save(state, force=force)


class HistoricalLearner:
    def __init__(self, bot, persistence=None):
        self.bot = bot
        self.persistence = persistence
        self.enabled = bool(config.AI_LEARNING_ENABLED)
        self.interval = max(config.LEARNING_LOOP_MIN_SLEEP, float(config.AI_LEARNING_THREAD_INTERVAL))
        self.pair_window = max(2, int(config.AI_LEARNING_PAIR_WINDOW))
        self.batch_window = max(2, int(config.AI_LEARNING_BATCH_WINDOW))
        self.ema_alpha = max(0.01, min(0.8, float(config.AI_LEARNING_EMA_ALPHA)))
        self.top_k = max(1, int(config.AI_LEARNING_PROFILE_BLEND_TOP_K))
        self.min_improvement_ratio = max(0.0, float(config.AI_LEARNING_MIN_IMPROVEMENT_RATIO))
        self.apply_cooldown = max(0.0, float(config.AI_LEARNING_APPLY_COOLDOWN))
        self._last_apply_time = 0.0
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._records = []
        self._total_completions = 0
        self._last_pair_processed = 0
        self._last_batch_processed = 0
        self._tuned_behavior = {}

        persisted = self.persistence.load() if self.enabled and self.persistence else {}
        if persisted:
            self._records = list(persisted.get("records", []))[-config.AI_LEARNING_RECORDS_LIMIT :]
            self._total_completions = int(persisted.get("total_completions", len(self._records)))
            self._last_pair_processed = int(persisted.get("last_pair_processed", 0))
            self._last_batch_processed = int(persisted.get("last_batch_processed", 0))
            self._tuned_behavior = dict(persisted.get("tuned_behavior", {}))
            if self._tuned_behavior:
                self.bot.apply_learned_behavior(self._tuned_behavior)

    def start(self):
        if not self.enabled:
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="historical_learner", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=config.AI_LEARNING_THREAD_JOIN_TIMEOUT)
        self._persist(force=True)

    def record_completion(self, seconds_spent, source):
        if not self.enabled or seconds_spent <= 0:
            return
        record = {
            "timestamp": time.time(),
            "time_spent": float(seconds_spent),
            "source": source,
            "behavior": self.bot.get_runtime_behavior_snapshot(),
        }
        with self._lock:
            self._records.append(record)
            self._records = self._records[-config.AI_LEARNING_RECORDS_LIMIT :]
            self._total_completions += 1
        self._persist()

    def reset(self):
        with self._lock:
            self._records = []
            self._total_completions = 0
            self._last_pair_processed = 0
            self._last_batch_processed = 0
            self._tuned_behavior = {}
            self._last_apply_time = 0.0
        self._persist(force=True)

    def _loop(self):
        while not self._stop.is_set():
            try:
                self._run_cycle()
            except Exception:
                logger.exception("Historical learner cycle failed")
            time.sleep(self.interval)

    def _run_cycle(self):
        with self._lock:
            records = list(self._records)
            total = int(self._total_completions)

        if (time.monotonic() - self._last_apply_time) < self.apply_cooldown:
            return

        changed = False
        if total >= self.pair_window and (total // self.pair_window) > self._last_pair_processed:
            changed = self._apply_profile(records[-self.pair_window :]) or changed
            self._last_pair_processed = total // self.pair_window

        if total >= self.batch_window and (total // self.batch_window) > self._last_batch_processed:
            changed = self._apply_profile(records[-self.batch_window :]) or changed
            self._last_batch_processed = total // self.batch_window

        if changed:
            self._last_apply_time = time.monotonic()
        self._persist()

    def _apply_profile(self, records):
        valid = [record for record in records if record.get("time_spent", 0) > 0 and record.get("behavior")]
        if not valid:
            return False

        durations = [record["time_spent"] for record in valid]
        average = sum(durations) / len(durations)
        best = min(valid, key=lambda item: item["time_spent"])
        if average <= 0:
            return False

        improvement_ratio = (average - best["time_spent"]) / average
        if improvement_ratio < self.min_improvement_ratio:
            return False

        ranked = sorted(valid, key=lambda item: item["time_spent"])
        top = ranked[: self.top_k]
        profile = {"click_delay": 0.0, "move_delay": 0.0, "search_interval": 0.0}
        for record in top:
            behavior = record["behavior"]
            for key in profile:
                profile[key] += float(behavior.get(key, 0.0))

        count = float(len(top))
        for key in profile:
            profile[key] /= count

        current = self.bot.get_runtime_behavior_snapshot()
        tuned = {
            "click_delay": self._clamp(
                self._ema(current["click_delay"], profile["click_delay"]),
                config.AI_LEARNING_MIN_CLICK_DELAY,
                config.AI_LEARNING_MAX_CLICK_DELAY,
            ),
            "move_delay": self._clamp(
                self._ema(current["move_delay"], profile["move_delay"]),
                config.AI_LEARNING_MIN_MOVE_DELAY,
                config.AI_LEARNING_MAX_MOVE_DELAY,
            ),
            "search_interval": self._clamp(
                self._ema(current["search_interval"], profile["search_interval"]),
                config.AI_LEARNING_MIN_SEARCH_INTERVAL,
                config.AI_LEARNING_MAX_SEARCH_INTERVAL,
            ),
        }
        self._tuned_behavior = tuned
        self.bot.apply_learned_behavior(tuned)
        return True

    def _ema(self, current, target):
        return (1.0 - self.ema_alpha) * float(current) + self.ema_alpha * float(target)

    @staticmethod
    def _clamp(value, minimum, maximum):
        return max(minimum, min(maximum, value))

    def _persist(self, force=False):
        if self.persistence is None:
            return
        with self._lock:
            state = {
                "records": self._records[-config.AI_LEARNING_RECORDS_LIMIT :],
                "total_completions": self._total_completions,
                "last_pair_processed": self._last_pair_processed,
                "last_batch_processed": self._last_batch_processed,
                "tuned_behavior": self._tuned_behavior,
            }
        self.persistence.save(state, force=force)


class EatventureBot:
    def __init__(self):
        logger.info("Initializing Eatventure Bot")

        self.window_capture = WindowCapture(config.WINDOW_TITLE, config.WINDOW_WIDTH, config.WINDOW_HEIGHT)
        self.image_matcher = ImageMatcher(config.MATCH_THRESHOLD)
        self.mouse_controller = MouseController(
            self.window_capture.get_hwnd,
            config.CLICK_DELAY,
            config.MOUSE_MOVE_DELAY,
        )
        self.state_machine = StateMachine(State.FIND_RED_ICONS)
        self.telegram = TelegramNotifier(
            config.TELEGRAM_BOT_TOKEN,
            config.TELEGRAM_CHAT_ID,
            config.TELEGRAM_ENABLED,
        )

        self.tuner = AdaptiveTuner()
        self.vision_persistence = VisionPersistence(config.AI_VISION_STATE_FILE, config.AI_VISION_SAVE_INTERVAL)
        self.vision_optimizer = VisionOptimizer(self.vision_persistence)
        self.vision_optimizer.apply_persisted_state(self.vision_persistence.load())
        self.learning_persistence = VisionPersistence(
            config.AI_LEARNING_STATE_FILE,
            config.AI_LEARNING_SAVE_INTERVAL,
        )
        self.historical_learner = HistoricalLearner(self, self.learning_persistence)

        self.register_states()
        self.templates = self.load_templates()
        self._red_icon_template_names_cache = self._red_icon_template_names()
        self._red_icon_max_width, self._red_icon_max_height = self._red_icon_template_span()
        self._successful_red_icon_history_limit = 24
        self.running = False
        self.red_icons = []
        self.current_red_icon_index = 0
        self.wait_for_unlock_attempts = 0
        self.max_wait_for_unlock_attempts = 4
        self.work_done = False
        self.cycle_counter = 0
        self.upgrade_station_counter = 0
        self.successful_red_icon_positions = deque(maxlen=self._successful_red_icon_history_limit)
        self.upgrade_found_in_cycle = False
        self.consecutive_failed_cycles = 0
        self.total_levels_completed = 0
        self.current_level_start_time = None
        self.upgrade_station_pos = None
        self.overlay = None
        self._oscillation_cycle_index = 1
        self._oscillation_leg_direction = 1
        self._oscillation_leg_progress = 0
        self.forbidden_zones = [
            (
                config.FORBIDDEN_ZONE_1_X_MIN,
                config.FORBIDDEN_ZONE_1_X_MAX,
                config.FORBIDDEN_ZONE_1_Y_MIN,
                config.FORBIDDEN_ZONE_1_Y_MAX,
            ),
            (
                config.FORBIDDEN_ZONE_2_X_MIN,
                config.FORBIDDEN_ZONE_2_X_MAX,
                config.FORBIDDEN_ZONE_2_Y_MIN,
                config.FORBIDDEN_ZONE_2_Y_MAX,
            ),
            (
                config.FORBIDDEN_ZONE_3_X_MIN,
                config.FORBIDDEN_ZONE_3_X_MAX,
                config.FORBIDDEN_ZONE_3_Y_MIN,
                config.FORBIDDEN_ZONE_3_Y_MAX,
            ),
            (
                config.FORBIDDEN_ZONE_4_X_MIN,
                config.FORBIDDEN_ZONE_4_X_MAX,
                config.FORBIDDEN_ZONE_4_Y_MIN,
                config.FORBIDDEN_ZONE_4_Y_MAX,
            ),
            (
                config.FORBIDDEN_ZONE_5_X_MIN,
                config.FORBIDDEN_ZONE_5_X_MAX,
                config.FORBIDDEN_ZONE_5_Y_MIN,
                config.FORBIDDEN_ZONE_5_Y_MAX,
            ),
        ]

        logger.info("Bot initialized successfully")

    def load_templates(self):
        templates = {}
        templates_path = Path(config.ASSETS_DIR)
        if not templates_path.exists():
            logger.error("Assets directory not found: %s", templates_path)
            return templates

        for template_file in templates_path.glob("*.png"):
            try:
                template_name = template_file.stem
                template_img = self.image_matcher.load_template(template_file)
                templates[template_name] = template_img
                logger.info("Loaded template: %s", template_name)
            except Exception as exc:
                logger.error("Failed to load template %s: %s", template_file, exc)

        return templates

    def register_states(self):
        self.state_machine.register_handler(State.FIND_RED_ICONS, self.handle_find_red_icons)
        self.state_machine.register_handler(State.CLICK_RED_ICON, self.handle_click_red_icon)
        self.state_machine.register_handler(State.CHECK_UNLOCK, self.handle_check_unlock)
        self.state_machine.register_handler(State.SEARCH_UPGRADE_STATION, self.handle_search_upgrade_station)
        self.state_machine.register_handler(State.HOLD_UPGRADE_STATION, self.handle_hold_upgrade_station)
        self.state_machine.register_handler(State.OPEN_BOXES, self.handle_open_boxes)
        self.state_machine.register_handler(State.UPGRADE_STATS, self.handle_upgrade_stats)
        self.state_machine.register_handler(State.SCROLL, self.handle_scroll)
        self.state_machine.register_handler(State.CHECK_NEW_LEVEL, self.handle_check_new_level)
        self.state_machine.register_handler(State.TRANSITION_LEVEL, self.handle_transition_level)
        self.state_machine.register_handler(State.WAIT_FOR_UNLOCK, self.handle_wait_for_unlock)

    def _sleep(self, duration):
        if duration > 0:
            time.sleep(duration)

    def _apply_tuning(self):
        self.mouse_controller.click_delay = float(self.tuner.click_delay)
        self.mouse_controller.move_delay = float(self.tuner.move_delay)

    def get_runtime_behavior_snapshot(self):
        return {
            "click_delay": float(self.tuner.click_delay),
            "move_delay": float(self.tuner.move_delay),
            "search_interval": float(self.tuner.search_interval),
        }

    def apply_learned_behavior(self, learned):
        if not learned:
            return
        self.tuner.click_delay = float(learned.get("click_delay", self.tuner.click_delay))
        self.tuner.move_delay = float(learned.get("move_delay", self.tuner.move_delay))
        self.tuner.search_interval = float(learned.get("search_interval", self.tuner.search_interval))
        self._apply_tuning()

    def wipe_memory(self):
        self.tuner.reset()
        self.vision_optimizer.reset()
        self.historical_learner.reset()
        self.successful_red_icon_positions = deque(maxlen=self._successful_red_icon_history_limit)
        self.current_level_start_time = datetime.now() if self.running else None
        self._apply_tuning()

    def _red_icon_template_names(self):
        cached = getattr(self, "_red_icon_template_names_cache", None)
        if cached is not None:
            return cached
        template_names = [name for name in self.templates if name.startswith("RedIcon")]
        if not template_names:
            return ["RedIcon"]

        def sort_key(name):
            if name == "RedIcon":
                return (0, 0)
            if name == "RedIconNoBG":
                return (2, 0)
            suffix = name.replace("RedIcon", "", 1)
            if suffix.isdigit():
                return (1, int(suffix))
            return (3, suffix)

        return sorted(template_names, key=sort_key)

    def _red_icon_template_span(self):
        max_width = 0
        max_height = 0
        for template_name in self._red_icon_template_names():
            if template_name not in self.templates:
                continue
            template, _ = self.templates[template_name]
            max_height = max(max_height, int(template.shape[0]))
            max_width = max(max_width, int(template.shape[1]))
        return max_width, max_height

    @staticmethod
    def _extract_region(screenshot, x_min, x_max, y_min, y_max, pad_x=0, pad_y=0):
        height, width = screenshot.shape[:2]
        left = max(0, int(x_min) - int(pad_x))
        right = min(width, int(x_max) + int(pad_x))
        top = max(0, int(y_min) - int(pad_y))
        bottom = min(height, int(y_max) + int(pad_y))
        if left >= right or top >= bottom:
            return screenshot[0:0, 0:0], 0, 0
        return screenshot[top:bottom, left:right], left, top

    @staticmethod
    def _merge_icon_detection(detections, x, y, template_name, confidence):
        for existing_x, existing_y in list(detections.keys()):
            if abs(x - existing_x) < 10 and abs(y - existing_y) < 10:
                detections[(existing_x, existing_y)].append((template_name, confidence))
                return
        detections[(x, y)] = [(template_name, confidence)]

    def _collect_red_icon_detections(self, screenshot, threshold, min_distance=80, offset_x=0, offset_y=0):
        detections = {}
        if screenshot.size == 0:
            return detections
        for template_name in self._red_icon_template_names():
            if template_name not in self.templates:
                continue
            template, mask = self.templates[template_name]
            icons = self.image_matcher.find_all_templates(
                screenshot,
                template,
                mask=mask,
                threshold=threshold,
                min_distance=min_distance,
                template_name=template_name,
            )
            for confidence, x, y in icons:
                self._merge_icon_detection(
                    detections,
                    x + offset_x,
                    y + offset_y,
                    template_name,
                    confidence,
                )
        return detections

    @staticmethod
    def _icons_from_detections(detections, min_matches):
        icons = []
        confidences = []
        for (x, y), matches in detections.items():
            if len(matches) < min_matches:
                continue
            max_confidence = max(confidence for _, confidence in matches)
            icons.append((max_confidence, x, y))
            confidences.append(max_confidence)
        return icons, confidences

    def _find_best_zone_red_icon(self, screenshot, threshold, x_min, x_max, y_min, y_max, min_distance=80):
        region, offset_x, offset_y = self._extract_region(
            screenshot,
            x_min,
            x_max,
            y_min,
            y_max,
            pad_x=self._red_icon_max_width,
            pad_y=self._red_icon_max_height,
        )
        if region.size == 0:
            return None

        best_match = None
        for template_name in self._red_icon_template_names():
            if template_name not in self.templates:
                continue
            template, mask = self.templates[template_name]
            icons = self.image_matcher.find_all_templates(
                region,
                template,
                mask=mask,
                threshold=threshold,
                min_distance=min_distance,
                template_name=template_name,
            )
            for confidence, x, y in icons:
                global_x = x + offset_x
                global_y = y + offset_y
                if not (x_min <= global_x <= x_max and y_min <= global_y <= y_max):
                    continue
                if best_match is None or confidence > best_match[0]:
                    best_match = (confidence, global_x, global_y)
        return best_match

    def _remember_successful_red_icon_position(self, y_value):
        y_value = int(y_value)
        for existing_y in self.successful_red_icon_positions:
            if abs(existing_y - y_value) < 12:
                return
        self.successful_red_icon_positions.append(y_value)

    def _record_level_completion(self):
        self.total_levels_completed += 1
        elapsed = 0.0
        if self.current_level_start_time is not None:
            elapsed = (datetime.now() - self.current_level_start_time).total_seconds()
        self.current_level_start_time = datetime.now()
        self._reset_search_cycle()
        self.telegram.notify_new_level(self.total_levels_completed, elapsed)
        self.historical_learner.record_completion(elapsed, "transition")
        return elapsed

    def _reset_search_cycle(self):
        self.cycle_counter = 0
        self._oscillation_cycle_index = 1
        self._oscillation_leg_direction = 1
        self._oscillation_leg_progress = 0

    def _advance_oscillation_progress(self):
        target_steps = max(1, int(self._oscillation_cycle_index) * int(config.SCROLL_INCREMENT_STEP))
        self._oscillation_leg_progress += 1
        if self._oscillation_leg_progress < target_steps:
            return
        self._oscillation_leg_progress = 0
        if self._oscillation_leg_direction > 0:
            self._oscillation_leg_direction = -1
            return
        self._oscillation_leg_direction = 1
        self._oscillation_cycle_index += 1
        if self._oscillation_cycle_index > int(config.MAX_SCROLL_CYCLES):
            self._oscillation_cycle_index = 1

    def _perform_oscillating_scroll_step(self):
        distance = int(round(float(config.SCROLL_PIXEL_STEP) * float(config.SCROLL_DISTANCE_RATIO)))
        start_x, start_y = config.SCROLL_START_POS
        direction = 1 if self._oscillation_leg_direction > 0 else -1
        target_y = start_y - distance if direction > 0 else start_y + distance
        logger.info(
            "Oscillating scroll step: cycle=%s direction=%s progress=%s",
            self._oscillation_cycle_index,
            "down" if direction > 0 else "up",
            self._oscillation_leg_progress + 1,
        )
        moved = self.mouse_controller.drag(
            start_x,
            start_y,
            start_x,
            target_y,
            duration=config.SCROLL_DURATION,
            relative=True,
        )
        if moved:
            self._sleep(config.POST_SCROLL_SETTLE)
            self._sleep(config.SCROLL_INTERVAL_PAUSE)
            self._advance_oscillation_progress()
            self.mouse_controller.click(config.IDLE_CLICK_POS[0], config.IDLE_CLICK_POS[1], relative=True)
        return bool(moved)

    def start(self):
        if self.running:
            return True
        try:
            self.window_capture.ensure_window(resize=True)
        except WindowNotAvailableError as exc:
            logger.error("Cannot start bot: %s", exc)
            self.running = False
            return False
        self.running = True
        if self.current_level_start_time is None:
            self.current_level_start_time = datetime.now()
        self.historical_learner.start()
        if config.ShowForbiddenArea and self.overlay is None:
            self.overlay = ForbiddenAreaOverlay(self.window_capture.hwnd, self.forbidden_zones)
            self.overlay.start()
        return True

    def stop(self):
        if not self.running and self.overlay is None:
            return
        self.running = False
        self.historical_learner.stop()
        if self.overlay is not None:
            self.overlay.stop()
            self.overlay = None

    def step(self):
        try:
            if not self.window_capture.is_window_active():
                logger.error("Window '%s' is not available", config.WINDOW_TITLE)
                self.stop()
                return False
            self._apply_tuning()
            return bool(self.state_machine.update())
        except (WindowNotAvailableError, WindowCaptureError) as exc:
            logger.error("Stopping bot: %s", exc)
            self.stop()
            return False
        except pywintypes.error as exc:
            logger.error("Stopping bot due to Windows input failure: %s", exc)
            self.stop()
            return False

    def run(self):
        self.start()
        try:
            while self.running:
                if not self.window_capture.is_window_active():
                    logger.error("Window '%s' is no longer active", config.WINDOW_TITLE)
                    break
                self.step()
                time.sleep(0.1)
        finally:
            self.stop()

    def handle_find_red_icons(self, current_state):
        self.mouse_controller.click(config.IDLE_CLICK_POS[0], config.IDLE_CLICK_POS[1], relative=True)

        self.work_done = False

        screenshot = self.window_capture.capture(max_y=config.EXTENDED_SEARCH_Y)
        limited_screenshot = screenshot[: config.MAX_SEARCH_Y, :]

        new_level_threshold = (
            self.vision_optimizer.new_level_threshold
            if self.vision_optimizer.enabled
            else config.NEW_LEVEL_THRESHOLD
        )
        if "newLevel" in self.templates:
            template, mask = self.templates["newLevel"]
            found, confidence, x, y = self.image_matcher.find_template(
                limited_screenshot,
                template,
                mask=mask,
                threshold=new_level_threshold,
                template_name="newLevel",
            )
            if found:
                self.cycle_counter = 0
                self.vision_optimizer.update_new_level_confidence(confidence)
                logger.info("newLevel.png found at (%s, %s)", x, y)
                return State.TRANSITION_LEVEL
            self.vision_optimizer.update_new_level_miss()

        scan_threshold = config.RED_ICON_THRESHOLD
        if self.vision_optimizer.enabled:
            scan_threshold = min(
                self.vision_optimizer.red_icon_threshold,
                self.vision_optimizer.new_level_red_icon_threshold,
            )

        min_matches = config.RED_ICON_MIN_MATCHES
        all_detections = self._collect_red_icon_detections(
            limited_screenshot,
            scan_threshold,
            min_distance=80,
        )
        self.red_icons, valid_red_icon_confidences = self._icons_from_detections(
            all_detections,
            min_matches,
        )

        self.vision_optimizer.update_red_icon_scan(valid_red_icon_confidences)

        footer_region, offset_x, offset_y = self._extract_region(
            screenshot,
            config.NEW_LEVEL_RED_ICON_X_MIN,
            config.NEW_LEVEL_RED_ICON_X_MAX,
            config.NEW_LEVEL_RED_ICON_Y_MIN,
            config.NEW_LEVEL_RED_ICON_Y_MAX,
            pad_x=self._red_icon_max_width,
            pad_y=self._red_icon_max_height,
        )
        footer_detections = self._collect_red_icon_detections(
            footer_region,
            scan_threshold,
            min_distance=80,
            offset_x=offset_x,
            offset_y=offset_y,
        )
        all_red_icons_extended, _ = self._icons_from_detections(footer_detections, min_matches)

        new_level_icon_threshold = (
            self.vision_optimizer.new_level_red_icon_threshold
            if self.vision_optimizer.enabled
            else config.NEW_LEVEL_RED_ICON_THRESHOLD
        )
        best_new_level_icon = None
        for confidence, x, y in all_red_icons_extended:
            if (
                config.NEW_LEVEL_RED_ICON_X_MIN <= x <= config.NEW_LEVEL_RED_ICON_X_MAX
                and config.NEW_LEVEL_RED_ICON_Y_MIN <= y <= config.NEW_LEVEL_RED_ICON_Y_MAX
                and confidence >= new_level_icon_threshold
            ):
                if best_new_level_icon is None or confidence > best_new_level_icon[0]:
                    best_new_level_icon = (confidence, x, y)

        if best_new_level_icon is not None:
            self.vision_optimizer.update_new_level_red_icon_confidence(best_new_level_icon[0])
            logger.info(
                "New level red icon detected at (%s, %s) [%.3f]",
                best_new_level_icon[1],
                best_new_level_icon[2],
                best_new_level_icon[0],
            )
            return State.CHECK_NEW_LEVEL
        self.vision_optimizer.update_new_level_red_icon_miss()

        if self.red_icons:
            filtered_icons = []
            for confidence, x, y in self.red_icons:
                click_x = x + config.RED_ICON_OFFSET_X
                click_y = y + config.RED_ICON_OFFSET_Y
                if not self.mouse_controller.is_in_forbidden_zone(click_x, click_y, relative=True):
                    filtered_icons.append((confidence, x, y))

            if not filtered_icons:
                logger.info("No valid red icons after forbidden-zone filtering")
                return State.OPEN_BOXES

            def get_priority(icon):
                confidence, x, y = icon
                for success_y in self.successful_red_icon_positions:
                    if abs(y - success_y) < 50:
                        return (0, y, -confidence)
                return (1, y, -confidence)

            filtered_icons.sort(key=get_priority)
            self.red_icons = filtered_icons
            self.current_red_icon_index = 0
            self.cycle_counter = 0
            self.work_done = True
            logger.info("%s red icons ready to process", len(self.red_icons))
            return State.CLICK_RED_ICON

        return State.OPEN_BOXES

    def handle_click_red_icon(self, current_state):
        if self.current_red_icon_index >= len(self.red_icons):
            logger.info("All red icons processed, continuing cycle")
            return State.OPEN_BOXES

        confidence, x, y = self.red_icons[self.current_red_icon_index]
        click_x = x + config.RED_ICON_OFFSET_X
        click_y = y + config.RED_ICON_OFFSET_Y

        clicked = self.mouse_controller.click(click_x, click_y, relative=True)
        self.tuner.record_click_result(clicked)
        self._apply_tuning()
        if not clicked:
            logger.warning("Red icon click failed at (%s, %s)", click_x, click_y)
            self.current_red_icon_index += 1
            if self.current_red_icon_index < len(self.red_icons):
                return State.CLICK_RED_ICON
            return State.OPEN_BOXES

        logger.info(
            "Clicked red icon %s/%s at (%s, %s) [%.3f]",
            self.current_red_icon_index + 1,
            len(self.red_icons),
            click_x,
            click_y,
            confidence,
        )
        return State.CHECK_UNLOCK

    def handle_check_unlock(self, current_state):
        limited_screenshot = self.window_capture.capture(max_y=config.MAX_SEARCH_Y)

        if "unlock" in self.templates:
            template, mask = self.templates["unlock"]
            found, confidence, x, y = self.image_matcher.find_template(
                limited_screenshot,
                template,
                mask=mask,
                threshold=config.UNLOCK_THRESHOLD,
                template_name="unlock",
            )
            if found and not self.mouse_controller.is_in_forbidden_zone(x, y, relative=True):
                logger.info("Unlock found at (%s, %s) [%.3f]", x, y, confidence)
                self.mouse_controller.click(x, y, relative=True)

        return State.SEARCH_UPGRADE_STATION

    def handle_search_upgrade_station(self, current_state):
        base_threshold = (
            self.vision_optimizer.upgrade_station_threshold
            if self.vision_optimizer.enabled
            else config.UPGRADE_STATION_THRESHOLD
        )
        relaxed_threshold = max(0.0, base_threshold - 0.05)
        max_attempts = 5

        for attempt in range(max_attempts):
            limited_screenshot = self.window_capture.capture(max_y=config.MAX_SEARCH_Y)

            if "upgradeStation" not in self.templates:
                break

            template, mask = self.templates["upgradeStation"]
            current_threshold = base_threshold if attempt < 2 else relaxed_threshold
            found, confidence, x, y = self.image_matcher.find_template(
                limited_screenshot,
                template,
                mask=mask,
                threshold=current_threshold,
                template_name="upgradeStation",
                check_color=config.UPGRADE_STATION_COLOR_CHECK,
            )
            if found and not self.mouse_controller.is_in_forbidden_zone(x, y, relative=True):
                logger.info("Upgrade station found at (%s, %s) on attempt %s", x, y, attempt + 1)
                self.upgrade_station_pos = (x, y)
                self.upgrade_found_in_cycle = True
                self.consecutive_failed_cycles = 0
                self.cycle_counter = 0
                self.vision_optimizer.update_upgrade_station_confidence(confidence)
                self.tuner.record_search_result(True)
                self._apply_tuning()
                if self.current_red_icon_index < len(self.red_icons):
                    _, _, red_y = self.red_icons[self.current_red_icon_index]
                    self._remember_successful_red_icon_position(red_y)
                return State.HOLD_UPGRADE_STATION

            if attempt < max_attempts - 1:
                self._sleep(self.tuner.search_interval)

        self.vision_optimizer.update_upgrade_station_miss()
        self.tuner.record_search_result(False)
        self._apply_tuning()
        self.consecutive_failed_cycles += 1
        logger.info("Upgrade station not found, returning to OPEN_BOXES")
        return State.OPEN_BOXES

    def handle_hold_upgrade_station(self, current_state):
        if not self.upgrade_station_pos:
            return State.OPEN_BOXES

        x, y = self.upgrade_station_pos
        if self.mouse_controller.is_in_forbidden_zone(x, y, relative=True):
            logger.warning("Upgrade station blocked by forbidden zone at (%s, %s)", x, y)
            return State.OPEN_BOXES

        logger.info("Spam-clicking upgrade station at (%s, %s)", x, y)
        completed = self.mouse_controller.spam_click_at(
            x,
            y,
            duration=config.SPAM_CLICK_DURATION,
            click_delay=config.SPAM_CLICK_DELAY,
            jitter=config.SPAM_CLICK_JITTER,
            relative=True,
        )
        if not completed:
            logger.warning("Spam-click sequence ended early")
            return State.OPEN_BOXES

        self.mouse_controller.click(config.IDLE_CLICK_POS[0], config.IDLE_CLICK_POS[1], relative=True)
        self._sleep(config.STATE_DELAY)
        self.upgrade_station_counter += 1
        if self.upgrade_station_counter >= 2:
            self.upgrade_station_counter = 0
            logger.info("Upgrade counter reached stats threshold")
            return State.UPGRADE_STATS

        return State.OPEN_BOXES

    def handle_upgrade_stats(self, current_state):
        self.mouse_controller.click(config.IDLE_CLICK_POS[0], config.IDLE_CLICK_POS[1], relative=True)

        screenshot = self.window_capture.capture(max_y=config.EXTENDED_SEARCH_Y)
        limited_screenshot = screenshot[: config.MAX_SEARCH_Y, :]

        if "newLevel" in self.templates:
            template, mask = self.templates["newLevel"]
            found, confidence, x, y = self.image_matcher.find_template(
                limited_screenshot,
                template,
                mask=mask,
                threshold=(
                    self.vision_optimizer.new_level_threshold
                    if self.vision_optimizer.enabled
                    else config.NEW_LEVEL_THRESHOLD
                ),
                template_name="newLevel",
            )
            if found:
                self.vision_optimizer.update_new_level_confidence(confidence)
                return State.TRANSITION_LEVEL

        stats_threshold = (
            self.vision_optimizer.stats_upgrade_threshold
            if self.vision_optimizer.enabled
            else config.STATS_RED_ICON_THRESHOLD
        )
        best_stats_match = self._find_best_zone_red_icon(
            screenshot,
            stats_threshold,
            config.UPGRADE_RED_ICON_X_MIN,
            config.UPGRADE_RED_ICON_X_MAX,
            config.UPGRADE_RED_ICON_Y_MIN,
            config.UPGRADE_RED_ICON_Y_MAX,
            min_distance=80,
        )

        if best_stats_match is None:
            self.vision_optimizer.update_stats_upgrade_miss()
            logger.info("No stats icon detected")
            return State.SCROLL

        best_stats_confidence, _, _ = best_stats_match
        self.vision_optimizer.update_stats_upgrade_confidence(best_stats_confidence)
        self.cycle_counter = 0
        logger.info("Stats icon found, upgrading")
        opened = self.mouse_controller.click(
            config.STATS_UPGRADE_BUTTON_POS[0],
            config.STATS_UPGRADE_BUTTON_POS[1],
            relative=True,
        )
        if not opened:
            return State.OPEN_BOXES

        self._sleep(config.STATE_DELAY)
        for _ in range(config.STATS_UPGRADE_CLICK_COUNT):
            self.mouse_controller.click(
                config.STATS_UPGRADE_POS[0],
                config.STATS_UPGRADE_POS[1],
                relative=True,
                delay=0.0,
            )
            self._sleep(config.STATS_UPGRADE_CLICK_DELAY)

        self.mouse_controller.click(config.IDLE_CLICK_POS[0], config.IDLE_CLICK_POS[1], relative=True)
        logger.info("Stats upgrade completed")
        return State.OPEN_BOXES

    def handle_open_boxes(self, current_state):
        self.mouse_controller.click(config.IDLE_CLICK_POS[0], config.IDLE_CLICK_POS[1], relative=True)

        limited_screenshot = self.window_capture.capture(max_y=config.MAX_SEARCH_Y)

        if "newLevel" in self.templates:
            template, mask = self.templates["newLevel"]
            found, confidence, x, y = self.image_matcher.find_template(
                limited_screenshot,
                template,
                mask=mask,
                threshold=(
                    self.vision_optimizer.new_level_threshold
                    if self.vision_optimizer.enabled
                    else config.NEW_LEVEL_THRESHOLD
                ),
                template_name="newLevel",
            )
            if found:
                self.vision_optimizer.update_new_level_confidence(confidence)
                logger.info("New level found while opening boxes")
                return State.TRANSITION_LEVEL

        box_names = ["box1", "box2", "box3", "box4", "box5"]
        box_threshold = self.vision_optimizer.box_threshold if self.vision_optimizer.enabled else config.BOX_THRESHOLD
        boxes_found = 0
        best_box_confidence = 0.0

        for box_name in box_names:
            if box_name not in self.templates:
                continue

            template, mask = self.templates[box_name]
            found, confidence, x, y = self.image_matcher.find_template(
                limited_screenshot,
                template,
                mask=mask,
                threshold=box_threshold,
                template_name=box_name,
                check_color=config.BOX_COLOR_CHECK,
                color_threshold=config.BOX_COLOR_THRESHOLD,
            )
            if found:
                if self.mouse_controller.is_in_forbidden_zone(x, y, relative=True):
                    logger.debug("%s is in a forbidden zone", box_name)
                    continue
                clicked = self.mouse_controller.click(x, y, relative=True)
                if clicked:
                    boxes_found += 1
                    best_box_confidence = max(best_box_confidence, confidence)

        if boxes_found > 0:
            self.work_done = True
            self.cycle_counter = 0
            self.vision_optimizer.update_box_confidence(best_box_confidence)
            logger.info("Opened %s boxes", boxes_found)
        else:
            self.vision_optimizer.update_box_miss()

        if self.consecutive_failed_cycles >= 3:
            self.consecutive_failed_cycles = 0
            self.cycle_counter = 0
            logger.info("Repeated search failures reached threshold, forcing scroll")
            return State.SCROLL

        if self.upgrade_found_in_cycle:
            self.upgrade_found_in_cycle = False
            self.cycle_counter = 0
            logger.info("Upgrade found in cycle, staying in current area")
            return State.FIND_RED_ICONS

        if self.work_done:
            self.cycle_counter = 0
            logger.info("Work completed in current area, rescanning before scrolling")
            return State.FIND_RED_ICONS

        self.cycle_counter += 1
        logger.info("No work detected in current area (idle pass %s/2)", self.cycle_counter)
        if self.cycle_counter >= 2:
            self.cycle_counter = 0
            return State.SCROLL

        return State.FIND_RED_ICONS

    def handle_scroll(self, current_state):
        self.mouse_controller.click(config.IDLE_CLICK_POS[0], config.IDLE_CLICK_POS[1], relative=True)
        self._perform_oscillating_scroll_step()
        self.cycle_counter = 0
        return State.FIND_RED_ICONS

    def handle_check_new_level(self, current_state):
        if not self.mouse_controller.click(config.IDLE_CLICK_POS[0], config.IDLE_CLICK_POS[1], relative=True):
            logger.warning("Failed to clear focus before confirming the new level")
            return State.CHECK_NEW_LEVEL
        self._sleep(0.05)
        opened = self.mouse_controller.click(
            config.NEW_LEVEL_BUTTON_POS[0],
            config.NEW_LEVEL_BUTTON_POS[1],
            relative=True,
        )
        if not opened:
            logger.warning("Failed to click the new level button at %s", config.NEW_LEVEL_BUTTON_POS)
            return State.CHECK_NEW_LEVEL
        self._sleep(0.30)
        advanced = self.mouse_controller.click(
            config.LEVEL_TRANSITION_POS[0],
            config.LEVEL_TRANSITION_POS[1],
            relative=True,
        )
        if not advanced:
            logger.warning("Failed to click the level transition button at %s", config.LEVEL_TRANSITION_POS)
            return State.CHECK_NEW_LEVEL
        self._sleep(0.20)
        self._reset_search_cycle()
        return State.FIND_RED_ICONS

    def handle_transition_level(self, current_state):
        self.mouse_controller.click(config.IDLE_CLICK_POS[0], config.IDLE_CLICK_POS[1], relative=True)

        max_attempts = 5
        threshold = (
            self.vision_optimizer.new_level_threshold
            if self.vision_optimizer.enabled
            else config.NEW_LEVEL_THRESHOLD
        )
        for attempt in range(max_attempts):
            limited_screenshot = self.window_capture.capture(max_y=config.MAX_SEARCH_Y)

            if "newLevel" in self.templates:
                template, mask = self.templates["newLevel"]
                found, confidence, x, y = self.image_matcher.find_template(
                    limited_screenshot,
                    template,
                    mask=mask,
                    threshold=threshold,
                    template_name="newLevel",
                )
                if found:
                    self.vision_optimizer.update_new_level_confidence(confidence)
                    logger.info("New level button found at (%s, %s) on attempt %s", x, y, attempt + 1)
                    clicked = self.mouse_controller.click(x, y, relative=True)
                    if not clicked:
                        logger.warning("New level button click failed at (%s, %s)", x, y)
                        return State.CHECK_NEW_LEVEL
                    self._sleep(1.0)
                    elapsed = self._record_level_completion()
                    logger.info(
                        "Level %s completed. Time spent: %.1fs",
                        self.total_levels_completed,
                        elapsed,
                    )
                    return State.WAIT_FOR_UNLOCK

            if attempt < max_attempts - 1:
                self._sleep(0.20)

        self.vision_optimizer.update_new_level_miss()
        logger.warning("New level button not found after %s attempts", max_attempts)
        self._reset_search_cycle()
        return State.FIND_RED_ICONS

    def handle_wait_for_unlock(self, current_state):
        if not self.mouse_controller.click(config.IDLE_CLICK_POS[0], config.IDLE_CLICK_POS[1], relative=True):
            logger.warning("Failed to clear focus while waiting for the next unlock")
            return State.WAIT_FOR_UNLOCK
        self._sleep(0.05)

        self.wait_for_unlock_attempts += 1
        if self.wait_for_unlock_attempts > self.max_wait_for_unlock_attempts:
            logger.warning(
                "Unlock button not found after %s attempts, resetting",
                self.max_wait_for_unlock_attempts,
            )
            self.wait_for_unlock_attempts = 0
            self._reset_search_cycle()
            return State.FIND_RED_ICONS

        screenshot = self.window_capture.capture()
        if "unlock" in self.templates:
            template, mask = self.templates["unlock"]
            found, confidence, x, y = self.image_matcher.find_template(
                screenshot,
                template,
                mask=mask,
                threshold=config.UNLOCK_THRESHOLD,
                template_name="unlock",
            )
            if found:
                logger.info("Unlock button found at (%s, %s) [%.3f]", x, y, confidence)
                if not self.mouse_controller.click(x, y, relative=True):
                    logger.warning("Unlock button click failed at (%s, %s)", x, y)
                    return State.WAIT_FOR_UNLOCK
                self._sleep(0.50)
                self.wait_for_unlock_attempts = 0
                self._reset_search_cycle()
                return State.FIND_RED_ICONS

        self._sleep(0.30)
        return State.WAIT_FOR_UNLOCK
