import logging
import math
import queue
import signal
import sys
import threading
import time
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from pathlib import Path
from typing import Any

from pynput import keyboard

import config
from bot import EatventureBot

bot_instance: EatventureBot | None = None
should_exit = threading.Event()
bot_toggle_requested = threading.Event()
mode_toggle_requested = threading.Event()
log_listener: QueueListener | None = None
log_handlers: list[logging.Handler] = []

HOTKEYS = {"z", "x", "m", "p"}
# Keys currently held: the OS auto-repeats a held key, which must not re-trigger start/stop.
_pressed_keys: set[str] = set()
_pressed_keys_lock = threading.Lock()
# time.monotonic() of the latest key press anywhere on the PC (the hotkey listener is global): the
# keyboard half of the "is a person here" gate that auto-resume waits on.
_last_key_at = 0.0

ForbiddenZoneBounds = tuple[int, int, int, int]
primed_event_selection: tuple[int, ForbiddenZoneBounds] | None = None


def _get_key_character(key: Any) -> str | None:
    character = getattr(key, "char", None)
    if character is None:
        return None
    return str(character).lower()


def _log_window_relative_cursor_position(logger: logging.Logger) -> None:
    position = None if bot_instance is None else bot_instance.cursor_position_in_window()
    if position is None:
        logger.info("[X pressed] Bot window is not available")
        return
    logger.info("[X pressed] Window position: (%s, %s)", position[0], position[1])


def _toggle_red_icon_mode(logger: logging.Logger) -> None:
    if bot_instance is None:
        return
    if bot_instance.running:
        logger.warning("[M pressed] Red-icon mode can only be changed while stopped")
        return
    logger.info("[M pressed] Red-icon mode: %s", bot_instance.toggle_red_icon_mode())


def _event_forbidden_zone_options() -> list[tuple[int, ForbiddenZoneBounds]]:
    options = config.EVENT_FORBIDDEN_ZONE_OPTIONS
    if not isinstance(options, dict) or not options:
        raise ValueError("EVENT_FORBIDDEN_ZONE_OPTIONS must contain at least one option")

    validated_options: list[tuple[int, ForbiddenZoneBounds]] = []
    for event_count, bounds in options.items():
        if not isinstance(event_count, int) or isinstance(event_count, bool) or event_count < 1:
            raise ValueError("event option keys must be positive integers")
        if (
            not isinstance(bounds, tuple)
            or len(bounds) != 4
            or any(not isinstance(value, int) or isinstance(value, bool) for value in bounds)
        ):
            raise ValueError(f"event option {event_count} must contain four integer coordinates")
        x_min, x_max, y_min, y_max = bounds
        if x_min > x_max or y_min > y_max:
            raise ValueError(f"event option {event_count} has reversed coordinate bounds")
        if not (
            0 <= x_min <= x_max < config.WINDOW_WIDTH
            and 0 <= y_min <= y_max < config.WINDOW_HEIGHT
        ):
            raise ValueError(
                f"event option {event_count} must fit inside the configured "
                f"{config.WINDOW_WIDTH}x{config.WINDOW_HEIGHT} window"
            )
        validated_options.append((event_count, bounds))

    return sorted(validated_options)


