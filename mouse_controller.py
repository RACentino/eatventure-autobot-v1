import logging
import math
import threading
import time
from typing import Any

import pywintypes
import win32api
import win32con
import win32gui

import config

logger = logging.getLogger(__name__)

Point = tuple[int, int]
WindowBounds = tuple[int, int, int, int]
RelativeScreenPosition = tuple[int, int, int, int, int, int]
ForbiddenZone = tuple[str, int, int, int, int | None]
DRAG_STEPS = 20

class MouseController:
    def __init__(
        self,
        hwnd_source: Any,
        click_delay: Any = None,
        move_delay: Any = None,
        mouse_down_duration: Any = None,
        mouse_up_duration: Any = None,
        hover_enabled: bool | None = None,
        hover_duration: Any = None,
        stop_event: threading.Event | None = None,
    ) -> None:
        self._hwnd_source = hwnd_source
        self._stop_event = stop_event
        self.click_delay = self._coerce_non_negative_float(
            config.CLICK_DELAY if click_delay is None else click_delay,
            float(config.CLICK_DELAY),
        )
        self.move_delay = self._coerce_non_negative_float(
            config.MOUSE_MOVE_DELAY if move_delay is None else move_delay,
            float(config.MOUSE_MOVE_DELAY),
        )
        self.mouse_down_duration = self._coerce_non_negative_float(
            config.MOUSE_DOWN_DURATION if mouse_down_duration is None else mouse_down_duration,
            float(config.MOUSE_DOWN_DURATION),
        )
        self.mouse_up_duration = self._coerce_non_negative_float(
            config.MOUSE_UP_DURATION if mouse_up_duration is None else mouse_up_duration,
            0.0,
        )
        self.hover_enabled = bool(config.HOVER_ENABLED if hover_enabled is None else hover_enabled)
        self.hover_duration = self._coerce_non_negative_float(
            config.HOVER_DURATION if hover_duration is None else hover_duration,
            0.0,
        )
        self.input_retry_count = max(1, int(config.INPUT_RETRY_COUNT))
        self.input_retry_delay = self._coerce_non_negative_float(config.INPUT_RETRY_DELAY)
        self._forbidden_zones = tuple(self._configured_forbidden_zones())
        self._input_lock = threading.RLock()

    @staticmethod
    def _coerce_non_negative_float(value: Any, default: float = 0.0) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return max(0.0, float(default))
        if not math.isfinite(number):
            return max(0.0, float(default))
        return max(0.0, number)

    def _get_hwnd(self) -> int:
        hwnd = self._hwnd_source() if callable(self._hwnd_source) else self._hwnd_source
        if not hwnd or not win32gui.IsWindow(hwnd):
            raise RuntimeError("Target window is not available")
        return hwnd

    def is_target_foreground(self) -> bool:
        try:
            return int(win32gui.GetForegroundWindow() or 0) == int(self._get_hwnd())
        except (pywintypes.error, RuntimeError, TypeError, ValueError):
            return False

    def _input_allowed(self) -> bool:
        if self._stop_event is not None and self._stop_event.is_set():
            return False
        if self.is_target_foreground():
            return True
        logger.warning("Rejected global mouse input because the target window is not foreground")
        return False

    def get_window_bounds(self) -> WindowBounds:
        try:
            hwnd = self._get_hwnd()
            rect = win32gui.GetClientRect(hwnd)
            width = int(rect[2] - rect[0])
            height = int(rect[3] - rect[1])
            if width <= 0 or height <= 0:
                raise RuntimeError(f"Target window has invalid client size: {width}x{height}")
            x, y = win32gui.ClientToScreen(hwnd, (0, 0))
            return int(x), int(y), width, height
        except pywintypes.error as exc:
            raise RuntimeError(f"Cannot read target window bounds: {exc}") from exc

    def _relative_from_screen(self, x: Any, y: Any) -> RelativeScreenPosition:
        win_x, win_y, width, height = self.get_window_bounds()
        return int(x) - win_x, int(y) - win_y, win_x, win_y, width, height

    @staticmethod
    def _within_client(x: Any, y: Any, width: Any, height: Any) -> bool:
        return 0 <= int(x) < int(width) and 0 <= int(y) < int(height)

    @staticmethod
    def _cursor_matches_position(screen_x: int, screen_y: int) -> tuple[bool, int, int]:
        current_x, current_y = win32api.GetCursorPos()
        matches = int(current_x) == screen_x and int(current_y) == screen_y
        return matches, current_x, current_y

    def _wait(self, duration: Any) -> bool:
        delay = self._coerce_non_negative_float(duration)
        if self._stop_event is None:
            time.sleep(delay)
            return True
        return not self._stop_event.wait(delay)

    def _wait_until(self, deadline: float) -> bool:
        return self._wait(max(0.0, float(deadline) - time.perf_counter()))

    def _sleep_before_input_retry(self, attempt: int) -> bool:
        return attempt >= self.input_retry_count or self._wait(self.input_retry_delay)

    def _set_cursor_pos(self, x: Any, y: Any) -> bool:
        screen_x = int(x)
        screen_y = int(y)
        if self.is_in_forbidden_zone(screen_x, screen_y, relative=False):
            logger.warning("Rejected cursor move into forbidden zone at (%s, %s)", screen_x, screen_y)
            return False
        last_exc = None
        for attempt in range(1, self.input_retry_count + 1):
            if not self._input_allowed():
                return False
            try:
                win32api.SetCursorPos((screen_x, screen_y))
                if not self._wait(0.001):
                    return False
                matches, current_x, current_y = self._cursor_matches_position(screen_x, screen_y)
                if matches:
                    return True
                last_exc = RuntimeError(f"cursor settled at ({current_x}, {current_y})")
            except pywintypes.error as exc:
                last_exc = exc
                logger.warning(
                    "SetCursorPos failed at (%s, %s) on attempt %s/%s: %s",
                    screen_x,
                    screen_y,
                    attempt,
                    self.input_retry_count,
                    exc,
                )
            if not self._sleep_before_input_retry(attempt):
                return False
        logger.error("SetCursorPos failed at (%s, %s): %s", screen_x, screen_y, last_exc)
        return False

    def _mouse_event(self, event: int, x: Any, y: Any) -> bool:
        screen_x = int(x)
        screen_y = int(y)
        releases_left_button = bool(event & win32con.MOUSEEVENTF_LEFTUP)
        last_exc = None
        for attempt in range(1, self.input_retry_count + 1):
            if not releases_left_button and not self._input_allowed():
                return False
            try:
                cursor_matches = True
                current_x = screen_x
                current_y = screen_y
                if not releases_left_button:
                    cursor_matches, current_x, current_y = self._cursor_matches_position(
                        screen_x,
                        screen_y,
                    )
                if not cursor_matches:
                    logger.warning(
                        "Rejected mouse input because the cursor moved to (%s, %s)",
                        current_x,
                        current_y,
                    )
                    return False
                win32api.mouse_event(event, screen_x, screen_y, 0, 0)
                return True
            except pywintypes.error as exc:
                last_exc = exc
                logger.warning(
                    "mouse_event %s failed at (%s, %s) on attempt %s/%s: %s",
                    event,
                    screen_x,
                    screen_y,
                    attempt,
                    self.input_retry_count,
                    exc,
                )
                if not self._sleep_before_input_retry(attempt):
                    return False
        logger.error("mouse_event %s failed at (%s, %s): %s", event, screen_x, screen_y, last_exc)
        return False

    def _best_effort_left_up(self, x: Any, y: Any) -> bool:
        try:
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, int(x), int(y), 0, 0)
        except pywintypes.error:
            return False
        return True

    @staticmethod
    def _configured_forbidden_zones() -> list[ForbiddenZone]:
        zones: list[ForbiddenZone] = [
            (
                "FORBIDDEN_CLICK zone",
                config.FORBIDDEN_CLICK_X_MIN,
                config.FORBIDDEN_CLICK_X_MAX,
                config.FORBIDDEN_CLICK_Y_MIN,
                None,
            ),
        ]
        for zone_index, (x_min, x_max, y_min, y_max) in enumerate(
            config.NUMBERED_FORBIDDEN_ZONE_BOUNDS, start=1
        ):
            zones.append(
                (f"FORBIDDEN_ZONE_{zone_index}", x_min, x_max, y_min, y_max)
            )
        return zones

    @staticmethod
    def _position_in_forbidden_zone(x: int, y: int, forbidden_zone: ForbiddenZone) -> bool:
        _, x_minimum, x_maximum, y_minimum, y_maximum = forbidden_zone
        if y_maximum is None:
            return y >= y_minimum and x_minimum <= x <= x_maximum
        return y_minimum <= y <= y_maximum and x_minimum <= x <= x_maximum

    def is_in_forbidden_zone(self, x: Any, y: Any, relative: bool = True) -> bool:
        try:
            if not relative:
                x, y, _, _, _, _ = self._relative_from_screen(x, y)
            relative_x = int(x)
            relative_y = int(y)
        except (RuntimeError, TypeError, ValueError) as exc:
            logger.error("Cannot evaluate forbidden zone: %s", exc)
            return True

        for forbidden_zone in self._forbidden_zones:
            zone_name = forbidden_zone[0]
            if self._position_in_forbidden_zone(relative_x, relative_y, forbidden_zone):
                logger.debug("Coordinates (%s, %s) blocked - %s", relative_x, relative_y, zone_name)
                return True

        return False

    def _resolve_screen_position(
        self,
        x: Any,
        y: Any,
        relative: bool = True,
        check_forbidden: bool = True,
    ) -> Point | None:
        try:
            if relative:
                win_x, win_y, width, height = self.get_window_bounds()
                rel_x = int(x)
                rel_y = int(y)
            else:
                rel_x, rel_y, win_x, win_y, width, height = self._relative_from_screen(x, y)

            if not self._within_client(rel_x, rel_y, width, height):
                logger.warning(
                    "Rejected input outside target window: relative=(%s, %s), bounds=%sx%s",
                    rel_x,
                    rel_y,
                    width,
                    height,
                )
                return None

            if check_forbidden and self.is_in_forbidden_zone(rel_x, rel_y, relative=True):
                return None

            return int(win_x + rel_x), int(win_y + rel_y)
        except (RuntimeError, TypeError, ValueError) as exc:
            logger.error("Cannot resolve screen position: %s", exc)
            return None

    def _hover_before_click(self) -> bool:
        if not self.hover_enabled:
            return True
        duration = self._coerce_non_negative_float(self.hover_duration, 0.0)
        return self._wait(duration)

    def _click_down_up_delay(self, default: float = 0.02) -> float:
        return self._get_mouse_down_duration(default)

    def _get_mouse_down_duration(self, default: float = 0.02) -> float:
        return self._coerce_non_negative_float(self.mouse_down_duration, default)

    def _get_mouse_up_duration(self, default: float = 0.0) -> float:
        return self._coerce_non_negative_float(self.mouse_up_duration, default)

    def _left_down_at_screen(
        self,
        screen_x: Any,
        screen_y: Any,
        duration: Any = None,
    ) -> bool:
        if self.is_in_forbidden_zone(screen_x, screen_y, relative=False):
            logger.warning("Rejected click in forbidden zone at (%s, %s)", screen_x, screen_y)
            return False
        try:
            current_x, current_y = win32api.GetCursorPos()
        except pywintypes.error as exc:
            logger.error("Cannot verify cursor position before click: %s", exc)
            return False
        if self.is_in_forbidden_zone(current_x, current_y, relative=False):
            logger.warning("Rejected click at forbidden cursor position (%s, %s)", current_x, current_y)
            return False
        if not self._mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, screen_x, screen_y):
            self._best_effort_left_up(screen_x, screen_y)
            return False
        wait_time = (
            self._get_mouse_down_duration()
            if duration is None
            else self._coerce_non_negative_float(duration, self.mouse_down_duration)
        )
        if wait_time > 0 and not self._wait(wait_time):
            self._best_effort_left_up(screen_x, screen_y)
            return False
        return True

    def _left_up_at_screen(
        self,
        screen_x: Any,
        screen_y: Any,
        duration: Any = None,
    ) -> bool:
        if not self._mouse_event(win32con.MOUSEEVENTF_LEFTUP, screen_x, screen_y):
            self._best_effort_left_up(screen_x, screen_y)
            return False
        wait_time = (
            self._get_mouse_up_duration()
            if duration is None
            else self._coerce_non_negative_float(duration, self.mouse_up_duration)
        )
        return wait_time <= 0 or self._wait(wait_time)

    def _left_click_at_screen(
        self,
        screen_x: Any,
        screen_y: Any,
        down_duration: Any = None,
        up_duration: Any = None,
    ) -> bool:
        with self._input_lock:
            pressed = self._left_down_at_screen(screen_x, screen_y, down_duration)
            if not pressed:
                return False
            released = False
            try:
                released = self._left_up_at_screen(screen_x, screen_y, up_duration)
                return released
            finally:
                if not released:
                    self._best_effort_left_up(screen_x, screen_y)

    def _wait_after_click(self, delay: Any = None) -> bool:
        wait_time = self.click_delay if delay is None else delay
        wait_time = self._coerce_non_negative_float(wait_time, self.click_delay)
        return self._wait(wait_time)

    def click(self, x: Any, y: Any, relative: bool = True, delay: Any = None) -> bool:
        with self._input_lock:
            screen_pos = self._resolve_screen_position(x, y, relative=relative)
            if screen_pos is None:
                return False
            screen_x, screen_y = screen_pos
            down_up_delay = self._click_down_up_delay(0.02)
            if not self._set_cursor_pos(screen_x, screen_y):
                return False
            if not self._wait(self.move_delay) or not self._hover_before_click():
                return False
            if not self._left_click_at_screen(screen_x, screen_y, down_up_delay):
                logger.error("Click failed at (%s, %s)", screen_x, screen_y)
                return False
            logger.debug("Clicked at (%s, %s)", screen_x, screen_y)
            return self._wait_after_click(delay)

    def precise_click(self, x: Any, y: Any, relative: bool = True, delay: Any = None) -> bool:
        with self._input_lock:
            screen_pos = self._resolve_screen_position(x, y, relative=relative)
            if screen_pos is None:
                return False
            screen_x, screen_y = screen_pos
            down_duration = self._click_down_up_delay(0.02)
            up_duration = self._get_mouse_up_duration(0.0)
            if not self._set_cursor_pos(screen_x, screen_y):
                return False
            if not self._wait(self.move_delay) or not self._hover_before_click():
                return False
            if not self._left_down_at_screen(screen_x, screen_y, down_duration):
                return False
            released = False
            try:
                if self._set_cursor_pos(screen_x, screen_y):
                    released = self._left_up_at_screen(screen_x, screen_y, up_duration)
            finally:
                if not released:
                    self._best_effort_left_up(screen_x, screen_y)
            if not released:
                logger.error("Precise click failed at (%s, %s)", screen_x, screen_y)
                return False
            logger.debug("Precise-clicked at (%s, %s)", screen_x, screen_y)
            return self._wait_after_click(delay)

    def _run_spam_click_loop(
        self,
        base_x: int,
        base_y: int,
        duration: float,
        click_delay: float,
        click_down_up_delay: float,
        click_up_delay: float | None,
    ) -> int | None:
        start_time = time.perf_counter()
        end_time = start_time + duration
        next_click_at = start_time
        click_count = 0

        logger.debug(
            "Spam-clicking at (%s, %s) for %.2fs (interval=%.3fs)",
            base_x,
            base_y,
            duration,
            click_delay,
        )

        while True:
            if self._stop_event is not None and self._stop_event.is_set():
                logger.debug("Spam-click interrupted after %s clicks", click_count)
                return None

            now = time.perf_counter()
            if now >= end_time:
                return click_count

            if now < next_click_at:
                if not self._wait_until(next_click_at):
                    return None
                continue

            if not self._left_click_at_screen(
                base_x,
                base_y,
                down_duration=click_down_up_delay,
                up_duration=click_up_delay,
            ):
                return None

            click_count += 1
            next_click_at = time.perf_counter() + click_delay

    def spam_click_at(
        self,
        x: Any,
        y: Any,
        duration: Any = None,
        click_delay: Any = None,
        relative: bool = True,
        mouse_down_duration: Any = None,
        mouse_up_duration: Any = None,
    ) -> bool:
        with self._input_lock:
            if duration is None:
                duration = config.SPAM_CLICK_DURATION
            if click_delay is None:
                click_delay = config.SPAM_CLICK_DELAY

            duration = self._coerce_non_negative_float(duration, config.SPAM_CLICK_DURATION)
            click_delay = max(0.001, self._coerce_non_negative_float(click_delay, config.SPAM_CLICK_DELAY))

            screen_pos = self._resolve_screen_position(x, y, relative=relative)
            if screen_pos is None:
                return False

            base_x, base_y = screen_pos
            if not self._set_cursor_pos(base_x, base_y):
                return False
            if not self._wait(self.move_delay) or not self._hover_before_click():
                return False

            click_down_up_delay = (
                self._click_down_up_delay(0.008)
                if mouse_down_duration is None
                else self._coerce_non_negative_float(mouse_down_duration, click_delay)
            )
            click_up_delay = (
                None
                if mouse_up_duration is None
                else self._coerce_non_negative_float(mouse_up_duration, 0.0)
            )
            click_count = self._run_spam_click_loop(
                base_x,
                base_y,
                duration,
                click_delay,
                click_down_up_delay,
                click_up_delay,
            )
            if click_count is None:
                return False

            logger.debug("Spam-click complete: %s clicks", click_count)
            return self._wait(self.click_delay)

    def _move_drag_cursor(
        self,
        screen_from_x: int,
        screen_from_y: int,
        screen_to_x: int,
        screen_to_y: int,
        duration: float,
    ) -> tuple[bool, int, int]:
        started_at = time.perf_counter()
        current_x = screen_from_x
        current_y = screen_from_y
        step_delay = duration / DRAG_STEPS
        for index in range(DRAG_STEPS + 1):
            position = index / DRAG_STEPS
            current_x = int(screen_from_x + (screen_to_x - screen_from_x) * position)
            current_y = int(screen_from_y + (screen_to_y - screen_from_y) * position)
            if not self._set_cursor_pos(current_x, current_y):
                return False, current_x, current_y
            deadline = started_at + ((index + 1) * step_delay)
            if index < DRAG_STEPS and not self._wait_until(deadline):
                return False, current_x, current_y
        return True, current_x, current_y

    def drag(
        self,
        from_x: Any,
        from_y: Any,
        to_x: Any,
        to_y: Any,
        duration: Any = None,
        relative: bool = True,
    ) -> bool:
        with self._input_lock:
            if duration is None:
                duration = config.SCROLL_DURATION
            duration = max(0.01, self._coerce_non_negative_float(duration, config.SCROLL_DURATION))

            from_pos = self._resolve_screen_position(from_x, from_y, relative=relative)
            to_pos = self._resolve_screen_position(to_x, to_y, relative=relative)
            if from_pos is None or to_pos is None:
                return False
            screen_from_x, screen_from_y = from_pos
            screen_to_x, screen_to_y = to_pos

            if not self._set_cursor_pos(screen_from_x, screen_from_y):
                return False
            if not self._wait(self.move_delay):
                return False

            if not self._left_down_at_screen(screen_from_x, screen_from_y):
                return False

            released = False
            release_x = screen_from_x
            release_y = screen_from_y
            try:
                moved, release_x, release_y = self._move_drag_cursor(
                    screen_from_x,
                    screen_from_y,
                    screen_to_x,
                    screen_to_y,
                    duration,
                )
                if not moved:
                    return False
                released = self._left_up_at_screen(screen_to_x, screen_to_y)
            finally:
                if not released:
                    self._best_effort_left_up(release_x, release_y)
            if not released:
                return False
            logger.debug("Dragged from (%s, %s) to (%s, %s)", from_x, from_y, to_x, to_y)
            return self._wait(self.click_delay)
