"""Screen detection, cropping, and perspective correction using OpenCV.

Pipeline:
1. Grayscale + morphological closing (fills thin-bezel gaps)
2. Gaussian blur + Canny edge detection (multi-threshold)
3. Contour analysis → filter to valid quadrilaterals
4. Shape validation: aspect ratio + convexity
5. Perspective transform → flat, undistorted screen crop

Detects: laptop screens, desktop monitors, phone screens, tablet screens.
Ignores: keyboard, hands, desk, room background, monitor bezels.
Falls back to full image when no screen boundary found (screenshot mode).
"""

import cv2
import numpy as np
import logging
from typing import Optional, Tuple

logger = logging.getLogger("screensolve.screen_detector")


def order_points(pts: np.ndarray) -> np.ndarray:
    """
    Order 4 corner points as: top-left, top-right, bottom-right, bottom-left.
    Uses x+y sum / x-y diff — robust for near-rectangular quads.
    """
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]    # top-left:     smallest x+y
    rect[2] = pts[np.argmax(s)]    # bottom-right:  largest x+y
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)] # top-right:    smallest y−x
    rect[3] = pts[np.argmax(diff)] # bottom-left:   largest y−x
    return rect


def is_valid_screen_shape(corners: np.ndarray, image_np: np.ndarray) -> bool:
    """
    Reject quadrilaterals that can't plausibly be a screen.

    Checks:
    - Minimum pixel size (too small = bezel artifact)
    - Aspect ratio: screens are 1.1:1 → 3.2:1 (portrait or landscape)
    - Convexity ratio ≥ 0.82 (slightly concave quads are still valid due to lens distortion)
    """
    pts = order_points(corners.reshape(4, 2).astype("float32"))
    (tl, tr, br, bl) = pts

    width  = float(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))
    height = float(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))

    if width < 30 or height < 30:
        return False

    # Screen aspect ratio gate: 1.05:1 to 3.2:1 (covers phones in portrait up to 21:9)
    longer, shorter = max(width, height), min(width, height)
    if shorter < 1:
        return False
    aspect = longer / shorter
    if aspect > 3.2:
        return False

    # Convexity check — screen outline should be close to convex
    hull = cv2.convexHull(corners)
    hull_area = float(cv2.contourArea(hull))
    quad_area = float(cv2.contourArea(corners))
    if hull_area > 0 and quad_area / hull_area < 0.82:
        return False

    return True


def detect_screen(image_np: np.ndarray) -> Optional[np.ndarray]:
    """
    Find the largest valid rectangular screen region in the image.

    Strategy:
    1. Morphological closing bridges thin bezel gaps and frame edges
    2. Multi-threshold Canny catches screens with varying contrast / lighting
    3. Each candidate quad is validated for plausible screen geometry
    """
    h, w = image_np.shape[:2]
    image_area = h * w

    gray = cv2.cvtColor(image_np, cv2.COLOR_BGR2GRAY)

    # Morphological closing: fills small gaps in bezel/frame edges
    # Larger kernel = better for thin bezels; too large loses thin screens
    close_k = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    closed = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, close_k)
    blurred = cv2.GaussianBlur(closed, (5, 5), 0)

    thresholds = [(50, 150), (30, 100), (80, 200), (20, 80)]

    for low, high in thresholds:
        edges = cv2.Canny(blurred, low, high)

        # Dilate edges to connect nearby edge fragments
        dil_k = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        dilated = cv2.dilate(edges, dil_k, iterations=2)

        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)

        for contour in contours[:25]:
            peri = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * peri, True)

            if len(approx) == 4:
                area = cv2.contourArea(approx)
                # Screen must cover 8%–95% of the image
                if 0.08 * image_area < area < 0.95 * image_area:
                    if is_valid_screen_shape(approx, image_np):
                        coverage = area / image_area
                        logger.debug(
                            f"Screen found: thresh=({low},{high}) "
                            f"coverage={coverage:.2%}"
                        )
                        return approx

    return None


def perspective_correct(image_np: np.ndarray, corners: np.ndarray) -> np.ndarray:
    """
    Apply a 4-point perspective transform to produce a flat, undistorted screen crop.

    Includes a bounds sanity check: if the computed output exceeds 1.5× the
    input dimension in any direction, the transform is likely incorrect and
    the original image is returned.
    """
    pts = order_points(corners.reshape(4, 2).astype("float32"))
    (tl, tr, br, bl) = pts

    widthA  = float(np.linalg.norm(br - bl))
    widthB  = float(np.linalg.norm(tr - tl))
    maxWidth = max(int(widthA), int(widthB))

    heightA  = float(np.linalg.norm(tr - br))
    heightB  = float(np.linalg.norm(tl - bl))
    maxHeight = max(int(heightA), int(heightB))

    if maxWidth < 50 or maxHeight < 50:
        logger.warning("Perspective correction skipped: output dimensions too small")
        return image_np

    # Sanity check: output can't be much larger than input (catches degenerate transforms)
    ih, iw = image_np.shape[:2]
    if maxWidth > iw * 1.6 or maxHeight > ih * 1.6:
        logger.warning(
            f"Perspective correction skipped: output {maxWidth}x{maxHeight} "
            f"unreasonably large for input {iw}x{ih}"
        )
        return image_np

    dst = np.array([
        [0,           0],
        [maxWidth - 1, 0],
        [maxWidth - 1, maxHeight - 1],
        [0,           maxHeight - 1],
    ], dtype="float32")

    M = cv2.getPerspectiveTransform(pts, dst)
    warped = cv2.warpPerspective(image_np, M, (maxWidth, maxHeight))
    return warped


def compute_confidence(corners: np.ndarray, image_np: np.ndarray) -> float:
    """Confidence 0.0–1.0 derived from screen-to-image area coverage ratio."""
    h, w = image_np.shape[:2]
    image_area = h * w
    screen_area = float(cv2.contourArea(corners))
    coverage = screen_area / image_area

    if   coverage < 0.08:               return 0.30
    elif 0.08  <= coverage < 0.15:      return 0.55
    elif 0.15  <= coverage <= 0.80:     return 0.92
    elif 0.80  < coverage  <= 0.95:     return 0.60
    else:                               return 0.40


def process_image(image_np: np.ndarray) -> Tuple[np.ndarray, dict]:
    """
    Full screen processing pipeline.

    Returns:
        (processed_image, detection_info)
        - Screen found:   cropped + perspective-corrected image
        - Not found:      original image (treated as a direct screenshot)
    """
    corners = detect_screen(image_np)

    if corners is not None:
        confidence = compute_confidence(corners, image_np)
        bbox = cv2.boundingRect(corners)
        processed = perspective_correct(image_np, corners)

        return processed, {
            "screen_detected": True,
            "confidence": round(confidence, 2),
            "bbox": {
                "x": int(bbox[0]), "y": int(bbox[1]),
                "w": int(bbox[2]), "h": int(bbox[3]),
            },
            "corners": corners.reshape(4, 2).tolist(),
        }

    logger.info("No screen boundary detected — using full image (screenshot mode).")
    return image_np, {
        "screen_detected": False,
        "confidence": 0.0,
        "bbox": None,
        "corners": None,
    }
