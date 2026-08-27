import logging
import queue
import sys
import threading
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from pathlib import Path
from typing import Any

import win32api
import win32gui
from pynput import keyboard

import config
from bot import EatventureBot

bot_instance: EatventureBot | None = None
should_exit = threading.Event()
bot_toggle_requested = threading.Event()
log_listener: QueueListener | None = None

ForbiddenZoneBounds = tuple[int, int, int, int]
primed_event_selection: tuple[int, ForbiddenZoneBounds] | None = None


def _get_key_character(key: Any) -> str | None:
    character = getattr(key, "char", None)
    if character is None:
        return None
    return str(character).lower()


def _log_window_relative_cursor_position(logger: logging.Logger) -> None:
    if bot_instance is None or not bot_instance.window_capture.is_window_active():
        logger.info("[X pressed] Bot window is not available")
        return

    hwnd = bot_instance.window_capture.get_hwnd()
    screen_x, screen_y = win32api.GetCursorPos()
    window_x, window_y = win32gui.ClientToScreen(hwnd, (0, 0))
    logger.info("[X pressed] Window position: (%s, %s)", screen_x - window_x, screen_y - window_y)


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
    while True:
        try:
            raw_selection = input("\nType an option number and press Enter: ").strip()
        except EOFError:
            print("\nEvent selection cancelled. The bot remains stopped.")
            return None

        try:
            event_count = int(raw_selection)
        except ValueError:
            event_count = 0

        bounds = option_map.get(event_count)
        if bounds is None:
            print(f"Invalid selection. Enter one of: {valid_choices}.")
            continue

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


def _toggle_bot_running(logger: logging.Logger) -> None:
    global primed_event_selection

    if bot_instance is None:
        return
    if bot_instance.running:
        bot_instance.stop()
        bot_instance.telegram.notify_bot_stopped()
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
    started = bot_instance.start()
    if started:
        bot_instance.telegram.notify_bot_started()
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


def _request_program_exit(logger: logging.Logger) -> None:
    logger.info("[P pressed] Exiting program")
    if bot_instance is not None and bot_instance.running:
        bot_instance.request_stop()
    should_exit.set()


def on_press(key: Any) -> None:
    try:
        character = _get_key_character(key)
        if character is None:
            return

        logger = logging.getLogger(__name__)
        key_handlers = {
            "x": _log_window_relative_cursor_position,
            "z": _request_bot_toggle,
            "p": _request_program_exit,
        }
        handler = key_handlers.get(character)
        if handler is not None:
            handler(logger)
    except Exception as exc:
        logging.getLogger(__name__).error("Keyboard listener error: %s", exc)


def setup_logging() -> None:
    global log_listener
    logs_dir = Path(config.LOGS_DIR)
    logs_dir.mkdir(parents=True, exist_ok=True)

    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_level = logging.DEBUG if config.DEBUG else logging.INFO

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(log_format))

    file_handler = RotatingFileHandler(
        logs_dir / "bot.log",
        maxBytes=5_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(logging.Formatter(log_format))

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()

    if log_listener is not None:
        log_listener.stop()

    log_queue: queue.SimpleQueue[logging.LogRecord] = queue.SimpleQueue()
    queue_handler = QueueHandler(log_queue)
    root_logger.addHandler(queue_handler)

    log_listener = QueueListener(
        log_queue,
        console_handler,
        file_handler,
        respect_handler_level=True,
    )
    log_listener.start()


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
            continue
        if bot_instance is not None and bot_instance.running:
            bot_instance.step()
        should_exit.wait(config.EVENT_LOOP_INTERVAL)


def _cleanup_runtime(listener: keyboard.Listener | None) -> None:
    global log_listener
    if bot_instance is not None and bot_instance.running:
        bot_instance.stop()
    if bot_instance is not None:
        bot_instance.telegram.close()
    if listener is not None:
        listener.stop()
        listener.join(timeout=1.0)
    if log_listener is not None:
        log_listener.stop()
        log_listener = None


def main() -> int:
    global bot_instance
    listener = None

    _print_startup_banner()

    try:
        setup_logging()
        should_exit.clear()
        bot_toggle_requested.clear()

        listener = keyboard.Listener(on_press=on_press)
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
        logger.info("Press X to see window-relative cursor position")
        logger.info("Press P to EXIT the program")

        _run_bot_event_loop()

        logger.info("Program exiting")
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Bot stopped by user (Ctrl+C)")
        return 0
    except Exception:
        logging.getLogger(__name__).exception("Fatal error")
        return 1
    finally:
        _cleanup_runtime(listener)

    return 0


if __name__ == "__main__":
    sys.exit(main())
