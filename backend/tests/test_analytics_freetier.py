"""
Backend tests for Lensora analytics, free-tier, and feedback endpoints.
Tests anonymous usage tracking, limit enforcement, and feedback system.
"""
import pytest
import requests
import os
import io
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "lensora"


@pytest.fixture(scope="module", autouse=True)
def seed_and_cleanup():
    """Seed test data and cleanup after tests."""
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    # Seed anon_enforce_ui with count=3
    db.anonymous_usage.update_one(
        {"anonymous_id": "anon_enforce_ui"},
        {"$set": {"anonymous_id": "anon_enforce_ui", "analysis_count": 3}},
        upsert=True,
    )
    # Ensure fresh anon exists with count=0 (or doesn't exist)
    db.anonymous_usage.delete_one({"anonymous_id": "anon_test_fresh"})
    # Clean up feedback test data
    db.analysis_feedback.delete_many({"analysis_event_id": "test-event-123"})
    yield
    # Cleanup
    db.anonymous_usage.delete_one({"anonymous_id": "anon_enforce_ui"})
    db.anonymous_usage.delete_one({"anonymous_id": "anon_test_fresh"})
    db.analysis_feedback.delete_many({"analysis_event_id": "test-event-123"})
    client.close()


class TestAnonymousCheck:
    """Tests for GET /api/anonymous/check"""

    def test_fresh_anonymous_check(self):
        """Fresh anonymous ID should show full allowance."""
        r = requests.get(f"{BASE_URL}/api/anonymous/check", params={"anonymous_id": "anon_test_fresh"})
        assert r.status_code == 200
        data = r.json()
        assert data["can_scan"] is True
        assert data["analysis_count"] == 0
        assert data["analyses_remaining"] == 3
        assert data["limit"] == 3
        print("PASS: fresh anonymous check returns correct data")

    def test_exhausted_anonymous_check(self):
        """Seeded anon_enforce_ui (count=3) should show no remaining."""
        r = requests.get(f"{BASE_URL}/api/anonymous/check", params={"anonymous_id": "anon_enforce_ui"})
        assert r.status_code == 200
        data = r.json()
        assert data["can_scan"] is False
        assert data["analyses_remaining"] == 0
        print("PASS: exhausted anonymous check returns can_scan=false")


class TestAnalyzeEndpoint:
    """Tests for POST /api/analyze"""

    def _make_dummy_image(self):
        """Create a minimal JPEG-like bytes for upload."""
        return io.BytesIO(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

    def test_anonymous_user_gets_503_not_401(self):
        """Anonymous user (no token) should get 503 (no API key), not 401."""
        img = self._make_dummy_image()
        r = requests.post(
            f"{BASE_URL}/api/analyze",
            files={"file": ("test.jpg", img, "image/jpeg")},
            data={"anonymous_id": "anon_test_fresh"},
        )
        assert r.status_code == 503, f"Expected 503, got {r.status_code}: {r.text}"
        print(f"PASS: anonymous user gets 503 (no API key configured)")

    def test_anonymous_limit_enforced_403(self):
        """Seeded user with count=3 should get 403 with limit message."""
        img = self._make_dummy_image()
        r = requests.post(
            f"{BASE_URL}/api/analyze",
            files={"file": ("test.jpg", img, "image/jpeg")},
            data={"anonymous_id": "anon_enforce_ui"},
        )
        assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"
        detail = r.json().get("detail", "")
        assert "Free analysis limit reached" in detail, f"Unexpected detail: {detail}"
        print("PASS: limit enforcement returns 403 with correct message")

    def test_invalid_jwt_returns_503_not_401(self):
        """
        With SUPABASE_JWT_SECRET not set, providing any token → 503.
        The system can't verify the token, so it returns 503 (not 401).
        """
        r = requests.post(
            f"{BASE_URL}/api/analyze",
            headers={"Authorization": "Bearer bad.token.here"},
            files={"file": ("test.jpg", self._make_dummy_image(), "image/jpeg")},
        )
        # Per spec: SUPABASE_JWT_SECRET not set → 503
        assert r.status_code == 503, f"Expected 503, got {r.status_code}: {r.text}"
        print(f"PASS: invalid JWT with no secret configured returns 503")


class TestFeedbackEndpoint:
    """Tests for POST /api/feedback"""

    def test_feedback_missing_event_id(self):
        """Missing event_id should return 400."""
        r = requests.post(
            f"{BASE_URL}/api/feedback",
            json={"feedback": "correct", "anonymous_id": "anon_abc"},
        )
        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
        print("PASS: missing event_id returns 400")

    def test_feedback_invalid_value(self):
        """Invalid feedback value should return 400."""
        r = requests.post(
            f"{BASE_URL}/api/feedback",
            json={"event_id": "test-event-123", "feedback": "maybe", "anonymous_id": "anon_abc"},
        )
        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
        print("PASS: invalid feedback value returns 400")

    def test_feedback_valid_submission(self):
        """Valid feedback submission should return {success: true}."""
        r = requests.post(
            f"{BASE_URL}/api/feedback",
            json={"event_id": "test-event-123", "feedback": "correct", "anonymous_id": "anon_abc"},
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert data.get("success") is True
        print("PASS: valid feedback returns success=true")

    def test_feedback_duplicate_returns_409(self):
        """Submitting feedback for same event_id again should return 409."""
        r = requests.post(
            f"{BASE_URL}/api/feedback",
            json={"event_id": "test-event-123", "feedback": "incorrect", "anonymous_id": "anon_abc"},
        )
        assert r.status_code == 409, f"Expected 409, got {r.status_code}: {r.text}"
        print("PASS: duplicate feedback returns 409")
