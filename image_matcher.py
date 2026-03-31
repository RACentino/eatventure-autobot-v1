import argparse
import json
import logging
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import cv2
import numpy as np

import config

logger = logging.getLogger(__name__)


class ImageMatcher:
    def __init__(self, threshold=0.85):
        self.threshold = threshold
        cv2.setUseOptimized(True)
        # Limit to 1 thread to prevent CPU starvation between monitor and worker threads
        cv2.setNumThreads(1)

    def _sanitize_sqdiff_result(self, result, template_name="Unknown"):
        if result.size == 0:
            return result

        invalid_mask = ~np.isfinite(result)
        invalid_count = int(np.count_nonzero(invalid_mask))
        if invalid_count == 0:
            return result

        sanitized = np.array(result, copy=True)
        sanitized[invalid_mask] = 1.0
        logger.debug("[%s] Sanitized %d non-finite SQDIFF cells", template_name, invalid_count)
        return sanitized

    def _resolve_sqdiff_match_limit(self, result_shape, min_distance):
        height, width = result_shape[:2]
        suppression = max(1, int(min_distance))
        natural_limit = max(
            1,
            ((width + suppression - 1) // suppression) * ((height + suppression - 1) // suppression),
        )
        hard_limit = max(1, int(getattr(config, "TEMPLATE_MATCH_MAX_RESULTS", 2048)))
        return min(natural_limit, hard_limit)

    def _extract_square_roi(self, image, x, y, size):
        half = max(1, size // 2)
        x1 = max(0, x - half)
        y1 = max(0, y - half)
        x2 = min(image.shape[1], x + half)
        y2 = min(image.shape[0], y + half)
        return image[y1:y2, x1:x2]

    def _build_red_mask(self, hsv):
        mask1 = cv2.inRange(hsv, np.array(config.RED_HSV_LOWER1), np.array(config.RED_HSV_UPPER1))
        mask2 = cv2.inRange(hsv, np.array(config.RED_HSV_LOWER2), np.array(config.RED_HSV_UPPER2))
        mask = cv2.bitwise_or(mask1, mask2)

        kernel_size = max(1, int(getattr(config, "RED_ICON_DILATE_KERNEL", 3)))
        kernel = np.ones((kernel_size, kernel_size), np.uint8)
        return cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    def _build_upgrade_station_mask(self, hsv):
        """HSV mask for the upgrade station's dominant cyan/blue-green color."""
        lower = np.array(getattr(config, "UPGRADE_STATION_HSV_LOWER", (80, 40, 180)))
        upper = np.array(getattr(config, "UPGRADE_STATION_HSV_UPPER", (110, 210, 255)))
        return cv2.inRange(hsv, lower, upper)

    def check_upgrade_station_hsv(self, image, x, y, template_h, template_w):
        """
        HSV color gate for upgrade station candidates.
        Returns True if the ROI at (x, y) has enough cyan/blue-green pixels
        to be a genuine upgrade station rather than an environmental match.
        """
        x1 = max(0, x - template_w // 2)
        y1 = max(0, y - template_h // 2)
        x2 = min(image.shape[1], x1 + template_w)
        y2 = min(image.shape[0], y1 + template_h)
        roi = image[y1:y2, x1:x2]
        if roi.size == 0:
            return False
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = self._build_upgrade_station_mask(hsv)
        total_pixels = roi.shape[0] * roi.shape[1]
        if total_pixels == 0:
            return False
        ratio = cv2.countNonZero(mask) / float(total_pixels)
        min_ratio = float(getattr(config, "UPGRADE_STATION_HSV_MIN_RATIO", 0.15))
        return ratio >= min_ratio

    def analyze_red_region(self, image, x, y, size=24, show_mask=False):
        roi = self._extract_square_roi(image, x, y, size)
        if roi.size == 0:
            return {"pixel_count": 0, "red_ratio": 0.0, "red_mean": 0.0}

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = self._build_red_mask(hsv)
        pixel_count = int(cv2.countNonZero(mask))

        red_ratio = 0.0
        red_mean = 0.0
        if pixel_count:
            red_pixels = roi[mask > 0].astype(np.float32)
            if red_pixels.size:
                dominant = np.maximum(red_pixels[:, 0], red_pixels[:, 1]) + 1e-6
                red_values = red_pixels[:, 2]
                red_mean = float(np.mean(red_values))
                red_ratio = float(np.mean(red_values) / np.mean(dominant))

        if show_mask:
            debug_roi = cv2.resize(mask, (200, 200), interpolation=cv2.INTER_NEAREST)
            cv2.imshow("Red Icon Mask (Debug)", debug_roi)
            cv2.waitKey(1)

        return {"pixel_count": pixel_count, "red_ratio": red_ratio, "red_mean": red_mean}

    def build_red_template_signature(self, template, mask=None):
        opaque_mask = mask.copy() if mask is not None else np.full(template.shape[:2], 255, dtype=np.uint8)
        hsv = cv2.cvtColor(template, cv2.COLOR_BGR2HSV)
        red_mask = self._build_red_mask(hsv)
        red_mask = cv2.bitwise_and(red_mask, opaque_mask)
        return {
            "opaque_mask": opaque_mask,
            "opaque_pixels": int(cv2.countNonZero(opaque_mask)),
            "red_mask": red_mask,
            "red_pixels": int(cv2.countNonZero(red_mask)),
        }

    def is_red_dominant(self, image, x, y, size=12, min_ratio=1.15, min_mean=35):
        roi = self._extract_square_roi(image, x, y, size)
        if roi.size == 0:
            return True

        b, g, r, _ = cv2.mean(roi)
        if r < min_mean:
            return False

        dominant_ratio = max(g, b) + 1e-6
        return (r / dominant_ratio) >= min_ratio

    def count_red_pixels(self, image, x, y, size=24, show_mask=False):
        """
        Counts red pixels in a ROI using HSV masking and morphological opening.
        Requirement: Morphological Opening (erode then dilate) & Pixel Density Trigger.
        Opening removes isolated noise pixels before counting, preventing false gate passages
        caused by stray pixels inflating the density count past the threshold.
        """
        metrics = self.analyze_red_region(image, x, y, size=size, show_mask=show_mask)
        return metrics["pixel_count"]
    
    def load_template(self, template_path):
        template = cv2.imread(str(template_path), cv2.IMREAD_UNCHANGED)
        if template is None:
            raise FileNotFoundError(f"Template not found: {template_path}")
        
        mask = None
        if len(template.shape) == 3 and template.shape[2] == 4:
            alpha = template[:, :, 3]
            mask = np.zeros_like(alpha)
            mask[alpha > 0] = 255
            template = cv2.cvtColor(template, cv2.COLOR_BGRA2BGR)
        
        return template, mask

    @staticmethod
    def _match_top_left_to_center(top_left_x, top_left_y, width, height):
        """
        Convert cv2.matchTemplate top-left coordinates into a true center point.
        Math:
            center_x = top_left_x + (width / 2.0)
            center_y = top_left_y + (height / 2.0)
        Rounded to nearest integer pixel for click targeting.
        """
        center_x = int(round(float(top_left_x) + (float(width) / 2.0)))
        center_y = int(round(float(top_left_y) + (float(height) / 2.0)))
        return center_x, center_y
    
    def find_template(self, screenshot, template, mask=None, threshold=None, template_name="Unknown", check_color=False):
        thresh = threshold if threshold else self.threshold
        
        if template.shape[0] > screenshot.shape[0] or template.shape[1] > screenshot.shape[1]:
            logger.debug(f"Template is larger than screenshot. Template: {template.shape}, Screenshot: {screenshot.shape}")
            return False, 0.0, 0, 0
        
        result = cv2.matchTemplate(screenshot, template, cv2.TM_SQDIFF_NORMED, mask=mask)
        result = self._sanitize_sqdiff_result(result, template_name=template_name)
        
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        if not np.isfinite(min_val):
            logger.debug("[%s] SQDIFF minimum is non-finite; rejecting candidate", template_name)
            return False, 0.0, 0, 0
        if min_loc[0] < 0 or min_loc[1] < 0:
            logger.debug("[%s] SQDIFF minimum location is invalid: %s", template_name, min_loc)
            return False, 0.0, 0, 0
        
        confidence = max(0.0, 1 - float(min_val))
        
        if confidence >= thresh:
            h, w = template.shape[:2]
            center_x, center_y = self._match_top_left_to_center(min_loc[0], min_loc[1], w, h)
            
            if check_color:
                color_match = self._check_color_similarity(screenshot, template, min_loc, mask)
                if not color_match:
                    logger.debug(f"[{template_name}] Color check failed at ({center_x}, {center_y}), confidence: {confidence:.2%}")
                    return False, confidence, 0, 0
            
            return True, confidence, center_x, center_y
        
        return False, confidence, 0, 0
    
    def measure_color_similarity(self, screenshot, template, location, mask=None):
        x, y = location
        h, w = template.shape[:2]
        
        roi = screenshot[y:y+h, x:x+w]
        
        if roi.shape[:2] != template.shape[:2]:
            return 1.0
        
        if mask is not None:
            template_masked = cv2.bitwise_and(template, template, mask=mask)
            roi_masked = cv2.bitwise_and(roi, roi, mask=mask)
        else:
            template_masked = template
            roi_masked = roi
        
        hist_template_b = cv2.calcHist([template_masked], [0], mask, [32], [0, 256])
        hist_template_g = cv2.calcHist([template_masked], [1], mask, [32], [0, 256])
        hist_template_r = cv2.calcHist([template_masked], [2], mask, [32], [0, 256])
        
        hist_roi_b = cv2.calcHist([roi_masked], [0], mask, [32], [0, 256])
        hist_roi_g = cv2.calcHist([roi_masked], [1], mask, [32], [0, 256])
        hist_roi_r = cv2.calcHist([roi_masked], [2], mask, [32], [0, 256])
        
        cv2.normalize(hist_template_b, hist_template_b, 0, 1, cv2.NORM_MINMAX)
        cv2.normalize(hist_template_g, hist_template_g, 0, 1, cv2.NORM_MINMAX)
        cv2.normalize(hist_template_r, hist_template_r, 0, 1, cv2.NORM_MINMAX)
        cv2.normalize(hist_roi_b, hist_roi_b, 0, 1, cv2.NORM_MINMAX)
        cv2.normalize(hist_roi_g, hist_roi_g, 0, 1, cv2.NORM_MINMAX)
        cv2.normalize(hist_roi_r, hist_roi_r, 0, 1, cv2.NORM_MINMAX)
        
        corr_b = cv2.compareHist(hist_template_b, hist_roi_b, cv2.HISTCMP_CORREL)
        corr_g = cv2.compareHist(hist_template_g, hist_roi_g, cv2.HISTCMP_CORREL)
        corr_r = cv2.compareHist(hist_template_r, hist_roi_r, cv2.HISTCMP_CORREL)
        
        return float((corr_b + corr_g + corr_r) / 3)

    def _check_color_similarity(self, screenshot, template, location, mask=None):
        avg_corr = self.measure_color_similarity(screenshot, template, location, mask=mask)
        color_threshold = getattr(config, "COLOR_SIMILARITY_THRESHOLD", 0.7)
        return avg_corr >= color_threshold

    def analyze_red_template_candidate(self, screenshot, x, y, template, mask=None, signature=None, max_offset=1):
        h, w = template.shape[:2]
        if h <= 0 or w <= 0:
            return {
                "coverage": 0.0,
                "precision": 0.0,
                "recall": 0.0,
                "iou": 0.0,
                "color_similarity": 0.0,
                "runtime_red_pixels": 0,
                "score": -1.0,
                "x1": 0,
                "y1": 0,
            }

        signature = signature or self.build_red_template_signature(template, mask=mask)
        opaque_pixels = signature.get("opaque_pixels", 0)
        template_red_pixels = signature.get("red_pixels", 0)
        if opaque_pixels <= 0 or template_red_pixels <= 0:
            return {
                "coverage": 0.0,
                "precision": 0.0,
                "recall": 0.0,
                "iou": 0.0,
                "color_similarity": 0.0,
                "runtime_red_pixels": 0,
                "score": -1.0,
                "x1": 0,
                "y1": 0,
            }

        best = None
        base_x1 = int(round(float(x) - (float(w) / 2.0)))
        base_y1 = int(round(float(y) - (float(h) / 2.0)))
        offset_limit = max(0, int(max_offset))

        for dx in range(-offset_limit, offset_limit + 1):
            for dy in range(-offset_limit, offset_limit + 1):
                x1 = base_x1 + dx
                y1 = base_y1 + dy
                x2 = x1 + w
                y2 = y1 + h
                if x1 < 0 or y1 < 0 or x2 > screenshot.shape[1] or y2 > screenshot.shape[0]:
                    continue

                roi = screenshot[y1:y2, x1:x2]
                if roi.shape[:2] != (h, w):
                    continue

                hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
                runtime_red_mask = self._build_red_mask(hsv)
                runtime_red_mask = cv2.bitwise_and(runtime_red_mask, signature["opaque_mask"])
                runtime_red_pixels = int(cv2.countNonZero(runtime_red_mask))
                overlap_mask = cv2.bitwise_and(runtime_red_mask, signature["red_mask"])
                overlap_pixels = int(cv2.countNonZero(overlap_mask))
                union_pixels = int(
                    cv2.countNonZero(cv2.bitwise_or(runtime_red_mask, signature["red_mask"]))
                )

                coverage = runtime_red_pixels / float(opaque_pixels)
                precision = overlap_pixels / float(runtime_red_pixels) if runtime_red_pixels else 0.0
                recall = overlap_pixels / float(template_red_pixels) if template_red_pixels else 0.0
                iou = overlap_pixels / float(union_pixels) if union_pixels else 0.0
                color_similarity = self.measure_color_similarity(
                    screenshot,
                    template,
                    (x1, y1),
                    mask=mask,
                )
                score = precision + recall + iou + (color_similarity * 0.5)
                candidate = {
                    "coverage": float(coverage),
                    "precision": float(precision),
                    "recall": float(recall),
                    "iou": float(iou),
                    "color_similarity": float(color_similarity),
                    "runtime_red_pixels": runtime_red_pixels,
                    "score": float(score),
                    "x1": int(x1),
                    "y1": int(y1),
                }
                if best is None or candidate["score"] > best["score"]:
                    best = candidate

        return best or {
            "coverage": 0.0,
            "precision": 0.0,
            "recall": 0.0,
            "iou": 0.0,
            "color_similarity": 0.0,
            "runtime_red_pixels": 0,
            "score": -1.0,
            "x1": 0,
            "y1": 0,
        }
    
    def find_all_templates(self, screenshot, template, mask=None, threshold=None, min_distance=15, scales=None, template_name="Unknown", area_tolerance=0.15):
        thresh = threshold if threshold else self.threshold
        all_matches = []
        
        if scales is None:
            scales = [1.0]
        
        if template.shape[0] > screenshot.shape[0] or template.shape[1] > screenshot.shape[1]:
            logger.debug(f"Template is larger than screenshot. Template: {template.shape}, Screenshot: {screenshot.shape}")
            return []
        
        for scale in scales:
            if scale != 1.0:
                scaled_template = cv2.resize(template, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
                scaled_mask = None
                if mask is not None:
                    scaled_mask = cv2.resize(mask, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
                    scaled_mask[scaled_mask > 0] = 255
            else:
                scaled_template = template
                scaled_mask = mask
            
            if scaled_template.shape[0] > screenshot.shape[0] or scaled_template.shape[1] > screenshot.shape[1]:
                continue
            
            result = cv2.matchTemplate(screenshot, scaled_template, cv2.TM_SQDIFF_NORMED, mask=scaled_mask)
            result = self._sanitize_sqdiff_result(result, template_name=template_name)

            fast_matches = self._find_sqdiff_matches(
                result,
                threshold=thresh,
                min_distance=min_distance,
                template_name=template_name,
            )

            h, w = scaled_template.shape[:2]
            expected_area = h * w
            area_min = int(expected_area * (1.0 - area_tolerance))
            area_max = int(expected_area * (1.0 + area_tolerance))
            for confidence, match_x, match_y in fast_matches:
                # Whitelist guard: reject matches whose bounding area deviates
                # beyond tolerance from the known template size. At scale=1.0
                # the match area always equals the template area, so this guard
                # only has bite when multi-scale search is active.
                match_area = h * w  # same scaled template for all matches in this loop
                if not (area_min <= match_area <= area_max):
                    logger.debug(
                        "[%s] Area whitelist rejected match: area=%d not in [%d, %d]",
                        template_name, match_area, area_min, area_max
                    )
                    continue
                center_x, center_y = self._match_top_left_to_center(match_x, match_y, w, h)
                all_matches.append((confidence, center_x, center_y, w, h))
        
        if all_matches:
            all_matches = self._non_max_suppression(all_matches, min_distance)
        
        return [(conf, x, y) for conf, x, y, _, _ in all_matches]

    def _find_sqdiff_matches(self, result, threshold, min_distance, template_name="Unknown"):
        if result.size == 0:
            return []

        max_error = 1 - threshold
        if not np.isfinite(max_error) or max_error < 0:
            return []

        suppression = max(1, int(min_distance))
        working = np.array(result, copy=True)
        height, width = working.shape[:2]
        match_limit = self._resolve_sqdiff_match_limit(working.shape, suppression)
        matches = []

        while len(matches) < match_limit:
            min_val, _, min_loc, _ = cv2.minMaxLoc(working)
            if not np.isfinite(min_val) or min_val > max_error:
                break

            x, y = min_loc
            if x < 0 or y < 0 or x >= width or y >= height:
                logger.warning(
                    "[%s] SQDIFF minimum location %s is outside result bounds %sx%s",
                    template_name,
                    min_loc,
                    width,
                    height,
                )
                break

            matches.append((1 - float(min_val), int(x), int(y)))

            x1 = max(0, x - suppression)
            x2 = min(width, x + suppression + 1)
            y1 = max(0, y - suppression)
            y2 = min(height, y + suppression + 1)
            working[y1:y2, x1:x2] = 1.0

        if len(matches) >= match_limit:
            min_val, _, _, _ = cv2.minMaxLoc(working)
            if np.isfinite(min_val) and min_val <= max_error:
                logger.warning(
                    "[%s] SQDIFF extraction reached match cap (%s); truncating remaining candidates",
                    template_name,
                    match_limit,
                )

        return matches
    
    def _non_max_suppression(self, matches, min_distance):
        if not matches:
            return []
        
        matches = sorted(matches, key=lambda x: x[0], reverse=True)
        filtered = []
        
        for conf, x, y, w, h in matches:
            is_unique = True
            for f_conf, fx, fy, fw, fh in filtered:
                dx = abs(x - fx)
                dy = abs(y - fy)
                
                if dx < min_distance and dy < min_distance:
                    x1, y1 = max(x - w//2, fx - fw//2), max(y - h//2, fy - fh//2)
                    x2, y2 = min(x + w//2, fx + fw//2), min(y + h//2, fy + fh//2)
                    
                    if x2 > x1 and y2 > y1:
                        intersection = (x2 - x1) * (y2 - y1)
                        area1 = w * h
                        area2 = fw * fh
                        union = area1 + area2 - intersection
                        iou = intersection / union if union > 0 else 0
                        
                        if iou > 0.1:
                            is_unique = False
                            break
            
            if is_unique:
                filtered.append((conf, x, y, w, h))
        
        return filtered


class AssetScanner:
    def __init__(self, image_matcher, max_workers=None):
        self.image_matcher = image_matcher
        cpu_count = os.cpu_count() or 1
        self.max_workers = max_workers or min(32, cpu_count + 4)
        self._template_cache = {}
        self._asset_index_cache = {}
        self._cache_lock = threading.RLock()

    def scan(self, assets_dir, required_templates=None):
        assets_path = Path(assets_dir)
        if not assets_path.exists():
            logger.error(f"Assets directory not found: {assets_path}")
            return {}

        required_set = set(required_templates or [])
        template_files = self._collect_template_files(assets_path, required_set)

        templates = {}
        if not template_files:
            return templates

        if len(template_files) == 1:
            template_name, template_data = self._load_template(template_files[0])
            if template_data is not None:
                templates[template_name] = template_data
                logger.info(f"Loaded template: {template_name}")
        else:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {
                    executor.submit(self._load_template, template_file): template_file
                    for template_file in template_files
                }
                for future in as_completed(futures):
                    template_file = futures[future]
                    try:
                        template_name, template_data = future.result()
                    except Exception as exc:
                        logger.error(f"Failed to load template {template_file}: {exc}")
                        continue

                    if template_data is None:
                        continue

                    templates[template_name] = template_data
                    logger.info(f"Loaded template: {template_name}")

        if required_set:
            missing = sorted(required_set.difference(templates.keys()))
            if missing:
                logger.warning(f"Missing {len(missing)} required templates: {', '.join(missing)}")

        return templates

    def _normalize_key(self, name):
        return re.sub(r"[^a-z0-9]+", "", name.lower())

    def _collect_template_files(self, assets_path, required_set):
        indexed = self._index_assets_dir(assets_path)
        if required_set:
            template_files = []
            for template_name in required_set:
                indexed_path = indexed.get(template_name.lower())
                if indexed_path is None:
                    indexed_path = indexed.get(self._normalize_key(template_name))
                if indexed_path is not None:
                    template_files.append(indexed_path)
        else:
            template_files = list(indexed.values())
        template_files = sorted(set(template_files), key=lambda path: str(path).lower())
        return template_files

    def _index_assets_dir(self, assets_path):
        assets_key = str(assets_path)
        try:
            mtime = assets_path.stat().st_mtime
        except OSError:
            mtime = None

        with self._cache_lock:
            cached = self._asset_index_cache.get(assets_key)
            if cached and cached["mtime"] == mtime:
                return cached["index"]

        indexed = {}
        for template_path in assets_path.rglob("*"):
            if not template_path.is_file() or template_path.suffix.lower() != ".png":
                continue
            stem = template_path.stem
            indexed.setdefault(stem.lower(), template_path)
            indexed.setdefault(self._normalize_key(stem), template_path)

        with self._cache_lock:
            self._asset_index_cache[assets_key] = {"mtime": mtime, "index": indexed}
        return indexed

    def _load_template(self, template_file):
        template_name = template_file.stem
        try:
            mtime = template_file.stat().st_mtime
        except OSError:
            mtime = None

        key = str(template_file)
        with self._cache_lock:
            cached = self._template_cache.get(key)
            if cached and cached["mtime"] == mtime:
                return template_name, cached["data"]

        template_img = self.image_matcher.load_template(template_file)
        with self._cache_lock:
            self._template_cache[key] = {"mtime": mtime, "data": template_img}
        return template_name, template_img


def parse_hsv_triplet(value):
    parts = [int(part.strip()) for part in value.split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("HSV bounds must be comma-separated triplets")
    h, s, v = parts
    if not (0 <= h <= 179 and 0 <= s <= 255 and 0 <= v <= 255):
        raise argparse.ArgumentTypeError("HSV bounds must stay within OpenCV ranges")
    return h, s, v


def apply_probe_overrides(args):
    overrides = {
        "RED_ICON_THRESHOLD": args.threshold,
        "RED_ICON_PIXEL_THRESHOLD": args.pixel_threshold,
        "RED_ICON_COLOR_MIN_RATIO": args.ratio_threshold,
        "RED_ICON_COLOR_MAX_RATIO": args.max_ratio_threshold,
        "RED_ICON_COLOR_MIN_MEAN": args.mean_threshold,
        "RED_ICON_TEMPLATE_MIN_COVERAGE": args.coverage_threshold,
        "RED_ICON_TEMPLATE_MIN_PRECISION": args.precision_threshold,
        "RED_ICON_TEMPLATE_MIN_RECALL": args.recall_threshold,
        "RED_ICON_TEMPLATE_MIN_IOU": args.iou_threshold,
        "RED_ICON_TEMPLATE_COLOR_SIMILARITY": args.color_similarity_threshold,
        "RED_HSV_LOWER1": args.red_hsv_lower1,
        "RED_HSV_UPPER1": args.red_hsv_upper1,
        "RED_HSV_LOWER2": args.red_hsv_lower2,
        "RED_HSV_UPPER2": args.red_hsv_upper2,
    }
    for key, value in overrides.items():
        if value is not None:
            setattr(config, key, value)


def load_red_templates(assets_dir, matcher):
    templates = []
    for path in sorted(Path(assets_dir).glob("RedIcon*.png")):
        template, mask = matcher.load_template(path)
        signature = matcher.build_red_template_signature(template, mask=mask)
        templates.append((path.stem, template, mask, signature))
    return templates


def merge_detection(detections, buckets, x, y, template_name, confidence, metrics):
    proximity = config.RED_ICON_MERGE_PROXIMITY
    bucket_size = config.RED_ICON_MERGE_BUCKET_SIZE
    bucket_x = x // bucket_size
    bucket_y = y // bucket_size
    payload = {
        "template": template_name,
        "confidence": float(confidence),
        "pixel_count": int(metrics["pixel_count"]),
        "red_ratio": float(metrics["red_ratio"]),
        "red_mean": float(metrics["red_mean"]),
        "coverage": float(metrics.get("coverage", 0.0)),
        "precision": float(metrics.get("precision", 0.0)),
        "recall": float(metrics.get("recall", 0.0)),
        "iou": float(metrics.get("iou", 0.0)),
        "color_similarity": float(metrics.get("color_similarity", 0.0)),
    }

    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for px, py in buckets.get((bucket_x + dx, bucket_y + dy), []):
                if abs(x - px) < proximity and abs(y - py) < proximity:
                    detections[(px, py)].append(payload)
                    return

    detections[(x, y)] = [payload]
    buckets.setdefault((bucket_x, bucket_y), []).append((x, y))


def passes_red_gate(matcher, frame, x, y):
    metrics = matcher.analyze_red_region(
        frame,
        x,
        y,
        size=config.RED_ICON_COLOR_SAMPLE_SIZE,
        show_mask=False,
    )
    if metrics["pixel_count"] < config.RED_ICON_PIXEL_THRESHOLD:
        return False, "pixel", metrics
    if metrics["red_ratio"] > config.RED_ICON_COLOR_MAX_RATIO:
        return False, "dominance", metrics
    if (
        metrics["red_ratio"] < config.RED_ICON_COLOR_MIN_RATIO
        or metrics["red_mean"] < config.RED_ICON_COLOR_MIN_MEAN
    ):
        return False, "dominance", metrics
    return True, "pass", metrics


def passes_template_gate(matcher, frame, x, y, template, mask, signature):
    metrics = matcher.analyze_red_template_candidate(
        frame,
        x,
        y,
        template,
        mask=mask,
        signature=signature,
        max_offset=config.RED_ICON_TEMPLATE_VERIFY_MAX_OFFSET,
    )
    passes = (
        metrics["coverage"] >= config.RED_ICON_TEMPLATE_MIN_COVERAGE
        and metrics["precision"] >= config.RED_ICON_TEMPLATE_MIN_PRECISION
        and metrics["recall"] >= config.RED_ICON_TEMPLATE_MIN_RECALL
        and metrics["iou"] >= config.RED_ICON_TEMPLATE_MIN_IOU
        and metrics["color_similarity"] >= config.RED_ICON_TEMPLATE_COLOR_SIMILARITY
    )
    return passes, metrics


def detect_red_icons(frame, matcher, templates, threshold, min_distance, max_y):
    working = frame if max_y is None else frame[:max_y, :]
    detections = {}
    buckets = {}
    stats = {
        "raw_template_hits": 0,
        "pixel_rejects": 0,
        "dominance_rejects": 0,
        "template_rejects": 0,
        "accepted_candidates": 0,
        "final_detections": [],
    }

    for template_name, template, mask, signature in templates:
        hits = matcher.find_all_templates(
            working,
            template,
            mask=mask,
            threshold=threshold,
            min_distance=min_distance,
            template_name=template_name,
        )
        stats["raw_template_hits"] += len(hits)

        for confidence, x, y in hits:
            passed, reason, metrics = passes_red_gate(matcher, working, x, y)
            if not passed:
                stats[f"{reason}_rejects"] += 1
                continue
            passed_template, template_metrics = passes_template_gate(
                matcher,
                working,
                x,
                y,
                template,
                mask,
                signature,
            )
            if not passed_template:
                stats["template_rejects"] += 1
                continue
            stats["accepted_candidates"] += 1
            merge_detection(
                detections,
                buckets,
                x,
                y,
                template_name,
                confidence,
                {
                    **metrics,
                    "coverage": template_metrics["coverage"],
                    "precision": template_metrics["precision"],
                    "recall": template_metrics["recall"],
                    "iou": template_metrics["iou"],
                    "color_similarity": template_metrics["color_similarity"],
                },
            )

    for (x, y), matches in detections.items():
        best = max(matches, key=lambda item: item["confidence"])
        stats["final_detections"].append(
            {
                "x": int(x),
                "y": int(y),
                "confidence": round(float(best["confidence"]), 4),
                "pixel_count": int(max(item["pixel_count"] for item in matches)),
                "red_ratio": round(float(max(item["red_ratio"] for item in matches)), 4),
                "red_mean": round(float(max(item["red_mean"] for item in matches)), 2),
                "coverage": round(float(max(item["coverage"] for item in matches)), 4),
                "precision": round(float(max(item["precision"] for item in matches)), 4),
                "recall": round(float(max(item["recall"] for item in matches)), 4),
                "iou": round(float(max(item["iou"] for item in matches)), 4),
                "color_similarity": round(float(max(item["color_similarity"] for item in matches)), 4),
                "templates": sorted({item["template"] for item in matches}),
            }
        )

    stats["final_detections"].sort(key=lambda item: item["confidence"], reverse=True)
    return stats


def iter_probe_frames(input_path, frame_step, max_frames):
    path = Path(input_path)
    if path.is_dir():
        yielded = 0
        for image_path in sorted(path.glob("*")):
            if image_path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".bmp"}:
                continue
            frame = cv2.imread(str(image_path))
            if frame is None:
                continue
            yield {"label": image_path.name, "frame": frame}
            yielded += 1
            if max_frames is not None and yielded >= max_frames:
                return
        return

    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp"}:
        frame = cv2.imread(str(path))
        if frame is not None:
            yield {"label": path.name, "frame": frame}
        return

    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise FileNotFoundError(f"Unable to open input: {path}")

    yielded = 0
    index = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        if index % frame_step == 0:
            yield {"label": f"{path.name}:frame-{index}", "frame": frame}
            yielded += 1
            if max_frames is not None and yielded >= max_frames:
                break
        index += 1
    capture.release()


def build_probe_parser(parser):
    parser.description = "Probe red icon HSV and confidence settings on sample frames"
    parser.add_argument("--input", required=True, help="Image, directory of images, or video to probe")
    parser.add_argument(
        "--assets-dir",
        default=config.ASSETS_DIR,
        help="Directory containing RedIcon*.png templates",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=config.RED_ICON_THRESHOLD,
        help="Template confidence threshold",
    )
    parser.add_argument(
        "--pixel-threshold",
        type=int,
        default=config.RED_ICON_PIXEL_THRESHOLD,
        help="Minimum masked red pixel count",
    )
    parser.add_argument(
        "--ratio-threshold",
        type=float,
        default=config.RED_ICON_COLOR_MIN_RATIO,
        help="Minimum masked red dominance ratio",
    )
    parser.add_argument(
        "--max-ratio-threshold",
        type=float,
        default=config.RED_ICON_COLOR_MAX_RATIO,
        help="Maximum masked red dominance ratio",
    )
    parser.add_argument(
        "--mean-threshold",
        type=float,
        default=config.RED_ICON_COLOR_MIN_MEAN,
        help="Minimum masked red channel mean",
    )
    parser.add_argument(
        "--coverage-threshold",
        type=float,
        default=config.RED_ICON_TEMPLATE_MIN_COVERAGE,
        help="Minimum template-mask red coverage",
    )
    parser.add_argument(
        "--precision-threshold",
        type=float,
        default=config.RED_ICON_TEMPLATE_MIN_PRECISION,
        help="Minimum template-mask precision",
    )
    parser.add_argument(
        "--recall-threshold",
        type=float,
        default=config.RED_ICON_TEMPLATE_MIN_RECALL,
        help="Minimum template-mask recall",
    )
    parser.add_argument(
        "--iou-threshold",
        type=float,
        default=config.RED_ICON_TEMPLATE_MIN_IOU,
        help="Minimum template-mask IoU",
    )
    parser.add_argument(
        "--color-similarity-threshold",
        type=float,
        default=config.RED_ICON_TEMPLATE_COLOR_SIMILARITY,
        help="Minimum template color histogram correlation",
    )
    parser.add_argument(
        "--red-hsv-lower1",
        type=parse_hsv_triplet,
        default=config.RED_HSV_LOWER1,
        help="Low red lower HSV bound",
    )
    parser.add_argument(
        "--red-hsv-upper1",
        type=parse_hsv_triplet,
        default=config.RED_HSV_UPPER1,
        help="Low red upper HSV bound",
    )
    parser.add_argument(
        "--red-hsv-lower2",
        type=parse_hsv_triplet,
        default=config.RED_HSV_LOWER2,
        help="High red lower HSV bound",
    )
    parser.add_argument(
        "--red-hsv-upper2",
        type=parse_hsv_triplet,
        default=config.RED_HSV_UPPER2,
        help="High red upper HSV bound",
    )
    parser.add_argument("--frame-step", type=int, default=45, help="Video frame sampling interval")
    parser.add_argument("--max-frames", type=int, default=8, help="Maximum sampled frames to analyze")
    parser.add_argument(
        "--max-y",
        type=int,
        default=config.MAX_SEARCH_Y,
        help="Crop frames to this Y limit before detection",
    )
    parser.add_argument(
        "--min-distance",
        type=int,
        default=config.RED_ICON_MIN_DISTANCE,
        help="Minimum template match spacing",
    )
    parser.add_argument("--json-out", help="Optional path to write the analysis summary as JSON")


def run_red_icon_probe_cli(argv=None):
    parser = argparse.ArgumentParser()
    build_probe_parser(parser)
    args = parser.parse_args(argv)
    apply_probe_overrides(args)

    matcher = ImageMatcher(config.MATCH_THRESHOLD)
    templates = load_red_templates(args.assets_dir, matcher)
    if not templates:
        raise FileNotFoundError(f"No RedIcon*.png templates found in {args.assets_dir}")

    summary = {
        "config": {
            "threshold": config.RED_ICON_THRESHOLD,
            "pixel_threshold": config.RED_ICON_PIXEL_THRESHOLD,
            "ratio_threshold": config.RED_ICON_COLOR_MIN_RATIO,
            "max_ratio_threshold": config.RED_ICON_COLOR_MAX_RATIO,
            "mean_threshold": config.RED_ICON_COLOR_MIN_MEAN,
            "coverage_threshold": config.RED_ICON_TEMPLATE_MIN_COVERAGE,
            "precision_threshold": config.RED_ICON_TEMPLATE_MIN_PRECISION,
            "recall_threshold": config.RED_ICON_TEMPLATE_MIN_RECALL,
            "iou_threshold": config.RED_ICON_TEMPLATE_MIN_IOU,
            "color_similarity_threshold": config.RED_ICON_TEMPLATE_COLOR_SIMILARITY,
            "red_hsv_lower1": config.RED_HSV_LOWER1,
            "red_hsv_upper1": config.RED_HSV_UPPER1,
            "red_hsv_lower2": config.RED_HSV_LOWER2,
            "red_hsv_upper2": config.RED_HSV_UPPER2,
        },
        "frames": [],
    }

    for frame_info in iter_probe_frames(args.input, args.frame_step, args.max_frames):
        stats = detect_red_icons(
            frame_info["frame"],
            matcher,
            templates,
            threshold=config.RED_ICON_THRESHOLD,
            min_distance=args.min_distance,
            max_y=args.max_y,
        )
        stats["label"] = frame_info["label"]
        summary["frames"].append(stats)

    totals = {
        "frame_count": len(summary["frames"]),
        "raw_template_hits": sum(frame["raw_template_hits"] for frame in summary["frames"]),
        "pixel_rejects": sum(frame["pixel_rejects"] for frame in summary["frames"]),
        "dominance_rejects": sum(frame["dominance_rejects"] for frame in summary["frames"]),
        "template_rejects": sum(frame["template_rejects"] for frame in summary["frames"]),
        "accepted_candidates": sum(frame["accepted_candidates"] for frame in summary["frames"]),
        "final_detections": sum(len(frame["final_detections"]) for frame in summary["frames"]),
    }
    summary["totals"] = totals

    print(json.dumps(summary, indent=2))
    if args.json_out:
        output_path = Path(args.json_out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 0


def load_opaque(path):
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        return None, None
    if len(img.shape) == 3 and img.shape[2] == 4:
        alpha = img[:, :, 3]
        bgr = img[:, :, :3]
        mask = alpha > 0
    else:
        bgr = img
        mask = np.ones(img.shape[:2], dtype=bool)
    return bgr, mask


def test_red_icon_gate(bgr, opaque_mask):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)

    lower1 = np.array(config.RED_HSV_LOWER1)
    upper1 = np.array(config.RED_HSV_UPPER1)
    lower2 = np.array(config.RED_HSV_LOWER2)
    upper2 = np.array(config.RED_HSV_UPPER2)

    mask1 = cv2.inRange(hsv, lower1, upper1)
    mask2 = cv2.inRange(hsv, lower2, upper2)
    combined = cv2.bitwise_or(mask1, mask2)

    opaque_uint8 = opaque_mask.astype(np.uint8) * 255
    combined = cv2.bitwise_and(combined, opaque_uint8)

    red_count = cv2.countNonZero(combined)
    total_opaque = int(np.sum(opaque_mask))
    ratio = red_count / total_opaque if total_opaque > 0 else 0
    threshold = getattr(config, "RED_ICON_PIXEL_THRESHOLD", 48)

    return {
        "red_pixels": red_count,
        "total_opaque": total_opaque,
        "ratio": ratio,
        "passes_threshold": red_count >= threshold,
        "threshold": threshold,
    }


def test_upgrade_station_gate(bgr, opaque_mask):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)

    lower = np.array(getattr(config, "UPGRADE_STATION_HSV_LOWER", (80, 40, 180)))
    upper = np.array(getattr(config, "UPGRADE_STATION_HSV_UPPER", (110, 210, 255)))

    mask = cv2.inRange(hsv, lower, upper)

    opaque_uint8 = opaque_mask.astype(np.uint8) * 255
    mask = cv2.bitwise_and(mask, opaque_uint8)

    cyan_count = cv2.countNonZero(mask)
    total_opaque = int(np.sum(opaque_mask))
    ratio = cyan_count / total_opaque if total_opaque > 0 else 0
    min_ratio = float(getattr(config, "UPGRADE_STATION_HSV_MIN_RATIO", 0.15))

    return {
        "cyan_pixels": cyan_count,
        "total_opaque": total_opaque,
        "ratio": ratio,
        "passes_ratio": ratio >= min_ratio,
        "min_ratio": min_ratio,
    }


def run_hsv_gate_validation_cli(argv=None):
    parser = argparse.ArgumentParser(description="Validate HSV color gates against the bot's asset images")
    parser.add_argument(
        "--assets-dir",
        default=config.ASSETS_DIR,
        help="Directory containing the asset PNGs to validate",
    )
    args = parser.parse_args(argv)

    assets_dir = Path(args.assets_dir)
    print("=" * 70)
    print("HSV COLOR GATE VALIDATION")
    print(f"Assets directory: {assets_dir}")
    print("=" * 70)

    print("\nRed Icon HSV Config:")
    print(f"  Band 1: {config.RED_HSV_LOWER1} - {config.RED_HSV_UPPER1}")
    print(f"  Band 2: {config.RED_HSV_LOWER2} - {config.RED_HSV_UPPER2}")
    print(f"  Pixel Threshold: {config.RED_ICON_PIXEL_THRESHOLD}")

    print("\nUpgrade Station HSV Config:")
    print(f"  Range: {config.UPGRADE_STATION_HSV_LOWER} - {config.UPGRADE_STATION_HSV_UPPER}")
    print(f"  Min Ratio: {config.UPGRADE_STATION_HSV_MIN_RATIO}")

    passed = 0
    failed = 0
    total = 0

    print(f"\n{'-' * 70}")
    print("RED ICON ASSETS")
    print(f"{'-' * 70}")

    for path in sorted(assets_dir.glob("*.png")):
        if not path.name.lower().startswith("redicon"):
            continue

        bgr, opaque_mask = load_opaque(path)
        if bgr is None:
            print(f"  SKIP {path.name} (could not load)")
            continue

        total += 1
        result = test_red_icon_gate(bgr, opaque_mask)
        status = "PASS" if result["passes_threshold"] else "FAIL"
        if result["passes_threshold"]:
            passed += 1
        else:
            failed += 1

        print(
            f"  [{status}] {path.name:25s}  red_px={result['red_pixels']:4d}/{result['total_opaque']:4d}  "
            f"ratio={result['ratio']:.1%}  (threshold={result['threshold']})"
        )

    print(f"\n{'-' * 70}")
    print("UPGRADE STATION ASSETS")
    print(f"{'-' * 70}")

    for path in sorted(assets_dir.glob("*.png")):
        if "upgrade" not in path.name.lower():
            continue

        bgr, opaque_mask = load_opaque(path)
        if bgr is None:
            print(f"  SKIP {path.name} (could not load)")
            continue

        total += 1
        result = test_upgrade_station_gate(bgr, opaque_mask)
        status = "PASS" if result["passes_ratio"] else "FAIL"
        if result["passes_ratio"]:
            passed += 1
        else:
            failed += 1

        print(
            f"  [{status}] {path.name:25s}  cyan_px={result['cyan_pixels']:4d}/{result['total_opaque']:5d}  "
            f"ratio={result['ratio']:.1%}  (min={result['min_ratio']:.0%})"
        )

    print(f"\n{'=' * 70}")
    print(f"SUMMARY: {passed}/{total} passed, {failed}/{total} failed")
    if failed > 0:
        print("WARNING: Some assets FAILED their HSV gate!")
        return 1

    print("All assets passed their respective HSV color gates.")
    return 0


def run_cli(argv=None):
    parser = argparse.ArgumentParser(description="Image matching utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_probe_parser(subparsers.add_parser("probe-red-icons"))
    subparsers.add_parser("validate-hsv-gates", help="Validate HSV gates against asset PNGs")
    args, remaining = parser.parse_known_args(argv)

    if args.command == "probe-red-icons":
        return run_red_icon_probe_cli(remaining)
    if args.command == "validate-hsv-gates":
        return run_hsv_gate_validation_cli(remaining)
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(run_cli(sys.argv[1:]))
