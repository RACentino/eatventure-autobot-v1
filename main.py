import argparse
import logging
from pathlib import Path
import sys
import time

import config

current_match_index = 0
current_matches = []
bot_instance = None
z_pressed = False
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
        print("Error: 'pywin32' is not installed correctly.")
        print("Please run: pip install pywin32")
        print("If you still see this error, you might need to run: python Scripts/pywin32_postinstall.py -install")
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
        print("Error: 'pynput' is not installed.")
        print("Please run: pip install pynput")
        return False

    keyboard = _keyboard
    return True


def on_press(key):
    global current_match_index, bot_instance, z_pressed, current_matches, should_exit
    try:
        if hasattr(key, "char"):
            if key.char == "x":
                screen_x, screen_y = win32api.GetCursorPos()
                logger = logging.getLogger(__name__)
                if bot_instance and bot_instance.window_capture.hwnd:
                    win_x, win_y = win32gui.ClientToScreen(bot_instance.window_capture.hwnd, (0, 0))
                    rel_x = screen_x - win_x
                    rel_y = screen_y - win_y
                    logger.info(f"[X pressed] Window position: ({rel_x}, {rel_y})")
                else:
                    logger.info("[X pressed] Bot not initialized yet")
            elif key.char == "z":
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
            elif key.char == "c":
                logger = logging.getLogger(__name__)
                if bot_instance:
                    try:
                        logger.info("[C pressed] Wiping AI memory...")
                        bot_instance.wipe_memory()
                    except Exception as exc:
                        logger.error(f"Failed to wipe AI memory: {exc}. Defaulting to safe state.")
                        if bot_instance.running:
                            bot_instance.stop()
                else:
                    logger.info("[C pressed] Bot not initialized yet")
            elif key.char == "p":
                logger = logging.getLogger(__name__)
                logger.info("[P pressed] Exiting program...")
                should_exit = True
    except Exception as exc:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in keyboard listener: {exc}")


def setup_logging():
    logs_dir = Path(config.LOGS_DIR)
    logs_dir.mkdir(exist_ok=True)

    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_level = logging.DEBUG if config.DEBUG else logging.INFO

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(log_format))

    file_handler = logging.FileHandler(logs_dir / "bot.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(log_format))

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    for handler in list(root_logger.handlers):
        if getattr(handler, "_eatventure_handler", False):
            root_logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass

    console_handler._eatventure_handler = True
    file_handler._eatventure_handler = True
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)


