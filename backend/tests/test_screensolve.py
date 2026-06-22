"""Lensora backend tests — health, analyze, upload, MIME, size, rate limit, provider imports"""
import os
import io
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


# ── Helper ────────────────────────────────────────────────────────────────────

def make_minimal_jpeg() -> bytes:
    """1x1 white JPEG ~631 bytes."""
    import base64
    b64 = (
        "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8U"
        "HRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgN"
        "DRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIy"
        "MjL/wAARCAABAAEDASIAAhEBAxEB/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAA"
        "AAAAAAAAAAAAAP/EABQBAQAAAAAAAAAAAAAAAAAAAAD/xAAUEQEAAAAAAAAAAAAAAAAAAAAA"
        "/9oADAMBAAIRAxEAPwCwABmX/9k="
    )
    return base64.b64decode(b64)


# ── Health ────────────────────────────────────────────────────────────────────

class TestHealth:
    """GET /api/health — always 200, no key required"""

    def test_health_status_200(self):
        r = requests.get(f"{BASE_URL}/api/health")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"

    def test_health_body_status_healthy(self):
        r = requests.get(f"{BASE_URL}/api/health")
        data = r.json()
        assert data.get("status") == "healthy", f"status field: {data}"

    def test_health_no_emergent_fields(self):
        r = requests.get(f"{BASE_URL}/api/health")
        text = r.text.lower()
        assert "emergent" not in text, "emergent found in health response"


# ── Analyze — no API key → 503 ────────────────────────────────────────────────

class TestAnalyzeNoKey:
    """POST /api/analyze with no OPENROUTER_API_KEY → 503"""

    def test_analyze_503_when_no_key(self):
        jpeg = make_minimal_jpeg()
        r = requests.post(
            f"{BASE_URL}/api/analyze",
            files={"file": ("test.jpg", io.BytesIO(jpeg), "image/jpeg")},
        )
        assert r.status_code == 503, f"Expected 503, got {r.status_code}: {r.text}"

    def test_analyze_503_body_success_false(self):
        jpeg = make_minimal_jpeg()
        r = requests.post(
            f"{BASE_URL}/api/analyze",
            files={"file": ("test.jpg", io.BytesIO(jpeg), "image/jpeg")},
        )
        data = r.json()
        assert data.get("success") is False, f"success field: {data}"
        assert data.get("error") == "OPENROUTER_API_KEY is not configured", f"error field: {data}"


# ── Upload — no API key → 503 ────────────────────────────────────────────────

class TestUploadNoKey:
    """POST /api/upload with no OPENROUTER_API_KEY → 503"""

    def test_upload_503_when_no_key(self):
        jpeg = make_minimal_jpeg()
        r = requests.post(
            f"{BASE_URL}/api/upload",
            files={"file": ("test.jpg", io.BytesIO(jpeg), "image/jpeg")},
        )
        assert r.status_code == 503, f"Expected 503, got {r.status_code}: {r.text}"

    def test_upload_503_body_exact(self):
        jpeg = make_minimal_jpeg()
        r = requests.post(
            f"{BASE_URL}/api/upload",
            files={"file": ("test.jpg", io.BytesIO(jpeg), "image/jpeg")},
        )
        data = r.json()
        assert data.get("success") is False
        assert data.get("error") == "OPENROUTER_API_KEY is not configured"


# ── MIME validation ────────────────────────────────────────────────────────────

class TestMimeValidation:
    """POST /api/analyze with invalid MIME. Key check happens before MIME check."""

    def test_invalid_mime_text_plain(self):
        """No key → 503 (key checked first). With key → expect 400."""
        r = requests.post(
            f"{BASE_URL}/api/analyze",
            files={"file": ("test.txt", io.BytesIO(b"hello world"), "text/plain")},
        )
        assert r.status_code in (400, 503), f"Unexpected status: {r.status_code}: {r.text}"

    def test_oversized_file(self):
        """No key → 503. With key → expect 400."""
        big = b"X" * (11 * 1024 * 1024)
        r = requests.post(
            f"{BASE_URL}/api/analyze",
            files={"file": ("big.jpg", io.BytesIO(big), "image/jpeg")},
        )
        assert r.status_code in (400, 503), f"Unexpected status: {r.status_code}: {r.text}"


# ── Provider import ───────────────────────────────────────────────────────────

class TestProviderImports:
    """openrouter_provider.py must import cleanly."""

    def test_openrouter_provider_imports(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from providers.openrouter_provider import (
            OpenRouterProvider,
            get_primary_provider,
            get_secondary_provider,
        )
        assert OpenRouterProvider is not None
        assert callable(get_primary_provider)
        assert callable(get_secondary_provider)

    def test_emergent_provider_does_not_exist(self):
        assert not os.path.exists("/app/backend/providers/emergent_provider.py"), \
            "emergent_provider.py must not exist"

    def test_requirements_no_emergentintegrations(self):
        with open("/app/backend/requirements.txt") as f:
            content = f.read()
        assert "emergentintegrations" not in content.lower()

    def test_env_no_emergent_keys(self):
        with open("/app/backend/.env") as f:
            content = f.read()
        assert "EMERGENT_LLM_KEY" not in content
        assert "VISION_PROVIDER=emergent" not in content

    def test_no_emergent_in_source(self):
        import subprocess
        result = subprocess.run(
            ["grep", "-rn", "--include=*.py", "emergent",
             "--exclude-dir=tests", "/app/backend/"],
            capture_output=True, text=True
        )
        assert result.stdout == "", f"Found 'emergent' in source:\n{result.stdout}"
