"""Screen detection, cropping, and perspective correction using OpenCV.

Two-Stage Pipeline:
  Stage 1: Detect on downscaled image (≤1500px longest side) — fast contour extraction
  Stage 2: Apply perspective warp on original full-resolution image — maximum quality

Multi-Strategy Edge Detection:
  A. CLAHE normalization + morphological closing + multi-threshold Canny
  B. CLAHE + Gaussian blur + Canny (no closing — better for thin bezels)
  C. Adaptive threshold (dark bezels, uneven lighting, black-on-black scenarios)

Robust Quad Extraction:
  - Multi-epsilon approxPolyDP (0.01–0.06 range)
  - Convex hull simplification fallback (for angled/perspective-distorted contours)
  - 4-extreme-corner extraction (for 5-8 corner near-quads)

Angle Estimation:
  - 0°–50°:  reliable detection + correction
  - 50°–60°: graceful degradation (caution flag)
  - 60°+:    rejected upstream with retake prompt

Timing Metrics (internal only — logged, never user-facing):
  - detection_ms: time to find corners on downscaled image
  - warp_ms:      time to apply perspective transform on full-res
  - total_ms:     end-to-end preprocessing time
"""

import time
import cv2
import numpy as np
import logging
from typing import Optional, Tuple, List

logger = logging.getLogger("lensora.screen_detector")

# Detection downscale target (longest side, pixels)
_MAX_DETECT_DIM = 1500


# ─── Corner Ordering ──────────────────────────────────────────────────────────

def order_points(pts: np.ndarray) -> np.ndarray:
    """
    Order 4 corner points as: top-left, top-right, bottom-right, bottom-left.
    Uses x+y sum / x-y diff — robust for near-rectangular quads.
    """
    rect = np.zeros((4, 2), dtype="float32")
    s    = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]     # top-left:    smallest x+y
    rect[2] = pts[np.argmax(s)]     # bottom-right: largest x+y
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]  # top-right:   smallest y−x
    rect[3] = pts[np.argmax(diff)]  # bottom-left:  largest y−x
    return rect


# ─── Shape Validation ─────────────────────────────────────────────────────────

def is_valid_screen_shape(corners: np.ndarray, image_np: np.ndarray) -> bool:
    """
    Reject quadrilaterals that can't plausibly be a screen.

    Thresholds (conservative — tuning deferred until test-suite results):
    - Minimum edge length: 30px
    - Aspect ratio: 1.05:1 – 3.2:1  (longer / shorter side)
    - Convexity ratio ≥ 0.82        (quad area / hull area)

    NOTE: These are the original thresholds. They will be tuned after the
    test suite reports per-category failure rates.
    """
    pts = order_points(corners.reshape(4, 2).astype("float32"))
    (tl, tr, br, bl) = pts

    width  = float(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))
    height = float(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))

    if width < 30 or height < 30:
        return False

    longer, shorter = max(width, height), min(width, height)
    if shorter < 1:
        return False
    if longer / shorter > 3.2:
        return False

    hull     = cv2.convexHull(corners)
    hull_area = float(cv2.contourArea(hull))
    quad_area = float(cv2.contourArea(corners))
    if hull_area > 0 and quad_area / hull_area < 0.82:
        return False

    return True


# ─── Edge Maps ────────────────────────────────────────────────────────────────

def _build_edge_maps(gray: np.ndarray) -> List[np.ndarray]:
    """
    Build multiple edge maps using three strategies.

    Strategy A (closing + CLAHE + Canny): original approach, improved with CLAHE.
      Best for: standard screens, moderate contrast bezels.

    Strategy B (CLAHE + thin Gaussian + Canny): no morphological closing.
      Best for: thin bezels where closing bridges the wrong gaps.

    Strategy C (adaptive threshold): local-contrast-based binary edges.
      Best for: dark bezels, black monitor on dark desk, uneven lighting.

    Maps are ordered by expected reliability — callers should prefer early hits.
    """
    # CLAHE: normalize local contrast — critical for dark bezels, uneven lighting
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    edge_maps: List[np.ndarray] = []

    # ── Strategy A: morphological closing + CLAHE + multi-threshold Canny ────
    close_k = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    closed  = cv2.morphologyEx(enhanced, cv2.MORPH_CLOSE, close_k)
    blurred = cv2.GaussianBlur(closed, (5, 5), 0)
    for lo, hi in [(50, 150), (30, 100), (80, 200), (20, 80)]:
        edge_maps.append(cv2.Canny(blurred, lo, hi))

    # ── Strategy B: CLAHE + light Gaussian + Canny (no closing) ──────────────
    blurred_direct = cv2.GaussianBlur(enhanced, (5, 5), 0)
    for lo, hi in [(40, 120), (25, 75), (60, 160)]:
        edge_maps.append(cv2.Canny(blurred_direct, lo, hi))

    # Fine kernel pass: picks up very thin bezels
    blurred_fine = cv2.GaussianBlur(enhanced, (3, 3), 0)
    edge_maps.append(cv2.Canny(blurred_fine, 45, 135))

    # ── Strategy C: adaptive threshold (dark-bezel & uneven-lighting) ────────
    for block_size, c_val in [(11, 2), (21, 3), (15, 2)]:
        adaptive = cv2.adaptiveThreshold(
            enhanced, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            block_size, c_val
        )
        edge_maps.append(adaptive)

    return edge_maps


