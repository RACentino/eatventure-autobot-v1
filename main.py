import argparse
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
import time
import unittest

import config

bot_instance = None
should_exit = False
keyboard = None
win32api = None
win32gui = None


def _load_pywin32():
    global win32api, win32gui
    if win32api is not None and win32gui is not None:
        return True
    try:
        import win32api as _win32api
        import win32gui as _win32gui
    except ImportError:
        print("Error: pywin32 is not installed correctly.")
        print("Please run: pip install pywin32")
        return False
    win32api = _win32api
    win32gui = _win32gui
    return True


def _load_keyboard_listener():
    global keyboard
    if keyboard is not None:
        return True
    try:
        from pynput import keyboard as _keyboard
    except ImportError:
        print("Error: pynput is not installed.")
        print("Please run: pip install pynput")
        return False
    keyboard = _keyboard
    return True


def on_press(key):
    global should_exit
    try:
        if not hasattr(key, "char"):
            return
        logger = logging.getLogger(__name__)
        if key.char == "x":
            if bot_instance and bot_instance.window_capture.hwnd:
                screen_x, screen_y = win32api.GetCursorPos()
                win_x, win_y = win32gui.ClientToScreen(bot_instance.window_capture.hwnd, (0, 0))
                logger.info("[X pressed] Window position: (%s, %s)", screen_x - win_x, screen_y - win_y)
            else:
                logger.info("[X pressed] Bot not initialized yet")
        elif key.char == "z":
            if not bot_instance:
                logger.info("[Z pressed] Bot not initialized yet")
                return
            if bot_instance.running:
                bot_instance.stop()
                bot_instance.telegram.notify_bot_stopped()
                logger.info("[Z pressed] Bot STOPPED")
            else:
                bot_instance.start()
                bot_instance.telegram.notify_bot_started()
                logger.info("[Z pressed] Bot STARTED")
        elif key.char == "c":
            if bot_instance:
                bot_instance.wipe_memory()
                logger.info("[C pressed] AI memory wiped")
        elif key.char == "p":
            logger.info("[P pressed] Exiting program")
            should_exit = True
    except Exception as exc:
        logging.getLogger(__name__).error("Keyboard listener error: %s", exc)


def setup_logging():
    logs_dir = Path(config.LOGS_DIR)
    logs_dir.mkdir(exist_ok=True)

    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_level = logging.DEBUG if config.DEBUG else logging.INFO

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(log_format))

    file_handler = RotatingFileHandler(
        logs_dir / "bot.log",
        maxBytes=max(1, int(config.LOG_FILE_MAX_BYTES)),
        backupCount=max(1, int(config.LOG_FILE_BACKUP_COUNT)),
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(log_format))

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)


def run_self_tests():
    loader = unittest.defaultTestLoader
    suite = loader.discover(start_dir=str(Path(__file__).parent / "tests"), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


def run_bot():
    global bot_instance, should_exit
    if not _load_pywin32():
        return 1
    if not _load_keyboard_listener():
        return 1

    from bot import EatventureBot

    print("=" * 60)
    print("Eatventure Bot - Screen Automation Tool")
    print("=" * 60)
    print(f"Window Title: {config.WINDOW_TITLE}")
    print(f"Match Threshold: {config.MATCH_THRESHOLD * 100}%")
    print(f"Assets Directory: {config.ASSETS_DIR}")
    print("=" * 60)

    setup_logging()
    should_exit = False
    listener = keyboard.Listener(on_press=on_press)
    listener.start()

    try:
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
            if config.MAIN_LOOP_DELAY > 0:
                time.sleep(config.MAIN_LOOP_DELAY)

        logger.info("Program exiting")
        return 0
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Bot stopped by user (Ctrl+C)")
        return 0
    except Exception as exc:
        logging.getLogger(__name__).error("Fatal error: %s", exc, exc_info=True)
        return 1
    finally:
        if bot_instance is not None and bot_instance.running:
            bot_instance.stop()
        listener.stop()


def build_parser():
    parser = argparse.ArgumentParser(description="Eatventure bot entrypoint")
    parser.add_argument("--self-test", action="store_true", help="Run the unit test suite")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.self_test:
        return run_self_tests()
    return run_bot()


if __name__ == "__main__":
    sys.exit(main())