def run_self_tests():
    if not _load_pywin32():
        return 1

    import json
    import shutil
    import types
    import unittest

    import cv2
    import numpy as np

    from bot import EatventureBot, HistoricalLearner, State, VisionPersistence
    from image_matcher import ImageMatcher
    from mouse_controller import MouseController

    test_temp_root = Path(config.LOGS_DIR)

    def make_test_dir(name: str) -> Path:
        path = test_temp_root / name
        shutil.rmtree(path, ignore_errors=True)
        path.mkdir(parents=True, exist_ok=True)
        return path

    class TimingControllerTests(unittest.TestCase):
        def setUp(self):
            self.controller = MouseController(hwnd=0)

        def test_seconds_to_ns_clamps_negative_values(self):
            self.assertEqual(MouseController._seconds_to_ns(-0.25), 0)
            self.assertEqual(MouseController._seconds_to_ns(0.010), 10_000_000)

        def test_rapid_click_hold_is_capped_to_half_interval(self):
            original_hold = config.RAPID_CLICK_DOWN_UP_DELAY
            try:
                config.RAPID_CLICK_DOWN_UP_DELAY = 0.050
                hold_ns = self.controller._rapid_click_hold_ns(0.010)
            finally:
                config.RAPID_CLICK_DOWN_UP_DELAY = original_hold

            self.assertEqual(hold_ns, 5_000_000)

        def test_next_deadline_prefers_smooth_spacing_after_lateness(self):
            previous_deadline_ns = 100_000_000
            click_start_ns = 113_000_000
            interval_ns = 10_000_000

            self.assertEqual(
                MouseController._compute_next_click_deadline(
                    previous_deadline_ns,
                    click_start_ns,
                    interval_ns,
                ),
                123_000_000,
            )

        def test_next_deadline_keeps_nominal_schedule_when_on_time(self):
            previous_deadline_ns = 100_000_000
            click_start_ns = 100_500_000
            interval_ns = 10_000_000

            self.assertEqual(
                MouseController._compute_next_click_deadline(
                    previous_deadline_ns,
                    click_start_ns,
                    interval_ns,
                ),
                110_500_000,
            )

    class VisionPersistenceTests(unittest.TestCase):
        def test_load_returns_empty_dict_for_malformed_json(self):
            temp_dir = make_test_dir("test-vision-load")
            state_path = temp_dir / "vision_state.json"
            state_path.write_text("{invalid json", encoding="utf-8")

            persistence = VisionPersistence(str(state_path), save_interval=0.0)
            self.assertEqual(persistence.load(), {})

        def test_save_and_load_round_trip(self):
            temp_dir = make_test_dir("test-vision-save")
            state_path = temp_dir / "vision_state.json"
            persistence = VisionPersistence(str(state_path), save_interval=0.0)

            saved = persistence.save({"threshold": 0.95}, force=True)

            self.assertTrue(saved)
            self.assertEqual(persistence.load(), {"threshold": 0.95})

    class HistoricalLearnerBootstrapTests(unittest.TestCase):
        def test_disabled_learning_does_not_apply_persisted_profile(self):
            temp_dir = make_test_dir("test-learning-disabled")
            state_path = temp_dir / "learning_state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "records": [
                            {
                                "behavior": {
                                    "click_delay": 0.04,
                                    "move_delay": 0.002,
                                    "upgrade_click_interval": 0.01,
                                    "search_interval": 0.08,
                                },
                                "source": "test",
                                "time_spent": 5.0,
                                "timestamp": 1.0,
                            }
                        ],
                        "total_completions": 1,
                        "last_pair_processed": 0,
                        "last_batch_processed": 0,
                        "tuned_behavior": {
                            "click_delay": 0.04,
                            "move_delay": 0.002,
                            "upgrade_click_interval": 0.01,
                            "search_interval": 0.08,
                        },
                    }
                ),
                encoding="utf-8",
            )

            applied = []
            bot = types.SimpleNamespace(
                apply_learned_behavior=lambda *args, **kwargs: applied.append((args, kwargs)),
                get_runtime_behavior_snapshot=lambda: {},
            )
            persistence = VisionPersistence(str(state_path), save_interval=0.0)
            original_enabled = config.AI_LEARNING_ENABLED
            try:
                config.AI_LEARNING_ENABLED = False
                learner = HistoricalLearner(bot, persistence)
            finally:
                config.AI_LEARNING_ENABLED = original_enabled

            self.assertEqual(applied, [])
            self.assertEqual(learner._records, [])
            self.assertEqual(learner._total_completions, 0)
            self.assertEqual(learner._tuned_behavior, {})

    class BotRegressionTests(unittest.TestCase):
        def test_new_level_red_icon_recaptures_when_frame_is_too_short(self):
            bot = EatventureBot.__new__(EatventureBot)
            bot._last_new_level_fail_time = 0.0
            bot._new_level_red_icon_cache = {"timestamp": 0.0, "result": (False, 0.0, 0, 0), "max_y": None}
            template = np.zeros((10, 10, 3), dtype=np.uint8)
            bot.available_red_icon_templates = [("RedIcon", template, None)]
            bot._iter_red_icon_templates = lambda: bot.available_red_icon_templates
            bot.image_matcher = types.SimpleNamespace(find_all_templates=lambda *args, **kwargs: [])
            bot.vision_optimizer = types.SimpleNamespace(
                enabled=False,
                update_new_level_red_icon_confidence=lambda *args, **kwargs: None,
                update_new_level_red_icon_miss=lambda *args, **kwargs: None,
            )
            bot._passes_red_color_gate = lambda *args, **kwargs: (True, 100)
            bot._merge_detection = EatventureBot._merge_detection.__get__(bot, EatventureBot)
            bot._update_red_template_priority = lambda *args, **kwargs: None

            recaptured_frame = np.zeros((config.NEW_LEVEL_RED_ICON_Y_MAX + 32, 100, 3), dtype=np.uint8)
            capture_calls = []
            bot._capture = lambda max_y=None, force=False: capture_calls.append((max_y, force)) or recaptured_frame

            short_frame = np.zeros((config.MAX_SEARCH_Y, 100, 3), dtype=np.uint8)
            result = EatventureBot._detect_new_level_red_icon(
                bot,
                screenshot=short_frame,
                max_y=config.EXTENDED_SEARCH_Y,
                force=True,
            )

            self.assertEqual(result, (False, 0.0, 0, 0))
            self.assertTrue(capture_calls)
            self.assertGreaterEqual(capture_calls[-1][0], config.NEW_LEVEL_RED_ICON_Y_MAX)
            self.assertTrue(capture_calls[-1][1])

        def test_hold_upgrade_station_retries_after_spam_click_abort(self):
            bot = EatventureBot.__new__(EatventureBot)
            bot.check_critical_interrupts = lambda *args, **kwargs: False
            bot.upgrade_station_pos = (50, 50)
            bot._capture = lambda *args, **kwargs: np.zeros((100, 100, 3), dtype=np.uint8)
            bot.vision_optimizer = types.SimpleNamespace(enabled=False)
            bot._refine_template_position = lambda *args, **kwargs: ((50, 50), True)
            bot._refine_upgrade_station_click_target = lambda *args, **kwargs: ((50, 50), True)
            bot._last_upgrade_station_pos = None
            bot._is_asset_click_safe = lambda *args, **kwargs: True
            bot.mouse_controller = types.SimpleNamespace(spam_click_at=lambda *args, **kwargs: False)
            bot._click_idle = lambda *args, **kwargs: None
            bot._sleep_with_interrupt = lambda *args, **kwargs: False
            bot._should_interrupt_for_new_level = lambda *args, **kwargs: False
            bot.red_icon_processed_count = 0
            bot.current_red_icon_index = 0

            state = EatventureBot.handle_hold_upgrade_station(bot, None)

            self.assertEqual(state, State.SEARCH_UPGRADE_STATION)
            self.assertEqual(bot.current_red_icon_index, 0)

        def test_open_boxes_counts_one_miss_per_empty_scan(self):
            bot = EatventureBot.__new__(EatventureBot)
            bot.check_critical_interrupts = lambda *args, **kwargs: False
            bot._click_idle = lambda *args, **kwargs: None
            bot._capture = lambda *args, **kwargs: np.zeros((100, 100, 3), dtype=np.uint8)
            bot._should_interrupt_for_new_level = lambda *args, **kwargs: False
            bot.templates = {
                f"box{i}": (np.zeros((1, 1, 3), dtype=np.uint8), None)
                for i in range(1, 6)
            }
            miss_counter = {"count": 0}
            bot.vision_optimizer = types.SimpleNamespace(
                enabled=False,
                update_box_miss=lambda: miss_counter.__setitem__("count", miss_counter["count"] + 1),
                update_box_confidence=lambda confidence: None,
            )
            bot.image_matcher = types.SimpleNamespace(find_template=lambda *args, **kwargs: (False, 0.0, 0, 0))
            bot.mouse_controller = types.SimpleNamespace(
                is_in_forbidden_zone=lambda *args, **kwargs: False,
                click=lambda *args, **kwargs: True,
            )
            bot.work_done = False
            bot.upgrade_found_in_cycle = False
            bot.cycle_counter = 0
            bot.consecutive_failed_cycles = 0

            state = EatventureBot.handle_open_boxes(bot, None)

            self.assertEqual(miss_counter["count"], 1)
            self.assertEqual(state, State.FIND_RED_ICONS)

    class RedIconGateTests(unittest.TestCase):
        @staticmethod
        def _make_red_icon_bot():
            bot = EatventureBot.__new__(EatventureBot)
            bot.image_matcher = ImageMatcher(config.MATCH_THRESHOLD)
            template_path = Path(config.ASSETS_DIR) / "RedIcon.png"
            template, mask = bot.image_matcher.load_template(template_path)
            bot._red_template_signatures = {
                "RedIcon": bot.image_matcher.build_red_template_signature(template, mask=mask)
            }
            return bot, template, mask

        def test_real_red_icon_template_gate_passes(self):
            bot, template, mask = self._make_red_icon_bot()
            center_x = template.shape[1] // 2
            center_y = template.shape[0] // 2

            passed, metrics = EatventureBot._passes_red_icon_template_gate(
                bot,
                template,
                center_x,
                center_y,
                "RedIcon",
                template,
                mask,
            )

            self.assertTrue(passed, metrics)

        def test_template_gate_rejects_close_button_like_shape(self):
            bot, template, mask = self._make_red_icon_bot()
            h, w = template.shape[:2]
            frame = np.full((h, w, 3), 255, dtype=np.uint8)
            cv2.rectangle(frame, (2, 2), (w - 3, h - 3), (70, 70, 235), -1)
            cv2.line(frame, (4, 4), (w - 5, h - 5), (255, 255, 255), 2)
            cv2.line(frame, (w - 5, 4), (4, h - 5), (255, 255, 255), 2)

            center_x = w // 2
            center_y = h // 2
            passed, metrics = EatventureBot._passes_red_icon_template_gate(
                bot,
                frame,
                center_x,
                center_y,
                "RedIcon",
                template,
                mask,
            )

            self.assertFalse(passed, metrics)

        def test_color_gate_rejects_over_saturated_red_badge(self):
            bot, _, _ = self._make_red_icon_bot()
            frame = np.full((24, 24, 3), 255, dtype=np.uint8)
            cv2.circle(frame, (12, 12), 9, (30, 30, 220), -1)

            passed, pixel_count = EatventureBot._passes_red_color_gate(bot, frame, 12, 12)

            self.assertFalse(passed)
            self.assertGreater(pixel_count, config.RED_ICON_PIXEL_THRESHOLD)

    suite = unittest.TestSuite()
    for case in (
        TimingControllerTests,
        VisionPersistenceTests,
        HistoricalLearnerBootstrapTests,
        BotRegressionTests,
        RedIconGateTests,
    ):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))

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
    print(f"Templates Directory: {config.TEMPLATES_DIR}")
    print("=" * 60)

    setup_logging()
    should_exit = False

    listener = keyboard.Listener(on_press=on_press)
    listener.start()

    try:
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
    except Exception as exc:
        logging.error(f"\nFatal error: {exc}", exc_info=True)
        listener.stop()
        return 1
    finally:
        listener.stop()

    return 0


def build_parser():
    parser = argparse.ArgumentParser(description="Eatventure bot entrypoint")
    parser.add_argument("--self-test", action="store_true", help="Run the embedded regression tests")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.self_test:
        return run_self_tests()
    return run_bot()


if __name__ == "__main__":
    sys.exit(main())