# ─── Quad Extraction ──────────────────────────────────────────────────────────

def _four_extreme_corners(pts: np.ndarray) -> Optional[np.ndarray]:
    """
    Given N ≥ 4 points, return the 4 that represent TL, TR, BR, BL extremes.
    Used to reduce 5-8 corner near-quads (angled shots) to 4 corners.
    """
    if len(pts) < 4:
        return None
    s    = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).flatten()
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmin(diff)]
    bl = pts[np.argmax(diff)]
    quad = np.array([tl, tr, br, bl], dtype="float32")
    return quad.reshape(-1, 1, 2).astype(np.int32)


def _extract_quad(contour: np.ndarray) -> Optional[np.ndarray]:
    """
    Robustly extract a 4-corner quadrilateral from a contour.

    Three passes to handle both well-aligned and perspective-distorted shapes:

    Pass 1 — vary epsilon on raw contour (standard case + moderate angles).
    Pass 2 — vary epsilon on convex hull (trapezoidal/angled quads).
    Pass 3 — extract 4 extreme corners from 5-8 corner near-quads.
    """
    peri = cv2.arcLength(contour, True)
    if peri < 10:
        return None

    # Pass 1: vary epsilon on contour directly
    for eps_frac in [0.02, 0.015, 0.03, 0.01, 0.04, 0.05, 0.06]:
        approx = cv2.approxPolyDP(contour, eps_frac * peri, True)
        if len(approx) == 4:
            return approx

    # Pass 2: convex hull first, then approximate
    hull      = cv2.convexHull(contour)
    hull_peri = cv2.arcLength(hull, True)
    if hull_peri > 10:
        for eps_frac in [0.02, 0.03, 0.04, 0.05, 0.08, 0.10]:
            approx = cv2.approxPolyDP(hull, eps_frac * hull_peri, True)
            if len(approx) == 4:
                return approx

    # Pass 3: for 5–8 corner near-quads, use 4 extreme points
    for eps_frac in [0.005, 0.01, 0.015, 0.02]:
        approx = cv2.approxPolyDP(contour, eps_frac * peri, True)
        if 4 < len(approx) <= 8:
            pts  = approx.reshape(-1, 2).astype("float32")
            quad = _four_extreme_corners(pts)
            if quad is not None:
                return quad

    return None


# ─── Angle Estimation ─────────────────────────────────────────────────────────

def estimate_tilt_angle(corners: np.ndarray) -> float:
    """
    Estimate the maximum viewing angle from quad corner geometry.

    Method: ratio of parallel opposite sides (foreshortening model).
      ratio = shorter_side / longer_side ≈ cos(θ)
      θ ≈ arccos(ratio)

    Returns degrees (0 = front-on, 90 = edge-on).
    Note: this is a geometric approximation; assumes rectangular screen.
    """
    pts = order_points(corners.reshape(4, 2).astype("float32"))
    tl, tr, br, bl = pts

    top    = float(np.linalg.norm(tr - tl))
    bottom = float(np.linalg.norm(br - bl))
    left   = float(np.linalg.norm(bl - tl))
    right  = float(np.linalg.norm(br - tr))

    h_ratio = (min(top, bottom) / max(top, bottom)) if max(top, bottom) > 0 else 1.0
    v_ratio = (min(left, right) / max(left, right)) if max(left, right) > 0 else 1.0

    h_angle = float(np.degrees(np.arccos(float(np.clip(h_ratio, 0.01, 1.0)))))
    v_angle = float(np.degrees(np.arccos(float(np.clip(v_ratio, 0.01, 1.0)))))

    return round(max(h_angle, v_angle), 1)


