"""Lensora - FastAPI Backend"""
import os
import sys
import re
import json
import uuid
import time
import logging
import tempfile
from pathlib import Path
from typing import Optional, Tuple
from difflib import SequenceMatcher
from datetime import datetime, timezone

from fastapi import FastAPI, APIRouter, File, Form, UploadFile, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import httpx
import jwt
from motor.motor_asyncio import AsyncIOMotorClient
import numpy as np
import cv2

ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))
load_dotenv(ROOT_DIR / ".env")

from providers.openrouter_provider import get_primary_provider, get_secondary_provider
from services.screen_detector import process_image
from services.image_validator import validate_image_quality, is_borderline_quality

# Structured JSON logging
logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "msg": "%(message)s"}'
)
logger = logging.getLogger("lensora")

app = FastAPI(
    title="Lensora API",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json"
)
api_router = APIRouter(prefix="/api")

# Configuration
MAX_FILE_SIZE_MB = int(os.environ.get("MAX_FILE_SIZE_MB", "10"))
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/jpg"}
ENABLE_VERIFICATION = os.environ.get("ENABLE_VERIFICATION", "false").lower() == "true"
LARGE_QUESTION_THRESHOLD = int(os.environ.get("LARGE_QUESTION_THRESHOLD", "5"))

# Rate limiting (in-memory, per IP)
_rate_store: dict = {}
RATE_MAX = 30
RATE_WINDOW = 60

# Supabase JWT auth
_http_bearer = HTTPBearer(auto_error=False)
SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")

# Free tier
FREE_SCAN_LIMIT = 3

# MongoDB (motor async client — lazy init)
_mongo_client: Optional[AsyncIOMotorClient] = None


def _get_db():
    """Return async MongoDB handle, or None if MONGO_URL is not set."""
    global _mongo_client
    mongo_url = os.environ.get("MONGO_URL", "")
    if not mongo_url:
        return None
    if _mongo_client is None:
        _mongo_client = AsyncIOMotorClient(mongo_url)
    return _mongo_client[os.environ.get("DB_NAME", "lensora")]


