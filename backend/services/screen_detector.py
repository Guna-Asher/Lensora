"""Screen detection, cropping, and perspective correction using OpenCV.

Pipeline:
1. Grayscale + Gaussian blur
2. Canny edge detection (multi-threshold)
3. Contour analysis for quadrilateral screens
4. Perspective transform to flatten/straighten

Detects: laptop screens, desktop monitors, phone screens, tablet screens.
Ignores: keyboard, hands, desk, room background, monitor bezels.
"""

import cv2
import numpy as np
import logging
from typing import Optional, Tuple

logger = logging.getLogger("screensolve.screen_detector")


def order_points(pts: np.ndarray) -> np.ndarray:
    """Order corner points: top-left, top-right, bottom-right, bottom-left."""
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]   # top-left: smallest x+y
    rect[2] = pts[np.argmax(s)]   # bottom-right: largest x+y
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]  # top-right: smallest y-x
    rect[3] = pts[np.argmax(diff)]  # bottom-left: largest y-x
    return rect


def detect_screen(image_np: np.ndarray) -> Optional[np.ndarray]:
    """
    Find the largest rectangular screen region in the image.
    Tries multiple edge detection thresholds for robustness.
    Returns 4-corner contour array or None if not found.
    """
    h, w = image_np.shape[:2]
    image_area = h * w

    gray = cv2.cvtColor(image_np, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    thresholds = [(50, 150), (30, 100), (80, 200), (20, 80)]

    for low, high in thresholds:
        edges = cv2.Canny(blurred, low, high)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        dilated = cv2.dilate(edges, kernel, iterations=2)

        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)

        for contour in contours[:20]:
            peri = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * peri, True)

            if len(approx) == 4:
                area = cv2.contourArea(approx)
                # Screen must cover 8% to 95% of the image area
                if 0.08 * image_area < area < 0.95 * image_area:
                    coverage = area / image_area
                    logger.debug(f"Screen detected: thresh=({low},{high}) coverage={coverage:.2%}")
                    return approx

    return None


def perspective_correct(image_np: np.ndarray, corners: np.ndarray) -> np.ndarray:
    """Apply perspective transform to produce a flat, undistorted screen crop."""
    pts = order_points(corners.reshape(4, 2).astype("float32"))
    (tl, tr, br, bl) = pts

    widthA = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
    widthB = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
    maxWidth = max(int(widthA), int(widthB))

    heightA = np.sqrt(((tr[0] - br[0]) ** 2) + ((tr[1] - br[1]) ** 2))
    heightB = np.sqrt(((tl[0] - bl[0]) ** 2) + ((tl[1] - bl[1]) ** 2))
    maxHeight = max(int(heightA), int(heightB))

    if maxWidth < 50 or maxHeight < 50:
        logger.warning("Perspective correction skipped: computed dimensions too small")
        return image_np

    dst = np.array([
        [0, 0],
        [maxWidth - 1, 0],
        [maxWidth - 1, maxHeight - 1],
        [0, maxHeight - 1]
    ], dtype="float32")

    M = cv2.getPerspectiveTransform(pts, dst)
    warped = cv2.warpPerspective(image_np, M, (maxWidth, maxHeight))
    return warped


def compute_confidence(corners: np.ndarray, image_np: np.ndarray) -> float:
    """Estimate detection confidence based on screen coverage ratio."""
    h, w = image_np.shape[:2]
    image_area = h * w
    screen_area = float(cv2.contourArea(corners))
    coverage = screen_area / image_area

    if coverage < 0.08:
        return 0.30
    elif 0.08 <= coverage < 0.15:
        return 0.55
    elif 0.15 <= coverage <= 0.80:
        return 0.90
    elif 0.80 < coverage <= 0.95:
        return 0.60
    else:
        return 0.40


def process_image(image_np: np.ndarray) -> Tuple[np.ndarray, dict]:
    """
    Full screen processing pipeline.

    Returns:
        (processed_image, detection_info)
        - If screen found: cropped + perspective-corrected image
        - If not found: original image (likely a screenshot already cropped)
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
                "w": int(bbox[2]), "h": int(bbox[3])
            },
            "corners": corners.reshape(4, 2).tolist()
        }

    # No screen boundary found — treat full image as the screen content
    logger.info("No screen boundary detected. Using full image (assumed screenshot).")
    return image_np, {
        "screen_detected": False,
        "confidence": 0.0,
        "bbox": None,
        "corners": None
    }
