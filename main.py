import logging
from pathlib import Path
import sys
import time

# Dependency check
try:
    import win32api
    import win32gui
except ImportError:
    print("Error: 'pywin32' is not installed correctly.")
    print("Please run: pip install pywin32")
    print("If you still see this error, you might need to run: python Scripts/pywin32_postinstall.py -install")
    sys.exit(1)

try:
    from pynput import keyboard
except ImportError:
    print("Error: 'pynput' is not installed.")
    print("Please run: pip install pynput")
    sys.exit(1)

from pynput import keyboard

import config
from bot import EatventureBot

current_match_index = 0
current_matches = []
bot_instance = None
z_pressed = False
should_exit = False


def on_press(key):
    global current_match_index, bot_instance, z_pressed, current_matches, should_exit
    try:
        if hasattr(key, 'char'):
            if key.char == 'x':
                screen_x, screen_y = win32api.GetCursorPos()
                logger = logging.getLogger(__name__)
                if bot_instance and bot_instance.window_capture.hwnd:
                    win_x, win_y = win32gui.ClientToScreen(bot_instance.window_capture.hwnd, (0, 0))
                    rel_x = screen_x - win_x
                    rel_y = screen_y - win_y
                    logger.info(f"[X pressed] Window position: ({rel_x}, {rel_y})")
                else:
                    logger.info("[X pressed] Bot not initialized yet")
            elif key.char == 'z':
                logger = logging.getLogger(__name__)
                if bot_instance:
                    if not bot_instance.running:
                        bot_instance.start()
                        from datetime import datetime
                        bot_instance.current_level_start_time = datetime.now()
                        bot_instance.telegram.notify_bot_started()
                    else:
                        bot_instance.stop()
                        bot_instance.telegram.notify_bot_stopped()
            elif key.char == 'c':
                logger = logging.getLogger(__name__)
                if bot_instance:
                    try:
                        logger.info("[C pressed] Wiping AI memory...")
                        bot_instance.wipe_memory()
                    except Exception as e:
                        logger.error(f"Failed to wipe AI memory: {e}. Defaulting to safe state.")
                        if bot_instance.running:
                            bot_instance.stop()
                else:
                    logger.info("[C pressed] Bot not initialized yet")
            elif key.char == 'p':
                logger = logging.getLogger(__name__)
                logger.info("[P pressed] Exiting program...")
                should_exit = True
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in keyboard listener: {e}")


def setup_logging():
    logs_dir = Path(config.LOGS_DIR)
    logs_dir.mkdir(exist_ok=True)
    
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    log_level = logging.DEBUG if config.DEBUG else logging.INFO
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(log_format))
    
    file_handler = logging.FileHandler(logs_dir / 'bot.log', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(log_format))
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)


def main():
    global cursor_showing_enabled
    
    print("=" * 60)
    print("Eatventure Bot - Screen Automation Tool")
    print("=" * 60)
    print(f"Window Title: {config.WINDOW_TITLE}")
    print(f"Match Threshold: {config.MATCH_THRESHOLD * 100}%")
    print(f"Templates Directory: {config.TEMPLATES_DIR}")
    print("=" * 60)
    
    setup_logging()
    
    listener = keyboard.Listener(on_press=on_press)
    listener.start()
    
    try:
        global bot_instance
        bot = EatventureBot()
        bot_instance = bot
        
        logger = logging.getLogger(__name__)
        logger.info("Bot initialized and ready")
        logger.info("Press Z to START/STOP the bot")
        logger.info("Press X to see window-relative cursor position")
        logger.info("Press P to EXIT the program")
        
        while not should_exit:
            if bot.running:
                bot.step()
            if config.MAIN_LOOP_DELAY > 0:
                time.sleep(config.MAIN_LOOP_DELAY)
        
        logger.info("Program exiting...")
        
    except KeyboardInterrupt:
        logging.info("\nBot stopped by user (Ctrl+C)")
        listener.stop()
        return 0
    except Exception as e:
        logging.error(f"\nFatal error: {e}", exc_info=True)
        listener.stop()
        return 1
    finally:
        listener.stop()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