async def get_auth_context(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
) -> dict:
    """
    Optional auth dependency — used on /analyze and /upload.

    Behavior:
      - No token       → anonymous  {"user_id": None,  "authenticated": False}
      - Valid JWT      → auth user  {"user_id": <sub>, "authenticated": True}
      - Invalid JWT    → HTTP 401   (NEVER treated as anonymous)
      - Auth not configured + token present → HTTP 503
    """
    if credentials is None:
        return {"user_id": None, "authenticated": False}
    if not SUPABASE_JWT_SECRET:
        raise HTTPException(
            status_code=503,
            detail="Authentication is not configured. Set SUPABASE_JWT_SECRET.",
        )
    try:
        payload = jwt.decode(
            credentials.credentials,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
        return {"user_id": payload.get("sub"), "authenticated": True}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired.")
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")


def check_rate_limit(client_ip: str) -> bool:
    now = time.time()
    _rate_store.setdefault(client_ip, [])
    _rate_store[client_ip] = [t for t in _rate_store[client_ip] if now - t < RATE_WINDOW]
    if len(_rate_store[client_ip]) >= RATE_MAX:
        return False
    _rate_store[client_ip].append(now)
    return True


def get_client_ip(request: Request) -> str:
    fwd = request.headers.get("X-Forwarded-For")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def resolve_answers(image_path: str, answer_a: str, answer_b: str) -> tuple:
    """Compare two answers; run verification pass if they differ."""
    a_clean = answer_a.strip().lower()
    b_clean = answer_b.strip().lower()
    ratio = SequenceMatcher(None, a_clean, b_clean).ratio()

    if ratio >= 0.70:
        return answer_a, True

    # Verification pass: ask primary to decide
    primary = get_primary_provider()
    verified = await primary.verify(image_path, answer_a, answer_b)
    return verified, True


def parse_gpt_metadata(raw: str) -> Tuple[bool, bool, int, str]:
    """
    Parse compact JSON metadata from the first line of a GPT response.

    GPT-5 is instructed to begin every response with:
        {"c":"SIMPLE","u":false,"n":3}

    Fields:
        c  — "COMPLEX" | "SIMPLE"
        u  — true | false  (uncertain)
        n  — integer question count

    Returns:
        (is_uncertain, is_complex, question_count, clean_answer)

    This metadata is INTERNAL. It is never forwarded to end users.
    """
    lines = raw.strip().split("\n")
    meta: dict = {"c": "SIMPLE", "u": False, "n": 0}
    answer_start = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                meta = json.loads(stripped)
                answer_start = i + 1
                break
            except json.JSONDecodeError:
                # Fallback: regex-extract the JSON object
                match = re.search(r"\{[^}]+\}", stripped)
                if match:
                    try:
                        meta = json.loads(match.group())
                        answer_start = i + 1
                        break
                    except json.JSONDecodeError:
                        pass

    # Skip blank separator lines
    while answer_start < len(lines) and not lines[answer_start].strip():
        answer_start += 1

    clean = "\n".join(lines[answer_start:]).strip()

    is_complex = str(meta.get("c", "SIMPLE")).upper() == "COMPLEX"
    is_uncertain = bool(meta.get("u", False))
    question_count = int(meta.get("n", 0))

    return is_uncertain, is_complex, question_count, clean


def pick_verification_reason(
    enable_verification_env: bool,
    is_uncertain: bool,
    is_complex: bool,
    borderline: bool,
    question_count: int,
) -> Optional[str]:
    """
    Return the verification trigger reason, or None if no verification needed.

    Priority order:
      1. Explicit config  (ENABLE_VERIFICATION=true)
      2. GPT-5 uncertainty flag
      3. Complex question type  (puzzle / logic / data / math)
      4. Large question set     (≥ LARGE_QUESTION_THRESHOLD, default 5)
      5. Borderline image quality
    """
    if enable_verification_env:
        return "config"
    if is_uncertain:
        return "gpt5_uncertainty"
    if is_complex:
        return "complex_question_type"
    if question_count >= LARGE_QUESTION_THRESHOLD:
        return "large_question_set"
    if borderline:
        return "borderline_quality"
    return None


async def run_analysis(file: UploadFile, explain: bool, request_id: str) -> dict:
    """Core pipeline: validate → detect → crop → validate quality → analyze."""
    start = time.time()

    # MIME validation
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{content_type}'. Allowed: JPEG, PNG, WEBP"
        )

    content = await file.read()

    # File size validation
    if len(content) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum: {MAX_FILE_SIZE_MB}MB"
        )

    # Decode image
    np_arr = np.frombuffer(content, np.uint8)
    image_np = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if image_np is None:
        raise HTTPException(status_code=400, detail="Invalid or corrupted image data")

    logger.info(f"rid={request_id} shape={image_np.shape} size={len(content)//1024}KB")

    # Screen detection + perspective correction (two-stage pipeline)
    processed, detection = process_image(image_np)

    # Log internal timing metrics (never exposed to users)
    _t = detection.get("_timing", {})
    logger.info(
        f"rid={request_id} screen_detected={detection['screen_detected']} "
        f"conf={detection['confidence']} tilt={detection.get('tilt_angle_deg', 0)}° "
        f"detect={_t.get('detection_ms', 0)}ms warp={_t.get('warp_ms', 0)}ms "
        f"preprocess={_t.get('total_ms', 0)}ms"
    )

    # Angle check: reject shots that are too steep to analyze accurately
    tilt_angle = detection.get("tilt_angle_deg", 0.0)
    if detection["screen_detected"] and tilt_angle >= 60.0:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Screen angle is too steep ({tilt_angle:.0f}°) to analyze accurately. "
                "Please retake from a more direct angle (under 60°)."
            )
        )

    # Image quality check + borderline detection
    is_valid, quality_msg = validate_image_quality(processed)
    if not is_valid:
        raise HTTPException(status_code=400, detail=quality_msg)
    borderline = is_borderline_quality(processed)

    # Save to temp file
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp_path = tmp.name
        cv2.imwrite(tmp_path, processed, [cv2.IMWRITE_JPEG_QUALITY, 95])

    try:
        primary = get_primary_provider()

        # Step 1: GPT-5 primary analysis (always runs)
        raw_answer = await primary.analyze(tmp_path, explain)

        # Step 2: Parse self-reported JSON metadata (internal — never forwarded to users)
        is_uncertain, is_complex, question_count, clean_answer = parse_gpt_metadata(raw_answer)

        logger.info(
            f"rid={request_id} uncertain={is_uncertain} "
            f"complex={is_complex} qcount={question_count} borderline={borderline}"
        )

        # Step 3: Smart verification trigger
        verification_reason = pick_verification_reason(
            ENABLE_VERIFICATION, is_uncertain, is_complex, borderline, question_count
        )

        if verification_reason:
            secondary = get_secondary_provider()
            raw_b = await secondary.analyze(tmp_path, explain)
            _, _, _, clean_b = parse_gpt_metadata(raw_b)
            final_answer, _ = await resolve_answers(tmp_path, clean_answer, clean_b)
            verification_used = True
            logger.info(f"rid={request_id} verification triggered reason={verification_reason}")
        else:
            final_answer = clean_answer
            verification_used = False

        ms = int((time.time() - start) * 1000)
        logger.info(f"rid={request_id} ms={ms} verified={verification_used}")

        response: dict = {
            "success": True,
            "answers": final_answer,
            "screen_detected": detection["screen_detected"],
            "confidence": detection["confidence"],
            "processing_time_ms": ms,
            "model_used": primary.model_name,
            "verification_used": verification_used,
            "explained": explain,
        }

        # Add caution flag for borderline angles (50°–60°) without rejecting
        tilt = detection.get("tilt_angle_deg", 0.0)
        if 50.0 <= tilt < 60.0:
            response["angle_caution"] = True
            response["angle_caution_msg"] = (
                f"Screen captured at a steep angle ({tilt:.0f}°). "
                "Results may be less accurate. Consider retaking more directly."
            )

        return response
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


