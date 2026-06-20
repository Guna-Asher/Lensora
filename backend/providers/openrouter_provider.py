"""OpenRouterProvider — Vision AI via OpenRouter REST API.

Pure async httpx implementation. Zero vendor-specific SDKs.
Set OPENROUTER_API_KEY in .env to activate.

Docs: https://openrouter.ai/docs
API:  https://openrouter.ai/api/v1
"""

import os
import base64
import logging
from typing import Optional

import httpx
from .vision_provider import VisionProvider

logger = logging.getLogger("screensolve.providers")

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# ─── Prompts ──────────────────────────────────────────────────────────────────

ANSWERS_PROMPT = """You are ScreenSolve, a precision screen answer extractor.

RESPONSE FORMAT — strictly required:
Line 1: compact JSON, no spaces: {"c":"SIMPLE","u":false,"n":0}

  c = "COMPLEX" if content contains: puzzle, logical reasoning, data
      interpretation, statistics, calculus, probability, combinatorics,
      or multi-step graph/spatial reasoning. Otherwise "SIMPLE".
  u = true only if screen text is unreadable/cut-off or you genuinely
      cannot determine an answer. false otherwise.
  n = integer count of distinct questions/problems visible.

Line 2: blank
Lines 3+: ONLY direct answers:
- MCQ:        Q1 B) Answer
- Numerical:  Q2 42
- Fill-blank:  Q3 Paris
- Code:       Q4\n```\n<final code only>\n```
- SQL:        Q5\n```sql\n<query only>\n```
- General:    1-2 line summary only

STRICT RULES — never break:
- NEVER explain reasoning or show chain-of-thought
- NEVER show confidence scores
- NEVER add caveats, disclaimers, or extra commentary
- Number each answer Q1 Q2 Q3... on separate lines
- Be extremely concise"""

EXPLAIN_PROMPT = """You are ScreenSolve, a screen content analyzer.

RESPONSE FORMAT — strictly required:
Line 1: compact JSON, no spaces: {"c":"SIMPLE","u":false,"n":0}
  c = "COMPLEX" for puzzle/logic/data/math/probability. Otherwise "SIMPLE".
  u = true if any screen text is unclear or answer uncertain.
  n = count of distinct questions visible.

Line 2: blank
Lines 3+: answers with brief explanations:
Q1 B) Answer
   → [one-sentence explanation]
Q2 42
   → [one-sentence explanation]

Rules:
- Always lead with the answer
- One sentence per explanation, prefixed with →
- Number from Q1"""

VERIFY_PROMPT = """You are ScreenSolve, a verification expert.
Two AI models analyzed the same screen image and produced different answers.
Re-analyze the image carefully to determine the correct answer.

Model 1 answer:
{answer_a}

Model 2 answer:
{answer_b}

Return ONLY the most accurate answer in the standard concise format.
Do NOT explain your choice."""

# ─── Provider ─────────────────────────────────────────────────────────────────


class OpenRouterProvider(VisionProvider):
    """
    Vision provider backed by OpenRouter's OpenAI-compatible REST API.

    Uses pure httpx — no vendor SDKs. Supports any vision-capable model
    available on OpenRouter (200+ models via a single OPENROUTER_API_KEY).
    """

    def __init__(self, api_key: str, model: str):
        self._api_key = api_key
        self._model = model
        self._base_url = os.environ.get("OPENROUTER_BASE_URL", _OPENROUTER_BASE_URL)

    @property
    def model_name(self) -> str:
        return self._model

    def _encode_image(self, image_path: str) -> str:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    async def _call(self, system_prompt: str, image_path: str, user_text: str) -> str:
        """Make a single chat-completions request to OpenRouter."""
        image_b64 = self._encode_image(image_path)
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}"
                            },
                        },
                    ],
                },
            ],
            "temperature": 0.1,
            "max_tokens": 2048,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": os.environ.get("APP_URL", "https://screensolve.app"),
            "X-Title": "ScreenSolve",
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        result = (data["choices"][0]["message"]["content"] or "").strip()
        logger.info(f"openrouter model={self._model} chars={len(result)}")
        return result

    async def analyze(self, image_path: str, explain: bool = False) -> str:
        prompt = EXPLAIN_PROMPT if explain else ANSWERS_PROMPT
        return await self._call(prompt, image_path, "Extract answers from this screen.")

    async def verify(self, image_path: str, answer_a: str, answer_b: str) -> str:
        prompt = VERIFY_PROMPT.format(answer_a=answer_a, answer_b=answer_b)
        return await self._call(
            prompt, image_path, "Determine the correct answer from this screen."
        )


# ─── Module-level singletons (lazy-init) ──────────────────────────────────────

_primary: Optional[OpenRouterProvider] = None
_secondary: Optional[OpenRouterProvider] = None


def _make_provider(model_env: str, default_model: str) -> OpenRouterProvider:
    """Create an OpenRouterProvider from environment variables."""
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    model = os.environ.get(model_env, default_model)
    return OpenRouterProvider(api_key=api_key, model=model)


def get_primary_provider() -> OpenRouterProvider:
    global _primary
    if _primary is None:
        _primary = _make_provider("PRIMARY_MODEL", "openai/gpt-4o")
    return _primary


def get_secondary_provider() -> OpenRouterProvider:
    global _secondary
    if _secondary is None:
        _secondary = _make_provider("SECONDARY_MODEL", "google/gemini-2.5-pro")
    return _secondary
