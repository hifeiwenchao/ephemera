from datetime import datetime, timedelta, timezone

from tortoise.expressions import Q

from .errors import ForbiddenError, NotFoundError, UnauthorizedError, ValidationError, positive_integer
from .message_store import get_message_store
from .models import Conversation, User
from .schemas import conversation_to_dict, parse_ttl_seconds, user_to_dict


async def require_user(user_id: int) -> User:
    if type(user_id) is not int or not 1 <= user_id <= 2**31 - 1:
        raise UnauthorizedError("请选择有效的演示用户")
    user = await User.get_or_none(id=user_id)
    if user is None:
        raise UnauthorizedError("演示用户不存在")
    return user


async def require_conversation(user_id: int, conversation_id: int) -> Conversation:
    await require_user(user_id)
    positive_integer(conversation_id, "conversation_id")
    conversation = await Conversation.get_or_none(id=conversation_id)
    if conversation is None:
        raise NotFoundError("会话不存在")
    if user_id not in (conversation.user_a_id, conversation.user_b_id):
        raise ForbiddenError("你不能访问此会话")
    return conversation


async def search_users(current_user_id: int, query: str):
    await require_user(current_user_id)
    if not isinstance(query, str):
        raise ValidationError("搜索内容必须是文本")
    query = query.strip().lstrip("@").lower()
    if len(query) < 2:
        return []
    users = await User.filter(username_lower__contains=query).exclude(id=current_user_id).order_by("username_lower").limit(20)
    return [user_to_dict(user) for user in users]


async def get_or_create_conversation(current_user_id: int, other_user_id: int):
    await require_user(current_user_id)
    positive_integer(other_user_id, "user_id")
    if current_user_id == other_user_id:
        raise ValidationError("请选择其他用户开始聊天")
    if not await User.exists(id=other_user_id):
        raise NotFoundError("用户不存在")
    user_a_id, user_b_id = sorted((current_user_id, other_user_id))
    conversation, _ = await Conversation.get_or_create(user_a_id=user_a_id, user_b_id=user_b_id)
    return await conversation_to_dict(conversation, current_user_id)


async def list_conversations(current_user_id: int):
    await require_user(current_user_id)
    conversations = await Conversation.filter(Q(user_a_id=current_user_id) | Q(user_b_id=current_user_id)).order_by("-updated_at", "-id")
    return [await conversation_to_dict(conversation, current_user_id) for conversation in conversations]


async def list_messages(current_user_id: int, conversation_id: int, limit: int = 50, before_id: int | None = None):
    await require_conversation(current_user_id, conversation_id)
    positive_integer(limit, "limit")
    if limit > 100:
        raise ValidationError("limit 不能超过 100")
    if before_id is not None:
        positive_integer(before_id, "before")
    return await get_message_store().list_messages(conversation_id, limit, before_id)


async def set_conversation_ttl(current_user_id: int, conversation_id: int, ttl_seconds):
    conversation = await require_conversation(current_user_id, conversation_id)
    try:
        conversation.ttl_seconds = parse_ttl_seconds(ttl_seconds)
    except ValueError as error:
        raise ValidationError(str(error)) from error
    await conversation.save(update_fields=["ttl_seconds"])
    return await conversation_to_dict(conversation, current_user_id)


async def create_message(current_user_id: int, conversation_id: int, body):
    conversation = await require_conversation(current_user_id, conversation_id)
    if not isinstance(body, str):
        raise ValidationError("消息正文必须是文本")
    body = body.strip()
    if not 1 <= len(body) <= 4000:
        raise ValidationError("消息长度必须为 1–4000 个字符")
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=conversation.ttl_seconds) if conversation.ttl_seconds else None
    # Message content belongs only to Redis; SQL stores activity metadata.
    message = await get_message_store().create_message(
        conversation.id, current_user_id, body, created_at=now, expires_at=expires_at
    )
    await Conversation.filter(id=conversation.id).update(updated_at=now)
    return message