def _select_event_forbidden_zone() -> tuple[int, ForbiddenZoneBounds] | None:
    try:
        options = _event_forbidden_zone_options()
    except ValueError as exc:
        print(f"\nCannot prime bot: invalid event forbidden-zone configuration: {exc}")
        return None

    print("\n" + "=" * 60)
    print("Event Forbidden-Zone Selection")
    print("Choose how many Eatventure events are currently active.")
    print(
        "The bot will protect the matching top-right event-icon area "
        "from all mouse interaction."
    )
    print()

    option_map = dict(options)
    for event_count, (x_min, x_max, y_min, y_max) in options:
        event_label = "Event" if event_count == 1 else "Events"
        print(
            f"{event_count} - {event_count} {event_label} Active "
            f"(protected area: x={x_min}-{x_max}, y={y_min}-{y_max})"
        )

    valid_choices = ", ".join(str(event_count) for event_count in option_map)
    selection: queue.SimpleQueue[int | None] = queue.SimpleQueue()

    def read_selection() -> None:
        # input() blocks, so it runs on a worker: P and Ctrl-C must still be able to exit while primed.
        while not should_exit.is_set():
            try:
                raw_selection = input("\nType an option number and press Enter: ").strip()
            except EOFError:
                selection.put(None)
                return
            try:
                chosen = int(raw_selection)
            except ValueError:
                chosen = 0
            if chosen in option_map:
                selection.put(chosen)
                return
            print(f"Invalid selection. Enter one of: {valid_choices}.")

    threading.Thread(target=read_selection, name="event_selection", daemon=True).start()
    while not should_exit.wait(config.EVENT_LOOP_INTERVAL):
        try:
            event_count = selection.get_nowait()
        except queue.Empty:
            continue
        if event_count is None:
            print("\nEvent selection cancelled. The bot remains stopped.")
            return None
        bounds = option_map[event_count]
        x_min, x_max, y_min, y_max = bounds
        event_label = "Event" if event_count == 1 else "Events"
        print(
            f"Selected: {event_count} {event_label} Active. "
            f"Protected area: x={x_min}-{x_max}, y={y_min}-{y_max}."
        )
        print("Bot primed but NOT running.")
        print(
            f"Focus the '{config.WINDOW_TITLE}' scrcpy window, "
            "then press Z again to START."
        )
        print("=" * 60)
        return event_count, bounds
    return None


def _toggle_bot_running(logger: logging.Logger) -> None:
    global primed_event_selection

    if bot_instance is None:
        return
    if bot_instance.running:
        bot_instance.stop(manual=True)  # sends "Bot Stopped": only a Z press does
        primed_event_selection = None
        logger.info(
            "[Z pressed] Bot STOPPED. Press Z to select the active-event count "
            "for the next run."
        )
        return

    if primed_event_selection is None:
        selection = _select_event_forbidden_zone()
        bot_toggle_requested.clear()
        if selection is None or should_exit.is_set():
            logger.warning("[Z pressed] Bot priming cancelled")
            return

        event_count, bounds = selection
        bot_instance.set_event_forbidden_zone(bounds)
        primed_event_selection = selection
        logger.info("[Z pressed] Bot PRIMED for %s active event(s): %s", event_count, bounds)
        return

    event_count, _ = primed_event_selection
    if bot_instance.start():  # start() sends "Bot Started" itself, so auto-resume reports too
        logger.info("[Z pressed] Bot STARTED")
        return
    logger.warning(
        "[Z pressed] Bot START failed; the %s-event selection remains primed. "
        "Resolve the error above, focus '%s', and press Z again to retry.",
        event_count,
        config.WINDOW_TITLE,
    )


def _request_bot_toggle(logger: logging.Logger) -> None:
    if bot_instance is not None and bot_instance.running:
        bot_instance.request_stop()
    bot_toggle_requested.set()
    logger.debug("[Z pressed] Bot toggle requested")


def _request_red_icon_mode_toggle(logger: logging.Logger) -> None:
    mode_toggle_requested.set()  # applied by the main loop, never on the listener thread
    logger.debug("[M pressed] Red-icon mode toggle requested")


def _request_program_exit(logger: logging.Logger) -> None:
    logger.info("[P pressed] Exiting program")
    if bot_instance is not None and bot_instance.running:
        bot_instance.request_stop()
    should_exit.set()


def on_press(key: Any) -> None:
    global _last_key_at
    _last_key_at = time.monotonic()
    try:
        character = _get_key_character(key)
        if character not in HOTKEYS:
            return
        with _pressed_keys_lock:
            if character in _pressed_keys:
                return  # OS key auto-repeat: the press was already handled
            _pressed_keys.add(character)

        logger = logging.getLogger(__name__)
        key_handlers = {
            "x": _log_window_relative_cursor_position,
            "z": _request_bot_toggle,
            "m": _request_red_icon_mode_toggle,
            "p": _request_program_exit,
        }
        key_handlers[character](logger)
    except Exception as exc:
        logging.getLogger(__name__).error("Keyboard listener error: %s", exc)


def on_release(key: Any) -> None:
    character = _get_key_character(key)
    if character is not None:
        with _pressed_keys_lock:
            _pressed_keys.discard(character)


class ConfigError(ValueError):
    """config.py holds a value the bot cannot run with; the message lists every bad constant."""


