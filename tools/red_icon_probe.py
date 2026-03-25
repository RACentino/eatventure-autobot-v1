import argparse
import json
from pathlib import Path
import sys

import cv2

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
from image_matcher import ImageMatcher


def parse_hsv_triplet(value):
    parts = [int(part.strip()) for part in value.split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("HSV bounds must be comma-separated triplets")
    h, s, v = parts
    if not (0 <= h <= 179 and 0 <= s <= 255 and 0 <= v <= 255):
        raise argparse.ArgumentTypeError("HSV bounds must stay within OpenCV ranges")
    return h, s, v


def apply_overrides(args):
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
    if metrics["red_ratio"] < config.RED_ICON_COLOR_MIN_RATIO or metrics["red_mean"] < config.RED_ICON_COLOR_MIN_MEAN:
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


def iter_frames(input_path, frame_step, max_frames):
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


def build_parser():
    parser = argparse.ArgumentParser(description="Probe red icon HSV and confidence settings on sample frames")
    parser.add_argument("--input", required=True, help="Image, directory of images, or video to probe")
    parser.add_argument("--assets-dir", default=config.ASSETS_DIR, help="Directory containing RedIcon*.png templates")
    parser.add_argument("--threshold", type=float, default=config.RED_ICON_THRESHOLD, help="Template confidence threshold")
    parser.add_argument("--pixel-threshold", type=int, default=config.RED_ICON_PIXEL_THRESHOLD, help="Minimum masked red pixel count")
    parser.add_argument("--ratio-threshold", type=float, default=config.RED_ICON_COLOR_MIN_RATIO, help="Minimum masked red dominance ratio")
    parser.add_argument("--max-ratio-threshold", type=float, default=config.RED_ICON_COLOR_MAX_RATIO, help="Maximum masked red dominance ratio")
    parser.add_argument("--mean-threshold", type=float, default=config.RED_ICON_COLOR_MIN_MEAN, help="Minimum masked red channel mean")
    parser.add_argument("--coverage-threshold", type=float, default=config.RED_ICON_TEMPLATE_MIN_COVERAGE, help="Minimum template-mask red coverage")
    parser.add_argument("--precision-threshold", type=float, default=config.RED_ICON_TEMPLATE_MIN_PRECISION, help="Minimum template-mask precision")
    parser.add_argument("--recall-threshold", type=float, default=config.RED_ICON_TEMPLATE_MIN_RECALL, help="Minimum template-mask recall")
    parser.add_argument("--iou-threshold", type=float, default=config.RED_ICON_TEMPLATE_MIN_IOU, help="Minimum template-mask IoU")
    parser.add_argument("--color-similarity-threshold", type=float, default=config.RED_ICON_TEMPLATE_COLOR_SIMILARITY, help="Minimum template color histogram correlation")
    parser.add_argument("--red-hsv-lower1", type=parse_hsv_triplet, default=config.RED_HSV_LOWER1, help="Low red lower HSV bound")
    parser.add_argument("--red-hsv-upper1", type=parse_hsv_triplet, default=config.RED_HSV_UPPER1, help="Low red upper HSV bound")
    parser.add_argument("--red-hsv-lower2", type=parse_hsv_triplet, default=config.RED_HSV_LOWER2, help="High red lower HSV bound")
    parser.add_argument("--red-hsv-upper2", type=parse_hsv_triplet, default=config.RED_HSV_UPPER2, help="High red upper HSV bound")
    parser.add_argument("--frame-step", type=int, default=45, help="Video frame sampling interval")
    parser.add_argument("--max-frames", type=int, default=8, help="Maximum sampled frames to analyze")
    parser.add_argument("--max-y", type=int, default=config.MAX_SEARCH_Y, help="Crop frames to this Y limit before detection")
    parser.add_argument("--min-distance", type=int, default=config.RED_ICON_MIN_DISTANCE, help="Minimum template match spacing")
    parser.add_argument("--json-out", help="Optional path to write the analysis summary as JSON")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    apply_overrides(args)

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

    for frame_info in iter_frames(args.input, args.frame_step, args.max_frames):
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


if __name__ == "__main__":
    main()
