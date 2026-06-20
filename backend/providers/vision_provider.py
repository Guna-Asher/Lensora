"""Abstract VisionProvider interface.

All provider implementations must extend this base class.
Business logic must never import concrete providers directly — use the factory.

Extension points:
- OpenRouterProvider: direct OpenRouter API (OPENROUTER_API_KEY required)
- OpenAIProvider: direct OpenAI API
- GeminiProvider: direct Gemini API
- AnthropicProvider: direct Anthropic API
- SelfHostedProvider: on-prem / local model
"""

from abc import ABC, abstractmethod


class VisionProvider(ABC):
    """Base interface for all vision AI providers."""

    @abstractmethod
    async def analyze(self, image_path: str, explain: bool = False) -> str:
        """
        Analyze a screen image and return concise answers.

        Args:
            image_path: Path to the pre-processed JPEG image file.
            explain: If True, include brief one-line explanations per answer.

        Returns:
            Formatted answer string (e.g., "Q1 B) 323\nQ2 D) 72")
        """

    @abstractmethod
    async def verify(self, image_path: str, answer_a: str, answer_b: str) -> str:
        """
        Verification pass: re-analyze image and choose the best answer from two candidates.

        Used when ENABLE_VERIFICATION=true and model answers disagree.
        """

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return provider/model identifier string (e.g., 'openai/gpt-5')."""
