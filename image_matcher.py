import cv2
import numpy as np
import logging

logger = logging.getLogger(__name__)


class ImageMatcher:
    def __init__(self, threshold=0.85):
        self.threshold = self._normalize_threshold(threshold)

    @staticmethod
    def _normalize_threshold(value):
        try:
            threshold = float(value)
        except (TypeError, ValueError):
            return 0.85
        if not np.isfinite(threshold):
            return 0.85
        return max(0.0, min(1.0, threshold))

    @staticmethod
    def _normalize_image(image, label):
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
    def _normalize_mask(mask, template_shape, template_name):
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
        normalized = np.zeros(mask.shape[:2], dtype=np.uint8)
        normalized[mask > 0] = 255
        if not np.any(normalized):
            logger.warning("[%s] Ignoring mask without active pixels", template_name)
            return None
        return normalized

    @staticmethod
    def _safe_match_template(screenshot, template, mask, template_name):
        try:
            result = cv2.matchTemplate(screenshot, template, cv2.TM_SQDIFF_NORMED, mask=mask)
        except cv2.error as exc:
            logger.warning("[%s] Template matching failed: %s", template_name, exc)
            return None
        if result.size == 0:
            return None
        result = np.nan_to_num(result, nan=1.0, posinf=1.0, neginf=1.0)
        return np.clip(result, 0.0, 1.0)
    
    def load_template(self, template_path):
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
        screenshot,
        template,
        mask=None,
        threshold=None,
        template_name="Unknown",
        check_color=False,
        color_threshold=0.7,
    ):
        thresh = self.threshold if threshold is None else self._normalize_threshold(threshold)
        try:
            screenshot = self._normalize_image(screenshot, "screenshot")
            template = self._normalize_image(template, template_name)
        except ValueError as exc:
            logger.warning("[%s] Invalid match input: %s", template_name, exc)
            return False, 0.0, 0, 0
        mask = self._normalize_mask(mask, template.shape, template_name)

        if template.shape[0] > screenshot.shape[0] or template.shape[1] > screenshot.shape[1]:
            logger.debug(f"Template is larger than screenshot. Template: {template.shape}, Screenshot: {screenshot.shape}")
            return False, 0.0, 0, 0

        result = self._safe_match_template(screenshot, template, mask, template_name)
        if result is None:
            return False, 0.0, 0, 0

        min_val, _, min_loc, _ = cv2.minMaxLoc(result)
        confidence = float(1.0 - min_val)
        if not np.isfinite(confidence):
            return False, 0.0, 0, 0
        
        if confidence >= thresh:
            h, w = template.shape[:2]
            center_x = min_loc[0] + w // 2
            center_y = min_loc[1] + h // 2
            
            if check_color:
                color_match = self._check_color_similarity(
                    screenshot,
                    template,
                    min_loc,
                    mask,
                    color_threshold=color_threshold,
                )
                if not color_match:
                    logger.debug(f"[{template_name}] Color check failed at ({center_x}, {center_y}), confidence: {confidence:.2%}")
                    return False, confidence, 0, 0
            
            return True, confidence, center_x, center_y
        
        return False, confidence, 0, 0
    
    def _check_color_similarity(self, screenshot, template, location, mask=None, color_threshold=0.7):
        x, y = location
        h, w = template.shape[:2]
        
        roi = screenshot[y:y+h, x:x+w]
        
        if roi.shape[:2] != template.shape[:2]:
            return False

        if mask is not None and not np.any(mask):
            return False

        try:
            hist_template_b = cv2.calcHist([template], [0], mask, [32], [0, 256])
            hist_template_g = cv2.calcHist([template], [1], mask, [32], [0, 256])
            hist_template_r = cv2.calcHist([template], [2], mask, [32], [0, 256])

            hist_roi_b = cv2.calcHist([roi], [0], mask, [32], [0, 256])
            hist_roi_g = cv2.calcHist([roi], [1], mask, [32], [0, 256])
            hist_roi_r = cv2.calcHist([roi], [2], mask, [32], [0, 256])

            histograms = (
                hist_template_b,
                hist_template_g,
                hist_template_r,
                hist_roi_b,
                hist_roi_g,
                hist_roi_r,
            )
            if any(not np.any(hist) for hist in histograms):
                return False

            for hist in histograms:
                cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)

            corr_b = cv2.compareHist(hist_template_b, hist_roi_b, cv2.HISTCMP_CORREL)
            corr_g = cv2.compareHist(hist_template_g, hist_roi_g, cv2.HISTCMP_CORREL)
            corr_r = cv2.compareHist(hist_template_r, hist_roi_r, cv2.HISTCMP_CORREL)
        except cv2.error as exc:
            logger.debug("Color similarity check failed: %s", exc)
            return False
        
        correlations = (corr_b, corr_g, corr_r)
        if not all(np.isfinite(value) for value in correlations):
            return False

        avg_corr = sum(correlations) / 3
        return avg_corr >= self._normalize_threshold(color_threshold)
    
    def find_all_templates(self, screenshot, template, mask=None, threshold=None, min_distance=15, scales=None, template_name="Unknown"):
        thresh = self.threshold if threshold is None else self._normalize_threshold(threshold)
        all_matches = []
        try:
            screenshot = self._normalize_image(screenshot, "screenshot")
            template = self._normalize_image(template, template_name)
        except ValueError as exc:
            logger.warning("[%s] Invalid multi-match input: %s", template_name, exc)
            return []
        mask = self._normalize_mask(mask, template.shape, template_name)

        if scales is None:
            scales = [1.0]
        
        for scale in scales:
            try:
                scale = float(scale)
            except (TypeError, ValueError):
                continue
            if not np.isfinite(scale) or scale <= 0:
                continue
            if scale != 1.0:
                scaled_template = cv2.resize(template, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
                scaled_mask = None
                if mask is not None:
                    scaled_mask = cv2.resize(mask, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
                    scaled_mask[scaled_mask > 0] = 255
            else:
                scaled_template = template
                scaled_mask = mask
            
            if scaled_template.shape[0] > screenshot.shape[0] or scaled_template.shape[1] > screenshot.shape[1]:
                continue
            
            result = self._safe_match_template(screenshot, scaled_template, scaled_mask, template_name)
            if result is None:
                continue
            
            locations = np.where(result <= (1 - thresh))
            
            h, w = scaled_template.shape[:2]
            for pt in zip(*locations[::-1]):
                confidence = float(1.0 - result[pt[1], pt[0]])
                if not np.isfinite(confidence):
                    continue
                center_x = pt[0] + w // 2
                center_y = pt[1] + h // 2
                all_matches.append((confidence, center_x, center_y, w, h))
        
        if all_matches:
            all_matches = self._non_max_suppression(all_matches, min_distance)
        
        return [(conf, x, y) for conf, x, y, _, _ in all_matches]
    
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
