"""OpenRouterProvider — Vision AI via OpenRouter (OpenAI-compatible API).

Set VISION_PROVIDER=openrouter and OPENROUTER_API_KEY to activate.

OpenRouter gives access to 200+ models through a single API endpoint,
using the same request format as the OpenAI SDK.

Reliability advantages over direct provider APIs:
- Automatic fallback across providers
- Single key for all models
- No per-provider rate limit management
- Unified billing
"""

import os
import base64
import logging
from openai import AsyncOpenAI
from .vision_provider import VisionProvider
from .emergent_provider import ANSWERS_PROMPT, EXPLAIN_PROMPT, VERIFY_PROMPT

logger = logging.getLogger("screensolve.providers.openrouter")

# OpenRouter sends these headers for model leaderboard attribution (optional)
_OPENROUTER_HEADERS = {
    "HTTP-Referer": os.environ.get("APP_URL", "https://screensolve.app"),
    "X-Title": "ScreenSolve",
}


class OpenRouterProvider(VisionProvider):
    """
    Vision provider backed by OpenRouter's OpenAI-compatible API.

    Drop-in replacement for EmergentProvider — same interface, different backend.
    Supports any vision-capable model available on OpenRouter.
    """

    def __init__(self, api_key: str, model: str):
        base_url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        self._model = model
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers=_OPENROUTER_HEADERS,
        )

    @property
    def model_name(self) -> str:
        return f"openrouter/{self._model}"

    def _encode_image(self, image_path: str) -> str:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    async def _call(self, system_prompt: str, image_path: str, user_text: str) -> str:
        image_b64 = self._encode_image(image_path)
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                        },
                    ],
                },
            ],
            temperature=0.1,
            max_tokens=2048,
        )
        result = response.choices[0].message.content or ""
        logger.info(f"openrouter model={self._model} chars={len(result)}")
        return result.strip()

    async def analyze(self, image_path: str, explain: bool = False) -> str:
        prompt = EXPLAIN_PROMPT if explain else ANSWERS_PROMPT
        return await self._call(prompt, image_path, "Extract answers from this screen.")

    async def verify(self, image_path: str, answer_a: str, answer_b: str) -> str:
        prompt = VERIFY_PROMPT.format(answer_a=answer_a, answer_b=answer_b)
        return await self._call(prompt, image_path, "Determine the correct answer from this screen.")
