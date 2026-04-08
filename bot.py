import json
import logging
import os
import tempfile
import threading
import time
import ctypes
from contextlib import contextmanager
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, List, Optional, Tuple

import numpy as np

import config
from image_matcher import AssetScanner, ImageMatcher
from mouse_controller import MouseController
from telegram_notifier import TelegramNotifier
from window_capture import WindowCapture

logger = logging.getLogger(__name__)


class State(Enum):
    FIND_RED_ICONS = auto()
    CLICK_RED_ICON = auto()
    CHECK_UNLOCK = auto()
    SEARCH_UPGRADE_STATION = auto()
    HOLD_UPGRADE_STATION = auto()
    OPEN_BOXES = auto()
    UPGRADE_STATS = auto()
    SCROLL = auto()
    CHECK_NEW_LEVEL = auto()
    TRANSITION_LEVEL = auto()
    WAIT_FOR_UNLOCK = auto()


class StateMachine:
    def __init__(self, initial_state=State.FIND_RED_ICONS):
        self.current_state = initial_state
        self.previous_state = None
        self.state_handlers = {}
        self.priority_resolver = None
        logger.info(f"State machine initialized in state: {initial_state.name}")

    def register_handler(self, state, handler):
        self.state_handlers[state] = handler
        logger.debug(f"Registered handler for state: {state.name}")

    def set_priority_resolver(self, resolver):
        self.priority_resolver = resolver
        logger.debug("Priority resolver registered")

    def transition(self, new_state):
        if new_state != self.current_state:
            logger.info(f"State transition: {self.current_state.name} -> {new_state.name}")
            self.previous_state = self.current_state
            self.current_state = new_state

    def update(self):
        if self.priority_resolver is not None:
            try:
                priority_state = self.priority_resolver(self.current_state)
            except Exception:
                logger.exception("Priority resolver failed")
                priority_state = None

            if priority_state is not None and isinstance(priority_state, State):
                self.transition(priority_state)

        if self.current_state in self.state_handlers:
            handler = self.state_handlers[self.current_state]
            next_state = handler(self.current_state)

            if next_state is not None and isinstance(next_state, State):
                self.transition(next_state)

            return True

        logger.warning(f"No handler registered for state: {self.current_state.name}")
        return False

    def get_state(self):
        return self.current_state

    def get_state_name(self):
        return self.current_state.name


class WindowsTimerResolution:
    def __init__(self):
        self._enabled = False
        self._period_ms = max(1, int(config.WINDOWS_TIMER_RESOLUTION_MS))
        self._winmm = None
        if os.name == "nt":
            try:
                self._winmm = ctypes.WinDLL("winmm")
                self._winmm.timeBeginPeriod.argtypes = [ctypes.c_uint]
                self._winmm.timeBeginPeriod.restype = ctypes.c_uint
                self._winmm.timeEndPeriod.argtypes = [ctypes.c_uint]
                self._winmm.timeEndPeriod.restype = ctypes.c_uint
            except Exception:
                self._winmm = None

    def enable(self):
        if self._enabled:
            return
        if not config.ENABLE_WINDOWS_TIMER_RESOLUTION:
            return
        if self._winmm is None:
            return
        result = self._winmm.timeBeginPeriod(self._period_ms)
        if result == 0:
            self._enabled = True
            logger.info("Windows timer resolution enabled: %sms", self._period_ms)
        else:
            logger.warning("Failed to enable Windows timer resolution (code=%s)", result)

    def disable(self):
        if not self._enabled or self._winmm is None:
            return
        result = self._winmm.timeEndPeriod(self._period_ms)
        if result != 0:
            logger.warning("Failed to restore Windows timer resolution (code=%s)", result)
        self._enabled = False


class AdaptiveTuner:
    def __init__(self):
        self.enabled = config.ADAPTIVE_TUNER_ENABLED
        self.alpha = config.ADAPTIVE_TUNER_ALPHA
        self.click_success_rate = 1.0
        self.search_success_rate = 1.0
        self.click_delay = config.CLICK_DELAY
        self.move_delay = config.MOUSE_MOVE_DELAY
        self.upgrade_click_interval = config.UPGRADE_CLICK_INTERVAL
        self.search_interval = config.UPGRADE_SEARCH_INTERVAL

    def _ema(self, current, new_value):
        return (1 - self.alpha) * current + self.alpha * new_value

    def record_click_result(self, success):
        if not self.enabled:
            return
        self.click_success_rate = self._ema(self.click_success_rate, 1.0 if success else 0.0)
        self._adjust_click_timing()

    def record_search_result(self, success):
        if not self.enabled:
            return
        self.search_success_rate = self._ema(self.search_success_rate, 1.0 if success else 0.0)
        self._adjust_search_timing()

    def _adjust_click_timing(self):
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

    def _adjust_search_timing(self):
        if self.search_success_rate < config.ADAPTIVE_TUNER_SEARCH_LOW_THRESHOLD:
            self.search_interval = min(
                self.search_interval + config.ADAPTIVE_TUNER_SEARCH_INTERVAL_STEP,
                config.ADAPTIVE_TUNER_MAX_SEARCH_INTERVAL,
            )
            self.upgrade_click_interval = min(
                self.upgrade_click_interval + config.ADAPTIVE_TUNER_UPGRADE_INTERVAL_STEP,
                config.ADAPTIVE_TUNER_MAX_UPGRADE_INTERVAL,
            )
        elif self.search_success_rate > config.ADAPTIVE_TUNER_SEARCH_HIGH_THRESHOLD:
            self.search_interval = max(
                self.search_interval - config.ADAPTIVE_TUNER_SEARCH_DECREMENT,
                config.ADAPTIVE_TUNER_MIN_SEARCH_INTERVAL,
            )
            self.upgrade_click_interval = max(
                self.upgrade_click_interval - config.ADAPTIVE_TUNER_UPGRADE_DECREMENT,
                config.ADAPTIVE_TUNER_MIN_UPGRADE_INTERVAL,
            )

    def reset(self):
        self.click_success_rate = 1.0
        self.search_success_rate = 1.0
        self.click_delay = config.CLICK_DELAY
        self.move_delay = config.MOUSE_MOVE_DELAY
        self.upgrade_click_interval = config.UPGRADE_CLICK_INTERVAL
        self.search_interval = config.UPGRADE_SEARCH_INTERVAL
        logger.info("AdaptiveTuner reset to defaults")


