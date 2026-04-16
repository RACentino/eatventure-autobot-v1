import json
import logging
import os
import tempfile
import threading
import time
from datetime import datetime

import config
from image_matcher import AssetScanner, ImageMatcher
from mouse_controller import MouseController
from state_machine import State, StateMachine
from telegram_notifier import TelegramNotifier
from window_capture import WindowCapture

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
                    handle.flush()
                    os.fsync(handle.fileno())

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

    def update_red_icon_confidences(self, confidences):
        if not self.enabled or not confidences:
            return
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

    def update_red_icon_scan(self, confidences):
        if not self.enabled:
            return
        if confidences:
            self._miss_counts["red_icon"] = 0
            self.update_red_icon_confidences(confidences)
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
        for key, (minimum, maximum) in clamps.items():
            if key not in state:
                continue
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
            self.window_capture.hwnd,
            config.CLICK_DELAY,
            config.MOUSE_MOVE_DELAY,
            hwnd_provider=lambda: self.window_capture.hwnd,
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
        self.templates = self.load_templates()
        self.red_icon_template_names = sorted(
            name for name in self.templates if name.lower().startswith("redicon")
        )
        self.overlay = None
        self.register_states()
        self.running = False
        self.red_icons = []
        self.current_red_icon_index = 0
        self.red_icon_cycle_count = 0
        self.wait_for_unlock_attempts = 0
        self.max_wait_for_unlock_attempts = 4
        self.upgrade_station_pos = None
        self.successful_red_icon_positions = []
        self.upgrade_found_in_cycle = False
        self.consecutive_failed_cycles = 0
        self.cycle_counter = 0
        self.upgrade_station_counter = 0
        self.red_icon_processed_count = 0
        self.total_levels_completed = 0
        self.current_level_start_time = None
        self.work_done = False
        self._pending_fallback_scroll = False
        self._oscillation_cycle_index = 1
        self._oscillation_leg_direction = 1
        self._oscillation_leg_progress = 0
        self._state_last_run_at = {}
        self.forbidden_zones = [
            (zone["x_min"], zone["x_max"], zone["y_min"], zone["y_max"])
            for zone in config.FORBIDDEN_ZONES
        ]
        logger.info("Bot initialized successfully")

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

    def load_templates(self):
        scanner = AssetScanner(self.image_matcher)
        return scanner.scan(config.ASSETS_DIR, required_templates=self._required_template_names())

    def _required_template_names(self):
        required = {"newLevel", "unlock", "upgradeStation"}
        required.update(f"box{i}" for i in range(1, 6))
        required.update({f"RedIcon{i}" for i in range(2, 16)})
        required.update({"RedIcon", "RedIconNoBG"})
        return required

    def _sync_window_bindings(self):
        self.window_capture.ensure_window_ready()
        self.mouse_controller.set_window_handle(self.window_capture.hwnd)
        if self.overlay is not None:
            self.overlay.update_target_hwnd(self.window_capture.hwnd)

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
        self.successful_red_icon_positions = []

    def _capture(self, max_y=None):
        self._sync_window_bindings()
        return self.window_capture.capture(max_y=max_y)

    def _click_idle(self):
        return self.mouse_controller.click(
            config.IDLE_CLICK_POS[0],
            config.IDLE_CLICK_POS[1],
            relative=True,
        )

    def _enforce_state_min_interval(self):
        state_name = self.state_machine.get_state_name()
        minimum = float(config.STATE_MIN_INTERVALS.get(state_name, config.STATE_MIN_INTERVAL_DEFAULT))
        if minimum <= 0:
            self._state_last_run_at[state_name] = time.monotonic()
            return
        now = time.monotonic()
        last = self._state_last_run_at.get(state_name, 0.0)
        wait_time = (last + minimum) - now
        if wait_time > 0:
            self._sleep(wait_time)
        self._state_last_run_at[state_name] = time.monotonic()

    def _find_template(self, name, screenshot, threshold, max_y=None):
        if name not in self.templates:
            return False, 0.0, 0, 0
        if max_y is not None:
            screenshot = screenshot[:max_y, :]
        template, mask = self.templates[name]
        return self.image_matcher.find_template(
            screenshot,
            template,
            mask=mask,
            threshold=threshold,
            template_name=name,
        )

    def _detect_new_level_button(self, screenshot):
        found, confidence, x, y = self._find_template(
            "newLevel",
            screenshot,
            self.vision_optimizer.new_level_threshold if self.vision_optimizer.enabled else config.NEW_LEVEL_THRESHOLD,
            max_y=config.MAX_SEARCH_Y,
        )
        if found:
            self.vision_optimizer.update_new_level_confidence(confidence)
            return found, confidence, x, y
        self.vision_optimizer.update_new_level_miss()
        return False, 0.0, 0, 0

    def _detect_new_level_red_icon(self, screenshot):
        icons = self._detect_red_icons(screenshot, max_y=config.EXTENDED_SEARCH_Y)
        best = None
        for confidence, x, y in icons:
            if (
                config.NEW_LEVEL_RED_ICON_X_MIN <= x <= config.NEW_LEVEL_RED_ICON_X_MAX
                and config.NEW_LEVEL_RED_ICON_Y_MIN <= y <= config.NEW_LEVEL_RED_ICON_Y_MAX
            ):
                if best is None or confidence > best[1]:
                    best = ("new level red icon", confidence, x, y)
        if best is not None:
            self.vision_optimizer.update_new_level_red_icon_confidence(best[1])
            return best
        self.vision_optimizer.update_new_level_red_icon_miss()
        return None

    def _cluster_detections(self, detections, distance=10):
        buckets = {}
        for confidence, x, y, template_name in detections:
            key = None
            for existing in list(buckets.keys()):
                if abs(existing[0] - x) < distance and abs(existing[1] - y) < distance:
                    key = existing
                    break
            if key is None:
                key = (x, y)
                buckets[key] = []
            buckets[key].append((template_name, confidence))
        return buckets

    def _detect_red_icons(self, screenshot, max_y=None):
        if max_y is not None:
            screenshot = screenshot[:max_y, :]
        detections = []
        confidences = []
        threshold = self.vision_optimizer.red_icon_threshold if self.vision_optimizer.enabled else config.RED_ICON_THRESHOLD
        for template_name in self.red_icon_template_names:
            template, mask = self.templates[template_name]
            matches = self.image_matcher.find_all_templates(
                screenshot,
                template,
                mask=mask,
                threshold=threshold,
                min_distance=80,
                template_name=template_name,
            )
            for confidence, x, y in matches:
                red_pixels = self.image_matcher.count_red_pixels(screenshot, x, y)
                if red_pixels < config.RED_ICON_PIXEL_THRESHOLD:
                    continue
                detections.append((confidence, x, y, template_name))
                confidences.append(confidence)

        if confidences:
            self.vision_optimizer.update_red_icon_scan(confidences)
        else:
            self.vision_optimizer.update_red_icon_scan([])

        clustered = self._cluster_detections(detections)
        results = []
        minimum_matches = max(1, int(config.RED_ICON_MIN_MATCHES))
        for (x, y), matches in clustered.items():
            if len(matches) < minimum_matches:
                continue
            results.append((max(confidence for _, confidence in matches), x, y))
        results.sort(key=lambda item: item[0], reverse=True)
        return results

    def _filter_safe_red_icons(self, icons):
        safe = []
        for confidence, x, y in icons:
            click_x = x + config.RED_ICON_OFFSET_X
            click_y = y + config.RED_ICON_OFFSET_Y
            if not self.mouse_controller.is_in_forbidden_zone(click_x, click_y, relative=True):
                safe.append((confidence, x, y))
        return safe

    def _prioritize_red_icons(self, icons):
        def sort_key(icon):
            confidence, _, y = icon
            preferred = 1
            for success_y in self.successful_red_icon_positions:
                if abs(y - success_y) < 50:
                    preferred = 0
                    break
            return (preferred, y, -confidence)

        return sorted(icons, key=sort_key)

    def _has_stats_upgrade_icon(self, screenshot):
        threshold = (
            self.vision_optimizer.stats_upgrade_threshold
            if self.vision_optimizer.enabled
            else config.STATS_RED_ICON_THRESHOLD
        )
        for template_name in self.red_icon_template_names:
            template, mask = self.templates[template_name]
            icons = self.image_matcher.find_all_templates(
                screenshot,
                template,
                mask=mask,
                threshold=threshold,
                min_distance=80,
                template_name=f"{template_name}-stats",
            )
            for confidence, x, y in icons:
                if (
                    config.UPGRADE_RED_ICON_X_MIN <= x <= config.UPGRADE_RED_ICON_X_MAX
                    and config.UPGRADE_RED_ICON_Y_MIN <= y <= config.UPGRADE_RED_ICON_Y_MAX
                ):
                    return True, confidence
        return False, 0.0

    def _find_boxes(self, screenshot):
        threshold = self.vision_optimizer.box_threshold if self.vision_optimizer.enabled else config.BOX_THRESHOLD
        found = []
        for name in [f"box{i}" for i in range(1, 6)]:
            if name not in self.templates:
                continue
            template, mask = self.templates[name]
            matched, confidence, x, y = self.image_matcher.find_template(
                screenshot,
                template,
                mask=mask,
                threshold=threshold,
                template_name=name,
            )
            if matched:
                found.append((name, confidence, x, y))
        return found

    def _find_upgrade_station(self, screenshot, threshold):
        if "upgradeStation" not in self.templates:
            return False, 0.0, 0, 0
        template, mask = self.templates["upgradeStation"]
        found, confidence, x, y = self.image_matcher.find_template(
            screenshot,
            template,
            mask=mask,
            threshold=threshold,
            template_name="upgradeStation",
        )
        if not found:
            return False, confidence, x, y
        if not self.image_matcher.check_upgrade_station_hsv(
            screenshot,
            x,
            y,
            template.shape[0],
            template.shape[1],
        ):
            return False, confidence, 0, 0
        return True, confidence, x, y

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
            "DOWN" if direction > 0 else "UP",
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
            self._click_idle()
        return bool(moved)

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
        self._oscillation_cycle_index = 1
        self._oscillation_leg_direction = 1
        self._oscillation_leg_progress = 0
        self._pending_fallback_scroll = False

    def start(self):
        if self.running:
            return
        self.running = True
        if self.current_level_start_time is None:
            self.current_level_start_time = datetime.now()
        self.historical_learner.start()
        if config.SHOW_FORBIDDEN_AREA and self.overlay is None:
            from window_capture import ForbiddenAreaOverlay

            self.overlay = ForbiddenAreaOverlay(self.window_capture.hwnd, self.forbidden_zones)
            self.overlay.start()

    def stop(self):
        if not self.running:
            return
        self.running = False
        self.historical_learner.stop()
        if self.overlay is not None:
            self.overlay.stop()
            self.overlay = None

    def step(self):
        self._sync_window_bindings()
        self._apply_tuning()
        self._enforce_state_min_interval()
        self.state_machine.update()

    def run(self):
        self.start()
        try:
            while self.running:
                if not self.window_capture.is_window_active():
                    logger.error("Window '%s' is no longer active", config.WINDOW_TITLE)
                    break
                self.step()
        finally:
            self.stop()

    def handle_find_red_icons(self, current_state):
        self._click_idle()
        self.cycle_counter += 1
        if self.cycle_counter >= 2:
            self.cycle_counter = 0
            logger.info("Find-red cycle threshold reached; forcing SCROLL")
            return State.SCROLL

        screenshot = self._capture(max_y=config.EXTENDED_SEARCH_Y)
        found_level, confidence, x, y = self._detect_new_level_button(screenshot)
        if found_level:
            logger.info("New level button found at (%s, %s)", x, y)
            return State.TRANSITION_LEVEL

        new_level_icon = self._detect_new_level_red_icon(screenshot)
        if new_level_icon is not None:
            _, icon_confidence, icon_x, icon_y = new_level_icon
            logger.info("New level red icon found at (%s, %s) [%.3f]", icon_x, icon_y, icon_confidence)
            return State.CHECK_NEW_LEVEL

        icons = self._detect_red_icons(screenshot, max_y=config.MAX_SEARCH_Y)
        safe_icons = self._filter_safe_red_icons(icons)
        if safe_icons:
            self.red_icons = self._prioritize_red_icons(safe_icons)
            self.current_red_icon_index = 0
            self.red_icon_cycle_count = 0
            self.work_done = True
            self._pending_fallback_scroll = False
            logger.info("Red icon scan found %s actionable targets", len(self.red_icons))
            return State.CLICK_RED_ICON

        self.red_icons = []
        self.current_red_icon_index = 0
        self.red_icon_cycle_count = 0
        self._pending_fallback_scroll = True
        logger.info("No actionable red icons detected; falling back to OPEN_BOXES")
        return State.OPEN_BOXES

    def handle_click_red_icon(self, current_state):
        if self.current_red_icon_index >= len(self.red_icons):
            logger.info("All red icons processed for this scan")
            return State.OPEN_BOXES

        confidence, x, y = self.red_icons[self.current_red_icon_index]
        click_x = x + config.RED_ICON_OFFSET_X
        click_y = y + config.RED_ICON_OFFSET_Y
        if self.mouse_controller.is_in_forbidden_zone(click_x, click_y, relative=True):
            logger.warning("Red icon click blocked at (%s, %s)", click_x, click_y)
            self.current_red_icon_index += 1
            return State.CLICK_RED_ICON if self.current_red_icon_index < len(self.red_icons) else State.OPEN_BOXES

        clicked = self.mouse_controller.click(click_x, click_y, relative=True)
        self.tuner.record_click_result(clicked)
        self._apply_tuning()
        if not clicked:
            self.current_red_icon_index += 1
            logger.warning("Red icon click failed at (%s, %s)", click_x, click_y)
            return State.CLICK_RED_ICON if self.current_red_icon_index < len(self.red_icons) else State.OPEN_BOXES

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
        screenshot = self._capture(max_y=config.MAX_SEARCH_Y)
        found, confidence, x, y = self._find_template(
            "unlock",
            screenshot,
            config.UNLOCK_THRESHOLD,
        )
        if found and not self.mouse_controller.is_in_forbidden_zone(x, y, relative=True):
            logger.info("Unlock found at (%s, %s) [%.3f]", x, y, confidence)
            self.mouse_controller.click(x, y, relative=True)
            self._sleep(config.STATE_DELAY)
        return State.SEARCH_UPGRADE_STATION

    def handle_search_upgrade_station(self, current_state):
        base_threshold = (
            self.vision_optimizer.upgrade_station_threshold
            if self.vision_optimizer.enabled
            else config.UPGRADE_STATION_THRESHOLD
        )
        relaxed_threshold = max(0.0, base_threshold - config.UPGRADE_STATION_RELAXED_THRESHOLD_DROP)
        for attempt in range(int(config.UPGRADE_STATION_SEARCH_MAX_ATTEMPTS)):
            screenshot = self._capture(max_y=config.MAX_SEARCH_Y)
            threshold = (
                base_threshold
                if attempt < int(config.UPGRADE_STATION_RELAXED_ATTEMPT_TRIGGER)
                else relaxed_threshold
            )
            found, confidence, x, y = self._find_upgrade_station(screenshot, threshold)
            if found and not self.mouse_controller.is_in_forbidden_zone(x, y, relative=True):
                self.upgrade_station_pos = (x, y)
                self.upgrade_found_in_cycle = True
                self.consecutive_failed_cycles = 0
                self.vision_optimizer.update_upgrade_station_confidence(confidence)
                self.tuner.record_search_result(True)
                if self.current_red_icon_index < len(self.red_icons):
                    red_y = self.red_icons[self.current_red_icon_index][2]
                    if red_y not in self.successful_red_icon_positions:
                        self.successful_red_icon_positions.append(red_y)
                logger.info("Upgrade station found at (%s, %s) on attempt %s", x, y, attempt + 1)
                return State.HOLD_UPGRADE_STATION
            if attempt < int(config.UPGRADE_STATION_SEARCH_MAX_ATTEMPTS) - 1:
                self._sleep(self.tuner.search_interval)

        self.vision_optimizer.update_upgrade_station_miss()
        self.tuner.record_search_result(False)
        self.consecutive_failed_cycles += 1
        self.red_icon_processed_count += 1
        logger.info("Upgrade station not found after search attempts; falling back to OPEN_BOXES")
        return State.OPEN_BOXES

    def handle_hold_upgrade_station(self, current_state):
        if self.upgrade_station_pos is None:
            return State.OPEN_BOXES
        x, y = self.upgrade_station_pos
        if self.mouse_controller.is_in_forbidden_zone(x, y, relative=True):
            logger.warning("Upgrade station is in a forbidden zone at (%s, %s)", x, y)
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
            logger.warning("Spam-click sequence ended early; continuing to OPEN_BOXES")
            return State.OPEN_BOXES

        self._click_idle()
        self._sleep(config.IDLE_CLICK_SETTLE_DELAY)
        self.red_icon_processed_count += 1
        self.upgrade_station_counter += 1
        if self.upgrade_station_counter >= 2:
            self.upgrade_station_counter = 0
            logger.info("Upgrade counter reached stats threshold")
            return State.UPGRADE_STATS
        return State.OPEN_BOXES

    def handle_upgrade_stats(self, current_state):
        self._click_idle()
        screenshot = self._capture(max_y=config.EXTENDED_SEARCH_Y)
        found_level, confidence, x, y = self._detect_new_level_button(screenshot)
        if found_level:
            logger.info("New level detected during stats upgrade at (%s, %s)", x, y)
            return State.TRANSITION_LEVEL

        has_stats_icon, stats_confidence = self._has_stats_upgrade_icon(screenshot)
        if not has_stats_icon:
            self.vision_optimizer.update_stats_upgrade_miss()
            logger.info("No stats icon present; returning to SCROLL")
            return State.SCROLL

        self.vision_optimizer.update_stats_upgrade_confidence(stats_confidence)
        opened = self.mouse_controller.click(
            config.STATS_UPGRADE_BUTTON_POS[0],
            config.STATS_UPGRADE_BUTTON_POS[1],
            relative=True,
        )
        if not opened:
            return State.OPEN_BOXES

        self._sleep(config.STATE_DELAY)
        self.mouse_controller.spam_click_at(
            config.STATS_UPGRADE_POS[0],
            config.STATS_UPGRADE_POS[1],
            duration=config.STATS_UPGRADE_CLICK_DURATION,
            click_delay=config.STATS_UPGRADE_CLICK_DELAY,
            jitter=0,
            relative=True,
        )
        self._click_idle()
        logger.info("Stats upgrade completed")
        return State.OPEN_BOXES

    def handle_open_boxes(self, current_state):
        self._click_idle()
        screenshot = self._capture(max_y=config.MAX_SEARCH_Y)
        found_level, confidence, x, y = self._detect_new_level_button(screenshot)
        if found_level:
            logger.info("New level detected during box handling at (%s, %s)", x, y)
            return State.TRANSITION_LEVEL

        boxes = self._find_boxes(screenshot)
        if boxes:
            best_confidence = 0.0
            opened = 0
            for name, confidence, x, y in boxes:
                if self.mouse_controller.is_in_forbidden_zone(x, y, relative=True):
                    continue
                if self.mouse_controller.click(x, y, relative=True):
                    opened += 1
                    best_confidence = max(best_confidence, confidence)
            if opened > 0:
                self.work_done = True
                self.vision_optimizer.update_box_confidence(best_confidence)
                logger.info("Opened %s boxes", opened)
            else:
                self.vision_optimizer.update_box_miss()
        else:
            self.vision_optimizer.update_box_miss()

        if self.upgrade_found_in_cycle:
            self.upgrade_found_in_cycle = False
            self.cycle_counter = 0
            logger.info("Upgrade found in current cycle; returning to FIND_RED_ICONS")
            return State.FIND_RED_ICONS

        if self._pending_fallback_scroll:
            self._pending_fallback_scroll = False
            self.cycle_counter = 0
            logger.info("Red-scan miss fallback complete; continuing to SCROLL")
            return State.SCROLL

        self.cycle_counter += 1
        if self.consecutive_failed_cycles >= 3:
            self.consecutive_failed_cycles = 0
            self.cycle_counter = 0
            logger.info("Repeated search misses reached threshold; forcing SCROLL")
            return State.SCROLL
        if self.cycle_counter >= 2:
            self.cycle_counter = 0
            logger.info("Open-box cycle threshold reached; forcing SCROLL")
            return State.SCROLL
        return State.FIND_RED_ICONS

    def handle_scroll(self, current_state):
        self._click_idle()
        screenshot = self._capture(max_y=config.MAX_SEARCH_Y)
        found_level, confidence, x, y = self._detect_new_level_button(screenshot)
        if found_level:
            logger.info("New level detected before scroll at (%s, %s)", x, y)
            return State.TRANSITION_LEVEL

        self._perform_oscillating_scroll_step()
        return State.FIND_RED_ICONS

    def handle_check_new_level(self, current_state):
        self._click_idle()
        logger.info("Handling new-level acknowledgement path")
        self.mouse_controller.click(config.NEW_LEVEL_BUTTON_POS[0], config.NEW_LEVEL_BUTTON_POS[1], relative=True)
        self._sleep(config.NEW_LEVEL_BUTTON_DELAY)
        self.mouse_controller.click(config.LEVEL_TRANSITION_POS[0], config.LEVEL_TRANSITION_POS[1], relative=True)
        self._sleep(config.STATE_DELAY)
        self._reset_search_cycle()
        return State.FIND_RED_ICONS

    def handle_transition_level(self, current_state):
        self._click_idle()
        for attempt in range(int(config.LEVEL_TRANSITION_MAX_ATTEMPTS)):
            screenshot = self._capture(max_y=config.MAX_SEARCH_Y)
            found, confidence, x, y = self._detect_new_level_button(screenshot)
            if found:
                logger.info("Transition button found at (%s, %s) on attempt %s", x, y, attempt + 1)
                self.mouse_controller.click(x, y, relative=True)
                self._sleep(config.TRANSITION_POST_CLICK_DELAY)
                elapsed = self._record_level_completion()
                logger.info(
                    "Level %s completed in %.2fs; waiting for unlock",
                    self.total_levels_completed,
                    elapsed,
                )
                return State.WAIT_FOR_UNLOCK
            if attempt < int(config.LEVEL_TRANSITION_MAX_ATTEMPTS) - 1:
                self._sleep(config.TRANSITION_RETRY_DELAY)

        logger.warning("Transition button not found after max attempts")
        self._reset_search_cycle()
        return State.FIND_RED_ICONS

    def handle_wait_for_unlock(self, current_state):
        self._click_idle()
        self.wait_for_unlock_attempts += 1
        if self.wait_for_unlock_attempts > self.max_wait_for_unlock_attempts:
            logger.warning("Unlock button not found after %s attempts", self.max_wait_for_unlock_attempts)
            self.wait_for_unlock_attempts = 0
            self._reset_search_cycle()
            return State.FIND_RED_ICONS

        screenshot = self._capture(max_y=config.EXTENDED_SEARCH_Y)
        found, confidence, x, y = self._find_template(
            "unlock",
            screenshot,
            config.UNLOCK_THRESHOLD,
        )
        if found:
            logger.info("Unlock button found at (%s, %s) [%.3f]", x, y, confidence)
            self.mouse_controller.click(x, y, relative=True)
            self._sleep(config.UNLOCK_REGISTER_WAIT)
            self.wait_for_unlock_attempts = 0
            self._reset_search_cycle()
            return State.FIND_RED_ICONS

        self._sleep(config.UNLOCK_POLL_INTERVAL)
        return State.WAIT_FOR_UNLOCK
