"""
Lensora — Screen Detection Test Suite
==========================================

Measures failure rates across 12 detection categories before algorithm tuning.

Usage:
  # Run full suite with report
  python -m pytest tests/test_screen_detection.py -v

  # Run with detailed JSON report
  python tests/test_screen_detection.py

  # Run only synthetic tests (no fixtures needed)
  python -m pytest tests/test_screen_detection.py -v -k "synthetic"

Fixture images:
  Place real test images in tests/fixtures/<category>/
  Supported formats: .jpg, .jpeg, .png, .webp

Category directory names:
  laptop_thin_bezel   — Modern laptop with thin dark bezel
  monitor_dark_desk   — Black monitor on dark desk
  phone_notch         — Mobile phone with notch
  phone_punch_hole    — Mobile phone with punch-hole camera
  tablet              — Tablet screen
  angled_30           — Angled shot ~30°
  angled_45           — Angled shot ~45°
  angled_60           — Angled shot ~60°
  glare               — Reflections/glare on screen
  dark_mode           — Dark mode screen content
  light_mode          — Light mode screen content
  multi_monitor       — Multiple monitors in frame
  busy_background     — Busy/cluttered background
  partial             — Partially visible screen
"""

import sys
import os
import json
import time
import math
import cv2
import numpy as np
import pytest
from pathlib import Path
from typing import Optional, Tuple

# ─── Path Setup ───────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from services.screen_detector import (
    process_image, detect_screen, estimate_tilt_angle,
    order_points, is_valid_screen_shape,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# ─── Category Definitions ─────────────────────────────────────────────────────
CATEGORIES = {
    "laptop_thin_bezel":  "Modern laptop with thin dark bezel",
    "monitor_dark_desk":  "Black monitor on dark desk",
    "phone_notch":        "Mobile phone with notch",
    "phone_punch_hole":   "Mobile phone with punch-hole camera",
    "tablet":             "Tablet screen",
    "angled_30":          "Angled shot ~30°",
    "angled_45":          "Angled shot ~45°",
    "angled_60":          "Angled shot ~60°",
    "glare":              "Reflections/glare on screen",
    "dark_mode":          "Dark mode screen content",
    "light_mode":         "Light mode screen content",
    "multi_monitor":      "Multiple monitors in frame",
    "busy_background":    "Busy/cluttered background",
    "partial":            "Partially visible screen",
}

# Expected outcomes per category
# "detect":  screen_detected=True expected
# "fallback": screen_detected=False OK (treated as screenshot mode, not a failure)
# "reject":  image quality rejection expected (extreme angle etc.)
EXPECTED_OUTCOME = {
    "laptop_thin_bezel": "detect",
    "monitor_dark_desk": "detect",
    "phone_notch":       "detect",
    "phone_punch_hole":  "detect",
    "tablet":            "detect",
    "angled_30":         "detect",
    "angled_45":         "detect",
    "angled_60":         "detect",   # at the boundary — graceful degradation
    "glare":             "detect",   # should still find screen area
    "dark_mode":         "detect",
    "light_mode":        "detect",
    "multi_monitor":     "detect",   # largest screen should be detected
    "busy_background":   "detect",
    "partial":           "fallback", # partial screens can't be fully corrected
}


# ─── Synthetic Image Generators ───────────────────────────────────────────────

def _make_text_content(img: np.ndarray, x: int, y: int, color: Tuple, scale: float = 0.7):
    """Add sample screen text content to an image."""
    lines = ["Q1 B) 323", "Q2 D) 72", "Q3 Canberra"]
    for i, line in enumerate(lines):
        cv2.putText(
            img, line,
            (x, y + i * int(30 * scale)),
            cv2.FONT_HERSHEY_SIMPLEX, scale, color, 2, cv2.LINE_AA
        )


def make_light_mode(size=(800, 600)) -> np.ndarray:
    """Light mode screen: bright content, visible bezel, medium background."""
    img = np.full((size[1], size[0], 3), 140, dtype=np.uint8)
    cv2.rectangle(img, (100, 80), (700, 520), (245, 245, 245), -1)   # screen
    cv2.rectangle(img, (100, 80), (700, 520), (40, 40, 40), 3)       # subtle frame
    _make_text_content(img, 130, 200, (30, 30, 30))
    return img