# ─── Core Detection ───────────────────────────────────────────────────────────

def detect_screen(image_np: np.ndarray) -> Optional[np.ndarray]:
    """
    Find the largest valid rectangular screen region in the image.

    Iterates over all edge maps in priority order; returns the first valid
    quad with the largest area within each map.
    """
    h, w = image_np.shape[:2]
    image_area = h * w

    gray      = cv2.cvtColor(image_np, cv2.COLOR_BGR2GRAY)
    edge_maps = _build_edge_maps(gray)

    best_corners: Optional[np.ndarray] = None
    best_area    = 0.0

    dil_k = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))

    for edges in edge_maps:
        dilated   = cv2.dilate(edges, dil_k, iterations=2)
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours  = sorted(contours, key=cv2.contourArea, reverse=True)

        for contour in contours[:20]:
            if cv2.contourArea(contour) < 0.04 * image_area:
                break  # All remaining contours too small

            quad = _extract_quad(contour)
            if quad is None:
                continue

            area     = float(cv2.contourArea(quad))
            coverage = area / image_area

            if not (0.08 <= coverage <= 0.95):
                continue

            if not is_valid_screen_shape(quad, image_np):
                continue

            if area > best_area:
                best_area    = area
                best_corners = quad

            break  # Best contour for this edge map found

        # Early exit: found a large, high-coverage detection
        if best_corners is not None and best_area / image_area > 0.25:
            break

    return best_corners


# ─── Perspective Correction ───────────────────────────────────────────────────

def perspective_correct(image_np: np.ndarray, corners: np.ndarray) -> np.ndarray:
    """
    4-point perspective transform → flat, undistorted screen crop.

    Applies sub-pixel corner refinement (cornerSubPix) before the warp
    for improved accuracy on angled shots.
    """
    pts  = order_points(corners.reshape(4, 2).astype("float32"))
    (tl, tr, br, bl) = pts

    # Sub-pixel corner refinement — improves edge accuracy for angled shots
    gray = cv2.cvtColor(image_np, cv2.COLOR_BGR2GRAY)
    try:
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.01)
        refined  = cv2.cornerSubPix(gray, pts.copy(), (5, 5), (-1, -1), criteria)
        # Accept only if refinement doesn't move any corner more than 10px
        if np.max(np.linalg.norm(refined - pts, axis=1)) < 10.0:
            pts  = refined
            (tl, tr, br, bl) = pts
    except Exception:
        pass  # Keep original corners if refinement fails

    widthA  = float(np.linalg.norm(br - bl))
    widthB  = float(np.linalg.norm(tr - tl))
    heightA = float(np.linalg.norm(tr - br))
    heightB = float(np.linalg.norm(tl - bl))

    maxWidth  = max(int(widthA),  int(widthB))
    maxHeight = max(int(heightA), int(heightB))

    if maxWidth < 50 or maxHeight < 50:
        logger.warning("Perspective correction skipped: output dimensions too small")
        return image_np

    ih, iw = image_np.shape[:2]
    if maxWidth > iw * 1.6 or maxHeight > ih * 1.6:
        logger.warning(
            f"Perspective correction skipped: output {maxWidth}x{maxHeight} "
            f"unreasonably large for input {iw}x{ih}"
        )
        return image_np

    dst = np.array([
        [0,            0],
        [maxWidth - 1, 0],
        [maxWidth - 1, maxHeight - 1],
        [0,            maxHeight - 1],
    ], dtype="float32")

    M      = cv2.getPerspectiveTransform(pts, dst)
    warped = cv2.warpPerspective(image_np, M, (maxWidth, maxHeight))
    return warped


# ─── Confidence Scoring ───────────────────────────────────────────────────────

def compute_confidence(corners: np.ndarray, image_np: np.ndarray) -> float:
    """
    Confidence 0.0–1.0 from coverage ratio (70%) and corner orthogonality (30%).

    Coverage gives the base score (same thresholds as before).
    Orthogonality rewards detections where corners are close to 90°
    (direct shots score higher than extreme-angle shots).
    """
    h, w      = image_np.shape[:2]
    image_area = h * w
    screen_area = float(cv2.contourArea(corners))
    coverage   = screen_area / image_area

    if   coverage < 0.05:               cov_score = 0.25
    elif 0.05  <= coverage < 0.15:      cov_score = 0.55
    elif 0.15  <= coverage <= 0.80:     cov_score = 0.92
    elif 0.80  < coverage  <= 0.95:     cov_score = 0.60
    else:                               cov_score = 0.40

    # Orthogonality: how close to 90° are the quad interior angles
    orth = _compute_orthogonality(corners)

    return round(min(0.70 * cov_score + 0.30 * orth, 0.99), 2)


