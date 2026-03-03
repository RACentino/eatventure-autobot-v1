import time
import logging
import cv2
import numpy as np
from typing import List, Tuple, Optional, Callable
import config

logger = logging.getLogger(__name__)

class WorldCoordTracker:
    """
    Dynamic ROI Tracker: Tracks asset positions in world-coordinates
    to calculate precise search ROIs as the screen scrolls.
    """
    def __init__(self):
        self.tracked_assets = {}  # {asset_id: (world_x, world_y, type)}
        self.next_id = 0

    def register_asset(self, screen_x, screen_y, scroll_y, asset_type):
        world_x = screen_x
        world_y = screen_y + scroll_y
        asset_id = self.next_id
        self.tracked_assets[asset_id] = (world_x, world_y, asset_type)
        self.next_id += 1
        return asset_id

    def get_screen_roi(self, asset_id, scroll_y, padding=50):
        if asset_id not in self.tracked_assets:
            return None
        world_x, world_y, _ = self.tracked_assets[asset_id]
        screen_x = world_x
        screen_y = world_y - scroll_y
        
        # Calculate ROI bounding box
        x_min = max(0, screen_x - padding)
        x_max = screen_x + padding # Clamping handled at scan-time
        y_min = max(0, screen_y - padding)
        y_max = screen_y + padding
        
        return (int(x_min), int(x_max), int(y_min), int(y_max))

class ScrollHandler:
    """
    Navigation Handler: Exclusively controls all screen movement.
    Maintains the current vertical scroll state and enforces smooth, steady linear glides.
    """
    def __init__(self, bot):
        self.bot = bot
        self.mouse = bot.mouse_controller
        self.current_scroll_y = 0  # Cumulative scroll offset in pixels
        
    def scroll(self, distance: int, direction: str = "DOWN", duration: float = None):
        """
        Executes a smooth, linear glide to prevent ballistic flicks and motion blur.
        distance: positive integer (pixels)
        direction: "DOWN" (moves world UP) or "UP" (moves world DOWN)
        """
        if duration is None:
            duration = getattr(config, "SCROLL_DURATION", 0.3)
            
        start_pos = getattr(config, "SCROLL_START_POS", (180, 390))
        start_x, start_y = start_pos
        
        # Scroll Physics: Precise linear step calculation
        dir_mult = 1 if direction.upper() == "UP" else -1
        end_y = start_y - (distance * dir_mult)
        
        logger.info(f"[Scroll] Linear Glide: {distance}px {direction} (World Y Offset: {self.current_scroll_y})")
        
        # Delegate to mouse controller which handles the smooth linear steps
        success = self.mouse.drag(
            start_x, start_y, start_x, end_y,
            duration=duration,
            relative=True,
            interrupt_check=lambda: self.bot.check_critical_interrupts(raise_exception=False)
        )
        
        if success:
            self.current_scroll_y += (distance * dir_mult)
            # Mandatory settle period for CV pipeline stability
            self.bot.sleep(getattr(config, "SCROLL_SETTLE_DELAY", 0.15))
            
        return success

    def reset_offset(self):
        """Used when a new level starts and the world resets."""
        self.current_scroll_y = 0

class BaseHandler:
    def __init__(self, bot, scroll_handler: ScrollHandler):
        self.bot = bot
        self.scroll_handler = scroll_handler
        self.image_matcher = bot.image_matcher
        self.templates = bot.templates
        self.tracker = WorldCoordTracker()

    def verify_bgr_match(self, screenshot, x, y, template_name, threshold=None):
        """
        Whitelist Click Policy: Strictly validates the BGR content at the target coordinate.
        If the template doesn't match perfectly, the click is aborted.
        """
        if template_name not in self.templates:
            return False
            
        template, mask = self.templates[template_name]
        # Use high confidence for verification
        threshold = threshold or getattr(config, "VERIFY_THRESHOLD", 0.96)
            
        padding = getattr(config, "VERIFY_PADDING", 32)
        x1, y1 = max(0, x - padding), max(0, y - padding)
        x2, y2 = min(screenshot.shape[1], x + padding), min(screenshot.shape[0], y + padding)
        
        roi = screenshot[y1:y2, x1:x2]
        if roi.size == 0: return False
        
        found, confidence, rx, ry = self.image_matcher.find_template(
            roi, template, mask=mask, threshold=threshold, template_name=f"{template_name}-verify"
        )
        
        if found:
            # Check if the found match is at the expected location (center of ROI)
            if abs(rx + x1 - x) < 5 and abs(ry + y1 - y) < 5:
                return True
        return False

