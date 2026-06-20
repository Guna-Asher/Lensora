"""ScreenSolve API tests - health, analyze, upload endpoints"""
import pytest
import requests
import os
import io
import base64
from PIL import Image

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


def make_test_image(format="JPEG"):
    """Create a real test image with visible text-like content."""
    img = Image.new("RGB", (400, 300), color=(255, 255, 255))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    # Draw some text-like black rectangles to simulate content
    draw.rectangle([20, 20, 380, 60], fill=(0, 0, 0))
    draw.rectangle([20, 80, 280, 100], fill=(50, 50, 50))
    draw.rectangle([20, 120, 320, 140], fill=(50, 50, 50))
    draw.rectangle([20, 160, 260, 180], fill=(50, 50, 50))
    draw.text((30, 25), "Q1: What is 2+2?", fill=(255, 255, 255))
    draw.text((30, 85), "A) 3   B) 4   C) 5   D) 6", fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format=format)
    buf.seek(0)
    return buf


class TestHealth:
    """Health endpoint tests"""

    def test_health_returns_200(self):
        res = requests.get(f"{BASE_URL}/api/health")
        assert res.status_code == 200

    def test_health_response_structure(self):
        res = requests.get(f"{BASE_URL}/api/health")
        data = res.json()
        assert data["status"] == "healthy"
        assert data["service"] == "ScreenSolve API"


class TestAnalyze:
    """POST /api/analyze tests"""

    def test_analyze_returns_success(self):
        buf = make_test_image("JPEG")
        res = requests.post(
            f"{BASE_URL}/api/analyze",
            files={"file": ("test.jpg", buf, "image/jpeg")},
            data={"explain": "false"},
            timeout=60
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True

    def test_analyze_response_fields(self):
        buf = make_test_image("JPEG")
        res = requests.post(
            f"{BASE_URL}/api/analyze",
            files={"file": ("test.jpg", buf, "image/jpeg")},
            data={"explain": "false"},
            timeout=60
        )
        data = res.json()
        assert "answers" in data
        assert "screen_detected" in data
        assert "confidence" in data
        assert "processing_time_ms" in data
        assert "model_used" in data

    def test_analyze_invalid_file_type_returns_400(self):
        content = b"This is a text file."
        res = requests.post(
            f"{BASE_URL}/api/analyze",
            files={"file": ("test.txt", io.BytesIO(content), "text/plain")},
            timeout=10
        )
        assert res.status_code == 400

    def test_analyze_with_explain_true(self):
        buf = make_test_image("JPEG")
        res = requests.post(
            f"{BASE_URL}/api/analyze",
            files={"file": ("test.jpg", buf, "image/jpeg")},
            data={"explain": "true"},
            timeout=60
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "answers" in data

    def test_analyze_png_image(self):
        buf = make_test_image("PNG")
        res = requests.post(
            f"{BASE_URL}/api/analyze",
            files={"file": ("test.png", buf, "image/png")},
            timeout=60
        )
        assert res.status_code == 200


class TestUpload:
    """POST /api/upload tests"""

    def test_upload_works_same_as_analyze(self):
        buf = make_test_image("JPEG")
        res = requests.post(
            f"{BASE_URL}/api/upload",
            files={"file": ("test.jpg", buf, "image/jpeg")},
            data={"explain": "false"},
            timeout=60
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "answers" in data