# Constants checked by validate_config, grouped by the rule they must satisfy. A name that is absent
# from config.py is itself reported, so a typo or a deleted constant fails at startup.
_FRACTION_NAMES = (  # a number in (0, 1]
    "MATCH_THRESHOLD",
    "RED_ICON_THRESHOLD",
    "NEW_LEVEL_RED_ICON_THRESHOLD",
    "STATS_RED_ICON_THRESHOLD",
    "UPGRADE_STATION_THRESHOLD",
    "BOX_THRESHOLD",
    "UNLOCK_THRESHOLD",
    "NEW_LEVEL_THRESHOLD",
    "CLOSE_BUTTON_THRESHOLD",
    "RED_ICON_HSV_MIN_MATCH_RATIO",
    "BOX_HSV_MIN_MATCH_RATIO",
    "UPGRADE_STATION_HSV_MIN_MATCH_RATIO",
    "CLOSE_BUTTON_HSV_MIN_MATCH_RATIO",
    "RED_ICON_NMS_IOU_THRESHOLD",
    "BOX_NMS_IOU_THRESHOLD",
    "UPGRADE_STATION_CANDIDATE_NMS_IOU_THRESHOLD",
    "UPGRADE_STATION_THRESHOLD_RELAXATION",
    "CLOSE_BUTTON_NMS_IOU_THRESHOLD",
    "CLOSE_BUTTON_BLOCK_MIN_FRACTION",
)
_NON_NEGATIVE_NAMES = (  # a number >= 0
    "SCRCPY_RED_ICON_MISS_RECOVERY_DELAY",
    "SCRCPY_BOX_MISS_RECOVERY_DELAY",
    "SCRCPY_UPGRADE_MISS_RECOVERY_DELAY",
    "SCRCPY_ACTION_SETTLE_DELAY",
    "CLICK_DELAY",
    "MOUSE_MOVE_DELAY",
    "MOUSE_DOWN_DURATION",
    "MOUSE_UP_DURATION",
    "INPUT_RETRY_DELAY",
    "HOVER_DURATION",
    "UPGRADE_SEARCH_INTERVAL",
    "STATE_STALL_TIMEOUT_SECONDS",
    "EVENT_LOOP_INTERVAL",
    "STATE_DELAY",
    "METRICS_LOG_INTERVAL",
    "FOCUS_SETTLE_DELAY",
    "UPGRADE_STATION_VERIFY_SETTLE_DELAY",
    "UPGRADE_STATION_VERIFY_SEARCH_INTERVAL",
    "UPGRADE_STATION_DISAPPEAR_POSITION_TOLERANCE_PX",
    "CLICK_HOLD_MAX_DURATION",
    "UPGRADE_HOLD_CHECK_INTERVAL_MIN",
    "UPGRADE_HOLD_CHECK_INTERVAL_MAX",
    "SPAM_CLICK_DURATION",
    "SPAM_CLICK_DELAY",
    "NEW_LEVEL_SEARCH_INTERVAL",
    "NEW_LEVEL_VERIFICATION_SCROLL_DISTANCE",
    "NEW_LEVEL_VERIFICATION_SCROLL_DURATION",
    "NEW_LEVEL_VERIFICATION_SCROLL_SETTLE_DELAY",
    "NEW_LEVEL_VERIFICATION_SCROLL_INTERVAL_PAUSE",
    "LEVEL_TRANSITION_SETTLE_DELAY",
    "NEW_LEVEL_CONFIRMATION_DELAY",
    "LEVEL_TRANSITION_SECONDARY_SETTLE_DELAY",
    "UNLOCK_SEARCH_INTERVAL",
    "UNLOCK_SETTLE_DELAY",
    "SCROLL_INTERVAL_PAUSE",
    "POST_SCROLL_SETTLE",
    "SCROLL_DURATION",
    "STALL_SCROLLS_BEFORE_ALERT",
    "STALL_PROBE_SCROLLS",
    "STATS_UPGRADE_CLICK_DURATION",
    "STATS_UPGRADE_CLICK_DELAY",
    "STATS_UPGRADE_MOUSE_DOWN_DURATION",
    "STATS_UPGRADE_MOUSE_UP_DURATION",
    "CURSOR_DRIFT_TOLERANCE_PX",
    "TELEGRAM_CLOSE_TIMEOUT",
    "CLOSE_BUTTON_SETTLE_DELAY",
    "CLOSE_BUTTON_SUPPRESS_SECONDS",
    "CLOSE_BUTTON_NEW_LEVEL_LOCK_SECONDS",
    "GAME_RECOVERY_RELAUNCH_SETTLE_SECONDS",
    "RESUME_IDLE_SECONDS",
)
_POSITIVE_NAMES = (  # a number > 0
    "WINDOW_WIDTH",
    "WINDOW_HEIGHT",
    "MAX_SEARCH_Y",
    "EXTENDED_SEARCH_Y",
    "UPGRADE_STATION_SEARCH_Y",
    "BOX_SEARCH_Y",
    "SCROLL_PIXEL_STEP",
    "SCROLL_DISTANCE_RATIO",
    "GAME_RECOVERY_STATIC_FRAME_DELTA",
    "GAME_RECOVERY_COMMAND_TIMEOUT",
    "GAME_RECOVERY_POLL_SECONDS",
    "RESUME_CHECK_SECONDS",
)
_AT_LEAST_ONE_NAMES = (  # a number >= 1
    "INPUT_RETRY_COUNT",
    "UPGRADE_SEARCH_ATTEMPTS",
    "FAILED_UPGRADE_SEARCHES_BEFORE_SCROLL",
    "UPGRADES_BEFORE_STATS",
    "UPGRADE_STATION_VERIFY_SEARCH_ATTEMPTS",
    "UPGRADE_STATION_DISAPPEAR_CONFIRMATION_COUNT",
    "NEW_LEVEL_SEARCH_ATTEMPTS",
    "UNLOCK_SEARCH_ATTEMPTS",
    "MAX_SCROLL_CYCLES",
    "MAX_IDLE_PASS_ATTEMPTS",
    "SCROLL_INCREMENT_STEP",
    "RED_ICON_MIN_MATCHES",
    "RED_ICON_FAST_MIN_DISTANCE",
    "BOX_MIN_MATCHES",
    "BOX_MIN_DISTANCE",
    "UPGRADE_STATION_CANDIDATE_MIN_DISTANCE",
    "CLOSE_BUTTON_MIN_DISTANCE",
    "CLOSE_BUTTON_MAX_CONSECUTIVE_CLICKS",
    "RESUME_MAX_ATTEMPTS",
    "TELEGRAM_QUEUE_MAXSIZE",
)
_HSV_RANGE_NAMES = (
    "RED_ICON_HSV_RANGES",
    "BOX_HSV_RANGES",
    "UPGRADE_STATION_HSV_RANGES",
    "CLOSE_BUTTON_HSV_RANGES",
    "CLOSE_BUTTON_BLOCK_HSV_RANGES",
)
_TEMPLATE_NAME_TUPLES = (
    "RED_ICON_FAST_TEMPLATE_NAMES",
    "RED_ICON_NORMAL_TEMPLATE_NAMES",
    "BOX_TEMPLATE_NAMES",
)


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _hsv_ranges_problem(ranges: Any) -> str | None:
    if not isinstance(ranges, tuple) or not ranges:
        return "must be a non-empty tuple of (lower, upper) HSV pairs"
    for pair in ranges:
        if not isinstance(pair, tuple) or len(pair) != 2:
            return f"entry {pair!r} is not a (lower, upper) pair"
        for bound in pair:
            if not isinstance(bound, tuple) or len(bound) != 3 or not all(_is_number(v) for v in bound):
                return f"bound {bound!r} is not an (h, s, v) triple"
            hue, saturation, value = bound
            if not (0 <= hue <= 179 and 0 <= saturation <= 255 and 0 <= value <= 255):
                return f"bound {bound!r} is outside H 0-179, S 0-255, V 0-255"
    return None