class RedIconHandler(BaseHandler):
    """Isolated module for Red Icon processing."""
    def __init__(self, bot, scroll_handler):
        super().__init__(bot, scroll_handler)
        self.red_icon_templates = [
            "RedIcon", "RedIcon2", "RedIcon3", "RedIcon4", "RedIcon5", "RedIcon6",
            "RedIcon7", "RedIcon8", "RedIcon9", "RedIcon10", "RedIcon11", "RedIcon12",
            "RedIcon13", "RedIcon14", "RedIcon15", "RedIconNoBG"
        ]
        self.active_targets = []  # List of (world_x, world_y, template_name)

    def process(self, screenshot: np.ndarray):
        """
        Refined: Hybrid Tracking and Banded Scanning.
        1. Tracks existing targets via World Coordinates.
        2. Falls back to Targeted Horizontal Banding for new discoveries.
        """
        scroll_y = self.scroll_handler.current_scroll_y
        
        # 1. Localized Search: Try known targets first
        if self._search_tracked_targets(screenshot, scroll_y):
            return True

        # 2. Discovery: Targeted Horizontal Banding (Scanning bands for new icons)
        max_y = getattr(config, "MAX_SEARCH_Y", 660)
        # Priority bands: Top, then Mid, then Bottom
        bands = [(0, 220), (220, 440), (440, max_y)]
        
        for y_start, y_end in bands:
            if self._scan_roi(screenshot, (0, screenshot.shape[1], y_start, y_end)):
                return True
        return False

    def _search_tracked_targets(self, screenshot, scroll_y):
        still_active = []
        found_any = False
        
        # Sort targets by Screen Y to click from top to bottom
        self.active_targets.sort(key=lambda t: t[1] - scroll_y)

        for wx, wy, name in self.active_targets:
            sx, sy = wx, wy - scroll_y
            
            # If target is on screen
            if 10 <= sy < getattr(config, "MAX_SEARCH_Y", 660) - 10:
                # Targeted Local ROI (Localized search)
                roi_box = (max(0, sx-45), min(screenshot.shape[1], sx+45), 
                           max(0, sy-45), min(screenshot.shape[0], sy+45))
                
                if not found_any and self._scan_roi(screenshot, roi_box):
                    found_any = True
                    # If clicked, it's no longer 'active' (or will be re-detected)
                    continue
                else:
                    still_active.append((wx, wy, name))
            elif -500 < sy < 1500: # Keep track of targets slightly off-screen
                still_active.append((wx, wy, name))
        
        self.active_targets = still_active
        return found_any

    def _scan_roi(self, screenshot, roi_box):
        x1, x2, y1, y2 = [int(v) for v in roi_box]
        roi = screenshot[y1:y2, x1:x2]
        if roi.size == 0: return False
        
        threshold = getattr(config, "RED_ICON_THRESHOLD", 0.94)
        scroll_y = self.scroll_handler.current_scroll_y
        
        found_icons = []
        for name in self.red_icon_templates:
            if name not in self.templates: continue
            template, mask = self.templates[name]
            
            matches = self.image_matcher.find_all_templates(
                roi, template, mask=mask, threshold=threshold
            )
            
            for conf, rx, ry in matches:
                abs_x, abs_y = rx + x1, ry + y1
                # Color gate check
                if self.bot._passes_red_color_gate(screenshot, abs_x, abs_y)[0]:
                    found_icons.append((conf, abs_x, abs_y, name))
        
        if not found_icons: return False
        
        # Whitelist Verification and Interaction
        found_icons.sort(key=lambda i: i[0], reverse=True)
        for conf, x, y, name in found_icons:
            if self.verify_bgr_match(screenshot, x, y, name):
                # Update tracker with world coordinates
                self._add_to_tracker(x, y, scroll_y, name)
                
                logger.info(f"[RedIcon] Whitelist Verified at ({x}, {y})")
                if self.bot.mouse_controller.click(x, y, relative=True):
                    return True
        return False

    def _add_to_tracker(self, sx, sy, scroll_y, name):
        wx, wy = sx, sy + scroll_y
        # Avoid duplicates
        for twx, twy, tname in self.active_targets:
            if abs(twx - wx) < 30 and abs(twy - wy) < 30:
                return
        self.active_targets.append((wx, wy, name))

class UpgradeStationHandler(BaseHandler):
    """Isolated module for Upgrade Station processing."""
    def process(self, screenshot: np.ndarray):
        # Upgrade stations are usually in the lower half
        search_roi = (0, screenshot.shape[1], 250, getattr(config, "MAX_SEARCH_Y", 660))
        x1, x2, y1, y2 = search_roi
        roi = screenshot[y1:y2, x1:x2]
        
        # Use existing bot logic to find candidates but wrap in strict verification
        stations = self.bot._find_upgrade_stations(roi)
        for conf, rel_x, rel_y in stations:
            abs_x, abs_y = rel_x + x1, rel_y + y1
            
            if self.verify_bgr_match(screenshot, abs_x, abs_y, "upgradeStation"):
                logger.info(f"[UpgradeStation] Whitelist Verified at ({abs_x}, {abs_y})")
                if self.bot.mouse_controller.click(abs_x, abs_y, relative=True):
                    return True
        return False

class BoxHandler(BaseHandler):
    """Isolated module for Box processing."""
    def process(self, screenshot: np.ndarray):
        # Boxes appear anywhere in the middle
        search_roi = (0, screenshot.shape[1], 150, getattr(config, "MAX_SEARCH_Y", 660))
        x1, x2, y1, y2 = search_roi
        roi = screenshot[y1:y2, x1:x2]
        
        boxes = self.bot._find_boxes(roi)
        for conf, rel_x, rel_y in boxes:
            abs_x, abs_y = rel_x + x1, rel_y + y1
            
            # Whitelist verification against all box variations
            for i in range(1, 6):
                if self.verify_bgr_match(screenshot, abs_x, abs_y, f"box{i}"):
                    logger.info(f"[Box] Whitelist Verified: box{i} at ({abs_x}, {abs_y})")
                    if self.bot.mouse_controller.click(abs_x, abs_y, relative=True):
                        return True
                    break
        return False

