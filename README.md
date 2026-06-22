# Lensora

> **The fastest way to get answers from a screen.**

Lensora is a production-ready, self-hostable platform that provides highly accurate answers from photos and screenshots of laptop screens, desktop monitors, phones, tablets, and digital screenshots.

Zero vendor lock-in. No OCR. No LangChain. Pure Vision AI via OpenRouter.

---

## Quick Start

```bash
# 1. Clone and configure
cp .env.example backend/.env
# Edit backend/.env → set OPENROUTER_API_KEY, SUPABASE_JWT_SECRET
# Edit frontend/.env → set REACT_APP_SUPABASE_URL, REACT_APP_SUPABASE_ANON_KEY

# 2. Backend
cd backend
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8001

# 3. Frontend
cd frontend && yarn install && yarn start

# 4. Docker (all-in-one)
cp .env.example .env
# Set OPENROUTER_API_KEY in .env
docker compose up -d
```

---

## Architecture

```
Browser / Mobile
  LoginScreen → HomeScreen → CameraScreen → ResultsScreen
                    │
            POST /api/analyze
                    │
         FastAPI Backend (port 8001)
          1. Supabase JWT Verification
          2. MIME + Size Validation
          3. Screen Detection (OpenCV)
          4. Auto-Crop + Perspective Correction
          5. Image Quality Validation
          6. VisionProvider.analyze()
                    │
         VisionProvider Layer
          OpenRouterProvider ──► primary model  (openai/gpt-5)
                             └─► secondary model (google/gemini-2.5-pro)
                                  └─ triggered by smart verification logic
```

---

## Folder Structure

```
/app/
├── backend/
│   ├── server.py                       # FastAPI app + routes + JWT middleware
│   ├── providers/
│   │   ├── vision_provider.py          # Abstract base class
│   │   └── openrouter_provider.py      # OpenRouter REST implementation (pure httpx)
│   ├── services/
│   │   ├── screen_detector.py          # OpenCV detection + perspective correction
│   │   └── image_validator.py          # Quality validation (blur, brightness, contrast)
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── screens/
│   │   │   ├── HomeScreen.js           # Landing (Capture + Upload)
│   │   │   ├── CameraScreen.js         # Live camera + viewfinder overlay
│   │   │   ├── ResultsScreen.js        # Bottom-sheet answers
│   │   │   ├── LoginScreen.js          # Email/password sign-in
│   │   │   ├── RegisterScreen.js       # Sign-up
│   │   │   ├── ForgotPasswordScreen.js # Password reset request
│   │   │   └── ResetPasswordScreen.js  # Password reset completion
│   │   ├── context/AuthContext.js      # Supabase session state
│   │   ├── components/ProtectedRoute.js
│   │   └── lib/
│   │       ├── supabaseClient.js       # Supabase singleton
│   │       └── fetchInterceptor.js     # JWT injection on API calls
│   ├── Dockerfile
│   └── tailwind.config.js
├── docker-compose.yml
├── render.yaml
└── .env.example
```

---

## API Reference

### `GET /api/health`
```json
{
  "status": "healthy",
  "service": "Lensora API",
  "version": "1.0.0",
  "verification_enabled": false
}
```

### `POST /api/analyze` *(requires JWT)*
**Request:** `multipart/form-data`
- `file`: JPEG / PNG / WEBP image (required)
- `explain`: boolean (optional, default: `false`)

**Success response:**
```json
{
  "success": true,
  "answers": "Q1 B) 323\nQ2 D) 72",
  "screen_detected": true,
  "confidence": 0.90,
  "processing_time_ms": 1842,
  "model_used": "openai/gpt-5",
  "verification_used": false,
  "explained": false
}
```

**Not configured response (503):**
```json
{
  "success": false,
  "error": "OPENROUTER_API_KEY is not configured"
}
```

### `POST /api/upload` *(requires JWT)*
Identical to `/api/analyze`. Alias for file gallery uploads.

---

## Environment Variables