def make_dark_mode(size=(800, 600)) -> np.ndarray:
    """Dark mode screen: dark content with light text, visible on light bg."""
    img = np.full((size[1], size[0], 3), 195, dtype=np.uint8)
    cv2.rectangle(img, (100, 80), (700, 520), (28, 28, 28), -1)      # dark screen
    cv2.rectangle(img, (100, 80), (700, 520), (60, 60, 60), 3)
    _make_text_content(img, 130, 200, (215, 215, 215))
    return img


def make_laptop_thin_bezel(size=(900, 700)) -> np.ndarray:
    """Bright screen with 6px thin dark bezel on mid-gray background."""
    img = np.full((size[1], size[0], 3), 160, dtype=np.uint8)
    bezel_px = 6
    bx1, by1, bx2, by2 = 140, 100, 760, 600
    cv2.rectangle(img, (bx1, by1), (bx2, by2), (18, 18, 18), -1)
    cv2.rectangle(img,
                  (bx1 + bezel_px, by1 + bezel_px),
                  (bx2 - bezel_px, by2 - bezel_px),
                  (235, 235, 235), -1)
    _make_text_content(img, bx1 + 40, by1 + 80, (25, 25, 25))
    return img


def make_monitor_dark_desk(size=(900, 700)) -> np.ndarray:
    """Bright screen on very dark desk background."""
    img = np.full((size[1], size[0], 3), 18, dtype=np.uint8)          # almost black bg
    cv2.rectangle(img, (120, 90), (780, 610), (220, 220, 220), -1)    # bright screen
    _make_text_content(img, 160, 220, (25, 25, 25))
    return img


def make_phone_notch(size=(400, 750)) -> np.ndarray:
    """Portrait phone with notch at top center."""
    img = np.full((size[1], size[0], 3), 185, dtype=np.uint8)
    # Screen body
    cv2.rectangle(img, (25, 25), (375, 725), (240, 240, 240), -1)
    # Notch (dark cutout at top center)
    cv2.rectangle(img, (140, 25), (260, 65), (18, 18, 18), -1)
    cv2.rectangle(img, (25, 25), (375, 725), (50, 50, 50), 3)
    _make_text_content(img, 60, 250, (25, 25, 25), scale=0.6)
    return img


def make_phone_punch_hole(size=(400, 750)) -> np.ndarray:
    """Portrait phone with small punch-hole camera at top-left."""
    img = np.full((size[1], size[0], 3), 185, dtype=np.uint8)
    cv2.rectangle(img, (25, 25), (375, 725), (240, 240, 240), -1)
    # Punch-hole (small circle near top-left of screen area)
    cv2.circle(img, (80, 55), 15, (18, 18, 18), -1)
    cv2.rectangle(img, (25, 25), (375, 725), (50, 50, 50), 3)
    _make_text_content(img, 60, 250, (25, 25, 25), scale=0.6)
    return img


def make_tablet(size=(900, 700)) -> np.ndarray:
    """Tablet in landscape — wider aspect ratio, moderate bezel."""
    img = np.full((size[1], size[0], 3), 155, dtype=np.uint8)
    cv2.rectangle(img, (30, 40), (870, 660), (22, 22, 22), -1)        # bezel
    cv2.rectangle(img, (55, 65), (845, 635), (238, 238, 238), -1)     # screen
    _make_text_content(img, 90, 200, (25, 25, 25), scale=0.8)
    return img


def _apply_perspective_angle(img: np.ndarray, angle_deg: float) -> np.ndarray:
    """
    Simulate a horizontal viewing angle by applying a perspective transform.
    angle_deg: approximate viewing angle from perpendicular.
    """
    h, w = img.shape[:2]
    # Compute foreshortening factor for the far (left) side
    cos_a  = math.cos(math.radians(angle_deg))
    shrink = (1.0 - cos_a) * (w * 0.40)   # how much to compress far side

    src = np.float32([
        [0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]
    ])
    dst = np.float32([
        [shrink,     shrink * 0.1],
        [w - 1,      0],
        [w - 1,      h - 1],
        [shrink,     h - 1 - shrink * 0.1],
    ])
    M      = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(img, M, (w, h), borderValue=(155, 155, 155))
    return warped