async def _create_analysis_event(db, **kwargs) -> str:
    """Insert one analysis_events document and return its event_id."""
    event_id = str(uuid.uuid4())
    await db.analysis_events.insert_one({
        "event_id": event_id,
        "created_at": datetime.now(timezone.utc),
        **kwargs,
    })
    return event_id


async def _tracked_analyze(
    request: Request,
    file: UploadFile,
    explain: bool,
    anonymous_id: Optional[str],
    auth: dict,
    endpoint: str,
) -> dict:
    """
    Thin wrapper around run_analysis() that adds:
      1. Rate limiting                (existing logic, untouched)
      2. Anonymous limit enforcement  (NEW — backend source of truth, BEFORE run_analysis)
      3. OPENROUTER_API_KEY check     (existing logic, untouched)
      4. run_analysis()               (READ-ONLY — not modified)
      5. Post-success analytics       (NEW — only reached when run_analysis succeeds)
    """
    request_id = str(uuid.uuid4())[:8]
    client_ip = get_client_ip(request)

    if not check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please wait and retry.")

    logger.info(
        f"rid={request_id} endpoint={endpoint} ip={client_ip} "
        f"authenticated={auth['authenticated']}"
    )

    # ── Anonymous limit enforcement (backend source of truth) ──────────────
    db = _get_db()
    if not auth["authenticated"] and anonymous_id and db is not None:
        doc = await db.anonymous_usage.find_one({"anonymous_id": anonymous_id})
        current_count = doc["analysis_count"] if doc else 0
        if current_count >= FREE_SCAN_LIMIT:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Free analysis limit reached ({FREE_SCAN_LIMIT} scans). "
                    "Create a free account to continue."
                ),
            )

    if not os.environ.get("OPENROUTER_API_KEY"):
        return JSONResponse(
            status_code=503,
            content={"success": False, "error": "OPENROUTER_API_KEY is not configured"},
        )

    # ── Core pipeline — error-handled wrapper (run_analysis is READ-ONLY) ────
    try:
        result = await run_analysis(file, explain, request_id)
    except HTTPException:
        raise  # 400s from run_analysis (bad file, quality, angle) pass through
    except httpx.TimeoutException as exc:
        logger.warning(f"rid={request_id} OpenRouter timeout: {exc}")
        raise HTTPException(
            status_code=504,
            detail="Vision AI request timed out. Please try again.",
        )
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        logger.warning(f"rid={request_id} OpenRouter HTTP {status}")
        if status == 429:
            raise HTTPException(
                status_code=429,
                detail="Vision AI quota exceeded. Please wait and try again.",
            )
        raise HTTPException(
            status_code=503,
            detail="Vision AI service temporarily unavailable. Please try again.",
        )
    except httpx.RequestError as exc:
        logger.warning(f"rid={request_id} OpenRouter connection error: {exc}")
        raise HTTPException(
            status_code=503,
            detail="Unable to reach Vision AI service. Please try again.",
        )
    except Exception as exc:
        logger.error(f"rid={request_id} unexpected analysis error: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Analysis failed unexpectedly. Please try again.",
        )

    # ── Post-success analytics (fire-and-forget: never fails the request) ───
    if db is not None:
        try:
            event_id = await _create_analysis_event(
                db,
                user_id=auth.get("user_id"),
                anonymous_id=anonymous_id if not auth["authenticated"] else None,
                authenticated=auth["authenticated"],
                status="success",
                processing_time_ms=result.get("processing_time_ms"),
                model_used=result.get("model_used"),
            )
            result["event_id"] = event_id

            if not auth["authenticated"] and anonymous_id:
                now = datetime.now(timezone.utc)
                await db.anonymous_usage.update_one(
                    {"anonymous_id": anonymous_id},
                    {
                        "$inc": {"analysis_count": 1},
                        "$set": {"last_seen_at": now},
                        "$setOnInsert": {"first_seen_at": now},
                    },
                    upsert=True,
                )
        except Exception as exc:
            logger.warning(f"rid={request_id} analytics tracking failed: {exc}")

    return result


