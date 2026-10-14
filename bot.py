import hashlib
import logging
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple

import numpy as np
import pywintypes

import config
from image_matcher import ImageMatcher
from mouse_controller import MouseController
from state_machine import X_LOCKED_STATES, State, StateMachine
from telegram_notifier import TelegramNotifier
from window_capture import (
    ForbiddenAreaOverlay,
    WindowCapture,
    WindowCaptureError,
    WindowNotAvailableError,
)

logger = logging.getLogger(__name__)

TemplatePair = tuple[Any, Any]
BoxCandidate = tuple[float, int, int, int, int, str]
RedIcon = tuple[float, int, int]
ForbiddenZoneBounds = tuple[int, int, int, int]
AdbRunner = Callable[[Sequence[str], float], tuple[int, str]]
Point = tuple[int, int]

# The recovery window judges "is the screen alive" from its last few seconds.
_RECOVERY_TAIL_SECONDS = 5.0

# Auto-resume (see EatventureBot.poll_resume): how often the cursor is sampled for movement, how often an
# unchanged check is logged anyway, and the longest wait between failed live attempts.
_RESUME_SAMPLE_SECONDS = 1.0
_RESUME_HEARTBEAT_SECONDS = 600.0
_RESUME_MAX_BACKOFF_SECONDS = 900.0


class LevelMark(NamedTuple):
    """Cumulative tallies at one instant. run_s is time spent inside handlers, so unlike wall-clock it
    does not count the time the bot sat stopped. Two marks bracket a level."""

    run_s: float = 0.0
    holds: int = 0
    boxes: int = 0
    unlock_miss: int = 0


@dataclass
class _ResumeWatch:
    """One auto-resume episode, created when the bot stops itself on a window or focus error."""

    reason: str
    since: float  # when the bot stopped itself
    activity_at: float  # the last key press or cursor movement seen
    sample_at: float  # next cursor sample
    check_at: float  # next readiness check
    cursor: Point | None = None
    attempts: int = 0
    logged: tuple[bool, bool] | None = None  # (ready, quiet) of the last logged check
    logged_at: float = 0.0


def _top_close_position(positions: dict[Point, int]) -> str:
    """The most-tapped X position as 'x,yxCOUNT' text (e.g. 308,250x3698), or 'none': the unattended
    logs' only clue to which popup keeps coming back."""
    if not positions:
        return "none"
    (x, y), count = max(positions.items(), key=lambda item: item[1])
    return f"{x},{y}x{count}"


def _frame_thumbnail(frame: np.ndarray) -> np.ndarray:
    """64x36 grayscale subsample, enough to tell a frozen or dimmed view from a live one.
    ponytail: nearest-pixel sampling, not an area average; it only has to distinguish an identical
    frame (delta 0) from an animated one, so no cv2 call and any frame size works."""
    gray = frame.mean(axis=2) if frame.ndim == 3 else frame.astype(np.float64)
    rows = np.linspace(0, gray.shape[0] - 1, 36).astype(int)
    cols = np.linspace(0, gray.shape[1] - 1, 64).astype(int)
    return np.asarray(gray[rows][:, cols])


def _format_near_misses(seen: list[Any], clickable: Callable[[Point], bool] | None = None) -> str:
    """Text for the early probe: per template its best raw match, how much of it sits inside the HSV
    gate, the median colour it had (H,S,V: judge the gate in numbers, not images) and, when a zone check
    is given, whether that spot is a forbidden zone. `seen` holds explain_template_detailed tuples."""
    parts = []
    for name, confidence, center, ratio, median in seen:
        ratio_text = "n/a" if ratio is None else f"{ratio:.2f}"
        median_text = "" if median is None else f" med_hsv={median[0]},{median[1]},{median[2]}"
        zone = " IN-FORBIDDEN-ZONE" if clickable and not clickable(center) else ""
        parts.append(f"{name} conf={confidence:.3f} at {center} hsv={ratio_text}{median_text}{zone}")
    return "; ".join(parts) or "none"