def validate_config() -> None:
    """Fails loudly at startup when config.py holds a value the bot cannot run with, instead of
    letting a typo surface later as erratic behavior. Ranges and cross-field rules mirror v2's
    BotConfig validation; every problem found is reported at once."""
    problems: list[str] = []
    numbers: dict[str, float] = {}

    def read(name: str) -> Any:
        if not hasattr(config, name):
            problems.append(f"{name} is missing")
            return None
        return getattr(config, name)

    def check(names: tuple[str, ...], rule: str, valid: Any) -> None:
        for name in names:
            value = read(name)
            if value is None:
                continue
            if not _is_number(value):
                problems.append(f"{name} must be a finite number, got {value!r}")
            elif not valid(value):
                problems.append(f"{name} must be {rule}, got {value}")
            else:
                numbers[name] = value

    check(_FRACTION_NAMES, "in (0, 1]", lambda v: 0.0 < v <= 1.0)
    check(_NON_NEGATIVE_NAMES, ">= 0", lambda v: v >= 0)
    check(_POSITIVE_NAMES, "> 0", lambda v: v > 0)
    check(_AT_LEAST_ONE_NAMES, ">= 1", lambda v: v >= 1)
    check(("MAX_BOX_ONLY_PASSES",), ">= 2", lambda v: v >= 2)
    check(("CLOSE_BUTTON_BLOCK_WINDOW",), ">= 3", lambda v: v >= 3)

    for name in _HSV_RANGE_NAMES:
        ranges = read(name)
        problem = None if ranges is None else _hsv_ranges_problem(ranges)
        if problem is not None:
            problems.append(f"{name} {problem}")
    for name in _TEMPLATE_NAME_TUPLES:
        names = read(name)
        if names is not None and (
            not isinstance(names, tuple) or not names or not all(isinstance(n, str) and n for n in names)
        ):
            problems.append(f"{name} must be a non-empty tuple of template names")
    if read("CLOSE_BUTTON_ENABLED"):
        names = read("CLOSE_BUTTON_TEMPLATE_NAMES")
        if not isinstance(names, tuple) or not names or not all(isinstance(n, str) and n for n in names):
            problems.append("CLOSE_BUTTON_ENABLED is on but CLOSE_BUTTON_TEMPLATE_NAMES is empty")
    if read("GAME_RECOVERY_ENABLED"):
        for name in ("GAME_RECOVERY_ADB_PATH", "GAME_RECOVERY_PACKAGE_HINT"):
            value = read(name)
            if not isinstance(value, str) or not value.strip():
                problems.append(f"GAME_RECOVERY_ENABLED is on but {name} is blank")

    # Cross-field rules a single constant cannot see.
    low = numbers.get("UPGRADE_HOLD_CHECK_INTERVAL_MIN")
    high = numbers.get("UPGRADE_HOLD_CHECK_INTERVAL_MAX")
    if low is not None and high is not None and low > high:
        problems.append(f"UPGRADE_HOLD_CHECK_INTERVAL_MIN ({low}) must be <= ..._MAX ({high})")
    max_y, extended_y = numbers.get("MAX_SEARCH_Y"), numbers.get("EXTENDED_SEARCH_Y")
    if max_y is not None and extended_y is not None and max_y > extended_y:
        problems.append(
            f"MAX_SEARCH_Y ({max_y}) must be <= EXTENDED_SEARCH_Y ({extended_y}), or the red-icon "
            "scan area silently shrinks"
        )
    stall_timeout = numbers.get("STATE_STALL_TIMEOUT_SECONDS", 0)
    # WAIT_FOR_UNLOCK's attempt cap is deliberately excluded: the watchdog, not that cap, ends a
    # stuck wait, so its budget may exceed the stall timeout on purpose.
    for label, attempts, interval in (
        ("UPGRADE_SEARCH_ATTEMPTS x UPGRADE_SEARCH_INTERVAL", "UPGRADE_SEARCH_ATTEMPTS", "UPGRADE_SEARCH_INTERVAL"),
        (
            "UPGRADE_STATION_VERIFY_SEARCH_ATTEMPTS x UPGRADE_STATION_VERIFY_SEARCH_INTERVAL",
            "UPGRADE_STATION_VERIFY_SEARCH_ATTEMPTS",
            "UPGRADE_STATION_VERIFY_SEARCH_INTERVAL",
        ),
        ("NEW_LEVEL_SEARCH_ATTEMPTS x NEW_LEVEL_SEARCH_INTERVAL", "NEW_LEVEL_SEARCH_ATTEMPTS", "NEW_LEVEL_SEARCH_INTERVAL"),
    ):
        if attempts in numbers and interval in numbers and stall_timeout > 0:
            worst_case = numbers[attempts] * numbers[interval]
            if worst_case >= stall_timeout:
                problems.append(
                    f"{label} worst case ({worst_case:.3f}s) must be less than "
                    f"STATE_STALL_TIMEOUT_SECONDS ({stall_timeout}s), or the watchdog can reset a "
                    "state that is still legitimately retrying"
                )

    if problems:
        raise ConfigError("config.py has %d problem(s):\n  - %s" % (len(problems), "\n  - ".join(problems)))