@api_router.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "Lensora API",
        "version": "1.0.0",
        "verification_enabled": ENABLE_VERIFICATION,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@api_router.post("/analyze")
async def analyze_image(
    request: Request,
    file: UploadFile = File(...),
    explain: bool = Form(default=False),
    anonymous_id: Optional[str] = Form(default=None),
    auth: dict = Depends(get_auth_context),
):
    return await _tracked_analyze(request, file, explain, anonymous_id, auth, "/analyze")


@api_router.post("/upload")
async def upload_image(
    request: Request,
    file: UploadFile = File(...),
    explain: bool = Form(default=False),
    anonymous_id: Optional[str] = Form(default=None),
    auth: dict = Depends(get_auth_context),
):
    """Upload endpoint — alias for /analyze for file gallery uploads."""
    return await _tracked_analyze(request, file, explain, anonymous_id, auth, "/upload")


@api_router.get("/anonymous/check")
async def anonymous_check(anonymous_id: str):
    """
    Returns anonymous user's usage status for UX pre-check.
    The backend enforces the limit independently; this is informational.
    """
    db = _get_db()
    if db is None:
        return {
            "can_scan": True,
            "analysis_count": 0,
            "analyses_remaining": FREE_SCAN_LIMIT,
            "limit": FREE_SCAN_LIMIT,
        }
    doc = await db.anonymous_usage.find_one({"anonymous_id": anonymous_id})
    count = doc["analysis_count"] if doc else 0
    return {
        "can_scan": count < FREE_SCAN_LIMIT,
        "analysis_count": count,
        "analyses_remaining": max(0, FREE_SCAN_LIMIT - count),
        "limit": FREE_SCAN_LIMIT,
    }


@api_router.post("/feedback")
async def submit_feedback(
    request: Request,
    auth: dict = Depends(get_auth_context),
):
    """
    Store user feedback for one analysis. One entry per event_id (enforced).
    Does not store images, prompts, or answer content.
    """
    body = await request.json()
    event_id = (body.get("event_id") or "").strip()
    feedback = (body.get("feedback") or "").strip()
    anonymous_id = (body.get("anonymous_id") or "").strip() or None

    if not event_id or feedback not in ("correct", "incorrect"):
        raise HTTPException(
            status_code=400,
            detail="event_id required; feedback must be 'correct' or 'incorrect'.",
        )

    db = _get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database not configured.")

    if await db.analysis_feedback.find_one({"analysis_event_id": event_id}):
        raise HTTPException(status_code=409, detail="Feedback already submitted for this analysis.")

    await db.analysis_feedback.insert_one({
        "analysis_event_id": event_id,
        "user_id": auth.get("user_id"),
        "anonymous_id": anonymous_id if not auth["authenticated"] else None,
        "feedback": feedback,
        "created_at": datetime.now(timezone.utc),
    })
    return {"success": True}


app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        logger.warning("OPENROUTER_API_KEY not set — /analyze and /upload will return 503")
    else:
        logger.info("Lensora API started. OpenRouter configured.")

    db = _get_db()
    if db is not None:
        try:
            await db.anonymous_usage.create_index("anonymous_id", unique=True)
            await db.analysis_events.create_index("event_id", unique=True)
            await db.analysis_events.create_index("user_id")
            await db.analysis_events.create_index("anonymous_id")
            await db.analysis_feedback.create_index("analysis_event_id", unique=True)
            logger.info("MongoDB indexes ready.")
        except Exception as exc:
            logger.warning(f"MongoDB index creation: {exc}")


@app.on_event("shutdown")
async def shutdown():
    logger.info("Lensora API shutting down.")
