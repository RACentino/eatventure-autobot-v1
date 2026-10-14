import logging
import time
from collections.abc import Iterable
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

MatchResult = tuple[bool, float, int, int]
MatchCandidate = tuple[float, int, int, int, int]
Point = tuple[int, int]
HsvRange = tuple[np.ndarray, np.ndarray]
# (template_name, confidence, center, hsv_ratio) - hsv_ratio is None when no gate was given or it
# could not be measured. Diagnostics only; see ImageMatcher.explain_template.
TemplateExplanation = tuple[str, float, Point, float | None]
# explain_template_detailed adds the median (H, S, V) of the matched pixels, so a miss can be judged in
# numbers instead of images. Diagnostics only.
TemplateExplanationDetailed = tuple[str, float, Point, float | None, tuple[int, int, int] | None]
# A multi-template candidate: (confidence, center_x, center_y, width, height, template_name).
NamedCandidate = tuple[float, int, int, int, int, str]


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
        started_at = time.perf_counter() if logger.isEnabledFor(logging.DEBUG) else None
        try:
            result = cv2.matchTemplate(screenshot, template, cv2.TM_SQDIFF_NORMED, mask=match_mask)
        except cv2.error as exc:
            logger.warning("[%s] Template matching failed: %s", template_name, exc)
            return None
        finally:
            if started_at is not None:
                logger.debug("[%s] matchTemplate %.2fms", template_name, (time.perf_counter() - started_at) * 1000)
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
        hsv_frame: np.ndarray | None = None,
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

        if hsv_frame is not None:
            # The caller converted the whole frame to HSV once and shares it across templates;
            # slicing it is identical to converting this region (the conversion is per pixel).
            hsv_region = hsv_frame[y : y + template_height, x : x + template_width]
        else:
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

    def _hsv_match_ratio(
        self,
        screenshot: np.ndarray,
        template: np.ndarray,
        location: Point,
        mask: np.ndarray | None,
        hsv_ranges: list[HsvRange],
    ) -> float | None:
        """Share of the template's active pixels whose colour is inside hsv_ranges at `location`;
        None when it can't be measured (window falls off the frame, conversion failed, no active
        pixels, or no ranges given). Diagnostics only (explain_template); never used to decide a
        click - _check_hsv_gate is the click-path gate and is untouched by this method."""
        x, y = location
        template_height, template_width = template.shape[:2]
        region_of_interest = screenshot[y : y + template_height, x : x + template_width]
        if region_of_interest.shape[:2] != template.shape[:2]:
            return None

        active_mask = np.ones((template_height, template_width), dtype=bool) if mask is None else mask > 0
        active_count = int(np.count_nonzero(active_mask))
        if active_count <= 0 or not hsv_ranges:
            return None

        try:
            hsv_region = cv2.cvtColor(region_of_interest, cv2.COLOR_BGR2HSV)
        except cv2.error as exc:
            logger.debug("HSV ratio conversion failed: %s", exc)
            return None

        combined = np.zeros((template_height, template_width), dtype=np.uint8)
        for lower, upper in hsv_ranges:
            combined = cv2.bitwise_or(combined, self._apply_hsv_range_mask(hsv_region, lower, upper))

        matched_count = int(np.count_nonzero((combined > 0) & active_mask))
        return matched_count / active_count

    @staticmethod
    def _hsv_median(
        screenshot: np.ndarray,
        template: np.ndarray,
        location: Point,
        mask: np.ndarray | None,
    ) -> tuple[int, int, int] | None:
        """Median (H, S, V) of the template's visible pixels at `location`; None when the window
        falls off the frame, has no visible pixels or cannot be converted. Diagnostics only."""
        x, y = location
        template_height, template_width = template.shape[:2]
        region_of_interest = screenshot[y : y + template_height, x : x + template_width]
        if region_of_interest.shape[:2] != template.shape[:2]:
            return None
        active_mask = np.ones((template_height, template_width), dtype=bool) if mask is None else mask > 0
        if not active_mask.any():
            return None
        try:
            hsv_region = cv2.cvtColor(region_of_interest, cv2.COLOR_BGR2HSV)
        except cv2.error as exc:
            logger.debug("HSV median conversion failed: %s", exc)
            return None
        hue, saturation, value = (int(np.median(hsv_region[:, :, channel][active_mask])) for channel in range(3))
        return hue, saturation, value

    def explain_template(
        self,
        screenshot: np.ndarray,
        template: np.ndarray,
        mask: np.ndarray | None = None,
        template_name: str = "Unknown",
        hsv_ranges: Any = None,
    ) -> TemplateExplanation | None:
        """The single best raw match of a template with no threshold or gate applied, plus how
        much of it sits inside hsv_ranges - what the detector saw when it reported no match.
        Diagnostics only (the stall probe); never used to decide a click."""
        detailed = self.explain_template_detailed(screenshot, template, mask, template_name, hsv_ranges)
        return None if detailed is None else detailed[:4]

    def explain_template_detailed(
        self,
        screenshot: np.ndarray,
        template: np.ndarray,
        mask: np.ndarray | None = None,
        template_name: str = "Unknown",
        hsv_ranges: Any = None,
    ) -> TemplateExplanationDetailed | None:
        """explain_template plus the median (H, S, V) of the matched pixels, so the HSV gate can be
        judged in numbers. Diagnostics only (the stall probes); never used to decide a click."""
        try:
            screenshot = self._normalize_image(screenshot, "screenshot")
            template = self._normalize_image(template, template_name)
        except ValueError as exc:
            logger.warning("[%s] Invalid explain input: %s", template_name, exc)
            return None
        mask = self._normalize_mask(mask, template.shape, template_name)
        if not self._template_fits_screenshot(screenshot, template, template_name):
            return None

        result = self._safe_match_template(screenshot, template, mask, template_name)
        if result is None:
            return None

        min_value, _, min_location, _ = cv2.minMaxLoc(result)
        confidence = float(1.0 - min_value)
        if not np.isfinite(confidence):
            return None

        normalized_hsv_ranges = self._normalize_hsv_ranges(hsv_ranges) if hsv_ranges is not None else None
        ratio = (
            None
            if normalized_hsv_ranges is None
            else self._hsv_match_ratio(screenshot, template, min_location, mask, normalized_hsv_ranges)
        )
        center_x, center_y = self._center_from_location(min_location, template)
        median = self._hsv_median(screenshot, template, min_location, mask)
        return template_name, confidence, (center_x, center_y), ratio, median

    def find_all_templates(
        self,
        screenshot: np.ndarray,
        template: np.ndarray,
        mask: np.ndarray | None = None,
        threshold: float | None = None,
        min_distance: int = 15,
        template_name: str = "Unknown",
        hsv_ranges: Any = None,
        hsv_match_threshold: float = 0.9,
        nms_iou_threshold: float = 0.20,
    ) -> list[tuple[float, int, int]]:
        all_matches = self.find_template_candidates(
            screenshot,
            template,
            mask=mask,
            threshold=threshold,
            min_distance=min_distance,
            template_name=template_name,
            hsv_ranges=hsv_ranges,
            hsv_match_threshold=hsv_match_threshold,
        )
        if all_matches:
            all_matches = self.suppress_overlaps(all_matches, nms_iou_threshold)
        return [(conf, x, y) for conf, x, y, _, _ in all_matches]

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
        template_name: str = "Unknown",
        hsv_ranges: Any = None,
        hsv_match_threshold: float = 0.9,
        hsv_frame: np.ndarray | None = None,
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
        if not self._template_fits_screenshot(screenshot, template, template_name):
            return []

        result = self._safe_match_template(screenshot, template, mask, template_name)
        if result is None:
            return []
        template_height, template_width = template.shape[:2]
        for candidate_x, candidate_y in self._local_minima_candidates(result, 1.0 - thresh, min_distance):
            confidence = float(1.0 - result[candidate_y, candidate_x])
            if not np.isfinite(confidence):
                continue
            if normalized_hsv_ranges is not None and not self._check_hsv_gate(
                screenshot,
                template,
                (candidate_x, candidate_y),
                mask,
                normalized_hsv_ranges,
                normalized_hsv_threshold,
                hsv_frame=hsv_frame,
            ):
                continue
            all_matches.append(
                (
                    confidence,
                    candidate_x + template_width // 2,
                    candidate_y + template_height // 2,
                    template_width,
                    template_height,
                )
            )

        return sorted(all_matches, key=lambda match: match[0], reverse=True)

    def find_candidates_across_templates(
        self,
        screenshot: np.ndarray,
        templates: Iterable[tuple[str, np.ndarray, np.ndarray | None]],
        threshold: float | None = None,
        min_distance: int = 15,
        hsv_ranges: Any = None,
        hsv_match_threshold: float = 0.9,
    ) -> list[NamedCandidate]:
        """Candidates of several (name, template, mask) templates over ONE frame. The frame is
        converted to HSV at most once (only when hsv_ranges is given) and shared by every template's
        gate instead of each candidate re-converting its own region. Each result carries its
        template name so a later step can ask how many distinct templates agree on a spot."""
        try:
            frame = self._normalize_image(screenshot, "screenshot")
        except ValueError as exc:
            logger.warning("Invalid multi-template input: %s", exc)
            return []
        hsv_frame = None
        if hsv_ranges is not None:
            try:
                hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            except cv2.error as exc:
                logger.debug("Shared HSV conversion failed; gating per candidate instead: %s", exc)
        named: list[NamedCandidate] = []
        for template_name, template, mask in templates:
            for confidence, x, y, width, height in self.find_template_candidates(
                frame,
                template,
                mask=mask,
                threshold=threshold,
                min_distance=min_distance,
                template_name=template_name,
                hsv_ranges=hsv_ranges,
                hsv_match_threshold=hsv_match_threshold,
                hsv_frame=hsv_frame,
            ):
                named.append((confidence, x, y, width, height, template_name))
        return named

    @classmethod
    def filter_by_template_consensus(
        cls,
        candidates: list[NamedCandidate],
        min_matches: int,
        iou_threshold: float = 0.20,
    ) -> list[NamedCandidate]:
        """Keeps only spots where at least `min_matches` DISTINCT templates agree, returning the
        highest-confidence candidate of each surviving cluster. Candidates cluster when their boxes
        overlap by more than `iou_threshold`. It suppresses a spot that only one template variant
        happens to like. With min_matches <= 1 nothing is clustered: just confidence order."""
        ordered = sorted(candidates, key=lambda candidate: candidate[0], reverse=True)
        if min_matches <= 1:
            return ordered
        threshold = cls._normalize_threshold(iou_threshold, 0.20)
        clusters: list[list[NamedCandidate]] = []
        for candidate in ordered:
            for cluster in clusters:
                if cls._box_intersection_over_union(cluster[0], candidate) > threshold:
                    cluster.append(candidate)
                    break
            else:
                clusters.append([candidate])
        return [cluster[0] for cluster in clusters if len({member[5] for member in cluster}) >= min_matches]

    @classmethod
    def red_block_area(
        cls,
        screenshot: np.ndarray,
        hsv_ranges: Any,
        window: int,
        min_fraction: float,
    ) -> tuple[int, int, int, int] | None:
        """Bounding area (left, top, right, bottom) around every solid block of colour at least
        `window` pixels across, or None when the frame has none. A cheap gate (a box filter over a
        colour mask, a few ms) in front of the far costlier masked template match: only a frame
        that holds such a block, and only the area around it, is handed on to the match."""
        try:
            frame = cls._normalize_image(screenshot, "screenshot")
        except ValueError:
            return None
        normalized_ranges = cls._normalize_hsv_ranges(hsv_ranges)
        if not normalized_ranges:
            return None
        window = max(3, int(window))
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        coloured = np.zeros(frame.shape[:2], dtype=np.uint8)
        for lower, upper in normalized_ranges:
            coloured = cv2.bitwise_or(coloured, cls._apply_hsv_range_mask(hsv, lower, upper))
        share = cv2.boxFilter(
            (coloured > 0).astype(np.float32),
            -1,
            (window, window),
            normalize=True,
            borderType=cv2.BORDER_CONSTANT,
        )
        rows, cols = np.where(share >= min_fraction)
        if rows.size == 0:
            return None
        reach = window // 2 + window // 2 + 6  # block centre -> far edge of a template placed on it
        height, width = frame.shape[:2]
        return (
            max(0, int(cols.min()) - reach),
            max(0, int(rows.min()) - reach),
            min(width, int(cols.max()) + reach),
            min(height, int(rows.max()) + reach),
        )

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
        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        candidates = []
        for index in range(1, count):
            component_x, component_y, component_width, component_height, component_area = stats[index]
            if component_area <= 0:
                continue
            region = result[
                component_y : component_y + component_height,
                component_x : component_x + component_width,
            ]
            # Two components can have overlapping bounding rectangles even when their pixels are
            # disjoint (non-convex shapes). Take the minimum over this component's own labelled
            # pixels so a neighbour's lower score is never attributed to the wrong candidate.
            label_region = labels[
                component_y : component_y + component_height,
                component_x : component_x + component_width,
            ]
            region = np.where(label_region == index, region, 1.0).astype(np.float32)
            min_value, _, min_location, _ = cv2.minMaxLoc(region)
            if min_value <= normalized_max_score:
                candidates.append((int(component_x + min_location[0]), int(component_y + min_location[1])))
        return candidates

    @staticmethod
    def _box_intersection_over_union(first_match: tuple[Any, ...], second_match: tuple[Any, ...]) -> float:
        _, raw_first_x, raw_first_y, raw_first_width, raw_first_height = first_match[:5]
        _, raw_second_x, raw_second_y, raw_second_width, raw_second_height = second_match[:5]
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
        # Boxes are (x, y, x + w, y + h) with x = centre - w // 2 (a candidate's centre is x + w // 2), the
        # integer boxes v2 uses. Centre +/- w / 2 shifts odd-sized templates by half a pixel, which flips
        # the keep/drop decision for a small share of near-threshold overlaps between different sizes.
        first_left, first_top = first_center_x - first_width // 2, first_center_y - first_height // 2
        second_left, second_top = second_center_x - second_width // 2, second_center_y - second_height // 2
        left = max(first_left, second_left)
        top = max(first_top, second_top)
        right = min(first_left + first_width, second_left + second_width)
        bottom = min(first_top + first_height, second_top + second_height)
        if right <= left or bottom <= top:
            return 0.0
        intersection = (right - left) * (bottom - top)
        first_area = first_width * first_height
        second_area = second_width * second_height
        union = first_area + second_area - intersection
        return intersection / union if union > 0 else 0.0

    @classmethod
    def suppress_overlaps(cls, matches: list[Any], iou_threshold: float = 0.20) -> list[Any]:
        """Non-maximum suppression by overlap alone (IoU): the higher-confidence match wins. v1 used
        to skip the overlap test unless both axes were within a min_distance, which kept large,
        heavily overlapping templates (the upgrade station) as near-duplicates; v2 does not."""
        if not matches:
            return []
        iou_threshold = cls._normalize_threshold(iou_threshold, 0.20)
        matches = sorted(matches, key=lambda match: match[0], reverse=True)
        filtered: list[Any] = []

        for candidate in matches:
            if not any(cls._box_intersection_over_union(candidate, existing) > iou_threshold for existing in filtered):
                filtered.append(candidate)

        return filtered
