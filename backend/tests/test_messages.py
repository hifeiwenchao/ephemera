from datetime import datetime, timedelta, timezone

import pytest

from backend.app.errors import ForbiddenError, ValidationError
from backend.app.services import create_message, get_or_create_conversation, list_conversations, list_messages, set_conversation_ttl


async def test_message_trims_and_checks_sender(users):
    conversation = await get_or_create_conversation(users.alice.id, users.bob.id)
    message = await create_message(users.alice.id, conversation["id"], "  你好 🌿  ")
    assert message["body"] == "你好 🌿"
    assert message["sender_id"] == users.alice.id
    assert message["expires_at"] is None
    with pytest.raises(ForbiddenError):
        await create_message(users.carol.id, conversation["id"], "unauthorized")


@pytest.mark.parametrize("body", ["", " \n ", "x" * 4001, True, 1, None, [], {}])
async def test_invalid_message_bodies_rejected(users, redis_store, body):
    conversation = await get_or_create_conversation(users.alice.id, users.bob.id)
    with pytest.raises(ValidationError):
        await create_message(users.alice.id, conversation["id"], body)
    assert await redis_store.list_messages(conversation["id"]) == []


async def test_ttl_changes_only_future_messages(users, redis_store):
    conversation = await get_or_create_conversation(users.alice.id, users.bob.id)
    await set_conversation_ttl(users.alice.id, conversation["id"], 3600)
    first = await create_message(users.alice.id, conversation["id"], "一小时")
    first_dt = datetime.fromisoformat(first["created_at"])
    assert datetime.fromisoformat(first["expires_at"]) - first_dt == timedelta(hours=1)
    await set_conversation_ttl(users.bob.id, conversation["id"], 86400)
    second = await create_message(users.bob.id, conversation["id"], "一天")
    assert datetime.fromisoformat(second["expires_at"]) - datetime.fromisoformat(second["created_at"]) == timedelta(days=1)
    await set_conversation_ttl(users.alice.id, conversation["id"], None)
    third = await create_message(users.alice.id, conversation["id"], "保留")
    assert third["expires_at"] is None
    stored = await redis_store.get_message(first["id"])
    assert stored["expires_at"] == first["expires_at"]
    assert 0 < await redis_store.client.pttl(redis_store.message_key(first["id"])) <= 3_600_000


async def test_history_filters_expired_and_paginates_ascending(users, redis_store):
    conversation = await get_or_create_conversation(users.alice.id, users.bob.id)
    first = await create_message(users.alice.id, conversation["id"], "第一条")
    second = await create_message(users.bob.id, conversation["id"], "第二条")
    third = await create_message(users.alice.id, conversation["id"], "第三条")
    expired = await redis_store.create_message(conversation["id"], users.bob.id, "已过期", expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    history = await list_messages(users.alice.id, conversation["id"], limit=2)
    assert [item["id"] for item in history] == [second["id"], third["id"]]
    older = await list_messages(users.alice.id, conversation["id"], before_id=second["id"])
    assert [item["id"] for item in older] == [first["id"]]
    assert await redis_store.get_message(expired["id"]) is None
    assert (await list_conversations(users.bob.id))[0]["last_message"]["id"] == third["id"]
