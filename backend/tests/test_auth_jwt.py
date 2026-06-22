"""Auth JWT middleware tests for Lensora — iteration 4"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


class TestHealthPublic:
    """Health endpoint — must be publicly accessible"""

    def test_health_returns_200(self):
        r = requests.get(f"{BASE_URL}/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "healthy"
        print("PASS: /api/health returns 200")


class TestAnalyzeWithoutToken:
    """POST /api/analyze — SUPABASE_JWT_SECRET is blank → expect 503"""

    def test_analyze_no_token_returns_503(self):
        # Send a minimal fake image file
        import io
        fake_img = io.BytesIO(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
        r = requests.post(
            f"{BASE_URL}/api/analyze",
            files={"file": ("test.jpg", fake_img, "image/jpeg")},
        )
        assert r.status_code == 503, f"Expected 503 got {r.status_code}: {r.text}"
        detail = r.json().get("detail", "")
        assert "SUPABASE_JWT_SECRET" in detail, f"Unexpected detail: {detail}"
        print(f"PASS: /api/analyze no token → 503. detail={detail}")


class TestUploadWithoutToken:
    """POST /api/upload — same JWT check → expect 503"""

    def test_upload_no_token_returns_503(self):
        import io
        fake_img = io.BytesIO(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
        r = requests.post(
            f"{BASE_URL}/api/upload",
            files={"file": ("test.jpg", fake_img, "image/jpeg")},
        )
        assert r.status_code == 503, f"Expected 503 got {r.status_code}: {r.text}"
        detail = r.json().get("detail", "")
        assert "SUPABASE_JWT_SECRET" in detail, f"Unexpected detail: {detail}"
        print(f"PASS: /api/upload no token → 503. detail={detail}")