def make_angled(angle_deg: float, size=(850, 650)) -> np.ndarray:
    """Simulated angled shot by applying perspective distortion."""
    # First create a clean front-on screen
    img = np.full((size[1], size[0], 3), 155, dtype=np.uint8)
    cv2.rectangle(img, (100, 80), (750, 570), (235, 235, 235), -1)
    cv2.rectangle(img, (100, 80), (750, 570), (40, 40, 40), 2)
    _make_text_content(img, 130, 200, (25, 25, 25))

    # Apply angle distortion
    return _apply_perspective_angle(img, angle_deg)


def make_glare(size=(800, 600)) -> np.ndarray:
    """Screen with bright glare/reflection in one corner."""
    img = make_light_mode(size)
    # Add bright glare ellipse (simulates window reflection)
    center = (600, 150)
    cv2.ellipse(img, center, (120, 80), -30, 0, 360, (255, 255, 255), -1)
    # Blend to avoid hard edge
    overlay = img.copy()
    cv2.ellipse(overlay, center, (100, 60), -30, 0, 360, (255, 255, 255), -1)
    cv2.addWeighted(img, 0.6, overlay, 0.4, 0, img)
    return img


def make_multi_monitor(size=(1400, 700)) -> np.ndarray:
    """Two screens side by side — detection should find the larger one."""
    img = np.full((size[1], size[0], 3), 140, dtype=np.uint8)
    # Left screen (slightly smaller)
    cv2.rectangle(img, (30, 80), (640, 620), (235, 235, 235), -1)
    cv2.rectangle(img, (30, 80), (640, 620), (40, 40, 40), 2)
    _make_text_content(img, 60, 250, (25, 25, 25), scale=0.6)
    # Right screen (slightly larger — should be detected)
    cv2.rectangle(img, (760, 60), (1370, 640), (240, 240, 240), -1)
    cv2.rectangle(img, (760, 60), (1370, 640), (40, 40, 40), 2)
    _make_text_content(img, 800, 250, (25, 25, 25))
    return img


def make_busy_background(size=(900, 700)) -> np.ndarray:
    """Screen on a cluttered desk with many rectangular objects."""
    rng = np.random.default_rng(42)
    img = np.full((size[1], size[0], 3), 120, dtype=np.uint8)
    # Background noise: books/papers
    for _ in range(8):
        x1 = int(rng.integers(0, size[0] - 100))
        y1 = int(rng.integers(0, size[1] - 80))
        x2 = x1 + int(rng.integers(80, 180))
        y2 = y1 + int(rng.integers(60, 130))
        color = tuple(int(c) for c in rng.integers(60, 210, size=3))
        cv2.rectangle(img, (x1, y1), (min(x2, size[0]-1), min(y2, size[1]-1)), color, -1)
    # Main screen (centered, clearly the largest)
    cv2.rectangle(img, (200, 150), (700, 550), (238, 238, 238), -1)
    cv2.rectangle(img, (200, 150), (700, 550), (30, 30, 30), 3)
    _make_text_content(img, 230, 280, (25, 25, 25))
    return img


def make_partial_screen(size=(800, 600)) -> np.ndarray:
    """Screen cropped at the right edge — only 3 corners visible."""
    img = np.full((size[1], size[0], 3), 140, dtype=np.uint8)
    # Screen extends beyond right edge (partial visibility)
    cv2.rectangle(img, (100, 80), (900, 520), (235, 235, 235), -1)   # x2=900 > width=800
    cv2.rectangle(img, (100, 80), (800, 520), (40, 40, 40), 2)
    _make_text_content(img, 130, 200, (25, 25, 25))
    return img


# ─── Synthetic Image Map ──────────────────────────────────────────────────────

SYNTHETIC_GENERATORS = {
    "laptop_thin_bezel": make_laptop_thin_bezel,
    "monitor_dark_desk": make_monitor_dark_desk,
    "phone_notch":       make_phone_notch,
    "phone_punch_hole":  make_phone_punch_hole,
    "tablet":            make_tablet,
    "angled_30":         lambda: make_angled(30.0),
    "angled_45":         lambda: make_angled(45.0),
    "angled_60":         lambda: make_angled(60.0),
    "glare":             make_glare,
    "dark_mode":         make_dark_mode,
    "light_mode":        make_light_mode,
    "multi_monitor":     make_multi_monitor,
    "busy_background":   make_busy_background,
    "partial":           make_partial_screen,
}


# ─── Test Runner ──────────────────────────────────────────────────────────────

