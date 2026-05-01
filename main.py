import logging
import queue
from pathlib import Path
import sys
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler

import win32api
import win32gui
from pynput import keyboard

import config
from bot import EatventureBot
from mouse_controller import precise_sleep

bot_instance = None
should_exit = False
log_listener = None


def on_press(key):
    global should_exit
    try:
        char = getattr(key, "char", None)
        if char is None:
            return
        char = char.lower()

        logger = logging.getLogger(__name__)
        if char == "x":
            if bot_instance and bot_instance.window_capture.is_window_active():
                hwnd = bot_instance.window_capture.get_hwnd()
                screen_x, screen_y = win32api.GetCursorPos()
                win_x, win_y = win32gui.ClientToScreen(hwnd, (0, 0))
                rel_x = screen_x - win_x
                rel_y = screen_y - win_y
                logger.info("[X pressed] Window position: (%s, %s)", rel_x, rel_y)
            else:
                logger.info("[X pressed] Bot window is not available")
        elif char == "z":
            if bot_instance:
                if bot_instance.running:
                    bot_instance.stop()
                    bot_instance.telegram.notify_bot_stopped()
                    logger.info("[Z pressed] Bot STOPPED")
                else:
                    started = bot_instance.start()
                    if started:
                        bot_instance.telegram.notify_bot_started()
                        logger.info("[Z pressed] Bot STARTED")
                    else:
                        logger.warning("[Z pressed] Bot START failed")
        elif char == "c":
            if bot_instance:
                bot_instance.wipe_memory()
                logger.info("[C pressed] AI memory wiped")
        elif char == "p":
            logger.info("[P pressed] Exiting program")
            should_exit = True
    except Exception as exc:
        logging.getLogger(__name__).error("Keyboard listener error: %s", exc)


def setup_logging():
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

    log_queue = queue.SimpleQueue()
    queue_handler = QueueHandler(log_queue)
    root_logger.addHandler(queue_handler)

    log_listener = QueueListener(
        log_queue,
        console_handler,
        file_handler,
        respect_handler_level=True,
    )
    log_listener.start()


def main():
    global bot_instance, should_exit, log_listener
    listener = None

    print("=" * 60)
    print("Eatventure Bot - Screen Automation Tool")
    print("=" * 60)
    print(f"Window Title: {config.WINDOW_TITLE}")
    print(f"Match Threshold: {config.MATCH_THRESHOLD * 100}%")
    print(f"Assets Directory: {config.ASSETS_DIR}")
    print("=" * 60)

    try:
        setup_logging()
        should_exit = False

        listener = keyboard.Listener(on_press=on_press)
        listener.start()

        bot_instance = EatventureBot()

        logger = logging.getLogger(__name__)
        logger.info("Bot initialized and ready")
        logger.info("Press Z to START/STOP the bot")
        logger.info("Press X to see window-relative cursor position")
        logger.info("Press C to wipe AI memory")
        logger.info("Press P to EXIT the program")

        while not should_exit:
            if bot_instance.running:
                bot_instance.step()
            precise_sleep(0.1)

        logger.info("Program exiting")
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Bot stopped by user (Ctrl+C)")
        return 0
    except Exception as exc:
        logging.getLogger(__name__).error("Fatal error: %s", exc, exc_info=True)
        return 1
    finally:
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

    return 0


if __name__ == "__main__":
    sys.exit(main())