def _compute_orthogonality(corners: np.ndarray) -> float:
    """Score 0.0–1.0: how close to 90° are the quad's interior angles."""
    pts = order_points(corners.reshape(4, 2).astype("float32"))
    angles = []
    n = len(pts)
    for i in range(n):
        a = pts[(i - 1) % n]
        b = pts[i]
        c = pts[(i + 1) % n]
        v1, v2 = a - b, c - b
        n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
        if n1 < 1 or n2 < 1:
            continue
        cos_a = float(np.clip(np.dot(v1, v2) / (n1 * n2), -1.0, 1.0))
        angles.append(float(np.degrees(np.arccos(cos_a))))

    if not angles:
        return 0.5
    mean_dev = float(np.mean([abs(a - 90.0) for a in angles]))
    return float(max(0.0, 1.0 - mean_dev / 45.0))


# ─── Main Pipeline ────────────────────────────────────────────────────────────

def process_image(image_np: np.ndarray) -> Tuple[np.ndarray, dict]:
    """
    Two-stage pipeline: detect on downscaled copy, warp on full-resolution original.

    Stage 1: Downscale longest side to ≤1500px → fast edge detection.
    Stage 2: Map corners back to original resolution → high-quality warp.

    Returns:
        (processed_image, detection_info)
        detection_info["_timing"] contains internal-only performance metrics.
    """
    t_total_start = time.perf_counter()
    h, w = image_np.shape[:2]

    # ── Stage 1: Detection on downscaled image ────────────────────────────────
    scale = min(1.0, _MAX_DETECT_DIM / max(h, w))
    if scale < 0.99:
        detect_w = int(w * scale)
        detect_h = int(h * scale)
        detect_img = cv2.resize(
            image_np, (detect_w, detect_h), interpolation=cv2.INTER_AREA
        )
        logger.debug(
            f"Downscaled {w}x{h} → {detect_w}x{detect_h} "
            f"(scale={scale:.3f}) for detection"
        )
    else:
        detect_img = image_np
        scale = 1.0

    t_detect_start = time.perf_counter()
    corners_scaled = detect_screen(detect_img)
    t_detect_end   = time.perf_counter()
    detection_ms   = round((t_detect_end - t_detect_start) * 1000, 1)

    # Map corners back to original resolution
    if corners_scaled is not None and scale < 0.99:
        corners = (corners_scaled.astype("float32") / scale).astype(np.int32)
    else:
        corners = corners_scaled

    # ── Stage 2: Perspective correction on full-resolution original ───────────
    t_warp_start = time.perf_counter()

    if corners is not None:
        confidence  = compute_confidence(corners, image_np)
        tilt_angle  = estimate_tilt_angle(corners)
        bbox        = cv2.boundingRect(corners)
        processed   = perspective_correct(image_np, corners)

        t_warp_end = time.perf_counter()
        warp_ms    = round((t_warp_end - t_warp_start) * 1000, 1)
        total_ms   = round((time.perf_counter() - t_total_start) * 1000, 1)

        logger.info(
            f"screen_detected=True conf={confidence} "
            f"tilt={tilt_angle}° detect={detection_ms}ms "
            f"warp={warp_ms}ms total={total_ms}ms"
        )

        return processed, {
            "screen_detected": True,
            "confidence": confidence,
            "tilt_angle_deg": tilt_angle,
            "bbox": {
                "x": int(bbox[0]), "y": int(bbox[1]),
                "w": int(bbox[2]), "h": int(bbox[3]),
            },
            "corners": corners.reshape(4, 2).tolist(),
            "_timing": {
                "detection_ms": detection_ms,
                "warp_ms":      warp_ms,
                "total_ms":     total_ms,
            },
        }

    t_warp_end = time.perf_counter()
    total_ms   = round((time.perf_counter() - t_total_start) * 1000, 1)

    logger.info(
        f"screen_detected=False (screenshot mode) "
        f"detect={detection_ms}ms total={total_ms}ms"
    )

    return image_np, {
        "screen_detected": False,
        "confidence": 0.0,
        "tilt_angle_deg": 0.0,
        "bbox": None,
        "corners": None,
        "_timing": {
            "detection_ms": detection_ms,
            "warp_ms":      0.0,
            "total_ms":     total_ms,
        },
    }
