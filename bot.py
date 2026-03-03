import json
import os
import time
import logging
import threading
from datetime import datetime
from contextlib import contextmanager

from window_capture import WindowCapture
from image_matcher import ImageMatcher
from mouse_controller import MouseController
from state_machine import StateMachine, State
from telegram_notifier import TelegramNotifier
from asset_scanner import AssetScanner
from search_utils import OscillatingSearcher
import config

logger = logging.getLogger(__name__)


class LevelCompleteInterrupt(Exception):
    """Raised when a new level is detected to immediately halt standard gameplay."""
    pass


class BotStoppedInterrupt(Exception):
    """Raised when the bot is stopped to immediately halt all actions."""
    pass


from optimization import AdaptiveTuner, VisionOptimizer, VisionPersistence, HistoricalLearner

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
        self._red_template_hit_counts = {}
        self._red_template_priority = []
        self._red_template_last_seen = {}
        self._red_template_decay_window = max(1.0, float(getattr(config, "RED_ICON_STABILITY_CACHE_TTL", 0.22)))
        self.running = False
        self.red_icon_cycle_count = 0
        self.red_icons = []
        self.current_red_icon_index = 0
        self.wait_for_unlock_attempts = 0
        self.max_wait_for_unlock_attempts = getattr(config, "WAIT_FOR_UNLOCK_MAX_ATTEMPTS", 50)
        
        # Legacy directional scroll state removed.
        # One-Scroll Rule: execute_oscillating_search() is the only scroll driver.
        self.work_done = False
        self.cycle_counter = 0
        self.red_icon_processed_count = 0
        self.forbidden_icon_scrolls = 0
        self.scroll_offset_units = 0  # Tracks vertical drift from center
        
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

        self.forbidden_zones = [
            (zone["x_min"], zone["x_max"], zone["y_min"], zone["y_max"])
            for zone in getattr(config, "FORBIDDEN_ZONES", [])
        ]

        self.overlay = None
        
        logger.info("Bot initialized successfully")

    def _record_new_level_interrupt(self, source, confidence, x, y):
        # ... existing logic ...
        if self._should_ignore_new_level_signal(source=source):
            logger.debug(
                "Ignoring background %s signal while in %s",
                source,
                self.state_machine.get_state_name(),
            )
            return

        self._new_level_interrupt = {
            "source": source,
            "confidence": confidence,
            "x": x,
            "y": y,
            "timestamp": time.monotonic(),
        }
        self._new_level_event.set()
        self._mark_restaurant_completed(source, confidence)

    def check_critical_interrupts(self, raise_exception=True):
        """
        The Global Safety Check (Deep Hook).
        Returns True if a critical interrupt is pending, or raises an exception to halt actions.
        """
        # 0. Re-entrancy Guard: Suppress interrupts during priority overrides
        if getattr(self, "_suppress_interrupts", False):
            return False

        # 1. Check if bot was stopped by user
        if not self.running:
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
            time.sleep(duration)

    def _consume_new_level_interrupt(self):
        if not self._new_level_event.is_set():
            return None
        interrupt = self._new_level_interrupt
        self._new_level_event.clear()
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
            if time.monotonic() - self._last_transition_time < 5.0:
                return True
                
        return False

    def _monitor_new_level(self):
        interval = config.NEW_LEVEL_MONITOR_INTERVAL
        while not self._new_level_monitor_stop.is_set():
            # YIELD PRIORITY: Back off if main thread is in critical interaction
            active_state = self.state_machine.get_state()
            if active_state in (State.CLICK_RED_ICON, State.HOLD_UPGRADE_STATION, State.TRANSITION_LEVEL):
                time.sleep(max(interval, 0.2)) # Significant back-off duration
                continue

            if self._new_level_event.is_set():
                time.sleep(max(interval, 0.01))
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
                time.sleep(max(interval, 0.01))
                continue

            found, confidence, x, y = self._detect_new_level(
                screenshot=limited_screenshot,
                max_y=config.MAX_SEARCH_Y,
                force=True,
            )
            if found:
                logger.info("Background monitor: new level button detected at (%s, %s)", x, y)
                self._record_new_level_interrupt("new level button", confidence, x, y)

            time.sleep(max(interval, 0.01))

    def _apply_tuning(self):
        if not self.tuner.enabled:
            return
        self.mouse_controller.click_delay = self.tuner.click_delay
        self.mouse_controller.move_delay = self.tuner.move_delay

    def _click_idle(self, wait_after=True):
        now = time.monotonic()
        cooldown = getattr(config, "IDLE_CLICK_COOLDOWN", 0.0)
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
        cooldown = max(0.0, float(getattr(config, "FORBIDDEN_ZONE_SCROLL_REENTRY_COOLDOWN", 0.0)))
        wait_remaining = (self._last_forbidden_scroll_time + cooldown) - now
        if wait_remaining > 0:
            logger.debug(
                "Applying forbidden-zone scroll redirect cooldown %.3fs",
                wait_remaining,
            )
            self._sleep_with_interrupt(wait_remaining)
        self._last_forbidden_scroll_time = time.monotonic()
        return True

    def _is_asset_click_safe(self, asset_name, x, y):
        precheck_delay = max(0.0, float(getattr(config, "ASSET_BOUNDARY_PRECHECK_DELAY", 0.0)))
        confirm_delay = max(0.0, float(getattr(config, "ASSET_BOUNDARY_CONFIRM_DELAY", 0.0)))

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

        if current_state == State.FIND_RED_ICONS and self._no_red_scroll_cycle_pending:
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
            if self._no_red_scroll_cycle_pending:
                logger.info("Clearing deferred no-red scroll due to pending level transition interrupt")
                self._no_red_scroll_cycle_pending = False
            self._click_new_level_override(
                source=interrupt["source"],
                x=interrupt["x"],
                y=interrupt["y"]
            )
            return State.TRANSITION_LEVEL

        priority_screenshot = self._capture(max_y=config.MAX_SEARCH_Y)
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
            if self._no_red_scroll_cycle_pending:
                logger.info("Clearing deferred no-red scroll due to immediate level transition")
                self._no_red_scroll_cycle_pending = False
            self._click_new_level_override(source=source)
            return State.TRANSITION_LEVEL

        return None

    def _enforce_state_min_interval(self):
        state = self.state_machine.get_state_name()
        per_state = getattr(config, "STATE_MIN_INTERVALS", {})
        min_interval = float(per_state.get(state, getattr(config, "STATE_MIN_INTERVAL_DEFAULT", 0.0)))
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

        ttl = max(0.01, float(getattr(config, "RED_ICON_STABILITY_CACHE_TTL", 0.22)))
        radius = max(4, int(getattr(config, "RED_ICON_STABILITY_RADIUS", 14)))
        min_hits = max(1, int(getattr(config, "RED_ICON_STABILITY_MIN_HITS", 2)))
        max_history = max(2, int(getattr(config, "RED_ICON_STABILITY_MAX_HISTORY", 10)))
        immediate_threshold = getattr(config, "RED_ICON_PIXEL_THRESHOLD", 50) * 1.5 # Super solid trigger
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
        ttl = float(getattr(config, "FORBIDDEN_BLACKOUT_DURATION", 2.5))
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
        cooldown = getattr(config, "NEW_LEVEL_OVERRIDE_COOLDOWN", 0.0)
        if cooldown > 0 and now - self._last_new_level_override_time < cooldown:
            logger.debug("Priority override: skipping click sequence due to cooldown")
            return
        
        with self.suppress_interrupts():
            self._last_new_level_override_time = now

            self._mark_restaurant_completed(source or "priority override")

            # Use detected coordinates if provided, otherwise fallback to config
            click_x = x if x is not None else config.NEW_LEVEL_BUTTON_POS[0]
            click_y = y if y is not None else config.NEW_LEVEL_BUTTON_POS[1]

            logger.info(
                "Priority override: clicking %s at (%s, %s)",
                source or "button",
                click_x,
                click_y,
            )
            self.mouse_controller.click(click_x, click_y, relative=True)

            button_delay = getattr(config, "NEW_LEVEL_BUTTON_DELAY", 0.02)
            if button_delay > 0:
                time.sleep(button_delay)

            logger.info(
                "Priority override: clicking new level position at (%s, %s)",
                config.NEW_LEVEL_POS[0],
                config.NEW_LEVEL_POS[1],
            )
            self.mouse_controller.click(
                config.NEW_LEVEL_POS[0],
                config.NEW_LEVEL_POS[1],
                relative=True,
            )
            
            if button_delay > 0:
                time.sleep(button_delay)

            logger.info(
                "Priority override: clicking level transition position at (%s, %s)",
                config.LEVEL_TRANSITION_POS[0],
                config.LEVEL_TRANSITION_POS[1],
            )
            self.mouse_controller.click(
                config.LEVEL_TRANSITION_POS[0],
                config.LEVEL_TRANSITION_POS[1],
                relative=True,
            )

    def _capture(self, max_y=None, force=False):
        cache_key = max_y if max_y is not None else "full"
        cached = self._capture_cache.get(cache_key)
        now = time.monotonic()
        if not force and cached and now - cached[0] <= self._capture_cache_ttl:
            return cached[1]

        with self._capture_lock:
            frame = self.window_capture.capture(max_y=max_y)
        self._capture_cache[cache_key] = (now, frame)
        return frame

    def _clear_capture_cache(self):
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
            if self._new_level_event.is_set():
                interrupt = self._new_level_interrupt
                if interrupt and self._should_ignore_new_level_signal(source=interrupt.get("source")):
                    self._new_level_event.clear()
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
        interval = max(0.01, config.NEW_LEVEL_INTERRUPT_INTERVAL)
        
        while time.monotonic() < target_time:
            # Check for critical interrupts (like Level Complete)
            self.check_critical_interrupts()
            
            # 1. Check for Level Transition (High Priority)
            if self._should_interrupt_for_new_level(force=True):
                return State.TRANSITION_LEVEL
                
            # 2. Check for Red Icons
            screenshot = self._capture(max_y=config.MAX_SEARCH_Y, force=True)
            red_icons = self._detect_red_icons_in_view(screenshot, max_y=config.MAX_SEARCH_Y)
            
            # Implementation: Immediate Trigger for high density
            immediate_threshold = getattr(config, "RED_ICON_PIXEL_THRESHOLD", 50) * 1.5
            
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
                return State.TRANSITION_LEVEL
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
        if not force and cached["max_y"] == target_max_y and now - cached["timestamp"] <= self._capture_cache_ttl:
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
        if not force and cached["max_y"] == target_max_y and now - cached["timestamp"] <= cache_ttl:
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

        if screenshot.shape[0] < required_bottom and max_y is None:
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

    def _is_red_icon_present_at(self, x, y, screenshot=None, threshold_override=None):
        if not self.available_red_icon_templates:
            return False

        target_screenshot = screenshot if screenshot is not None else self._capture(max_y=config.MAX_SEARCH_Y)

        if config.RED_ICON_COLOR_CHECK:
            show_mask = getattr(config, "DEBUG_VISION", False)
            pixel_count = self.image_matcher.count_red_pixels(
                target_screenshot, x, y,
                size=getattr(config, "RED_ICON_COLOR_SAMPLE_SIZE", 24),
                show_mask=show_mask
            )
            if pixel_count < getattr(config, "RED_ICON_PIXEL_THRESHOLD", 50):
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
            ):
                return True

        return False

    def _passes_red_color_gate(self, screenshot, x, y, relaxed=False):
        """
        Requirement: Pixel Density Trigger.
        Counts red pixels in ROI after dilation.
        Returns: (passed, pixel_count)
        """
        show_mask = getattr(config, "DEBUG_VISION", False)
        pixel_count = self.image_matcher.count_red_pixels(
            screenshot, x, y, 
            size=getattr(config, "RED_ICON_COLOR_SAMPLE_SIZE", 24),
            show_mask=show_mask
        )
        
        threshold = getattr(config, "RED_ICON_PIXEL_THRESHOLD", 50)
        if relaxed:
            threshold = int(threshold * 0.7)
            
        return pixel_count >= threshold, pixel_count

    def _segregate_assets(self, detections):
        """
        Action Step 1 & 4: Segregate detections and pad execution delays.
        Categorizes coordinates into safe_assets and forbidden_assets.
        'Slow is Smooth, Smooth is Fast' - Deliberately sort coordinates before action.
        """
        # Step 4: Pad the Execution Delays
        delay = getattr(config, "ASSET_SEGREGATION_DELAY", 0.04)
        if delay > 0:
            time.sleep(delay)
            
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
        ttl = float(getattr(config, "FORBIDDEN_BLACKOUT_DURATION", 2.5))
        radius = int(getattr(config, "RED_ICON_STABILITY_RADIUS", 14))
        
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

        max_per_scan = max(1, int(getattr(config, "RED_ICON_MAX_PER_SCAN", 1)))
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
            return State.TRANSITION_LEVEL

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
            return State.TRANSITION_LEVEL
        if clicked == -1:
            return State.SCROLL
        return None

    def execute_oscillating_search(self):
        """
        Principal Architect Refactor: Uses the new OscillatingSearcher class 
        to execute a strict 5-step Scan-First protocol.
        """
        # Execute cycle with 3 distinct callback layers
        target_state = self.searcher.execute_cycle(
            check_priority=self.check_priority_targets,
            check_main_target=self.check_main_success,
            check_fallbacks=self.check_fallbacks
        )
        
        if target_state:
            # Cycle cooldown if found
            cooldown = getattr(config, "OSCILLATION_CYCLE_COOLDOWN", 0)
            if cooldown > 0:
                time.sleep(cooldown)
            return target_state
        
        # Exhausted retries -> return to base scanning
        return State.FIND_RED_ICONS


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
            all_stations = self.image_matcher.find_all_templates(
                screenshot,
                template,
                mask=mask,
                threshold=upgrade_threshold,
                template_name="upgradeStation-all"
            )
            
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
                if self._redirect_forbidden_asset_to_scroll("Upgrade Station", forbidden_stations[0][1], forbidden_stations[0][2]):
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
            found_boxes = self.image_matcher.find_all_templates(
                screenshot,
                template,
                mask=mask,
                threshold=box_threshold,
                template_name=box_name
            )
            for b_conf, b_x, b_y in found_boxes:
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
            self._no_red_scroll_cycle_pending = True
            logger.info(
                "Fallback scan summary: clicked %s target(s) [upgrade_station=%s, boxes=%s]; scheduling no-red scroll cycle",
                clicked_targets,
                clicked_upgrade_station,
                clicked_box,
            )

        return clicked_targets

        if clicked_targets > 0:
            self._no_red_scroll_cycle_pending = True
            logger.info(
                "Fallback scan summary: clicked %s target(s) [upgrade_station=%s, boxes=%s]; scheduling no-red scroll cycle",
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

        decay_window = max(1.0, float(getattr(config, "RED_ICON_STABILITY_CACHE_TTL", self._red_template_decay_window)))
        scored = []
        for name, count in self._red_template_hit_counts.items():
            last_seen = self._red_template_last_seen.get(name, now)
            age = max(0.0, now - last_seen)
            freshness = max(0.1, 1.0 - min(1.0, age / decay_window))
            score = count * freshness
            scored.append((name, score))

        scored.sort(key=lambda item: item[1], reverse=True)
        limit = max(1, getattr(config, "RED_ICON_PRIORITY_TEMPLATE_LIMIT", 8))
        self._red_template_priority = [name for name, _ in scored[:limit]]

    def _build_available_red_icon_templates(self):
        available = []
        for template_name in self.red_icon_templates:
            if template_name in self.templates:
                template, mask = self.templates[template_name]
                available.append((template_name, template, mask))
        return available

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
            cooldown = max(0.0, float(getattr(config, "FORBIDDEN_ZONE_SCROLL_REENTRY_COOLDOWN", 0.0)))
            wait_remaining = (self._last_forbidden_scroll_time + cooldown) - now
            if wait_remaining > 0:
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

        # STEP 4: No targets (Fallback scan then search)
        self.check_fallbacks()
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
        pre_delay = max(0.0, float(getattr(config, "FORBIDDEN_ZONE_DETECTION_PRE_DELAY", 0.0)))
        post_delay = max(0.0, float(getattr(config, "FORBIDDEN_ZONE_DETECTION_POST_DELAY", 0.0)))
        ticks = max(1, int(getattr(config, "FORBIDDEN_ZONE_DEBOUNCE_TICKS", 1)))
        required_consensus = max(
            1,
            min(
                ticks,
                int(getattr(config, "FORBIDDEN_ZONE_DEBOUNCE_REQUIRED_CONSENSUS", ticks)),
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
            return State.OPEN_BOXES
        
        confidence, x, y = self.red_icons[self.current_red_icon_index]
        limited_screenshot = self._capture(max_y=config.MAX_SEARCH_Y, force=True)
        
        # Calculate relaxed threshold for verification (matching search cycle logic)
        base_threshold = (
            self.vision_optimizer.red_icon_threshold
            if self.vision_optimizer.enabled
            else config.RED_ICON_THRESHOLD
        )
        relaxed_threshold = max(0.0, base_threshold - 0.04) # Match SCROLL_RED_ICON_THRESHOLD_DROP approx
        
        if not self._is_red_icon_present_at(x, y, screenshot=limited_screenshot, threshold_override=relaxed_threshold):
            logger.info(
                "Red icon no longer present at (%s, %s); skipping click",
                x,
                y,
            )
            self.current_red_icon_index += 1
            if self.current_red_icon_index < len(self.red_icons):
                return State.CLICK_RED_ICON
            return State.FIND_RED_ICONS

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
            return State.TRANSITION_LEVEL
        if not is_safe:
            logger.warning(f"Red icon click blocked - position with offset ({click_x}, {click_y}) is in forbidden zone")
            self._add_to_blackout(x, y) # Blacklist the original detection point
            if self._redirect_forbidden_asset_to_scroll("Red Icon", click_x, click_y):
                return State.SCROLL
            
            if self._new_level_event.is_set():
                return State.TRANSITION_LEVEL
                
            self.current_red_icon_index += 1
            return State.CLICK_RED_ICON if self.current_red_icon_index < len(self.red_icons) else State.OPEN_BOXES
        
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
                if self._redirect_forbidden_asset_to_scroll("Red Icon", click_x, click_y):
                    return State.SCROLL

            self.current_red_icon_index += 1
            return State.CLICK_RED_ICON if self.current_red_icon_index < len(self.red_icons) else State.OPEN_BOXES
        
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
                return State.TRANSITION_LEVEL
            return self.handle_search_upgrade_station(current_state)

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
                    return State.TRANSITION_LEVEL
        
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
            return State.TRANSITION_LEVEL
        if not is_safe:
            logger.warning("Upgrade station position is in forbidden zone; redirecting to oscillating search")
            if self._redirect_forbidden_asset_to_scroll("Upgrade Station", x, y):
                return State.SCROLL
            return State.FIND_RED_ICONS
        
        logger.info("Holding upgrade station click...")

        start_time = time.monotonic()
        
        # Use the hold action - it's now interrupt-aware via the MouseController global hook
        self.mouse_controller.hold_at(
            x, y, 
            duration=config.UPGRADE_HOLD_DURATION, 
            relative=True
        )

        elapsed_time = time.monotonic() - start_time
        logger.info(f"Clicking complete: hold duration {elapsed_time:.1f}s")
        
        self._click_idle()
        if config.IDLE_CLICK_SETTLE_DELAY > 0:
            if self._sleep_with_interrupt(config.IDLE_CLICK_SETTLE_DELAY):
                return State.TRANSITION_LEVEL
        
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
            return State.SCROLL

        self.vision_optimizer.update_stats_upgrade_confidence(stats_confidence)
        
        logger.info("✓ Stats icon found, upgrading")
        self.mouse_controller.click(config.STATS_UPGRADE_BUTTON_POS[0], config.STATS_UPGRADE_BUTTON_POS[1], relative=True)
        # Use standard non-interruptible sleep
        self.sleep(config.STATE_DELAY)
        
        start_time = time.monotonic()
        next_click_time = start_time
        while time.monotonic() - start_time < config.STATS_UPGRADE_CLICK_DURATION:
            self.mouse_controller.click(
                config.STATS_UPGRADE_POS[0],
                config.STATS_UPGRADE_POS[1],
                relative=True,
                wait_after=False,
            )
            
            # Use standard non-interruptible sleep
            sleep_duration = max(0, next_click_time + config.STATS_UPGRADE_CLICK_DELAY - time.monotonic())
            if sleep_duration > 0:
                time.sleep(sleep_duration)
            
            next_click_time = max(
                next_click_time + config.STATS_UPGRADE_CLICK_DELAY,
                time.monotonic()
            )
        
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
            return State.TRANSITION_LEVEL
        
        box_names = ["box1", "box2", "box3", "box4", "box5"]
        boxes_found = 0
        
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
                    if self.mouse_controller.is_in_forbidden_zone(x, y):
                        logger.debug(f"{box_name} in forbidden zone, skipping")
                    else:
                        self.mouse_controller.click(x, y, relative=True)
                        boxes_found += 1
                        self.vision_optimizer.update_box_confidence(confidence)
                else:
                    self.vision_optimizer.update_box_miss()
        
        if self._should_interrupt_for_new_level(
            max_y=config.MAX_SEARCH_Y,
            force=True,
        ):
            logger.info("New level detected while opening boxes")
            return State.TRANSITION_LEVEL
        
        if boxes_found > 0:
            logger.info(f"🎁 Opened {boxes_found} boxes")
            self.work_done = True
        
        if self.upgrade_found_in_cycle:
            logger.info("✓ Upgrade found → Staying in area")
            self.upgrade_found_in_cycle = False
            self.cycle_counter = 0
            return State.FIND_RED_ICONS
        
        self.cycle_counter += 1
        
        if self.consecutive_failed_cycles >= 3:
            logger.info(f"⚠ {self.consecutive_failed_cycles} failed → Force scroll")
            self.consecutive_failed_cycles = 0
            self.cycle_counter = 0
            return State.SCROLL
        
        if self.cycle_counter >= 2:
            logger.info(f"➡ Cycle {self.cycle_counter}/2 done → Scrolling")
            self.cycle_counter = 0
            return State.SCROLL
        else:
            return State.FIND_RED_ICONS
    
    def handle_scroll(self, current_state):
        self.check_critical_interrupts()
        self._click_idle()
        
        # 1. DRIFT CORRECTION: If we are not at center (due to interrupt), return to center first.
        # This ensures the IOS pattern always starts from a known reference point.
        if abs(self.scroll_offset_units) > 0.01:
            logger.info(f"Drift detected ({self.scroll_offset_units:.2f} units). Correcting to center before search.")
            # If offset is positive (DOWN), we need to scroll UP (direction=1)
            # If offset is negative (UP), we need to scroll DOWN (direction=-1)
            direction_int = 1 if self.scroll_offset_units > 0 else -1
            correction_dist = abs(self.scroll_offset_units)
            
            # Perform correction using the new searcher's single source of truth
            self.searcher.perform_scroll(
                direction=direction_int,
                distance_ratio=correction_dist,
                duration=config.SCROLL_DURATION
            )
            return State.FIND_RED_ICONS

        limited_screenshot = self._capture(max_y=config.MAX_SEARCH_Y)

        if self._should_interrupt_for_new_level(
            screenshot=limited_screenshot,
            max_y=config.MAX_SEARCH_Y,
            force=True,
        ):
            logger.info("New level detected before scroll, transitioning")
            return State.TRANSITION_LEVEL
        
        # We now rely entirely on the Incremental Oscillating Search pattern
        # when the bot enters the SCROLL state (which happens when no icons are found).
        logger.info("Executing Incremental Oscillating Search")
        return self.execute_oscillating_search()
    
    def handle_check_new_level(self, current_state):
        """
        Requirement: Priority Interrupt (Blocking Operation).
        Executes the strictly linear level transition sequence without interruption.
        """
        self._new_level_event.clear() # Clear the interrupt signal
        self._click_idle()
        logger.info(">>> PRIORITY INTERRUPT: Level Transition Sequence Started")

        # 1. First, check if the Travel button is ALREADY visible (pop-up open)
        found, conf, x, y = self._detect_new_level(force=False)
        
        if found and y < 600: # If it's the center Travel button
            logger.info("City travel pop-up already open. Clicking detected button at (%s, %s)", x, y)
            self.mouse_controller.click(x, y, relative=True)
        else:
            # STEP 1: Halt & Click 1 (Acknowledge Level Completion - Bottom Left)
            logger.info("Step 1: Clicking new level button acknowledgment at %s", config.NEW_LEVEL_BUTTON_POS)
            self.mouse_controller.click(config.NEW_LEVEL_BUTTON_POS[0], config.NEW_LEVEL_BUTTON_POS[1], relative=True)

            # STEP 2: Animation Buffer (Wait for City Travel UI)
            buffer_time = getattr(config, "TRANSITION_POST_CLICK_DELAY", 0.8)
            logger.info("Step 2: Animation Buffer (%ss)", buffer_time)
            time.sleep(buffer_time)

            # STEP 3: Click 2 (Confirm Travel - Center)
            # We try to detect the exact position again for precision
            found_nl, conf_nl, x_nl, y_nl = self._detect_new_level(force=True)
            if found_nl:
                logger.info("Step 3: Clicking detected travel button at (%s, %s)", x_nl, y_nl)
                self.mouse_controller.click(x_nl, y_nl, relative=True)
            else:
                logger.info("Step 3: Clicking config travel positions (backup)")
                self.mouse_controller.click(config.NEW_LEVEL_POS[0], config.NEW_LEVEL_POS[1], relative=True)
                time.sleep(0.1)
                self.mouse_controller.click(config.LEVEL_TRANSITION_POS[0], config.LEVEL_TRANSITION_POS[1], relative=True)
        
        # Final stabilization wait
        time.sleep(getattr(config, "NEW_LEVEL_FOLLOWUP_DELAY", 0.3))

        # STEP 4: State Commitment
        logger.info(">>> PRIORITY INTERRUPT Complete. Entering Transition State.")
        return State.TRANSITION_LEVEL
    
    def handle_transition_level(self, current_state):
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
                
                # Use fixed config positions as requested
                self.mouse_controller.click(config.NEW_LEVEL_BUTTON_POS[0], config.NEW_LEVEL_BUTTON_POS[1], relative=True)

                button_delay = getattr(config, "NEW_LEVEL_BUTTON_DELAY", 0.02)
                if button_delay > 0:
                    time.sleep(button_delay)

                logger.info(f"Clicking new level position at {config.NEW_LEVEL_POS}")
                self.mouse_controller.click(config.NEW_LEVEL_POS[0], config.NEW_LEVEL_POS[1], relative=True)
                
                if button_delay > 0:
                    time.sleep(button_delay)

                logger.info(f"Clicking level transition position at {config.LEVEL_TRANSITION_POS}")
                self.mouse_controller.click(config.LEVEL_TRANSITION_POS[0], config.LEVEL_TRANSITION_POS[1], relative=True)

                if config.TRANSITION_POST_CLICK_DELAY > 0:
                    if self._sleep_with_interrupt(config.TRANSITION_POST_CLICK_DELAY):
                        return State.TRANSITION_LEVEL

                return self._finalize_transition()
            
            if attempt < max_attempts - 1:
                if config.TRANSITION_RETRY_DELAY > 0:
                    if self._sleep_with_interrupt(config.TRANSITION_RETRY_DELAY):
                        return State.TRANSITION_LEVEL
        
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
        logger.debug(
            "Resetting search cycle (%s): scroll_offset_units=%.2f",
            reason,
            self.scroll_offset_units,
        )
        self.scroll_offset_units = 0
    
    def handle_wait_for_unlock(self, current_state):
        """
        Requirement: High-Frequency Visual Polling.
        Minimizes time between station availability and interaction to near-zero.
        """
        self._click_idle()
        max_duration = 5.0  # Smart Timeout: 5 seconds
        start_time = time.monotonic()
        polling_interval = 0.05  # 50ms tight loop
        
        logger.info(">>> HOT LOOP: Polling for Unlock button (Max 5s duration)...")

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
                    # We wait 100ms for UI to register and then re-verify
                    time.sleep(0.1)
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
            time.sleep(polling_interval)
            
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
            return
            
        self.running = False
        self._new_level_monitor_stop.set()
        if self._new_level_monitor_thread and self._new_level_monitor_thread.is_alive():
            self._new_level_monitor_thread.join(timeout=1.0)
        self.historical_learner.stop()
        if self.overlay:
            self.overlay.stop()
            self.overlay = None
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
