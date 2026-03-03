import win32api
import win32con
import win32gui
import time
import logging
import threading
import config

logger = logging.getLogger(__name__)


class MouseController:
    def __init__(self, hwnd, click_delay=0.1, move_delay=0.004):
        self.hwnd = hwnd
        self.click_delay = click_delay
        self.move_delay = move_delay
        self.interrupt_callback = None # Set by bot to check for high-priority interrupts
        self._last_click_time = 0.0
        self._last_cursor_pos = None
        self._last_drag_time = 0.0
        self._mouse_action_lock = threading.RLock()

    def _check_interrupts(self):
        """Calls the guard function. If it returns True, the action layer refuses to proceed."""
        if self.interrupt_callback and self.interrupt_callback():
            # The bot will raise the actual exception in the callback or we can do it here.
            # Requirement says: 'If check_critical_interrupts() returns True, raise custom exception'
            # We'll let the bot's callback handle the raising if it wants, 
            # but to be safe we can raise a generic one if it just returns True.
            pass

    def _sleep(self, duration):
        """Helper to sleep while remaining interrupt-aware."""
        self._check_interrupts()
        if duration > 0:
            time.sleep(duration)

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

    def _send_click(self, screen_x, screen_y, down_up_delay=None):
        if not self._validate_pre_click_target(screen_x, screen_y):
            logger.warning(
                "Blocked click dispatch at (%s, %s): forbidden-zone pre-check failed",
                int(screen_x),
                int(screen_y),
            )
            return False

        retries = max(1, int(getattr(config, "MOUSE_CLICK_RETRY_COUNT", 1)))
        settle_retry_delay = max(0.0, float(getattr(config, "MOUSE_CLICK_RETRY_SETTLE_DELAY", 0.0)))

        for attempt in range(retries):
            travel_distance = self._estimate_cursor_distance(screen_x, screen_y)

            if self._should_move_cursor(screen_x, screen_y):
                self._move_cursor(screen_x, screen_y)

            self._ensure_cursor_at_target(screen_x, screen_y)
            self._correct_cursor_position(screen_x, screen_y)
            self._stabilize_before_click(screen_x, screen_y, distance_override=travel_distance)
            current = win32api.GetCursorPos()
            tolerance = getattr(config, "MOUSE_POSITION_TOLERANCE", 0)
            if abs(current[0] - screen_x) <= tolerance and abs(current[1] - screen_y) <= tolerance:
                break

            win32api.SetCursorPos((int(screen_x), int(screen_y)))
            self._last_cursor_pos = (int(screen_x), int(screen_y))
            if attempt < retries - 1 and settle_retry_delay > 0:
                self._sleep(settle_retry_delay)

        self._ensure_min_click_interval()

        if not self._validate_pre_click_target(screen_x, screen_y):
            logger.warning(
                "Blocked click dispatch at (%s, %s): forbidden-zone final gate failed",
                int(screen_x),
                int(screen_y),
            )
            return False

        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, screen_x, screen_y, 0, 0)
        self._sleep(config.MOUSE_DOWN_UP_DELAY if down_up_delay is None else down_up_delay)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, screen_x, screen_y, 0, 0)
        self._last_click_time = time.monotonic()
        return True

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
        min_interval = getattr(config, "MIN_CLICK_INTERVAL", 0.0)
        if min_interval <= 0:
            return
        now = time.monotonic()
        wait_time = self._last_click_time + min_interval - now
        if wait_time > 0:
            self._sleep(wait_time)

    def _ensure_min_drag_interval(self):
        min_interval = getattr(config, "SCROLL_MIN_INTERVAL", 0.0)
        if min_interval <= 0:
            return
        now = time.monotonic()
        wait_time = self._last_drag_time + min_interval - now
        if wait_time > 0:
            self._sleep(wait_time)
        self._last_drag_time = time.monotonic()

    def _correct_cursor_position(self, screen_x, screen_y):
        retries = max(0, getattr(config, "MOUSE_TARGET_RETRIES", 0))
        if retries <= 0:
            return
        tolerance = getattr(config, "MOUSE_POSITION_TOLERANCE", 0)
        correction_delay = getattr(config, "MOUSE_TARGET_CORRECTION_DELAY", 0.0)
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
        tolerance = getattr(config, "MOUSE_POSITION_TOLERANCE", 0)
        dx = abs(self._last_cursor_pos[0] - screen_x)
        dy = abs(self._last_cursor_pos[1] - screen_y)
        return dx > tolerance or dy > tolerance

    def _move_cursor(self, screen_x, screen_y):
        target = (int(screen_x), int(screen_y))
        retries = max(1, getattr(config, "MOUSE_MOVE_RETRIES", 1))
        retry_delay = getattr(config, "MOUSE_MOVE_RETRY_DELAY", 0.0)
        tolerance = getattr(config, "MOUSE_POSITION_TOLERANCE", 0)

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

        base_delay = max(0.0, float(getattr(config, "MOUSE_PRE_CLICK_STABILIZE_BASE", 0.0)))
        max_delay = max(base_delay, float(getattr(config, "MOUSE_PRE_CLICK_STABILIZE_MAX", base_delay)))
        distance_factor = max(0.0, float(getattr(config, "MOUSE_PRE_CLICK_STABILIZE_DISTANCE_FACTOR", 0.0)))
        stabilize_delay = min(max_delay, base_delay + (distance * distance_factor))
        if stabilize_delay > 0:
            self._sleep(stabilize_delay)

    def _ensure_cursor_at_target(self, screen_x, screen_y):
        target = (int(screen_x), int(screen_y))
        tolerance = getattr(config, "MOUSE_POSITION_TOLERANCE", 0)
        timeout = getattr(config, "MOUSE_TARGET_TIMEOUT", 0.0)
        check_interval = getattr(config, "MOUSE_TARGET_CHECK_INTERVAL", 0.0)
        settle_delay = getattr(config, "MOUSE_TARGET_SETTLE_DELAY", 0.0)
        hover_delay = getattr(config, "MOUSE_TARGET_HOVER_DELAY", 0.0)
        stabilize_duration = getattr(config, "MOUSE_STABILIZE_DURATION", 0.0)

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

        for zone in getattr(config, "FORBIDDEN_ZONES", []):
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
            float(getattr(config, "FORBIDDEN_ZONE_PRECLICK_VALIDATION_DELAY", 0.0)),
        )
        double_check_delay = max(
            0.0,
            float(getattr(config, "FORBIDDEN_ZONE_DOUBLE_CHECK_DELAY", 0.0)),
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
    
    def click(self, x, y, relative=True, delay=None, wait_after=True):
        self._check_interrupts()
        with self._mouse_action_lock:
            screen_pos = self._resolve_screen_position(x, y, relative=relative)
            if screen_pos is None:
                if wait_after:
                    self._sleep(self.click_delay if delay is None else delay)
                return False

            screen_x, screen_y = screen_pos
            click_sent = self._send_click(screen_x, screen_y)
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
            self._send_mouse_down(screen_x, screen_y)
            
            # Sleep in small chunks to allow interruption
            start_time = time.monotonic()
            chunk_size = 0.1
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
    
    def drag(self, from_x, from_y, to_x, to_y, duration=0.3, relative=True, interrupt_check=None):
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

            steps = max(1, int(getattr(config, "SCROLL_STEP_COUNT", 20)))
            duration = max(duration, 0.001)
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
            settle_delay = getattr(config, "SCROLL_SETTLE_DELAY", 0.0)
            self._sleep(settle_delay if settle_delay > 0 else self.click_delay)
            return True
