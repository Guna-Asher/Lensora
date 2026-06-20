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

BEGIN your response with EXACTLY these two header lines — no exceptions:
CLASSIFY: SIMPLE
UNCERTAIN: NO

Change CLASSIFY to COMPLEX if the screen contains:
  puzzle, logical reasoning, data interpretation, complex mathematics,
  probability, combinatorics, graph analysis, or multi-step inference.

Change UNCERTAIN to YES if:
  any part of the screen is blurry/cut off, OR you cannot confidently read an answer.

After the two header lines, provide ONLY the direct answers:
- MCQ:        Q1 B) Answer
- Numerical:  Q2 42
- Fill-blank:  Q3 Paris
- Code:       Q4\n```\n<final code only>\n```
- SQL:        Q5\n```sql\n<query only>\n```
- General:    1-2 line summary only

STRICT RULES — never break these:
- NEVER explain reasoning or show chain-of-thought
- NEVER show confidence scores
- NEVER add caveats, disclaimers, or extra commentary
- Each answer on its own line, numbered Q1 Q2 Q3...
- Be extremely concise"""

EXPLAIN_PROMPT = """You are ScreenSolve, a screen content analyzer.

BEGIN your response with EXACTLY these two header lines:
CLASSIFY: SIMPLE
UNCERTAIN: NO

Change CLASSIFY to COMPLEX for: puzzle, logical reasoning, data interpretation,
complex math, probability, combinatorics, or graph analysis.
Change UNCERTAIN to YES if any part of the screen is unclear or you are unsure.

After the two header lines, provide answers with brief explanations:
Q1 B) Answer
   → [one-sentence explanation]
Q2 42
   → [one-sentence explanation]

Rules:
- Always lead with the answer first
- Explanation is exactly one sentence, prefixed with →
- Number starting from Q1"""

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


def get_primary_provider() -> EmergentProvider:
    global _primary
    if _primary is None:
        _primary = EmergentProvider(
            api_key=os.environ.get("EMERGENT_LLM_KEY", ""),
            provider=os.environ.get("PRIMARY_PROVIDER", "openai"),
            model=os.environ.get("PRIMARY_MODEL", "gpt-5"),
        )
    return _primary


def get_secondary_provider() -> EmergentProvider:
    global _secondary
    if _secondary is None:
        _secondary = EmergentProvider(
            api_key=os.environ.get("EMERGENT_LLM_KEY", ""),
            provider=os.environ.get("SECONDARY_PROVIDER", "gemini"),
            model=os.environ.get("SECONDARY_MODEL", "gemini-2.5-pro"),
        )
    return _secondary
