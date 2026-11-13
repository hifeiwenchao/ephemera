import asyncio
import logging
from .message_store import get_message_store
from .websocket import manager, notify_conversation

logger = logging.getLogger(__name__)


async def cleanup_expired_messages(now=None) -> int:
    grouped = await get_message_store().cleanup_expired(now)
    for conversation_id, ids in grouped.items():
        await manager.broadcast(conversation_id, {"type": "message.deleted", "data": {"ids": ids}})
        await notify_conversation(conversation_id)
    return sum(len(ids) for ids in grouped.values())


async def cleanup_loop(app):
    while True:
        await asyncio.sleep(max(1, app.ctx.settings.cleanup_interval_seconds))
        try:
            await cleanup_expired_messages()
        except Exception:
            logger.exception("Expired-message cleanup failed; retrying next interval")
