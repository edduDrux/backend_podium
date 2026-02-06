import json

from redis.asyncio import Redis

from app.core.config import settings


_redis_client: Redis | None = None


def get_redis() -> Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


async def publish_session_event(session_id: int, event: dict) -> None:
    channel = f"session:{session_id}:events"
    payload = json.dumps(event)
    await get_redis().publish(channel, payload)
