# ScreenSolve — Product Requirements Document

**Last Updated:** 2026-06-20

---

## Product Overview

ScreenSolve is a production-ready, enterprise-grade, self-hostable platform that provides highly accurate answers from photos and screenshots.

**Core Flow:** Screen Photo → OpenCV Processing → OpenRouter Vision AI → Concise Answers

**Target Audience:** Students and professionals who need fast answers from screen content, primarily mobile users.

---

## Architecture

### Frontend (React + Tailwind CSS)
- **React** single-page app with React Router DOM (3 routes)
- **Design:** Dark-only theme, Geist font, mobile-first (max-w-md)
- **Routes:** `/` (Home), `/camera` (Camera), `/results` (Results)

### Backend (FastAPI + OpenCV)
- **FastAPI** with `/api/health`, `/api/analyze`, `/api/upload`
- **OpenCV** for screen detection, auto-crop, perspective correction
- **httpx** for direct REST calls to OpenRouter API
- **Provider abstraction:** VisionProvider → OpenRouterProvider

### Provider Architecture
```
VisionProvider (abstract)
└── OpenRouterProvider (pure httpx → https://openrouter.ai/api/v1)
    ├── Primary:   PRIMARY_MODEL  (default: openai/gpt-4o)
    └── Secondary: SECONDARY_MODEL (default: google/gemini-2.5-pro)
                   └─ triggered by smart verification logic only
```

### Design Mandates
- **NO** vendor-specific LLM SDKs (use pure httpx to OpenRouter only)
- **NO** OCR (EasyOCR, Tesseract, etc.)
- **NO** conversational UI / RAG / LangChain
- **YES** pure HTTP via httpx to OpenRouter
- **YES** self-hostable, zero vendor lock-in

---

## Core Requirements

### Screen Detection Pipeline (v1.2 — two-stage)
1. **Two-Stage Pipeline** — detect on downscaled copy (≤1500px), warp on original full-res
2. **CLAHE preprocessing** — local contrast normalization (dark bezels, uneven lighting)
3. **Multi-strategy edge detection:**
   - Strategy A: morphological closing + CLAHE + multi-threshold Canny (50,150 / 30,100 / 80,200 / 20,80)
   - Strategy B: CLAHE + thin Gaussian + Canny (thin bezels)
   - Strategy C: adaptive threshold (dark bezels, black-on-black scenarios)
4. **Robust quad extraction** — multi-epsilon (0.01–0.06), convex hull fallback, 4-extreme-corners for near-quads
5. **Shape validation** — aspect ratio 1.05:1–3.2:1, convexity ≥ 0.82 (tuning deferred pending test-suite results)
6. **Corner sub-pixel refinement** (cornerSubPix) before perspective warp
7. **Angle estimation** — reject ≥60° with retake prompt; 50-60° returns caution flag
8. **Timing metrics** (internal only): detection_ms, warp_ms, total_ms
9. Falls back to full image if no screen detected (screenshot mode)

### Image Quality Validation
- Minimum resolution: 40,000 pixels
- Blur score (Laplacian variance): ≥ 40.0
- Brightness (mean gray): 18.0 – 242.0
- Contrast (std gray): ≥ 8.0

### Vision AI Analysis
- **Single model mode (default):** Image → PRIMARY_MODEL → Answer
- **Dual-model mode:** PRIMARY_MODEL + SECONDARY_MODEL → Compare (SequenceMatcher ≥ 0.70 = agree) → If differ: primary re-adjudicates

### Smart Verification Triggers
1. Explicit config (ENABLE_VERIFICATION=true)
2. Primary model uncertainty (JSON meta: u=true)
3. Complex question type (JSON meta: c=COMPLEX)
4. Large question set (n ≥ LARGE_QUESTION_THRESHOLD, default 5)
5. Borderline image quality

### Output Format
- MCQ: `Q1 B) 323`
- Numerical: `Q2 56`
- Fill-blank: `Q3 Canberra`
- Code: `Q4\n\`\`\`\n<code>\n\`\`\``
- SQL: `Q5\n\`\`\`sql\n<query>\n\`\`\``

---

## Environment Variables