def run_adb(argv: Sequence[str], timeout: float) -> tuple[int, str]:
    """Runs one adb command as a fixed argv list (never a shell) with a timeout. Never raises: a
    missing adb, a timeout or no device comes back as (127, reason)."""
    try:
        done = subprocess.run(list(argv), capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, str(exc)
    return done.returncode, done.stdout + done.stderr


class GameLauncher:
    """Revives a dead game over adb. The runner is injectable so tests never touch a phone."""

    def __init__(self, runner: AdbRunner = run_adb) -> None:
        self._run = runner
        self.package: str | None = None

    def detect_package(self) -> bool:
        """Picks the one installed package whose id contains GAME_RECOVERY_PACKAGE_HINT. Zero or
        several matches disable relaunch rather than guess."""
        code, output = self._run(
            [config.GAME_RECOVERY_ADB_PATH, "shell", "pm", "list", "packages"],
            config.GAME_RECOVERY_COMMAND_TIMEOUT,
        )
        if code != 0:
            logger.error("Game relaunch unavailable: 'adb shell pm list packages' failed: %s", output.strip())
            return False
        hint = str(config.GAME_RECOVERY_PACKAGE_HINT).lower()
        found = sorted(
            {
                line.removeprefix("package:").strip()
                for line in output.splitlines()
                if line.startswith("package:") and hint in line.lower()
            }
        )
        if len(found) != 1:
            logger.error(
                "Game relaunch disabled: %d packages match '%s': %s",
                len(found),
                config.GAME_RECOVERY_PACKAGE_HINT,
                ", ".join(found) or "none",
            )
            return False
        self.package = found[0]
        logger.info("Game relaunch armed for package %s", self.package)
        return True

    def relaunch(self) -> bool:
        """Force-stops then launches the game. A frozen app needs the stop; a crashed one ignores it."""
        if self.package is None:
            return False
        adb, timeout = config.GAME_RECOVERY_ADB_PATH, config.GAME_RECOVERY_COMMAND_TIMEOUT
        steps = (
            [adb, "shell", "am", "force-stop", self.package],
            [adb, "shell", "monkey", "-p", self.package, "-c", "android.intent.category.LAUNCHER", "1"],
        )
        for argv in steps:
            code, output = self._run(argv, timeout)
            if code != 0:
                logger.error("Game relaunch step failed (%s): %s", " ".join(argv[1:]), output.strip())
                return False
        return True


class EatventureBot:
    def __init__(self) -> None:
        logger.info("Initializing Eatventure Bot")
        self._running = threading.Event()
        self._stop_requested = threading.Event()
        self._state_operation_lock = threading.RLock()

        self.window_capture = WindowCapture(config.WINDOW_TITLE, config.WINDOW_WIDTH, config.WINDOW_HEIGHT)
        self.image_matcher = ImageMatcher(config.MATCH_THRESHOLD)
        self.mouse_controller = MouseController(
            self.window_capture.get_hwnd,
            click_delay=config.CLICK_DELAY,
            move_delay=config.MOUSE_MOVE_DELAY,
            stop_event=self._stop_requested,
        )
        self.state_machine = StateMachine(
            State.FIND_RED_ICONS,
            {
                State.FIND_RED_ICONS: self.handle_find_red_icons,
                State.CLICK_RED_ICON: self.handle_click_red_icon,
                State.CHECK_UNLOCK: self.handle_check_unlock,
                State.SEARCH_UPGRADE_STATION: self.handle_search_upgrade_station,
                State.HOLD_UPGRADE_STATION: self.handle_hold_upgrade_station,
                State.OPEN_BOXES: self.handle_open_boxes,
                State.UPGRADE_STATS: self.handle_upgrade_stats,
                State.SCROLL: self.handle_scroll,
                State.CHECK_NEW_LEVEL: self.handle_check_new_level,
                State.TRANSITION_LEVEL: self.handle_transition_level,
                State.WAIT_FOR_UNLOCK: self.handle_wait_for_unlock,
            },
        )
        self.telegram = TelegramNotifier(
            config.TELEGRAM_BOT_TOKEN,
            config.TELEGRAM_CHAT_ID,
            config.TELEGRAM_ENABLED,
        )

        # Fast/Normal red-icon matching, toggled at runtime by the M hotkey (only while stopped).
        self.red_icon_fast_mode = bool(config.RED_ICON_FAST_MODE_ENABLED)
        # adb relaunch of a dead game; None = recovery off (config) and the dead-game check never runs.
        self._launcher: GameLauncher | None = GameLauncher() if config.GAME_RECOVERY_ENABLED else None
        # Clock for the recovery window and auto-resume (tests advance it); the rest uses time.monotonic.
        self._clock: Callable[[], float] = time.monotonic

        self.templates = self.load_templates()
        self.ready = self._validate_required_templates()
        self._initialize_runtime_state()
        self._config_fingerprint = self._compute_config_fingerprint()

        logger.info("Bot initialized successfully")

    @property
    def running(self) -> bool:
        return self._running.is_set()

    @running.setter
    def running(self, is_running: bool) -> None:
        if is_running:
            self._running.set()
            return
        self._running.clear()

    def _initialize_runtime_state(self) -> None:
        self.running = False
        self.red_icons: list[RedIcon] = []
        self.current_red_icon_index = 0
        self.wait_for_unlock_attempts = 0
        self.max_wait_for_unlock_attempts = max(1, int(config.UNLOCK_SEARCH_ATTEMPTS))
        self.work_done = False
        self.cycle_counter = 0
        self.upgrade_station_counter = 0
        self.successful_red_icon_positions: deque[int] = deque(maxlen=24)
        self.upgrade_found_in_cycle = False
        self.consecutive_failed_cycles = 0
        self.total_levels_completed = 0
        self.current_level_start_time: float | None = None
        self.upgrade_station_pos: tuple[int, int] | None = None
        self.overlay: ForbiddenAreaOverlay | None = None
        self._oscillation_cycle_index = 1
        self._oscillation_leg_direction = 1
        self._oscillation_leg_progress = 0
        self._new_level_red_icon_verified = False
        self._state_entered_at: float | None = time.monotonic()
        self.forbidden_zones = self._configured_forbidden_zones()

        # Dead-loop guard + stall alert + metrics counters (see handle_open_boxes,
        # _maybe_alert_stall, _log_metrics). Tallies (holds_completed, boxes_opened_total,
        # box_guard_trips, stall_alerts) are never reset by _reset_search_cycle, only by stop()
        # below, mirroring total_levels_completed's treatment.
        self.box_only_passes = 0
        self.idle_scrolls = 0
        self.holds_completed = 0
        self.boxes_opened_total = 0
        self.box_guard_trips = 0
        self.stall_alerts = 0
        # Where the last few boxes were clicked, logged when the dead-loop guard trips so a
        # UI-fixed stuck target (same coordinates every pass) is visible in bot.log.
        self._recent_box_clicks: deque[tuple[int, int, float]] = deque(maxlen=8)
        # Stall alert: when the idle streak began, and whether the next OPEN_BOXES scan should
        # log what box detection actually saw.
        self._idle_started_at = 0.0
        self._stall_probe_pending = False

        # How many consecutive steps the flow has been in the current state. Owned by step(); read by
        # the attempt-loop states (SEARCH_UPGRADE_STATION, TRANSITION_LEVEL).
        self.state_attempt = 1
        # No-work loop FIND -> UPGRADE_STATS -> OPEN -> SCROLL -> OPEN -> FIND. Both flags live for ONE
        # step: FIND sets stats_from_find (so a stats miss goes to OPEN, not SCROLL as after a hold), a
        # landed scroll sets scan_boxes_after_scroll (so that OPEN pass hands back to FIND instead of
        # counting another idle pass and scrolling forever). Each is consumed by its handler.
        self.stats_from_find = False
        self.scan_boxes_after_scroll = False
        # Tallies for the metrics line; like total_levels_completed they are never reset by a search reset.
        self.stats_checks = 0
        self.stats_hits = 0
        self.post_scroll_boxes = 0  # crates only the post-scroll scan opened
        self.box_zone_skips = 0  # boxes that passed detection but sit in a forbidden zone
        self.box_click_fails = 0  # boxes whose click failed
        self.holds_capped = 0  # holds that ran to CLICK_HOLD_MAX_DURATION (cash was not the limit)
        self.hold_seconds_total = 0.0
        self.nl_unlock_miss = 0  # new-level attempts that exhausted WAIT_FOR_UNLOCK
        self.level_start_mark = LevelMark()
        self.nl_first_mark: LevelMark | None = None  # tallies at the level's first New Level sighting
        self.relaunches = 0
        self.relaunch_failures = 0
        self.close_clicks = 0
        self.close_suppressed = 0
        self.recovery_taps = 0
        self.close_positions: dict[Point, int] = {}  # taps per X position
        # Red-X rule (see _dismiss_popup): where the last X was tapped and how many times in a row, when
        # the rule may act again after standing down, when the post-level lock ends, and what the
        # pre-check cost in capture + match seconds.
        self._close_last_pos: Point | None = None
        self._close_streak = 0
        self._close_suppressed_until = 0.0
        self._close_level_lock_until = 0.0
        self._close_check_seconds = 0.0
        # The state whose handler ran last step (self.state is already the NEXT one by the time the popup
        # pre-check runs) and when this run started, for the self-stop line.
        self._last_handled_state: State | None = None
        self._started_at = 0.0
        # Stall probes and dead-game detection: thumbnails of the first scan of an idle streak, the latest
        # scan and the one at the previous metrics line; how far the last drag moved the picture.
        self._early_probe_pending = False
        self._scan_delta: float | None = None
        self._package_probed = False
        self._streak_thumb: np.ndarray | None = None
        self._streak_anchor_pending = False
        self._latest_thumb: np.ndarray | None = None
        self._metrics_thumb: np.ndarray | None = None
        self._last_probe_thumb: np.ndarray | None = None
        self._relaunch_progress: tuple[int, int] | None = None
        # Armed (not None) only while the bot is stopped after an environment self-stop and nobody has
        # restarted it since; see poll_resume.
        self._resume: _ResumeWatch | None = None
        # ponytail: cumulative since process start, no rolling window; subtract consecutive
        # metrics lines for a per-period rate. Upgrade path: a windowed deque if that gets tedious.
        self._state_seconds: dict[State, float] = dict.fromkeys(State, 0.0)
        self._last_metrics_at = 0.0

    @staticmethod
    def _configured_forbidden_zones() -> list[tuple[int, int, int, int]]:
        return list(config.NUMBERED_FORBIDDEN_ZONE_BOUNDS)

    @staticmethod
    def _compute_config_fingerprint() -> str:
        """Short stable id of the tuning in effect, so a metrics line says which config produced
        it. config.py is a flat module (no dataclass), so this hashes every public UPPERCASE
        constant except paths (machine-specific) and Telegram fields (secret/env-derived)."""
        excluded = {"ASSETS_DIR", "LOGS_DIR", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "TELEGRAM_ENABLED"}
        tuning = {
            name: value
            for name, value in vars(config).items()
            if name.isupper() and name not in excluded
        }
        fingerprint = repr(sorted(tuning.items(), key=lambda item: item[0]))
        return hashlib.sha1(fingerprint.encode(), usedforsecurity=False).hexdigest()[:8]

    def set_event_forbidden_zone(self, bounds: ForbiddenZoneBounds) -> None:
        self.forbidden_zones = [bounds, *self._configured_forbidden_zones()]
        self.mouse_controller.set_event_forbidden_zone(bounds)

    def load_templates(self) -> dict[str, TemplatePair]:
        templates: dict[str, TemplatePair] = {}
        templates_path = Path(config.ASSETS_DIR)
        if not templates_path.exists():
            logger.error("Assets directory not found: %s", templates_path)
            return templates

        for template_file in sorted(templates_path.glob("*.png")):
            try:
                template_name = template_file.stem
                template_img = self.image_matcher.load_template(template_file)
                templates[template_name] = template_img
                logger.info("Loaded template: %s", template_name)
            except Exception as exc:
                logger.error("Failed to load template %s: %s", template_file, exc)

        return templates

    def _active_red_icon_template_names(self) -> tuple[str, ...]:
        names = config.RED_ICON_FAST_TEMPLATE_NAMES if self.red_icon_fast_mode else config.RED_ICON_NORMAL_TEMPLATE_NAMES
        return tuple(name for name in names if name in self.templates)

    def _validate_required_templates(self) -> bool:
        """The start gate: refuse to run with assets missing rather than silently degrade into a bot
        that can never see what it is waiting for. A missing redX only switches the popup rule off."""
        missing = [name for name in ("newLevel", "unlock", "upgradeStation") if name not in self.templates]
        if not self._active_red_icon_template_names():
            missing.append("RedIcon*")
        if missing:
            logger.error("Missing required templates: %s", ", ".join(missing))
            return False
        return True

    def _sleep(self, duration: Any) -> bool:
        try:
            delay = max(0.0, float(duration))
        except (TypeError, ValueError):
            delay = 0.0
        return not self._stop_requested.wait(delay)

    def _template(self, template_name: str) -> TemplatePair | None:
        return self.templates.get(template_name)

    def _click_idle(self) -> bool:
        return self.mouse_controller.click(config.IDLE_CLICK_POS[0], config.IDLE_CLICK_POS[1], relative=True)

    def _scrcpy_miss_recovery_sleep(self, duration: Any) -> bool:
        if not config.SCRCPY_MISS_RECOVERY_ENABLED:
            return False
        try:
            delay = max(0.0, float(duration))
        except (TypeError, ValueError):
            delay = 0.0
        if delay <= 0:
            return True
        return self._sleep(delay)

    def _find_new_level_button(self, screenshot: Any) -> tuple[bool, float, int, int]:
        template_pair = self._template("newLevel")
        if template_pair is None:
            return False, 0.0, 0, 0
        template, mask = template_pair
        return self.image_matcher.find_template(
            screenshot,
            template,
            mask=mask,
            threshold=config.NEW_LEVEL_THRESHOLD,
            template_name="newLevel",
        )

    def find_unlock_button(self, screenshot: Any) -> tuple[bool, float, int, int]:
        template_pair = self._template("unlock")
        if template_pair is None:
            return False, 0.0, 0, 0
        template, mask = template_pair
        return self.image_matcher.find_template(
            screenshot,
            template,
            mask=mask,
            threshold=config.UNLOCK_THRESHOLD,
            template_name="unlock",
        )

    def _gather(
        self,
        frame: Any,
        template_names: tuple[str, ...],
        threshold: float,
        min_distance: int,
        hsv_ranges: Any,
        hsv_ratio: float,
        min_matches: int,
        iou_threshold: float,
    ) -> list[BoxCandidate]:
        """Candidates of several templates over one frame. With min_matches > 1 only spots where that
        many DISTINCT templates agree survive; otherwise overlapping matches are merged, best first."""
        templates = [(name, *self.templates[name]) for name in template_names if name in self.templates]
        raw = self.image_matcher.find_candidates_across_templates(
            frame,
            templates,
            threshold=threshold,
            min_distance=min_distance,
            hsv_ranges=hsv_ranges,
            hsv_match_threshold=hsv_ratio,
        )
        if min_matches > 1:
            return self.image_matcher.filter_by_template_consensus(raw, min_matches, iou_threshold)
        return self.image_matcher.suppress_overlaps(raw, iou_threshold)

    def find_red_icons(self, frame: Any) -> list[RedIcon]:
        names = self._active_red_icon_template_names()
        if not names:
            return []
        # Fast mode scans a single template, so consensus is trivially satisfied; normal mode requires
        # several template variants to agree on the same spot.
        min_matches = 1 if self.red_icon_fast_mode else min(max(1, int(config.RED_ICON_MIN_MATCHES)), len(names))
        found = self._gather(
            frame,
            names,
            config.RED_ICON_THRESHOLD,
            int(config.RED_ICON_FAST_MIN_DISTANCE),
            config.RED_ICON_HSV_RANGES,
            config.RED_ICON_HSV_MIN_MATCH_RATIO,
            min_matches,
            config.RED_ICON_NMS_IOU_THRESHOLD,
        )
        return [(confidence, x, y) for confidence, x, y, _, _, _ in found]

    @staticmethod
    def split_red_icons(icons: Iterable[RedIcon]) -> tuple[list[RedIcon], bool, bool]:
        """Partitions a red-icon scan into (actionable icons, new-level footer icon seen, stats icon
        seen). Footer icons live in dedicated zones and are signals, not click targets. A footer badge
        must clear its own, stricter confidence floor; one below it is dropped outright, never
        reclassified as an actionable icon."""
        actionable: list[RedIcon] = []
        new_level_seen = False
        stats_seen = False
        for confidence, x, y in icons:
            if (
                config.NEW_LEVEL_RED_ICON_X_MIN <= x <= config.NEW_LEVEL_RED_ICON_X_MAX
                and config.NEW_LEVEL_RED_ICON_Y_MIN <= y <= config.NEW_LEVEL_RED_ICON_Y_MAX
            ):
                new_level_seen = new_level_seen or confidence >= config.NEW_LEVEL_RED_ICON_THRESHOLD
            elif (
                config.UPGRADE_RED_ICON_X_MIN <= x <= config.UPGRADE_RED_ICON_X_MAX
                and config.UPGRADE_RED_ICON_Y_MIN <= y <= config.UPGRADE_RED_ICON_Y_MAX
            ):
                stats_seen = stats_seen or confidence >= config.STATS_RED_ICON_THRESHOLD
            elif y < config.MAX_SEARCH_Y:
                actionable.append((confidence, x, y))
        return actionable, new_level_seen, stats_seen

    def find_boxes(self, frame: Any) -> list[BoxCandidate]:
        names = tuple(name for name in config.BOX_TEMPLATE_NAMES if name in self.templates)
        if not names:
            return []
        return self._gather(
            frame,
            names,
            config.BOX_THRESHOLD,
            int(config.BOX_MIN_DISTANCE),
            config.BOX_HSV_RANGES,
            config.BOX_HSV_MIN_MATCH_RATIO,
            min(max(1, int(config.BOX_MIN_MATCHES)), len(names)),
            config.BOX_NMS_IOU_THRESHOLD,
        )

    def find_upgrade_station_candidates(self, frame: Any, threshold: float) -> list[BoxCandidate]:
        """Every station match so a caller can skip a forbidden-zone best match in favour of the next
        one. Only one template exists for this target, so there is no cross-template consensus."""
        if "upgradeStation" not in self.templates:
            return []
        return self._gather(
            frame,
            ("upgradeStation",),
            threshold,
            int(config.UPGRADE_STATION_CANDIDATE_MIN_DISTANCE),
            config.UPGRADE_STATION_HSV_RANGES,
            config.UPGRADE_STATION_HSV_MIN_MATCH_RATIO,
            1,
            config.UPGRADE_STATION_CANDIDATE_NMS_IOU_THRESHOLD,
        )

    def find_upgrade_station(self, frame: Any, threshold: float) -> tuple[bool, float, int, int]:
        """The single best station match, HSV-gated."""
        template_pair = self._template("upgradeStation")
        if template_pair is None:
            return False, 0.0, 0, 0
        template, mask = template_pair
        return self.image_matcher.find_template(
            frame,
            template,
            mask=mask,
            threshold=threshold,
            template_name="upgradeStation",
            hsv_ranges=config.UPGRADE_STATION_HSV_RANGES,
            hsv_match_threshold=config.UPGRADE_STATION_HSV_MIN_MATCH_RATIO,
        )

    def find_close_buttons(self, frame: Any) -> list[BoxCandidate]:
        """The red X of a popup, found the way boxes are (masked template match plus the per-asset HSV
        gate) behind a cheap prefilter: only a frame holding a solid red block the size of the X, and
        only the area around it, is handed to the full match. A missing asset turns the rule off."""
        names = tuple(name for name in config.CLOSE_BUTTON_TEMPLATE_NAMES if name in self.templates)
        if not names:
            return []
        area = self.image_matcher.red_block_area(
            frame,
            config.CLOSE_BUTTON_BLOCK_HSV_RANGES,
            config.CLOSE_BUTTON_BLOCK_WINDOW,
            config.CLOSE_BUTTON_BLOCK_MIN_FRACTION,
        )
        if area is None:
            return []
        left, top, right, bottom = area
        found = self._gather(
            frame[top:bottom, left:right],
            names,
            config.CLOSE_BUTTON_THRESHOLD,
            int(config.CLOSE_BUTTON_MIN_DISTANCE),
            config.CLOSE_BUTTON_HSV_RANGES,
            config.CLOSE_BUTTON_HSV_MIN_MATCH_RATIO,
            1,
            config.CLOSE_BUTTON_NMS_IOU_THRESHOLD,
        )
        return [(confidence, x + left, y + top, w, h, name) for confidence, x, y, w, h, name in found]

    def _explain_templates(self, frame: Any, names: Iterable[str], hsv_ranges: Any) -> list[Any]:
        explained = (
            self.image_matcher.explain_template_detailed(
                frame, *self.templates[name], template_name=name, hsv_ranges=hsv_ranges
            )
            for name in names
            if name in self.templates
        )
        return [item for item in explained if item is not None]

    def box_near_misses(self, frame: Any) -> list[Any]:
        """Best raw match per box template with the threshold and HSV gate NOT applied: what the
        detector saw when find_boxes reported nothing. Diagnostics only (the stall probes)."""
        return self._explain_templates(frame, config.BOX_TEMPLATE_NAMES, config.BOX_HSV_RANGES)

    def red_icon_near_misses(self, frame: Any) -> list[Any]:
        """box_near_misses for the red-icon templates the current mode really matches. Set against the
        box line it tells a crate-only miss from a miss of everything on screen."""
        return self._explain_templates(frame, self._active_red_icon_template_names(), config.RED_ICON_HSV_RANGES)

    def unlock_near_miss(self, frame: Any) -> Any:
        """Best raw `unlock` match with the threshold NOT applied: a greyed-out button reads low, a
        near-miss reads close to the threshold. Diagnostics only (the unlock-miss log line)."""
        template_pair = self._template("unlock")
        if template_pair is None:
            return None
        template, mask = template_pair
        return self.image_matcher.explain_template(frame, template, mask=mask, template_name="unlock")

    def _is_clickable(self, point: Point) -> bool:
        return not self.mouse_controller.is_in_forbidden_zone(point[0], point[1], relative=True)

    def _remember_successful_red_icon_position(self, y_value: Any) -> None:
        y_value = int(y_value)
        for existing_y in self.successful_red_icon_positions:
            if abs(existing_y - y_value) < 12:
                return
        self.successful_red_icon_positions.append(y_value)

    def _reset_search_cycle(self) -> None:
        self.cycle_counter = 0
        self.wait_for_unlock_attempts = 0
        self._oscillation_cycle_index = 1
        self._oscillation_leg_direction = 1
        self._oscillation_leg_progress = 0
        self._new_level_red_icon_verified = False
        self.box_only_passes = 0
        self.stats_from_find = False
        self.scan_boxes_after_scroll = False

    def _advance_oscillation_progress(self) -> None:
        target_steps = max(1, int(self._oscillation_cycle_index) * int(config.SCROLL_INCREMENT_STEP))
        self._oscillation_leg_progress += 1
        if self._oscillation_leg_progress < target_steps:
            return
        self._oscillation_leg_progress = 0
        if self._oscillation_leg_direction > 0:
            self._oscillation_leg_direction = -1
            return
        self._oscillation_leg_direction = 1
        self._oscillation_cycle_index += 1
        if self._oscillation_cycle_index > int(config.MAX_SCROLL_CYCLES):
            self._oscillation_cycle_index = 1

    def _perform_oscillating_scroll_step(self) -> bool:
        distance = round(float(config.SCROLL_PIXEL_STEP) * float(config.SCROLL_DISTANCE_RATIO))
        start_x, start_y = config.SCROLL_START_POS
        direction = 1 if self._oscillation_leg_direction > 0 else -1
        target_y = start_y - distance if direction > 0 else start_y + distance
        logger.info(
            "Oscillating scroll step: cycle=%s direction=%s progress=%s",
            self._oscillation_cycle_index,
            "down" if direction > 0 else "up",
            self._oscillation_leg_progress + 1,
        )
        moved = self.mouse_controller.drag(
            start_x,
            start_y,
            start_x,
            target_y,
            duration=config.SCROLL_DURATION,
            relative=True,
        )
        if not moved:
            return False
        self._advance_oscillation_progress()
        if not self._sleep(config.POST_SCROLL_SETTLE):
            return False
        if not self._sleep(config.SCROLL_INTERVAL_PAUSE):
            return False
        return True

    def _perform_new_level_verification_scroll(self) -> bool:
        """Restored from v1 (73f5db0/eccd810): one down-drag used solely to force a fresh render
        before re-scanning for the new-level red icon. Reuses the shared SCROLL_START_POS origin;
        distance/duration/settle timing are dedicated to this step, independent of the oscillating
        SCROLL_* config used by _perform_oscillating_scroll_step. Not part of the oscillation
        cycle, so it does not touch _oscillation_cycle_index/_oscillation_leg_* progress."""
        start_x, start_y = config.SCROLL_START_POS
        target_y = start_y - config.NEW_LEVEL_VERIFICATION_SCROLL_DISTANCE
        moved = self.mouse_controller.drag(
            start_x,
            start_y,
            start_x,
            target_y,
            duration=config.NEW_LEVEL_VERIFICATION_SCROLL_DURATION,
            relative=True,
        )
        if not moved:
            return False
        if not self._sleep(config.NEW_LEVEL_VERIFICATION_SCROLL_SETTLE_DELAY):
            return False
        return self._sleep(config.NEW_LEVEL_VERIFICATION_SCROLL_INTERVAL_PAUSE)

    def _find_upgrade_station_position(self, threshold: float) -> Point | None:
        """The first station candidate outside a forbidden zone, not necessarily the best one, so a
        blocked best match does not hide a usable second one."""
        frame = self.window_capture.capture(max_y=config.UPGRADE_STATION_SEARCH_Y)
        for _, x, y, _, _, _ in self.find_upgrade_station_candidates(frame, threshold):
            if self._is_clickable((x, y)):
                return x, y
        return None

    def _red_icon_priority_key(self, icon: RedIcon) -> tuple[int, int, float]:
        confidence, _, y = icon
        for success_y in self.successful_red_icon_positions:
            if abs(y - success_y) < 50:
                return (0, y, -confidence)
        return (1, y, -confidence)

    def _relaxed_station_threshold(self) -> float:
        return max(0.0, config.UPGRADE_STATION_THRESHOLD - config.UPGRADE_STATION_THRESHOLD_RELAXATION)

    def _verify_upgrade_station_round(self) -> tuple[Point, float] | None:
        """One full verify-attempts retry loop: base threshold on the first attempt, relaxed afterwards.
        Returns the verified position and the relaxed threshold the hold will monitor with."""
        base = config.UPGRADE_STATION_THRESHOLD
        relaxed = self._relaxed_station_threshold()
        attempts = max(1, int(config.UPGRADE_STATION_VERIFY_SEARCH_ATTEMPTS))
        for attempt in range(attempts):
            threshold = base if attempt == 0 else relaxed
            frame = self.window_capture.capture(max_y=config.UPGRADE_STATION_SEARCH_Y)
            found, _, x, y = self.find_upgrade_station(frame, threshold)
            if found and self._is_clickable((x, y)):
                return (x, y), relaxed
            # No sleep before giving up on the last attempt.
            if attempt < attempts - 1 and not self._sleep(config.UPGRADE_STATION_VERIFY_SEARCH_INTERVAL):
                return None
        return None

    def _verify_upgrade_station(self) -> tuple[Point, float] | None:
        """Two-round pre-hold verification: a settle delay, then round one checks the current screen with
        no click at all; only if the station is still there does a priming click fire on the
        freshly-verified position (not the stale stored one), followed by another settle delay and a
        second round that must also confirm it before committing to a hold."""
        if not self._sleep(config.UPGRADE_STATION_VERIFY_SETTLE_DELAY):
            return None
        first = self._verify_upgrade_station_round()
        if first is None:
            logger.info("Upgrade station was not visible during verification")
            return None
        target, _ = first
        if not self.mouse_controller.precise_click(target[0], target[1], relative=True):
            logger.info("Upgrade station verification click failed at (%s, %s)", *target)
            return None
        if not self._sleep(config.UPGRADE_STATION_VERIFY_SETTLE_DELAY):
            return None
        second = self._verify_upgrade_station_round()
        if second is None:
            logger.info("Upgrade station was not visible during verification")
            return None
        return second

    def _station_seen_near(self, threshold: float, position: Point) -> bool:
        """One capture and match at the relaxed threshold, accepted only near `position`, the spot being
        held. At the relaxed threshold, once the real station's popup turns to its MAX state late in a
        hold, the template can false-positive on an unrelated button elsewhere on screen at a
        confidence at or above the base threshold, so threshold tuning alone cannot exclude it. A match
        far from the held spot is rejected wherever on screen it appears."""
        frame = self.window_capture.capture(max_y=config.UPGRADE_STATION_SEARCH_Y)
        found, _, x, y = self.find_upgrade_station(frame, threshold)
        if not found:
            return False
        tolerance = config.UPGRADE_STATION_DISAPPEAR_POSITION_TOLERANCE_PX
        return abs(x - position[0]) <= tolerance and abs(y - position[1]) <= tolerance

    def _station_disappeared(self, threshold: float, position: Point) -> bool:
        """One poll tick's verdict. A first miss is only believed after one delayed scrcpy-recovery
        re-check, so a single dropped frame does not end the hold. Recovery disabled or its sleep
        interrupted means gone. Debouncing across ticks is _make_disappearance_check's job."""
        if self._station_seen_near(threshold, position):
            return False
        if not self._scrcpy_miss_recovery_sleep(config.SCRCPY_UPGRADE_MISS_RECOVERY_DELAY):
            return True
        return not self._station_seen_near(threshold, position)

    def _make_disappearance_check(self, threshold: float, position: Point, required_misses: int) -> Callable[[], bool]:
        """Requires `required_misses` CONSECUTIVE misses before treating the station as gone, which
        debounces a single flaky miss so a real hold is not cut short by one bad frame."""
        misses = 0

        def check() -> bool:
            nonlocal misses
            misses = misses + 1 if self._station_disappeared(threshold, position) else 0
            return misses >= max(1, required_misses)

        return check

    def _record_hold(self, seconds: float) -> None:
        self.hold_seconds_total += seconds
        # Within one poll gap of the cap = the clock ran out, not the popup vanishing.
        if seconds >= config.CLICK_HOLD_MAX_DURATION - 0.1:
            self.holds_capped += 1

    def _next_state_after_box_cycle(self, opened: int, after_scroll: bool) -> State:
        if opened > 0:
            self.work_done = True
            self.cycle_counter = 0
            self.idle_scrolls = 0
            self.boxes_opened_total += opened
            # Deliberate v2 deviation from the old v1 flow (v1 never scrolled while boxes kept opening): live logs
            # showed a stuck "box" re-clicked for hours, work_done re-arming every pass, so SCROLL (and
            # with it every off-screen upgrade) was starved and the same-state watchdog never fired
            # because the state changes each tick. Zero-box passes do not reset the count, so an
            # alternating stuck target can't dodge it.
            # ponytail: interleave only. A UI-fixed stuck target still burns (K-1)/K of passes;
            # upgrade path: ignore a position clicked K times in a row (positions are logged on trip).
            self.box_only_passes += 1
            if after_scroll:
                self.post_scroll_boxes += opened
            # The post-scroll pass never trips the guard: it must never answer SCROLL (see below).
            if self.box_only_passes >= max(2, int(config.MAX_BOX_ONLY_PASSES)) and not after_scroll:
                self.box_only_passes = 0
                self.box_guard_trips += 1
                logger.warning(
                    "Box loop guard: %s box passes without a scroll or upgrade; forcing a scroll. "
                    "Last clicked positions: %s",
                    config.MAX_BOX_ONLY_PASSES,
                    [(x, y, round(confidence, 3)) for x, y, confidence in self._recent_box_clicks],
                )
                return State.SCROLL

        if after_scroll:
            # The scan right after a landed scroll is not an idle pass. Run through the ladder below it
            # would count one, answer SCROLL again, and FIND_RED_ICONS would never run (scroll forever);
            # so it always hands back to the red-icon scan, leaving work_done and the failed-search and
            # upgrade-found triggers for the next ordinary OPEN_BOXES pass.
            self.cycle_counter = 0
            return State.FIND_RED_ICONS

        if self.consecutive_failed_cycles >= config.FAILED_UPGRADE_SEARCHES_BEFORE_SCROLL:
            self.consecutive_failed_cycles = 0
            self.cycle_counter = 0
            logger.info("Repeated search failures reached threshold, forcing scroll")
            return State.SCROLL

        if self.upgrade_found_in_cycle:
            self.upgrade_found_in_cycle = False
            self.cycle_counter = 0
            logger.info("Upgrade found in cycle, staying in current area")
            return State.FIND_RED_ICONS

        if self.work_done:
            self.cycle_counter = 0
            logger.info("Work completed in current area, rescanning before scrolling")
            return State.FIND_RED_ICONS

        max_idle_pass_attempts = max(1, int(config.MAX_IDLE_PASS_ATTEMPTS))
        self.cycle_counter += 1
        logger.info(
            "No work detected in current area (idle pass %s/%s)",
            self.cycle_counter,
            max_idle_pass_attempts,
        )
        if self.cycle_counter >= max_idle_pass_attempts:
            self.cycle_counter = 0
            return State.SCROLL

        return State.FIND_RED_ICONS

    def start(self, *, report: bool = True) -> bool:
        """report=False is for the auto-resume retries, which must not alert on every failed try."""
        if not self._state_operation_lock.acquire(blocking=False):
            logger.warning("Cannot start bot while a state operation is active")
            return False
        try:
            if self.running:
                return True
            self.ready = self._validate_required_templates()
            if not self.ready:
                logger.error("Cannot start bot because required templates are missing")
                return False
            try:
                self.window_capture.ensure_window(resize=True)
            except WindowCaptureError as exc:
                logger.error("Cannot start bot: %s", exc)
                if report:
                    self._report_self_stop(f"cannot start: {exc}")
                self.running = False
                return False
            if not self.mouse_controller.is_target_foreground():
                logger.error("Cannot start bot because '%s' is not the foreground window", config.WINDOW_TITLE)
                if report:
                    self._report_self_stop("cannot start: target window is not foreground")
                self.running = False
                return False
            if self._launcher is not None and not self._package_probed:
                self._package_probed = True  # once per process: adb is only touched at start
                self._launcher.detect_package()
            self._stop_requested.clear()
            self.running = True
            self._resume = None  # running again, by a person or by poll_resume
            self.state_attempt = 1
            # The stall clock is armed by the first handled step, not by start(): popup taps right after
            # a start (they skip the watchdog) must not eat into the first handler's budget.
            self._state_entered_at = None
            self._started_at = self._last_metrics_at = time.monotonic()
            if self.current_level_start_time is None:
                self.current_level_start_time = time.monotonic()
            if config.ShowForbiddenArea and self.overlay is None:
                self.overlay = ForbiddenAreaOverlay(self.window_capture.get_hwnd(), self.forbidden_zones)
                self.overlay.start()
            self.telegram.notify_bot_started()
            return True
        finally:
            self._state_operation_lock.release()

    def request_stop(self) -> None:
        self._stop_requested.set()

    def stop(self, *, manual: bool = False) -> None:
        self.request_stop()
        with self._state_operation_lock:
            was_running = self.running
            self.running = False
            self.mouse_controller.release_left_button()
            self.state_machine.transition(State.FIND_RED_ICONS)
            self._reset_search_cycle()
            self.red_icons.clear()
            self.current_red_icon_index = 0
            self.upgrade_station_pos = None
            self.upgrade_found_in_cycle = False
            self.work_done = False
            self.consecutive_failed_cycles = 0
            self.idle_scrolls = 0
            self.state_attempt = 1
            if self.overlay is not None:
                self.overlay.stop()
                self.overlay = None
            if was_running and config.METRICS_LOG_INTERVAL > 0:
                self._log_metrics()
        # Only the manual Z-toggle says "Bot Stopped". An internal auto-stop (stop-requested race, lost
        # foreground, an unhandled handler exception, or close()'s own cleanup call) is reported by
        # _report_self_stop where it applies, never here.
        if was_running and manual:
            self.telegram.notify_bot_stopped()

    def close(self) -> None:
        self.stop()
        self.telegram.close()

    def toggle_red_icon_mode(self) -> str:
        self.red_icon_fast_mode = not self.red_icon_fast_mode
        return "Fast" if self.red_icon_fast_mode else "Normal"

    def cursor_position_in_window(self) -> Point | None:
        """Window-relative cursor readout for the 'X' debug hotkey."""
        try:
            screen_x, screen_y = self.mouse_controller.get_cursor_position()
            left, top, _, _ = self.window_capture.get_window_rect()
        except Exception:
            return None
        return screen_x - left, screen_y - top

    def step(self) -> bool:
        if not self._state_operation_lock.acquire(blocking=False):
            logger.warning("Ignoring reentrant bot step")
            return False
        try:
            if not self.running:
                return False
            if self._stop_requested.is_set():
                self.stop()
                return False
            self.window_capture.ensure_window(resize=True)
            if not self.mouse_controller.is_target_foreground():
                logger.error("Window '%s' lost foreground ownership; stopping bot", config.WINDOW_TITLE)
                self._report_self_stop("target lost foreground")
                self.stop()
                self._arm_resume("target lost foreground")
                return False

            if self._dismiss_popup():
                return True  # a popup was closed this step; the handler runs on the next one

            previous_state = self.state_machine.current_state
            handler_started_at = time.monotonic()
            current_state = self.state_machine.update()
            now = time.monotonic()
            self._state_seconds[previous_state] += now - handler_started_at
            self._last_handled_state = previous_state
            if previous_state in X_LOCKED_STATES:
                # Hard-lock layer 2: any New Level step (attempt, miss or completion) keeps the X rule off
                # afterwards, so a dialog still open when control returns is left to that flow.
                self._close_level_lock_until = max(
                    self._close_level_lock_until, now + config.CLOSE_BUTTON_NEW_LEVEL_LOCK_SECONDS
                )
            if not self.running:
                return False
            self.state_attempt = self.state_attempt + 1 if current_state == previous_state else 1
            if self._state_entered_at is None or current_state != previous_state:
                self._state_entered_at = now
            elif now - self._state_entered_at >= config.STATE_STALL_TIMEOUT_SECONDS:
                logger.warning("State %s stalled; resetting search flow", current_state.name)
                self._reset_search_cycle()
                self.state_machine.transition(State.FIND_RED_ICONS)
                self.state_attempt = 1
                self._state_entered_at = now
            self._maybe_log_metrics()
            return True
        except (WindowNotAvailableError, WindowCaptureError) as exc:
            logger.error("Stopping bot: %s", exc)
            self._report_self_stop(str(exc))
            self.stop()
            self._arm_resume(str(exc))
            return False
        except pywintypes.error as exc:
            logger.error("Stopping bot due to Windows input failure: %s", exc)
            self._report_self_stop(f"Windows input failure: {exc}")
            self.stop()
            return False
        except Exception:
            logger.exception("Stopping bot due to unexpected state-handler failure")
            self._report_self_stop("unexpected handler failure")
            self.stop()
            return False
        finally:
            self._state_operation_lock.release()

    # --- auto-resume after an environment self-stop -----------------------------------------

    def _arm_resume(self, reason: str) -> None:
        """Only the two environment self-stops (window gone, focus lost) call this. A Z press, a stop
        request and a handler bug leave the decision to a person or a code fix, so they never arm it:
        the stopped-but-primed state alone cannot tell those apart."""
        now = self._clock()
        self._resume = _ResumeWatch(reason, now, now, now, now + config.RESUME_CHECK_SECONDS)

    def poll_resume(self, last_key_at: float) -> None:
        """Called on every pass of the main loop while the bot is stopped; a no-op unless armed.
        last_key_at is the latest key press on this PC, on the same clock as self._clock.

        Shadow mode (RESUME_ENABLED False, the default): each check only logs whether it WOULD start the
        bot, so the share of downtime it could recover is measured first. Live mode: when the window is
        already in a state start() will not touch (WindowCapture.environment_ready: no resize, no focus
        change) and nobody has pressed a key or moved the mouse for RESUME_IDLE_SECONDS, it calls
        start(). A failed attempt backs off exponentially, and RESUME_MAX_ATTEMPTS failures in one stop
        make it give up and wait for a person. Never raises: the main loop must survive whatever
        happens in here."""
        watch = self._resume
        if watch is None or self.running:
            return
        now = self._clock()
        if now < watch.sample_at:
            return
        watch.sample_at = now + _RESUME_SAMPLE_SECONDS
        try:
            cursor = self.mouse_controller.get_cursor_position()
            # The first sample is only a baseline; a later change means a person moved the mouse.
            if watch.cursor is not None and cursor != watch.cursor:
                watch.activity_at = now
            watch.cursor = cursor
            if now >= watch.check_at:
                self._check_resume(watch, now, last_key_at)
        except Exception:
            logger.exception("Resume check failed")
            watch.check_at = now + config.RESUME_CHECK_SECONDS

    def _check_resume(self, watch: _ResumeWatch, now: float, last_key_at: float) -> None:
        idle = now - max(watch.activity_at, last_key_at)
        ready = self.window_capture.environment_ready()
        quiet = idle >= config.RESUME_IDLE_SECONDS
        watch.check_at = now + config.RESUME_CHECK_SECONDS
        # One line per change plus a heartbeat, not one per minute of a 20 h stop.
        if (ready, quiet) != watch.logged or now - watch.logged_at >= _RESUME_HEARTBEAT_SECONDS:
            watch.logged, watch.logged_at = (ready, quiet), now
            logger.info(
                "Resume check (%s): ready=%s idle_s=%.0f/%.0f down_min=%.0f -> %s | %s",
                "live" if config.RESUME_ENABLED else "shadow",
                ready,
                idle,
                config.RESUME_IDLE_SECONDS,
                (now - watch.since) / 60,
                ("resuming" if config.RESUME_ENABLED else "would resume") if ready and quiet else "waiting",
                self.window_capture.describe_environment(),
            )
        if not (config.RESUME_ENABLED and ready and quiet):
            return
        watch.attempts += 1
        if self.start(report=False):
            logger.info(
                "Auto-resumed after %.0f min (attempt %d): %s",
                (now - watch.since) / 60,
                watch.attempts,
                watch.reason,
            )
            return
        if watch.attempts >= config.RESUME_MAX_ATTEMPTS:
            logger.warning("Auto-resume gave up after %d attempts: %s", watch.attempts, watch.reason)
            self._resume = None
            return
        watch.check_at = now + min(_RESUME_MAX_BACKOFF_SECONDS, config.RESUME_CHECK_SECONDS * 2**watch.attempts)

    def _report_self_stop(self, reason: str) -> None:
        """Whenever the bot stops itself (not a Z press) it stays stopped until a person comes back, so
        log the facts that may explain why and alert once. Diagnostics only: never raises, never changes
        what the caller does next. ran_min is "-" for a start that failed, since there was no run."""
        try:
            ran = f"{(time.monotonic() - self._started_at) / 60:.0f}" if self.running else "-"
            logger.warning(
                "Self-stop: %s | ran_min=%s | %s", reason, ran, self.window_capture.describe_environment()
            )
            self.telegram.notify_bot_self_stopped(reason, 0.0 if ran == "-" else float(ran))
        except Exception:
            logger.exception("Self-stop report failed")

    # --- red-X popup rule and dead-game recovery ----------------------------------------------

    def _dismiss_popup(self) -> bool:
        """Red-X priority: runs before the state handler, so it outranks every handler and asset. True
        when it tapped an X (the step is then spent on that).

        Hard lock for the New Level dialog (its X looks exactly like this one), two layers, either of
        which blocks the tap:
        1. state: while CHECK_NEW_LEVEL / TRANSITION_LEVEL / WAIT_FOR_UNLOCK owns the screen, return
           before any capture;
        2. afterwards: for CLOSE_BUTTON_NEW_LEVEL_LOCK_SECONDS after any step in those states (attempt,
           miss or completion), leave the screen alone so a dialog still open is left to the flow.
        Deliberately NOT a lock on seeing the `unlock` button: that template also matches the blue
        "Collect x2" button of the Offline Earnings popup (0.935 against a 0.905 threshold), which would
        lock out the very popup this rule exists for.
        Stand-down guard: the same spot tapped CLOSE_BUTTON_MAX_CONSECUTIVE_CLICKS times in a row means
        the tap is not closing anything, so the rule pauses for CLOSE_BUTTON_SUPPRESS_SECONDS instead of
        starving the flow."""
        if not config.CLOSE_BUTTON_ENABLED or self.state_machine.current_state in X_LOCKED_STATES:
            return False
        now = time.monotonic()
        if now < self._close_level_lock_until or now < self._close_suppressed_until:
            return False
        frame = self.window_capture.capture()
        found = self.find_close_buttons(frame)
        self._close_check_seconds += time.monotonic() - now
        if not found:
            self._close_last_pos, self._close_streak = None, 0
            return False
        target = found[0]
        x, y = target[1], target[2]
        last = self._close_last_pos
        same_spot = last is not None and abs(last[0] - x) <= 3 and abs(last[1] - y) <= 3
        if same_spot and self._close_streak >= config.CLOSE_BUTTON_MAX_CONSECUTIVE_CLICKS:
            self.close_suppressed += 1
            self._close_last_pos, self._close_streak = None, 0
            self._close_suppressed_until = now + config.CLOSE_BUTTON_SUPPRESS_SECONDS
            logger.warning(
                "Red X at (%d, %d) still there after %d taps; ignoring X's for %.0f s",
                x,
                y,
                config.CLOSE_BUTTON_MAX_CONSECUTIVE_CLICKS,
                config.CLOSE_BUTTON_SUPPRESS_SECONDS,
            )
            return False
        self._close_streak = self._close_streak + 1 if same_spot else 1
        self._close_last_pos = (x, y)
        self._tap_close_button(target)
        return True

    def _tap_close_button(self, target: BoxCandidate, *, remaining: float | None = None, recovery: bool = False) -> bool:
        """Taps one detected X and waits out the modal settle (clamped to `remaining` seconds when the
        recovery window is closing). Shared by the main-flow rule and the recovery window."""
        confidence, x, y = target[0], target[1], target[2]
        # check_forbidden=False: the X is the intended target, wherever the popup puts it.
        clicked = self.mouse_controller.click(x, y, relative=True, check_forbidden=False)
        if clicked:
            self.close_clicks += 1
            self.recovery_taps += int(recovery)
        self.close_positions[(x, y)] = self.close_positions.get((x, y), 0) + 1
        after = self._last_handled_state
        logger.info(
            "Closed popup at (%d, %d) conf=%.3f state=%s%s%s%s",
            x,
            y,
            confidence,
            self.state_machine.current_state.name,
            " (recovery)" if recovery else "",
            "" if clicked else " (tap failed)",
            "" if after is None else f" after={after.name}",
        )
        settle = config.CLOSE_BUTTON_SETTLE_DELAY
        self._sleep(settle if remaining is None else max(0.0, min(settle, remaining)))
        return clicked

    def _recover_popups(self) -> None:
        """The recovery window after an adb relaunch: for the whole GAME_RECOVERY_RELAUNCH_SETTLE_SECONDS
        ONLY the red-X rule runs. No handler, no other asset (red icons, boxes, unlock, scroll, idle
        click), no New Level lock and no stand-down guard (nothing is in flight in a freshly restarted
        game, and the window is time-bounded). It always runs the full window, even after the X is gone,
        because popups can arrive late in a cold start. A capture error is retried until the deadline; a
        stop request ends the window early."""
        started = self._clock()
        deadline = started + config.GAME_RECOVERY_RELAUNCH_SETTLE_SECONDS
        tail_from = deadline - _RECOVERY_TAIL_SECONDS
        tail: np.ndarray | None = None
        last: np.ndarray | None = None
        taps = capture_errors = 0
        while self._clock() < deadline and not self._stop_requested.is_set():
            remaining = deadline - self._clock()
            try:
                frame = self.window_capture.capture()
                found = self.find_close_buttons(frame)
            except WindowCaptureError as exc:
                capture_errors += 1
                if capture_errors == 1:
                    logger.warning("Recovery: capture failed (%s); retrying until it ends", exc)
                self._sleep(min(config.GAME_RECOVERY_POLL_SECONDS, remaining))
                continue
            last = _frame_thumbnail(frame)
            if tail is None and self._clock() >= tail_from:
                tail = last
            if found:
                taps += 1
                self._tap_close_button(found[0], remaining=remaining, recovery=True)
            else:
                self._sleep(min(config.GAME_RECOVERY_POLL_SECONDS, remaining))
        elapsed = self._clock() - started
        if tail is None or last is None:  # stopped early or never captured: no verdict to give
            logger.info("Recovery window ended after %.0f s: %d X tapped", elapsed, taps)
            return
        delta = float(np.abs(last - tail).mean())
        changing = delta >= config.GAME_RECOVERY_STATIC_FRAME_DELTA
        (logger.info if changing else logger.warning)(
            "Recovery window ended after %.0f s: %d X tapped, screen %s "
            "(frame delta %.2f over the last %.0f s)%s",
            elapsed,
            taps,
            "changing" if changing else "still static",
            delta,
            _RECOVERY_TAIL_SECONDS,
            "" if changing else "; the next stall alert will relaunch again",
        )

    def _game_looks_dead(self, thumb: np.ndarray) -> bool:
        """Runs only on a stall probe (>= STALL_SCROLLS_BEFORE_ALERT idle scrolls). It runs on the scan
        right after a drag, when a live game has just moved and a frozen one has not: the picture has
        not changed since the streak began. Healthy idle streaks peak near 66 scrolls, so the scroll
        count alone is no evidence; the frame is."""
        before = self._streak_thumb
        if before is None or self._launcher is None:  # no launcher = recovery switched off
            return False
        limit = config.GAME_RECOVERY_STATIC_FRAME_DELTA
        delta = float(np.abs(thumb - before).mean())
        static = delta < limit
        # The decision's own inputs: the stall probe's "Frame delta vs last probe" compares a different
        # pair of frames, so on its own it cannot tell whether a relaunch was justified.
        logger.info(
            "Dead-game check: frame delta vs streak start=%.2f (static below %.2f), idle_scrolls=%d -> %s",
            delta,
            limit,
            self.idle_scrolls,
            "static" if static else "alive",
        )
        if static and self._launcher.package is None:
            logger.warning("Game appears dead (frame unchanged) but adb relaunch is not available")
            return False
        return static

    def _relaunch_game(self) -> State:
        """adb force-stop + launch, wait out the cold start, and restart the search from scratch. No cap
        on repeats: the next chance is another full stall alert, many minutes away."""
        launcher = self._launcher
        assert launcher is not None  # _game_looks_dead only says yes when a launcher is armed
        progress = (self.holds_completed, self.boxes_opened_total)
        again = ""
        if progress == self._relaunch_progress:
            again = " (still static after the previous relaunch; the scrcpy window may be frozen)"
        minutes = (time.monotonic() - self._idle_started_at) / 60
        logger.warning(
            "Game appears dead: frame unchanged for %.0f min%s; relaunching %s", minutes, again, launcher.package
        )
        self._relaunch_progress = progress
        if launcher.relaunch():
            self.relaunches += 1
            self.telegram.notify_game_relaunch(True, minutes)
            self._recover_popups()  # exclusive X-only window; the main flow resumes after it
        else:
            # Nothing restarted, so there is nothing to wait for: log (done by the launcher) and carry
            # on with the main flow as before.
            self.relaunch_failures += 1
            self.telegram.notify_game_relaunch(False, minutes)
        self.idle_scrolls = 0
        self._reset_search_cycle()
        self._streak_thumb = None
        self._last_probe_thumb = None
        # The restarted game starts the X rule from scratch: no stale stand-down or lock window.
        self._close_last_pos, self._close_streak = None, 0
        self._close_suppressed_until = self._close_level_lock_until = 0.0
        return State.FIND_RED_ICONS

    # --- metrics, stall alert and probes ------------------------------------------------------

    def _maybe_log_metrics(self) -> None:
        interval = config.METRICS_LOG_INTERVAL
        now = time.monotonic()
        if interval <= 0 or now - self._last_metrics_at < interval:
            return
        self._last_metrics_at = now
        self._log_metrics()

    def _log_metrics(self) -> None:
        """One parseable line: run_s is time spent inside handlers (not the event-loop wake), and each
        state's share of it - where the run actually went."""
        total = sum(self._state_seconds.values())
        shares = " ".join(
            f"{state.name}={100 * seconds / total:.1f}%"
            for state, seconds in self._state_seconds.items()
            if seconds > 0
        )
        logger.info(
            "metrics cfg=%s run_s=%.0f levels=%d holds=%d boxes=%d guard_trips=%d "
            "idle_scrolls=%d stall_alerts=%d hold_capped=%d hold_avg_s=%.1f nl_unlock_miss=%d "
            "relaunches=%d relaunch_failures=%d frame_delta_5m=%s close_clicks=%d "
            "close_suppressed=%d close_check_s=%.1f recovery_taps=%d close_top=%s "
            "box_zone_skips=%d box_click_fails=%d stats_checks=%d stats_hits=%d "
            "post_scroll_boxes=%d | %s",
            self._config_fingerprint,
            total,
            self.total_levels_completed,
            self.holds_completed,
            self.boxes_opened_total,
            self.box_guard_trips,
            self.idle_scrolls,
            self.stall_alerts,
            self.holds_capped,
            self.hold_seconds_total / max(1, self.holds_completed),
            self.nl_unlock_miss,
            self.relaunches,
            self.relaunch_failures,
            self._frame_delta_since_last_metrics(),
            self.close_clicks,
            self.close_suppressed,
            self._close_check_seconds,
            self.recovery_taps,
            _top_close_position(self.close_positions),
            self.box_zone_skips,
            self.box_click_fails,
            self.stats_checks,
            self.stats_hits,
            self.post_scroll_boxes,
            shares or "-",
        )

    def _frame_delta_since_last_metrics(self) -> str:
        """Mean-abs-diff between the latest scan and the one at the previous metrics line: the
        healthy-farm baseline that GAME_RECOVERY_STATIC_FRAME_DELTA is judged against (a dead game
        reads ~0)."""
        latest, before = self._latest_thumb, self._metrics_thumb
        self._metrics_thumb = latest
        if latest is None or before is None:
            return "n/a"
        return f"{np.abs(latest - before).mean():.1f}"

    def _maybe_alert_stall(self) -> None:
        """After every landed scroll: idle_scrolls says how long the search has produced nothing. Every
        STALL_SCROLLS_BEFORE_ALERT scrolls, log a WARNING and arm a one-shot probe of box detection on the
        next OPEN_BOXES frame, so a silent stall names its own cause. No extra capture, gesture or click,
        so no slowdown. Separately, at STALL_PROBE_SCROLLS (earlier, log-only) arm the early probe, which
        also reads the red icons: the alert's probe is boxes only and a hand stop can beat it.
        ponytail: a scroll re-anchor stays deferred until a probe shows it is the problem."""
        idle = self.idle_scrolls
        if idle == 1:
            self._idle_started_at = time.monotonic()
            self._streak_anchor_pending = True
        early = max(0, int(config.STALL_PROBE_SCROLLS))
        if early > 0 and idle == early:
            self._early_probe_pending = True
        every = max(0, int(config.STALL_SCROLLS_BEFORE_ALERT))
        if every <= 0 or idle % every != 0:
            return
        self.stall_alerts += 1
        self._stall_probe_pending = True
        logger.warning(
            "Stall: %d scrolls over %.0f min with no box opened, upgrade held, stats upgrade or "
            "level completed (levels=%d holds=%d boxes=%d); probing box detection on the next scan",
            idle,
            (time.monotonic() - self._idle_started_at) / 60,
            self.total_levels_completed,
            self.holds_completed,
            self.boxes_opened_total,
        )

    def _log_box_near_misses(self, frame: Any, detected: int) -> None:
        """One text line: how many boxes passed detection on this frame, and for each box template its
        best raw match against the two gates a box must clear (template score, HSV ratio) and whether
        that spot is a forbidden zone. Tells a template/HSV miss from a zone block."""
        parts = []
        for name, confidence, center, ratio, _ in self.box_near_misses(frame):
            ratio_text = "n/a" if ratio is None else f"{ratio:.2f}"
            zone = "" if self._is_clickable(center) else " IN-FORBIDDEN-ZONE"
            parts.append(f"{name} conf={confidence:.3f} at {center} hsv={ratio_text}{zone}")
        thumb = _frame_thumbnail(frame)
        previous, self._last_probe_thumb = self._last_probe_thumb, thumb
        # delta ~0 between alerts (minutes apart) = frozen stream or static overlay; the quadrant means
        # (TL TR BL BR) show a dimmed screen. Text only: no pixels leave the process.
        delta = "n/a" if previous is None else f"{np.abs(thumb - previous).mean():.2f}"
        quads = " ".join(f"{thumb[r : r + 18, c : c + 32].mean():.0f}" for r in (0, 18) for c in (0, 32))
        logger.warning(
            "Stall probe: %d box(es) passed detection on this scan. Frame delta vs last probe=%s, "
            "quadrant brightness=[%s]. Best raw match per template "
            "(a box needs conf>=%.3f and hsv>=%.2f, outside forbidden zones): %s",
            detected,
            delta,
            quads,
            config.BOX_THRESHOLD,
            config.BOX_HSV_MIN_MATCH_RATIO,
            "; ".join(parts) or "none",
        )

    def _log_early_probe(self, frame: Any, detected: int) -> None:
        """One INFO line at STALL_PROBE_SCROLLS idle scrolls: what box AND red-icon detection saw on this
        scan (best raw match per template, gates and zones not applied) and whether the last drag changed
        the picture. Box vs red-icon confidence tells a crate-only miss from a miss of everything; a flat
        picture change says the drag moved nothing. Log-only: no alert, never reaches the dead-game
        check, leaves the alert probe's thumbnail alone, and a failure here is logged, not raised (an
        unexpected handler error would stop the whole bot)."""
        if self.idle_scrolls <= 0:  # progress ended the streak before this scan ran
            return
        try:
            thumb = _frame_thumbnail(frame)
            start = self._streak_thumb
            streak = "n/a" if start is None else f"{np.abs(thumb - start).mean():.2f}"
            drag = "n/a" if self._scan_delta is None else f"{self._scan_delta:.2f}"
            quads = " ".join(f"{thumb[r : r + 18, c : c + 32].mean():.0f}" for r in (0, 18) for c in (0, 32))
            boxes = _format_near_misses(self.box_near_misses(frame), self._is_clickable)
            icons = _format_near_misses(self.red_icon_near_misses(frame))
            logger.info(
                "Early probe: %d idle scrolls (%.1f min), %d box(es) passed detection, "
                "box_zone_skips=%d box_click_fails=%d. Picture change across the last drag=%s, "
                "vs streak start=%s, quadrant brightness=[%s]. "
                "Boxes (need conf>=%.3f and hsv>=%.2f): %s. "
                "Red icons (need conf>=%.3f and hsv>=%.2f): %s",
                self.idle_scrolls,
                (time.monotonic() - self._idle_started_at) / 60,
                detected,
                self.box_zone_skips,
                self.box_click_fails,
                drag,
                streak,
                quads,
                config.BOX_THRESHOLD,
                config.BOX_HSV_MIN_MATCH_RATIO,
                boxes,
                config.RED_ICON_THRESHOLD,
                config.RED_ICON_HSV_MIN_MATCH_RATIO,
                icons,
            )
        except Exception:
            logger.exception("Early probe failed")

    # --- level bookkeeping --------------------------------------------------------------------

    def _level_mark(self) -> LevelMark:
        return LevelMark(
            sum(self._state_seconds.values()), self.holds_completed, self.boxes_opened_total, self.nl_unlock_miss
        )

    def _note_unlock_miss(self, frame: Any) -> None:
        self.nl_unlock_miss += 1
        # best_conf = the raw best `unlock` match, threshold not applied: low = the button is greyed out
        # (cash is the limit), near the threshold = an appearance problem. Diagnostics only.
        best = self.unlock_near_miss(frame)
        logger.info(
            "New level: unlock button not found (miss %d, levels=%d, best_conf=%s)",
            self.nl_unlock_miss,
            self.total_levels_completed,
            "-" if best is None else f"{best[1]:.3f}",
        )

    def _report_level_completion(self) -> None:
        now = time.monotonic()
        started = self.current_level_start_time
        elapsed = now - started if started is not None else 0.0
        self.current_level_start_time = now
        logger.info("Restaurant %s completed in %.1fs", self.total_levels_completed, elapsed)
        # Breakdown in RUNNING seconds (the line above is wall-clock and includes stopped time). "before"
        # = up to the first New Level sighting, "after" = from it to the completion; a level with no
        # recorded sighting counts wholly as "before". The running time of the handler that is
        # completing the level is not in _state_seconds yet (a few seconds at most).
        start, end = self.level_start_mark, self._level_mark()
        seen = self.nl_first_mark or end
        self.level_start_mark, self.nl_first_mark = end, None
        logger.info(
            "Level %d breakdown: run_s=%.0f holds=%d boxes=%d unlock_miss=%d | "
            "before_nl: run_s=%.0f holds=%d boxes=%d | after_nl: run_s=%.0f holds=%d boxes=%d",
            self.total_levels_completed,
            end.run_s - start.run_s,
            end.holds - start.holds,
            end.boxes - start.boxes,
            end.unlock_miss - start.unlock_miss,
            seen.run_s - start.run_s,
            seen.holds - start.holds,
            seen.boxes - start.boxes,
            end.run_s - seen.run_s,
            end.holds - seen.holds,
            end.boxes - seen.boxes,
        )
        self.telegram.notify_new_level(self.total_levels_completed, elapsed)

    # --- handlers -----------------------------------------------------------------------------

    def handle_find_red_icons(self) -> State:
        if not self._click_idle():
            return State.FIND_RED_ICONS

        self.work_done = False

        # The newLevel button is checked on a frame limited to MAX_SEARCH_Y, distinct from the full
        # EXTENDED_SEARCH_Y frame used for the red-icon scan below.
        frame = self.window_capture.capture(max_y=config.EXTENDED_SEARCH_Y)
        if self._find_new_level_button(frame[: config.MAX_SEARCH_Y, :])[0]:
            logger.info("New level button visible during red-icon scan")
            self.cycle_counter = 0
            return State.TRANSITION_LEVEL

        actionable, new_level_seen, _ = self.split_red_icons(self.find_red_icons(frame))
        # Retry only when neither an ordinary icon nor the footer new-level icon was seen. A lone stats
        # badge (classified out by split_red_icons) must not suppress it, but a new-level badge does:
        # that goes straight to CHECK_NEW_LEVEL.
        if (
            not actionable
            and not new_level_seen
            and self._scrcpy_miss_recovery_sleep(config.SCRCPY_RED_ICON_MISS_RECOVERY_DELAY)
        ):
            frame = self.window_capture.capture(max_y=config.EXTENDED_SEARCH_Y)
            if self._find_new_level_button(frame[: config.MAX_SEARCH_Y, :])[0]:
                logger.info("New level button visible during red-icon scan after SCRCPY recovery")
                self.cycle_counter = 0
                return State.TRANSITION_LEVEL
            actionable, new_level_seen, _ = self.split_red_icons(self.find_red_icons(frame))

        clickable = [
            icon
            for icon in actionable
            if self._is_clickable((icon[1] + config.RED_ICON_OFFSET_X, icon[2] + config.RED_ICON_OFFSET_Y))
        ]
        return self._state_from_red_icon_scan(new_level_seen, clickable)

    def _state_from_red_icon_scan(self, new_level_seen: bool, clickable: list[RedIcon]) -> State:
        if new_level_seen:
            logger.info("New level footer red icon detected")
            self._new_level_red_icon_verified = False
            return State.CHECK_NEW_LEVEL

        if not clickable:
            # No-work loop: the stats badge gets a look before the crate scan (see stats_from_find for
            # why the next step must know where it came from).
            logger.info("No valid red icons; checking the stats badge before the boxes")
            self.stats_from_find = True
            return State.UPGRADE_STATS

        self.red_icons = sorted(clickable, key=self._red_icon_priority_key)
        self.current_red_icon_index = 0
        self.cycle_counter = 0
        self.work_done = True
        logger.info("%s red icons ready to process", len(self.red_icons))
        return State.CLICK_RED_ICON

    def handle_click_red_icon(self) -> State:
        if self.current_red_icon_index >= len(self.red_icons):
            logger.info("All red icons processed, continuing cycle")
            return State.OPEN_BOXES

        confidence, x, y = self.red_icons[self.current_red_icon_index]
        click_x = x + config.RED_ICON_OFFSET_X
        click_y = y + config.RED_ICON_OFFSET_Y

        clicked = self.mouse_controller.click(click_x, click_y, relative=True)
        if not clicked:
            logger.warning("Red icon click failed at (%s, %s)", click_x, click_y)
            self.current_red_icon_index += 1
            if self.current_red_icon_index < len(self.red_icons):
                return State.CLICK_RED_ICON
            return State.OPEN_BOXES

        logger.info(
            "Clicked red icon %s/%s at (%s, %s) [%.3f]",
            self.current_red_icon_index + 1,
            len(self.red_icons),
            click_x,
            click_y,
            confidence,
        )
        return State.CHECK_UNLOCK

    def handle_check_unlock(self) -> State:
        if not self._sleep(config.SCRCPY_ACTION_SETTLE_DELAY):
            return State.CHECK_UNLOCK

        limited_screenshot = self.window_capture.capture(max_y=config.MAX_SEARCH_Y)

        found, confidence, x, y = self.find_unlock_button(limited_screenshot)
        if not found or not self._is_clickable((x, y)):
            return State.SEARCH_UPGRADE_STATION

        logger.info("Unlock found at (%s, %s) [%.3f]", x, y, confidence)
        if not self.mouse_controller.click(x, y, relative=True):
            logger.warning("Unlock click failed at (%s, %s)", x, y)
            return State.CHECK_UNLOCK

        # A stop landing in this settle is handled by the next step(); the state flow does not change.
        self._sleep(config.UNLOCK_SETTLE_DELAY)
        return State.SEARCH_UPGRADE_STATION

    def handle_search_upgrade_station(self) -> State:
        # One attempt per step (state_attempt counts re-entries), so the popup rule, foreground check and
        # watchdog run between attempts. The later attempts use the relaxed threshold.
        attempt = self.state_attempt
        max_attempts = max(1, int(config.UPGRADE_SEARCH_ATTEMPTS))
        threshold = self._relaxed_station_threshold() if attempt > 2 else config.UPGRADE_STATION_THRESHOLD
        position = self._find_upgrade_station_position(threshold)
        if position is not None:
            logger.info("Upgrade station found at (%s, %s) on attempt %s", position[0], position[1], attempt)
            self.upgrade_station_pos = position
            self.upgrade_found_in_cycle = True
            # Deliberately NOT resetting consecutive_failed_cycles here (moved to
            # handle_hold_upgrade_station's genuine-completion point): a station that is found every
            # cycle but never successfully held would otherwise re-zero this counter on every pass,
            # before the hold below ever gets a chance to increment it past 1.
            self.cycle_counter = 0
            return State.HOLD_UPGRADE_STATION

        if attempt < max_attempts:
            # No sleep before giving up on the last attempt.
            self._sleep(config.UPGRADE_SEARCH_INTERVAL)
            return State.SEARCH_UPGRADE_STATION
        self.consecutive_failed_cycles += 1
        logger.info("Upgrade station not found, returning to OPEN_BOXES")
        return State.OPEN_BOXES

    def handle_hold_upgrade_station(self) -> State:
        # Intentional v2 deviation from the old v1 flow (this exact gap was unfixed there): a red icon
        # whose station is found every SEARCH but never actually holds/clicks successfully would
        # otherwise loop FIND_RED_ICONS<->OPEN_BOXES forever, since nothing here used to touch
        # consecutive_failed_cycles and the same-state watchdog never fires (the state keeps changing
        # every tick). Every early exit below counts as a failure and feeds the OPEN_BOXES->SCROLL escape
        # (FAILED_UPGRADE_SEARCHES_BEFORE_SCROLL); it only resets on a genuinely COMPLETED hold, not on
        # the search's "found" branch, so repeated hold failures accumulate across cycles.
        position = self.upgrade_station_pos
        if position is None:
            self.consecutive_failed_cycles += 1
            return State.OPEN_BOXES
        if not self._is_clickable(position):
            logger.warning("Upgrade station blocked by forbidden zone at (%s, %s)", position[0], position[1])
            self.consecutive_failed_cycles += 1
            return State.OPEN_BOXES

        verified = self._verify_upgrade_station()
        if verified is None:
            self.upgrade_station_pos = None
            self.upgrade_found_in_cycle = False
            self.consecutive_failed_cycles += 1
            return State.OPEN_BOXES
        target, relaxed_threshold = verified
        # Replace the stored position with the freshly-verified one: if the hold below fails without
        # clearing it, the next attempt retries against the accurate position.
        self.upgrade_station_pos = target
        # The red icon's row is learned as soon as its station verifies, before the hold, so it is
        # remembered even if the hold then fails.
        if self.current_red_icon_index < len(self.red_icons):
            _, _, red_y = self.red_icons[self.current_red_icon_index]
            self._remember_successful_red_icon_position(red_y)

        hold_check_interval = max(
            config.UPGRADE_HOLD_CHECK_INTERVAL_MIN,
            min(config.UPGRADE_HOLD_CHECK_INTERVAL_MAX, float(config.UPGRADE_STATION_VERIFY_SEARCH_INTERVAL)),
        )
        logger.info("Press-and-holding upgrade station at (%s, %s)", target[0], target[1])
        hold_started_at = time.monotonic()
        held = self.mouse_controller.hold_at(
            target[0],
            target[1],
            config.CLICK_HOLD_MAX_DURATION,
            hold_check_interval,
            self._make_disappearance_check(
                relaxed_threshold, target, max(1, int(config.UPGRADE_STATION_DISAPPEAR_CONFIRMATION_COUNT))
            ),
        )
        if not held:
            # A failed hold returns without clearing the stored position.
            self.consecutive_failed_cycles += 1
            return State.OPEN_BOXES
        self._record_hold(time.monotonic() - hold_started_at)

        # The hold actually completed: real progress, so clear the streak here rather than at the search.
        self.consecutive_failed_cycles = 0
        self.upgrade_station_pos = None
        self.holds_completed += 1
        self.box_only_passes = 0  # a purchase is progress: the dead-loop guard starts over
        self.idle_scrolls = 0
        if not (self._click_idle() and self._sleep(config.STATE_DELAY)):
            return State.OPEN_BOXES
        self.upgrade_station_counter += 1
        if self.upgrade_station_counter >= config.UPGRADES_BEFORE_STATS:
            self.upgrade_station_counter = 0
            logger.info("Upgrade counter reached stats threshold")
            return State.UPGRADE_STATS
        return State.OPEN_BOXES

    def handle_upgrade_stats(self) -> State:
        # Consumed on every entry, even through the idle-click bail-out below, so it cannot go stale.
        from_find = self.stats_from_find
        self.stats_from_find = False
        # Single-shot, no retry loop and no scrcpy recovery here. This is also the one state where an
        # idle-click failure does NOT retry itself.
        if not self._click_idle():
            return State.OPEN_BOXES

        frame = self.window_capture.capture(max_y=config.EXTENDED_SEARCH_Y)
        if self._find_new_level_button(frame[: config.MAX_SEARCH_Y, :])[0]:
            return State.TRANSITION_LEVEL

        self.stats_checks += 1
        # Reuses the shared red-icon scan; split_red_icons applies the stats-icon threshold.
        _, _, stats_seen = self.split_red_icons(self.find_red_icons(frame))
        if not stats_seen:
            logger.info("No stats icon detected")
            # After a hold a miss goes straight to SCROLL; in the no-work loop (from_find) it goes to
            # OPEN_BOXES, and that loop's own scroll comes after it.
            return State.OPEN_BOXES if from_find else State.SCROLL

        self.stats_hits += 1
        self.cycle_counter = 0
        # A hit after a hold is progress. A hit found by the idle loop is NOT: a badge that stays up
        # would zero the stall counter every cycle, so the early probe and the stall alert would never
        # fire, and a frozen frame that shows the badge would never be relaunched.
        if not from_find:
            self.idle_scrolls = 0
        logger.info("Stats icon found, upgrading")
        opened = self.mouse_controller.click(
            config.STATS_UPGRADE_BUTTON_POS[0],
            config.STATS_UPGRADE_BUTTON_POS[1],
            relative=True,
        )
        if opened and self._sleep(config.STATE_DELAY):
            # The stats panel is already open and covers the event banner the forbidden event zones
            # protect, so that protection is a false positive for this one call: bypass it rather than
            # shrinking the zones or moving this confirmed-correct click target.
            if self.mouse_controller.spam_click_at(
                config.STATS_UPGRADE_POS[0],
                config.STATS_UPGRADE_POS[1],
                duration=config.STATS_UPGRADE_CLICK_DURATION,
                click_delay=config.STATS_UPGRADE_CLICK_DELAY,
                mouse_down_duration=config.STATS_UPGRADE_MOUSE_DOWN_DURATION,
                mouse_up_duration=config.STATS_UPGRADE_MOUSE_UP_DURATION,
                relative=True,
                check_forbidden=False,
            ):
                self._click_idle()
                logger.info("Stats upgrade completed")
            else:
                logger.warning("Stats upgrade spam-click failed at %s", config.STATS_UPGRADE_POS)
        return State.OPEN_BOXES

    def handle_open_boxes(self) -> State:
        if not self._click_idle():
            return State.OPEN_BOXES  # retries this same pass, so the after-scroll flag is kept

        # Consumed only now that the pass is really running (see scan_boxes_after_scroll).
        after_scroll = self.scan_boxes_after_scroll
        self.scan_boxes_after_scroll = False
        frame = self.window_capture.capture(max_y=config.BOX_SEARCH_Y)
        thumb = _frame_thumbnail(frame)
        previous = self._latest_thumb
        self._scan_delta = None if previous is None else float(np.abs(thumb - previous).mean())
        self._latest_thumb = thumb
        # First scan after the first scroll of an idle streak. Armed once per streak, not keyed on
        # idle_scrolls == 1: that stays 1 for the next cycle too, whose scan would overwrite it.
        if self._streak_anchor_pending:
            self._streak_anchor_pending = False
            self._streak_thumb = thumb

        if self._find_new_level_button(frame)[0]:
            logger.info("New level found while opening boxes")
            return State.TRANSITION_LEVEL

        boxes = self.find_boxes(frame)
        if not boxes and self._scrcpy_miss_recovery_sleep(config.SCRCPY_BOX_MISS_RECOVERY_DELAY):
            frame = self.window_capture.capture(max_y=config.BOX_SEARCH_Y)
            if self._find_new_level_button(frame)[0]:
                logger.info("New level found while opening boxes after SCRCPY recovery")
                return State.TRANSITION_LEVEL
            boxes = self.find_boxes(frame)

        if self._early_probe_pending:  # log-only: kept clear of the relaunch decision below
            self._early_probe_pending = False
            self._log_early_probe(frame, len(boxes))

        if self._stall_probe_pending:
            self._stall_probe_pending = False
            self._log_box_near_misses(frame, len(boxes))
            if self._game_looks_dead(_frame_thumbnail(frame)):
                return self._relaunch_game()

        opened = 0
        for confidence, x, y, _, _, _ in boxes:
            if not self._is_clickable((x, y)):
                self.box_zone_skips += 1
                continue
            if self.mouse_controller.click(x, y, relative=True):
                opened += 1
                self._recent_box_clicks.append((x, y, confidence))
            else:
                self.box_click_fails += 1
        if opened:
            logger.info("Opened %s boxes", opened)
        return self._next_state_after_box_cycle(opened, after_scroll)

    def handle_scroll(self) -> State:
        if not self._click_idle():
            return State.SCROLL
        if not self._perform_oscillating_scroll_step():
            return State.SCROLL
        self.cycle_counter = 0
        self.box_only_passes = 0
        # Progress elsewhere (box opened, hold, stats, level) zeroes this; a run of landed scrolls with
        # none of those is the stall the alert in _maybe_alert_stall reports.
        self.idle_scrolls += 1
        # The post-scroll crate scan runs before the next red-icon scan (see _next_state_after_box_cycle).
        self.scan_boxes_after_scroll = True
        self._maybe_alert_stall()
        return State.OPEN_BOXES

    def handle_check_new_level(self) -> State:
        if self.nl_first_mark is None:  # every sighting routes here; first one per level
            self.nl_first_mark = self._level_mark()
        # No attempt caps and no scrcpy recovery here: a verify miss resets immediately (single-shot),
        # and the click-retry tail is an unbounded, watchdog-only loop.
        if not self._click_idle():
            logger.warning("Failed to clear focus before confirming the new level")
            return State.CHECK_NEW_LEVEL
        if not self._sleep(config.FOCUS_SETTLE_DELAY):
            return State.CHECK_NEW_LEVEL
        if not self._new_level_red_icon_verified:
            if not self._perform_new_level_verification_scroll():
                logger.warning("Failed to perform verification scroll for new level red icon")
                return State.CHECK_NEW_LEVEL

            frame = self.window_capture.capture(max_y=config.EXTENDED_SEARCH_Y)
            _, verified, _ = self.split_red_icons(self.find_red_icons(frame))
            if not verified:
                logger.info("New level red icon disappeared before visual confirmation; resuming main flow")
                self._reset_search_cycle()
                return State.FIND_RED_ICONS
            logger.info("New level red icon confirmed")
        self._new_level_red_icon_verified = True

        opened = self.mouse_controller.click(
            config.NEW_LEVEL_BUTTON_POS[0],
            config.NEW_LEVEL_BUTTON_POS[1],
            relative=True,
        )
        if not opened:
            logger.warning("Failed to click the new level button at %s", config.NEW_LEVEL_BUTTON_POS)
            return State.CHECK_NEW_LEVEL
        if not self._sleep(config.NEW_LEVEL_CONFIRMATION_DELAY):
            return State.CHECK_NEW_LEVEL
        advanced = self.mouse_controller.click(
            config.LEVEL_TRANSITION_POS[0],
            config.LEVEL_TRANSITION_POS[1],
            relative=True,
        )
        if not advanced:
            logger.warning("Failed to click the level transition button at %s", config.LEVEL_TRANSITION_POS)
            return State.CHECK_NEW_LEVEL
        self._sleep(config.LEVEL_TRANSITION_SECONDARY_SETTLE_DELAY)
        logger.info("Verified red-icon level transition submitted; awaiting unlock confirmation")
        return State.WAIT_FOR_UNLOCK

    def handle_transition_level(self) -> State:
        attempt = self.state_attempt
        max_attempts = max(1, int(config.NEW_LEVEL_SEARCH_ATTEMPTS))
        # One idle click ahead of the whole search (not one per capture), and a failed idle click retries
        # without consuming a search attempt: step() charges one for every same-state return, so net it out.
        if attempt == 1 and not self._click_idle():
            self.state_attempt -= 1
            return State.TRANSITION_LEVEL

        frame = self.window_capture.capture(max_y=config.MAX_SEARCH_Y)
        found, _, x, y = self._find_new_level_button(frame)
        if not found:
            if attempt < max_attempts:
                # No sleep before giving up on the last attempt.
                self._sleep(config.NEW_LEVEL_SEARCH_INTERVAL)
                return State.TRANSITION_LEVEL
            logger.warning("New level button not found after %s attempts", max_attempts)
            self._reset_search_cycle()
            return State.FIND_RED_ICONS

        logger.info("New level button found at (%s, %s) on attempt %s", x, y, attempt)
        # No forbidden-zone pre-gate: a forbidden match is handed to click(), which rejects it, and the
        # failed click routes to CHECK_NEW_LEVEL.
        if not self.mouse_controller.click(x, y, relative=True):
            logger.warning("New level button click failed at (%s, %s)", x, y)
            return State.CHECK_NEW_LEVEL
        if self._sleep(config.LEVEL_TRANSITION_SETTLE_DELAY):
            logger.info("New-level transition submitted; awaiting unlock confirmation")
        return State.WAIT_FOR_UNLOCK

    def handle_wait_for_unlock(self) -> State:
        if not self._click_idle():
            logger.warning("Failed to clear focus while waiting for the next unlock")
            return State.WAIT_FOR_UNLOCK
        if not self._sleep(config.FOCUS_SETTLE_DELAY):
            return State.WAIT_FOR_UNLOCK

        # Full-window capture here, distinct from CHECK_UNLOCK, which looks for the same template in a
        # MAX_SEARCH_Y frame.
        frame = self.window_capture.capture()
        found, confidence, x, y = self.find_unlock_button(frame)
        if found and self._is_clickable((x, y)):
            if self.mouse_controller.click(x, y, relative=True):
                logger.info("Unlock button found at (%s, %s) [%.3f]", x, y, confidence)
                self.total_levels_completed += 1
                self.idle_scrolls = 0
                self.wait_for_unlock_attempts = 0
                self._reset_search_cycle()
                self._report_level_completion()
                self._sleep(config.UNLOCK_SETTLE_DELAY)
                return State.FIND_RED_ICONS
            logger.warning("Unlock button click failed at (%s, %s)", x, y)
        else:
            if found:
                logger.warning("Unlock button found in forbidden zone at (%s, %s)", x, y)
            self._sleep(config.UNLOCK_SEARCH_INTERVAL)

        # A miss, a forbidden match and a failed click all count against the attempt cap.
        self.wait_for_unlock_attempts += 1
        if self.wait_for_unlock_attempts >= self.max_wait_for_unlock_attempts:
            logger.warning(
                "Unlock button not found after %s attempts, resetting",
                self.max_wait_for_unlock_attempts,
            )
            self.wait_for_unlock_attempts = 0
            self._reset_search_cycle()
            self._note_unlock_miss(frame)
            return State.FIND_RED_ICONS
        return State.WAIT_FOR_UNLOCK
