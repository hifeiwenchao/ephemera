from datetime import datetime, timezone
from collections.abc import Mapping

from .message_store import get_message_store
from .models import Conversation, User

TTL_VALUES = {3600, 86400, 604800, 2592000}


def parse_ttl_seconds(value):
    if value is None:
        return None
    if type(value) is not int or value not in TTL_VALUES:
        raise ValueError("请选择有效的消息保留时间")
    return value


def iso_time(value: datetime | None):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if value else None


def user_to_dict(user: User):
    return {"id": user.id, "username": user.username, "display_name": user.display_name, "avatar_url": user.avatar_url}


def message_to_dict(message):
    """Return the stable public message DTO from Redis or a mapping-like value."""
    if isinstance(message, Mapping):
        return dict(message)
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "sender_id": message.sender_id,
        "body": message.body,
        "created_at": iso_time(message.created_at),
        "expires_at": iso_time(message.expires_at),
    }


async def conversation_to_dict(conversation: Conversation, current_user_id: int):
    other_id = conversation.user_b_id if conversation.user_a_id == current_user_id else conversation.user_a_id
    other_user = await User.get(id=other_id)
    last_message = await get_message_store().last_message(conversation.id)
    return {
        "id": conversation.id, "other_user": user_to_dict(other_user), "ttl_seconds": conversation.ttl_seconds,
        "created_at": iso_time(conversation.created_at), "updated_at": iso_time(conversation.updated_at),
        "last_message": message_to_dict(last_message) if last_message else None, "unread_count": 0,
    }
