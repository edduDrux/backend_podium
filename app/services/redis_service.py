import json
import logging

from redis.asyncio import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis_client: Redis | None = None


def get_redis() -> Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


async def publish_session_event(session_id: int, event: dict) -> None:
    channel = f"session:{session_id}:events"
    payload = json.dumps(event)
    try:
        await get_redis().publish(channel, payload)
    except Exception as exc:
        logger.warning(f"Falha ao publicar evento no Redis (session={session_id}): {exc}")
