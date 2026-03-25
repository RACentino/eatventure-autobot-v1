"""
Validate HSV color gates against the bot's asset images.

Reads each PNG in Assets/, applies the HSV masks defined in config.py,
and verifies that every genuine asset passes its respective gate.

Usage:
    python tools/validate_hsv_gates.py
"""
import cv2
import numpy as np
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Assets")


def load_opaque(path):
    """Load image and return BGR + boolean mask of opaque pixels."""
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
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
    """Test if a red icon asset passes the red HSV gate."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    
    lower1 = np.array(config.RED_HSV_LOWER1)
    upper1 = np.array(config.RED_HSV_UPPER1)
    lower2 = np.array(config.RED_HSV_LOWER2)
    upper2 = np.array(config.RED_HSV_UPPER2)
    
    mask1 = cv2.inRange(hsv, lower1, upper1)
    mask2 = cv2.inRange(hsv, lower2, upper2)
    combined = cv2.bitwise_or(mask1, mask2)
    
    # Only count opaque pixels
    opaque_uint8 = opaque_mask.astype(np.uint8) * 255
    combined = cv2.bitwise_and(combined, opaque_uint8)
    
    red_count = cv2.countNonZero(combined)
    total_opaque = int(np.sum(opaque_mask))
    ratio = red_count / total_opaque if total_opaque > 0 else 0
    
    # The gate requires RED_ICON_PIXEL_THRESHOLD pixels from config.py.
    threshold = getattr(config, "RED_ICON_PIXEL_THRESHOLD", 48)
    
    return {
        "red_pixels": red_count,
        "total_opaque": total_opaque,
        "ratio": ratio,
        "passes_threshold": red_count >= threshold,
        "threshold": threshold,
    }


def test_upgrade_station_gate(bgr, opaque_mask):
    """Test if an upgrade station asset passes the HSV gate."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    
    lower = np.array(getattr(config, "UPGRADE_STATION_HSV_LOWER", (80, 40, 180)))
    upper = np.array(getattr(config, "UPGRADE_STATION_HSV_UPPER", (110, 210, 255)))
    
    mask = cv2.inRange(hsv, lower, upper)
    
    # Only count opaque pixels
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


def main():
    print("=" * 70)
    print("HSV COLOR GATE VALIDATION")
    print(f"Assets directory: {ASSETS_DIR}")
    print("=" * 70)
    
    # Show current config values
    print(f"\nRed Icon HSV Config:")
    print(f"  Band 1: {config.RED_HSV_LOWER1} - {config.RED_HSV_UPPER1}")
    print(f"  Band 2: {config.RED_HSV_LOWER2} - {config.RED_HSV_UPPER2}")
    print(f"  Pixel Threshold: {config.RED_ICON_PIXEL_THRESHOLD}")
    
    print(f"\nUpgrade Station HSV Config:")
    print(f"  Range: {config.UPGRADE_STATION_HSV_LOWER} - {config.UPGRADE_STATION_HSV_UPPER}")
    print(f"  Min Ratio: {config.UPGRADE_STATION_HSV_MIN_RATIO}")
    
    passed = 0
    failed = 0
    total = 0
    
    # Test red icons
    print(f"\n{'-' * 70}")
    print("RED ICON ASSETS")
    print(f"{'-' * 70}")
    
    for fname in sorted(os.listdir(ASSETS_DIR)):
        if not fname.lower().startswith("redicon") or not fname.lower().endswith(".png"):
            continue
        
        path = os.path.join(ASSETS_DIR, fname)
        bgr, opaque_mask = load_opaque(path)
        if bgr is None:
            print(f"  SKIP {fname} (could not load)")
            continue
        
        total += 1
        result = test_red_icon_gate(bgr, opaque_mask)
        status = "PASS" if result["passes_threshold"] else "FAIL"
        if result["passes_threshold"]:
            passed += 1
        else:
            failed += 1
        
        print(f"  [{status}] {fname:25s}  red_px={result['red_pixels']:4d}/{result['total_opaque']:4d}  "
              f"ratio={result['ratio']:.1%}  (threshold={result['threshold']})")
    
    # Test upgrade station
    print(f"\n{'-' * 70}")
    print("UPGRADE STATION ASSETS")
    print(f"{'-' * 70}")
    
    for fname in sorted(os.listdir(ASSETS_DIR)):
        if "upgrade" not in fname.lower() or not fname.lower().endswith(".png"):
            continue
        
        path = os.path.join(ASSETS_DIR, fname)
        bgr, opaque_mask = load_opaque(path)
        if bgr is None:
            print(f"  SKIP {fname} (could not load)")
            continue
        
        total += 1
        result = test_upgrade_station_gate(bgr, opaque_mask)
        status = "PASS" if result["passes_ratio"] else "FAIL"
        if result["passes_ratio"]:
            passed += 1
        else:
            failed += 1
        
        print(f"  [{status}] {fname:25s}  cyan_px={result['cyan_pixels']:4d}/{result['total_opaque']:5d}  "
              f"ratio={result['ratio']:.1%}  (min={result['min_ratio']:.0%})")
    
    # Summary
    print(f"\n{'=' * 70}")
    print(f"SUMMARY: {passed}/{total} passed, {failed}/{total} failed")
    if failed > 0:
        print("WARNING: Some assets FAILED their HSV gate!")
        sys.exit(1)
    else:
        print("All assets passed their respective HSV color gates.")
        sys.exit(0)


if __name__ == "__main__":
    main()