def setup_logging() -> None:
    global log_listener, log_handlers
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_level = logging.DEBUG if config.DEBUG else logging.INFO

    outputs: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    try:
        logs_dir = Path(config.LOGS_DIR)
        logs_dir.mkdir(parents=True, exist_ok=True)
        outputs.append(
            RotatingFileHandler(logs_dir / "bot.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8")
        )
    except OSError as exc:
        print(f"Log file unavailable; using console only: {exc}", file=sys.stderr)
    for handler in outputs:
        handler.setLevel(log_level)
        handler.setFormatter(logging.Formatter(log_format))

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()

    if log_listener is not None:
        log_listener.stop()

    log_queue: queue.SimpleQueue[logging.LogRecord] = queue.SimpleQueue()
    root_logger.addHandler(QueueHandler(log_queue))
    logging.raiseExceptions = False  # a broken log handler must never take the bot down

    log_handlers = outputs
    log_listener = QueueListener(log_queue, *outputs, respect_handler_level=True)
    log_listener.start()


def shutdown_logging() -> None:
    global log_listener, log_handlers
    logging.getLogger().handlers.clear()
    if log_listener is not None:
        log_listener.stop()
    for handler in log_handlers:
        handler.close()
    log_listener = None
    log_handlers = []


def _print_startup_banner() -> None:
    print("=" * 60)
    print("Eatventure Bot - Screen Automation Tool")
    print("=" * 60)
    print(f"Window Title: {config.WINDOW_TITLE}")
    print(f"Match Threshold: {config.MATCH_THRESHOLD * 100}%")
    print(f"Assets Directory: {config.ASSETS_DIR}")
    print("=" * 60)


