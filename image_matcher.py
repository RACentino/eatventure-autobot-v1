import logging
from itertools import islice
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

MatchResult = tuple[bool, float, int, int]
MatchCandidate = tuple[float, int, int, int, int]
Point = tuple[int, int]
HsvRange = tuple[np.ndarray, np.ndarray]
MAX_TEMPLATE_SCALES = 16


class ImageMatcher:
    def __init__(self, threshold: float = 0.85) -> None:
        self.threshold = self._normalize_threshold(threshold)

    @staticmethod
    def _normalize_threshold(value: Any, default: float = 0.85) -> float:
        try:
            fallback = float(default)
        except (TypeError, ValueError):
            fallback = 0.85
        if not np.isfinite(fallback):
            fallback = 0.85
        fallback = max(0.0, min(1.0, fallback))

        try:
            threshold = float(value)
        except (TypeError, ValueError):
            return fallback
        if not np.isfinite(threshold):
            return fallback
        return max(0.0, min(1.0, threshold))

    @staticmethod
    def _normalize_image(image: np.ndarray, label: str) -> np.ndarray:
        if image is None or not hasattr(image, "shape") or image.size == 0:
            raise ValueError(f"{label} is empty")
        if image.ndim == 2:
            return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        if image.ndim == 3 and image.shape[2] == 3:
            return image
        if image.ndim == 3 and image.shape[2] == 4:
            return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
        raise ValueError(f"{label} has unsupported shape {image.shape}")

    @staticmethod
    def _normalize_mask(mask: np.ndarray | None, template_shape: tuple[int, ...], template_name: str) -> np.ndarray | None:
        if mask is None:
            return None
        if not hasattr(mask, "shape") or mask.size == 0:
            logger.warning("[%s] Ignoring empty mask", template_name)
            return None
        if mask.ndim == 3:
            try:
                mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)
            except cv2.error as exc:
                logger.warning("[%s] Ignoring unsupported mask: %s", template_name, exc)
                return None
        elif mask.ndim != 2:
            logger.warning("[%s] Ignoring mask with unsupported shape %s", template_name, mask.shape)
            return None
        if mask.shape[:2] != template_shape[:2]:
            logger.warning(
                "[%s] Ignoring mask with shape %s for template shape %s",
                template_name,
                mask.shape,
                template_shape,
            )
            return None
        if mask.dtype == np.uint8:
            if not np.any(mask):
                logger.warning("[%s] Ignoring mask without active pixels", template_name)
                return None
            return mask
        normalized = np.zeros(mask.shape[:2], dtype=np.uint8)
        normalized[mask > 0] = 255
        if not np.any(normalized):
            logger.warning("[%s] Ignoring mask without active pixels", template_name)
            return None
        return normalized

    @staticmethod
    def _safe_match_template(
        screenshot: np.ndarray,
        template: np.ndarray,
        mask: np.ndarray | None,
        template_name: str,
    ) -> np.ndarray | None:
        match_mask = None if mask is not None and np.all(mask) else mask
        try:
            result = cv2.matchTemplate(screenshot, template, cv2.TM_SQDIFF_NORMED, mask=match_mask)
        except cv2.error as exc:
            logger.warning("[%s] Template matching failed: %s", template_name, exc)
            return None
        if result.size == 0:
            return None
        np.nan_to_num(result, copy=False, nan=1.0, posinf=1.0, neginf=1.0)
        np.clip(result, 0.0, 1.0, out=result)
        return result

    @staticmethod
    def _failed_match(confidence: float = 0.0) -> MatchResult:
        return False, float(confidence), 0, 0

    @staticmethod
    def _template_fits_screenshot(screenshot: np.ndarray, template: np.ndarray, template_name: str) -> bool:
        if template.shape[0] <= screenshot.shape[0] and template.shape[1] <= screenshot.shape[1]:
            return True
        logger.debug(
            "Template is larger than screenshot. Template %s: %s, Screenshot: %s",
            template_name,
            template.shape,
            screenshot.shape,
        )
        return False

    @staticmethod
    def _center_from_location(location: Point, template: np.ndarray) -> Point:
        template_height, template_width = template.shape[:2]
        return location[0] + template_width // 2, location[1] + template_height // 2
    
    def load_template(self, template_path: Any) -> tuple[np.ndarray, np.ndarray | None]:
        template = cv2.imread(str(template_path), cv2.IMREAD_UNCHANGED)
        if template is None:
            raise FileNotFoundError(f"Template not found: {template_path}")
        
        mask = None
        if template.ndim == 3 and template.shape[2] == 4:
            alpha = template[:, :, 3]
            if not np.any(alpha > 0):
                raise ValueError(f"Template has no visible pixels: {template_path}")
            mask = np.zeros_like(alpha)
            mask[alpha > 0] = 255
        template = self._normalize_image(template, str(template_path))
        
        return template, mask

    def find_template(
        self,
        screenshot: np.ndarray,
        template: np.ndarray,
        mask: np.ndarray | None = None,
        threshold: float | None = None,
        template_name: str = "Unknown",
        hsv_ranges: Any = None,
        hsv_match_threshold: float = 0.9,
    ) -> MatchResult:
        thresh = self.threshold if threshold is None else self._normalize_threshold(threshold, self.threshold)
        try:
            screenshot = self._normalize_image(screenshot, "screenshot")
            template = self._normalize_image(template, template_name)
        except ValueError as exc:
            logger.warning("[%s] Invalid match input: %s", template_name, exc)
            return self._failed_match()
        mask = self._normalize_mask(mask, template.shape, template_name)
        normalized_hsv_ranges = self._normalize_hsv_ranges(hsv_ranges) if hsv_ranges is not None else None
        normalized_hsv_threshold = self._normalize_threshold(hsv_match_threshold, 0.9)

        if not self._template_fits_screenshot(screenshot, template, template_name):
            return self._failed_match()

        result = self._safe_match_template(screenshot, template, mask, template_name)
        if result is None:
            return self._failed_match()

        min_value, _, min_location, _ = cv2.minMaxLoc(result)
        confidence = float(1.0 - min_value)
        if not np.isfinite(confidence):
            return self._failed_match()
        
        if confidence < thresh:
            return self._failed_match(confidence)

        center_x, center_y = self._center_from_location(min_location, template)
        if normalized_hsv_ranges is not None and not self._check_hsv_gate(
            screenshot,
            template,
            min_location,
            mask,
            normalized_hsv_ranges,
            normalized_hsv_threshold,
        ):
            logger.debug(
                "[%s] HSV gate failed at (%s, %s), confidence: %.2f%%",
                template_name,
                center_x,
                center_y,
                confidence * 100,
            )
            return self._failed_match(confidence)
        return True, confidence, center_x, center_y

    @staticmethod
    def _normalize_hsv_component(values: np.ndarray) -> np.ndarray | None:
        if values.shape != (3,) or not np.all(np.isfinite(values)):
            return None
        return np.clip(values, (0, 0, 0), (179, 255, 255)).astype(np.uint8)

    @classmethod
    def _normalize_hsv_range(cls: type["ImageMatcher"], hsv_range: Any) -> HsvRange | None:
        try:
            lower, upper = hsv_range
            lower = np.asarray(lower, dtype=np.float64)
            upper = np.asarray(upper, dtype=np.float64)
        except (TypeError, ValueError, OverflowError):
            return None
        if lower.shape != (3,) or upper.shape != (3,):
            return None
        normalized_lower = cls._normalize_hsv_component(lower)
        normalized_upper = cls._normalize_hsv_component(upper)
        if normalized_lower is None or normalized_upper is None:
            return None
        return normalized_lower, normalized_upper

    @classmethod
    def _normalize_hsv_ranges(cls: type["ImageMatcher"], hsv_ranges: Any) -> list[HsvRange]:
        try:
            return [
                normalized_range
                for hsv_range in hsv_ranges
                if (normalized_range := cls._normalize_hsv_range(hsv_range)) is not None
            ]
        except TypeError:
            return []

    @staticmethod
    def _apply_hsv_range_mask(hsv_region: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> np.ndarray:
        if int(lower[0]) <= int(upper[0]):
            return cv2.inRange(hsv_region, lower, upper)

        lower_wrap = lower.copy()
        upper_wrap = upper.copy()
        lower_wrap[0] = 0
        upper_wrap[0] = 179
        return cv2.bitwise_or(
            cv2.inRange(hsv_region, lower, upper_wrap),
            cv2.inRange(hsv_region, lower_wrap, upper),
        )

    def _check_hsv_gate(
        self,
        screenshot: np.ndarray,
        template: np.ndarray,
        location: Point,
        mask: np.ndarray | None,
        hsv_ranges: list[HsvRange],
        hsv_match_threshold: float,
    ) -> bool:
        x, y = location
        template_height, template_width = template.shape[:2]
        region_of_interest = screenshot[y : y + template_height, x : x + template_width]

        if region_of_interest.shape[:2] != template.shape[:2]:
            return False

        if mask is None:
            active_mask = np.ones((template_height, template_width), dtype=bool)
        else:
            active_mask = mask > 0

        active_count = int(np.count_nonzero(active_mask))
        if active_count <= 0:
            return False

        if not hsv_ranges:
            return False

        try:
            hsv_region = cv2.cvtColor(region_of_interest, cv2.COLOR_BGR2HSV)
        except cv2.error as exc:
            logger.debug("HSV gate conversion failed: %s", exc)
            return False

        combined = np.zeros((template_height, template_width), dtype=np.uint8)
        for lower, upper in hsv_ranges:
            combined = cv2.bitwise_or(combined, self._apply_hsv_range_mask(hsv_region, lower, upper))

        matched_count = int(np.count_nonzero((combined > 0) & active_mask))
        match_ratio = matched_count / active_count
        return match_ratio >= hsv_match_threshold
    
    def find_all_templates(
        self,
        screenshot: np.ndarray,
        template: np.ndarray,
        mask: np.ndarray | None = None,
        threshold: float | None = None,
        min_distance: int = 15,
        scales: list[float] | None = None,
        template_name: str = "Unknown",
        hsv_ranges: Any = None,
        hsv_match_threshold: float = 0.9,
    ) -> list[tuple[float, int, int]]:
        all_matches = self.find_template_candidates(
            screenshot,
            template,
            mask=mask,
            threshold=threshold,
            min_distance=min_distance,
            scales=scales,
            template_name=template_name,
            hsv_ranges=hsv_ranges,
            hsv_match_threshold=hsv_match_threshold,
        )
        if all_matches:
            all_matches = self._non_max_suppression(all_matches, min_distance)
        return [(conf, x, y) for conf, x, y, _, _ in all_matches]

    @staticmethod
    def _scaled_template_and_mask(
        template: np.ndarray,
        mask: np.ndarray | None,
        scale: float,
    ) -> tuple[np.ndarray, np.ndarray | None]:
        if scale == 1.0:
            return template, mask
        scaled_template = cv2.resize(template, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        if mask is None:
            return scaled_template, None
        scaled_mask = cv2.resize(mask, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
        scaled_mask[scaled_mask > 0] = 255
        return scaled_template, scaled_mask

    @staticmethod
    def _valid_scale(scale: Any) -> float | None:
        try:
            normalized_scale = float(scale)
        except (TypeError, ValueError):
            return None
        if not np.isfinite(normalized_scale) or normalized_scale <= 0:
            return None
        return normalized_scale

    @staticmethod
    def _scaled_template_fits(screenshot: np.ndarray, template: np.ndarray, scale: float) -> bool:
        scaled_width = float(template.shape[1]) * scale
        scaled_height = float(template.shape[0]) * scale
        return bool(
            np.isfinite(scaled_width)
            and np.isfinite(scaled_height)
            and 1.0 <= scaled_width <= screenshot.shape[1]
            and 1.0 <= scaled_height <= screenshot.shape[0]
        )

    @staticmethod
    def _normalize_min_distance(value: Any) -> int:
        try:
            return max(0, int(value))
        except (TypeError, ValueError, OverflowError):
            return 0

    def find_template_candidates(
        self,
        screenshot: np.ndarray,
        template: np.ndarray,
        mask: np.ndarray | None = None,
        threshold: float | None = None,
        min_distance: int = 15,
        scales: list[float] | None = None,
        template_name: str = "Unknown",
        hsv_ranges: Any = None,
        hsv_match_threshold: float = 0.9,
    ) -> list[MatchCandidate]:
        thresh = self.threshold if threshold is None else self._normalize_threshold(threshold, self.threshold)
        all_matches: list[MatchCandidate] = []
        try:
            screenshot = self._normalize_image(screenshot, "screenshot")
            template = self._normalize_image(template, template_name)
        except ValueError as exc:
            logger.warning("[%s] Invalid multi-match input: %s", template_name, exc)
            return []
        mask = self._normalize_mask(mask, template.shape, template_name)
        normalized_hsv_ranges = self._normalize_hsv_ranges(hsv_ranges) if hsv_ranges is not None else None
        normalized_hsv_threshold = self._normalize_threshold(hsv_match_threshold, 0.9)

        if scales is None:
            scales = [1.0]
        try:
            scale_values = iter(scales)
        except TypeError:
            logger.warning("[%s] Scales must be iterable", template_name)
            return []

        for scale_value in islice(scale_values, MAX_TEMPLATE_SCALES):
            scale = self._valid_scale(scale_value)
            if scale is None:
                continue
            if not self._scaled_template_fits(screenshot, template, scale):
                continue
            try:
                scaled_template, scaled_mask = self._scaled_template_and_mask(template, mask, scale)
            except cv2.error as exc:
                logger.warning("[%s] Template resize failed at scale %s: %s", template_name, scale, exc)
                continue

            result = self._safe_match_template(screenshot, scaled_template, scaled_mask, template_name)
            if result is None:
                continue

            template_height, template_width = scaled_template.shape[:2]
            candidates = self._local_minima_candidates(result, 1.0 - thresh, min_distance)
            for candidate_x, candidate_y in candidates:
                confidence = float(1.0 - result[candidate_y, candidate_x])
                if not np.isfinite(confidence):
                    continue
                if normalized_hsv_ranges is not None and not self._check_hsv_gate(
                    screenshot,
                    scaled_template,
                    (candidate_x, candidate_y),
                    scaled_mask,
                    normalized_hsv_ranges,
                    normalized_hsv_threshold,
                ):
                    continue
                center_x = candidate_x + template_width // 2
                center_y = candidate_y + template_height // 2
                all_matches.append((confidence, center_x, center_y, template_width, template_height))

        return sorted(all_matches, key=lambda match: match[0], reverse=True)

    @staticmethod
    def _local_minima_candidates(result: np.ndarray | None, max_score: float, min_distance: int) -> list[Point]:
        if result is None or result.size == 0 or result.ndim != 2:
            return []
        try:
            normalized_max_score = float(max_score)
        except (TypeError, ValueError, OverflowError):
            return []
        if not np.isfinite(normalized_max_score):
            return []
        maximum_window = max(3, min(int(result.shape[0]), int(result.shape[1])))
        window = min(maximum_window, max(3, ImageMatcher._normalize_min_distance(min_distance)))
        if window % 2 == 0:
            window = max(3, window - 1)
        kernel = np.ones((window, window), dtype=np.float32)
        local_min = cv2.erode(result, kernel)
        candidate_mask = (result <= normalized_max_score) & (result <= local_min + 1e-6)
        if not np.any(candidate_mask):
            return []
        mask = candidate_mask.astype(np.uint8)
        count, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        candidates = []
        for index in range(1, count):
            component_x, component_y, component_width, component_height, component_area = stats[index]
            if component_area <= 0:
                continue
            region = result[
                component_y : component_y + component_height,
                component_x : component_x + component_width,
            ]
            min_value, _, min_location, _ = cv2.minMaxLoc(region)
            if min_value <= normalized_max_score:
                candidates.append((int(component_x + min_location[0]), int(component_y + min_location[1])))
        return candidates

    @staticmethod
    def _box_intersection_over_union(first_match: MatchCandidate, second_match: MatchCandidate) -> float:
        _, raw_first_x, raw_first_y, raw_first_width, raw_first_height = first_match
        _, raw_second_x, raw_second_y, raw_second_width, raw_second_height = second_match
        values = tuple(
            float(value)
            for value in (
                raw_first_x,
                raw_first_y,
                raw_first_width,
                raw_first_height,
                raw_second_x,
                raw_second_y,
                raw_second_width,
                raw_second_height,
            )
        )
        if not all(np.isfinite(value) for value in values):
            return 0.0
        first_center_x, first_center_y, first_width, first_height = values[:4]
        second_center_x, second_center_y, second_width, second_height = values[4:]
        first_width = max(0.0, first_width)
        first_height = max(0.0, first_height)
        second_width = max(0.0, second_width)
        second_height = max(0.0, second_height)
        left = max(first_center_x - first_width / 2.0, second_center_x - second_width / 2.0)
        top = max(first_center_y - first_height / 2.0, second_center_y - second_height / 2.0)
        right = min(first_center_x + first_width / 2.0, second_center_x + second_width / 2.0)
        bottom = min(first_center_y + first_height / 2.0, second_center_y + second_height / 2.0)
        if right <= left or bottom <= top:
            return 0.0
        intersection = (right - left) * (bottom - top)
        first_area = first_width * first_height
        second_area = second_width * second_height
        union = first_area + second_area - intersection
        return intersection / union if union > 0 else 0.0

    @classmethod
    def _overlaps_existing_match(
        cls: type["ImageMatcher"],
        candidate_match: MatchCandidate,
        filtered_match: MatchCandidate,
        min_distance: int,
    ) -> bool:
        _, candidate_x, candidate_y, _, _ = candidate_match
        _, filtered_x, filtered_y, _, _ = filtered_match
        if abs(candidate_x - filtered_x) >= min_distance or abs(candidate_y - filtered_y) >= min_distance:
            return False
        return cls._box_intersection_over_union(candidate_match, filtered_match) > 0.2

    def _non_max_suppression(self, matches: list[MatchCandidate], min_distance: int) -> list[MatchCandidate]:
        if not matches:
            return []

        min_distance = self._normalize_min_distance(min_distance)
        matches = sorted(matches, key=lambda match: match[0], reverse=True)
        filtered: list[MatchCandidate] = []

        for candidate_match in matches:
            if not any(
                self._overlaps_existing_match(candidate_match, filtered_match, min_distance)
                for filtered_match in filtered
            ):
                filtered.append(candidate_match)

        return filtered