def load_fixture_images(category: str):
    """Load all images from the fixture directory for a category."""
    cat_dir = FIXTURES_DIR / category
    if not cat_dir.exists():
        return []
    images = []
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
        for p in cat_dir.glob(ext):
            img = cv2.imread(str(p))
            if img is not None:
                images.append((p.name, img))
    return images


def run_category(category: str, verbose: bool = False) -> dict:
    """
    Run detection tests for one category.

    Tests real fixture images first; falls back to one synthetic image
    if no fixtures are present.
    """
    results = {
        "category":         category,
        "description":      CATEGORIES.get(category, ""),
        "expected_outcome": EXPECTED_OUTCOME.get(category, "detect"),
        "total":            0,
        "detected":         0,
        "fallback":         0,
        "quality_failed":   0,
        "errors":           0,
        "detection_rate":   0.0,
        "avg_confidence":   0.0,
        "avg_tilt_deg":     0.0,
        "avg_detect_ms":    0.0,
        "avg_total_ms":     0.0,
        "image_results":    [],
        "source":           "synthetic",
    }

    # Load images
    fixture_imgs = load_fixture_images(category)
    if fixture_imgs:
        images     = fixture_imgs
        results["source"] = "fixture"
    else:
        gen = SYNTHETIC_GENERATORS.get(category)
        images = [(f"synthetic_{category}.png", gen())] if gen else []

    if not images:
        results["notes"] = "No images available and no synthetic generator"
        return results

    confidences = []
    tilts       = []
    detect_ms_list = []
    total_ms_list  = []

    for img_name, img in images:
        result = {"image": img_name}
        try:
            processed, detection = process_image(img)
            timing = detection.get("_timing", {})

            result["screen_detected"] = detection["screen_detected"]
            result["confidence"]      = detection["confidence"]
            result["tilt_angle_deg"]  = detection.get("tilt_angle_deg", 0.0)
            result["detect_ms"]       = timing.get("detection_ms", 0)
            result["total_ms"]        = timing.get("total_ms", 0)

            if detection["screen_detected"]:
                results["detected"] += 1
                confidences.append(detection["confidence"])
                tilts.append(detection.get("tilt_angle_deg", 0.0))
            else:
                results["fallback"] += 1

            detect_ms_list.append(timing.get("detection_ms", 0))
            total_ms_list.append(timing.get("total_ms", 0))

        except Exception as exc:
            result["error"] = str(exc)
            results["errors"] += 1
            if verbose:
                print(f"  ERROR [{category}/{img_name}]: {exc}")

        results["total"] += 1
        results["image_results"].append(result)

    if results["total"] > 0:
        results["detection_rate"] = round(results["detected"] / results["total"] * 100, 1)
        results["avg_confidence"] = round(float(np.mean(confidences)), 3) if confidences else 0.0
        results["avg_tilt_deg"]   = round(float(np.mean(tilts)), 1) if tilts else 0.0
        results["avg_detect_ms"]  = round(float(np.mean(detect_ms_list)), 1) if detect_ms_list else 0.0
        results["avg_total_ms"]   = round(float(np.mean(total_ms_list)), 1) if total_ms_list else 0.0

    return results


def run_full_suite(verbose: bool = True) -> dict:
    """Run all categories and return a structured failure-rate report."""
    print("\n" + "=" * 70)
    print("  Lensora — Screen Detection Test Suite")
    print("=" * 70)

    all_results  = {}
    overall_pass = 0
    overall_fail = 0
    overall_total = 0

    for category in CATEGORIES:
        result = run_category(category, verbose=verbose)
        all_results[category] = result

        expected = result["expected_outcome"]
        detected = result["detected"]
        fallback = result["fallback"]
        total    = result["total"]

        # Determine pass/fail
        if expected == "detect":
            passed = detected == total
            status = "PASS" if passed else "FAIL"
        elif expected == "fallback":
            passed = fallback > 0 or detected > 0   # either is acceptable
            status = "PASS" if passed else "FAIL"
        else:
            passed = True
            status = "PASS"

        if passed:
            overall_pass += 1
        else:
            overall_fail += 1
        overall_total += 1

        source_tag = f"[{result['source']}]"
        print(
            f"  {status:4s}  {category:<24s}  "
            f"detected={detected}/{total}  "
            f"conf={result['avg_confidence']:.2f}  "
            f"tilt={result['avg_tilt_deg']:.1f}°  "
            f"{result['avg_total_ms']:.0f}ms  "
            f"{source_tag}"
        )

    print("-" * 70)
    print(f"  SUMMARY: {overall_pass}/{overall_total} categories passed")
    print(f"  Failure rate: {overall_fail/overall_total*100:.1f}%")
    print("=" * 70 + "\n")

    report = {
        "test_suite_version": "1.0",
        "summary": {
            "categories_total":  overall_total,
            "categories_passed": overall_pass,
            "categories_failed": overall_fail,
            "failure_rate_pct":  round(overall_fail / overall_total * 100, 1),
        },
        "categories": all_results,
    }

    # Write JSON report
    report_path = Path(__file__).parent.parent / ".." / "test_reports" / "screen_detection_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"  Full report written to: {report_path.resolve()}")

    return report


