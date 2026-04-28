import logging
import math
import random
import time

import pywintypes
import win32api
import win32con
import win32gui

import config

logger = logging.getLogger(__name__)


class MouseController:
    def __init__(self, hwnd_source, click_delay=None, move_delay=None):
        self._hwnd_source = hwnd_source
        self.click_delay = self._coerce_non_negative_float(
            config.CLICK_DELAY if click_delay is None else click_delay,
            float(config.CLICK_DELAY),
        )
        self.move_delay = self._coerce_non_negative_float(
            config.MOUSE_MOVE_DELAY if move_delay is None else move_delay,
            float(config.MOUSE_MOVE_DELAY),
        )
        self.input_retry_count = 3
        self.input_retry_delay = 0.05

    @staticmethod
    def _coerce_non_negative_float(value, default=0.0):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return max(0.0, float(default))
        if not math.isfinite(number):
            return max(0.0, float(default))
        return max(0.0, number)

    def _get_hwnd(self):
        hwnd = self._hwnd_source() if callable(self._hwnd_source) else self._hwnd_source
        if not hwnd or not win32gui.IsWindow(hwnd):
            raise RuntimeError("Target window is not available")
        return hwnd

    def get_window_position(self):
        win_x, win_y, _, _ = self.get_window_bounds()
        return win_x, win_y

    def get_window_bounds(self):
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

    def _relative_from_screen(self, x, y):
        win_x, win_y, width, height = self.get_window_bounds()
        return int(x) - win_x, int(y) - win_y, win_x, win_y, width, height

    @staticmethod
    def _within_client(x, y, width, height):
        return 0 <= int(x) < int(width) and 0 <= int(y) < int(height)

    def _set_cursor_pos(self, x, y):
        screen_x = int(x)
        screen_y = int(y)
        last_exc = None
        for attempt in range(1, self.input_retry_count + 1):
            try:
                win32api.SetCursorPos((screen_x, screen_y))
                return True
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
                if attempt < self.input_retry_count:
                    time.sleep(self.input_retry_delay)
        logger.error("SetCursorPos failed at (%s, %s): %s", screen_x, screen_y, last_exc)
        return False

    def _mouse_event(self, event, x, y):
        screen_x = int(x)
        screen_y = int(y)
        last_exc = None
        for attempt in range(1, self.input_retry_count + 1):
            try:
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
                    time.sleep(self.input_retry_delay)
        logger.error("mouse_event %s failed at (%s, %s): %s", event, screen_x, screen_y, last_exc)
        return False

    def _best_effort_left_up(self, x, y):
        try:
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, int(x), int(y), 0, 0)
        except pywintypes.error:
            return False
        return True

    def is_in_forbidden_zone(self, x, y, relative=True):
        try:
            if not relative:
                x, y, _, _, _, _ = self._relative_from_screen(x, y)
        except (RuntimeError, TypeError, ValueError) as exc:
            logger.error("Cannot evaluate forbidden zone: %s", exc)
            return True

        if (
            y >= config.FORBIDDEN_CLICK_Y_MIN
            and config.FORBIDDEN_CLICK_X_MIN <= x <= config.FORBIDDEN_CLICK_X_MAX
        ):
            logger.debug("Coordinates (%s, %s) blocked - FORBIDDEN_CLICK zone", x, y)
            return True

        if (
            config.FORBIDDEN_ZONE_1_Y_MIN <= y <= config.FORBIDDEN_ZONE_1_Y_MAX
            and config.FORBIDDEN_ZONE_1_X_MIN <= x <= config.FORBIDDEN_ZONE_1_X_MAX
        ):
            logger.debug("Coordinates (%s, %s) blocked - FORBIDDEN_ZONE_1", x, y)
            return True

        if (
            config.FORBIDDEN_ZONE_2_Y_MIN <= y <= config.FORBIDDEN_ZONE_2_Y_MAX
            and config.FORBIDDEN_ZONE_2_X_MIN <= x <= config.FORBIDDEN_ZONE_2_X_MAX
        ):
            logger.debug("Coordinates (%s, %s) blocked - FORBIDDEN_ZONE_2", x, y)
            return True

        if (
            config.FORBIDDEN_ZONE_3_Y_MIN <= y <= config.FORBIDDEN_ZONE_3_Y_MAX
            and config.FORBIDDEN_ZONE_3_X_MIN <= x <= config.FORBIDDEN_ZONE_3_X_MAX
        ):
            logger.debug("Coordinates (%s, %s) blocked - FORBIDDEN_ZONE_3", x, y)
            return True

        if (
            config.FORBIDDEN_ZONE_4_Y_MIN <= y <= config.FORBIDDEN_ZONE_4_Y_MAX
            and config.FORBIDDEN_ZONE_4_X_MIN <= x <= config.FORBIDDEN_ZONE_4_X_MAX
        ):
            logger.debug("Coordinates (%s, %s) blocked - FORBIDDEN_ZONE_4", x, y)
            return True

        if (
            config.FORBIDDEN_ZONE_5_Y_MIN <= y <= config.FORBIDDEN_ZONE_5_Y_MAX
            and config.FORBIDDEN_ZONE_5_X_MIN <= x <= config.FORBIDDEN_ZONE_5_X_MAX
        ):
            logger.debug("Coordinates (%s, %s) blocked - FORBIDDEN_ZONE_5", x, y)
            return True

        return False

    def _resolve_screen_position(self, x, y, relative=True, check_forbidden=True):
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

    def move_to(self, x, y, relative=True):
        screen_pos = self._resolve_screen_position(x, y, relative=relative)
        if screen_pos is None:
            return False

        screen_x, screen_y = screen_pos
        if not self._set_cursor_pos(screen_x, screen_y):
            return False
        if self.move_delay > 0:
            time.sleep(self.move_delay)
        logger.debug("Cursor moved to (%s, %s)", screen_x, screen_y)
        return True

    def click(self, x, y, relative=True, delay=None):
        last_screen_pos = None
        for _ in range(self.input_retry_count):
            screen_pos = self._resolve_screen_position(x, y, relative=relative)
            if screen_pos is None:
                return False

            screen_x, screen_y = screen_pos
            last_screen_pos = (screen_x, screen_y)
            if not self._set_cursor_pos(screen_x, screen_y):
                continue
            if self.move_delay > 0:
                time.sleep(self.move_delay)

            down_up_delay = min(
                max(float(getattr(config, "RAPID_CLICK_DOWN_UP_DELAY", 0.02)), 0.001),
                0.02,
            )
            if not self._mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, screen_x, screen_y):
                self._best_effort_left_up(screen_x, screen_y)
                continue
            time.sleep(down_up_delay)
            if not self._mouse_event(win32con.MOUSEEVENTF_LEFTUP, screen_x, screen_y):
                self._best_effort_left_up(screen_x, screen_y)
                continue

            logger.debug("Clicked at (%s, %s)", screen_x, screen_y)
            wait_time = self.click_delay if delay is None else delay
            wait_time = self._coerce_non_negative_float(wait_time, self.click_delay)
            if wait_time > 0:
                time.sleep(wait_time)
            return True

        if last_screen_pos is not None:
            logger.error("Click failed at (%s, %s)", last_screen_pos[0], last_screen_pos[1])
        return False

    def double_click(self, x, y, relative=True):
        if not self.click(x, y, relative=relative, delay=0.05):
            return False
        return self.click(x, y, relative=relative)

    def hold_at(self, x, y, duration=None, relative=True, interrupt_check=None):
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
            time.sleep(self.move_delay)

        if not self._mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, screen_x, screen_y):
            self._best_effort_left_up(screen_x, screen_y)
            return False
        logger.debug("Holding at (%s, %s) for %.2fs", screen_x, screen_y, duration)

        end_time = time.monotonic() + duration
        while time.monotonic() < end_time:
            if interrupt_check and interrupt_check():
                self._best_effort_left_up(screen_x, screen_y)
                return False
            remaining = end_time - time.monotonic()
            if remaining > 0:
                time.sleep(min(0.05, remaining))

        if not self._mouse_event(win32con.MOUSEEVENTF_LEFTUP, screen_x, screen_y):
            self._best_effort_left_up(screen_x, screen_y)
            return False
        if self.click_delay > 0:
            time.sleep(self.click_delay)
        return True

    def spam_click_at(self, x, y, duration=None, click_delay=None, jitter=0, relative=True, interrupt_check=None):
        if duration is None:
            duration = config.SPAM_CLICK_DURATION
        if click_delay is None:
            click_delay = config.SPAM_CLICK_DELAY

        duration = self._coerce_non_negative_float(duration, config.SPAM_CLICK_DURATION)
        click_delay = max(0.001, self._coerce_non_negative_float(click_delay, config.SPAM_CLICK_DELAY))
        jitter = max(0, int(jitter))

        screen_pos = self._resolve_screen_position(x, y, relative=relative)
        if screen_pos is None:
            return False

        base_x, base_y = screen_pos
        if not self._set_cursor_pos(base_x, base_y):
            return False
        if self.move_delay > 0:
            time.sleep(self.move_delay)

        click_down_up_delay = min(
            max(float(getattr(config, "RAPID_CLICK_DOWN_UP_DELAY", 0.008)), 0.001),
            click_delay / 2.0,
        )

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
                return False

            now = time.perf_counter()
            if now >= end_time:
                break

            if now < next_click_at:
                time.sleep(min(next_click_at - now, 0.001))
                continue

            target_x = base_x
            target_y = base_y
            if jitter > 0:
                target_x += random.randint(-jitter, jitter)
                target_y += random.randint(-jitter, jitter)
                jittered_pos = self._resolve_screen_position(target_x, target_y, relative=False)
                if jittered_pos is None:
                    return False
                target_x, target_y = jittered_pos
                if not self._set_cursor_pos(target_x, target_y):
                    return False

            if not self._mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, target_x, target_y):
                self._best_effort_left_up(target_x, target_y)
                return False
            time.sleep(click_down_up_delay)
            if not self._mouse_event(win32con.MOUSEEVENTF_LEFTUP, target_x, target_y):
                self._best_effort_left_up(target_x, target_y)
                return False

            click_count += 1
            next_click_at += click_delay

        logger.debug("Spam-click complete: %s clicks", click_count)
        if self.click_delay > 0:
            time.sleep(self.click_delay)
        return True

    def drag(self, from_x, from_y, to_x, to_y, duration=None, relative=True):
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
            time.sleep(self.move_delay)

        if not self._mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, screen_from_x, screen_from_y):
            self._best_effort_left_up(screen_from_x, screen_from_y)
            return False
        time.sleep(0.02)

        steps = 20
        for index in range(steps + 1):
            position = index / steps
            current_x = int(screen_from_x + (screen_to_x - screen_from_x) * position)
            current_y = int(screen_from_y + (screen_to_y - screen_from_y) * position)
            if not self._set_cursor_pos(current_x, current_y):
                self._best_effort_left_up(current_x, current_y)
                return False
            time.sleep(duration / steps)

        if not self._mouse_event(win32con.MOUSEEVENTF_LEFTUP, screen_to_x, screen_to_y):
            self._best_effort_left_up(screen_to_x, screen_to_y)
            return False
        logger.debug("Dragged from (%s, %s) to (%s, %s)", from_x, from_y, to_x, to_y)
        if self.click_delay > 0:
            time.sleep(self.click_delay)
        return True
