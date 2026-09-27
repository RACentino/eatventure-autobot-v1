import hashlib
import logging
import math
import threading
import time
from collections import deque
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pywintypes

import config
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

TemplatePair = tuple[Any, Any]
BoxCandidate = tuple[float, int, int, int, int, str]
RedIcon = tuple[float, int, int]
ForbiddenZoneBounds = tuple[int, int, int, int]


class EatventureBot:
    def __init__(self) -> None:
        logger.info("Initializing Eatventure Bot")
        self._running = threading.Event()
        self._stop_requested = threading.Event()
        self._state_operation_lock = threading.RLock()

        self.window_capture = WindowCapture(config.WINDOW_TITLE, config.WINDOW_WIDTH, config.WINDOW_HEIGHT)
        self.image_matcher = ImageMatcher(config.MATCH_THRESHOLD)
        self.mouse_controller = MouseController(
            self.window_capture.get_hwnd,
            click_delay=config.CLICK_DELAY,
            move_delay=config.MOUSE_MOVE_DELAY,
            stop_event=self._stop_requested,
        )
        self.state_machine = StateMachine(
            State.FIND_RED_ICONS,
            {
                State.FIND_RED_ICONS: self.handle_find_red_icons,
                State.CLICK_RED_ICON: self.handle_click_red_icon,
                State.CHECK_UNLOCK: self.handle_check_unlock,
                State.SEARCH_UPGRADE_STATION: self.handle_search_upgrade_station,
                State.HOLD_UPGRADE_STATION: self.handle_hold_upgrade_station,
                State.OPEN_BOXES: self.handle_open_boxes,
                State.UPGRADE_STATS: self.handle_upgrade_stats,
                State.SCROLL: self.handle_scroll,
                State.CHECK_NEW_LEVEL: self.handle_check_new_level,
                State.TRANSITION_LEVEL: self.handle_transition_level,
                State.WAIT_FOR_UNLOCK: self.handle_wait_for_unlock,
            },
        )
        self.telegram = TelegramNotifier(
            config.TELEGRAM_BOT_TOKEN,
            config.TELEGRAM_CHAT_ID,
            config.TELEGRAM_ENABLED,
        )

        self.templates = self.load_templates()
        self._red_icon_template_names_cache: list[str] | None = None
        self._red_icon_template_names_cache = self._red_icon_template_names()
        self._red_icon_max_width, self._red_icon_max_height = self._red_icon_template_span()
        self.ready = self._validate_required_templates()
        self._initialize_runtime_state()
        self._config_fingerprint = self._compute_config_fingerprint()

        logger.info("Bot initialized successfully")

    @property
    def running(self) -> bool:
        return self._running.is_set()

    @running.setter
    def running(self, is_running: bool) -> None:
        if is_running:
            self._running.set()
            return
        self._running.clear()

    def _initialize_runtime_state(self) -> None:
        self.running = False
        self.red_icons: list[RedIcon] = []
        self.current_red_icon_index = 0
        self.wait_for_unlock_attempts = 0
        self.max_wait_for_unlock_attempts = max(1, int(config.UNLOCK_SEARCH_ATTEMPTS))
        self.work_done = False
        self.cycle_counter = 0
        self.upgrade_station_counter = 0
        self.successful_red_icon_positions: deque[int] = deque(maxlen=24)
        self.upgrade_found_in_cycle = False
        self.consecutive_failed_cycles = 0
        self.total_levels_completed = 0
        self.current_level_start_time: float | None = None
        self.upgrade_station_pos: tuple[int, int] | None = None
        self.overlay: ForbiddenAreaOverlay | None = None
        self._oscillation_cycle_index = 1
        self._oscillation_leg_direction = 1
        self._oscillation_leg_progress = 0
        self._new_level_red_icon_verified = False
        self._state_entered_at = time.monotonic()
        self.forbidden_zones = self._configured_forbidden_zones()

        # Dead-loop guard + stall alert + metrics counters (see handle_open_boxes,
        # _maybe_alert_stall, _log_metrics). Tallies (holds_completed, boxes_opened_total,
        # box_guard_trips, stall_alerts) are never reset by _reset_search_cycle, only by stop()
        # below, mirroring total_levels_completed's treatment.
        self.box_only_passes = 0
        self.idle_scrolls = 0
        self.holds_completed = 0
        self.boxes_opened_total = 0
        self.box_guard_trips = 0
        self.stall_alerts = 0
        # Where the last few boxes were clicked, logged when the dead-loop guard trips so a
        # UI-fixed stuck target (same coordinates every pass) is visible in bot.log.
        self._recent_box_clicks: deque[tuple[int, int]] = deque(maxlen=8)
        # Stall alert: when the idle streak began, and whether the next OPEN_BOXES scan should
        # log what box detection actually saw.
        self._idle_started_at = 0.0
        self._stall_probe_pending = False
        # ponytail: cumulative since process start, no rolling window; subtract consecutive
        # metrics lines for a per-period rate. Upgrade path: a windowed deque if that gets tedious.
        self._state_seconds: dict[State, float] = dict.fromkeys(State, 0.0)
        self._last_metrics_at = 0.0

    @staticmethod
    def _configured_forbidden_zones() -> list[tuple[int, int, int, int]]:
        return list(config.NUMBERED_FORBIDDEN_ZONE_BOUNDS)

    @staticmethod
    def _compute_config_fingerprint() -> str:
        """Short stable id of the tuning in effect, so a metrics line says which config produced
        it. config.py is a flat module (no dataclass), so this hashes every public UPPERCASE
        constant except paths (machine-specific) and Telegram fields (secret/env-derived)."""
        excluded = {"ASSETS_DIR", "LOGS_DIR", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "TELEGRAM_ENABLED"}
        tuning = {
            name: value
            for name, value in vars(config).items()
            if name.isupper() and name not in excluded
        }
        fingerprint = repr(sorted(tuning.items(), key=lambda item: item[0]))
        return hashlib.sha1(fingerprint.encode(), usedforsecurity=False).hexdigest()[:8]

    def set_event_forbidden_zone(self, bounds: ForbiddenZoneBounds) -> None:
        self.forbidden_zones = [bounds, *self._configured_forbidden_zones()]
        self.mouse_controller.set_event_forbidden_zone(bounds)

    def load_templates(self) -> dict[str, TemplatePair]:
        templates: dict[str, TemplatePair] = {}
        templates_path = Path(config.ASSETS_DIR)
        if not templates_path.exists():
            logger.error("Assets directory not found: %s", templates_path)
            return templates

        for template_file in sorted(templates_path.glob("*.png")):
            try:
                template_name = template_file.stem
                template_img = self.image_matcher.load_template(template_file)
                templates[template_name] = template_img
                logger.info("Loaded template: %s", template_name)
            except Exception as exc:
                logger.error("Failed to load template %s: %s", template_file, exc)

        return templates

    def _available_red_icon_template_count(self) -> int:
        return sum(1 for name in self.templates if name.startswith("RedIcon"))

    def _red_icon_min_matches(self) -> int:
        if config.RED_ICON_FAST_MODE_ENABLED:
            return 1
        available = self._available_red_icon_template_count()
        if available <= 0:
            return 1
        configured = max(1, int(config.RED_ICON_MIN_MATCHES))
        return min(configured, available)

    @staticmethod
    def _configured_fast_red_icon_template_names() -> tuple[str, ...]:
        configured_names = config.RED_ICON_FAST_TEMPLATE_NAMES
        if not isinstance(configured_names, tuple) or not configured_names:
            return ()
        if any(not isinstance(name, str) or not name for name in configured_names):
            return ()
        if len(set(configured_names)) != len(configured_names):
            return ()
        return tuple(configured_names)

    def _validate_required_templates(self) -> bool:
        missing = [name for name in ("newLevel", "unlock", "upgradeStation") if name not in self.templates]
        red_icon_count = self._available_red_icon_template_count()
        if red_icon_count <= 0:
            missing.append("RedIcon*")
        if config.RED_ICON_FAST_MODE_ENABLED:
            fast_template_names = self._configured_fast_red_icon_template_names()
            if not fast_template_names:
                missing.append("RED_ICON_FAST_TEMPLATE_NAMES")
            else:
                missing.extend(name for name in fast_template_names if name not in self.templates)
        if missing:
            logger.error("Missing required templates: %s", ", ".join(missing))
            return False
        if red_icon_count < int(config.RED_ICON_MIN_MATCHES):
            logger.warning(
                "Only %s red-icon templates are available; consensus requirement reduced from %s",
                red_icon_count,
                config.RED_ICON_MIN_MATCHES,
            )
        return True

    def _sleep(self, duration: Any) -> bool:
        try:
            delay = max(0.0, float(duration))
        except (TypeError, ValueError):
            delay = 0.0
        return not self._stop_requested.wait(delay)

    def _template(self, template_name: str) -> TemplatePair | None:
        return self.templates.get(template_name)

    def _click_idle(self) -> bool:
        return self.mouse_controller.click(config.IDLE_CLICK_POS[0], config.IDLE_CLICK_POS[1], relative=True)

    def _scrcpy_miss_recovery_sleep(self, duration: Any) -> bool:
        if not config.SCRCPY_MISS_RECOVERY_ENABLED:
            return False
        try:
            delay = max(0.0, float(duration))
        except (TypeError, ValueError):
            delay = 0.0
        if delay <= 0:
            return True
        return self._sleep(delay)

    def _scan_red_icon_frame(
        self,
        screenshot: Any,
        limited_screenshot: Any,
        scan_threshold: float,
        min_matches: int,
    ) -> tuple[list[RedIcon], RedIcon | None]:
        all_detections = self._collect_red_icon_detections(
            limited_screenshot,
            scan_threshold,
            min_distance=80,
        )
        red_icons = self._icons_from_detections(all_detections, min_matches)
        best_new_level_icon = self._find_new_level_red_icon(screenshot, scan_threshold, min_matches)
        return red_icons, best_new_level_icon

    def _find_new_level_button(self, screenshot: Any) -> tuple[bool, float, int, int]:
        template_pair = self._template("newLevel")
        if template_pair is None:
            return False, 0.0, 0, 0
        template, mask = template_pair
        return self.image_matcher.find_template(
            screenshot,
            template,
            mask=mask,
            threshold=config.NEW_LEVEL_THRESHOLD,
            template_name="newLevel",
        )

    def _red_icon_template_names(self) -> list[str]:
        cached = self._red_icon_template_names_cache
        if cached is not None:
            return cached
        template_names = [name for name in self.templates if name.startswith("RedIcon")]
        if not template_names:
            return ["RedIcon"]

        def sort_key(name: str) -> tuple[int, Any]:
            if name == "RedIcon":
                return (0, 0)
            if name == "RedIconNoBG":
                return (2, 0)
            suffix = name.replace("RedIcon", "", 1)
            if suffix.isdigit():
                return (1, int(suffix))
            return (3, suffix)

        return sorted(template_names, key=sort_key)

    def _red_icon_template_span(self) -> tuple[int, int]:
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
    def _extract_region(
        screenshot: Any,
        x_min: Any,
        x_max: Any,
        y_min: Any,
        y_max: Any,
        pad_x: Any = 0,
        pad_y: Any = 0,
    ) -> tuple[Any, int, int]:
        height, width = screenshot.shape[:2]
        left = max(0, int(x_min) - int(pad_x))
        right = min(width, int(x_max) + int(pad_x))
        top = max(0, int(y_min) - int(pad_y))
        bottom = min(height, int(y_max) + int(pad_y))
        if left >= right or top >= bottom:
            return screenshot[0:0, 0:0], 0, 0
        return screenshot[top:bottom, left:right], left, top
    @staticmethod
    def _merge_icon_detection(
        detections: dict[tuple[int, int], list[tuple[str, float]]],
        x: int,
        y: int,
        template_name: str,
        confidence: float,
    ) -> None:
        for existing_x, existing_y in list(detections.keys()):
            if abs(x - existing_x) < 10 and abs(y - existing_y) < 10:
                detections[(existing_x, existing_y)].append((template_name, confidence))
                return
        detections[(x, y)] = [(template_name, confidence)]

    def _collect_red_icon_detections(
        self,
        screenshot: Any,
        threshold: float,
        min_distance: int = 80,
        offset_x: int = 0,
        offset_y: int = 0,
    ) -> dict[tuple[int, int], list[tuple[str, float]]]:
        detections: dict[tuple[int, int], list[tuple[str, float]]] = {}
        if screenshot.size == 0:
            return detections
        template_names = self._red_icon_template_names()
        if config.RED_ICON_FAST_MODE_ENABLED:
            configured_fast_names = self._configured_fast_red_icon_template_names()
            fast_names = [name for name in configured_fast_names if name in self.templates]
            if not fast_names:
                logger.error("No configured Fast Mode red-icon template is loaded")
                return detections
            template_names = fast_names
            min_distance = int(config.RED_ICON_FAST_MIN_DISTANCE)
        for template_name in template_names:
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
                hsv_ranges=config.RED_ICON_HSV_RANGES,
                hsv_match_threshold=config.RED_ICON_HSV_MIN_MATCH_RATIO,
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
    def _best_confidence_by_template(matches: list[tuple[str, float]]) -> dict[str, float]:
        by_template: dict[str, float] = {}
        for template_name, confidence in matches:
            existing = by_template.get(template_name)
            if existing is None or confidence > existing:
                by_template[template_name] = confidence
        return by_template

    @classmethod
    def _icons_from_detections(
        cls: type["EatventureBot"],
        detections: dict[tuple[int, int], list[tuple[str, float]]],
        min_matches: int,
    ) -> list[RedIcon]:
        icons: list[RedIcon] = []
        for (x, y), matches in detections.items():
            by_template = cls._best_confidence_by_template(matches)
            if len(by_template) < min_matches:
                continue
            max_confidence = max(by_template.values())
            icons.append((max_confidence, x, y))
        return icons

    def _find_best_zone_red_icon(
        self,
        screenshot: Any,
        threshold: float,
        x_min: int,
        x_max: int,
        y_min: int,
        y_max: int,
        min_distance: int = 80,
    ) -> RedIcon | None:
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

        detections = self._collect_red_icon_detections(
            region,
            threshold,
            min_distance=min_distance,
            offset_x=offset_x,
            offset_y=offset_y,
        )
        min_matches = self._red_icon_min_matches()
        icons = self._icons_from_detections(detections, min_matches)
        best_match = None
        for confidence, x, y in icons:
            if not (x_min <= x <= x_max and y_min <= y <= y_max):
                continue
            if best_match is None or confidence > best_match[0]:
                best_match = (confidence, x, y)
        return best_match

    def _find_new_level_red_icon(
        self,
        screenshot: Any = None,
        scan_threshold: float | None = None,
        min_matches: int | None = None,
    ) -> RedIcon | None:
        if screenshot is None:
            screenshot = self.window_capture.capture(max_y=config.EXTENDED_SEARCH_Y)
        if scan_threshold is None:
            scan_threshold = config.NEW_LEVEL_RED_ICON_THRESHOLD
        else:
            scan_threshold = min(float(scan_threshold), float(config.NEW_LEVEL_RED_ICON_THRESHOLD))
        if min_matches is None:
            min_matches = self._red_icon_min_matches()

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
        all_red_icons_extended = self._icons_from_detections(footer_detections, min_matches)

        best_new_level_icon = None
        for confidence, x, y in all_red_icons_extended:
            if not (
                config.NEW_LEVEL_RED_ICON_X_MIN <= x <= config.NEW_LEVEL_RED_ICON_X_MAX
                and config.NEW_LEVEL_RED_ICON_Y_MIN <= y <= config.NEW_LEVEL_RED_ICON_Y_MAX
            ):
                continue
            if confidence < config.NEW_LEVEL_RED_ICON_THRESHOLD:
                continue
            if best_new_level_icon is None or confidence > best_new_level_icon[0]:
                best_new_level_icon = (confidence, x, y)
        return best_new_level_icon

    def _remember_successful_red_icon_position(self, y_value: Any) -> None:
        y_value = int(y_value)
        for existing_y in self.successful_red_icon_positions:
            if abs(existing_y - y_value) < 12:
                return
        self.successful_red_icon_positions.append(y_value)

    def _record_level_completion(self) -> float:
        self.total_levels_completed += 1
        self.idle_scrolls = 0
        elapsed = 0.0
        completion_time = time.monotonic()
        if self.current_level_start_time is not None:
            elapsed = max(0.0, completion_time - self.current_level_start_time)
        self.current_level_start_time = completion_time
        self._reset_search_cycle()
        self.telegram.notify_new_level(self.total_levels_completed, elapsed)
        return elapsed

    def _reset_search_cycle(self) -> None:
        self.cycle_counter = 0
        self.wait_for_unlock_attempts = 0
        self._oscillation_cycle_index = 1
        self._oscillation_leg_direction = 1
        self._oscillation_leg_progress = 0
        self._new_level_red_icon_verified = False

    def _advance_oscillation_progress(self) -> None:
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

    def _perform_oscillating_scroll_step(self) -> bool:
        distance = round(float(config.SCROLL_PIXEL_STEP) * float(config.SCROLL_DISTANCE_RATIO))
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
        if not moved:
            return False
        self._advance_oscillation_progress()
        if not self._sleep(config.POST_SCROLL_SETTLE):
            return False
        if not self._sleep(config.SCROLL_INTERVAL_PAUSE):
            return False
        return True

    def _perform_new_level_verification_scroll(self) -> bool:
        """Restored from v1 (73f5db0/eccd810): one down-drag used solely to force a fresh render
        before re-scanning for the new-level red icon. Reuses the shared SCROLL_START_POS origin;
        distance/duration/settle timing are dedicated to this step, independent of the oscillating
        SCROLL_* config used by _perform_oscillating_scroll_step. Not part of the oscillation
        cycle, so it does not touch _oscillation_cycle_index/_oscillation_leg_* progress."""
        start_x, start_y = config.SCROLL_START_POS
        target_y = start_y - config.NEW_LEVEL_VERIFICATION_SCROLL_DISTANCE
        moved = self.mouse_controller.drag(
            start_x,
            start_y,
            start_x,
            target_y,
            duration=config.NEW_LEVEL_VERIFICATION_SCROLL_DURATION,
            relative=True,
        )
        if not moved:
            return False
        if not self._sleep(config.NEW_LEVEL_VERIFICATION_SCROLL_SETTLE_DELAY):
            return False
        return self._sleep(config.NEW_LEVEL_VERIFICATION_SCROLL_INTERVAL_PAUSE)

    def _find_upgrade_station_match(self, threshold: float) -> RedIcon | None:
        if "upgradeStation" not in self.templates:
            return None

        limited_screenshot = self.window_capture.capture(max_y=config.UPGRADE_STATION_SEARCH_Y)
        template, mask = self.templates["upgradeStation"]
        candidates = self.image_matcher.find_all_templates(
            limited_screenshot,
            template,
            mask=mask,
            threshold=threshold,
            min_distance=15,
            template_name="upgradeStation",
            hsv_ranges=config.UPGRADE_STATION_HSV_RANGES,
            hsv_match_threshold=config.UPGRADE_STATION_HSV_MIN_MATCH_RATIO,
        )
        if not candidates:
            return None

        for confidence, x, y in candidates:
            x = int(x)
            y = int(y)
            if not self.mouse_controller.is_in_forbidden_zone(x, y, relative=True):
                return float(confidence), x, y

        return None

    def _clickable_red_icons(self, red_icons: Iterable[RedIcon]) -> list[RedIcon]:
        return [
            (confidence, x, y)
            for confidence, x, y in red_icons
            if not self.mouse_controller.is_in_forbidden_zone(
                x + config.RED_ICON_OFFSET_X,
                y + config.RED_ICON_OFFSET_Y,
                relative=True,
            )
        ]

    def _red_icon_priority_key(self, icon: RedIcon) -> tuple[int, int, float]:
        confidence, _, y = icon
        for success_y in self.successful_red_icon_positions:
            if abs(y - success_y) < 50:
                return (0, y, -confidence)
        return (1, y, -confidence)

    def _find_verified_upgrade_station_match(
        self,
        base_threshold: float,
        relaxed_threshold: float,
    ) -> tuple[RedIcon | None, bool]:
        verify_attempts = max(1, int(config.UPGRADE_STATION_VERIFY_SEARCH_ATTEMPTS))
        for attempt in range(verify_attempts):
            current_threshold = base_threshold if attempt == 0 else relaxed_threshold
            verified_match = self._find_upgrade_station_match(current_threshold)
            if verified_match is not None:
                return verified_match, True
            if attempt < verify_attempts - 1 and not self._sleep(config.UPGRADE_STATION_VERIFY_SEARCH_INTERVAL):
                return None, False
        return None, True

    @staticmethod
    def _hold_max_duration() -> float:
        hold_max_duration = float(config.CLICK_HOLD_MAX_DURATION)
        if not math.isfinite(hold_max_duration):
            return 0.0
        return max(0.0, hold_max_duration)

    def _position_cursor_for_upgrade_hold(self, x: int, y: int) -> tuple[int, int] | None:
        screen_pos = self.mouse_controller._resolve_screen_position(x, y, relative=True)
        if screen_pos is None:
            logger.warning("Upgrade station hold position could not be resolved at (%s, %s)", x, y)
            return None

        screen_x, screen_y = screen_pos
        if self.mouse_controller._set_cursor_pos(screen_x, screen_y):
            if self.mouse_controller.move_delay > 0 and not self._sleep(self.mouse_controller.move_delay):
                return None
            return screen_x, screen_y

        logger.warning("Failed to position cursor for Upgrade Station hold at (%s, %s)", x, y)
        return None

    def _find_current_upgrade_hold_match(
        self,
        base_threshold: float,
        relaxed_threshold: float,
    ) -> RedIcon | None:
        current_match = self._find_upgrade_station_match(base_threshold)
        if current_match is not None:
            return current_match
        current_match = self._find_upgrade_station_match(relaxed_threshold)
        if current_match is not None:
            return current_match
        if self._scrcpy_miss_recovery_sleep(config.SCRCPY_UPGRADE_MISS_RECOVERY_DELAY):
            return self._find_upgrade_station_match(relaxed_threshold)
        return None

    @staticmethod
    def _hold_duration_reached(hold_max_duration: float, hold_elapsed: float) -> bool:
        return hold_elapsed >= hold_max_duration

    def _monitor_upgrade_station_hold(
        self,
        base_threshold: float,
        relaxed_threshold: float,
        hold_check_interval: float,
        hold_max_duration: float,
        hold_started_at: float,
    ) -> tuple[bool, bool, float]:
        maximum_checks = max(1, int(config.UPGRADE_HOLD_MAX_CHECKS))
        disappearance_confirmations = max(1, int(config.UPGRADE_STATION_DISAPPEAR_CONFIRMATION_COUNT))
        consecutive_misses = 0
        for _ in range(maximum_checks):
            hold_elapsed = time.monotonic() - hold_started_at
            if self._stop_requested.is_set():
                logger.warning("Upgrade station hold interrupted after %.2fs", hold_elapsed)
                return False, False, hold_elapsed
            if self._hold_duration_reached(hold_max_duration, hold_elapsed):
                logger.warning(
                    "Upgrade station hold max duration %.2fs reached after %.2fs; releasing hold",
                    hold_max_duration,
                    hold_elapsed,
                )
                return True, True, hold_elapsed
            if not self._sleep(hold_check_interval):
                return False, False, hold_elapsed
            if not self.mouse_controller.is_target_foreground():
                logger.warning("Upgrade station hold interrupted because target lost foreground")
                return False, False, time.monotonic() - hold_started_at

            current_match = self._find_current_upgrade_hold_match(base_threshold, relaxed_threshold)
            if current_match is None:
                consecutive_misses += 1
                if consecutive_misses >= disappearance_confirmations:
                    return True, False, time.monotonic() - hold_started_at
                continue

            consecutive_misses = 0

            _, x, y = current_match
            self.upgrade_station_pos = (x, y)

        logger.warning("Upgrade station hold safety limit of %s checks reached", maximum_checks)
        return True, True, time.monotonic() - hold_started_at

    def _hold_upgrade_station_until_complete(
        self,
        screen_position: tuple[int, int],
        base_threshold: float,
        relaxed_threshold: float,
        hold_check_interval: float,
        hold_max_duration: float,
    ) -> tuple[bool, bool, float]:
        screen_x, screen_y = screen_position
        hold_started_at = time.monotonic()
        if hold_max_duration <= 0.0:
            logger.error("Upgrade station hold rejected because its maximum duration is not positive")
            return False, True, 0.0

        with self.mouse_controller._input_lock:
            if not self.mouse_controller._left_down_at_screen(screen_x, screen_y):
                logger.warning("Upgrade station hold press failed at (%s, %s)", screen_x, screen_y)
                return False, False, time.monotonic() - hold_started_at
            released = False
            try:
                hold_result = self._monitor_upgrade_station_hold(
                    base_threshold,
                    relaxed_threshold,
                    hold_check_interval,
                    hold_max_duration,
                    hold_started_at,
                )
            finally:
                try:
                    released = self.mouse_controller._left_up_at_screen(screen_x, screen_y)
                finally:
                    if not released:
                        self.mouse_controller._best_effort_left_up(screen_x, screen_y)
                if not released:
                    logger.critical("Upgrade station hold release could not be confirmed")

            if not released:
                return False, False, time.monotonic() - hold_started_at
            return hold_result

    def _box_template_names(self) -> list[str]:
        return [box_name for box_name in ("box1", "box2", "box3", "box4") if box_name in self.templates]

    def _collect_box_candidates(self, limited_screenshot: Any, box_threshold: float) -> list[BoxCandidate]:
        box_candidates: list[BoxCandidate] = []
        for box_name in self._box_template_names():
            template, mask = self.templates[box_name]
            candidates = self.image_matcher.find_template_candidates(
                limited_screenshot,
                template,
                mask=mask,
                threshold=box_threshold,
                min_distance=12,
                template_name=box_name,
                hsv_ranges=config.BOX_HSV_RANGES,
                hsv_match_threshold=config.BOX_HSV_MIN_MATCH_RATIO,
            )
            for confidence, x, y, candidate_width, candidate_height in candidates:
                candidate_width = int(candidate_width)
                candidate_height = int(candidate_height)
                box_candidates.append((confidence, int(x), int(y), candidate_width, candidate_height, box_name))
        return box_candidates

    def _click_box_candidates(self, merged_boxes: list[BoxCandidate]) -> int:
        boxes_found = 0
        for _, x, y, _, _, _ in merged_boxes:
            if self.mouse_controller.is_in_forbidden_zone(x, y, relative=True):
                logger.debug("Box candidate is in a forbidden zone")
                continue
            if self.mouse_controller.click(x, y, relative=True):
                boxes_found += 1
                self._recent_box_clicks.append((x, y))
        return boxes_found

    def _next_state_after_box_cycle(self) -> State:
        if self.consecutive_failed_cycles >= config.FAILED_UPGRADE_SEARCHES_BEFORE_SCROLL:
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

        max_idle_pass_attempts = max(1, int(config.MAX_IDLE_PASS_ATTEMPTS))
        self.cycle_counter += 1
        logger.info(
            "No work detected in current area (idle pass %s/%s)",
            self.cycle_counter,
            max_idle_pass_attempts,
        )
        if self.cycle_counter >= max_idle_pass_attempts:
            self.cycle_counter = 0
            return State.SCROLL

        return State.FIND_RED_ICONS

    def start(self) -> bool:
        if not self._state_operation_lock.acquire(blocking=False):
            logger.warning("Cannot start bot while a state operation is active")
            return False
        try:
            if self.running:
                return True
            if not self.ready:
                logger.error("Cannot start bot because required templates are missing")
                return False
            try:
                self.window_capture.ensure_window(resize=True)
            except WindowCaptureError as exc:
                logger.error("Cannot start bot: %s", exc)
                self.running = False
                return False
            if not self.mouse_controller.is_target_foreground():
                logger.error("Cannot start bot because '%s' is not the foreground window", config.WINDOW_TITLE)
                self.running = False
                return False
            self._stop_requested.clear()
            self.running = True
            self._state_entered_at = time.monotonic()
            self._last_metrics_at = time.monotonic()
            if self.current_level_start_time is None:
                self.current_level_start_time = time.monotonic()
            if config.ShowForbiddenArea and self.overlay is None:
                self.overlay = ForbiddenAreaOverlay(self.window_capture.get_hwnd(), self.forbidden_zones)
                self.overlay.start()
            return True
        finally:
            self._state_operation_lock.release()

    def request_stop(self) -> None:
        self._stop_requested.set()

    def stop(self) -> None:
        self.request_stop()
        with self._state_operation_lock:
            if not self.running and self.overlay is None:
                return
            was_running = self.running
            self.running = False
            self.state_machine.transition(State.FIND_RED_ICONS)
            self._reset_search_cycle()
            self.red_icons.clear()
            self.current_red_icon_index = 0
            self.upgrade_station_pos = None
            self.upgrade_found_in_cycle = False
            self.work_done = False
            self.consecutive_failed_cycles = 0
            self.box_only_passes = 0
            self.idle_scrolls = 0
            if self.overlay is not None:
                self.overlay.stop()
                self.overlay = None
            if was_running and config.METRICS_LOG_INTERVAL > 0:
                self._log_metrics()

    def step(self) -> bool:
        if not self._state_operation_lock.acquire(blocking=False):
            logger.warning("Ignoring reentrant bot step")
            return False
        try:
            if self._stop_requested.is_set():
                self.stop()
                return False
            self.window_capture.ensure_window(resize=True)
            if not self.mouse_controller.is_target_foreground():
                logger.error("Window '%s' lost foreground ownership; stopping bot", config.WINDOW_TITLE)
                self.stop()
                return False
            previous_state = self.state_machine.current_state
            handler_started_at = time.monotonic()
            current_state = self.state_machine.update()
            self._state_seconds[previous_state] += time.monotonic() - handler_started_at
            now = time.monotonic()
            if current_state != previous_state:
                self._state_entered_at = now
            elif now - self._state_entered_at >= config.STATE_STALL_TIMEOUT_SECONDS:
                logger.warning("State %s stalled; resetting search flow", current_state.name)
                self._reset_search_cycle()
                self.state_machine.transition(State.FIND_RED_ICONS)
                self._state_entered_at = now
            self._maybe_log_metrics()
            return True
        except (WindowNotAvailableError, WindowCaptureError) as exc:
            logger.error("Stopping bot: %s", exc)
            self.stop()
            return False
        except pywintypes.error as exc:
            logger.error("Stopping bot due to Windows input failure: %s", exc)
            self.stop()
            return False
        except Exception:
            logger.exception("Stopping bot due to unexpected state-handler failure")
            self.stop()
            return False
        finally:
            self._state_operation_lock.release()

    def _maybe_log_metrics(self) -> None:
        interval = config.METRICS_LOG_INTERVAL
        now = time.monotonic()
        if interval <= 0 or now - self._last_metrics_at < interval:
            return
        self._last_metrics_at = now
        self._log_metrics()

    def _log_metrics(self) -> None:
        """One parseable line: run_s is time spent inside handlers (not the event-loop wake), and
        each state's share of it - where the run actually went."""
        total = sum(self._state_seconds.values())
        shares = " ".join(
            f"{state.name}={100 * seconds / total:.1f}%"
            for state, seconds in self._state_seconds.items()
            if seconds > 0
        )
        logger.info(
            "metrics cfg=%s run_s=%.0f levels=%d holds=%d boxes=%d guard_trips=%d "
            "idle_scrolls=%d stall_alerts=%d | %s",
            self._config_fingerprint,
            total,
            self.total_levels_completed,
            self.holds_completed,
            self.boxes_opened_total,
            self.box_guard_trips,
            self.idle_scrolls,
            self.stall_alerts,
            shares or "-",
        )

    def _maybe_alert_stall(self) -> None:
        """After every landed scroll: idle_scrolls says how long the search has produced nothing.
        Every STALL_SCROLLS_BEFORE_ALERT scrolls, log a WARNING and arm a one-shot probe of box
        detection on the next OPEN_BOXES frame, so a silent stall names its own cause."""
        if self.idle_scrolls == 1:
            self._idle_started_at = time.monotonic()
        every = max(0, int(config.STALL_SCROLLS_BEFORE_ALERT))
        if every <= 0 or self.idle_scrolls % every != 0:
            return
        self.stall_alerts += 1
        self._stall_probe_pending = True
        logger.warning(
            "Stall: %d scrolls over %.0f min with no box opened, upgrade held, stats upgrade or "
            "level completed (levels=%d holds=%d boxes=%d); probing box detection on the next scan",
            self.idle_scrolls,
            (time.monotonic() - self._idle_started_at) / 60,
            self.total_levels_completed,
            self.holds_completed,
            self.boxes_opened_total,
        )

    def _log_box_near_misses(self, limited_screenshot: Any, detected: int) -> None:
        """One text line: how many boxes passed detection on this frame, and for each box template
        its best raw match with no threshold/gate applied (template score, HSV ratio) and whether
        that spot is a forbidden zone. Tells a template/HSV miss from a zone block."""
        parts = []
        for box_name in self._box_template_names():
            template, mask = self.templates[box_name]
            explained = self.image_matcher.explain_template(
                limited_screenshot,
                template,
                mask=mask,
                template_name=box_name,
                hsv_ranges=config.BOX_HSV_RANGES,
            )
            if explained is None:
                continue
            name, confidence, (center_x, center_y), ratio = explained
            zone = " IN-FORBIDDEN-ZONE" if self.mouse_controller.is_in_forbidden_zone(
                center_x, center_y, relative=True
            ) else ""
            ratio_text = "n/a" if ratio is None else f"{ratio:.2f}"
            parts.append(f"{name} conf={confidence:.3f} at ({center_x}, {center_y}) hsv={ratio_text}{zone}")
        logger.warning(
            "Stall probe: %d box(es) passed detection on this scan. Best raw match per template "
            "(a box needs conf>=%.3f and hsv>=%.2f, outside forbidden zones): %s",
            detected,
            config.BOX_THRESHOLD,
            config.BOX_HSV_MIN_MATCH_RATIO,
            "; ".join(parts) or "none",
        )

    def _state_from_red_icon_scan(self, best_new_level_icon: RedIcon | None) -> State:
        if best_new_level_icon is not None:
            logger.info(
                "New level red icon detected at (%s, %s) [%.3f]",
                best_new_level_icon[1],
                best_new_level_icon[2],
                best_new_level_icon[0],
            )
            self._new_level_red_icon_verified = False
            return State.CHECK_NEW_LEVEL

        if not self.red_icons:
            return State.OPEN_BOXES

        filtered_icons = self._clickable_red_icons(self.red_icons)
        if not filtered_icons:
            logger.info("No valid red icons after forbidden-zone filtering")
            return State.OPEN_BOXES

        self.red_icons = sorted(filtered_icons, key=self._red_icon_priority_key)
        self.current_red_icon_index = 0
        self.cycle_counter = 0
        self.work_done = True
        logger.info("%s red icons ready to process", len(self.red_icons))
        return State.CLICK_RED_ICON

    def handle_find_red_icons(self) -> State:
        if not self._click_idle():
            return State.FIND_RED_ICONS

        self.work_done = False

        screenshot = self.window_capture.capture(max_y=config.EXTENDED_SEARCH_Y)
        limited_screenshot = screenshot[: config.MAX_SEARCH_Y, :]

        found, confidence, x, y = self._find_new_level_button(limited_screenshot)
        if found:
            self.cycle_counter = 0
            logger.info("newLevel.png found at (%s, %s)", x, y)
            return State.TRANSITION_LEVEL

        scan_threshold = config.RED_ICON_THRESHOLD

        min_matches = self._red_icon_min_matches()
        self.red_icons, best_new_level_icon = self._scan_red_icon_frame(
            screenshot,
            limited_screenshot,
            scan_threshold,
            min_matches,
        )

        if (
            not self.red_icons
            and best_new_level_icon is None
            and self._scrcpy_miss_recovery_sleep(config.SCRCPY_RED_ICON_MISS_RECOVERY_DELAY)
        ):
            screenshot = self.window_capture.capture(max_y=config.EXTENDED_SEARCH_Y)
            limited_screenshot = screenshot[: config.MAX_SEARCH_Y, :]
            found, confidence, x, y = self._find_new_level_button(limited_screenshot)
            if found:
                self.cycle_counter = 0
                logger.info("newLevel.png found at (%s, %s) after SCRCPY recovery", x, y)
                return State.TRANSITION_LEVEL
            self.red_icons, best_new_level_icon = self._scan_red_icon_frame(
                screenshot,
                limited_screenshot,
                scan_threshold,
                min_matches,
            )
        return self._state_from_red_icon_scan(best_new_level_icon)

    def handle_click_red_icon(self) -> State:
        if self.current_red_icon_index >= len(self.red_icons):
            logger.info("All red icons processed, continuing cycle")
            return State.OPEN_BOXES

        confidence, x, y = self.red_icons[self.current_red_icon_index]
        click_x = x + config.RED_ICON_OFFSET_X
        click_y = y + config.RED_ICON_OFFSET_Y

        clicked = self.mouse_controller.click(click_x, click_y, relative=True)
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

    def handle_check_unlock(self) -> State:
        if not self._sleep(config.SCRCPY_ACTION_SETTLE_DELAY):
            return State.CHECK_UNLOCK

        limited_screenshot = self.window_capture.capture(max_y=config.MAX_SEARCH_Y)

        template_pair = self._template("unlock")
        if template_pair is None:
            return State.SEARCH_UPGRADE_STATION

        template, mask = template_pair
        found, confidence, x, y = self.image_matcher.find_template(
            limited_screenshot,
            template,
            mask=mask,
            threshold=config.UNLOCK_THRESHOLD,
            template_name="unlock",
        )
        if not found or self.mouse_controller.is_in_forbidden_zone(x, y, relative=True):
            return State.SEARCH_UPGRADE_STATION

        logger.info("Unlock found at (%s, %s) [%.3f]", x, y, confidence)
        if not self.mouse_controller.click(x, y, relative=True):
            logger.warning("Unlock click failed at (%s, %s)", x, y)
            return State.CHECK_UNLOCK

        if not self._sleep(config.SCRCPY_ACTION_SETTLE_DELAY):
            return State.CHECK_UNLOCK
        return State.SEARCH_UPGRADE_STATION

    def handle_search_upgrade_station(self) -> State:
        base_threshold = config.UPGRADE_STATION_THRESHOLD
        relaxed_threshold = max(0.0, base_threshold - 0.05)
        max_attempts = max(1, int(config.UPGRADE_SEARCH_ATTEMPTS))

        for attempt in range(max_attempts):
            if "upgradeStation" not in self.templates:
                break

            current_threshold = base_threshold if attempt < 2 else relaxed_threshold
            match = self._find_upgrade_station_match(current_threshold)
            if match is not None:
                _, x, y = match
                logger.info("Upgrade station found at (%s, %s) on attempt %s", x, y, attempt + 1)
                self.upgrade_station_pos = (x, y)
                self.upgrade_found_in_cycle = True
                # Deliberately NOT resetting consecutive_failed_cycles here (moved to
                # handle_hold_upgrade_station's genuine-completion point, see comment there): a
                # station that is found every cycle but never successfully held would otherwise
                # re-zero this counter on every pass, before the hold below ever gets a chance to
                # increment it past 1.
                self.cycle_counter = 0
                return State.HOLD_UPGRADE_STATION

            if attempt < max_attempts - 1 and not self._sleep(config.UPGRADE_SEARCH_INTERVAL):
                return State.OPEN_BOXES

        self.consecutive_failed_cycles += 1
        logger.info("Upgrade station not found, returning to OPEN_BOXES")
        return State.OPEN_BOXES

    def _verify_upgrade_station_hold_target(
        self,
        x: int,
        y: int,
    ) -> tuple[RedIcon, float, float] | None:
        logger.info("Visually verifying upgrade station at (%s, %s) before holding", x, y)
        if not self._sleep(config.UPGRADE_STATION_VERIFY_SETTLE_DELAY):
            return None

        base_threshold = config.UPGRADE_STATION_THRESHOLD
        relaxed_threshold = max(0.0, base_threshold - 0.05)
        verified_match, verification_completed = self._find_verified_upgrade_station_match(
            base_threshold,
            relaxed_threshold,
        )
        if not verification_completed:
            return None

        if verified_match is not None:
            _, verified_x, verified_y = verified_match
            logger.info("Single-clicking visually verified upgrade station at (%s, %s)", verified_x, verified_y)
            clicked = self.mouse_controller.precise_click(verified_x, verified_y, relative=True)
            if not clicked:
                logger.warning("Upgrade station verification click failed at (%s, %s)", verified_x, verified_y)
                return None
            if not self._sleep(config.UPGRADE_STATION_VERIFY_SETTLE_DELAY):
                return None
            verified_match, verification_completed = self._find_verified_upgrade_station_match(
                base_threshold,
                relaxed_threshold,
            )
            if not verification_completed:
                return None

        if verified_match is None:
            logger.info("Upgrade station was not visible during visual verification; continuing main flow")
            self.upgrade_station_pos = None
            self.upgrade_found_in_cycle = False
            return None

        confidence, verified_x, verified_y = verified_match
        self.upgrade_station_pos = (verified_x, verified_y)
        logger.info(
            "Upgrade station verified active at (%s, %s) [%.3f]",
            verified_x,
            verified_y,
            confidence,
        )
        return verified_match, base_threshold, relaxed_threshold

    def handle_hold_upgrade_station(self) -> State:
        # Intentional deviation from literal v1 parity (this exact gap was unfixed): a red icon
        # whose station is found every SEARCH but never actually holds/clicks successfully would
        # otherwise loop FIND_RED_ICONS<->OPEN_BOXES forever, since nothing here used to touch
        # consecutive_failed_cycles and the same-state watchdog never fires (the state keeps
        # changing every tick). Every early exit below now increments the same counter that
        # already feeds the OPEN_BOXES->SCROLL escape (FAILED_UPGRADE_SEARCHES_BEFORE_SCROLL),
        # without adding a new counter or config value; it only resets on a genuinely completed
        # hold further down, not on handle_search_upgrade_station's "found" branch, so repeated
        # hold failures accumulate across cycles instead of being re-zeroed by the very next
        # search success.
        if not self.upgrade_station_pos:
            self.consecutive_failed_cycles += 1
            return State.OPEN_BOXES

        x, y = self.upgrade_station_pos
        if self.mouse_controller.is_in_forbidden_zone(x, y, relative=True):
            logger.warning("Upgrade station blocked by forbidden zone at (%s, %s)", x, y)
            self.consecutive_failed_cycles += 1
            return State.OPEN_BOXES

        verified_target = self._verify_upgrade_station_hold_target(x, y)
        if verified_target is None:
            self.consecutive_failed_cycles += 1
            return State.OPEN_BOXES
        (_, x, y), base_threshold, relaxed_threshold = verified_target
        if self.current_red_icon_index < len(self.red_icons):
            _, _, red_y = self.red_icons[self.current_red_icon_index]
            self._remember_successful_red_icon_position(red_y)

        hold_check_interval = max(
            config.UPGRADE_HOLD_CHECK_INTERVAL_MIN,
            min(config.UPGRADE_HOLD_CHECK_INTERVAL_MAX, float(config.UPGRADE_STATION_VERIFY_SEARCH_INTERVAL)),
        )
        hold_max_duration = self._hold_max_duration()
        with self.mouse_controller._input_lock:
            screen_position = self._position_cursor_for_upgrade_hold(x, y)
            if screen_position is None:
                self.consecutive_failed_cycles += 1
                return State.OPEN_BOXES

            logger.info("Press-and-holding upgrade station at (%s, %s)", x, y)
            hold_completed, hold_stopped_by_max_duration, hold_elapsed = (
                self._hold_upgrade_station_until_complete(
                    screen_position,
                    base_threshold,
                    relaxed_threshold,
                    hold_check_interval,
                    hold_max_duration,
                )
            )
        if not hold_completed:
            self.consecutive_failed_cycles += 1
            return State.OPEN_BOXES

        # The hold actually completed: real progress, so clear the streak here rather than at
        # handle_search_upgrade_station's "found" branch (see comment there).
        self.consecutive_failed_cycles = 0
        self.holds_completed += 1
        self.box_only_passes = 0  # a purchase is progress: the dead-loop guard starts over
        self.idle_scrolls = 0

        if hold_stopped_by_max_duration:
            logger.info("Upgrade station hold released by max duration fallback after %.2fs", hold_elapsed)
        else:
            logger.info("Upgrade station no longer detected after %.2fs hold", hold_elapsed)
        self.upgrade_station_pos = None

        if not self._click_idle():
            return State.OPEN_BOXES
        if not self._sleep(config.STATE_DELAY):
            return State.OPEN_BOXES
        self.upgrade_station_counter += 1
        if self.upgrade_station_counter >= config.UPGRADES_BEFORE_STATS:
            self.upgrade_station_counter = 0
            logger.info("Upgrade counter reached stats threshold")
            return State.UPGRADE_STATS

        return State.OPEN_BOXES

    def handle_upgrade_stats(self) -> State:
        if not self._click_idle():
            return State.OPEN_BOXES

        screenshot = self.window_capture.capture(max_y=config.EXTENDED_SEARCH_Y)
        limited_screenshot = screenshot[: config.MAX_SEARCH_Y, :]

        found, _, _, _ = self._find_new_level_button(limited_screenshot)
        if found:
            return State.TRANSITION_LEVEL

        best_stats_match = self._find_best_zone_red_icon(
            screenshot,
            config.STATS_RED_ICON_THRESHOLD,
            config.UPGRADE_RED_ICON_X_MIN,
            config.UPGRADE_RED_ICON_X_MAX,
            config.UPGRADE_RED_ICON_Y_MIN,
            config.UPGRADE_RED_ICON_Y_MAX,
            min_distance=80,
        )

        if best_stats_match is None:
            logger.info("No stats icon detected")
            return State.SCROLL

        self.cycle_counter = 0
        self.idle_scrolls = 0
        logger.info("Stats icon found, upgrading")
        opened = self.mouse_controller.click(
            config.STATS_UPGRADE_BUTTON_POS[0],
            config.STATS_UPGRADE_BUTTON_POS[1],
            relative=True,
        )
        if not opened:
            return State.OPEN_BOXES

        if not self._sleep(config.STATE_DELAY):
            return State.OPEN_BOXES
        clicked = self.mouse_controller.spam_click_at(
            config.STATS_UPGRADE_POS[0],
            config.STATS_UPGRADE_POS[1],
            duration=config.STATS_UPGRADE_CLICK_DURATION,
            click_delay=config.STATS_UPGRADE_CLICK_DELAY,
            mouse_down_duration=config.STATS_UPGRADE_CLICK_DELAY,
            mouse_up_duration=0.0,
            relative=True,
        )
        if not clicked:
            logger.warning("Stats upgrade spam-click failed at %s", config.STATS_UPGRADE_POS)
            return State.OPEN_BOXES

        if not self._click_idle():
            return State.OPEN_BOXES
        logger.info("Stats upgrade completed")
        return State.OPEN_BOXES

    def handle_open_boxes(self) -> State:
        if not self._click_idle():
            return State.OPEN_BOXES

        limited_screenshot = self.window_capture.capture(max_y=config.BOX_SEARCH_Y)

        found, _, _, _ = self._find_new_level_button(limited_screenshot)
        if found:
            logger.info("New level found while opening boxes")
            return State.TRANSITION_LEVEL

        box_threshold = config.BOX_THRESHOLD
        box_candidates = self._collect_box_candidates(limited_screenshot, box_threshold)
        if not box_candidates and self._scrcpy_miss_recovery_sleep(config.SCRCPY_BOX_MISS_RECOVERY_DELAY):
            limited_screenshot = self.window_capture.capture(max_y=config.BOX_SEARCH_Y)
            found, _, _, _ = self._find_new_level_button(limited_screenshot)
            if found:
                logger.info("New level found while opening boxes after SCRCPY recovery")
                return State.TRANSITION_LEVEL
            box_candidates = self._collect_box_candidates(limited_screenshot, box_threshold)

        merged_boxes = self.image_matcher.suppress_overlaps(box_candidates, 0.20)

        if self._stall_probe_pending:
            self._stall_probe_pending = False
            self._log_box_near_misses(limited_screenshot, len(merged_boxes))

        boxes_found = self._click_box_candidates(merged_boxes)

        if boxes_found > 0:
            self.work_done = True
            self.cycle_counter = 0
            self.idle_scrolls = 0
            self.boxes_opened_total += boxes_found
            logger.info("Opened %s boxes", boxes_found)
            # Deliberate deviation from v1 parity (v1 never scrolls while boxes keep opening):
            # live v2 logs showed a stuck "box" re-clicked for hours, work_done re-arming every
            # pass, so SCROLL (and with it every off-screen upgrade) was starved and the
            # same-state watchdog never fired because the state changes each tick. Zero-box passes
            # do not reset the count, so an alternating stuck target can't dodge it.
            # ponytail: interleave only. A UI-fixed stuck target still burns (K-1)/K of passes;
            # upgrade path: ignore a position clicked K times in a row (positions are logged on
            # trip via _recent_box_clicks).
            self.box_only_passes += 1
            if self.box_only_passes >= max(2, int(config.MAX_BOX_ONLY_PASSES)):
                self.box_only_passes = 0
                self.box_guard_trips += 1
                logger.warning(
                    "Box loop guard: %s box passes without a scroll or upgrade; forcing a "
                    "scroll. Last clicked positions: %s",
                    config.MAX_BOX_ONLY_PASSES,
                    list(self._recent_box_clicks),
                )
                return State.SCROLL

        return self._next_state_after_box_cycle()

    def handle_scroll(self) -> State:
        if not self._click_idle():
            return State.SCROLL
        if not self._perform_oscillating_scroll_step():
            return State.SCROLL
        self.cycle_counter = 0
        self.box_only_passes = 0
        self.idle_scrolls += 1
        self._maybe_alert_stall()
        return State.FIND_RED_ICONS

    def handle_check_new_level(self) -> State:
        if not self._click_idle():
            logger.warning("Failed to clear focus before confirming the new level")
            return State.CHECK_NEW_LEVEL
        if not self._sleep(config.FOCUS_SETTLE_DELAY):
            return State.CHECK_NEW_LEVEL
        if not self._new_level_red_icon_verified:
            if not self._perform_new_level_verification_scroll():
                logger.warning("Failed to perform verification scroll for new level red icon")
                return State.CHECK_NEW_LEVEL

            confirmed_icon = self._find_new_level_red_icon()
            if confirmed_icon is None:
                logger.info("New level red icon disappeared before visual confirmation; resuming main flow")
                self._new_level_red_icon_verified = False
                self._reset_search_cycle()
                return State.FIND_RED_ICONS

            self._new_level_red_icon_verified = True
            logger.info(
                "New level red icon confirmed at (%s, %s) [%.3f]",
                confirmed_icon[1],
                confirmed_icon[2],
                confirmed_icon[0],
            )

        opened = self.mouse_controller.click(
            config.NEW_LEVEL_BUTTON_POS[0],
            config.NEW_LEVEL_BUTTON_POS[1],
            relative=True,
        )
        if not opened:
            logger.warning("Failed to click the new level button at %s", config.NEW_LEVEL_BUTTON_POS)
            return State.CHECK_NEW_LEVEL
        if not self._sleep(config.NEW_LEVEL_CONFIRMATION_DELAY):
            return State.CHECK_NEW_LEVEL
        advanced = self.mouse_controller.click(
            config.LEVEL_TRANSITION_POS[0],
            config.LEVEL_TRANSITION_POS[1],
            relative=True,
        )
        if not advanced:
            logger.warning("Failed to click the level transition button at %s", config.LEVEL_TRANSITION_POS)
            return State.CHECK_NEW_LEVEL
        if not self._sleep(config.LEVEL_TRANSITION_SECONDARY_SETTLE_DELAY):
            return State.WAIT_FOR_UNLOCK
        logger.info("Verified red-icon level transition submitted; awaiting unlock confirmation")
        return State.WAIT_FOR_UNLOCK

    def handle_transition_level(self) -> State:
        if not self._click_idle():
            return State.TRANSITION_LEVEL

        max_attempts = max(1, int(config.NEW_LEVEL_SEARCH_ATTEMPTS))
        for attempt in range(max_attempts):
            limited_screenshot = self.window_capture.capture(max_y=config.MAX_SEARCH_Y)

            found, _, x, y = self._find_new_level_button(limited_screenshot)
            if found:
                logger.info("New level button found at (%s, %s) on attempt %s", x, y, attempt + 1)
                clicked = self.mouse_controller.click(x, y, relative=True)
                if not clicked:
                    logger.warning("New level button click failed at (%s, %s)", x, y)
                    return State.CHECK_NEW_LEVEL
                if self._sleep(config.LEVEL_TRANSITION_SETTLE_DELAY):
                    logger.info("New-level transition submitted; awaiting unlock confirmation")
                return State.WAIT_FOR_UNLOCK

            if attempt < max_attempts - 1 and not self._sleep(config.NEW_LEVEL_SEARCH_INTERVAL):
                return State.TRANSITION_LEVEL

        logger.warning("New level button not found after %s attempts", max_attempts)
        self._reset_search_cycle()
        return State.FIND_RED_ICONS

    def handle_wait_for_unlock(self) -> State:
        if not self._click_idle():
            logger.warning("Failed to clear focus while waiting for the next unlock")
            return State.WAIT_FOR_UNLOCK
        if not self._sleep(config.FOCUS_SETTLE_DELAY):
            return State.WAIT_FOR_UNLOCK

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
        template_pair = self._template("unlock")
        if template_pair is None:
            if not self._sleep(config.UNLOCK_SEARCH_INTERVAL):
                return State.WAIT_FOR_UNLOCK
            return State.WAIT_FOR_UNLOCK

        template, mask = template_pair
        found, confidence, x, y = self.image_matcher.find_template(
            screenshot,
            template,
            mask=mask,
            threshold=config.UNLOCK_THRESHOLD,
            template_name="unlock",
        )
        if not found:
            if not self._sleep(config.UNLOCK_SEARCH_INTERVAL):
                return State.WAIT_FOR_UNLOCK
            return State.WAIT_FOR_UNLOCK

        logger.info("Unlock button found at (%s, %s) [%.3f]", x, y, confidence)
        if self.mouse_controller.is_in_forbidden_zone(x, y, relative=True):
            logger.warning("Unlock button found in forbidden zone at (%s, %s)", x, y)
            if not self._sleep(config.UNLOCK_SEARCH_INTERVAL):
                return State.WAIT_FOR_UNLOCK
            return State.WAIT_FOR_UNLOCK
        if not self.mouse_controller.click(x, y, relative=True):
            logger.warning("Unlock button click failed at (%s, %s)", x, y)
            return State.WAIT_FOR_UNLOCK

        elapsed = self._record_level_completion()
        logger.info(
            "Level %s confirmed by unlock. Time spent: %.1fs",
            self.total_levels_completed,
            elapsed,
        )
        if not self._sleep(config.UNLOCK_SETTLE_DELAY):
            return State.FIND_RED_ICONS
        return State.FIND_RED_ICONS
