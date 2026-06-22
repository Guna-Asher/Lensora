"""Image quality validation.

Validates processed screen images before sending to Vision AI.
Catches common issues: blur, poor lighting, low resolution, no contrast.
"""

import cv2
import numpy as np
import logging
from typing import Tuple

logger = logging.getLogger("lensora.image_validator")

# Thresholds
MIN_PIXELS = 40_000        # ~200x200 minimum
MIN_BLUR_SCORE = 40.0      # Laplacian variance
MIN_BRIGHTNESS = 18.0      # Mean pixel value (0-255)
MAX_BRIGHTNESS = 242.0
MIN_CONTRAST = 8.0


def is_borderline_quality(image_np: np.ndarray) -> bool:
    """
    Return True when image quality is valid but close enough to thresholds
    that a second-opinion model pass is worthwhile.

    Borderline bands:
      blur:        40–100  (valid min is 40; under 100 is still fuzzy)
      brightness:  18–54   (valid min is 18; under 54 can hide detail)
                   210–242 (approaching overexposed ceiling of 242)
      contrast:    8–20    (valid min is 8; under 20 is low-contrast content)
    """
    gray = cv2.cvtColor(image_np, cv2.COLOR_BGR2GRAY)
    blur_score  = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness  = float(np.mean(gray))
    contrast    = float(np.std(gray))

    borderline = (
        MIN_BLUR_SCORE   <= blur_score  < MIN_BLUR_SCORE * 2.5    # 40–100
        or MIN_BRIGHTNESS <= brightness < MIN_BRIGHTNESS * 3.0    # 18–54
        or MAX_BRIGHTNESS * 0.87 < brightness <= MAX_BRIGHTNESS   # 210–242
        or MIN_CONTRAST   <= contrast   < MIN_CONTRAST * 2.5      # 8–20
    )
    if borderline:
        logger.debug(
            f"Borderline quality: blur={blur_score:.1f} "
            f"brightness={brightness:.1f} contrast={contrast:.1f}"
        )
    return borderline         # Std deviation of grayscale


def validate_image_quality(image_np: np.ndarray) -> Tuple[bool, str]:
    """
    Validate image quality for vision analysis.

    Returns:
        (is_valid: bool, error_message: str)
        error_message is empty string when is_valid is True.
    """
    h, w = image_np.shape[:2]
    total_pixels = h * w

    # Resolution check
    if total_pixels < MIN_PIXELS:
        logger.info(f"Resolution too low: {w}x{h}={total_pixels}px")
        return False, "Image resolution is too low. Please use a higher quality photo."

    gray = cv2.cvtColor(image_np, cv2.COLOR_BGR2GRAY)

    # Blur detection via Laplacian variance
    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if blur_score < MIN_BLUR_SCORE:
        logger.info(f"Image too blurry: blur_score={blur_score:.2f}")
        return False, "Screen is out of focus. Please hold your device steady and retake."

    # Brightness check
    brightness = float(np.mean(gray))
    if brightness < MIN_BRIGHTNESS:
        logger.info(f"Image too dark: brightness={brightness:.1f}")
        return False, "Screen is too dark. Ensure the screen is on and well-lit, then retake."
    if brightness > MAX_BRIGHTNESS:
        logger.info(f"Image overexposed: brightness={brightness:.1f}")
        return False, "Image is overexposed. Reduce glare or angle and retake."

    # Contrast check (screen must have visible content)
    contrast = float(np.std(gray))
    if contrast < MIN_CONTRAST:
        logger.info(f"Low contrast: contrast={contrast:.2f}")
        return False, "Screen content not visible. Ensure the screen is on and showing content."

    logger.debug(f"Quality OK: {w}x{h} blur={blur_score:.1f} brightness={brightness:.1f} contrast={contrast:.1f}")
    return True, ""