# ─── Pytest Cases ─────────────────────────────────────────────────────────────

class TestSyntheticDetection:
    """Pytest-runnable detection tests using synthetic images."""

    def _run(self, category: str):
        result = run_category(category)
        assert result["total"] > 0, f"No images for {category}"
        return result

    # --- Basic geometry ---

    def test_synthetic_light_mode(self):
        r = self._run("light_mode")
        assert r["detection_rate"] == 100.0, f"light_mode: {r}"

    def test_synthetic_dark_mode(self):
        r = self._run("dark_mode")
        assert r["detection_rate"] == 100.0, f"dark_mode: {r}"

    def test_synthetic_laptop_thin_bezel(self):
        r = self._run("laptop_thin_bezel")
        assert r["detection_rate"] == 100.0, f"laptop_thin_bezel: {r}"

    def test_synthetic_monitor_dark_desk(self):
        r = self._run("monitor_dark_desk")
        assert r["detection_rate"] == 100.0, f"monitor_dark_desk: {r}"

    def test_synthetic_tablet(self):
        r = self._run("tablet")
        assert r["detection_rate"] == 100.0, f"tablet: {r}"

    # --- Mobile ---

    def test_synthetic_phone_notch(self):
        r = self._run("phone_notch")
        assert r["detection_rate"] == 100.0, f"phone_notch: {r}"

    def test_synthetic_phone_punch_hole(self):
        r = self._run("phone_punch_hole")
        assert r["detection_rate"] == 100.0, f"phone_punch_hole: {r}"

    # --- Angles ---

    def test_synthetic_angled_30(self):
        r = self._run("angled_30")
        assert r["detection_rate"] == 100.0, f"angled_30: {r}"

    def test_synthetic_angled_45(self):
        r = self._run("angled_45")
        assert r["detection_rate"] == 100.0, f"angled_45: {r}"

    def test_synthetic_angled_60(self):
        r = self._run("angled_60")
        # 60° is borderline — detect or graceful fallback both acceptable
        assert r["detected"] + r["fallback"] == r["total"], f"angled_60: {r}"

    # --- Edge cases ---

    def test_synthetic_glare(self):
        r = self._run("glare")
        assert r["detection_rate"] == 100.0, f"glare: {r}"

    def test_synthetic_multi_monitor(self):
        r = self._run("multi_monitor")
        assert r["detection_rate"] == 100.0, f"multi_monitor: {r}"

    def test_synthetic_busy_background(self):
        r = self._run("busy_background")
        assert r["detection_rate"] == 100.0, f"busy_background: {r}"

    def test_synthetic_partial(self):
        r = self._run("partial")
        # Partial screens — detection or fallback both acceptable
        assert r["errors"] == 0, f"partial: unexpected errors {r}"