def _run_bot_event_loop() -> None:
    while not should_exit.is_set():
        if bot_toggle_requested.is_set():
            bot_toggle_requested.clear()
            _toggle_bot_running(logging.getLogger(__name__))
        elif mode_toggle_requested.is_set():
            mode_toggle_requested.clear()
            _toggle_red_icon_mode(logging.getLogger(__name__))
        elif bot_instance is not None and bot_instance.running:
            bot_instance.step()
        elif bot_instance is not None:
            bot_instance.poll_resume(_last_key_at)  # a no-op unless it stopped itself on an error
        should_exit.wait(config.EVENT_LOOP_INTERVAL)


def _request_exit(_signum: int, _frame: Any) -> None:
    if bot_instance is not None:
        bot_instance.request_stop()
    should_exit.set()


def _cleanup_runtime(listener: keyboard.Listener | None) -> None:
    if bot_instance is not None:
        try:
            bot_instance.close()
        except Exception:
            logging.getLogger(__name__).exception("Bot cleanup failed")
    if listener is not None:
        listener.stop()
        listener.join(timeout=1.0)
    shutdown_logging()


def main() -> int:
    global bot_instance
    listener = None
    previous_signal_handlers: dict[int, Any] = {}

    _print_startup_banner()

    try:
        setup_logging()
        validate_config()
        should_exit.clear()
        bot_toggle_requested.clear()
        mode_toggle_requested.clear()
        with _pressed_keys_lock:
            _pressed_keys.clear()
        for signal_number in (signal.SIGINT, signal.SIGTERM):
            previous_signal_handlers[signal_number] = signal.getsignal(signal_number)
            signal.signal(signal_number, _request_exit)

        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.start()

        bot_instance = EatventureBot()

        logger = logging.getLogger(__name__)
        logger.info("Bot initialized and ready")
        logger.info("Press Z to select the active-event count and PRIME the bot")
        logger.info(
            "After priming, focus '%s' and press Z again to START",
            config.WINDOW_TITLE,
        )
        logger.info("Press Z while running to STOP the bot")
        logger.info("Press M while stopped to toggle Fast/Normal red-icon matching")
        logger.info("Press X to see window-relative cursor position")
        logger.info("Press P to EXIT the program")

        _run_bot_event_loop()

        logger.info("Program exiting")
    except ConfigError as exc:
        logging.getLogger(__name__).error("Invalid config.py: %s", exc)
        return 1
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Bot stopped by user (Ctrl+C)")
        return 0
    except Exception:
        logging.getLogger(__name__).exception("Fatal error")
        return 1
    finally:
        for signal_number, previous_handler in previous_signal_handlers.items():
            signal.signal(signal_number, previous_handler)
        _cleanup_runtime(listener)

    return 0


if __name__ == "__main__":
    sys.exit(main())
