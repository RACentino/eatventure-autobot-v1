import cv2
import numpy as np
import logging
import os
import config

logger = logging.getLogger(__name__)


class ImageMatcher:
    def __init__(self, threshold=0.85):
        self.threshold = threshold
        cv2.setUseOptimized(True)
        # Limit to 1 thread to prevent CPU starvation between monitor and worker threads
        cv2.setNumThreads(1)

    def is_red_dominant(self, image, x, y, size=12, min_ratio=1.15, min_mean=35):
        # ... existing logic ...
        half = max(1, size // 2)
        x1 = max(0, x - half)
        y1 = max(0, y - half)
        x2 = min(image.shape[1], x + half)
        y2 = min(image.shape[0], y + half)

        roi = image[y1:y2, x1:x2]
        if roi.size == 0:
            return True

        b, g, r, _ = cv2.mean(roi)
        if r < min_mean:
            return False

        dominant_ratio = max(g, b) + 1e-6
        return (r / dominant_ratio) >= min_ratio

    def count_red_pixels(self, image, x, y, size=24, show_mask=False):
        """
        Counts red pixels in a ROI using HSV masking and dilation.
        Requirement: Morphological Dilation & Pixel Density Trigger.
        """
        half = max(1, size // 2)
        x1 = max(0, x - half)
        y1 = max(0, y - half)
        x2 = min(image.shape[1], x + half)
        y2 = min(image.shape[0], y + half)

        roi = image[y1:y2, x1:x2]
        if roi.size == 0:
            return 0

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # Apply HSV mask for red (handles both ends of hue scale)
        mask1 = cv2.inRange(hsv, np.array(config.RED_HSV_LOWER1), np.array(config.RED_HSV_UPPER1))
        mask2 = cv2.inRange(hsv, np.array(config.RED_HSV_LOWER2), np.array(config.RED_HSV_UPPER2))
        mask = cv2.bitwise_or(mask1, mask2)

        # Requirement: Apply Morphological Dilation to connect/inflate red pixels
        kernel_size = getattr(config, "RED_ICON_DILATE_KERNEL", 3)
        kernel = np.ones((kernel_size, kernel_size), np.uint8)
        dilated = cv2.dilate(mask, kernel, iterations=1)

        # Requirement: Count total red pixels (pixel density)
        count = cv2.countNonZero(dilated)

        if show_mask:
            debug_roi = cv2.resize(dilated, (200, 200), interpolation=cv2.INTER_NEAREST)
            cv2.imshow("Red Icon Mask (Debug)", debug_roi)
            cv2.waitKey(1)

        return count
    
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
        
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        
        confidence = 1 - min_val
        
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
    
    def _check_color_similarity(self, screenshot, template, location, mask=None):
        x, y = location
        h, w = template.shape[:2]
        
        roi = screenshot[y:y+h, x:x+w]
        
        if roi.shape[:2] != template.shape[:2]:
            return True
        
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
        
        avg_corr = (corr_b + corr_g + corr_r) / 3
        
        color_threshold = 0.7
        return avg_corr >= color_threshold
    
    def find_all_templates(self, screenshot, template, mask=None, threshold=None, min_distance=15, scales=None, template_name="Unknown"):
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

            fast_matches = self._find_sqdiff_matches(
                result,
                threshold=thresh,
                min_distance=min_distance,
            )

            h, w = scaled_template.shape[:2]
            for confidence, match_x, match_y in fast_matches:
                center_x, center_y = self._match_top_left_to_center(match_x, match_y, w, h)
                all_matches.append((confidence, center_x, center_y, w, h))
        
        if all_matches:
            all_matches = self._non_max_suppression(all_matches, min_distance)
        
        return [(conf, x, y) for conf, x, y, _, _ in all_matches]

    def _find_sqdiff_matches(self, result, threshold, min_distance):
        if result.size == 0:
            return []

        max_error = 1 - threshold
        if max_error < 0:
            return []

        suppression = max(1, int(min_distance))
        working = result.copy()
        height, width = working.shape[:2]
        matches = []

        while True:
            min_val, _, min_loc, _ = cv2.minMaxLoc(working)
            if min_val > max_error:
                break

            x, y = min_loc
            matches.append((1 - min_val, x, y))

            x1 = max(0, x - suppression)
            x2 = min(width, x + suppression + 1)
            y1 = max(0, y - suppression)
            y2 = min(height, y + suppression + 1)
            working[y1:y2, x1:x2] = 1.0

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
