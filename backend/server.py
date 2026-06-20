"""ScreenSolve - FastAPI Backend"""
import os
import sys
import uuid
import time
import logging
import tempfile
from pathlib import Path
from typing import Optional
from difflib import SequenceMatcher
from datetime import datetime, timezone

from fastapi import FastAPI, APIRouter, File, Form, UploadFile, HTTPException, Request
from starlette.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import numpy as np
import cv2

ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))
load_dotenv(ROOT_DIR / ".env")

from providers.emergent_provider import get_primary_provider, get_secondary_provider
from services.screen_detector import process_image
from services.image_validator import validate_image_quality, is_borderline_quality

# Structured JSON logging
logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "msg": "%(message)s"}'
)
logger = logging.getLogger("screensolve")

app = FastAPI(
    title="ScreenSolve API",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json"
)
api_router = APIRouter(prefix="/api")

# Configuration
MAX_FILE_SIZE_MB = int(os.environ.get("MAX_FILE_SIZE_MB", "10"))
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/jpg"}
ENABLE_VERIFICATION = os.environ.get("ENABLE_VERIFICATION", "false").lower() == "true"

# Rate limiting (in-memory, per IP)
_rate_store: dict = {}
RATE_MAX = 30
RATE_WINDOW = 60


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


def parse_gpt_metadata(raw: str) -> tuple:
    """
    Parse CLASSIFY / UNCERTAIN header lines embedded in a GPT-5 response.

    GPT-5 is instructed to start every response with:
        CLASSIFY: SIMPLE|COMPLEX
        UNCERTAIN: YES|NO

    Returns:
        (is_uncertain: bool, is_complex: bool, clean_answer: str)
    """
    is_uncertain = False
    is_complex = False
    answer_lines = []

    for line in raw.split("\n"):
        upper = line.strip().upper()
        if upper.startswith("CLASSIFY:"):
            is_complex = "COMPLEX" in upper
        elif upper.startswith("UNCERTAIN:"):
            is_uncertain = "YES" in upper
        else:
            answer_lines.append(line)

    clean = "\n".join(answer_lines).strip()
    return is_uncertain, is_complex, clean


def pick_verification_reason(
    enable_verification_env: bool,
    is_uncertain: bool,
    is_complex: bool,
    borderline: bool,
) -> Optional[str]:
    """
    Return the reason string if verification should run, else None.

    Priority order (matches product spec):
      1. Explicit config (ENABLE_VERIFICATION=true)
      2. GPT-5 reported uncertainty
      3. Complex question type (puzzle / logic / data / math)
      4. Borderline image quality
    """
    if enable_verification_env:
        return "config"
    if is_uncertain:
        return "gpt5_uncertainty"
    if is_complex:
        return "complex_question_type"
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

    # Screen detection + perspective correction
    processed, detection = process_image(image_np)
    logger.info(f"rid={request_id} screen_detected={detection['screen_detected']} conf={detection['confidence']}")

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

        # Step 2: Parse self-reported metadata (CLASSIFY / UNCERTAIN headers)
        is_uncertain, is_complex, clean_answer = parse_gpt_metadata(raw_answer)

        logger.info(
            f"rid={request_id} uncertain={is_uncertain} "
            f"complex={is_complex} borderline={borderline}"
        )

        # Step 3: Smart verification trigger
        verification_reason = pick_verification_reason(
            ENABLE_VERIFICATION, is_uncertain, is_complex, borderline
        )

        if verification_reason:
            secondary = get_secondary_provider()
            raw_b = await secondary.analyze(tmp_path, explain)
            _, _, clean_b = parse_gpt_metadata(raw_b)
            final_answer, _ = await resolve_answers(tmp_path, clean_answer, clean_b)
            verification_used = True
            logger.info(f"rid={request_id} verification triggered reason={verification_reason}")
        else:
            final_answer = clean_answer
            verification_used = False

        ms = int((time.time() - start) * 1000)
        logger.info(f"rid={request_id} ms={ms} verified={verification_used}")

        return {
            "success": True,
            "answers": final_answer,
            "screen_detected": detection["screen_detected"],
            "confidence": detection["confidence"],
            "processing_time_ms": ms,
            "model_used": primary.model_name,
            "verification_used": verification_used,
            "verification_reason": verification_reason,
            "explained": explain
        }
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


@api_router.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "ScreenSolve API",
        "version": "1.0.0",
        "verification_enabled": ENABLE_VERIFICATION,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@api_router.post("/analyze")
async def analyze_image(
    request: Request,
    file: UploadFile = File(...),
    explain: bool = Form(default=False)
):
    request_id = str(uuid.uuid4())[:8]
    client_ip = get_client_ip(request)

    if not check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please wait and retry.")

    logger.info(f"rid={request_id} endpoint=/analyze ip={client_ip}")

    if not os.environ.get("EMERGENT_LLM_KEY"):
        raise HTTPException(
            status_code=503,
            detail="Vision AI not configured. Please set EMERGENT_LLM_KEY in environment."
        )

    return await run_analysis(file, explain, request_id)


@api_router.post("/upload")
async def upload_image(
    request: Request,
    file: UploadFile = File(...),
    explain: bool = Form(default=False)
):
    """Upload endpoint — alias for /analyze for file gallery uploads."""
    return await analyze_image(request, file, explain)


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
    key = os.environ.get("EMERGENT_LLM_KEY", "")
    if not key:
        logger.warning("EMERGENT_LLM_KEY not set — vision analysis will fail on requests")
    else:
        logger.info("ScreenSolve API started. Vision AI configured.")


@app.on_event("shutdown")
async def shutdown():
    logger.info("ScreenSolve API shutting down.")
