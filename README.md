# ScreenSolve

> **The fastest way to get answers from a screen.**

ScreenSolve is a production-ready, enterprise-grade, self-hostable platform that provides highly accurate answers from photos and screenshots of laptop screens, desktop monitors, phones, tablets, and digital screenshots.

---

## Quick Start

```bash
# Backend
cd backend
pip install -r requirements.txt
# Edit .env → set EMERGENT_LLM_KEY
uvicorn server:app --host 0.0.0.0 --port 8001

# Frontend
cd frontend && yarn install && yarn start

# Docker
cp .env.example .env && docker compose up -d
```

---

## Architecture

```
Browser/Mobile
  HomeScreen → CameraScreen → ResultsScreen
                    │
            POST /api/analyze
                    │
         FastAPI Backend (port 8001)
          1. MIME + Size Validation
          2. Screen Detection (OpenCV)
          3. Auto-Crop + Perspective Correction
          4. Image Quality Validation
          5. VisionProvider.analyze()
                    │
         VisionProvider Layer
          EmergentProvider → openai/gpt-5 (primary)
                           → gemini/gemini-2.5-pro (secondary, ENABLE_VERIFICATION=true)
          [Future] OpenRouterProvider, AnthropicProvider, SelfHostedProvider
```

---

## Folder Structure

```
/app/
├── backend/
│   ├── server.py                   # FastAPI app + routes
│   ├── providers/
│   │   ├── vision_provider.py      # Abstract base class
│   │   └── emergent_provider.py    # EmergentProvider implementation
│   ├── services/
│   │   ├── screen_detector.py      # OpenCV detection + perspective
│   │   └── image_validator.py      # Quality validation
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/screens/
│   │   ├── HomeScreen.js           # Landing (Capture + Upload)
│   │   ├── CameraScreen.js         # Live camera + viewfinder
│   │   └── ResultsScreen.js        # Bottom sheet answers
│   ├── Dockerfile
│   └── tailwind.config.js
├── docker-compose.yml
└── .env.example
```

---

## API Reference

### `GET /api/health`
```json
{ "status": "healthy", "service": "ScreenSolve API", "version": "1.0.0" }
```

### `POST /api/analyze`
**Request:** `multipart/form-data`
- `file`: JPEG/PNG/WEBP image (required)
- `explain`: boolean (optional, default: false)

**Response:**
```json
{
  "success": true,
  "answers": "Q1 B) 323\nQ2 D) 72",
  "screen_detected": true,
  "confidence": 0.90,
  "processing_time_ms": 1842,
  "model_used": "openai/gpt-5",
  "verification_used": false
}
```

### `POST /api/upload`
Identical to `/api/analyze`.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `EMERGENT_LLM_KEY` | — | Universal LLM key (required) |
| `VISION_PROVIDER` | `emergent` | Provider backend |
| `PRIMARY_PROVIDER` | `openai` | Primary AI provider |
| `PRIMARY_MODEL` | `gpt-5` | Primary AI model |
| `SECONDARY_PROVIDER` | `gemini` | Secondary provider |
| `SECONDARY_MODEL` | `gemini-2.5-pro` | Secondary model |
| `ENABLE_VERIFICATION` | `false` | Dual-model verification |
| `MAX_FILE_SIZE_MB` | `10` | Upload size limit |
| `CORS_ORIGINS` | `*` | Allowed CORS origins |
| `OPENROUTER_API_KEY` | — | Future: OpenRouter key |

---

## Vision Provider Architecture

```python
class VisionProvider(ABC):
    async def analyze(self, image_path: str, explain: bool) -> str: ...
    async def verify(self, image_path, answer_a, answer_b) -> str: ...
    model_name: str
```

To add a new provider: extend `VisionProvider`, implement the methods, add to factory.

---

## Screen Detection

Multi-threshold Canny edge detection → contour analysis → 4-corner quadrilateral → perspective transform. Falls back to full image (screenshot mode) if no screen found.

---

## Security

- MIME validation (JPEG/PNG/WEBP only)
- File size limit (default 10MB)
- Rate limiting (30 req/min per IP)
- Temp file cleanup (try/finally)
- No persistent image storage

---

## Docker Deployment

```bash
cp .env.example .env
# Set EMERGENT_LLM_KEY in .env
docker compose up -d
```

---

## Kubernetes Readiness

- Stateless backend (no local storage)
- Health check: `GET /api/health`
- 12-factor compliant (all config via env vars)
- Scale backend replicas horizontally

---

## Extension Points

| Feature | Where |
|---------|-------|
| New AI provider | `providers/new_provider.py` |
| OpenRouter | `providers/openrouter_provider.py` |
| Answer history | MongoDB repository + `/api/sessions` |
| Benchmarking | `services/benchmark.py` |
| Auth | JWT middleware in `server.py` |
