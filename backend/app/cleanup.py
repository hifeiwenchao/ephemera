import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timezone

from .models import Message
from .websocket import manager

logger = logging.getLogger(__name__)


async def cleanup_expired_messages(now=None) -> int:
    now = now or datetime.now(timezone.utc)
    expired = await Message.filter(expires_at__lte=now).values("id", "conversation_id")
    if not expired:
        return 0
    grouped = defaultdict(list)
    for message in expired:
        grouped[message["conversation_id"]].append(message["id"])
    deleted = await Message.filter(id__in=[message["id"] for message in expired]).delete()
    for conversation_id, ids in grouped.items():
        await manager.broadcast(conversation_id, {"type": "message.deleted", "data": {"ids": ids}})
    return deleted


async def cleanup_loop(app):
    while True:
        await asyncio.sleep(max(1, app.ctx.settings.cleanup_interval_seconds))
        try:
            await cleanup_expired_messages()
        except Exception:
            logger.exception("Expired-message cleanup failed; retrying next interval")
