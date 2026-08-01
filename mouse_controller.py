import atexit
import ctypes
import logging
import math
import random
import threading
import time
from collections.abc import Callable
from typing import Any

import pywintypes
import win32api
import win32con
import win32gui

import config

logger = logging.getLogger(__name__)

_timer_resolution_enabled = False
Point = tuple[int, int]
WindowBounds = tuple[int, int, int, int]
RelativeScreenPosition = tuple[int, int, int, int, int, int]
ForbiddenZone = tuple[str, int, int, int, int | None]


def _disable_timer_resolution() -> None:
    global _timer_resolution_enabled
    if not _timer_resolution_enabled:
        return
    try:
        ctypes.windll.winmm.timeEndPeriod(1)
    except Exception:
        return
    _timer_resolution_enabled = False


def _enable_timer_resolution() -> None:
    global _timer_resolution_enabled
    if _timer_resolution_enabled:
        return
    try:
        result = ctypes.windll.winmm.timeBeginPeriod(1)
    except Exception:
        return
    if result == 0:
        _timer_resolution_enabled = True
        atexit.register(_disable_timer_resolution)


def _coerce_duration(duration: Any, default: float = 0.0) -> float:
    try:
        value = float(duration)
    except (TypeError, ValueError):
        value = float(default)
    if not math.isfinite(value):
        value = float(default)
    return max(0.0, value)


def precise_sleep(duration: Any) -> None:
    duration = _coerce_duration(duration)
    if duration <= 0:
        return
    sleep_until(time.perf_counter() + duration)


def _wait_until_next_deadline_slice(remaining: float, stop_event: threading.Event | None) -> bool:
    if remaining > 0.004:
        wait_time = min(remaining - 0.002, 0.05)
        if stop_event is None:
            time.sleep(wait_time)
            return True
        return not stop_event.wait(wait_time)
    if remaining > 0.001:
        time.sleep(0)
    return True


def sleep_until(deadline: float, stop_event: threading.Event | None = None) -> bool:
    while True:
        if stop_event is not None and stop_event.is_set():
            return False
        remaining = float(deadline) - time.perf_counter()
        if remaining <= 0:
            return stop_event is None or not stop_event.is_set()
        if not _wait_until_next_deadline_slice(remaining, stop_event):
            return False


def wait_event(stop_event: threading.Event | None, duration: Any) -> bool:
    duration = _coerce_duration(duration)
    if stop_event is None:
        precise_sleep(duration)
        return True
    if duration <= 0:
        return not stop_event.is_set()
    return sleep_until(time.perf_counter() + duration, stop_event)