### Backend

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENROUTER_API_KEY` | *(required)* | OpenRouter API key — get from [openrouter.ai/keys](https://openrouter.ai/keys) |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | Override for proxies or self-hosting |
| `VISION_PROVIDER` | `openrouter` | Active provider (`openrouter` \| future: `openai`, `gemini`, `anthropic`) |
| `PRIMARY_MODEL` | `openai/gpt-5` | Primary vision model (full OpenRouter model ID) |
| `SECONDARY_MODEL` | `google/gemini-2.5-pro` | Secondary model for verification |
| `ENABLE_VERIFICATION` | `false` | Force dual-model verification on every request |
| `LARGE_QUESTION_THRESHOLD` | `5` | Question count that auto-triggers verification |
| `MAX_FILE_SIZE_MB` | `10` | Upload size limit |
| `CORS_ORIGINS` | `*` | Allowed CORS origins |
| `APP_URL` | `https://lensora.app` | Used in OpenRouter `HTTP-Referer` header |
| `SUPABASE_JWT_SECRET` | *(required for auth)* | JWT secret from Supabase Project Settings → API |

### Frontend

| Variable | Description |
|----------|-------------|
| `REACT_APP_BACKEND_URL` | Backend URL |
| `REACT_APP_SUPABASE_URL` | Supabase project URL |
| `REACT_APP_SUPABASE_ANON_KEY` | Supabase anon key |

---

## Vision Provider Architecture

```python
class VisionProvider(ABC):
    async def analyze(self, image_path: str, explain: bool) -> str: ...
    async def verify(self, image_path, answer_a, answer_b) -> str: ...
    model_name: str
```

**OpenRouterProvider** (pure httpx):
- POST `https://openrouter.ai/api/v1/chat/completions`
- OpenAI-compatible message format with base64 image URLs
- 60s timeout, temperature 0.1, max_tokens 2048
- Supports any vision-capable model on OpenRouter

To add a new provider: extend `VisionProvider`, implement `analyze()` / `verify()`, update `VISION_PROVIDER` factory in `openrouter_provider.py`.

---

## Smart Verification Logic

Dual-model verification auto-triggers when:

| Trigger | Condition |
|---------|-----------|
| Config | `ENABLE_VERIFICATION=true` |
| Uncertainty | Primary model JSON metadata: `"u": true` |
| Complexity | Primary model JSON metadata: `"c": "COMPLEX"` |
| Volume | Question count ≥ `LARGE_QUESTION_THRESHOLD` (default 5) |
| Quality | Borderline image quality detected by OpenCV |

---

## Screen Detection Pipeline

1. Grayscale + Gaussian blur
2. Multi-threshold Canny edge detection `(50,150)`, `(30,100)`, `(80,200)`
3. Contour analysis — largest quadrilateral in 8%–95% image area
4. Aspect-ratio validation (1.05:1 – 3.2:1) + convexity ≥ 0.82
5. Perspective transform (flatten/undistort)
6. Falls back to full image if no screen detected (screenshot mode)

---

## Image Quality Validation

| Check | Threshold |
|-------|-----------|
| Minimum resolution | 40,000 pixels |
| Blur (Laplacian variance) | ≥ 40.0 |
| Brightness (mean gray) | 18.0 – 242.0 |
| Contrast (std gray) | ≥ 8.0 |

---

## Security

- Supabase JWT verification on all analysis endpoints
- MIME validation (JPEG/PNG/WEBP only)
- File size limit (default 10 MB)
- Rate limiting (30 req/min per IP, in-memory)
- Temp file cleanup via `try/finally`
- No persistent image storage
- Structured JSON logging with request IDs

---

## Docker Deployment

```bash
cp .env.example .env
# Set OPENROUTER_API_KEY and SUPABASE_JWT_SECRET in .env
docker compose up -d
```

---

## Render.com Deployment

1. Fork this repository
2. Create a new Blueprint in Render → link to `render.yaml`
3. Set `OPENROUTER_API_KEY` and `SUPABASE_JWT_SECRET` in the backend environment
4. Set `REACT_APP_BACKEND_URL`, `REACT_APP_SUPABASE_URL`, `REACT_APP_SUPABASE_ANON_KEY` in the frontend environment

---

## Kubernetes Readiness

- Stateless backend (no local storage between requests)
- Health check: `GET /api/health`
- 12-factor compliant (all config via env vars)
- Scale backend replicas horizontally
