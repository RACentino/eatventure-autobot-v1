import ctypes
import win32api
import win32con
import win32gui
import time
import logging
import threading
import config
from ctypes import wintypes

logger = logging.getLogger(__name__)

_INPUT_MOUSE = 0
_ULONG_PTR = wintypes.WPARAM
_USER32 = ctypes.WinDLL("user32", use_last_error=True)


class _MouseInput(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", _ULONG_PTR),
    )


class _InputUnion(ctypes.Union):
    _fields_ = (("mi", _MouseInput),)


class _Input(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = (
        ("type", wintypes.DWORD),
        ("union", _InputUnion),
    )


_SEND_INPUT = _USER32.SendInput
_SEND_INPUT.argtypes = (wintypes.UINT, ctypes.POINTER(_Input), ctypes.c_int)
_SEND_INPUT.restype = wintypes.UINT


class MouseController:
    def __init__(self, hwnd, click_delay=None, move_delay=None):
        self.hwnd = hwnd
        self.click_delay = config.CLICK_DELAY if click_delay is None else click_delay
        self.move_delay = config.MOUSE_MOVE_DELAY if move_delay is None else move_delay
        self.interrupt_callback = None # Set by bot to check for high-priority interrupts
        self._last_click_time = 0.0
        self._last_cursor_pos = None
        self._last_drag_time = 0.0
        self._mouse_action_lock = threading.RLock()

    def _check_interrupts(self):
        """Calls the guard function. Returns True if an interrupt is pending.

        The bot's check_critical_interrupts (with raise_exception=True, the default)
        will raise LevelCompleteInterrupt directly — so in the normal flow, this
        method never returns True because the exception propagates out.  When the
        callback is invoked with raise_exception=False (e.g. inside drag interrupt
        checks), we return True so the caller can abort its operation gracefully.
        """
        if self.interrupt_callback and self.interrupt_callback():
            return True
        return False

    def _sleep(self, duration):
        """Helper to sleep while remaining interrupt-aware."""
        self._check_interrupts()
        if duration > 0:
            time.sleep(duration)

    @staticmethod
    def _seconds_to_ns(duration_seconds):
        return max(0, int(round(float(duration_seconds) * 1_000_000_000)))

    @staticmethod
    def _compute_next_click_deadline(previous_deadline_ns, click_start_ns, interval_ns):
        return max(previous_deadline_ns + interval_ns, click_start_ns + interval_ns)

    def _rapid_click_hold_ns(self, click_interval):
        requested_hold = max(0.0, float(config.RAPID_CLICK_DOWN_UP_DELAY))
        if click_interval <= 0:
            return self._seconds_to_ns(requested_hold)

        # Keep the button dwell shorter than the target interval so the scheduler
        # can honor sub-50 ms cadences without back-to-back overlap.
        max_hold = max(0.0, click_interval * 0.5)
        return self._seconds_to_ns(min(requested_hold, max_hold))

    def _wait_until_precise(self, deadline_ns, interrupt_check=None):
        spin_threshold_ns = self._seconds_to_ns(config.RAPID_CLICK_SPIN_THRESHOLD)

        while True:
            self._check_interrupts()
            if interrupt_check and interrupt_check():
                return False

            remaining_ns = deadline_ns - time.perf_counter_ns()
            if remaining_ns <= 0:
                return True

            if remaining_ns > spin_threshold_ns:
                sleep_ns = remaining_ns - spin_threshold_ns
                time.sleep(sleep_ns / 1_000_000_000)

    def _send_input_mouse_button(self, flags):
        input_event = _Input(
            type=_INPUT_MOUSE,
            mi=_MouseInput(
                0,
                0,
                0,
                flags,
                0,
                _ULONG_PTR(0),
            ),
        )
        sent = _SEND_INPUT(1, ctypes.byref(input_event), ctypes.sizeof(_Input))
        if sent != 1:
            raise ctypes.WinError(ctypes.get_last_error())

    def _prepare_rapid_click_target(self, screen_x, screen_y):
        if not self._validate_pre_click_target(screen_x, screen_y):
            logger.warning(
                "Blocked rapid-click setup at (%s, %s): forbidden-zone pre-check failed",
                int(screen_x),
                int(screen_y),
            )
            return False

        travel_distance = self._estimate_cursor_distance(screen_x, screen_y)

        if self._should_move_cursor(screen_x, screen_y):
            self._move_cursor(screen_x, screen_y)

        self._ensure_cursor_at_target(screen_x, screen_y)
        self._correct_cursor_position(screen_x, screen_y)
        self._stabilize_before_click(screen_x, screen_y, distance_override=travel_distance)

        if not self.is_safe_to_click(screen_x, screen_y, relative=False):
            logger.warning(
                "Blocked rapid-click setup at (%s, %s): forbidden-zone final gate failed",
                int(screen_x),
                int(screen_y),
            )
            return False

        self._last_cursor_pos = (int(screen_x), int(screen_y))
        return True

    def _send_precise_click(self, click_hold_ns, interrupt_check=None):
        self._check_interrupts()
        if interrupt_check and interrupt_check():
            return False

        self._send_input_mouse_button(win32con.MOUSEEVENTF_LEFTDOWN)

        if click_hold_ns > 0:
            release_deadline_ns = time.perf_counter_ns() + click_hold_ns
            if not self._wait_until_precise(
                release_deadline_ns,
                interrupt_check=interrupt_check,
            ):
                self._send_input_mouse_button(win32con.MOUSEEVENTF_LEFTUP)
                self._last_click_time = time.monotonic()
                return False

        self._send_input_mouse_button(win32con.MOUSEEVENTF_LEFTUP)
        self._last_click_time = time.monotonic()
        return True

    def _resolve_screen_position(self, x, y, relative=True, check_forbidden=True):
        screen_x, screen_y = self._translate_to_monitor_space(x, y, relative=relative)

        if check_forbidden and not self._validate_pre_click_target(screen_x, screen_y):
            return None

        return self._clamp_to_screen(int(screen_x), int(screen_y))

    def _translate_to_monitor_space(self, x, y, relative=True):
        if relative:
            win_x, win_y = self.get_window_position()
            return float(win_x) + float(x), float(win_y) + float(y)
        return float(x), float(y)

    def _zone_to_monitor_space(self, zone, window_origin):
        coord_space = str(zone.get("coordinate_space", "image")).lower()
        x_min = float(zone["x_min"])
        x_max = float(zone["x_max"])
        y_min = float(zone["y_min"])
        y_max = float(zone["y_max"])

        if coord_space in {"image", "window", "relative"}:
            win_x, win_y = window_origin
            return (
                x_min + float(win_x),
                x_max + float(win_x),
                y_min + float(win_y),
                y_max + float(win_y),
            )

        if coord_space in {"monitor", "screen", "absolute"}:
            return x_min, x_max, y_min, y_max

        logger.warning(
            "Unknown coordinate_space '%s' for forbidden zone '%s'; assuming image space",
            coord_space,
            zone.get("name", "unnamed"),
        )
        win_x, win_y = window_origin
        return x_min + float(win_x), x_max + float(win_x), y_min + float(win_y), y_max + float(win_y)

    def _clamp_to_screen(self, screen_x, screen_y):
        width = max(1, win32api.GetSystemMetrics(0))
        height = max(1, win32api.GetSystemMetrics(1))
        clamped_x = max(0, min(int(screen_x), width - 1))
        clamped_y = max(0, min(int(screen_y), height - 1))
        if clamped_x != int(screen_x) or clamped_y != int(screen_y):
            logger.warning(
                "Clamped cursor target from (%s, %s) to (%s, %s)",
                screen_x,
                screen_y,
                clamped_x,
                clamped_y,
            )
        return clamped_x, clamped_y

    def _send_click(self, screen_x, screen_y, down_up_delay=None, prevalidated=False):
        if not prevalidated and not self._validate_pre_click_target(screen_x, screen_y):
            logger.warning(
                "Blocked click dispatch at (%s, %s): forbidden-zone pre-check failed",
                int(screen_x),
                int(screen_y),
            )
            return False

        retries = max(1, int(config.MOUSE_CLICK_RETRY_COUNT))
        settle_retry_delay = max(0.0, float(config.MOUSE_CLICK_RETRY_SETTLE_DELAY))

        for attempt in range(retries):
            travel_distance = self._estimate_cursor_distance(screen_x, screen_y)

            if self._should_move_cursor(screen_x, screen_y):
                self._move_cursor(screen_x, screen_y)

            self._ensure_cursor_at_target(screen_x, screen_y)
            self._correct_cursor_position(screen_x, screen_y)
            self._stabilize_before_click(screen_x, screen_y, distance_override=travel_distance)
            current = win32api.GetCursorPos()
            tolerance = config.MOUSE_POSITION_TOLERANCE
            if abs(current[0] - screen_x) <= tolerance and abs(current[1] - screen_y) <= tolerance:
                break

            win32api.SetCursorPos((int(screen_x), int(screen_y)))
            self._last_cursor_pos = (int(screen_x), int(screen_y))
            if attempt < retries - 1 and settle_retry_delay > 0:
                self._sleep(settle_retry_delay)

        self._ensure_min_click_interval()

        if not prevalidated and not self._validate_pre_click_target(screen_x, screen_y):
            logger.warning(
                "Blocked click dispatch at (%s, %s): forbidden-zone final gate failed",
                int(screen_x),
                int(screen_y),
            )
            return False

        hold_delay = config.MOUSE_DOWN_UP_DELAY if down_up_delay is None else down_up_delay
        hold_ns = self._seconds_to_ns(hold_delay)
        return self._send_precise_click(hold_ns)

    def _send_mouse_down(self, screen_x, screen_y):
        if not self._validate_pre_click_target(screen_x, screen_y):
            logger.warning(
                "Blocked mouse-down dispatch at (%s, %s): forbidden-zone pre-check failed",
                int(screen_x),
                int(screen_y),
            )
            return False

        travel_distance = self._estimate_cursor_distance(screen_x, screen_y)

        if self._should_move_cursor(screen_x, screen_y):
            self._move_cursor(screen_x, screen_y)

        self._ensure_cursor_at_target(screen_x, screen_y)
        self._correct_cursor_position(screen_x, screen_y)
        self._stabilize_before_click(screen_x, screen_y, distance_override=travel_distance)
        self._ensure_min_click_interval()

        if not self._validate_pre_click_target(screen_x, screen_y):
            logger.warning(
                "Blocked mouse-down dispatch at (%s, %s): forbidden-zone final gate failed",
                int(screen_x),
                int(screen_y),
            )
            return False

        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, screen_x, screen_y, 0, 0)
        return True

    def _send_mouse_up(self, screen_x, screen_y):
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, screen_x, screen_y, 0, 0)
        self._last_click_time = time.monotonic()

    def _ensure_min_click_interval(self):
        min_interval = config.MIN_CLICK_INTERVAL
        if min_interval <= 0:
            return
        now = time.monotonic()
        wait_time = self._last_click_time + min_interval - now
        if wait_time > 0:
            self._sleep(wait_time)

    def _ensure_min_drag_interval(self):
        min_interval = config.SCROLL_MIN_INTERVAL
        if min_interval <= 0:
            return
        now = time.monotonic()
        wait_time = self._last_drag_time + min_interval - now
        if wait_time > 0:
            self._sleep(wait_time)
        self._last_drag_time = time.monotonic()

    def _correct_cursor_position(self, screen_x, screen_y):
        retries = max(0, config.MOUSE_TARGET_RETRIES)
        if retries <= 0:
            return
        tolerance = config.MOUSE_POSITION_TOLERANCE
        correction_delay = config.MOUSE_TARGET_CORRECTION_DELAY
        target = (int(screen_x), int(screen_y))

        for _ in range(retries):
            current = win32api.GetCursorPos()
            if abs(current[0] - target[0]) <= tolerance and abs(current[1] - target[1]) <= tolerance:
                self._last_cursor_pos = target
                return
            win32api.SetCursorPos(target)
            if correction_delay > 0:
                self._sleep(correction_delay)
        self._last_cursor_pos = target

    def _should_move_cursor(self, screen_x, screen_y):
        if self._last_cursor_pos is None:
            return True
        tolerance = config.MOUSE_POSITION_TOLERANCE
        dx = abs(self._last_cursor_pos[0] - screen_x)
        dy = abs(self._last_cursor_pos[1] - screen_y)
        return dx > tolerance or dy > tolerance

    def _move_cursor(self, screen_x, screen_y):
        target = (int(screen_x), int(screen_y))
        retries = max(1, config.MOUSE_MOVE_RETRIES)
        retry_delay = config.MOUSE_MOVE_RETRY_DELAY
        tolerance = config.MOUSE_POSITION_TOLERANCE

        for _ in range(retries):
            win32api.SetCursorPos(target)
            if retry_delay > 0:
                self._sleep(retry_delay)
            current = win32api.GetCursorPos()
            if abs(current[0] - target[0]) <= tolerance and abs(current[1] - target[1]) <= tolerance:
                break

        self._sleep(self.move_delay)
        self._last_cursor_pos = target

    def _estimate_cursor_distance(self, screen_x, screen_y):
        target = (int(screen_x), int(screen_y))
        try:
            current = win32api.GetCursorPos()
        except Exception:
            current = self._last_cursor_pos

        if current is None:
            return 0.0

        return ((current[0] - target[0]) ** 2 + (current[1] - target[1]) ** 2) ** 0.5

    def _stabilize_before_click(self, screen_x, screen_y, distance_override=None):
        if distance_override is None:
            target = (int(screen_x), int(screen_y))
            prev = self._last_cursor_pos
            if prev is None:
                distance = 0.0
            else:
                distance = ((prev[0] - target[0]) ** 2 + (prev[1] - target[1]) ** 2) ** 0.5
        else:
            distance = max(0.0, float(distance_override))

        base_delay = max(0.0, float(config.MOUSE_PRE_CLICK_STABILIZE_BASE))
        max_delay = max(base_delay, float(config.MOUSE_PRE_CLICK_STABILIZE_MAX))
        distance_factor = max(0.0, float(config.MOUSE_PRE_CLICK_STABILIZE_DISTANCE_FACTOR))
        stabilize_delay = min(max_delay, base_delay + (distance * distance_factor))
        if stabilize_delay > 0:
            self._sleep(stabilize_delay)

    def _ensure_cursor_at_target(self, screen_x, screen_y):
        target = (int(screen_x), int(screen_y))
        tolerance = config.MOUSE_POSITION_TOLERANCE
        timeout = config.MOUSE_TARGET_TIMEOUT
        check_interval = config.MOUSE_TARGET_CHECK_INTERVAL
        settle_delay = config.MOUSE_TARGET_SETTLE_DELAY
        hover_delay = config.MOUSE_TARGET_HOVER_DELAY
        stabilize_duration = config.MOUSE_STABILIZE_DURATION

        start_time = time.monotonic()
        stable_since = None
        while True:
            current = win32api.GetCursorPos()
            if abs(current[0] - target[0]) <= tolerance and abs(current[1] - target[1]) <= tolerance:
                if stable_since is None:
                    stable_since = time.monotonic()
                if stabilize_duration <= 0 or time.monotonic() - stable_since >= stabilize_duration:
                    if settle_delay > 0:
                        self._sleep(settle_delay)
                    if hover_delay > 0:
                        self._sleep(hover_delay)
                    self._last_cursor_pos = target
                    return
            else:
                stable_since = None

            if timeout <= 0 or time.monotonic() - start_time >= timeout:
                win32api.SetCursorPos(target)
                self._last_cursor_pos = target
                if hover_delay > 0:
                    self._sleep(hover_delay)
                return

            if check_interval > 0:
                self._sleep(check_interval)
    
    def is_safe_to_click(self, x, y, relative=True):
        """
        Coordinate Gatekeeper.
        Uses monitor-space collision checks with explicit inclusive bounds:
            if (zone_x1 <= target_center_x <= zone_x2) and (zone_y1 <= target_center_y <= zone_y2):
                return False
        """
        target_center_x, target_center_y = self._translate_to_monitor_space(x, y, relative=relative)
        window_origin = self.get_window_position()

        for zone in config.FORBIDDEN_ZONES:
            zone_x1, zone_x2, zone_y1, zone_y2 = self._zone_to_monitor_space(zone, window_origin)
            zone_x1, zone_x2 = sorted((zone_x1, zone_x2))
            zone_y1, zone_y2 = sorted((zone_y1, zone_y2))
            if (zone_x1 <= target_center_x <= zone_x2) and (zone_y1 <= target_center_y <= zone_y2):
                logger.warning(
                    "Coordinates (%s, %s) blocked by forbidden zone '%s' in monitor space",
                    int(round(target_center_x)),
                    int(round(target_center_y)),
                    zone.get("name", "unnamed"),
                )
                return False
        return True

    def _validate_pre_click_target(self, screen_x, screen_y):
        validation_delay = max(
            0.0,
            float(config.FORBIDDEN_ZONE_PRECLICK_VALIDATION_DELAY),
        )
        double_check_delay = max(
            0.0,
            float(config.FORBIDDEN_ZONE_DOUBLE_CHECK_DELAY),
        )

        if validation_delay > 0:
            self._sleep(validation_delay)

        first_check = self.is_safe_to_click(screen_x, screen_y, relative=False)
        if not first_check:
            return False

        if double_check_delay > 0:
            self._sleep(double_check_delay)

        return self.is_safe_to_click(screen_x, screen_y, relative=False)

    def is_in_forbidden_zone(self, x, y, relative=True):
        return not self.is_safe_to_click(x, y, relative=relative)
    
    def get_window_position(self):
        x, y = win32gui.ClientToScreen(self.hwnd, (0, 0))
        return x, y
    
    def move_to(self, x, y, relative=True):
        self._check_interrupts()
        with self._mouse_action_lock:
            if relative:
                win_x, win_y = self.get_window_position()
                screen_x = win_x + x
                screen_y = win_y + y
            else:
                screen_x = x
                screen_y = y

            screen_x, screen_y = self._clamp_to_screen(int(screen_x), int(screen_y))
            win32api.SetCursorPos((int(screen_x), int(screen_y)))
            self._last_cursor_pos = (int(screen_x), int(screen_y))
            logger.info(f"Cursor moved to window position ({x}, {y})")
    
    def click(self, x, y, relative=True, delay=None, wait_after=True, prevalidated=False):
        self._check_interrupts()
        with self._mouse_action_lock:
            screen_pos = self._resolve_screen_position(
                x,
                y,
                relative=relative,
                check_forbidden=not prevalidated,
            )
            if screen_pos is None:
                if wait_after:
                    self._sleep(self.click_delay if delay is None else delay)
                return False

            screen_x, screen_y = screen_pos
            click_sent = self._send_click(
                screen_x,
                screen_y,
                prevalidated=prevalidated,
            )
            if not click_sent:
                if wait_after:
                    self._sleep(self.click_delay if delay is None else delay)
                return False

            logger.info(f"Clicked at ({screen_x}, {screen_y})")

            if wait_after:
                self._sleep(self.click_delay if delay is None else delay)
            return True

    def mouse_down(self, x, y, relative=True):
        self._check_interrupts()
        with self._mouse_action_lock:
            screen_pos = self._resolve_screen_position(x, y, relative=relative)
            if screen_pos is None:
                return False

            screen_x, screen_y = screen_pos
            if not self._send_mouse_down(screen_x, screen_y):
                return False
            self._last_cursor_pos = (screen_x, screen_y)
            logger.info(f"Mouse down at ({screen_x}, {screen_y})")
            return True

    def mouse_up(self, x, y, relative=True):
        self._check_interrupts()
        with self._mouse_action_lock:
            screen_pos = self._resolve_screen_position(x, y, relative=relative, check_forbidden=False)
            if screen_pos is None:
                return False

            screen_x, screen_y = screen_pos
            self._send_mouse_up(screen_x, screen_y)
            self._last_cursor_pos = (screen_x, screen_y)
            logger.info(f"Mouse up at ({screen_x}, {screen_y})")
            return True
    
    def double_click(self, x, y, relative=True):
        with self._mouse_action_lock:
            self.click(x, y, relative)
            self._sleep(config.DOUBLE_CLICK_DELAY)
            self.click(x, y, relative)
    
    def hold_at(self, x, y, duration=None, relative=True, interrupt_check=None):
        self._check_interrupts()
        if duration is None:
            duration = config.UPGRADE_HOLD_DURATION

        with self._mouse_action_lock:
            screen_pos = self._resolve_screen_position(x, y, relative=relative)
            if screen_pos is None:
                return False

            screen_x, screen_y = screen_pos

            logger.info(
                "Holding click at (%s, %s) for %ss",
                screen_x,
                screen_y,
                duration,
            )
            if not self._send_mouse_down(screen_x, screen_y):
                return False
            
            # Sleep in small chunks to allow interruption
            start_time = time.monotonic()
            chunk_size = config.HOLD_ITERATION_INTERVAL
            while time.monotonic() - start_time < duration:
                if interrupt_check and interrupt_check():
                    logger.info("Hold interrupted by callback")
                    self._send_mouse_up(screen_x, screen_y)
                    return False
                
                remaining = duration - (time.monotonic() - start_time)
                if remaining > 0:
                    self._sleep(min(chunk_size, remaining))

            self._send_mouse_up(screen_x, screen_y)
            self._sleep(self.click_delay)
            return True

    def spam_click_at(self, x, y, duration=None, click_delay=None, jitter=0,
                      relative=True, interrupt_check=None):
        """
        Spam-clicks at the given position for ``duration`` seconds.

        This path uses a dedicated high-resolution scheduler so repeated clicks
        are timed against absolute deadlines instead of chaining ``sleep()``
        calls after the full single-click pipeline.

        Args:
            x, y:            Target coordinates.
            duration:        Total spam-click window in seconds.
                             Defaults to ``config.SPAM_CLICK_DURATION``.
            click_delay:     Pause between individual clicks in seconds.
                             Defaults to ``config.SPAM_CLICK_DELAY``.
            jitter:          Max random pixel offset applied to each click
                             position (0 = no jitter).
            relative:        If True, coordinates are relative to window.
            interrupt_check: Optional callback; if it returns True the
                             sequence is aborted early.

        Returns:
            True if the full duration elapsed, False if interrupted.
        """
        import random

        self._check_interrupts()
        if duration is None:
            duration = config.SPAM_CLICK_DURATION
        if click_delay is None:
            click_delay = config.SPAM_CLICK_DELAY

        duration = max(0.0, float(duration))
        click_delay = max(0.0, float(click_delay))
        if duration <= 0:
            return True
        if click_delay <= 0:
            logger.warning("Rapid-click rejected: click interval must be > 0")
            return False

        interval_ns = self._seconds_to_ns(click_delay)
        click_hold_ns = self._rapid_click_hold_ns(click_delay)

        with self._mouse_action_lock:
            screen_pos = self._resolve_screen_position(
                x,
                y,
                relative=relative,
                check_forbidden=False,
            )
            if screen_pos is None:
                return False

            screen_x, screen_y = screen_pos
            if not self._prepare_rapid_click_target(screen_x, screen_y):
                return False

            click_count = 0
            start_ns = time.perf_counter_ns()
            end_ns = start_ns + self._seconds_to_ns(duration)
            next_click_ns = start_ns

            logger.info(
                "Rapid-clicking at (%s, %s) for %.3fs (interval=%.3fs, hold=%.4fs, jitter=%s)",
                screen_x,
                screen_y,
                duration,
                click_delay,
                click_hold_ns / 1_000_000_000,
                jitter,
            )

            while True:
                if not self._wait_until_precise(
                    next_click_ns,
                    interrupt_check=interrupt_check,
                ):
                    elapsed = (time.perf_counter_ns() - start_ns) / 1_000_000_000
                    logger.info(
                        "Rapid-click interrupted after %s clicks (%.2fs)",
                        click_count,
                        elapsed,
                    )
                    return False

                click_start_ns = time.perf_counter_ns()
                if click_start_ns >= end_ns:
                    break

                if jitter > 0:
                    target_x = screen_x + random.randint(-jitter, jitter)
                    target_y = screen_y + random.randint(-jitter, jitter)
                    target_x, target_y = self._clamp_to_screen(target_x, target_y)
                    if not self.is_safe_to_click(target_x, target_y, relative=False):
                        logger.warning(
                            "Blocked rapid-click dispatch at (%s, %s): forbidden-zone check failed",
                            int(target_x),
                            int(target_y),
                        )
                        return False
                    if self._should_move_cursor(target_x, target_y):
                        win32api.SetCursorPos((int(target_x), int(target_y)))
                        self._last_cursor_pos = (int(target_x), int(target_y))

                if not self._send_precise_click(
                    click_hold_ns,
                    interrupt_check=interrupt_check,
                ):
                    elapsed = (time.perf_counter_ns() - start_ns) / 1_000_000_000
                    logger.info(
                        "Rapid-click interrupted after %s clicks (%.2fs)",
                        click_count,
                        elapsed,
                    )
                    return False

                click_count += 1
                next_click_ns = self._compute_next_click_deadline(
                    next_click_ns,
                    click_start_ns,
                    interval_ns,
                )

            elapsed = (time.perf_counter_ns() - start_ns) / 1_000_000_000
            logger.info(
                "Rapid-click complete: %s clicks in %.2fs",
                click_count,
                elapsed,
            )
            return True

    def drag(self, from_x, from_y, to_x, to_y, duration=None, relative=True, interrupt_check=None):
        if duration is None:
            duration = config.DEFAULT_DRAG_DURATION
        self._check_interrupts()
        with self._mouse_action_lock:
            if relative:
                win_x, win_y = self.get_window_position()
                screen_from_x = win_x + from_x
                screen_from_y = win_y + from_y
                screen_to_x = win_x + to_x
                screen_to_y = win_y + to_y
            else:
                screen_from_x = from_x
                screen_from_y = from_y
                screen_to_x = to_x
                screen_to_y = to_y

            self._ensure_min_drag_interval()

            screen_from_x, screen_from_y = self._clamp_to_screen(int(screen_from_x), int(screen_from_y))
            screen_to_x, screen_to_y = self._clamp_to_screen(int(screen_to_x), int(screen_to_y))

            win32api.SetCursorPos((int(screen_from_x), int(screen_from_y)))
            self._ensure_cursor_at_target(int(screen_from_x), int(screen_from_y))
            self._correct_cursor_position(int(screen_from_x), int(screen_from_y))
            self._last_cursor_pos = (int(screen_from_x), int(screen_from_y))
            self._sleep(self.move_delay)

            win32api.mouse_event(
                win32con.MOUSEEVENTF_LEFTDOWN,
                int(screen_from_x),
                int(screen_from_y),
                0,
                0,
            )
            self._sleep(config.MOUSE_DOWN_UP_DELAY)

            steps = max(1, int(config.SCROLL_STEP_COUNT))
            duration = max(duration, config.DRAG_MIN_DURATION)
            start_time = time.monotonic()
            interrupted = False
            current_x = int(screen_from_x)
            current_y = int(screen_from_y)
            for i in range(steps + 1):
                if interrupt_check and interrupt_check():
                    logger.info("Drag interrupted by callback")
                    interrupted = True
                    break
                t = i / steps
                current_x = int(screen_from_x + (screen_to_x - screen_from_x) * t)
                current_y = int(screen_from_y + (screen_to_y - screen_from_y) * t)
                win32api.SetCursorPos((current_x, current_y))
                target_time = start_time + (duration * t)
                sleep_time = target_time - time.monotonic()
                if sleep_time > 0:
                    self._sleep(sleep_time)

            win32api.mouse_event(
                win32con.MOUSEEVENTF_LEFTUP,
                int(current_x) if interrupted else int(screen_to_x),
                int(current_y) if interrupted else int(screen_to_y),
                0,
                0,
            )
            final_x = int(current_x) if interrupted else int(screen_to_x)
            final_y = int(current_y) if interrupted else int(screen_to_y)
            self._ensure_cursor_at_target(final_x, final_y)
            self._correct_cursor_position(final_x, final_y)
            self._last_cursor_pos = (final_x, final_y)
            
            if interrupted:
                logger.info(f"Drag interrupted at ({final_x}, {final_y})")
                return False

            logger.info(f"Dragged from ({from_x}, {from_y}) to ({to_x}, {to_y})")
            self._sleep(config.SCROLL_SETTLE_DELAY)
            return True