_enable_timer_resolution()


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
        interrupt_check: Callable[[], bool] | None = None,
    ) -> None:
        self._hwnd_source = hwnd_source
        self._interrupt_check = interrupt_check
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
        self.input_retry_count = 3
        self.input_retry_delay = 0.05
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

    @staticmethod
    def _coerce_non_negative_int(value: Any, default: int = 0) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            try:
                number = int(default)
            except (TypeError, ValueError):
                number = 0
        return max(0, number)

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
        if self._interrupt_check is not None and self._interrupt_check():
            return False
        if self.is_target_foreground():
            return True
        logger.warning("Rejected global mouse input because the target window is not foreground")
        return False

    def get_window_position(self) -> Point:
        win_x, win_y, _, _ = self.get_window_bounds()
        return win_x, win_y

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

    def _sleep_before_input_retry(self, attempt: int) -> None:
        if attempt < self.input_retry_count:
            precise_sleep(self.input_retry_delay)

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
                precise_sleep(0.001)
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
            self._sleep_before_input_retry(attempt)
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
            if (
                not releases_left_button
                and self._resolve_screen_position(
                    screen_x,
                    screen_y,
                    relative=False,
                )
                != (screen_x, screen_y)
            ):
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
                if attempt < self.input_retry_count:
                    precise_sleep(self.input_retry_delay)
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
        return [
            (
                "FORBIDDEN_CLICK zone",
                config.FORBIDDEN_CLICK_X_MIN,
                config.FORBIDDEN_CLICK_X_MAX,
                config.FORBIDDEN_CLICK_Y_MIN,
                None,
            ),
            (
                "FORBIDDEN_ZONE_1",
                config.FORBIDDEN_ZONE_1_X_MIN,
                config.FORBIDDEN_ZONE_1_X_MAX,
                config.FORBIDDEN_ZONE_1_Y_MIN,
                config.FORBIDDEN_ZONE_1_Y_MAX,
            ),
            (
                "FORBIDDEN_ZONE_2",
                config.FORBIDDEN_ZONE_2_X_MIN,
                config.FORBIDDEN_ZONE_2_X_MAX,
                config.FORBIDDEN_ZONE_2_Y_MIN,
                config.FORBIDDEN_ZONE_2_Y_MAX,
            ),
            (
                "FORBIDDEN_ZONE_3",
                config.FORBIDDEN_ZONE_3_X_MIN,
                config.FORBIDDEN_ZONE_3_X_MAX,
                config.FORBIDDEN_ZONE_3_Y_MIN,
                config.FORBIDDEN_ZONE_3_Y_MAX,
            ),
            (
                "FORBIDDEN_ZONE_4",
                config.FORBIDDEN_ZONE_4_X_MIN,
                config.FORBIDDEN_ZONE_4_X_MAX,
                config.FORBIDDEN_ZONE_4_Y_MIN,
                config.FORBIDDEN_ZONE_4_Y_MAX,
            ),
            (
                "FORBIDDEN_ZONE_5",
                config.FORBIDDEN_ZONE_5_X_MIN,
                config.FORBIDDEN_ZONE_5_X_MAX,
                config.FORBIDDEN_ZONE_5_Y_MIN,
                config.FORBIDDEN_ZONE_5_Y_MAX,
            ),
        ]

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

        for forbidden_zone in self._configured_forbidden_zones():
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

    def move_to(self, x: Any, y: Any, relative: bool = True) -> bool:
        with self._input_lock:
            screen_pos = self._resolve_screen_position(x, y, relative=relative)
            if screen_pos is None:
                return False

            screen_x, screen_y = screen_pos
            if not self._set_cursor_pos(screen_x, screen_y):
                return False
            if self.move_delay > 0:
                precise_sleep(self.move_delay)
            logger.debug("Cursor moved to (%s, %s)", screen_x, screen_y)
            return True

    def _hover_before_click(self) -> None:
        if not self.hover_enabled:
            return
        duration = self._coerce_non_negative_float(self.hover_duration, 0.0)
        if duration > 0:
            precise_sleep(duration)

    def _click_down_up_delay(self, default: float = 0.02) -> float:
        return self._get_mouse_down_duration(default)

    def _get_mouse_down_duration(self, default: float = 0.02) -> float:
        return self._coerce_non_negative_float(self.mouse_down_duration, default)

    def _get_mouse_up_duration(self, default: float = 0.0) -> float:
        return self._coerce_non_negative_float(self.mouse_up_duration, default)

    @staticmethod
    def _interruptible_delay(duration: Any, interrupt_check: Callable[[], bool] | None = None) -> bool:
        deadline = time.perf_counter() + max(0.0, float(duration))
        while True:
            if interrupt_check and interrupt_check():
                return False
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                return True
            precise_sleep(min(remaining, 0.005))

    @staticmethod
    def _interruptible_sleep_until(deadline: float, interrupt_check: Callable[[], bool] | None = None) -> bool:
        while True:
            if interrupt_check and interrupt_check():
                return False
            remaining = float(deadline) - time.perf_counter()
            if remaining <= 0:
                return True
            precise_sleep(min(remaining, 0.005))

    def _left_down_at_screen(
        self,
        screen_x: Any,
        screen_y: Any,
        duration: Any = None,
        interrupt_check: Callable[[], bool] | None = None,
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
        if wait_time > 0:
            if interrupt_check:
                if not self._interruptible_delay(wait_time, interrupt_check):
                    self._best_effort_left_up(screen_x, screen_y)
                    return False
            else:
                precise_sleep(wait_time)
        return True

    def _left_up_at_screen(
        self,
        screen_x: Any,
        screen_y: Any,
        duration: Any = None,
        interrupt_check: Callable[[], bool] | None = None,
    ) -> bool:
        if not self._mouse_event(win32con.MOUSEEVENTF_LEFTUP, screen_x, screen_y):
            self._best_effort_left_up(screen_x, screen_y)
            return False
        wait_time = (
            self._get_mouse_up_duration()
            if duration is None
            else self._coerce_non_negative_float(duration, self.mouse_up_duration)
        )
        if wait_time > 0:
            if interrupt_check:
                return self._interruptible_delay(wait_time, interrupt_check)
            precise_sleep(wait_time)
        return True

    def _left_click_at_screen(
        self,
        screen_x: Any,
        screen_y: Any,
        down_duration: Any = None,
        up_duration: Any = None,
        interrupt_check: Callable[[], bool] | None = None,
    ) -> bool:
        if not self._left_down_at_screen(screen_x, screen_y, down_duration, interrupt_check):
            return False
        return self._left_up_at_screen(screen_x, screen_y, up_duration, interrupt_check)

    def _wait_after_click(self, delay: Any = None) -> None:
        wait_time = self.click_delay if delay is None else delay
        wait_time = self._coerce_non_negative_float(wait_time, self.click_delay)
        if wait_time > 0:
            precise_sleep(wait_time)

    def click(self, x: Any, y: Any, relative: bool = True, delay: Any = None) -> bool:
        with self._input_lock:
            last_screen_pos = None
            down_up_delay = self._click_down_up_delay(0.02)
            for _ in range(self.input_retry_count):
                screen_pos = self._resolve_screen_position(x, y, relative=relative)
                if screen_pos is None:
                    return False

                screen_x, screen_y = screen_pos
                last_screen_pos = (screen_x, screen_y)
                if not self._set_cursor_pos(screen_x, screen_y):
                    continue
                if self.move_delay > 0:
                    precise_sleep(self.move_delay)
                self._hover_before_click()

                if not self._left_click_at_screen(screen_x, screen_y, down_up_delay):
                    continue

                logger.debug("Clicked at (%s, %s)", screen_x, screen_y)
                self._wait_after_click(delay)
                return True

            if last_screen_pos is not None:
                logger.error("Click failed at (%s, %s)", last_screen_pos[0], last_screen_pos[1])
            return False

    def precise_click(self, x: Any, y: Any, relative: bool = True, delay: Any = None) -> bool:
        with self._input_lock:
            last_screen_pos = None
            down_duration = self._click_down_up_delay(0.02)
            up_duration = self._get_mouse_up_duration(0.0)
            for _ in range(self.input_retry_count):
                screen_pos = self._resolve_screen_position(x, y, relative=relative)
                if screen_pos is None:
                    return False

                screen_x, screen_y = screen_pos
                last_screen_pos = (screen_x, screen_y)
                if not self._set_cursor_pos(screen_x, screen_y):
                    continue
                if self.move_delay > 0:
                    precise_sleep(self.move_delay)
                self._hover_before_click()

                if not self._set_cursor_pos(screen_x, screen_y):
                    continue
                if not self._left_down_at_screen(screen_x, screen_y, down_duration):
                    continue
                if not self._set_cursor_pos(screen_x, screen_y):
                    self._best_effort_left_up(screen_x, screen_y)
                    continue
                if not self._left_up_at_screen(screen_x, screen_y, up_duration):
                    continue

                logger.debug("Precise-clicked at (%s, %s)", screen_x, screen_y)
                self._wait_after_click(delay)
                return True

            if last_screen_pos is not None:
                logger.error("Precise click failed at (%s, %s)", last_screen_pos[0], last_screen_pos[1])
            return False

    def double_click(self, x: Any, y: Any, relative: bool = True) -> bool:
        if not self.click(x, y, relative=relative, delay=0.05):
            return False
        return self.click(x, y, relative=relative)

    def hold_at(
        self,
        x: Any,
        y: Any,
        duration: Any = None,
        relative: bool = True,
        interrupt_check: Callable[[], bool] | None = None,
    ) -> bool:
        with self._input_lock:
            if duration is None:
                duration = 4.0
            duration = self._coerce_non_negative_float(duration, 4.0)

            screen_pos = self._resolve_screen_position(x, y, relative=relative)
            if screen_pos is None:
                return False

            screen_x, screen_y = screen_pos
            if not self._set_cursor_pos(screen_x, screen_y):
                return False
            if self.move_delay > 0:
                precise_sleep(self.move_delay)

            if not self._left_down_at_screen(screen_x, screen_y, interrupt_check=interrupt_check):
                return False
            logger.debug("Holding at (%s, %s) for %.2fs", screen_x, screen_y, duration)

            if not self._interruptible_delay(duration, interrupt_check):
                self._left_up_at_screen(screen_x, screen_y)
                return False

            if not self._left_up_at_screen(screen_x, screen_y, interrupt_check=interrupt_check):
                return False
            if self.click_delay > 0:
                precise_sleep(self.click_delay)
            return True

    def click_sequence(
        self,
        x: Any,
        y: Any,
        count: Any,
        interval: Any,
        relative: bool = True,
        interrupt_check: Callable[[], bool] | None = None,
    ) -> bool:
        with self._input_lock:
            count = self._coerce_non_negative_int(count)
            interval = max(0.0, self._coerce_non_negative_float(interval, 0.0))
            if count <= 0:
                return True

            screen_pos = self._resolve_screen_position(x, y, relative=relative)
            if screen_pos is None:
                return False

            screen_x, screen_y = screen_pos
            if not self._set_cursor_pos(screen_x, screen_y):
                return False
            if self.move_delay > 0:
                precise_sleep(self.move_delay)
            self._hover_before_click()

            down_up_delay = self._click_down_up_delay(0.008)
            first_click_at = time.perf_counter()
            for index in range(count):
                if not self._interruptible_sleep_until(first_click_at + (index * interval), interrupt_check):
                    return False
                if not self._left_click_at_screen(
                    screen_x,
                    screen_y,
                    down_duration=down_up_delay,
                    interrupt_check=interrupt_check,
                ):
                    return False

            logger.debug("Click sequence complete at (%s, %s): %s clicks", screen_x, screen_y, count)
            return True

    def _resolve_jittered_screen_position(
        self,
        base_x: int,
        base_y: int,
        jitter: int,
    ) -> Point | None:
        if jitter <= 0:
            return base_x, base_y
        target_x = base_x + random.randint(-jitter, jitter)
        target_y = base_y + random.randint(-jitter, jitter)
        jittered_position = self._resolve_screen_position(target_x, target_y, relative=False)
        if jittered_position is None:
            return None
        if not self._set_cursor_pos(jittered_position[0], jittered_position[1]):
            return None
        return jittered_position

    def _run_spam_click_loop(
        self,
        base_x: int,
        base_y: int,
        duration: float,
        click_delay: float,
        jitter: int,
        click_down_up_delay: float,
        click_up_delay: float | None,
        interrupt_check: Callable[[], bool] | None,
    ) -> int | None:
        start_time = time.perf_counter()
        end_time = start_time + duration
        next_click_at = start_time
        click_count = 0

        logger.debug(
            "Spam-clicking at (%s, %s) for %.2fs (interval=%.3fs, jitter=%s)",
            base_x,
            base_y,
            duration,
            click_delay,
            jitter,
        )

        while True:
            if interrupt_check and interrupt_check():
                logger.debug("Spam-click interrupted after %s clicks", click_count)
                return None

            now = time.perf_counter()
            if now >= end_time:
                return click_count

            if now < next_click_at:
                if not self._interruptible_sleep_until(next_click_at, interrupt_check):
                    return None
                continue

            target_position = self._resolve_jittered_screen_position(base_x, base_y, jitter)
            if target_position is None:
                return None
            target_x, target_y = target_position

            if not self._left_click_at_screen(
                target_x,
                target_y,
                down_duration=click_down_up_delay,
                up_duration=click_up_delay,
                interrupt_check=interrupt_check,
            ):
                return None

            click_count += 1
            next_click_at += click_delay

    def spam_click_at(
        self,
        x: Any,
        y: Any,
        duration: Any = None,
        click_delay: Any = None,
        jitter: Any = 0,
        relative: bool = True,
        interrupt_check: Callable[[], bool] | None = None,
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
            jitter = self._coerce_non_negative_int(jitter)

            screen_pos = self._resolve_screen_position(x, y, relative=relative)
            if screen_pos is None:
                return False

            base_x, base_y = screen_pos
            if not self._set_cursor_pos(base_x, base_y):
                return False
            if self.move_delay > 0:
                precise_sleep(self.move_delay)
            self._hover_before_click()

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
                jitter,
                click_down_up_delay,
                click_up_delay,
                interrupt_check,
            )
            if click_count is None:
                return False

            logger.debug("Spam-click complete: %s clicks", click_count)
            if self.click_delay > 0:
                precise_sleep(self.click_delay)
            return True

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
            if self.move_delay > 0:
                precise_sleep(self.move_delay)

            if not self._left_down_at_screen(screen_from_x, screen_from_y):
                return False

            steps = 20
            start_time = time.perf_counter()
            for index in range(steps + 1):
                position = index / steps
                current_x = int(screen_from_x + (screen_to_x - screen_from_x) * position)
                current_y = int(screen_from_y + (screen_to_y - screen_from_y) * position)
                if not self._set_cursor_pos(current_x, current_y):
                    self._left_up_at_screen(current_x, current_y)
                    return False
                sleep_until(start_time + ((index + 1) * (duration / steps)))

            if not self._left_up_at_screen(screen_to_x, screen_to_y):
                return False
            logger.debug("Dragged from (%s, %s) to (%s, %s)", from_x, from_y, to_x, to_y)
            if self.click_delay > 0:
                precise_sleep(self.click_delay)
            return True
