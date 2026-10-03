from src.ai.interfaces import BaseAIProvider
from src.ai.providers.openai_provider import OpenAIProvider

# from src.ai.providers.anthropic_provider import AnthropicProvider


class AIFactory:
    @staticmethod
    def get_provider(
        provider_name: str,
        api_key: str,
        embedding_model: str | None = None,
        chat_model: str | None = None,
    ) -> BaseAIProvider:
        """
        Dynamically returns the correct AI provider class based on the requested name.
        """
        provider_name = provider_name.lower()

        if provider_name == "openai":
            # Use provided models or fallback to safe defaults
            return OpenAIProvider(
                api_key=api_key,
                embedding_model=embedding_model or "text-embedding-3-small",
                chat_model=chat_model or "gpt-4o",
            )

        elif provider_name == "anthropic":
            # return AnthropicProvider(api_key=api_key)
            raise NotImplementedError("Anthropic provider coming soon!")

        elif provider_name == "huggingface":
            # return HuggingFaceProvider(api_key=api_key)
            raise NotImplementedError("HuggingFace provider coming soon!")

        else:
            raise ValueError(f"Unsupported AI Provider: {provider_name}")
