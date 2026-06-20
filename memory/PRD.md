# ScreenSolve — Product Requirements Document

**Last Updated:** 2026-06-20

---

## Product Overview

ScreenSolve is a production-ready, enterprise-grade platform that provides highly accurate answers from photos and screenshots.

**Core Flow:** Screen Photo → AI Vision Analysis → Concise Answers

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
- **emergentintegrations** library for Vision AI (EMERGENT_LLM_KEY)
- **Provider abstraction:** VisionProvider → EmergentProvider

### Provider Architecture
```
VisionProvider (abstract)
└── EmergentProvider (default, uses emergentintegrations)
    ├── Primary: openai/gpt-5
    └── Secondary: gemini/gemini-2.5-pro (when ENABLE_VERIFICATION=true)
```

---

## Core Requirements

### Screen Detection Pipeline
1. Grayscale + Gaussian blur
2. Canny edge detection (multi-threshold: (50,150), (30,100), (80,200))
3. Contour analysis (find largest quadrilateral, 8%-95% image area)
4. Perspective transform (flatten/undistort)
5. Falls back to full image if no screen detected (screenshot mode)

### Image Quality Validation
- Minimum resolution: 40,000 pixels
- Blur score (Laplacian variance): ≥ 40.0
- Brightness (mean gray): 18.0 – 242.0
- Contrast (std gray): ≥ 8.0

### Vision AI Analysis
- **Single model mode (default):** Image → GPT-5 → Answer
- **Dual-model mode (ENABLE_VERIFICATION=true):** GPT-5 + Gemini 2.5 Pro → Compare (SequenceMatcher ≥ 0.70 = agree) → If differ: verification pass

### Output Format
- MCQ: `Q1 B) 323`
- Numerical: `Q2 56`
- Fill-blank: `Q3 Canberra`
- Code: `Q4\n\`\`\`\n<code>\n\`\`\``
- SQL: `Q5\n\`\`\`sql\n<query>\n\`\`\``

---

## Environment Variables

```
EMERGENT_LLM_KEY=sk-emergent-50416B04cB8CdD2848
VISION_PROVIDER=emergent
PRIMARY_PROVIDER=openai
PRIMARY_MODEL=gpt-5
SECONDARY_PROVIDER=gemini
SECONDARY_MODEL=gemini-2.5-pro
ENABLE_VERIFICATION=false
MAX_FILE_SIZE_MB=10
```

---

## What's Been Implemented (2026-06-20 — v1.1)

### Backend
- [x] FastAPI server with /api/health, /api/analyze, /api/upload
- [x] VisionProvider abstract interface
- [x] EmergentProvider (gpt-5 + gemini-2.5-pro)
- [x] OpenRouterProvider (openai-compatible, activates via VISION_PROVIDER=openrouter)
- [x] Provider factory (VISION_PROVIDER env selects backend)
- [x] Screen detection (OpenCV multi-threshold + morphological closing)
- [x] Shape validation (aspect ratio 1.05:1–3.2:1 + convexity ≥ 0.82)
- [x] Perspective correction with bounds sanity check
- [x] Image quality validation + borderline detection
- [x] Rate limiting (30 req/min per IP)
- [x] MIME + file size validation
- [x] Structured JSON logging with request IDs
- [x] Smart verification triggers:
      - Explicit config (ENABLE_VERIFICATION=true)
      - GPT-5 uncertainty (JSON meta: u=true)
      - Complex question type (JSON meta: c=COMPLEX)
      - Large question set (n ≥ LARGE_QUESTION_THRESHOLD, default 5)
      - Borderline image quality
- [x] Structured JSON metadata in prompts ({"c":"SIMPLE","u":false,"n":3})
- [x] Internal metadata never exposed to end users
- [x] Temporary file cleanup

### Frontend
- [x] Home screen (Capture + Upload)
- [x] Camera screen (live preview, animated scanner corners, viewfinder overlay)
- [x] Camera denied → Upload fallback state
- [x] Results screen (bottom sheet, swipe-down dismiss, scroll overflow fade)
- [x] Grouped code block rendering
- [x] Dark theme (#0A0A0A) + Geist font
- [x] Mobile-first max-w-md layout
- [x] Copy All / Explain / Retake / Back to Home actions

### Infrastructure
- [x] Backend Dockerfile + Frontend Dockerfile
- [x] docker-compose.yml
- [x] render.yaml (Render.com deployment blueprint)
- [x] .env.example

### Backend
- [x] FastAPI server with /api/health, /api/analyze, /api/upload
- [x] VisionProvider abstract interface
- [x] EmergentProvider (gpt-5 + gemini-2.5-pro)
- [x] Screen detection (OpenCV multi-threshold)
- [x] Perspective correction
- [x] Image quality validation
- [x] Rate limiting (30 req/min per IP)
- [x] MIME + file size validation
- [x] Structured JSON logging with request IDs
- [x] Dual-model verification mode (configurable)
- [x] Temporary file cleanup

### Frontend
- [x] Home screen (Capture + Upload)
- [x] Camera screen (live preview, viewfinder overlay, capture)
- [x] Results screen (bottom sheet, answers, copy, explain, retake)
- [x] Dark theme (#0A0A0A) + Geist font
- [x] Mobile-first max-w-md layout
- [x] Slide-up animation for bottom sheet
- [x] Staggered answer reveal animation
- [x] Explain feature (re-analyzes with explanation prompt)

### Infrastructure
- [x] Backend Dockerfile
- [x] Frontend Dockerfile
- [x] docker-compose.yml
- [x] .env.example
- [x] CRACO webpack-dev-server v5 compatibility fix

---

## Prioritized Backlog

### P0 (Blocking / Critical)
- [ ] End-to-end testing validation

### P1 (Next Phase)
- [ ] OpenRouter provider implementation (when user provides OPENROUTER_API_KEY)
- [ ] README.md enterprise documentation
- [ ] Error boundary component

### P2 (Future)
- [ ] Benchmarking framework (deferred by user)
- [ ] PWA support (deferred by user)
- [ ] History / saved sessions (no DB in V1)
- [ ] Self-hosted model provider
- [ ] Kubernetes deployment manifests
