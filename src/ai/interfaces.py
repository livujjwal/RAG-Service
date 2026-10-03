from abc import ABC, abstractmethod
from typing import Any


class BaseAIProvider(ABC):
    """
    The 'Universal Remote' blueprint. Every AI provider (OpenAI, Claude, Gemini)
    MUST implement these methods.
    """

    @abstractmethod
    async def get_embedding(self, text: str) -> list[float]:
        """Convert text into a vector array (e.g., for pgvector)."""
        pass

    @abstractmethod
    async def generate_chat(self, system_prompt: str, user_prompt: str) -> str:
        """Standard chatbot response."""
        pass

    @abstractmethod
    async def generate_with_tools(
        self, system_prompt: str, user_prompt: str, tools: list[dict]
    ) -> Any:
        """
        FUTURE-PROOFING: Placeholder for MCP (Model Context Protocol).
        Allows passing tools/functions that the AI can trigger.
        """
        pass
