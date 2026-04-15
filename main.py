import argparse
import logging
from logging.handlers import RotatingFileHandler
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
    import threading
    import types
    import unittest
    from unittest import mock

    import cv2
    import numpy as np

    from bot import EatventureBot, HistoricalLearner, State, VisionPersistence
    from image_matcher import ImageMatcher
    from mouse_controller import MouseController
    from window_capture import WindowCapture

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

        def test_hold_at_returns_false_when_mouse_down_is_blocked(self):
            self.controller._resolve_screen_position = lambda *args, **kwargs: (100, 200)
            self.controller._send_mouse_down = lambda *args, **kwargs: False
            mouse_up_calls = []
            self.controller._send_mouse_up = lambda *args, **kwargs: mouse_up_calls.append(args)
            self.controller._sleep = lambda *args, **kwargs: None

            result = self.controller.hold_at(100, 200, duration=0.01, relative=False)

            self.assertFalse(result)
            self.assertEqual(mouse_up_calls, [])

        def test_click_returns_false_when_cursor_positioning_fails(self):
            self.controller._resolve_screen_position = lambda *args, **kwargs: (100, 200)
            self.controller._sleep = lambda *args, **kwargs: None
            self.controller._validate_pre_click_target = lambda *args, **kwargs: True

            with mock.patch("mouse_controller.win32api.GetCursorPos", return_value=(0, 0)):
                with mock.patch("mouse_controller.win32api.SetCursorPos", side_effect=RuntimeError("boom")) as set_cursor:
                    with mock.patch("mouse_controller.win32api.mouse_event") as mouse_event:
                        result = self.controller.click(100, 200, relative=False)

            self.assertFalse(result)
            self.assertGreaterEqual(set_cursor.call_count, 1)
            mouse_event.assert_not_called()

        def test_click_recovers_after_transient_cursor_position_failure(self):
            self.controller._resolve_screen_position = lambda *args, **kwargs: (100, 200)
            self.controller._sleep = lambda *args, **kwargs: None
            self.controller._validate_pre_click_target = lambda *args, **kwargs: True
            self.controller.recovery_callback = mock.Mock()
            cursor = {"pos": (0, 0), "failures": 0}

            def fake_set_cursor(target):
                if cursor["failures"] == 0:
                    cursor["failures"] += 1
                    raise RuntimeError("boom")
                cursor["pos"] = target

            with mock.patch("mouse_controller.win32api.GetCursorPos", side_effect=lambda: cursor["pos"]):
                with mock.patch("mouse_controller.win32api.SetCursorPos", side_effect=fake_set_cursor):
                    with mock.patch("mouse_controller.win32api.mouse_event") as mouse_event:
                        result = self.controller.click(100, 200, relative=False)

            self.assertTrue(result)
            self.controller.recovery_callback.assert_called()
            self.assertEqual(mouse_event.call_count, 2)

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
        def test_step_rebinds_mouse_handle_after_window_refresh(self):
            bot = EatventureBot.__new__(EatventureBot)
            rebinds = []
            bot.window_capture = types.SimpleNamespace(
                hwnd=202,
                ensure_window_ready=lambda resize_on_refresh=False: True,
            )
            bot.mouse_controller = types.SimpleNamespace(
                set_window_handle=lambda hwnd: rebinds.append(hwnd),
            )
            bot.overlay = None
            bot._sync_window_bindings = EatventureBot._sync_window_bindings.__get__(bot, EatventureBot)
            bot._clear_capture_cache = lambda: None
            bot._apply_tuning = lambda: None
            bot._enforce_state_min_interval = lambda: None
            bot.state_machine = types.SimpleNamespace(update=lambda: None)
            bot.running = True

            EatventureBot.step(bot)

            self.assertEqual(rebinds, [202])

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

        def test_hold_upgrade_station_advances_after_spam_click_abort(self):
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
            bot.red_icons = []
            state = EatventureBot.handle_hold_upgrade_station(bot, None)

            self.assertEqual(state, State.UPGRADE_STATS)
            self.assertEqual(bot.current_red_icon_index, 1)
            self.assertEqual(bot.red_icon_processed_count, 1)

        def test_click_red_icon_forbidden_skip_advances_queue(self):
            bot = EatventureBot.__new__(EatventureBot)
            bot.check_critical_interrupts = lambda *args, **kwargs: False
            bot._capture = lambda *args, **kwargs: np.zeros((100, 100, 3), dtype=np.uint8)
            bot.vision_optimizer = types.SimpleNamespace(
                enabled=False,
                update_red_icon_confidences=lambda *args, **kwargs: None,
            )
            bot._is_red_icon_present_at = lambda *args, **kwargs: True
            bot._refine_red_icon_position = lambda *args, **kwargs: ((10, 20), False, 0.0)
            bot._is_asset_click_safe = lambda *args, **kwargs: False
            blackout_hits = []
            bot._add_to_blackout = lambda x, y: blackout_hits.append((x, y))
            bot.red_icons = [(0.99, 10, 20), (0.98, 30, 40)]
            bot.current_red_icon_index = 0
            bot.mouse_controller = types.SimpleNamespace(
                click=lambda *args, **kwargs: False,
                is_in_forbidden_zone=lambda *args, **kwargs: True,
            )
            bot.tuner = types.SimpleNamespace(record_click_result=lambda *args, **kwargs: None)
            bot._apply_tuning = lambda *args, **kwargs: None

            state = EatventureBot.handle_click_red_icon(bot, None)

            self.assertEqual(state, State.CLICK_RED_ICON)
            self.assertEqual(bot.current_red_icon_index, 1)
            self.assertEqual(blackout_hits, [(10, 20)])

        def test_search_upgrade_station_forbidden_skip_advances_queue(self):
            bot = EatventureBot.__new__(EatventureBot)
            bot.check_critical_interrupts = lambda *args, **kwargs: False
            bot._capture = lambda *args, **kwargs: np.zeros((100, 100, 3), dtype=np.uint8)
            bot.templates = {
                "upgradeStation": (np.zeros((4, 4, 3), dtype=np.uint8), None),
            }
            bot.image_matcher = types.SimpleNamespace(
                find_template=lambda *args, **kwargs: (True, 0.97, 50, 60),
                check_upgrade_station_hsv=lambda *args, **kwargs: True,
            )
            bot.mouse_controller = types.SimpleNamespace(
                is_in_forbidden_zone=lambda *args, **kwargs: True,
            )
            miss_counter = {"count": 0}
            bot.vision_optimizer = types.SimpleNamespace(
                enabled=False,
                update_upgrade_station_miss=lambda: miss_counter.__setitem__("count", miss_counter["count"] + 1),
                update_upgrade_station_confidence=lambda *args, **kwargs: None,
            )
            recorded_search_results = []
            bot.tuner = types.SimpleNamespace(
                search_interval=0.0,
                record_search_result=lambda result: recorded_search_results.append(result),
            )
            bot._apply_tuning = lambda *args, **kwargs: None
            bot.red_icons = [(0.99, 10, 20), (0.98, 30, 40)]
            bot.current_red_icon_index = 0
            bot.red_icon_processed_count = 0
            bot.successful_red_icon_positions = []
            bot.upgrade_found_in_cycle = False
            bot.consecutive_failed_cycles = 0
            state = EatventureBot.handle_search_upgrade_station(bot, None)

            self.assertEqual(state, State.CLICK_RED_ICON)
            self.assertEqual(bot.current_red_icon_index, 1)
            self.assertEqual(bot.red_icon_processed_count, 1)
            self.assertEqual(miss_counter["count"], 1)
            self.assertEqual(recorded_search_results, [False])

        def test_hold_upgrade_station_skips_after_abort(self):
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
            bot.red_icons = [(0.99, 10, 20), (0.98, 30, 40)]
            state = EatventureBot.handle_hold_upgrade_station(bot, None)

            self.assertEqual(state, State.CLICK_RED_ICON)
            self.assertEqual(bot.current_red_icon_index, 1)
            self.assertEqual(bot.red_icon_processed_count, 1)

        def test_click_red_icon_exhausted_queue_continues_to_check_unlock(self):
            bot = EatventureBot.__new__(EatventureBot)
            bot.check_critical_interrupts = lambda *args, **kwargs: False
            bot._capture = lambda *args, **kwargs: np.zeros((100, 100, 3), dtype=np.uint8)
            bot.vision_optimizer = types.SimpleNamespace(
                enabled=False,
                update_red_icon_confidences=lambda *args, **kwargs: None,
            )
            bot.red_icons = [(0.99, 10, 20)]
            bot.current_red_icon_index = 0
            bot._is_red_icon_present_at = lambda *args, **kwargs: False

            state = EatventureBot.handle_click_red_icon(bot, None)

            self.assertEqual(state, State.CHECK_UNLOCK)
            self.assertEqual(bot.current_red_icon_index, 1)

        def test_upgrade_stats_without_primary_actions_enters_fallback_boxes(self):
            bot = EatventureBot.__new__(EatventureBot)
            bot.check_critical_interrupts = lambda *args, **kwargs: False
            bot._click_idle = lambda *args, **kwargs: None
            bot._capture = lambda *args, **kwargs: np.zeros((100, 100, 3), dtype=np.uint8)
            bot._has_stats_upgrade_icon = lambda *args, **kwargs: (False, 0.0)
            bot._consume_asset_action_completed = (
                EatventureBot._consume_asset_action_completed.__get__(bot, EatventureBot)
            )
            bot.vision_optimizer = types.SimpleNamespace(
                enabled=False,
                update_stats_upgrade_miss=lambda *args, **kwargs: None,
            )
            bot._asset_action_completed = False

            state = EatventureBot.handle_upgrade_stats(bot, None)

            self.assertEqual(state, State.OPEN_BOXES)

        def test_upgrade_stats_restarts_primary_loop_when_primary_action_completed(self):
            bot = EatventureBot.__new__(EatventureBot)
            bot.check_critical_interrupts = lambda *args, **kwargs: False
            bot._click_idle = lambda *args, **kwargs: None
            bot._capture = lambda *args, **kwargs: np.zeros((100, 100, 3), dtype=np.uint8)
            bot._has_stats_upgrade_icon = lambda *args, **kwargs: (False, 0.0)
            bot._consume_asset_action_completed = (
                EatventureBot._consume_asset_action_completed.__get__(bot, EatventureBot)
            )
            bot.vision_optimizer = types.SimpleNamespace(
                enabled=False,
                update_stats_upgrade_miss=lambda *args, **kwargs: None,
            )
            bot._asset_action_completed = True

            state = EatventureBot.handle_upgrade_stats(bot, None)

            self.assertEqual(state, State.FIND_RED_ICONS)
            self.assertFalse(bot._asset_action_completed)

        def test_upgrade_stats_success_restarts_primary_loop_before_fallback(self):
            bot = EatventureBot.__new__(EatventureBot)
            bot.check_critical_interrupts = lambda *args, **kwargs: False
            bot._click_idle = lambda *args, **kwargs: None
            bot._capture = lambda *args, **kwargs: np.zeros((100, 100, 3), dtype=np.uint8)
            bot._has_stats_upgrade_icon = lambda *args, **kwargs: (True, 0.99)
            bot._should_interrupt_for_new_level = lambda *args, **kwargs: False
            bot._mark_asset_action_completed = (
                EatventureBot._mark_asset_action_completed.__get__(bot, EatventureBot)
            )
            bot._consume_asset_action_completed = (
                EatventureBot._consume_asset_action_completed.__get__(bot, EatventureBot)
            )
            bot.mouse_controller = types.SimpleNamespace(
                click=lambda *args, **kwargs: True,
                spam_click_at=lambda *args, **kwargs: True,
            )
            bot.sleep = lambda *args, **kwargs: None
            bot.vision_optimizer = types.SimpleNamespace(
                enabled=False,
                update_stats_upgrade_confidence=lambda *args, **kwargs: None,
                update_stats_upgrade_miss=lambda *args, **kwargs: None,
            )
            bot._asset_action_completed = False

            state = EatventureBot.handle_upgrade_stats(bot, None)

            self.assertEqual(state, State.FIND_RED_ICONS)
            self.assertFalse(bot._asset_action_completed)

        def test_find_red_icons_forbidden_only_continues_asset_cycle_before_scroll(self):
            bot = EatventureBot.__new__(EatventureBot)
            bot.check_critical_interrupts = lambda *args, **kwargs: False
            bot._click_idle = lambda *args, **kwargs: None
            bot._continue_asset_cycle_after_red_scan = (
                EatventureBot._continue_asset_cycle_after_red_scan.__get__(bot, EatventureBot)
            )
            bot._resolve_red_icon_zone_state = lambda: {
                "safe_present": False,
                "forbidden_present": True,
                "actionable_icons": [],
                "forbidden_count": 1,
            }
            bot.red_icons = [(0.99, 10, 20)]
            bot.current_red_icon_index = 3
            bot.red_icon_cycle_count = 2

            state = EatventureBot.handle_find_red_icons(bot, None)

            self.assertEqual(state, State.CHECK_UNLOCK)
            self.assertEqual(bot.red_icons, [])
            self.assertEqual(bot.current_red_icon_index, 0)
            self.assertEqual(bot.red_icon_cycle_count, 0)

        def test_find_red_icons_without_targets_continues_asset_cycle_before_scroll(self):
            bot = EatventureBot.__new__(EatventureBot)
            bot.check_critical_interrupts = lambda *args, **kwargs: False
            bot._click_idle = lambda *args, **kwargs: None
            bot._continue_asset_cycle_after_red_scan = (
                EatventureBot._continue_asset_cycle_after_red_scan.__get__(bot, EatventureBot)
            )
            bot._resolve_red_icon_zone_state = lambda: {
                "safe_present": False,
                "forbidden_present": False,
                "actionable_icons": [],
                "forbidden_count": 0,
            }
            bot.red_icons = [(0.99, 10, 20)]
            bot.current_red_icon_index = 1
            bot.red_icon_cycle_count = 4

            state = EatventureBot.handle_find_red_icons(bot, None)

            self.assertEqual(state, State.CHECK_UNLOCK)
            self.assertEqual(bot.red_icons, [])
            self.assertEqual(bot.current_red_icon_index, 0)
            self.assertEqual(bot.red_icon_cycle_count, 0)

        def test_search_miss_flows_into_stats_before_boxes(self):
            bot = EatventureBot.__new__(EatventureBot)
            bot.check_critical_interrupts = lambda *args, **kwargs: False
            bot._capture = lambda *args, **kwargs: np.zeros((100, 100, 3), dtype=np.uint8)
            bot.templates = {}
            bot.vision_optimizer = types.SimpleNamespace(
                enabled=False,
                update_upgrade_station_miss=lambda: None,
                update_upgrade_station_confidence=lambda *args, **kwargs: None,
            )
            bot.tuner = types.SimpleNamespace(
                search_interval=0.0,
                record_search_result=lambda *args, **kwargs: None,
            )
            bot._apply_tuning = lambda *args, **kwargs: None
            bot.red_icons = []
            bot.current_red_icon_index = 0
            bot.red_icon_processed_count = 0
            bot.successful_red_icon_positions = []
            bot.upgrade_found_in_cycle = False
            bot.consecutive_failed_cycles = 0

            state = EatventureBot.handle_search_upgrade_station(bot, None)

            self.assertEqual(state, State.UPGRADE_STATS)

        def test_step_recovers_from_unexpected_exception(self):
            bot = EatventureBot.__new__(EatventureBot)
            bot.running = True
            bot._apply_tuning = lambda *args, **kwargs: None
            bot._enforce_state_min_interval = lambda *args, **kwargs: None
            bot._interrupt_lock = threading.RLock()
            bot._new_level_event = threading.Event()
            bot._new_level_interrupt = None
            bot._clear_new_level_interrupt = EatventureBot._clear_new_level_interrupt.__get__(bot, EatventureBot)
            bot._capture_lock = threading.Lock()
            bot._capture_cache = {}
            bot._new_level_cache = {"timestamp": 0.0, "result": (False, 0.0, 0, 0), "max_y": None}
            bot._new_level_red_icon_cache = {"timestamp": 0.0, "result": (False, 0.0, 0, 0), "max_y": None}
            bot._suppress_interrupts = False
            bot.red_icons = [(0.99, 10, 20)]
            bot.current_red_icon_index = 0
            bot.red_icon_cycle_count = 1
            bot.wait_for_unlock_attempts = 1
            bot.work_done = True
            bot.upgrade_found_in_cycle = True
            bot.upgrade_station_pos = (50, 50)
            bot._last_upgrade_station_pos = (50, 50)
            bot._recent_red_icon_history = [{"timestamp": time.monotonic(), "icons": []}]
            bot.completion_detected_time = None
            bot.completion_detected_by = None
            bot._reset_search_cycle = lambda *args, **kwargs: None
            transitions = []

            class FailingStateMachine:
                def update(self_inner):
                    raise RuntimeError("boom")

                def get_state_name(self_inner):
                    return "FIND_RED_ICONS"

                def get_state(self_inner):
                    return State.FIND_RED_ICONS

                def transition(self_inner, state):
                    transitions.append(state)

            bot.state_machine = FailingStateMachine()

            EatventureBot.step(bot)

            self.assertEqual(transitions, [State.FIND_RED_ICONS])
            self.assertEqual(bot.red_icons, [])
            self.assertEqual(bot.current_red_icon_index, 0)
            self.assertIsNone(bot.upgrade_station_pos)

        def test_scroll_stage_oscillation_expands_and_resets(self):
            bot = EatventureBot.__new__(EatventureBot)
            bot.check_critical_interrupts = lambda *args, **kwargs: False
            bot._click_idle = lambda *args, **kwargs: None
            bot._sleep_with_interrupt = lambda *args, **kwargs: False
            bot._should_interrupt_for_new_level = lambda *args, **kwargs: False
            bot._oscillation_cycle_index = 1
            bot._oscillation_leg_direction = 1
            bot._oscillation_leg_progress = 0
            bot._scroll_break_sequence_pending = False

            scroll_calls = []
            bot.searcher = types.SimpleNamespace(
                perform_scroll=(
                    lambda direction, distance_ratio=None, duration=None:
                    scroll_calls.append((direction, distance_ratio, duration)) or True
                )
            )

            original_max_cycles = config.MAX_SCROLL_CYCLES
            original_increment = config.SCROLL_INCREMENT_STEP
            try:
                config.MAX_SCROLL_CYCLES = 2
                config.SCROLL_INCREMENT_STEP = 1
                states = [EatventureBot.handle_scroll(bot, None) for _ in range(8)]
            finally:
                config.MAX_SCROLL_CYCLES = original_max_cycles
                config.SCROLL_INCREMENT_STEP = original_increment

            self.assertEqual(
                [direction for direction, _, _ in scroll_calls],
                [1, -1, 1, 1, -1, -1, 1, -1],
            )
            self.assertEqual(states, [State.CHECK_NEW_LEVEL] * 8)
            self.assertEqual(
                [ratio for _, ratio, _ in scroll_calls],
                [config.SCROLL_DISTANCE_RATIO] * 8,
            )
            self.assertEqual(
                [duration for _, _, duration in scroll_calls],
                [config.SCROLL_DURATION] * 8,
            )

        def test_scroll_break_sequence_passthrough_routes_9_10_11(self):
            bot = EatventureBot.__new__(EatventureBot)
            bot._scroll_break_sequence_pending = True
            bot._new_level_event = threading.Event()
            bot.completion_detected_time = None
            bot.completion_detected_by = None

            state_9 = EatventureBot.handle_check_new_level(bot, None)
            state_10 = EatventureBot.handle_transition_level(bot, None)
            state_11 = EatventureBot.handle_wait_for_unlock(bot, None)

            self.assertEqual(state_9, State.TRANSITION_LEVEL)
            self.assertEqual(state_10, State.WAIT_FOR_UNLOCK)
            self.assertEqual(state_11, State.FIND_RED_ICONS)
            self.assertFalse(bot._scroll_break_sequence_pending)

        def test_open_boxes_counts_one_miss_per_empty_scan(self):
            bot = EatventureBot.__new__(EatventureBot)
            bot.check_critical_interrupts = lambda *args, **kwargs: False
            bot._click_idle = lambda *args, **kwargs: None
            bot._capture = lambda *args, **kwargs: np.zeros((100, 100, 3), dtype=np.uint8)
            bot._should_interrupt_for_new_level = lambda *args, **kwargs: False
            bot._consume_asset_action_completed = EatventureBot._consume_asset_action_completed.__get__(bot, EatventureBot)
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
            bot._asset_action_completed = False

            state = EatventureBot.handle_open_boxes(bot, None)

            self.assertEqual(miss_counter["count"], 1)
            self.assertEqual(state, State.FIND_RED_ICONS)

    class NewLevelCacheTests(unittest.TestCase):
        def test_detect_new_level_uses_explicit_screenshot_over_cache(self):
            bot = EatventureBot.__new__(EatventureBot)
            bot._capture_cache_ttl = 60.0
            bot._new_level_cache = {
                "timestamp": time.monotonic(),
                "result": (False, 0.0, 0, 0),
                "max_y": config.MAX_SEARCH_Y,
            }
            fresh_frame = object()
            bot.vision_optimizer = types.SimpleNamespace(
                enabled=False,
                update_new_level_confidence=lambda *args, **kwargs: None,
                update_new_level_miss=lambda *args, **kwargs: None,
            )
            bot._find_new_level = (
                lambda screenshot, threshold=None:
                (True, 0.99, 11, 22) if screenshot is fresh_frame else (False, 0.0, 0, 0)
            )

            result = EatventureBot._detect_new_level(
                bot,
                screenshot=fresh_frame,
                max_y=config.MAX_SEARCH_Y,
            )

            self.assertEqual(result, (True, 0.99, 11, 22))

        def test_detect_new_level_red_icon_uses_explicit_screenshot_over_cache(self):
            bot = EatventureBot.__new__(EatventureBot)
            bot._last_new_level_fail_time = 0.0
            bot._new_level_red_icon_cache = {
                "timestamp": time.monotonic(),
                "result": (False, 0.0, 0, 0),
                "max_y": config.EXTENDED_SEARCH_Y,
            }
            bot.available_red_icon_templates = [("RedIcon", np.zeros((2, 2, 3), dtype=np.uint8), None)]
            bot._iter_red_icon_templates = lambda: bot.available_red_icon_templates
            bot.image_matcher = types.SimpleNamespace(
                find_all_templates=lambda *args, **kwargs: [(0.97, 2, 2)]
            )
            bot.vision_optimizer = types.SimpleNamespace(
                enabled=False,
                update_new_level_red_icon_confidence=lambda *args, **kwargs: None,
                update_new_level_red_icon_miss=lambda *args, **kwargs: None,
            )
            bot._passes_red_color_gate = lambda *args, **kwargs: (True, 99)
            bot._passes_red_icon_template_gate = lambda *args, **kwargs: (True, {})
            bot._merge_detection = EatventureBot._merge_detection.__get__(bot, EatventureBot)
            bot._update_red_template_priority = lambda *args, **kwargs: None

            screenshot = np.zeros(
                (config.NEW_LEVEL_RED_ICON_Y_MAX + 10, config.NEW_LEVEL_RED_ICON_X_MAX + 10, 3),
                dtype=np.uint8,
            )

            result = EatventureBot._detect_new_level_red_icon(
                bot,
                screenshot=screenshot,
                max_y=config.EXTENDED_SEARCH_Y,
            )

            self.assertTrue(result[0])

    class InterruptStateTests(unittest.TestCase):
        def test_consume_new_level_interrupt_clears_payload(self):
            bot = EatventureBot.__new__(EatventureBot)
            bot._new_level_event = threading.Event()
            bot._new_level_event.set()
            bot._new_level_interrupt = {"source": "test"}
            bot._should_ignore_new_level_signal = lambda *args, **kwargs: False

            result = EatventureBot._consume_new_level_interrupt(bot)

            self.assertEqual(result, {"source": "test"})
            self.assertFalse(bot._new_level_event.is_set())
            self.assertIsNone(bot._new_level_interrupt)

        def test_background_monitor_scan_pauses_in_foreground_priority_states(self):
            bot = EatventureBot.__new__(EatventureBot)
            bot.completion_detected_time = None
            bot.state_machine = types.SimpleNamespace(get_state=lambda: State.CHECK_NEW_LEVEL)

            self.assertTrue(EatventureBot._background_monitor_scan_paused(bot))

            bot.state_machine = types.SimpleNamespace(get_state=lambda: State.WAIT_FOR_UNLOCK)
            self.assertTrue(EatventureBot._background_monitor_scan_paused(bot))

        def test_sleep_probe_defers_to_live_background_monitor_coverage(self):
            bot = EatventureBot.__new__(EatventureBot)
            bot.completion_detected_time = None
            bot._new_level_monitor_thread = types.SimpleNamespace(is_alive=lambda: True)
            bot.state_machine = types.SimpleNamespace(get_state=lambda: State.FIND_RED_ICONS)
            bot._background_monitor_scan_paused = (
                EatventureBot._background_monitor_scan_paused.__get__(bot, EatventureBot)
            )
            bot._background_monitor_has_coverage = (
                EatventureBot._background_monitor_has_coverage.__get__(bot, EatventureBot)
            )
            bot._foreground_priority_polling_active = (
                EatventureBot._foreground_priority_polling_active.__get__(bot, EatventureBot)
            )

            self.assertFalse(EatventureBot._should_active_probe_during_sleep(bot))

            bot.state_machine = types.SimpleNamespace(get_state=lambda: State.HOLD_UPGRADE_STATION)
            self.assertTrue(EatventureBot._should_active_probe_during_sleep(bot))

    class WindowRecoveryTests(unittest.TestCase):
        def test_is_window_active_recovers_rebound_handle(self):
            capture = WindowCapture.__new__(WindowCapture)
            capture.window_title = "EatventureAuto"
            capture.hwnd = 101
            capture.target_width = 360
            capture.target_height = 780
            capture._capture_lock = threading.Lock()

            with mock.patch("window_capture.win32gui.IsWindow", side_effect=[False, True]):
                with mock.patch.object(
                    WindowCapture,
                    "find_window",
                    side_effect=lambda: setattr(capture, "hwnd", 202),
                ):
                    self.assertTrue(WindowCapture.is_window_active(capture))

            self.assertEqual(capture.hwnd, 202)

        def test_print_window_failure_is_rejected(self):
            with self.assertRaises(RuntimeError):
                WindowCapture._ensure_print_window_succeeded(0, "EatventureAuto", 123)

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

        @staticmethod
        def _make_scaled_detection_bot():
            bot = EatventureBot.__new__(EatventureBot)
            bot.image_matcher = ImageMatcher(config.MATCH_THRESHOLD)
            template_path = Path(config.ASSETS_DIR) / "RedIcon13.png"
            template, mask = bot.image_matcher.load_template(template_path)
            bot.available_red_icon_templates = [("RedIcon13", template, mask)]
            bot._red_template_priority = []
            bot._red_template_hit_counts = {}
            bot._red_template_last_seen = {}
            bot._red_template_scaled_cache = {}
            bot._red_template_signatures = {
                "RedIcon13": bot.image_matcher.build_red_template_signature(template, mask=mask)
            }
            bot.vision_optimizer = types.SimpleNamespace(enabled=False)
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

        def test_detect_red_icons_second_pass_recovers_scaled_icon(self):
            bot, template, _ = self._make_scaled_detection_bot()
            scale = 1.12
            scaled = cv2.resize(template, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)
            frame = np.full((240, 240, 3), 255, dtype=np.uint8)
            x1, y1 = 100, 90
            h, w = scaled.shape[:2]
            frame[y1:y1 + h, x1:x1 + w] = scaled

            detections = EatventureBot._detect_red_icons_in_view(
                bot,
                frame,
                max_y=240,
                threshold_override=0.935,
                min_distance=20,
            )

            self.assertTrue(detections)

        def test_is_red_icon_present_second_pass_recovers_scaled_icon(self):
            bot, template, _ = self._make_scaled_detection_bot()
            scale = 1.12
            scaled = cv2.resize(template, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)
            frame = np.full((240, 240, 3), 255, dtype=np.uint8)
            x1, y1 = 96, 92
            h, w = scaled.shape[:2]
            frame[y1:y1 + h, x1:x1 + w] = scaled
            center_x = x1 + (w // 2)
            center_y = y1 + (h // 2)

            present = EatventureBot._is_red_icon_present_at(
                bot,
                center_x,
                center_y,
                screenshot=frame,
                threshold_override=0.935,
            )

            self.assertTrue(present)

    suite = unittest.TestSuite()
    for case in (
        TimingControllerTests,
        VisionPersistenceTests,
        HistoricalLearnerBootstrapTests,
        BotRegressionTests,
        NewLevelCacheTests,
        InterruptStateTests,
        WindowRecoveryTests,
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
    print(f"Templates Directory: {config.ASSETS_DIR}")
    print("=" * 60)

    setup_logging()
    should_exit = False

    listener = keyboard.Listener(on_press=on_press)
    listener.start()
    bot = None

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
                if not bot.window_capture.is_window_active():
                    logger.error("Window '%s' is no longer active; stopping bot", config.WINDOW_TITLE)
                    should_exit = True
                    bot.stop()
                    continue
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
        if bot is not None:
            try:
                bot.stop()
            except Exception as exc:
                logging.error("Failed to stop bot cleanly during shutdown: %s", exc, exc_info=True)
        bot_instance = None
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
