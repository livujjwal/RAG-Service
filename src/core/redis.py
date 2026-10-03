import redis.asyncio as redis
from src.core.config import settings

# decode_responses=True ensures Redis returns strings instead of bytes
redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)


async def get_redis() -> redis.Redis:
    yield redis_client
