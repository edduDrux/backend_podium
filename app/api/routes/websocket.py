from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.redis_service import get_redis


router = APIRouter(tags=["websocket"])


@router.websocket("/sessions/{session_id}/live")
async def session_live_websocket(websocket: WebSocket, session_id: int):
    await websocket.accept()

    redis = get_redis()
    pubsub = redis.pubsub()
    channel = f"session:{session_id}:events"
    await pubsub.subscribe(channel)

    try:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            data = message.get("data")
            if isinstance(data, str):
                await websocket.send_text(data)
    except (WebSocketDisconnect, RuntimeError):
        # cliente desconectou ou websocket indisponível
        pass
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        try:
            await websocket.close()
        except RuntimeError:
            pass
