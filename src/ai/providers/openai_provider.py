from openai import AsyncOpenAI

from src.ai.interfaces import BaseAIProvider


class OpenAIProvider(BaseAIProvider):
    def __init__(
        self,
        api_key: str,
        embedding_model: str = "text-embedding-3-small",
        chat_model: str = "gpt-4o",
    ):
        self.client = AsyncOpenAI(api_key=api_key)
        self.embedding_model = embedding_model
        self.chat_model = chat_model

    async def get_embedding(self, text: str) -> list[float]:
        response = await self.client.embeddings.create(
            input=text, model=self.embedding_model
        )
        return response.data[0].embedding

    async def generate_chat(self, system_prompt: str, user_prompt: str) -> str:
        response = await self.client.chat.completions.create(
            model=self.chat_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content

    async def generate_with_tools(
        self, system_prompt: str, user_prompt: str, tools: list[dict]
    ):
        # Future implementation for OpenAI function calling / MCP
        pass