```
OPENROUTER_API_KEY=          # Required for analysis
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
PRIMARY_MODEL=openai/gpt-4o
SECONDARY_MODEL=google/gemini-2.5-pro
ENABLE_VERIFICATION=false
LARGE_QUESTION_THRESHOLD=5
MAX_FILE_SIZE_MB=10
CORS_ORIGINS=*
APP_URL=https://screensolve.app
SUPABASE_JWT_SECRET=         # Required for backend JWT verification
```

Frontend (`.env`):
```
REACT_APP_SUPABASE_URL=      # Required for Supabase auth
REACT_APP_SUPABASE_ANON_KEY= # Required for Supabase auth
```

---

## What's Been Implemented (2026-06-21 — v1.3)

### Backend
- [x] FastAPI server with /api/health, /api/analyze, /api/upload
- [x] VisionProvider abstract interface
- [x] **OpenRouterProvider** (pure httpx, zero vendor SDKs)
- [x] Provider factory with lazy-init singletons
- [x] Screen detection (OpenCV multi-threshold + morphological closing)
- [x] Shape validation (aspect ratio + convexity)
- [x] Perspective correction with bounds sanity check
- [x] Image quality validation + borderline detection
- [x] Rate limiting (30 req/min per IP)
- [x] MIME + file size validation
- [x] Structured JSON logging with request IDs
- [x] Smart verification triggers (5 conditions)
- [x] Structured JSON metadata in prompts ({"c":"SIMPLE","u":false,"n":3})
- [x] Internal metadata never exposed to end users
- [x] Temporary file cleanup
- [x] 503 response when OPENROUTER_API_KEY not set (health endpoint unaffected)

### Frontend
- [x] Home screen (Capture + Upload)
- [x] Camera screen (live preview, animated scanner corners, viewfinder overlay)
- [x] Camera denied → Upload fallback state
- [x] Results screen (bottom sheet, swipe-down dismiss, scroll overflow fade)
- [x] Grouped code block rendering
- [x] Dark theme (#0A0A0A) + Geist font
- [x] Mobile-first max-w-md layout
- [x] Copy All / Explain / Retake / Back to Home actions

### Authentication (v1.3 — Supabase Thin Layer)
- [x] `supabaseClient.js` — singleton, exports null when env vars missing
- [x] `fetchInterceptor.js` — patches window.fetch to inject JWT on backend calls
- [x] `AuthContext.js` — session state, onAuthStateChange, signOut
- [x] `ProtectedRoute.js` — redirects unauthenticated users to /login
- [x] `LoginScreen` — email/password + Google OAuth + forgot-password link
- [x] `RegisterScreen` — email/password sign-up
- [x] `ForgotPasswordScreen` — sends Supabase reset email
- [x] `ResetPasswordScreen` — completes password-reset flow
- [x] `App.js` updated — AuthProvider wraps all routes; auth routes public; app routes protected
- [x] `server.py` JWT middleware — `verify_jwt` dependency via PyJWT + SUPABASE_JWT_SECRET
- [x] `/api/analyze` and `/api/upload` protected; `/api/health` remains public
- [x] Option B enforced — when unconfigured, error shown; no silent bypass
- [x] Placeholder env vars added: `SUPABASE_JWT_SECRET` (backend), `REACT_APP_SUPABASE_URL`, `REACT_APP_SUPABASE_ANON_KEY` (frontend)


- [x] Backend Dockerfile + Frontend Dockerfile
- [x] docker-compose.yml (OpenRouter-only)
- [x] render.yaml (Render.com deployment blueprint)
- [x] .env.example (OpenRouter-only, no secrets)

---

## Prioritized Backlog

### P0 (Blocking / Critical)
- [ ] End-to-end testing with real OPENROUTER_API_KEY + real Supabase credentials

### P1 (Next Phase)
- [ ] Google OAuth configuration in Supabase dashboard
- [ ] Finalize Render deployment & OpenRouter reliability checks
- [ ] Logout button / user indicator in HomeScreen (currently no UI affordance)

### P2 (Future)
- [ ] Benchmarking framework (deferred by user)
- [ ] PWA support (deferred by user)
- [ ] History / saved sessions (no DB in V1)
- [ ] Self-hosted model provider
- [ ] Kubernetes deployment manifests