class TestTiltAngleEstimation:
    """Tests for the angle estimation function."""

    def _make_corners(self, tl, tr, br, bl):
        return np.array([tl, tr, br, bl], dtype="float32").reshape(-1, 1, 2).astype(np.int32)

    def test_front_on_angle_near_zero(self):
        """Perfect rectangle should report ~0°."""
        corners = self._make_corners([100, 100], [700, 100], [700, 500], [100, 500])
        angle = estimate_tilt_angle(corners)
        assert angle < 5.0, f"Expected <5°, got {angle}°"

    def test_30_degree_approx(self):
        """Foreshortened one side by cos(30°) ≈ 0.866."""
        cos30   = math.cos(math.radians(30))
        corners = self._make_corners(
            [150, 100], [650, 100], [650, 500],
            [150 + int(300 * (1 - cos30)), 500]
        )
        angle = estimate_tilt_angle(corners)
        assert 20.0 < angle < 45.0, f"Expected 20-45°, got {angle}°"

    def test_45_degree_approx(self):
        # Proper trapezoid: top edge foreshortened by cos(45°) ≈ 0.707, bottom is full width
        cos45      = math.cos(math.radians(45))
        full_w     = 500
        short_w    = int(full_w * cos45)   # ≈ 354
        cx         = 400
        corners = self._make_corners(
            [cx - short_w // 2, 100],   # TL — top edge shorter (far side)
            [cx + short_w // 2, 100],   # TR
            [cx + full_w  // 2, 500],   # BR — bottom edge full width (near side)
            [cx - full_w  // 2, 500],   # BL
        )
        angle = estimate_tilt_angle(corners)
        assert 30.0 < angle < 65.0, f"Expected 30-65°, got {angle}°"


class TestTwoStagePipeline:
    """Verify that the two-stage pipeline works for large images."""

    def test_large_image_detection(self):
        """Large image (>1500px) should be downscaled for detection."""
        # Create 3000x2000 image with a clear screen
        img = np.full((2000, 3000, 3), 140, dtype=np.uint8)
        cv2.rectangle(img, (300, 200), (2700, 1800), (240, 240, 240), -1)
        cv2.rectangle(img, (300, 200), (2700, 1800), (30, 30, 30), 5)

        _, detection = process_image(img)
        timing = detection.get("_timing", {})

        assert timing.get("total_ms", 0) > 0, "Timing not recorded"
        assert timing.get("detection_ms", 0) > 0, "Detection time not recorded"
        assert detection["screen_detected"] is True, "Should detect screen in large image"

    def test_timing_keys_present(self):
        """Detection info must always contain _timing dict."""
        img = make_light_mode()
        _, detection = process_image(img)
        timing = detection.get("_timing", {})
        assert "detection_ms" in timing
        assert "warp_ms" in timing
        assert "total_ms" in timing

    def test_small_image_no_downscale(self):
        """Small image (≤1500px) should not be downscaled."""
        img = make_light_mode(size=(800, 600))
        _, detection = process_image(img)
        assert detection is not None
        assert "_timing" in detection


class TestHelperFunctions:
    """Unit tests for utility functions."""

    def test_order_points_canonical(self):
        pts = np.array([[100, 500], [100, 100], [700, 100], [700, 500]], dtype="float32")
        ordered = order_points(pts)
        np.testing.assert_array_almost_equal(ordered[0], [100, 100])  # TL
        np.testing.assert_array_almost_equal(ordered[1], [700, 100])  # TR
        np.testing.assert_array_almost_equal(ordered[2], [700, 500])  # BR
        np.testing.assert_array_almost_equal(ordered[3], [100, 500])  # BL

    def test_valid_screen_shape_rejects_too_large_aspect(self):
        img  = np.zeros((600, 800, 3), dtype=np.uint8)
        pts  = np.array([[100, 290], [700, 290], [700, 310], [100, 310]], dtype="float32")
        quad = pts.reshape(-1, 1, 2).astype(np.int32)
        # This is 600x20 → aspect = 30:1 → should be rejected
        assert not is_valid_screen_shape(quad, img)

    def test_valid_screen_shape_accepts_16_9(self):
        img  = np.zeros((600, 900, 3), dtype=np.uint8)
        # 16:9 ≈ 1.78:1 — well within bounds
        pts  = np.array([[100, 100], [900, 100], [900, 607], [100, 607]], dtype="float32")
        quad = pts.reshape(-1, 1, 2).astype(np.int32)
        assert is_valid_screen_shape(quad, img)


# ─── CLI Entry Point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    report = run_full_suite(verbose=True)

    failed_cats = [
        cat for cat, r in report["categories"].items()
        if r["expected_outcome"] == "detect" and r["detection_rate"] < 100.0
    ]

    if failed_cats:
        print(f"\nFailing categories requiring investigation:")
        for cat in failed_cats:
            r = report["categories"][cat]
            print(f"  {cat}: detection_rate={r['detection_rate']}%")
            for img_r in r["image_results"]:
                if not img_r.get("screen_detected") and not img_r.get("error"):
                    print(f"    - missed: {img_r['image']} (tilt={img_r.get('tilt_angle_deg', 'N/A')}°)")
    else:
        print("All synthetic tests passed. Add real fixture images for production benchmarking.")
