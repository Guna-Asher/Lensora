"""EmergentProvider — Vision AI via emergentintegrations library.

Supports all models available through the EMERGENT_LLM_KEY universal key.
Provider/model selection is purely configuration-driven via environment variables.
"""

import os
import uuid
import logging
from typing import Optional

import base64
from emergentintegrations.llm.chat import (
    LlmChat, UserMessage, FileContentWithMimeType, ImageContent, TextDelta, StreamDone
)
from .vision_provider import VisionProvider

logger = logging.getLogger("screensolve.providers")

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


class EmergentProvider(VisionProvider):
    """Vision provider backed by emergentintegrations library."""

    def __init__(self, api_key: str, provider: str, model: str):
        self._api_key = api_key
        self._provider = provider
        self._model = model

    @property
    def model_name(self) -> str:
        return f"{self._provider}/{self._model}"

    async def _run_vision(self, system_prompt: str, image_path: str, user_text: str) -> str:
        chat = LlmChat(
            api_key=self._api_key,
            session_id=str(uuid.uuid4()),
            system_message=system_prompt,
        ).with_model(self._provider, self._model)

        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")
        image_content = ImageContent(image_base64=image_b64)
        message = UserMessage(text=user_text, file_contents=[image_content])

        text = ""
        async for event in chat.stream_message(message):
            if isinstance(event, TextDelta):
                text += event.content
            elif isinstance(event, StreamDone):
                break

        result = text.strip()
        logger.info(f"provider={self._provider} model={self._model} chars={len(result)}")
        return result

    async def analyze(self, image_path: str, explain: bool = False) -> str:
        prompt = EXPLAIN_PROMPT if explain else ANSWERS_PROMPT
        return await self._run_vision(prompt, image_path, "Extract answers from this screen.")

    async def verify(self, image_path: str, answer_a: str, answer_b: str) -> str:
        prompt = VERIFY_PROMPT.format(answer_a=answer_a, answer_b=answer_b)
        return await self._run_vision(prompt, image_path, "Determine the correct answer from this screen.")


# Module-level singletons (lazy init)
_primary: Optional[EmergentProvider] = None
_secondary: Optional[EmergentProvider] = None


def _make_provider(provider_env: str, model_env: str, key_env: str) -> "VisionProvider":
    """Factory: returns the correct VisionProvider based on VISION_PROVIDER env var."""
    vision_backend = os.environ.get("VISION_PROVIDER", "emergent").lower()
    api_key = os.environ.get(key_env, "")
    model = os.environ.get(model_env, "")

    if vision_backend == "openrouter":
        from providers.openrouter_provider import OpenRouterProvider
        return OpenRouterProvider(
            api_key=os.environ.get("OPENROUTER_API_KEY", ""),
            model=model or "openai/gpt-4o",
        )
    # Default: emergent
    return EmergentProvider(
        api_key=api_key,
        provider=os.environ.get(provider_env, "openai"),
        model=model or "gpt-5",
    )


def get_primary_provider() -> "VisionProvider":
    global _primary
    if _primary is None:
        _primary = _make_provider("PRIMARY_PROVIDER", "PRIMARY_MODEL", "EMERGENT_LLM_KEY")
    return _primary


def get_secondary_provider() -> "VisionProvider":
    global _secondary
    if _secondary is None:
        _secondary = _make_provider("SECONDARY_PROVIDER", "SECONDARY_MODEL", "EMERGENT_LLM_KEY")
    return _secondary