class VisionPersistence:
    def __init__(self, path, save_interval):
        self.path = path
        self.save_interval = save_interval
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
            except (OSError, ValueError, TypeError) as exc:
                logger.warning(
                    "Failed to load vision state from %s: %s. Using defaults.",
                    self.path,
                    exc,
                )
                return {}
        return data if isinstance(data, dict) else {}

    def save(self, state, force=False):
        if not self.path:
            return False

        now = time.monotonic()
        with self._lock:
            if not force and self.save_interval > 0 and now - self._last_save_time < self.save_interval:
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
                self._last_save_time = time.monotonic()
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
        self.enabled = config.AI_VISION_ENABLED
        self.alpha = config.AI_VISION_ALPHA
        self.alpha_max = config.AI_VISION_ALPHA_MAX
        self.confidence_boost = config.AI_VISION_CONFIDENCE_BOOST
        self.red_icon_threshold = config.RED_ICON_THRESHOLD
        self.new_level_threshold = config.NEW_LEVEL_THRESHOLD
        self.new_level_red_icon_threshold = config.NEW_LEVEL_RED_ICON_THRESHOLD
        self.upgrade_station_threshold = config.UPGRADE_STATION_THRESHOLD
        self.stats_upgrade_threshold = config.STATS_RED_ICON_THRESHOLD
        self.box_threshold = config.BOX_THRESHOLD
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
        return (1 - blend) * current + blend * new_value

    def _adaptive_alpha(self, confidence):
        if confidence <= 0:
            return self.alpha
        boost = (
            max(0.0, min(1.0, (confidence - config.AI_VISION_CONFIDENCE_THRESHOLD)))
            * self.confidence_boost
        )
        return min(self.alpha + boost, self.alpha_max)

    def _update_threshold(self, name, confidence, min_th, max_th):
        if not self.enabled or confidence <= 0:
            return
        self._miss_counts[name] = 0
        current_th = getattr(self, f"{name}_threshold")
        target = max(min_th, min(confidence, max_th))
        new_th = self._ema(current_th, target, self._adaptive_alpha(confidence))
        setattr(self, f"{name}_threshold", new_th)
        self._persist()

    def _update_miss(self, name, min_th, step, window):
        if not self.enabled:
            return
        self._miss_counts[name] += 1
        if self._miss_counts[name] < window:
            return
        self._miss_counts[name] = 0
        current_th = getattr(self, f"{name}_threshold")
        target = max(min_th, current_th - step)
        setattr(self, f"{name}_threshold", self._ema(current_th, target, self.alpha_max))
        self._persist()

    def update_red_icon_confidences(self, confidences):
        if not self.enabled or not confidences:
            return
        avg_conf = sum(confidences) / len(confidences)
        target = max(
            config.AI_RED_ICON_THRESHOLD_MIN,
            min(avg_conf - config.AI_RED_ICON_MARGIN, config.AI_RED_ICON_THRESHOLD_MAX),
        )
        self.red_icon_threshold = self._ema(
            self.red_icon_threshold,
            target,
            self._adaptive_alpha(avg_conf),
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

    def reset(self):
        self.red_icon_threshold = config.RED_ICON_THRESHOLD
        self.new_level_threshold = config.NEW_LEVEL_THRESHOLD
        self.new_level_red_icon_threshold = config.NEW_LEVEL_RED_ICON_THRESHOLD
        self.upgrade_station_threshold = config.UPGRADE_STATION_THRESHOLD
        self.stats_upgrade_threshold = config.STATS_RED_ICON_THRESHOLD
        self.box_threshold = config.BOX_THRESHOLD
        for key in self._miss_counts:
            self._miss_counts[key] = 0
        self._persist(force=True)
        logger.info("VisionOptimizer reset to defaults")

    def apply_persisted_state(self, state):
        if not state:
            return
        clamps = {
            "red_icon_threshold": (
                config.AI_RED_ICON_THRESHOLD_MIN,
                config.AI_RED_ICON_THRESHOLD_MAX,
            ),
            "new_level_threshold": (
                config.AI_NEW_LEVEL_THRESHOLD_MIN,
                config.AI_NEW_LEVEL_THRESHOLD_MAX,
            ),
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
            "box_threshold": (
                config.AI_BOX_THRESHOLD_MIN,
                config.AI_BOX_THRESHOLD_MAX,
            ),
        }
        for key, (minimum, maximum) in clamps.items():
            if key not in state:
                continue
            if key == "red_icon_threshold":
                bootstrap_max = float(config.AI_RED_ICON_BOOTSTRAP_MAX)
                maximum = min(maximum, bootstrap_max)
            try:
                value = float(state[key])
            except (TypeError, ValueError):
                logger.warning("Ignoring persisted %s value %r because it is not numeric", key, state[key])
                continue
            clamped = max(minimum, min(maximum, value))
            if clamped != value:
                logger.info("Clamped persisted %s from %.4f to %.4f", key, value, clamped)
            setattr(self, key, clamped)

    def _persist(self, force=False):
        if not self.persistence:
            return
        state = {
            "red_icon_threshold": self.red_icon_threshold,
            "new_level_threshold": self.new_level_threshold,
            "new_level_red_icon_threshold": self.new_level_red_icon_threshold,
            "upgrade_station_threshold": self.upgrade_station_threshold,
            "stats_upgrade_threshold": self.stats_upgrade_threshold,
            "box_threshold": self.box_threshold,
        }
        self.persistence.save({key: float(value) for key, value in state.items()}, force=force)


class HistoricalLearner:
    def __init__(self, bot, persistence=None):
        self.bot = bot
        self.persistence = persistence
        self.enabled = config.AI_LEARNING_ENABLED
        self.interval = max(config.LEARNING_LOOP_MIN_SLEEP, float(config.AI_LEARNING_THREAD_INTERVAL))
        self.pair_window = max(2, int(config.AI_LEARNING_PAIR_WINDOW))
        self.batch_window = max(2, int(config.AI_LEARNING_BATCH_WINDOW))
        self.ema_alpha = max(0.01, min(0.8, float(config.AI_LEARNING_EMA_ALPHA)))
        self.top_k = max(1, int(config.AI_LEARNING_PROFILE_BLEND_TOP_K))
        self.min_improvement_ratio = max(
            0.0,
            float(config.AI_LEARNING_MIN_IMPROVEMENT_RATIO),
        )
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
            self._records = self._sanitize_records(persisted.get("records", []))
            self._total_completions = max(
                len(self._records),
                self._coerce_non_negative_int(
                    persisted.get("total_completions", len(self._records)),
                    default=len(self._records),
                ),
            )
            self._last_pair_processed = self._coerce_non_negative_int(
                persisted.get("last_pair_processed", 0),
            )
            self._last_batch_processed = self._coerce_non_negative_int(
                persisted.get("last_batch_processed", 0),
            )
            self._tuned_behavior = self._sanitize_behavior_profile(
                persisted.get("tuned_behavior", {}),
            )

            if self._tuned_behavior:
                logger.info("Historical learner applying persisted behavior profile")
                self.bot.apply_learned_behavior(self._tuned_behavior, reason="persisted")

            max_pair_processed = self._total_completions // self.pair_window
            max_batch_processed = self._total_completions // self.batch_window
            self._last_pair_processed = min(self._last_pair_processed, max_pair_processed)
            self._last_batch_processed = min(self._last_batch_processed, max_batch_processed)

    def _coerce_non_negative_int(self, value, default=0):
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return max(0, parsed)

    def _sanitize_behavior_profile(self, behavior):
        if not isinstance(behavior, dict):
            return {}

        bounds = {
            "click_delay": (
                config.AI_LEARNING_MIN_CLICK_DELAY,
                config.AI_LEARNING_MAX_CLICK_DELAY,
            ),
            "move_delay": (
                config.AI_LEARNING_MIN_MOVE_DELAY,
                config.AI_LEARNING_MAX_MOVE_DELAY,
            ),
            "upgrade_click_interval": (
                config.AI_LEARNING_MIN_UPGRADE_INTERVAL,
                config.AI_LEARNING_MAX_UPGRADE_INTERVAL,
            ),
            "search_interval": (
                config.AI_LEARNING_MIN_SEARCH_INTERVAL,
                config.AI_LEARNING_MAX_SEARCH_INTERVAL,
            ),
        }
        sanitized = {}
        for key, (minimum, maximum) in bounds.items():
            if key not in behavior:
                continue
            try:
                value = float(behavior[key])
            except (TypeError, ValueError):
                logger.warning("Ignoring persisted learning value %s=%r because it is not numeric", key, behavior[key])
                continue
            sanitized[key] = self._clamp(value, minimum, maximum)
        return sanitized

    def _sanitize_records(self, records):
        if not isinstance(records, list):
            return []

        sanitized = []
        for record in records:
            if not isinstance(record, dict):
                continue

            behavior = self._sanitize_behavior_profile(record.get("behavior", {}))
            if not behavior:
                continue

            try:
                time_spent = float(record.get("time_spent", 0.0))
            except (TypeError, ValueError):
                continue
            if time_spent <= 0:
                continue

            try:
                timestamp = float(record.get("timestamp", time.time()))
            except (TypeError, ValueError):
                timestamp = time.time()

            sanitized.append(
                {
                    "timestamp": timestamp,
                    "time_spent": time_spent,
                    "source": str(record.get("source", "unknown")),
                    "behavior": behavior,
                }
            )

        return sanitized[-config.AI_LEARNING_RECORDS_LIMIT:]

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
        self._persist()

    def record_completion(self, time_spent, source):
        if not self.enabled or time_spent <= 0:
            return
        snapshot = self._sanitize_behavior_profile(self.bot.get_runtime_behavior_snapshot())
        if not snapshot:
            return
        record = {
            "timestamp": time.time(),
            "time_spent": float(time_spent),
            "source": source,
            "behavior": snapshot,
        }
        with self._lock:
            self._records.append(record)
            self._records = self._records[-config.AI_LEARNING_RECORDS_LIMIT:]
            self._total_completions += 1
        self._persist()

    def _loop(self):
        while not self._stop.is_set():
            try:
                self._run_learning_cycle()
            except Exception:
                logger.exception("Historical learner cycle failed; continuing")
            time.sleep(max(config.LEARNING_LOOP_MIN_SLEEP, self.interval))

    def _run_learning_cycle(self):
        with self._lock:
            records = list(self._records)
            total_completions = int(self._total_completions)

        if self._is_apply_cooldown_active():
            self._persist()
            return

        if (
            total_completions >= self.pair_window
            and total_completions // self.pair_window > self._last_pair_processed
        ):
            pair_records = records[-self.pair_window:]
            profile = self._build_profile(pair_records)
            self._apply_profile_if_improved(profile, pair_records, f"pair-{self.pair_window}")
            self._last_pair_processed = total_completions // self.pair_window

        if self._is_apply_cooldown_active():
            self._persist()
            return

        if (
            total_completions >= self.batch_window
            and total_completions // self.batch_window > self._last_batch_processed
        ):
            batch_records = records[-self.batch_window:]
            profile = self._build_profile(batch_records)
            self._apply_profile_if_improved(profile, batch_records, f"batch-{self.batch_window}")
            self._last_batch_processed = total_completions // self.batch_window

        self._persist()

    def _is_apply_cooldown_active(self):
        if self.apply_cooldown <= 0:
            return False
        return (time.monotonic() - self._last_apply_time) < self.apply_cooldown

    def _build_profile(self, records):
        valid = [
            record
            for record in records
            if record.get("time_spent", 0) > 0 and record.get("behavior")
        ]
        if not valid:
            return None
        ranked = sorted(valid, key=lambda item: item.get("time_spent", float("inf")))
        top = ranked[: self.top_k]
        profile = {
            "click_delay": 0.0,
            "move_delay": 0.0,
            "upgrade_click_interval": 0.0,
            "search_interval": 0.0,
        }
        for record in top:
            behavior = record.get("behavior") or {}
            for key in profile:
                profile[key] += float(behavior.get(key, 0.0))
        count = float(len(top))
        return {key: value / count for key, value in profile.items()}

    def _apply_profile_if_improved(self, profile, records, label):
        if not profile or not records:
            return
        durations = [
            record.get("time_spent", 0.0)
            for record in records
            if record.get("time_spent", 0.0) > 0
        ]
        if not durations:
            return
        best_time = min(durations)
        avg_time = sum(durations) / len(durations)
        if avg_time <= 0:
            return
        improvement_ratio = (avg_time - best_time) / avg_time
        if improvement_ratio < self.min_improvement_ratio:
            return
        self._apply_best_record({"behavior": profile, "time_spent": best_time}, label)
        self._last_apply_time = time.monotonic()

    def _ema(self, current, target):
        return (1 - self.ema_alpha) * current + self.ema_alpha * target

    def _clamp(self, value, minimum, maximum):
        return max(minimum, min(maximum, value))

    def _apply_best_record(self, record, label):
        behavior = record.get("behavior") or {}
        if not behavior:
            return

        current = self.bot.get_runtime_behavior_snapshot()
        tuned = {}
        keys = ("click_delay", "move_delay", "upgrade_click_interval", "search_interval")
        for key in keys:
            if key not in behavior or key not in current:
                continue
            tuned[key] = self._ema(float(current[key]), float(behavior[key]))

        tuned["click_delay"] = self._clamp(
            tuned.get("click_delay", current["click_delay"]),
            config.AI_LEARNING_MIN_CLICK_DELAY,
            config.AI_LEARNING_MAX_CLICK_DELAY,
        )
        tuned["move_delay"] = self._clamp(
            tuned.get("move_delay", current["move_delay"]),
            config.AI_LEARNING_MIN_MOVE_DELAY,
            config.AI_LEARNING_MAX_MOVE_DELAY,
        )
        tuned["upgrade_click_interval"] = self._clamp(
            tuned.get("upgrade_click_interval", current["upgrade_click_interval"]),
            config.AI_LEARNING_MIN_UPGRADE_INTERVAL,
            config.AI_LEARNING_MAX_UPGRADE_INTERVAL,
        )
        tuned["search_interval"] = self._clamp(
            tuned.get("search_interval", current["search_interval"]),
            config.AI_LEARNING_MIN_SEARCH_INTERVAL,
            config.AI_LEARNING_MAX_SEARCH_INTERVAL,
        )

        self._tuned_behavior = tuned
        self.bot.apply_learned_behavior(tuned, reason=label, best_time=record.get("time_spent", 0.0))

    def _persist(self, force=False):
        if not self.persistence:
            return
        with self._lock:
            state = {
                "records": self._records[-config.AI_LEARNING_RECORDS_LIMIT:],
                "total_completions": self._total_completions,
                "last_pair_processed": self._last_pair_processed,
                "last_batch_processed": self._last_batch_processed,
                "tuned_behavior": self._tuned_behavior,
            }
        self.persistence.save(state, force=force)

    def reset(self):
        with self._lock:
            logger.info("HistoricalLearner: Resetting historical data and tuned behavior.")
            self._records = []
            self._total_completions = 0
            self._last_pair_processed = 0
            self._last_batch_processed = 0
            self._tuned_behavior = {}
            self._last_apply_time = 0.0

            self._persist(force=True)

            if self.bot and hasattr(self.bot, "apply_learned_behavior"):
                self.bot.apply_learned_behavior({}, reason="reset")


class OscillatingSearcher:
    """
    Refactored Algorithm Engine: Implements the strictly incremental Oscillating Search.
    Follows a multi-step pattern (UP then DOWN) for each widening cycle with
    precise settle-and-scan synchronization.
    """

    def __init__(self, bot: Any):
        self.bot = bot
        self.max_cycles = config.MAX_SCROLL_CYCLES
        self.scroll_increment = config.SCROLL_INCREMENT_STEP
        self.settle_duration = config.POST_SCROLL_SETTLE

    def execute_cycle(
        self,
        check_priority: Callable,
        check_main_target: Callable,
        check_fallbacks: Optional[Callable] = None,
    ) -> Optional[Any]:
        logger.info(f"[Search] Initializing Incremental Search (Limit: {self.max_cycles} cycles)")

        initial_hit = self._perform_vision_pass(check_priority, check_main_target, check_fallbacks)
        if initial_hit:
            return initial_hit

        for cycle_index in range(1, self.max_cycles + 1):
            steps_in_leg = cycle_index * self.scroll_increment

            logger.info(f"[Search] Cycle {cycle_index}: Starting DOWN leg ({steps_in_leg} steps)")
            target_found = self._run_step_sequence(
                steps_in_leg,
                1,
                check_priority,
                check_main_target,
                check_fallbacks,
            )
            if target_found:
                return target_found

            self.bot.sleep(config.CYCLE_PAUSE_DURATION)
            boundary_hit = self._perform_vision_pass(check_priority, check_main_target, check_fallbacks)
            if boundary_hit:
                return boundary_hit

            logger.info(f"[Search] Cycle {cycle_index}: Starting UP leg ({steps_in_leg} steps)")
            target_found = self._run_step_sequence(
                steps_in_leg,
                -1,
                check_priority,
                check_main_target,
                check_fallbacks,
            )
            if target_found:
                return target_found

            self.bot.sleep(config.CYCLE_PAUSE_DURATION)
            cycle_hit = self._perform_vision_pass(check_priority, check_main_target, check_fallbacks)
            if cycle_hit:
                return cycle_hit

        logger.warning(f"[Search] Logic exhausted after {self.max_cycles} cycles.")
        return None

    def _run_step_sequence(
        self,
        count: int,
        direction: int,
        p_check: Callable,
        m_check: Callable,
        f_check: Optional[Callable],
    ) -> Optional[Any]:
        for _ in range(count):
            if not self.bot.running:
                return None

            if not self.perform_scroll(direction):
                return None

            settle_wait = self.settle_duration + config.SCROLL_INTERVAL_PAUSE
            self.bot.sleep(settle_wait)

            red_interrupt = self.bot.check_intra_scroll_red_interrupt()
            if red_interrupt:
                return red_interrupt

            hit = self._perform_vision_pass(p_check, m_check, f_check)
            if hit:
                return hit
        return None

    def _perform_vision_pass(
        self,
        p_check: Callable,
        m_check: Callable,
        f_check: Optional[Callable],
    ) -> Optional[Any]:
        priority_hit = p_check()
        if priority_hit:
            return priority_hit

        main_hit = m_check()
        if main_hit:
            return main_hit

        if f_check:
            fallback_hit = f_check()
            if fallback_hit:
                return fallback_hit

        return None

    def perform_scroll(
        self,
        direction: Any,
        distance_ratio: Optional[float] = None,
        duration: Optional[float] = None,
    ):
        dir_int = self._map_direction(direction)
        start_x, start_y = config.SCROLL_START_POS

        ratio = distance_ratio or config.SCROLL_DISTANCE_RATIO
        pixel_distance = int(config.SCROLL_PIXEL_STEP * ratio)
        end_y = start_y - (pixel_distance * dir_int)

        scroll_duration = duration if duration is not None else config.SCROLL_DURATION

        success = self.bot.mouse_controller.drag(
            start_x,
            start_y,
            start_x,
            end_y,
            duration=scroll_duration,
            relative=True,
            interrupt_check=lambda: self.bot.check_critical_interrupts(raise_exception=False),
        )

        if not success:
            return False

        if hasattr(self.bot, "_clear_capture_cache"):
            self.bot._clear_capture_cache()

        if hasattr(self.bot, "scroll_offset_units"):
            self.bot.scroll_offset_units -= ratio * dir_int
        return True

    def _map_direction(self, direction: Any) -> int:
        if isinstance(direction, int):
            return direction
        return {"DOWN": -1, "UP": 1}.get(str(direction).upper(), 1)


class WorldCoordTracker:
    """
    Dynamic ROI Tracker: Tracks asset positions in world-coordinates
    to calculate precise search ROIs as the screen scrolls.
    """

    def __init__(self):
        self.tracked_assets = {}
        self.next_id = 0

    def register_asset(self, screen_x, screen_y, scroll_y, asset_type):
        world_x = screen_x
        world_y = screen_y + scroll_y
        asset_id = self.next_id
        self.tracked_assets[asset_id] = (world_x, world_y, asset_type)
        self.next_id += 1
        return asset_id

    def get_screen_roi(self, asset_id, scroll_y, padding=50):
        if asset_id not in self.tracked_assets:
            return None
        world_x, world_y, _ = self.tracked_assets[asset_id]
        screen_x = world_x
        screen_y = world_y - scroll_y

        x_min = max(0, screen_x - padding)
        x_max = screen_x + padding
        y_min = max(0, screen_y - padding)
        y_max = screen_y + padding

        return (int(x_min), int(x_max), int(y_min), int(y_max))


class ScrollHandler:
    """
    Navigation Handler: Exclusively controls all screen movement.
    Maintains the current vertical scroll state and enforces smooth, steady linear glides.
    """

    def __init__(self, bot):
        self.bot = bot
        self.mouse = bot.mouse_controller
        self.current_scroll_y = 0

    def scroll(self, distance: int, direction: str = "DOWN", duration: float = None):
        if duration is None:
            duration = config.SCROLL_DURATION

        start_pos = config.SCROLL_START_POS
        start_x, start_y = start_pos

        dir_mult = 1 if direction.upper() == "UP" else -1
        end_y = start_y - (distance * dir_mult)

        logger.info(f"[Scroll] Linear Glide: {distance}px {direction} (World Y Offset: {self.current_scroll_y})")

        success = self.mouse.drag(
            start_x,
            start_y,
            start_x,
            end_y,
            duration=duration,
            relative=True,
            interrupt_check=lambda: self.bot.check_critical_interrupts(raise_exception=False),
        )

        if success:
            self.current_scroll_y += distance * dir_mult
            self.bot.sleep(config.SCROLL_SETTLE_DELAY)

        return success

    def reset_offset(self):
        self.current_scroll_y = 0


class BaseHandler:
    def __init__(self, bot, scroll_handler: ScrollHandler):
        self.bot = bot
        self.scroll_handler = scroll_handler
        self.image_matcher = bot.image_matcher
        self.templates = bot.templates
        self.tracker = WorldCoordTracker()

    def verify_bgr_match(self, screenshot, x, y, template_name, threshold=None):
        if template_name not in self.templates:
            return False

        template, mask = self.templates[template_name]
        threshold = threshold or config.VERIFY_THRESHOLD

        padding = config.VERIFY_PADDING
        x1, y1 = max(0, x - padding), max(0, y - padding)
        x2 = min(screenshot.shape[1], x + padding)
        y2 = min(screenshot.shape[0], y + padding)

        roi = screenshot[y1:y2, x1:x2]
        if roi.size == 0:
            return False

        found, confidence, rx, ry = self.image_matcher.find_template(
            roi,
            template,
            mask=mask,
            threshold=threshold,
            template_name=f"{template_name}-verify",
        )

        if found and abs(rx + x1 - x) < 5 and abs(ry + y1 - y) < 5:
            return True
        return False


class RedIconHandler(BaseHandler):
    """Isolated module for Red Icon processing."""

    def __init__(self, bot, scroll_handler):
        super().__init__(bot, scroll_handler)
        self.red_icon_templates = [
            "RedIcon",
            "RedIcon2",
            "RedIcon3",
            "RedIcon4",
            "RedIcon5",
            "RedIcon6",
            "RedIcon7",
            "RedIcon8",
            "RedIcon9",
            "RedIcon10",
            "RedIcon11",
            "RedIcon12",
            "RedIcon13",
            "RedIcon14",
            "RedIcon15",
            "RedIconNoBG",
        ]
        self.active_targets = []

    def process(self, screenshot: np.ndarray):
        scroll_y = self.scroll_handler.current_scroll_y

        if self._search_tracked_targets(screenshot, scroll_y):
            return True

        max_y = config.MAX_SEARCH_Y
        bands = [(0, 220), (220, 440), (440, max_y)]

        for y_start, y_end in bands:
            if self._scan_roi(screenshot, (0, screenshot.shape[1], y_start, y_end)):
                return True
        return False

    def _search_tracked_targets(self, screenshot, scroll_y):
        still_active = []
        found_any = False

        self.active_targets.sort(key=lambda target: target[1] - scroll_y)

        for wx, wy, name in self.active_targets:
            sx, sy = wx, wy - scroll_y

            if 10 <= sy < config.MAX_SEARCH_Y - 10:
                roi_box = (
                    max(0, sx - 45),
                    min(screenshot.shape[1], sx + 45),
                    max(0, sy - 45),
                    min(screenshot.shape[0], sy + 45),
                )

                if not found_any and self._scan_roi(screenshot, roi_box):
                    found_any = True
                    continue
                still_active.append((wx, wy, name))
            elif -500 < sy < 1500:
                still_active.append((wx, wy, name))

        self.active_targets = still_active
        return found_any

    def _scan_roi(self, screenshot, roi_box):
        x1, x2, y1, y2 = [int(value) for value in roi_box]
        roi = screenshot[y1:y2, x1:x2]
        if roi.size == 0:
            return False

        threshold = config.RED_ICON_THRESHOLD
        scroll_y = self.scroll_handler.current_scroll_y

        found_icons = []
        for name in self.red_icon_templates:
            if name not in self.templates:
                continue
            template, mask = self.templates[name]

            matches = self.image_matcher.find_all_templates(
                roi,
                template,
                mask=mask,
                threshold=threshold,
            )

            for conf, rx, ry in matches:
                abs_x, abs_y = rx + x1, ry + y1
                if self.bot._passes_red_color_gate(screenshot, abs_x, abs_y)[0]:
                    found_icons.append((conf, abs_x, abs_y, name))

        if not found_icons:
            return False

        found_icons.sort(key=lambda item: item[0], reverse=True)
        for conf, x, y, name in found_icons:
            if self.verify_bgr_match(screenshot, x, y, name):
                self._add_to_tracker(x, y, scroll_y, name)

                logger.info(f"[RedIcon] Whitelist Verified at ({x}, {y})")
                if self.bot.mouse_controller.click(x, y, relative=True):
                    return True
        return False

    def _add_to_tracker(self, sx, sy, scroll_y, name):
        wx, wy = sx, sy + scroll_y
        for twx, twy, tname in self.active_targets:
            if abs(twx - wx) < 30 and abs(twy - wy) < 30:
                return
        self.active_targets.append((wx, wy, name))


class UpgradeStationHandler(BaseHandler):
    """Isolated module for Upgrade Station processing."""

    def process(self, screenshot: np.ndarray):
        search_roi = (0, screenshot.shape[1], 250, config.MAX_SEARCH_Y)
        x1, x2, y1, y2 = search_roi
        roi = screenshot[y1:y2, x1:x2]

        stations = self.bot._find_upgrade_stations(roi)
        for conf, rel_x, rel_y in stations:
            abs_x, abs_y = rel_x + x1, rel_y + y1

            if self.verify_bgr_match(screenshot, abs_x, abs_y, "upgradeStation"):
                logger.info(f"[UpgradeStation] Whitelist Verified at ({abs_x}, {abs_y})")
                if self.bot.mouse_controller.click(abs_x, abs_y, relative=True):
                    return True
        return False


class BoxHandler(BaseHandler):
    """Isolated module for Box processing."""

    def process(self, screenshot: np.ndarray):
        search_roi = (0, screenshot.shape[1], 150, config.MAX_SEARCH_Y)
        x1, x2, y1, y2 = search_roi
        roi = screenshot[y1:y2, x1:x2]

        boxes = self.bot._find_boxes(roi)
        for conf, rel_x, rel_y in boxes:
            abs_x, abs_y = rel_x + x1, rel_y + y1

            for index in range(1, 6):
                if self.verify_bgr_match(screenshot, abs_x, abs_y, f"box{index}"):
                    logger.info(f"[Box] Whitelist Verified: box{index} at ({abs_x}, {abs_y})")
                    if self.bot.mouse_controller.click(abs_x, abs_y, relative=True):
                        return True
                    break
        return False


class LevelCompleteInterrupt(Exception):
    """Raised when a new level is detected to immediately halt standard gameplay."""


class BotStoppedInterrupt(Exception):
    """Raised when the bot is stopped to immediately halt all actions."""


class EatventureBot:
    def __init__(self):
        logger.info("Initializing Eatventure Bot...")
        
        self.window_capture = WindowCapture(config.WINDOW_TITLE, config.WINDOW_WIDTH, config.WINDOW_HEIGHT)
        self.image_matcher = ImageMatcher(config.MATCH_THRESHOLD)
        self.mouse_controller = MouseController(
            self.window_capture.hwnd,
            config.CLICK_DELAY,
            config.MOUSE_MOVE_DELAY
        )
        self.mouse_controller.interrupt_callback = self.check_critical_interrupts
        self.state_machine = StateMachine(State.FIND_RED_ICONS)
        
        self.register_states()
        self.state_machine.set_priority_resolver(self.resolve_priority_state)
        self.red_icon_templates = [
            "RedIcon", "RedIcon2", "RedIcon3", "RedIcon4", "RedIcon5", "RedIcon6",
            "RedIcon7", "RedIcon8", "RedIcon9", "RedIcon10", "RedIcon11", "RedIcon12",
            "RedIcon13", "RedIcon14", "RedIcon15", "RedIconNoBG"
        ]
        self.templates = self.load_templates()
        self.available_red_icon_templates = self._build_available_red_icon_templates()
        self._red_template_signatures = self._build_red_template_signatures()
        self._red_template_hit_counts = {}
        self._red_template_priority = []
        self._red_template_last_seen = {}
        self._red_template_decay_window = max(1.0, float(config.RED_ICON_STABILITY_CACHE_TTL))
        self.running = False
        self.red_icon_cycle_count = 0
        self.red_icons = []
        self.current_red_icon_index = 0
        self.wait_for_unlock_attempts = 0
        self.max_wait_for_unlock_attempts = config.WAIT_FOR_UNLOCK_MAX_ATTEMPTS
        self.upgrade_station_pos = None
        
        # Legacy directional scroll state removed.
        # One-Scroll Rule: execute_oscillating_search() is the only scroll driver.
        self.work_done = False
        self.cycle_counter = 0
        self.red_icon_processed_count = 0
        self.forbidden_icon_scrolls = 0
        self.scroll_offset_units = 0  # Tracks vertical drift from center
        self._oscillation_cycle_index = 1
        self._oscillation_leg_direction = 1
        self._oscillation_leg_progress = 0
        self._scroll_break_sequence_pending = False
        
        self.successful_red_icon_positions = []
        self.upgrade_found_in_cycle = False
        self.consecutive_failed_cycles = 0
        
        self.total_levels_completed = 0
        self._last_transition_time = 0.0
        self.current_level_start_time = None
        self.completion_detected_time = None
        self.completion_detected_by = None
        
        self.telegram = TelegramNotifier(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID, config.TELEGRAM_ENABLED)
        self.tuner = AdaptiveTuner()
        self.vision_persistence = VisionPersistence(
            config.AI_VISION_STATE_FILE,
            config.AI_VISION_SAVE_INTERVAL,
        )
        self.vision_optimizer = VisionOptimizer(self.vision_persistence)
        self.vision_optimizer.apply_persisted_state(self.vision_persistence.load())
        self.learning_persistence = VisionPersistence(
            config.AI_LEARNING_STATE_FILE,
            config.AI_LEARNING_SAVE_INTERVAL,
        )
        self.historical_learner = HistoricalLearner(self, self.learning_persistence)
        self.searcher = OscillatingSearcher(self)
        self._capture_cache = {}
        self._capture_cache_ttl = config.CAPTURE_CACHE_TTL
        self._new_level_cache = {"timestamp": 0.0, "result": (False, 0.0, 0, 0), "max_y": None}
        self._new_level_red_icon_cache = {"timestamp": 0.0, "result": (False, 0.0, 0, 0), "max_y": None}
        self._capture_lock = threading.Lock()
        self._interrupt_lock = threading.RLock()
        self._new_level_event = threading.Event()
        self._new_level_interrupt = None
        self._suppress_interrupts = False
        self._new_level_monitor_stop = threading.Event()
        self._new_level_monitor_thread = None
        self._last_upgrade_station_pos = None
        self._last_new_level_override_time = 0.0
        self._last_new_level_fail_time = 0.0
        self._last_idle_click_time = 0.0
        self._state_last_run_at = {}
        self._recent_red_icon_history = []
        self._forbidden_blackout_cache = {} # {world_coord_tuple: expiry_timestamp}
        self._no_red_scroll_cycle_pending = False
        self._last_forbidden_scroll_time = 0.0
        self._timer_resolution = WindowsTimerResolution()

        self.forbidden_zones = [
            (zone["x_min"], zone["x_max"], zone["y_min"], zone["y_max"])
            for zone in config.FORBIDDEN_ZONES
        ]

        self.overlay = None
        
        logger.info("Bot initialized successfully")

    def _record_new_level_interrupt(self, source, confidence, x, y):
        if self._should_ignore_new_level_signal(source=source):
            logger.debug(
                "Ignoring background %s signal while in %s",
                source,
                self.state_machine.get_state_name(),
            )
            return

        self._set_new_level_interrupt({
            "source": source,
            "confidence": confidence,
            "x": x,
            "y": y,
            "timestamp": time.monotonic(),
        })
        self._mark_restaurant_completed(source, confidence)

    def _set_new_level_interrupt(self, interrupt):
        with self._interrupt_lock:
            self._new_level_interrupt = dict(interrupt) if isinstance(interrupt, dict) else interrupt
            self._new_level_event.set()

    def _clear_new_level_interrupt(self):
        with self._interrupt_lock:
            self._new_level_event.clear()
            self._new_level_interrupt = None

    def check_critical_interrupts(self, raise_exception=True):
        """
        The Global Safety Check (Deep Hook).
        Returns True if a critical interrupt is pending, or raises an exception to halt actions.
        """
        # 0. Re-entrancy Guard: Suppress interrupts during priority overrides
        if getattr(self, "_suppress_interrupts", False):
            return False

        # 1. Check if bot was stopped by user
        if not getattr(self, "running", True):
            if raise_exception:
                raise BotStoppedInterrupt("Bot stopped")
            return True

        # 2. Check for New Level (Requirement)
        if self._new_level_event.is_set():
            if raise_exception:
                logger.info("!!! Critical Interrupt: New Level detected. Halting current action.")
                # Raising exception here as per 'Exception-Based Control Flow' requirement
                raise LevelCompleteInterrupt("New level reached")
            return True
            
        return False

    def sleep(self, duration):
        """Centralized sleep that is aware of high-priority interrupts."""
        self.check_critical_interrupts()
        if duration > 0:
            if self._sleep_with_interrupt(duration):
                self.check_critical_interrupts()

    def _consume_new_level_interrupt(self):
        with self._interrupt_lock:
            if not self._new_level_event.is_set():
                return None
            interrupt = (
                dict(self._new_level_interrupt)
                if isinstance(self._new_level_interrupt, dict)
                else self._new_level_interrupt
            )
            self._new_level_event.clear()
            self._new_level_interrupt = None
        if interrupt and self._should_ignore_new_level_signal(source=interrupt.get("source")):
            return None
        return interrupt

    def _should_ignore_new_level_signal(self, source, state=None):
        # Ignore ALL new level signals (icons and buttons) during critical phases.
        # This prevents the bot from jumping back to TRANSITION_LEVEL while 
        # it is already in the middle of a transition.
        active_state = state or self.state_machine.get_state()
        critical_states = (
            State.TRANSITION_LEVEL,
            State.CHECK_NEW_LEVEL,
        )
        if active_state in critical_states:
            return True
            
        # Also enforce a short cooldown after a transition to handle game lag/echoes
        if source == "new level button" or source == "new level red icon":
            if time.monotonic() - self._last_transition_time < config.NEW_LEVEL_POST_TRANSITION_IGNORE_WINDOW:
                return True
                
        return False

    def _monitor_new_level(self):
        interval = config.NEW_LEVEL_MONITOR_INTERVAL
        while not self._new_level_monitor_stop.is_set():
            try:
                active_state = self.state_machine.get_state()
                if active_state in (State.CLICK_RED_ICON, State.HOLD_UPGRADE_STATION, State.TRANSITION_LEVEL):
                    time.sleep(max(interval, config.MONITOR_YIELD_BACKOFF))
                    continue

                if self._new_level_event.is_set():
                    time.sleep(max(interval, config.MONITOR_POLL_MIN_SLEEP))
                    continue

                monitor_screenshot = self._capture(max_y=config.EXTENDED_SEARCH_Y, force=True)
                limited_screenshot = monitor_screenshot[:config.MAX_SEARCH_Y, :]

                red_found, red_conf, red_x, red_y = self._detect_new_level_red_icon(
                    screenshot=monitor_screenshot,
                    max_y=config.EXTENDED_SEARCH_Y,
                    force=True,
                )
                if red_found:
                    logger.info(
                        "Background monitor: new level red icon detected at (%s, %s)",
                        red_x,
                        red_y,
                    )
                    self._record_new_level_interrupt("new level red icon", red_conf, red_x, red_y)
                    time.sleep(max(interval, config.MONITOR_POLL_MIN_SLEEP))
                    continue

                found, confidence, x, y = self._detect_new_level(
                    screenshot=limited_screenshot,
                    max_y=config.MAX_SEARCH_Y,
                    force=True,
                )
                if found:
                    logger.info("Background monitor: new level button detected at (%s, %s)", x, y)
                    self._record_new_level_interrupt("new level button", confidence, x, y)

                time.sleep(max(interval, config.MONITOR_POLL_MIN_SLEEP))
            except Exception:
                if self._new_level_monitor_stop.is_set():
                    break
                logger.exception("Background new-level monitor cycle failed; continuing")
                time.sleep(max(interval, config.MONITOR_YIELD_BACKOFF))

    def _apply_tuning(self):
        if not self.tuner.enabled:
            return
        self.mouse_controller.click_delay = self.tuner.click_delay
        self.mouse_controller.move_delay = self.tuner.move_delay

    def _click_idle(self, wait_after=True):
        now = time.monotonic()
        cooldown = config.IDLE_CLICK_COOLDOWN
        if cooldown > 0 and now - self._last_idle_click_time < cooldown:
            logger.debug("Skipping idle click due to cooldown")
            return False
        clicked = self.mouse_controller.click(
            config.IDLE_CLICK_POS[0],
            config.IDLE_CLICK_POS[1],
            relative=True,
            wait_after=wait_after,
        )
        if clicked:
            self._last_idle_click_time = time.monotonic()
        return clicked

    def _scroll_away_from_forbidden_zone(self, y_position, asset_name="asset"):
        # One-Scroll Rule retained: do not execute manual directional drags here.
        # Instead, redirect the FSM into the canonical oscillating search cycle.
        logger.warning(
            "%s in forbidden zone at y=%s; redirecting to Main Loop Scroll (Oscillating Search)",
            asset_name,
            y_position,
        )
        now = time.monotonic()
        cooldown = max(0.0, float(config.FORBIDDEN_ZONE_SCROLL_REENTRY_COOLDOWN))
        wait_remaining = (self._last_forbidden_scroll_time + cooldown) - now
        if wait_remaining > 0:
            if self._uninterrupted_main_flow_enabled():
                logger.debug(
                    "Skipping forbidden-zone scroll redirect cooldown %.3fs to preserve main flow",
                    wait_remaining,
                )
            else:
                logger.debug(
                    "Applying forbidden-zone scroll redirect cooldown %.3fs",
                    wait_remaining,
                )
                self._sleep_with_interrupt(wait_remaining)
        self._last_forbidden_scroll_time = time.monotonic()
        return True

    def _uninterrupted_main_flow_enabled(self):
        return not bool(config.ENABLE_NO_ICON_SCROLL_INTERRUPT)

    def _no_icon_scroll_interrupt_enabled(self):
        return bool(config.ENABLE_NO_ICON_SCROLL_INTERRUPT)

    def _scroll_break_passthrough_active(self):
        if not getattr(self, "_scroll_break_sequence_pending", False):
            return False
        event = getattr(self, "_new_level_event", None)
        if event is not None and event.is_set():
            return False
        if getattr(self, "completion_detected_time", None) is not None:
            return False
        return True

    def _current_oscillation_leg_target_steps(self):
        increment = max(1, int(config.SCROLL_INCREMENT_STEP))
        return max(1, int(self._oscillation_cycle_index) * increment)

    def _advance_oscillation_progress(self):
        leg_target = self._current_oscillation_leg_target_steps()
        self._oscillation_leg_progress += 1

        leg_completed = self._oscillation_leg_progress >= leg_target
        cycle_completed = False

        if leg_completed:
            self._oscillation_leg_progress = 0
            if self._oscillation_leg_direction > 0:
                self._oscillation_leg_direction = -1
            else:
                self._oscillation_leg_direction = 1
                cycle_completed = True
                self._oscillation_cycle_index += 1
                max_cycles = max(1, int(config.MAX_SCROLL_CYCLES))
                if self._oscillation_cycle_index > max_cycles:
                    self._oscillation_cycle_index = 1

        return leg_completed, cycle_completed, leg_target

    def _advance_after_blocked_red_icon(self, reason):
        logger.warning("%s", reason)
        self.current_red_icon_index = getattr(self, "current_red_icon_index", 0) + 1
        red_icons = getattr(self, "red_icons", [])
        if self.current_red_icon_index < len(red_icons):
            return State.CLICK_RED_ICON
        return State.CHECK_UNLOCK

    def _advance_after_blocked_station(self, reason):
        logger.warning("%s", reason)
        self.red_icon_processed_count = getattr(self, "red_icon_processed_count", 0) + 1
        self.current_red_icon_index = getattr(self, "current_red_icon_index", 0) + 1
        self.upgrade_station_pos = None
        self._last_upgrade_station_pos = None
        red_icons = getattr(self, "red_icons", [])
        if self.current_red_icon_index < len(red_icons):
            return State.CLICK_RED_ICON
        return State.UPGRADE_STATS

    def _recover_from_step_exception(self):
        current_state = self.state_machine.get_state()
        recovery_state = (
            State.CHECK_NEW_LEVEL
            if self._new_level_event.is_set()
            or self.completion_detected_time is not None
            or current_state in (State.CHECK_NEW_LEVEL, State.TRANSITION_LEVEL)
            else State.FIND_RED_ICONS
        )

        self._suppress_interrupts = False
        self._no_red_scroll_cycle_pending = False
        self.red_icons = []
        self.current_red_icon_index = 0
        self.red_icon_cycle_count = 0
        self.wait_for_unlock_attempts = 0
        self.work_done = False
        self.upgrade_found_in_cycle = False
        self.upgrade_station_pos = None
        self._last_upgrade_station_pos = None
        self._recent_red_icon_history = []
        self._clear_capture_cache()
        self._reset_search_cycle(reason="unexpected step exception")

        if recovery_state != State.CHECK_NEW_LEVEL:
            self._clear_new_level_interrupt()
            self.completion_detected_time = None
            self.completion_detected_by = None

        logger.warning(
            "Recovering bot main flow after unexpected step failure via %s",
            recovery_state.name,
        )
        self.state_machine.transition(recovery_state)
        return recovery_state

    def _is_asset_click_safe(self, asset_name, x, y):
        precheck_delay = max(0.0, float(config.ASSET_BOUNDARY_PRECHECK_DELAY))
        confirm_delay = max(0.0, float(config.ASSET_BOUNDARY_CONFIRM_DELAY))

        if precheck_delay > 0:
            if self._sleep_with_interrupt(precheck_delay):
                logger.info(
                    "%s pre-click validation interrupted by new-level signal during precheck delay",
                    asset_name,
                )
                return None

        first_safe = self.mouse_controller.is_safe_to_click(x, y, relative=True)
        if not first_safe:
            logger.warning(
                "%s blocked by forbidden-zone pre-click validator at (%s, %s)",
                asset_name,
                x,
                y,
            )
            return False

        if confirm_delay > 0:
            if self._sleep_with_interrupt(confirm_delay):
                logger.info(
                    "%s pre-click validation interrupted by new-level signal during confirm delay",
                    asset_name,
                )
                return None

        second_safe = self.mouse_controller.is_safe_to_click(x, y, relative=True)
        if not second_safe:
            logger.warning(
                "%s blocked by forbidden-zone confirmation validator at (%s, %s)",
                asset_name,
                x,
                y,
            )
            return False

        return True

    def _redirect_forbidden_asset_to_scroll(self, asset_name, x, y):
        logger.info(
            "%s forbidden-zone redirect requested for (%s, %s)",
            asset_name,
            x,
            y,
        )
        return self._scroll_away_from_forbidden_zone(y, asset_name=asset_name)

    def resolve_priority_state(self, current_state):
        if current_state in (State.CHECK_NEW_LEVEL, State.TRANSITION_LEVEL):
            return None

        if (
            self._no_icon_scroll_interrupt_enabled()
            and current_state == State.FIND_RED_ICONS
            and self._no_red_scroll_cycle_pending
        ):
            logger.info("Priority override: continuing no-red scroll cycle after fallback asset scan")
            self._no_red_scroll_cycle_pending = False
            return State.SCROLL

        interrupt = self._consume_new_level_interrupt()
        if interrupt:
            logger.info(
                "Priority override: background %s detected at (%s, %s), interrupting current action",
                interrupt["source"],
                interrupt["x"],
                interrupt["y"],
            )
            if self._no_icon_scroll_interrupt_enabled() and self._no_red_scroll_cycle_pending:
                logger.info("Clearing deferred no-red scroll due to pending level transition interrupt")
                self._no_red_scroll_cycle_pending = False
            self._click_new_level_override(
                source=interrupt["source"],
                x=interrupt["x"],
                y=interrupt["y"]
            )
            return State.CHECK_NEW_LEVEL

        priority_screenshot = self._capture(max_y=config.EXTENDED_SEARCH_Y)
        priority_hit = self._detect_new_level_priority(
            screenshot=priority_screenshot,
            max_y=config.EXTENDED_SEARCH_Y,
            force=True,
        )
        if priority_hit:
            source, confidence, x, y = priority_hit
            logger.info(
                "Priority override: %s detected at (%s, %s), transitioning immediately",
                source,
                x,
                y,
            )
            if self._no_icon_scroll_interrupt_enabled() and self._no_red_scroll_cycle_pending:
                logger.info("Clearing deferred no-red scroll due to immediate level transition")
                self._no_red_scroll_cycle_pending = False
            self._click_new_level_override(source=source)
            return State.CHECK_NEW_LEVEL

        return None

    def _enforce_state_min_interval(self):
        state = self.state_machine.get_state_name()
        per_state = config.STATE_MIN_INTERVALS
        min_interval = float(per_state.get(state, config.STATE_MIN_INTERVAL_DEFAULT))
        if min_interval <= 0:
            self._state_last_run_at[state] = time.monotonic()
            return

        now = time.monotonic()
        last_run = self._state_last_run_at.get(state, 0.0)
        wait_time = (last_run + min_interval) - now
        if wait_time > 0 and self._sleep_with_interrupt(wait_time):
            self._state_last_run_at[state] = time.monotonic()
            return
        self._state_last_run_at[state] = time.monotonic()

    def _stable_red_icons(self, red_icons):
        if not red_icons:
            return []

        ttl = max(0.01, float(config.RED_ICON_STABILITY_CACHE_TTL))
        radius = max(4, int(config.RED_ICON_STABILITY_RADIUS))
        min_hits = max(1, int(config.RED_ICON_STABILITY_MIN_HITS))
        max_history = max(2, int(config.RED_ICON_STABILITY_MAX_HISTORY))
        immediate_threshold = config.RED_ICON_PIXEL_THRESHOLD * 1.5
        now = time.monotonic()

        history = []
        for entry in getattr(self, "_recent_red_icon_history", []):
            if now - entry.get("timestamp", 0.0) <= ttl:
                history.append(entry)

        current = {"timestamp": now, "icons": list(red_icons)}
        history.append(current)
        if len(history) > max_history:
            history = history[-max_history:]
        self._recent_red_icon_history = history

        stable = []
        for conf, x, y, px_count in red_icons:
            # Requirement: Pixel Density Trigger (Immediate success if high density)
            if px_count >= immediate_threshold:
                logger.debug(f"Immediate trigger: high pixel density ({px_count}) at ({x}, {y})")
                stable.append((conf, x, y))
                continue

            hits = 0
            best_conf = conf
            for entry in history:
                for h_conf, hx, hy, hpx in entry["icons"]:
                    if abs(hx - x) <= radius and abs(hy - y) <= radius:
                        hits += 1
                        if h_conf > best_conf:
                            best_conf = h_conf
                        break
            if hits >= min_hits:
                stable.append((best_conf, x, y))

        return stable

    def _add_to_blackout(self, x, y):
        """Registers a screen coordinate to the world-space blackout cache."""
        now = time.monotonic()
        ttl = float(config.FORBIDDEN_BLACKOUT_DURATION)
        scroll_y = int(self.scroll_offset_units * config.SCROLL_PIXEL_STEP)
        world_coord = (int(x), int(y + scroll_y))
        self._forbidden_blackout_cache[world_coord] = now + ttl
        logger.info(f"[Blackout] Added world-coord {world_coord} for {ttl}s")

    @contextmanager
    def suppress_interrupts(self):
        """Pythonic scope-guard to temporarily disable interrupt triggers."""
        self._suppress_interrupts = True
        try:
            yield
        finally:
            self._suppress_interrupts = False

    def _click_new_level_override(self, source=None, x=None, y=None):
        now = time.monotonic()
        cooldown = config.NEW_LEVEL_OVERRIDE_COOLDOWN
        if cooldown > 0 and now - self._last_new_level_override_time < cooldown:
            logger.debug("Priority override: skipping click sequence due to cooldown")
            return
        
        self._last_new_level_override_time = now
        self._mark_restaurant_completed(source or "priority override")
        # Logic: Transition to CHECK_NEW_LEVEL state which now handles verification and execution
        logger.info("Priority override: triggering CHECK_NEW_LEVEL sequence")

    def _reset_runtime_interrupt_state(self, reset_completion=True):
        self._clear_new_level_interrupt()
        self._last_new_level_override_time = 0.0
        self._last_new_level_fail_time = 0.0
        self._last_transition_time = 0.0
        self._no_red_scroll_cycle_pending = False
        self._scroll_break_sequence_pending = False
        self.red_icons = []
        self.current_red_icon_index = 0
        self.red_icon_cycle_count = 0
        self.wait_for_unlock_attempts = 0
        self.work_done = False
        self.upgrade_found_in_cycle = False
        self.upgrade_station_pos = None
        self._last_upgrade_station_pos = None
        self._recent_red_icon_history = []
        self._clear_capture_cache()
        self._reset_search_cycle(reason="runtime reset")
        if reset_completion:
            self.completion_detected_time = None
            self.completion_detected_by = None

    def _capture(self, max_y=None, force=False):
        cache_key = max_y if max_y is not None else "full"
        with self._capture_lock:
            now = time.monotonic()
            cached = self._capture_cache.get(cache_key)
            if not force and cached and now - cached[0] <= self._capture_cache_ttl:
                return cached[1]

            frame = self.window_capture.capture(max_y=max_y)
            self._capture_cache[cache_key] = (time.monotonic(), frame)
            return frame

    def _clear_capture_cache(self):
        with self._capture_lock:
            self._capture_cache.clear()
            self._new_level_cache = {"timestamp": 0.0, "result": (False, 0.0, 0, 0), "max_y": None}
            self._new_level_red_icon_cache = {"timestamp": 0.0, "result": (False, 0.0, 0, 0), "max_y": None}

    def _sleep_until(self, target_time):
        now = time.monotonic()
        if target_time <= now:
            return False

        interval = config.NEW_LEVEL_INTERRUPT_INTERVAL
        if interval <= 0:
            time.sleep(max(0, target_time - now))
            return False

        while now < target_time:
            # Check for critical interrupts (like Level Complete)
            self.check_critical_interrupts()
            
            remaining = max(0, target_time - now)
            time.sleep(min(interval, remaining))
            interrupt = None
            with self._interrupt_lock:
                if self._new_level_event.is_set():
                    interrupt = (
                        dict(self._new_level_interrupt)
                        if isinstance(self._new_level_interrupt, dict)
                        else self._new_level_interrupt
                    )
                    if interrupt is None:
                        self._new_level_event.clear()
            if interrupt:
                if self._should_ignore_new_level_signal(source=interrupt.get("source")):
                    self._clear_new_level_interrupt()
                    now = time.monotonic()
                    continue
                return True
            if self._should_interrupt_for_new_level(max_y=config.MAX_SEARCH_Y, force=True):
                return True
            now = time.monotonic()
        return False

    def _sleep_with_interrupt(self, duration):
        if duration <= 0:
            return False
        return self._sleep_until(time.monotonic() + duration)

    def _sleep_with_search_interrupt(self, duration):
        """
        Pauses for the specified duration but checks for Red Icons and Level Transitions.
        Returns a State if an interrupt is detected, otherwise None.
        """
        if duration <= 0:
            return None
            
        target_time = time.monotonic() + duration
        interval = max(config.MONITOR_POLL_MIN_SLEEP, config.NEW_LEVEL_INTERRUPT_INTERVAL)
        
        while time.monotonic() < target_time:
            # Check for critical interrupts (like Level Complete)
            self.check_critical_interrupts()
            
            # 1. Check for Level Transition (High Priority)
            if self._should_interrupt_for_new_level(force=True):
                return State.CHECK_NEW_LEVEL
                
            # 2. Check for Red Icons
            screenshot = self._capture(max_y=config.MAX_SEARCH_Y, force=True)
            red_icons = self._detect_red_icons_in_view(screenshot, max_y=config.MAX_SEARCH_Y)
            
            # Implementation: Immediate Trigger for high density
            immediate_threshold = config.RED_ICON_PIXEL_THRESHOLD * 1.5
            
            if red_icons:
                filtered, _ = self._filter_forbidden_red_icons(red_icons)
                if filtered:
                    # Check if any pass the 'immediate' threshold
                    has_immediate = any(px >= immediate_threshold for *_, px in filtered)
                    
                    if has_immediate:
                        self.red_icons = self._prioritize_red_icons(filtered)
                        self.current_red_icon_index = 0
                        self.work_done = True
                        return State.CLICK_RED_ICON
                    
                    # Otherwise, use standard stability check (which requires 3+ hits)
                    stable = self._stable_red_icons(filtered)
                    if stable:
                        self.red_icons = self._prioritize_red_icons(stable)
                        self.current_red_icon_index = 0
                        self.work_done = True
                        return State.CLICK_RED_ICON
            
            # 3. Check for Fallback Assets (Upgrade Station, Boxes)
            clicked = self._scan_and_click_non_red_assets(screenshot)
            if clicked == -2:
                return State.CHECK_NEW_LEVEL
            if clicked == -1:
                return State.SCROLL
            if clicked > 0:
                # We clicked something, need to re-evaluate state
                return State.FIND_RED_ICONS

            time.sleep(min(interval, max(0, target_time - time.monotonic())))
            
        return None

    def _detect_new_level(self, screenshot=None, max_y=None, force=False):
        target_max_y = max_y if max_y is not None else config.MAX_SEARCH_Y
        now = time.monotonic()
        cached = self._new_level_cache
        use_cache = screenshot is None and not force
        if use_cache and cached["max_y"] == target_max_y and now - cached["timestamp"] <= self._capture_cache_ttl:
            return cached["result"]

        if screenshot is None:
            screenshot = self._capture(max_y=target_max_y, force=force)

        threshold = self.vision_optimizer.new_level_threshold if self.vision_optimizer.enabled else config.NEW_LEVEL_THRESHOLD
        result = self._find_new_level(screenshot, threshold=threshold)
        if result[0]:
            self.vision_optimizer.update_new_level_confidence(result[1])
        else:
            self.vision_optimizer.update_new_level_miss()
        self._new_level_cache = {"timestamp": now, "result": result, "max_y": target_max_y}
        return result

    def _detect_new_level_red_icon(self, screenshot=None, max_y=None, force=False):
        now = time.monotonic()
        
        # Check cooldown after a recent failure to prevent click loops on non-level red icons (e.g. Map rewards)
        fail_cooldown = config.NEW_LEVEL_FAIL_COOLDOWN
        if now - self._last_new_level_fail_time < fail_cooldown:
            return (False, 0.0, 0, 0)

        target_max_y = max_y if max_y is not None else config.MAX_SEARCH_Y
        cached = self._new_level_red_icon_cache
        cache_ttl = config.NEW_LEVEL_RED_ICON_CACHE_TTL
        use_cache = screenshot is None and not force
        if use_cache and cached["max_y"] == target_max_y and now - cached["timestamp"] <= cache_ttl:
            return cached["result"]

        max_template_width = 0
        max_template_height = 0
        for _, template, _ in self._iter_red_icon_templates():
            max_template_height = max(max_template_height, int(template.shape[0]))
            max_template_width = max(max_template_width, int(template.shape[1]))

        roi_pad_x = max(2, max_template_width // 2)
        roi_pad_y = max(2, max_template_height // 2)

        # The new-level red icon is configured near the bottom of the screen.
        # If callers provide a cropped frame (e.g. MAX_SEARCH_Y), the ROI can
        # be clipped out entirely and produce guaranteed false negatives.
        required_bottom = config.NEW_LEVEL_RED_ICON_Y_MAX + roi_pad_y
        if screenshot is None:
            screenshot = self._capture(max_y=target_max_y, force=force)

        if screenshot.shape[0] < required_bottom:
            recapture_max_y = max(target_max_y, required_bottom)
            screenshot = self._capture(max_y=recapture_max_y, force=force)
            target_max_y = recapture_max_y

        height, width = screenshot.shape[:2]
        x_min = max(0, config.NEW_LEVEL_RED_ICON_X_MIN - roi_pad_x)
        x_max = min(width, config.NEW_LEVEL_RED_ICON_X_MAX + roi_pad_x)
        y_min = max(0, config.NEW_LEVEL_RED_ICON_Y_MIN - roi_pad_y)
        y_max = min(height, config.NEW_LEVEL_RED_ICON_Y_MAX + roi_pad_y)

        if x_min >= x_max or y_min >= y_max or not self.available_red_icon_templates:
            result = (False, 0.0, 0, 0)
            self._new_level_red_icon_cache = {
                "timestamp": now,
                "result": result,
                "max_y": target_max_y,
            }
            return result

        roi = screenshot[y_min:y_max, x_min:x_max]
        detections = {}
        buckets = {}
        template_hits = {}
        threshold = (
            self.vision_optimizer.new_level_red_icon_threshold
            if self.vision_optimizer.enabled
            else config.NEW_LEVEL_RED_ICON_THRESHOLD
        )

        for template_name, template, mask in self._iter_red_icon_templates():
            if template.shape[0] > roi.shape[0] or template.shape[1] > roi.shape[1]:
                continue

            icons = self.image_matcher.find_all_templates(
                roi,
                template,
                mask=mask,
                threshold=threshold,
                min_distance=config.RED_ICON_MIN_DISTANCE,
                template_name=template_name,
            )
            for conf, x, y in icons:
                abs_x = x + x_min
                abs_y = y + y_min
                passed_color_gate, _ = self._passes_red_color_gate(screenshot, abs_x, abs_y)
                if not passed_color_gate:
                    continue
                passed_template_gate, _ = self._passes_red_icon_template_gate(
                    screenshot,
                    abs_x,
                    abs_y,
                    template_name,
                    template,
                    mask,
                )
                if not passed_template_gate:
                    continue
                self._merge_detection(
                    detections,
                    buckets,
                    abs_x,
                    abs_y,
                    template_name,
                    conf,
                )
                template_hits[template_name] = template_hits.get(template_name, 0) + 1

        min_matches = config.NEW_LEVEL_RED_ICON_MIN_MATCHES
        best_match = None
        for (x, y), matches in detections.items():
            if len(matches) >= min_matches:
                max_conf = max(conf for _, conf, _ in matches)
                if best_match is None or max_conf > best_match[1]:
                    best_match = (True, max_conf, x, y)

        self._update_red_template_priority(template_hits)
        result = best_match or (False, 0.0, 0, 0)
        if result[0]:
            self.vision_optimizer.update_new_level_red_icon_confidence(result[1])
        else:
            self.vision_optimizer.update_new_level_red_icon_miss()

        self._new_level_red_icon_cache = {"timestamp": now, "result": result, "max_y": target_max_y}
        return result

    def _detect_new_level_priority(self, screenshot=None, max_y=None, force=False):
        found, confidence, x, y = self._detect_new_level(
            screenshot=screenshot,
            max_y=max_y,
            force=force,
        )
        if found:
            self._mark_restaurant_completed("new level button", confidence)
            return "new level button", confidence, x, y

        red_found, red_conf, red_x, red_y = self._detect_new_level_red_icon(
            screenshot=screenshot,
            max_y=max_y,
            force=force,
        )
        if red_found:
            self._mark_restaurant_completed("new level red icon", red_conf)
            return "new level red icon", red_conf, red_x, red_y

        return None

    def _should_interrupt_for_new_level(self, screenshot=None, max_y=None, force=False):
        priority_hit = self._detect_new_level_priority(
            screenshot=screenshot,
            max_y=max_y,
            force=force,
        )
        if priority_hit:
            source, confidence, x, y = priority_hit
            
            # During critical station interaction phases, only interrupt if we see the actual 
            # renovation button, never just the red icon on the map which could be a reward.
            if self._should_ignore_new_level_signal(source=source):
                return False

            if source == "new level red icon":
                logger.info(
                    "Priority override: new level red icon detected at (%s, %s), interrupting current action",
                    x,
                    y,
                )
            else:
                logger.info("Priority override: new level detected, interrupting current action")
            return True
        return False

    def _mark_restaurant_completed(self, source, confidence=None):
        if self.completion_detected_time is not None:
            return
        self.completion_detected_time = datetime.now()
        self.completion_detected_by = source
        if confidence is None:
            logger.info("Restaurant completion detected via %s", source)
        else:
            logger.info("Restaurant completion detected via %s (confidence %.3f)", source, confidence)

    def _abort_transition(self, reason):
        logger.warning("New-level transition aborted: %s", reason)
        self._last_new_level_fail_time = time.monotonic()
        self.completion_detected_time = None
        self.completion_detected_by = None
        return State.FIND_RED_ICONS

    def _click_transition_target(self, x, y, label, wait_after=True):
        success = self.mouse_controller.click(
            x,
            y,
            relative=True,
            wait_after=wait_after,
        )
        if not success:
            logger.warning("%s click failed at (%s, %s)", label, x, y)
        return success

    def _execute_transition_travel_clicks(self):
        found_nl, _, x_nl, y_nl = self._detect_new_level(force=True)
        if found_nl:
            logger.info(
                "Step 3: Confirm Travel - Clicking detected travel button at (%s, %s)",
                x_nl,
                y_nl,
            )
            if self._click_transition_target(x_nl, y_nl, "Detected travel button"):
                return True
            logger.warning(
                "Detected travel button click failed at (%s, %s); falling back to configured travel positions",
                x_nl,
                y_nl,
            )

        logger.info("Step 3: Confirm Travel - Clicking config travel positions (backup)")
        if not self._click_transition_target(
            config.NEW_LEVEL_POS[0],
            config.NEW_LEVEL_POS[1],
            "Configured travel button",
        ):
            return False
        if self._sleep_with_interrupt(config.BACKUP_CLICK_GAP):
            return False
        return self._click_transition_target(
            config.LEVEL_TRANSITION_POS[0],
            config.LEVEL_TRANSITION_POS[1],
            "Configured level transition button",
        )

    def _find_new_level(self, screenshot, threshold=None):
        if "newLevel" not in self.templates:
            return False, 0.0, 0, 0

        template, mask = self.templates["newLevel"]
        return self.image_matcher.find_template(
            screenshot,
            template,
            mask=mask,
            threshold=threshold or config.NEW_LEVEL_THRESHOLD,
            template_name="newLevel",
        )

    def _has_stats_upgrade_icon(self, screenshot):
        if not self.red_icon_templates:
            return False, 0.0

        height, width = screenshot.shape[:2]
        x_min = max(0, config.UPGRADE_RED_ICON_X_MIN - config.STATS_ICON_PADDING)
        x_max = min(width, config.UPGRADE_RED_ICON_X_MAX + config.STATS_ICON_PADDING)
        y_min = max(0, config.UPGRADE_RED_ICON_Y_MIN - config.STATS_ICON_PADDING)
        y_max = min(height, config.UPGRADE_RED_ICON_Y_MAX + config.STATS_ICON_PADDING)

        if x_min >= x_max or y_min >= y_max:
            return False, 0.0

        roi = screenshot[y_min:y_max, x_min:x_max]
        threshold = (
            self.vision_optimizer.stats_upgrade_threshold
            if self.vision_optimizer.enabled
            else config.STATS_RED_ICON_THRESHOLD
        )
        best_confidence = 0.0
        template_hits = {}

        for template_name, template, mask in self._iter_red_icon_templates():
            icons = self.image_matcher.find_all_templates(
                roi,
                template,
                mask=mask,
                threshold=threshold,
                min_distance=config.RED_ICON_MIN_DISTANCE,
                template_name=template_name,
            )

            if icons:
                for conf, x, y in icons:
                    abs_x = x + x_min
                    abs_y = y + y_min
                    passed_color_gate, _ = self._passes_red_color_gate(screenshot, abs_x, abs_y)
                    if not passed_color_gate:
                        continue
                    passed_template_gate, _ = self._passes_red_icon_template_gate(
                        screenshot,
                        abs_x,
                        abs_y,
                        template_name,
                        template,
                        mask,
                    )
                    if not passed_template_gate:
                        continue
                    best_confidence = max(best_confidence, conf)
                    template_hits[template_name] = template_hits.get(template_name, 0) + 1

        self._update_red_template_priority(template_hits)
        return best_confidence > 0, best_confidence

    def _merge_detection(self, detections, buckets, x, y, template_name, conf, proximity=None, bucket_size=None, pixel_count=0):
        prox = proximity if proximity is not None else config.RED_ICON_MERGE_PROXIMITY
        bsize = bucket_size if bucket_size is not None else config.RED_ICON_MERGE_BUCKET_SIZE
        bucket_x = x // bsize
        bucket_y = y // bsize
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for px, py in buckets.get((bucket_x + dx, bucket_y + dy), []):
                    if abs(x - px) < prox and abs(y - py) < prox:
                        detections[(px, py)].append((template_name, conf, pixel_count))
                        return

        detections[(x, y)] = [(template_name, conf, pixel_count)]
        buckets.setdefault((bucket_x, bucket_y), []).append((x, y))

    def _refine_template_position(
        self,
        template_name,
        expected_pos,
        search_radius,
        screenshot=None,
        threshold=None,
        check_color=False,
    ):
        if template_name not in self.templates:
            return expected_pos, False

        if screenshot is None:
            screenshot = self._capture(max_y=config.MAX_SEARCH_Y, force=True)

        template, mask = self.templates[template_name]
        x, y = expected_pos

        x1 = max(0, x - search_radius)
        y1 = max(0, y - search_radius)
        x2 = min(screenshot.shape[1], x + search_radius)
        y2 = min(screenshot.shape[0], y + search_radius)

        roi = screenshot[y1:y2, x1:x2]
        if roi.size == 0:
            return expected_pos, False

        found, confidence, rx, ry = self.image_matcher.find_template(
            roi,
            template,
            mask=mask,
            threshold=threshold,
            template_name=f"{template_name}-refine",
            check_color=check_color,
        )
        if not found:
            return expected_pos, False

        return (rx + x1, ry + y1), True

    def _refine_red_icon_position(self, x, y, screenshot=None):
        if not self.available_red_icon_templates:
            return (x, y), False, 0.0

        if screenshot is None:
            screenshot = self._capture(max_y=config.MAX_SEARCH_Y, force=True)

        search_radius = config.RED_ICON_REFINE_RADIUS
        x1 = max(0, x - search_radius)
        y1 = max(0, y - search_radius)
        x2 = min(screenshot.shape[1], x + search_radius)
        y2 = min(screenshot.shape[0], y + search_radius)

        roi = screenshot[y1:y2, x1:x2]
        if roi.size == 0:
            return (x, y), False, 0.0

        base_threshold = (
            self.vision_optimizer.red_icon_threshold
            if self.vision_optimizer.enabled
            else config.RED_ICON_THRESHOLD
        )
        threshold = max(0.0, base_threshold - config.RED_ICON_REFINE_THRESHOLD_DROP)
        best_match = None

        for template_name, template, mask in self._iter_red_icon_templates():
            found, confidence, rx, ry = self.image_matcher.find_template(
                roi,
                template,
                mask=mask,
                threshold=threshold,
                template_name=f"{template_name}-refine",
            )
            if not found:
                continue
            abs_x = rx + x1
            abs_y = ry + y1
            passed_color_gate, _ = self._passes_red_color_gate(screenshot, abs_x, abs_y)
            if not passed_color_gate:
                continue
            passed_template_gate, _ = self._passes_red_icon_template_gate(
                screenshot,
                abs_x,
                abs_y,
                template_name,
                template,
                mask,
            )
            if not passed_template_gate:
                continue
            if best_match is None or confidence > best_match[2]:
                best_match = (abs_x, abs_y, confidence)

        if best_match:
            return (best_match[0], best_match[1]), True, best_match[2]
        return (x, y), False, 0.0

    def _refine_upgrade_station_click_target(self, expected_pos, screenshot=None, threshold=None):
        refined_pos, refined = self._refine_template_position(
            "upgradeStation",
            expected_pos,
            config.UPGRADE_STATION_CLICK_REFINE_RADIUS,
            screenshot=screenshot,
            threshold=threshold,
            check_color=config.UPGRADE_STATION_COLOR_CHECK,
        )
        return refined_pos, refined

    def _detect_red_icons_in_view(self, screenshot, max_y=None, min_distance=80, threshold_override=None, min_matches_override=None, relaxed_color=False):
        if not self.available_red_icon_templates:
            return []

        detections = {}
        buckets = {}
        template_hits = {}
        if max_y is not None:
            screenshot = screenshot[:max_y, :]
        base_threshold = (
            self.vision_optimizer.red_icon_threshold
            if self.vision_optimizer.enabled
            else config.RED_ICON_THRESHOLD
        )
        threshold = base_threshold if threshold_override is None else threshold_override

        for template_name, template, mask in self._iter_red_icon_templates():
            icons = self.image_matcher.find_all_templates(
                screenshot,
                template,
                mask=mask,
                threshold=threshold,
                min_distance=min_distance,
                template_name=template_name,
            )

            for conf, x, y in icons:
                passed, pixel_count = self._passes_red_color_gate(screenshot, x, y, relaxed=relaxed_color)
                if not passed:
                    continue
                passed_template_gate, _ = self._passes_red_icon_template_gate(
                    screenshot,
                    x,
                    y,
                    template_name,
                    template,
                    mask,
                    relaxed=relaxed_color,
                )
                if not passed_template_gate:
                    continue
                self._merge_detection(
                    detections,
                    buckets,
                    x,
                    y,
                    template_name,
                    conf,
                    pixel_count=pixel_count
                )
                template_hits[template_name] = template_hits.get(template_name, 0) + 1

        self._update_red_template_priority(template_hits)

        min_matches = config.RED_ICON_MIN_MATCHES if min_matches_override is None else min_matches_override
        red_icons = []
        for (x, y), matches in detections.items():
            if len(matches) >= min_matches:
                max_conf = max(conf for _, conf, _ in matches)
                max_pixel_count = max(px for _, _, px in matches)
                red_icons.append((max_conf, x, y, max_pixel_count))
        return red_icons

    def _is_red_icon_present_at(self, x, y, screenshot=None, threshold_override=None, relaxed_color=False):
        if not self.available_red_icon_templates:
            return False

        target_screenshot = screenshot if screenshot is not None else self._capture(max_y=config.MAX_SEARCH_Y)

        if config.RED_ICON_COLOR_CHECK:
            passed_color_gate, _ = self._passes_red_color_gate(
                target_screenshot,
                x,
                y,
                relaxed=relaxed_color,
            )
            if not passed_color_gate:
                return False

        if threshold_override is not None:
            threshold = threshold_override
        else:
            threshold = (
                self.vision_optimizer.red_icon_threshold
                if self.vision_optimizer.enabled
                else config.RED_ICON_THRESHOLD
            )

        padding = config.RED_ICON_VERIFY_PADDING
        x1 = max(0, x - padding)
        y1 = max(0, y - padding)
        x2 = min(target_screenshot.shape[1], x + padding)
        y2 = min(target_screenshot.shape[0], y + padding)

        roi = target_screenshot[y1:y2, x1:x2]
        if roi.size == 0:
            return False

        for template_name, template, mask in self._iter_red_icon_templates():
            found, confidence, cx, cy = self.image_matcher.find_template(
                roi,
                template,
                mask=mask,
                threshold=threshold,
                template_name=f"{template_name}-verify",
            )
            if not found:
                continue

            abs_x = cx + x1
            abs_y = cy + y1
            if (
                abs(abs_x - x) <= config.RED_ICON_VERIFY_TOLERANCE
                and abs(abs_y - y) <= config.RED_ICON_VERIFY_TOLERANCE
                and self._passes_red_icon_template_gate(
                    target_screenshot,
                    abs_x,
                    abs_y,
                    template_name,
                    template,
                    mask,
                    relaxed=relaxed_color,
                )[0]
            ):
                return True

        return False

    def _passes_red_color_gate(self, screenshot, x, y, relaxed=False):
        """
        Strict dual-gate whitelist verification.
        Gate 1 (Pixel Density): Counts dilated red pixels in ROI - must meet minimum.
        Gate 2 (Masked Channel Dominance): Evaluates only the HSV-masked red pixels so
        background pixels cannot dilute a valid icon.
        Both gates must pass (AND logic). Either failure discards the candidate.
        Returns: (passed, pixel_count)
        """
        show_mask = config.DEBUG_VISION
        metrics = self.image_matcher.analyze_red_region(
            screenshot,
            x,
            y,
            size=config.RED_ICON_COLOR_SAMPLE_SIZE,
            show_mask=show_mask,
        )
        pixel_count = metrics["pixel_count"]

        threshold = config.RED_ICON_PIXEL_THRESHOLD
        min_ratio = config.RED_ICON_COLOR_MIN_RATIO
        max_ratio = config.RED_ICON_COLOR_MAX_RATIO
        min_mean = config.RED_ICON_COLOR_MIN_MEAN
        if relaxed:
            threshold = max(1, int(round(threshold * 0.8)))
            min_ratio *= 0.92
            max_ratio *= 1.08
            min_mean *= 0.9

        if pixel_count < threshold:
            return False, pixel_count

        if metrics["red_ratio"] < min_ratio or metrics["red_ratio"] > max_ratio or metrics["red_mean"] < min_mean:
            logger.debug(
                "[RedGate] Masked dominance rejected candidate at (%s, %s) px=%d ratio=%.3f mean=%.1f",
                x,
                y,
                pixel_count,
                metrics["red_ratio"],
                metrics["red_mean"],
            )
            return False, pixel_count

        return True, pixel_count

    def _segregate_assets(self, detections):
        """
        Action Step 1 & 4: Segregate detections and pad execution delays.
        Categorizes coordinates into safe_assets and forbidden_assets.
        'Slow is Smooth, Smooth is Fast' - Deliberately sort coordinates before action.
        """
        # Segregation is pure computation — no sleep needed (MAJ-004 fix)
            
        safe_assets = []
        forbidden_assets = []
        
        for det in detections:
            # det is assumed to be (confidence, x, y, ...)
            if len(det) < 3:
                continue
            conf, x, y = det[:3]
            
            # Action Step 1: Segregate Detections immediately upon scanning
            if self.mouse_controller.is_in_forbidden_zone(x, y, relative=True):
                forbidden_assets.append(det)
            else:
                safe_assets.append(det)
                
        # Return distinct arrays
        return safe_assets, forbidden_assets

    def _filter_forbidden_red_icons(self, red_icons):
        """
        Coordinate Blackout Implementation.
        1. Segregates icons into safe/forbidden.
        2. Adds forbidden icons to a world-coordinate blackout cache.
        3. Filters 'safe' icons against the blackout cache to prevent immediate re-detection.
        """
        now = time.monotonic()
        ttl = float(config.FORBIDDEN_BLACKOUT_DURATION)
        radius = int(config.RED_ICON_STABILITY_RADIUS)
        
        # Purge expired blackout entries
        self._forbidden_blackout_cache = {
            coord: expiry for coord, expiry in self._forbidden_blackout_cache.items()
            if expiry > now
        }
        
        # 1. Primary Segregation (Forbidden Zone Check)
        safe_icons, forbidden_icons = self._segregate_assets(red_icons)
        
        # Calculate current world offset (pixels)
        # We assume scroll_offset_units is tracked correctly by searcher
        scroll_y = int(self.scroll_offset_units * config.SCROLL_PIXEL_STEP)

        # 2. Update Blackout Cache with new forbidden icons
        for icon in forbidden_icons:
            _, sx, sy = icon[:3]
            self._add_to_blackout(sx, sy)
            
        # 3. Filter Safe Icons against Blackout Cache
        # This prevents "Immediate trigger" from re-detecting the same icon we just blacklisted
        final_safe_icons = []
        for icon in safe_icons:
            _, sx, sy = icon[:3]
            wx, wy = sx, sy + scroll_y
            
            is_blacklisted = False
            for (bx, by), expiry in self._forbidden_blackout_cache.items():
                # Distance check in World Space
                if abs(bx - wx) <= radius and abs(by - wy) <= radius:
                    is_blacklisted = True
                    break
            
            if not is_blacklisted:
                final_safe_icons.append(icon)
            else:
                logger.debug(f"[Blackout] Active: Ignoring icon at world-coord ({wx}, {wy})")
                
        return final_safe_icons, len(forbidden_icons)

    def _prioritize_red_icons(self, red_icons):
        def get_priority(icon):
            conf, x, y = icon[:3]
            for success_y in self.successful_red_icon_positions:
                if abs(y - success_y) < 50:
                    return (0, y)
            return (1, y)

        red_icons.sort(key=get_priority)

        max_per_scan = max(1, int(config.RED_ICON_MAX_PER_SCAN))
        if len(red_icons) > max_per_scan:
            logger.debug(
                "Red icon queue limited from %s to %s for single-target interaction safety",
                len(red_icons),
                max_per_scan,
            )
            red_icons = red_icons[:max_per_scan]

        return red_icons

    def check_priority_targets(self):
        """STEP A: Priority Scan. Checks for Red Icons and Level Transitions."""
        self.check_critical_interrupts()
        screenshot = self._capture(max_y=config.MAX_SEARCH_Y, force=True)
        
        # 1. Check for Level Transition
        if self._should_interrupt_for_new_level(screenshot=screenshot, force=True):
            return State.CHECK_NEW_LEVEL

        # 2. Check for Red Icons
        red_icons = self._detect_red_icons_in_view(screenshot, max_y=config.MAX_SEARCH_Y)
        # Apply Temporal Consistency Check (Debouncing)
        red_icons = self._stable_red_icons(red_icons)
        
        if red_icons:
            filtered, _ = self._filter_forbidden_red_icons(red_icons)
            if filtered:
                self.red_icons = self._prioritize_red_icons(filtered)
                self.current_red_icon_index = 0
                self.red_icon_cycle_count = 0
                self.work_done = True
                # Return 'RED_ICON_FOUND' status (State.CLICK_RED_ICON)
                return State.CLICK_RED_ICON
        return None

    def check_intra_scroll_red_interrupt(self):
        """
        Targeted intra-loop red icon interrupt scan.
        Runs between individual scroll intervals and hard-interrupts to CLICK_RED_ICON
        as soon as a safe actionable icon is detected.
        """
        self.check_critical_interrupts()
        screenshot = self._capture(max_y=config.MAX_SEARCH_Y, force=False)
        # IMPORTANT: Do not run temporal debouncing here.
        # _stable_red_icons mutates shared history and would "prime" the cache before
        # the main priority pass in the same interval.
        red_icons = self._detect_red_icons_in_view(screenshot, max_y=config.MAX_SEARCH_Y)

        if not red_icons:
            return None

        # ACTION STEP: Filter for safety BEFORE prioritizing/truncating
        safe_icons, _ = self._filter_forbidden_red_icons(red_icons)
        if not safe_icons:
            return None

        prioritized_icons = self._prioritize_red_icons(safe_icons)
        actionable_icons = []
        for confidence, x, y, *_ in prioritized_icons:
            # Re-verify specific click point (center + offset)
            click_x = x + config.RED_ICON_OFFSET_X
            click_y = y + config.RED_ICON_OFFSET_Y

            if self.mouse_controller.is_in_forbidden_zone(click_x, click_y):
                continue

            if not self._is_red_icon_present_at(x, y, screenshot=screenshot):
                continue

            actionable_icons.append((confidence, x, y))

        if not actionable_icons:
            return None

        self.red_icons = actionable_icons
        self.current_red_icon_index = 0
        self.work_done = True
        logger.info(
            "[ScrollInterrupt] Safe red icon detected intra-loop at (%s, %s); aborting remaining swipes",
            actionable_icons[0][1],
            actionable_icons[0][2],
        )
        return State.CLICK_RED_ICON

    def check_main_success(self):
        """STEP B: Main Target Scan. Reserved for specific success conditions."""
        self.check_critical_interrupts()
        # In current context, Red Icons are the primary success, handled by priority.
        return None

    def check_fallbacks(self):
        """STEP C: Fallback Scan. Clicks boxes and stations without returning success."""
        self.check_critical_interrupts()
        screenshot = self._capture(max_y=config.MAX_SEARCH_Y, force=True)
        clicked = self._scan_and_click_non_red_assets(screenshot)
        if clicked == -2:
            return State.CHECK_NEW_LEVEL
        if clicked == -1:
            return State.SCROLL
        return None

    def execute_oscillating_search(self):
        direction = 1 if self._oscillation_leg_direction > 0 else -1
        direction_label = "DOWN" if direction > 0 else "UP"
        cycle_index = self._oscillation_cycle_index
        step_target = self._current_oscillation_leg_target_steps()
        step_index = self._oscillation_leg_progress + 1

        logger.info(
            "[ScrollStep] Cycle %s %s step %s/%s",
            cycle_index,
            direction_label,
            step_index,
            step_target,
        )

        motion_ok = self.searcher.perform_scroll(
            direction=direction,
            distance_ratio=config.SCROLL_DISTANCE_RATIO,
            duration=config.SCROLL_DURATION,
        )
        if not motion_ok:
            if self._should_interrupt_for_new_level(max_y=config.MAX_SEARCH_Y, force=True):
                return State.CHECK_NEW_LEVEL
            logger.warning("[ScrollStep] Motion aborted; returning to FIND_RED_ICONS")
            return State.FIND_RED_ICONS

        if self._sleep_with_interrupt(config.POST_SCROLL_SETTLE):
            return State.CHECK_NEW_LEVEL

        if self._sleep_with_interrupt(config.SCROLL_INTERVAL_PAUSE):
            return State.CHECK_NEW_LEVEL

        leg_completed, cycle_completed, _ = self._advance_oscillation_progress()
        if leg_completed and config.CYCLE_PAUSE_DURATION > 0:
            if self._sleep_with_interrupt(config.CYCLE_PAUSE_DURATION):
                return State.CHECK_NEW_LEVEL
        if cycle_completed and config.OSCILLATION_CYCLE_COOLDOWN > 0:
            if self._sleep_with_interrupt(config.OSCILLATION_CYCLE_COOLDOWN):
                return State.CHECK_NEW_LEVEL

        self._scroll_break_sequence_pending = True
        return State.CHECK_NEW_LEVEL


    def load_templates(self):
        required_templates = self._required_template_names()
        scanner = AssetScanner(self.image_matcher)
        return scanner.scan(config.ASSETS_DIR, required_templates=required_templates)

    def _scan_and_click_non_red_assets(self, screenshot):
        """
        Action Step 2 & 3: Implement Priority and Fallback logic for non-red assets.
        Ensures Upgrade Stations and Boxes are handled with safe-zone prioritization.
        """
        clicked_targets = 0
        clicked_upgrade_station = False
        clicked_box = False

        # 1. Upgrade Station Handling
        upgrade_template = self.templates.get("upgradeStation")
        if upgrade_template is not None:
            template, mask = upgrade_template
            upgrade_threshold = (
                self.vision_optimizer.upgrade_station_threshold
                if self.vision_optimizer.enabled
                else config.UPGRADE_STATION_THRESHOLD
            )
            
            # Action Step 1: Segregate Detections immediately
            all_stations_raw = self.image_matcher.find_all_templates(
                screenshot,
                template,
                mask=mask,
                threshold=upgrade_threshold,
                template_name="upgradeStation-all"
            )

            # Whitelist Filter: mandatory color histogram gate.
            # Shape match alone is insufficient — the color distribution of the
            # matched region must also correlate with the template.
            # This rejects background textures that happen to match the silhouette.
            h_t, w_t = template.shape[:2]
            all_stations = []
            for cand_conf, cand_x, cand_y in all_stations_raw:
                # HSV pre-filter: reject candidates without enough cyan pixels
                if not self.image_matcher.check_upgrade_station_hsv(
                    screenshot, cand_x, cand_y, h_t, w_t
                ):
                    logger.debug(
                        "[UpgradeStation] HSV gate rejected candidate at (%s, %s) conf=%.2f",
                        cand_x, cand_y, cand_conf,
                    )
                    continue
                x1 = max(0, cand_x - w_t // 2)
                y1 = max(0, cand_y - h_t // 2)
                roi_slice = screenshot[y1:y1 + h_t, x1:x1 + w_t]
                if roi_slice.shape[:2] == (h_t, w_t):
                    color_ok = self.image_matcher._check_color_similarity(
                        screenshot, template, (x1, y1), mask
                    )
                    if not color_ok:
                        logger.debug(
                            "[UpgradeStation] Color gate rejected candidate at (%s, %s) conf=%.2f",
                            cand_x, cand_y, cand_conf,
                        )
                        continue
                all_stations.append((cand_conf, cand_x, cand_y))
            
            safe_stations, forbidden_stations = self._segregate_assets(all_stations)
            
            # Condition 2 (The Priority): IF safe assets exist, click them.
            if safe_stations:
                safe_stations.sort(key=lambda s: s[0], reverse=True)
                for conf, x, y in safe_stations:
                    is_safe = self._is_asset_click_safe("Upgrade Station", x, y)
                    if is_safe is None:
                        return -2
                    if is_safe:
                        logger.info("Fallback scan: clicking safe upgrade station at (%s, %s) [%.2f%%]", x, y, conf * 100)
                        if self.mouse_controller.click(x, y, relative=True):
                            clicked_targets += 1
                            clicked_upgrade_station = True
                            self.upgrade_found_in_cycle = True
                            self.vision_optimizer.update_upgrade_station_confidence(conf)
                            break # Prioritize one station per pass
            # Condition 1 (The Fallback): IF ONLY forbidden assets detected -> Scroll
            elif forbidden_stations:
                logger.warning("Fallback scan: ONLY forbidden upgrade stations detected; triggering Oscillating Search")
                self.vision_optimizer.update_upgrade_station_miss()
                if self._uninterrupted_main_flow_enabled():
                    logger.info("Fallback scan: preserving main flow and skipping forced scroll redirect for forbidden upgrade station")
                elif self._redirect_forbidden_asset_to_scroll("Upgrade Station", forbidden_stations[0][1], forbidden_stations[0][2]):
                    return -1
            else:
                self.vision_optimizer.update_upgrade_station_miss()

        # 2. Box Handling
        all_boxes = []
        for box_name in ("box1", "box2", "box3", "box4", "box5"):
            box_template = self.templates.get(box_name)
            if box_template is None:
                continue

            template, mask = box_template
            box_threshold = (
                self.vision_optimizer.box_threshold
                if self.vision_optimizer.enabled
                else config.BOX_THRESHOLD
            )
            found_boxes_raw = self.image_matcher.find_all_templates(
                screenshot,
                template,
                mask=mask,
                threshold=box_threshold,
                template_name=box_name
            )

            # Whitelist Filter: mandatory color histogram gate for boxes.
            # Boxes have distinctive color palettes — reject background matches
            # whose color distribution doesn't correlate with the template.
            h_t, w_t = template.shape[:2]
            for b_conf, b_x, b_y in found_boxes_raw:
                x1 = max(0, b_x - w_t // 2)
                y1 = max(0, b_y - h_t // 2)
                roi_slice = screenshot[y1:y1 + h_t, x1:x1 + w_t]
                if roi_slice.shape[:2] == (h_t, w_t):
                    box_color_ok = self.image_matcher._check_color_similarity(
                        screenshot, template, (x1, y1), mask
                    )
                    if not box_color_ok:
                        logger.debug(
                            "[Box] Color gate rejected %s at (%s, %s) conf=%.2f",
                            box_name, b_x, b_y, b_conf,
                        )
                        continue
                all_boxes.append((b_conf, b_x, b_y, box_name))

        if all_boxes:
            safe_boxes, forbidden_boxes = self._segregate_assets(all_boxes)
            
            if safe_boxes:
                safe_boxes.sort(key=lambda b: b[0], reverse=True)
                for conf, x, y, name in safe_boxes:
                    logger.info("Fallback scan: clicking safe %s at (%s, %s) [%.2f%%]", name, x, y, conf * 100)
                    if self.mouse_controller.click(x, y, relative=True):
                        clicked_targets += 1
                        clicked_box = True
                        self.vision_optimizer.update_box_confidence(conf)
            elif forbidden_boxes:
                logger.debug("Fallback scan: boxes only in forbidden zone, ignoring.")

        if clicked_targets > 0:
            if self._no_icon_scroll_interrupt_enabled():
                self._no_red_scroll_cycle_pending = True
                logger.info(
                    "Fallback scan summary: clicked %s target(s) [upgrade_station=%s, boxes=%s]; scheduling no-red scroll cycle",
                    clicked_targets,
                    clicked_upgrade_station,
                    clicked_box,
                )
            else:
                self._no_red_scroll_cycle_pending = False
                logger.info(
                    "Fallback scan summary: clicked %s target(s) [upgrade_station=%s, boxes=%s]",
                    clicked_targets,
                    clicked_upgrade_station,
                    clicked_box,
                )

        return clicked_targets


    def _iter_red_icon_templates(self):
        if not self.available_red_icon_templates:
            return []

        if not self._red_template_priority:
            return self.available_red_icon_templates

        by_name = {name: (name, template, mask) for name, template, mask in self.available_red_icon_templates}
        ordered = []
        seen = set()

        for template_name in self._red_template_priority:
            item = by_name.get(template_name)
            if item is None:
                continue
            ordered.append(item)
            seen.add(template_name)

        for item in self.available_red_icon_templates:
            if item[0] in seen:
                continue
            ordered.append(item)

        return ordered

    def _update_red_template_priority(self, hit_counts):
        if not hit_counts:
            return

        now = time.monotonic()
        for template_name, count in hit_counts.items():
            self._red_template_hit_counts[template_name] = self._red_template_hit_counts.get(template_name, 0) + count
            self._red_template_last_seen[template_name] = now

        decay_window = max(1.0, float(config.RED_ICON_STABILITY_CACHE_TTL))
        scored = []
        for name, count in self._red_template_hit_counts.items():
            last_seen = self._red_template_last_seen.get(name, now)
            age = max(0.0, now - last_seen)
            freshness = max(0.1, 1.0 - min(1.0, age / decay_window))
            score = count * freshness
            scored.append((name, score))

        scored.sort(key=lambda item: item[1], reverse=True)
        limit = max(1, config.RED_ICON_PRIORITY_TEMPLATE_LIMIT)
        self._red_template_priority = [name for name, _ in scored[:limit]]

    def _build_available_red_icon_templates(self):
        available = []
        for template_name in self.red_icon_templates:
            if template_name in self.templates:
                template, mask = self.templates[template_name]
                available.append((template_name, template, mask))
        return available

    def _build_red_template_signatures(self):
        signatures = {}
        for template_name, template, mask in self.available_red_icon_templates:
            signatures[template_name] = self.image_matcher.build_red_template_signature(
                template,
                mask=mask,
            )
        return signatures

    def _passes_red_icon_template_gate(self, screenshot, x, y, template_name, template, mask, relaxed=False):
        if not config.RED_ICON_TEMPLATE_VERIFY:
            return True, {}

        signature = getattr(self, "_red_template_signatures", {}).get(template_name)
        if signature is None:
            signature = self.image_matcher.build_red_template_signature(template, mask=mask)

        metrics = self.image_matcher.analyze_red_template_candidate(
            screenshot,
            x,
            y,
            template,
            mask=mask,
            signature=signature,
            max_offset=config.RED_ICON_TEMPLATE_VERIFY_MAX_OFFSET,
        )

        min_coverage = float(config.RED_ICON_TEMPLATE_MIN_COVERAGE)
        min_precision = float(config.RED_ICON_TEMPLATE_MIN_PRECISION)
        min_recall = float(config.RED_ICON_TEMPLATE_MIN_RECALL)
        min_iou = float(config.RED_ICON_TEMPLATE_MIN_IOU)
        min_color_similarity = float(config.RED_ICON_TEMPLATE_COLOR_SIMILARITY)
        if relaxed:
            min_coverage *= 0.9
            min_precision *= 0.95
            min_recall *= 0.95
            min_iou *= 0.9
            min_color_similarity *= 0.95

        passed = (
            metrics["coverage"] >= min_coverage
            and metrics["precision"] >= min_precision
            and metrics["recall"] >= min_recall
            and metrics["iou"] >= min_iou
            and metrics["color_similarity"] >= min_color_similarity
        )
        if not passed:
            logger.debug(
                "[RedTemplateGate] Rejected %s at (%s, %s): coverage=%.3f precision=%.3f recall=%.3f iou=%.3f color=%.3f",
                template_name,
                x,
                y,
                metrics["coverage"],
                metrics["precision"],
                metrics["recall"],
                metrics["iou"],
                metrics["color_similarity"],
            )
        return passed, metrics

    def get_runtime_behavior_snapshot(self):
        return {
            "click_delay": float(self.tuner.click_delay),
            "move_delay": float(self.tuner.move_delay),
            "upgrade_click_interval": float(self.tuner.upgrade_click_interval),
            "search_interval": float(self.tuner.search_interval),
        }

    def apply_learned_behavior(self, learned, reason="historical", best_time=0.0):
        if not learned:
            return
        self.tuner.click_delay = float(learned.get("click_delay", self.tuner.click_delay))
        self.tuner.move_delay = float(learned.get("move_delay", self.tuner.move_delay))
        self.tuner.upgrade_click_interval = float(
            learned.get("upgrade_click_interval", self.tuner.upgrade_click_interval)
        )
        self.tuner.search_interval = float(learned.get("search_interval", self.tuner.search_interval))
        logger.info(
            "Historical learner (%s) applied timing profile from best %.2fs run",
            reason,
            best_time,
        )
        self._apply_tuning()

    def _required_template_names(self):
        box_names = [f"box{i}" for i in range(1, 6)]
        required = set(self.red_icon_templates)
        required.update(["newLevel", "unlock", "upgradeStation"])
        required.update(box_names)
        return required
    
    def wipe_memory(self):
        logger.info("Wiping AI memory...")
        
        try:
            self.tuner.reset()
        except Exception as e:
            logger.error(f"Failed to reset AdaptiveTuner: {e}")
            
        try:
            self.vision_optimizer.reset()
        except Exception as e:
            logger.error(f"Failed to reset VisionOptimizer: {e}")
            
        try:
            self.historical_learner.reset()
        except Exception as e:
            logger.error(f"Failed to reset HistoricalLearner: {e}")
        
        self._red_template_hit_counts = {}
        self._red_template_priority = []
        self._red_template_last_seen = {}
        self._recent_red_icon_history = []
        self._reset_search_cycle(reason="wipe_memory")
        
        # Apply the defaults back to mouse controller
        self._apply_tuning()
        
        logger.info("AI memory wiped successfully. Bot starting fresh.")
    
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
    
    def handle_find_red_icons(self, current_state):
        """
        Refactored: Scenario-Based Action Layer.
        Implements clean Scenario A/B/C branching using Guard Clauses.
        """
        self.check_critical_interrupts()
        self._click_idle()

        # Step 1: Discovery pipeline with debounced zone-state arbitration.
        zone_state = self._resolve_red_icon_zone_state()
        safe_present = zone_state["safe_present"]
        forbidden_present = zone_state["forbidden_present"]
        actionable_icons = zone_state["actionable_icons"]

        logger.info(
            "Red icon zone-state matrix => safe=%s forbidden=%s (safe_icons=%s forbidden_icons=%s)",
            int(safe_present),
            int(forbidden_present),
            len(actionable_icons),
            zone_state["forbidden_count"],
        )

        # 4-state logic matrix:
        # 1) safe=1, forbidden=1 => proceed to main loop cycle
        # 2) safe=0, forbidden=1 => oscillating scroll cycle
        # 3) safe=1, forbidden=0 => proceed to main loop cycle
        # 4) safe=0, forbidden=0 => proceed to main loop cycle
        if safe_present:
            logger.info("✓ %s valid targets in safe zone.", len(actionable_icons))
            self.red_icons = self._prioritize_red_icons(actionable_icons)
            self.current_red_icon_index = 0
            self.red_icon_cycle_count = 0
            self.work_done = True
            return State.CLICK_RED_ICON

        if forbidden_present:
            now = time.monotonic()
            cooldown = max(0.0, float(config.FORBIDDEN_ZONE_SCROLL_REENTRY_COOLDOWN))
            wait_remaining = (self._last_forbidden_scroll_time + cooldown) - now
            if wait_remaining > 0:
                if self._uninterrupted_main_flow_enabled():
                    logger.debug(
                        "Forbidden-only state detected; skipping scroll reentry cooldown %.3fs to preserve main flow",
                        wait_remaining,
                    )
                else:
                    logger.debug(
                        "Forbidden-only state detected; applying scroll reentry cooldown %.3fs",
                        wait_remaining,
                    )
                    self._sleep_with_interrupt(wait_remaining)
            self._last_forbidden_scroll_time = time.monotonic()
            logger.warning(
                "⚠ %s targets currently inside Forbidden Zone with no safe counterpart. "
                "Switching to oscillating search cycle.",
                zone_state["forbidden_count"],
            )
            return State.SCROLL

        fallback_state = self.check_fallbacks()
        if fallback_state is not None:
            logger.info("Fallback scan triggered state redirect to: %s", fallback_state)
            return fallback_state
        logger.info("No targets detected; initiating exploration.")
        return State.SCROLL

    def _collect_red_icon_zone_snapshot(self):
        """Collect a single red-icon snapshot and split safe/forbidden detections."""
        screenshot = self._capture(max_y=config.EXTENDED_SEARCH_Y, force=True)
        raw_icons = self._detect_red_icons_in_view(screenshot, max_y=config.MAX_SEARCH_Y)
        stable_icons = self._stable_red_icons(raw_icons)
        safe_icons, forbidden_count = self._filter_forbidden_red_icons(stable_icons)
        return {
            "safe_icons": safe_icons,
            "safe_count": len(safe_icons),
            "forbidden_count": forbidden_count,
            "safe_present": len(safe_icons) > 0,
            "forbidden_present": forbidden_count > 0,
        }

    def _resolve_red_icon_zone_state(self):
        """Debounced 4-state arbitration for safe-vs-forbidden red icon handling."""
        pre_delay = max(0.0, float(config.FORBIDDEN_ZONE_DETECTION_PRE_DELAY))
        post_delay = max(0.0, float(config.FORBIDDEN_ZONE_DETECTION_POST_DELAY))
        ticks = max(1, int(config.FORBIDDEN_ZONE_DEBOUNCE_TICKS))
        required_consensus = max(
            1,
            min(
                ticks,
                int(config.FORBIDDEN_ZONE_DEBOUNCE_REQUIRED_CONSENSUS),
            ),
        )

        if pre_delay > 0:
            self._sleep_with_interrupt(pre_delay)

        snapshots = []
        state_hits = {}
        chosen = None
        for idx in range(ticks):
            snapshot = self._collect_red_icon_zone_snapshot()
            snapshots.append(snapshot)
            state_key = (snapshot["safe_present"], snapshot["forbidden_present"])
            state_hits[state_key] = state_hits.get(state_key, 0) + 1

            if state_hits[state_key] >= required_consensus:
                chosen = snapshot
                break

            if idx < ticks - 1 and post_delay > 0:
                self._sleep_with_interrupt(post_delay)

        if chosen is None:
            chosen = snapshots[-1] if snapshots else {
                "safe_icons": [],
                "safe_count": 0,
                "forbidden_count": 0,
                "safe_present": False,
                "forbidden_present": False,
            }

        logger.debug(
            "Forbidden-zone debounce completed: ticks=%s required=%s states=%s chosen=(safe=%s forbidden=%s)",
            len(snapshots),
            required_consensus,
            {f"{int(k[0])}/{int(k[1])}": v for k, v in state_hits.items()},
            int(chosen["safe_present"]),
            int(chosen["forbidden_present"]),
        )

        return {
            "safe_present": chosen["safe_present"],
            "forbidden_present": chosen["forbidden_present"],
            "actionable_icons": chosen["safe_icons"],
            "forbidden_count": chosen["forbidden_count"],
        }
    
    def handle_click_red_icon(self, current_state):
        self.check_critical_interrupts()
        if self.current_red_icon_index >= len(self.red_icons):
            logger.info("All red icons processed, continuing cycle")
            return State.CHECK_UNLOCK
        
        confidence, x, y = self.red_icons[self.current_red_icon_index]
        limited_screenshot = self._capture(max_y=config.MAX_SEARCH_Y, force=True)
        
        # Calculate relaxed threshold for verification (matching search cycle logic)
        base_threshold = (
            self.vision_optimizer.red_icon_threshold
            if self.vision_optimizer.enabled
            else config.RED_ICON_THRESHOLD
        )
        relaxed_threshold = max(0.0, base_threshold - 0.04) # Match SCROLL_RED_ICON_THRESHOLD_DROP approx
        
        if not self._is_red_icon_present_at(
            x,
            y,
            screenshot=limited_screenshot,
            threshold_override=relaxed_threshold,
            relaxed_color=True,
        ):
            logger.info(
                "Red icon no longer present at (%s, %s); skipping click",
                x,
                y,
            )
            self.current_red_icon_index += 1
            if self.current_red_icon_index < len(self.red_icons):
                return State.CLICK_RED_ICON
            return State.CHECK_UNLOCK

        refined_pos, refined, refined_conf = self._refine_red_icon_position(
            x,
            y,
            screenshot=limited_screenshot,
        )
        if refined:
            x, y = refined_pos
            self.vision_optimizer.update_red_icon_confidences([refined_conf])

        click_x = x + config.RED_ICON_OFFSET_X
        click_y = y + config.RED_ICON_OFFSET_Y
        
        is_safe = self._is_asset_click_safe("Red Icon", click_x, click_y)
        if is_safe is None:
            return State.CHECK_NEW_LEVEL
        if not is_safe:
            logger.warning(f"Red icon click blocked - position with offset ({click_x}, {click_y}) is in forbidden zone")
            self._add_to_blackout(x, y) # Blacklist the original detection point
            if self._uninterrupted_main_flow_enabled():
                return self._advance_after_blocked_red_icon(
                    f"Red icon blocked by forbidden zone at ({click_x}, {click_y}); skipping to preserve main flow"
                )
            if self._redirect_forbidden_asset_to_scroll("Red Icon", click_x, click_y):
                return State.SCROLL
            
            if self._new_level_event.is_set():
                return State.CHECK_NEW_LEVEL
                
            self.current_red_icon_index += 1
            return State.CLICK_RED_ICON if self.current_red_icon_index < len(self.red_icons) else State.CHECK_UNLOCK
        
        logger.info(f"Clicking red icon {self.current_red_icon_index + 1}/{len(self.red_icons)} at ({click_x}, {click_y})")
        click_success = self.mouse_controller.click(click_x, click_y, relative=True)
        self.tuner.record_click_result(click_success)
        self._apply_tuning()

        if not click_success:
            if self.mouse_controller.is_in_forbidden_zone(click_x, click_y):
                logger.warning(
                    "Red icon click canceled by strict pre-click validator at (%s, %s); redirecting to oscillating search",
                    click_x,
                    click_y,
                )
                if self._uninterrupted_main_flow_enabled():
                    self._add_to_blackout(x, y)
                    return self._advance_after_blocked_red_icon(
                        f"Red icon click canceled at ({click_x}, {click_y}); skipping blocked action to preserve main flow"
                    )
                if self._redirect_forbidden_asset_to_scroll("Red Icon", click_x, click_y):
                    return State.SCROLL

            self.current_red_icon_index += 1
            return State.CLICK_RED_ICON if self.current_red_icon_index < len(self.red_icons) else State.CHECK_UNLOCK
        
        self.red_icon_cycle_count = 0
        return State.CHECK_UNLOCK
    
    def handle_check_unlock(self, current_state):
        self.check_critical_interrupts()
        limited_screenshot = self._capture(max_y=config.MAX_SEARCH_Y)
        
        clicked_unlock = False
        if "unlock" in self.templates:
            template, mask = self.templates["unlock"]
            found, confidence, x, y = self.image_matcher.find_template(
                limited_screenshot, template, mask=mask,
                threshold=config.UNLOCK_THRESHOLD, template_name="unlock"
            )
            
            if found:
                if self.mouse_controller.is_in_forbidden_zone(x, y):
                    logger.warning("Unlock button in forbidden zone, skipping")
                else:
                    logger.info("Unlock found, clicking")
                    clicked_unlock = self.mouse_controller.click(x, y, relative=True)

        if clicked_unlock:
            if self._sleep_with_interrupt(config.STATE_DELAY):
                return State.CHECK_NEW_LEVEL
            return State.SEARCH_UPGRADE_STATION

        return State.SEARCH_UPGRADE_STATION
    
    def handle_search_upgrade_station(self, current_state):
        self.check_critical_interrupts()
        max_attempts = config.UPGRADE_STATION_SEARCH_MAX_ATTEMPTS
        base_threshold = (
            self.vision_optimizer.upgrade_station_threshold
            if self.vision_optimizer.enabled
            else config.UPGRADE_STATION_THRESHOLD
        )
        relaxed_threshold = base_threshold - config.UPGRADE_STATION_RELAXED_THRESHOLD_DROP
        retry_delay = self.tuner.search_interval
        
        for attempt in range(max_attempts):
            limited_screenshot = self._capture(max_y=config.MAX_SEARCH_Y)
            
            if "upgradeStation" in self.templates:
                template, mask = self.templates["upgradeStation"]
                
                current_threshold = base_threshold if attempt < config.UPGRADE_STATION_RELAXED_ATTEMPT_TRIGGER else relaxed_threshold
                
                found, confidence, x, y = self.image_matcher.find_template(
                    limited_screenshot, template, mask=mask,
                    threshold=current_threshold, template_name="upgradeStation"
                )
                
                if found:
                    # HSV pre-filter: reject candidates without enough cyan pixels
                    if not self.image_matcher.check_upgrade_station_hsv(
                        limited_screenshot, x, y, template.shape[0], template.shape[1]
                    ):
                        logger.debug(
                            "handle_search_upgrade_station: HSV gate rejected at (%s, %s) conf=%.2f",
                            x, y, confidence,
                        )
                        continue
                    # Gap 3 fix: strict forbidden zone guard immediately after detection.
                    # Without this, a forbidden station passes through refine + confidence
                    # update before being blocked by handle_hold_upgrade_station, which:
                    #   (a) wastes a full handler cycle, and
                    #   (b) biases the VisionOptimizer with update_upgrade_station_confidence()
                    #       for a coordinate that will ultimately never be clicked.
                    # Reject here, record an honest miss, and redirect to oscillating search.
                    if self.mouse_controller.is_in_forbidden_zone(x, y, relative=True):
                        logger.warning(
                            "handle_search_upgrade_station: station at (%s, %s) is inside "
                            "forbidden zone — rejecting immediately, triggering Oscillating Search.",
                            x, y,
                        )
                        self.vision_optimizer.update_upgrade_station_miss()
                        self.tuner.record_search_result(False)
                        self._apply_tuning()
                        return self._advance_after_blocked_station(
                            f"Upgrade station at ({x}, {y}) blocked by forbidden zone during search; advancing main loop"
                        )

                    logger.info(f"✓ Upgrade station found (attempt {attempt + 1})")
                    refined_pos, refined = self._refine_template_position(
                        "upgradeStation",
                        (x, y),
                        config.UPGRADE_STATION_REFINE_RADIUS,
                        screenshot=limited_screenshot,
                        threshold=current_threshold,
                        check_color=config.UPGRADE_STATION_COLOR_CHECK,
                    )
                    self.upgrade_station_pos = refined_pos
                    if refined:
                        logger.debug(
                            "Refined upgrade station position: (%s, %s) -> (%s, %s)",
                            x,
                            y,
                            refined_pos[0],
                            refined_pos[1],
                        )
                    self.vision_optimizer.update_upgrade_station_confidence(confidence)
                    
                    if self.current_red_icon_index < len(self.red_icons):
                        _, _, red_y = self.red_icons[self.current_red_icon_index]
                        if red_y not in self.successful_red_icon_positions:
                            self.successful_red_icon_positions.append(red_y)
                    
                    self.upgrade_found_in_cycle = True
                    self.consecutive_failed_cycles = 0
                    self._last_upgrade_station_pos = self.upgrade_station_pos
                    self.tuner.record_search_result(True)
                    self._apply_tuning()
                    return State.HOLD_UPGRADE_STATION
            
            if attempt < max_attempts - 1:
                if retry_delay > 0 and self._sleep_with_interrupt(retry_delay):
                    return State.CHECK_NEW_LEVEL
        
        logger.info(f"✗ Upgrade station not found (failed cycles: {self.consecutive_failed_cycles + 1})")
        self.vision_optimizer.update_upgrade_station_miss()
        self.tuner.record_search_result(False)
        self._apply_tuning()
        self.red_icon_processed_count += 1
        self.consecutive_failed_cycles += 1
        self.current_red_icon_index += 1
        if self.current_red_icon_index < len(self.red_icons):
            logger.info("Trying next red icon after station search miss")
            return State.CLICK_RED_ICON
        return State.OPEN_BOXES
    
    def handle_hold_upgrade_station(self, current_state):
        self.check_critical_interrupts()
        base_pos = self.upgrade_station_pos
        limited_screenshot = self._capture(max_y=config.MAX_SEARCH_Y, force=True)
        hold_threshold = (
            self.vision_optimizer.upgrade_station_threshold
            if self.vision_optimizer.enabled
            else config.UPGRADE_STATION_THRESHOLD
        )
        refined_pos, refined = self._refine_template_position(
            "upgradeStation",
            base_pos,
            config.UPGRADE_STATION_REFINE_RADIUS,
            screenshot=limited_screenshot,
            threshold=hold_threshold,
            check_color=config.UPGRADE_STATION_COLOR_CHECK,
        )
        x, y = refined_pos
        if refined:
            self._last_upgrade_station_pos = refined_pos
            self.upgrade_station_pos = refined_pos
        elif self._last_upgrade_station_pos:
            last_x, last_y = self._last_upgrade_station_pos
            drift_limit = config.UPGRADE_STATION_REFINE_RADIUS * 2
            if abs(last_x - base_pos[0]) <= drift_limit and abs(last_y - base_pos[1]) <= drift_limit:
                x, y = self._last_upgrade_station_pos
                self.upgrade_station_pos = self._last_upgrade_station_pos

        click_refined_pos, click_refined = self._refine_upgrade_station_click_target(
            (x, y),
            screenshot=limited_screenshot,
            threshold=hold_threshold,
        )
        if click_refined:
            x, y = click_refined_pos
            self._last_upgrade_station_pos = click_refined_pos
            self.upgrade_station_pos = click_refined_pos

        is_safe = self._is_asset_click_safe("Upgrade Station", x, y)
        if is_safe is None:
            return State.CHECK_NEW_LEVEL
        if not is_safe:
            logger.warning("Upgrade station position is in forbidden zone; redirecting to oscillating search")
            return self._advance_after_blocked_station(
                f"Upgrade station at ({x}, {y}) blocked before spam-click; advancing main loop"
            )
        
        logger.info("Spam-clicking upgrade station...")

        start_time = time.monotonic()
        
        # Use spam-click instead of hold — rapid sequential left clicks
        # with interrupt awareness via the critical interrupt callback.
        spam_click_success = self.mouse_controller.spam_click_at(
            x, y,
            duration=config.SPAM_CLICK_DURATION,
            click_delay=config.SPAM_CLICK_DELAY,
            jitter=config.SPAM_CLICK_JITTER,
            relative=True,
            interrupt_check=lambda: self.check_critical_interrupts(raise_exception=False),
        )

        elapsed_time = time.monotonic() - start_time
        logger.info(f"Spam-clicking complete: duration {elapsed_time:.1f}s")

        if not spam_click_success:
            if self._should_interrupt_for_new_level(max_y=config.MAX_SEARCH_Y, force=True):
                return State.CHECK_NEW_LEVEL
            return self._advance_after_blocked_station(
                "Upgrade station rapid-click sequence aborted; advancing main loop"
            )
        
        self._click_idle()
        if config.IDLE_CLICK_SETTLE_DELAY > 0:
            if self._sleep_with_interrupt(config.IDLE_CLICK_SETTLE_DELAY):
                return State.CHECK_NEW_LEVEL
        
        self.red_icon_processed_count += 1
        self.current_red_icon_index += 1

        logger.info("✓ Upgrade station complete → Stats upgrade next")
        return State.UPGRADE_STATS
    
    def handle_upgrade_stats(self, current_state):
        self.check_critical_interrupts()
        logger.info("⬆ Stats upgrade starting")
        self._click_idle()
        
        extended_screenshot = self._capture(max_y=config.EXTENDED_SEARCH_Y)
        
        has_stats_icon, stats_confidence = self._has_stats_upgrade_icon(extended_screenshot)
        if not has_stats_icon:
            logger.info("✗ No stats icon, skipping")
            self.vision_optimizer.update_stats_upgrade_miss()
            return State.OPEN_BOXES

        self.vision_optimizer.update_stats_upgrade_confidence(stats_confidence)
        
        logger.info("✓ Stats icon found, upgrading")
        opened_menu = self.mouse_controller.click(
            config.STATS_UPGRADE_BUTTON_POS[0],
            config.STATS_UPGRADE_BUTTON_POS[1],
            relative=True,
        )
        if not opened_menu:
            if self._should_interrupt_for_new_level(max_y=config.MAX_SEARCH_Y, force=True):
                return State.CHECK_NEW_LEVEL
            logger.warning("Stats upgrade menu click failed; continuing without stat spam")
            return State.OPEN_BOXES

        self.sleep(config.STATE_DELAY)

        stats_click_success = self.mouse_controller.spam_click_at(
            config.STATS_UPGRADE_POS[0],
            config.STATS_UPGRADE_POS[1],
            duration=config.STATS_UPGRADE_CLICK_DURATION,
            click_delay=config.STATS_UPGRADE_CLICK_DELAY,
            jitter=0,
            relative=True,
            interrupt_check=lambda: self.check_critical_interrupts(raise_exception=False),
        )

        if not stats_click_success:
            if self._should_interrupt_for_new_level(max_y=config.MAX_SEARCH_Y, force=True):
                return State.CHECK_NEW_LEVEL
            logger.warning("Stats upgrade click burst aborted; continuing to box handling")
            return State.OPEN_BOXES

        self._click_idle()
        logger.info("========== STAT UPGRADE COMPLETED ==========")
        return State.OPEN_BOXES
    
    def handle_open_boxes(self, current_state):
        self.check_critical_interrupts()
        self._click_idle()
        
        limited_screenshot = self._capture(max_y=config.MAX_SEARCH_Y)

        if self._should_interrupt_for_new_level(
            screenshot=limited_screenshot,
            max_y=config.MAX_SEARCH_Y,
            force=True,
        ):
            logger.info("New level found during box opening, transitioning")
            return State.CHECK_NEW_LEVEL
        
        box_names = ["box1", "box2", "box3", "box4", "box5"]
        boxes_found = 0
        detected_box = False
        best_box_confidence = None
        
        for box_name in box_names:
            if box_name in self.templates:
                template, mask = self.templates[box_name]
                box_threshold = (
                    self.vision_optimizer.box_threshold
                    if self.vision_optimizer.enabled
                    else config.BOX_THRESHOLD
                )
                found, confidence, x, y = self.image_matcher.find_template(
                    limited_screenshot, template, mask=mask,
                    threshold=box_threshold, template_name=box_name
                )
                
                if found:
                    detected_box = True
                    if self.mouse_controller.is_in_forbidden_zone(x, y):
                        logger.debug(f"{box_name} in forbidden zone, skipping")
                    else:
                        if self.mouse_controller.click(x, y, relative=True):
                            boxes_found += 1
                            if best_box_confidence is None or confidence > best_box_confidence:
                                best_box_confidence = confidence

        if best_box_confidence is not None:
            self.vision_optimizer.update_box_confidence(best_box_confidence)
        elif not detected_box:
            self.vision_optimizer.update_box_miss()
        
        if self._should_interrupt_for_new_level(
            max_y=config.MAX_SEARCH_Y,
            force=True,
        ):
            logger.info("New level detected while opening boxes")
            return State.CHECK_NEW_LEVEL
        
        if boxes_found > 0:
            logger.info(f"🎁 Opened {boxes_found} boxes")
            self.work_done = True

        if self.upgrade_found_in_cycle:
            logger.info("✓ Upgrade found → continuing strict main-loop stage order")
            self.upgrade_found_in_cycle = False

        self.cycle_counter = 0
        if self.consecutive_failed_cycles >= 3:
            logger.info(f"⚠ {self.consecutive_failed_cycles} failed → continuing scroll sequence")
            self.consecutive_failed_cycles = 0

        return State.SCROLL
    
    def handle_scroll(self, current_state):
        self.check_critical_interrupts()
        self._click_idle()

        logger.info("Executing single-step oscillating scroll stage")
        return self.execute_oscillating_search()
    
    def handle_check_new_level(self, current_state):
        """
        Requirement: Robust Two-Step Verification for New Level.
        Eliminates false positives via a scroll-up check before execution.
        """
        if self._scroll_break_passthrough_active():
            logger.debug("Scroll break sequence: CHECK_NEW_LEVEL passthrough")
            return State.TRANSITION_LEVEL

        self._clear_new_level_interrupt()
        self._click_idle()
        logger.info(">>> VERIFICATION PHASE: New Level Trigger Detected")

        # 1. Verification Step: Scroll Down
        logger.info("Verification: Performing single scroll down to verify trigger")
        start_x, start_y = config.SCROLL_START_POS
        # Dragging from start_y to start_y - distance scrolls the CONTENT DOWN (finger moves up)
        drag_success = self.mouse_controller.drag(
            start_x, start_y,
            start_x, start_y - config.SCROLL_VERIFICATION_DISTANCE,
            duration=config.VERIFICATION_SCROLL_DURATION,
            relative=True,
            interrupt_check=lambda: self.check_critical_interrupts(raise_exception=False),
        )
        if not drag_success:
            if self._should_interrupt_for_new_level(max_y=config.MAX_SEARCH_Y, force=True):
                return State.CHECK_NEW_LEVEL
            return self._abort_transition("verification drag failed")
        # Settle after scroll
        if self._sleep_with_interrupt(config.POST_SCROLL_SETTLE):
            return State.CHECK_NEW_LEVEL

        # 2. Secondary Detection Check
        screenshot = self._capture(max_y=config.MAX_SEARCH_Y, force=True)
        priority_hit = self._detect_new_level_priority(screenshot=screenshot, force=True)
        
        if not priority_hit:
            logger.warning("Verification Failed: Secondary check was False. False positive aborted.")
            # Fallback to main loop
            self.completion_detected_time = None
            self.completion_detected_by = None
            return State.FIND_RED_ICONS

        found, confidence, x, y = priority_hit
        logger.info(f"Verification Success: Secondary check confirmed {found} [conf: {confidence:.2f}]")

        # 3. Transition Sequence (Strictly Chronological)
        # CRIT-003 fix: suppress interrupts during transition clicks to prevent
        # LevelCompleteInterrupt from firing mid-sequence and causing double-transitions.
        logger.info(">>> TRANSITION SEQUENCE: Executing strictly linear path")

        with self.suppress_interrupts():
            # Step 1: Acknowledge Level Completion
            logger.info("Step 1: Clicking new level button acknowledgment at %s", config.NEW_LEVEL_BUTTON_POS)
            if not self._click_transition_target(
                config.NEW_LEVEL_BUTTON_POS[0],
                config.NEW_LEVEL_BUTTON_POS[1],
                "New level acknowledgment",
            ):
                return self._abort_transition("acknowledgment click failed")
            if self._sleep_with_interrupt(config.NEW_LEVEL_BUTTON_DELAY):
                return State.CHECK_NEW_LEVEL

            # Step 2: Animation Buffer
            logger.info("Step 2: Animation Buffer (%ss)", config.TRANSITION_POST_CLICK_DELAY)
            if self._sleep_with_interrupt(config.TRANSITION_POST_CLICK_DELAY):
                return State.CHECK_NEW_LEVEL

            # Step 3: Confirm Travel
            if not self._execute_transition_travel_clicks():
                return self._abort_transition("travel confirmation click failed")

        # Step 4: Bookkeeping
        logger.info("Step 4: Executing transition bookkeeping")
        # _finalize_transition increments levels, resets scroll, clears progression, triggers records
        target_state = self._finalize_transition()

        # Step 5: Load Stabilization
        logger.info("Step 5: Load Stabilization (%ss)", config.NEW_LEVEL_FOLLOWUP_DELAY)
        if self._sleep_with_interrupt(config.NEW_LEVEL_FOLLOWUP_DELAY):
            return State.CHECK_NEW_LEVEL

        # 4. Hand back to specialized Hot Loop (WAIT_FOR_UNLOCK is returned by _finalize_transition)
        logger.info(">>> TRANSITION COMPLETE: Handing control to Hot Loop (WAIT_FOR_UNLOCK)")
        return target_state
    
    def handle_transition_level(self, current_state):
        if self._scroll_break_passthrough_active():
            logger.debug("Scroll break sequence: TRANSITION_LEVEL passthrough")
            return State.WAIT_FOR_UNLOCK

        self._click_idle()
        
        max_attempts = config.LEVEL_TRANSITION_MAX_ATTEMPTS
        
        # Check if we already marked completion recently (e.g. via override)
        if self.completion_detected_time and (datetime.now() - self.completion_detected_time).total_seconds() < config.LEVEL_COMPLETION_RECENCY_WINDOW:
            logger.info("Completion already marked recently; proceeding to transition bookkeeping")
            return self._finalize_transition()

        for attempt in range(max_attempts):
            limited_screenshot = self._capture(max_y=config.MAX_SEARCH_Y)

            found, confidence, x, y = self._detect_new_level(
                screenshot=limited_screenshot,
                max_y=config.MAX_SEARCH_Y,
            )
            if found:
                self._mark_restaurant_completed("new level button", confidence)
                logger.info(f"New level button found at ({x}, {y}); clicking config.NEW_LEVEL_BUTTON_POS at {config.NEW_LEVEL_BUTTON_POS}")
                
                if not self._click_transition_target(
                    config.NEW_LEVEL_BUTTON_POS[0],
                    config.NEW_LEVEL_BUTTON_POS[1],
                    "New level acknowledgment",
                ):
                    return self._abort_transition("acknowledgment click failed")

                button_delay = config.NEW_LEVEL_BUTTON_DELAY
                if button_delay > 0:
                    if self._sleep_with_interrupt(button_delay):
                        return State.CHECK_NEW_LEVEL

                if not self._execute_transition_travel_clicks():
                    return self._abort_transition("travel confirmation click failed")

                if config.TRANSITION_POST_CLICK_DELAY > 0:
                    if self._sleep_with_interrupt(config.TRANSITION_POST_CLICK_DELAY):
                        return State.CHECK_NEW_LEVEL

                return self._finalize_transition()
            
            if attempt < max_attempts - 1:
                if config.TRANSITION_RETRY_DELAY > 0:
                    if self._sleep_with_interrupt(config.TRANSITION_RETRY_DELAY):
                        return State.CHECK_NEW_LEVEL
        
        logger.warning("New level button not found after 5 attempts")
        self._last_new_level_fail_time = time.monotonic()
        return State.FIND_RED_ICONS

    def _finalize_transition(self):
        self.total_levels_completed += 1
        self._last_transition_time = time.monotonic()

        time_spent = 0
        if self.current_level_start_time:
            completion_time = self.completion_detected_time or datetime.now()
            time_spent = (completion_time - self.current_level_start_time).total_seconds()

        completion_source = self.completion_detected_by or "new level button"
        self.current_level_start_time = datetime.now()
        self.completion_detected_time = None
        self.completion_detected_by = None
        self._reset_search_cycle(reason="level transition")

        self.telegram.notify_new_level(self.total_levels_completed, time_spent)
        self.historical_learner.record_completion(
            time_spent,
            completion_source,
        )

        logger.info(f"Level {self.total_levels_completed} completed. Time spent: {time_spent:.1f}s")
        logger.info("Waiting for unlock button after level transition")
        return State.WAIT_FOR_UNLOCK

    def _reset_search_cycle(self, reason="state reset"):
        """Reset oscillating-search progression so the next search starts from base sweep."""
        cycle_index = getattr(self, "_oscillation_cycle_index", 1)
        leg_direction = getattr(self, "_oscillation_leg_direction", 1)
        leg_progress = getattr(self, "_oscillation_leg_progress", 0)
        logger.debug(
            "Resetting search cycle (%s): scroll_offset_units=%.2f cycle=%s leg=%s progress=%s",
            reason,
            self.scroll_offset_units,
            cycle_index,
            "DOWN" if leg_direction > 0 else "UP",
            leg_progress,
        )
        self.scroll_offset_units = 0
        self._oscillation_cycle_index = 1
        self._oscillation_leg_direction = 1
        self._oscillation_leg_progress = 0
        self._scroll_break_sequence_pending = False
    
    def handle_wait_for_unlock(self, current_state):
        """
        Requirement: High-Frequency Visual Polling.
        Minimizes time between station availability and interaction to near-zero.
        """
        if self._scroll_break_passthrough_active():
            logger.debug("Scroll break sequence: WAIT_FOR_UNLOCK passthrough")
            self._scroll_break_sequence_pending = False
            return State.FIND_RED_ICONS

        self._click_idle()
        max_duration = config.UNLOCK_HOT_LOOP_TIMEOUT
        start_time = time.monotonic()
        polling_interval = config.UNLOCK_POLL_INTERVAL
        
        logger.info(">>> HOT LOOP: Polling for Unlock button (Max %ss duration)...", max_duration)

        while time.monotonic() - start_time < max_duration:
            # 1. INTERRUPT CHECK: Ensure immediate stop
            if not self.running:
                return None

            # 2. CAPTURE & SCAN
            # Use force=True to bypass cache for real-time reactivity
            screenshot = self._capture(max_y=config.MAX_SEARCH_Y, force=True)

            # SAFETY CHECK: If the travel button appears, transition likely failed or pop-up is persistent
            found_nl, _, x_nl, y_nl = self._detect_new_level(screenshot=screenshot)
            if found_nl:
                logger.warning("Detected transition button during unlock polling; returning to CHECK_NEW_LEVEL")
                return State.CHECK_NEW_LEVEL

            # STEP A: Tight check for Unlock button
            if "unlock" in self.templates:
                template, mask = self.templates["unlock"]
                found, confidence, x, y = self.image_matcher.find_template(
                    screenshot, template, mask=mask,
                    threshold=config.UNLOCK_THRESHOLD, template_name="unlock-poll"
                )

                if found:
                    # STEP B: CLICK IMMEDIATELY
                    logger.info(f"Unlock button detected [conf: {confidence:.2f}]. Clicking immediately.")
                    self.mouse_controller.click(x, y, relative=True, wait_after=False)
                    
                    # STEP C: Verify click success (Check if button disappeared)
                    # We wait for UI to register and then re-verify
                    if self._sleep_with_interrupt(config.UNLOCK_REGISTER_WAIT):
                        return State.CHECK_NEW_LEVEL
                    v_screenshot = self._capture(max_y=config.MAX_SEARCH_Y, force=True)
                    v_found, _, _, _ = self.image_matcher.find_template(
                        v_screenshot, template, mask=mask,
                        threshold=config.UNLOCK_THRESHOLD, template_name="unlock-verify"
                    )
                    
                    if not v_found:
                        logger.info(f"✓ Station Unlocked! Total latency: {time.monotonic() - start_time:.2f}s")
                        self.wait_for_unlock_attempts = 0
                        return State.FIND_RED_ICONS
                    else:
                        logger.debug("Unlock click not registered by UI; retrying next poll...")

            # Maintain the tight polling cadence
            if self._sleep_with_interrupt(polling_interval):
                return State.CHECK_NEW_LEVEL
            
        # --- SMART TIMEOUT EXIT STRATEGY ---
        logger.warning(f"!!! Timeout: Unlock button not found within {max_duration}s.")
        
        # Step 1: Immediate Sanity Check for Level Completion
        # If we couldn't find the unlock button, it might be because the level is already finished.
        screenshot = self._capture(max_y=config.MAX_SEARCH_Y, force=True)
        found_nl, conf_nl, x_nl, y_nl = self._detect_new_level(screenshot=screenshot)
        
        if found_nl:
            logger.info("Smart Timeout: Detected new level button after unlock timeout. Triggering transition.")
            self.wait_for_unlock_attempts = 0
            return State.CHECK_NEW_LEVEL
            
        # Step 2: Standard Fallback
        logger.info("Smart Timeout: No level transition detected. Falling back to search.")
        self.wait_for_unlock_attempts = 0
        return State.FIND_RED_ICONS
    
    def start(self):
        if self.running:
            return

        self._timer_resolution.enable()
        self._reset_runtime_interrupt_state(reset_completion=True)
        self.running = True
        logger.info("Bot started")
        
        if self.current_level_start_time is None:
            self.current_level_start_time = datetime.now()
            logger.info("Starting level timer at bot start")

        if self._new_level_monitor_thread is None or not self._new_level_monitor_thread.is_alive():
            self._new_level_monitor_stop.clear()
            self._new_level_monitor_thread = threading.Thread(
                target=self._monitor_new_level,
                name="new_level_monitor",
                daemon=True,
            )
            self._new_level_monitor_thread.start()

        self.historical_learner.start()
        
        if config.ShowForbiddenArea and not self.overlay:
            from window_capture import ForbiddenAreaOverlay
            self.overlay = ForbiddenAreaOverlay(self.window_capture.hwnd, self.forbidden_zones)
            self.overlay.start()
            logger.info("Forbidden area overlay enabled and started")

    def stop(self):
        if not self.running:
            self._timer_resolution.disable()
            return

        self.running = False
        self._new_level_monitor_stop.set()
        if self._new_level_monitor_thread and self._new_level_monitor_thread.is_alive():
            self._new_level_monitor_thread.join(timeout=config.THREAD_JOIN_TIMEOUT)
        self._new_level_monitor_thread = None
        self.historical_learner.stop()
        if self.overlay:
            self.overlay.stop()
            self.overlay = None
        self._reset_runtime_interrupt_state(reset_completion=True)
        self._timer_resolution.disable()
        logger.info("Bot stopped")

    def step(self):
        self._clear_capture_cache()
        self._apply_tuning()
        self._enforce_state_min_interval()
        try:
            self.state_machine.update()
        except LevelCompleteInterrupt:
            # Handle the priority interrupt: Force transition to New Level check
            logger.info("Handling LevelCompleteInterrupt: Switching to CHECK_NEW_LEVEL state.")
            self.state_machine.transition(State.CHECK_NEW_LEVEL)
        except BotStoppedInterrupt:
            # Bot was stopped, just exit the step
            logger.debug("BotStoppedInterrupt caught in step")
            pass
        except Exception:
            logger.exception(
                "Unexpected exception during bot step in state %s",
                self.state_machine.get_state_name(),
            )
            if self._uninterrupted_main_flow_enabled() and self.running:
                self._recover_from_step_exception()
                return
            raise

    def run(self):
        self.start()
        try:
            while self.running:
                if not self.window_capture.is_window_active():
                    logger.error(f"Window '{config.WINDOW_TITLE}' is no longer active!")
                    break
                
                self.step()
                
        except KeyboardInterrupt:
            logger.info("Bot stopped by user (Ctrl+C)")
        except Exception as e:
            logger.error(f"Bot error: {e}", exc_info=True)
        finally:
            self.stop()
