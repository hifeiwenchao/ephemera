import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from backend.app import services
from backend.app.errors import ForbiddenError, ValidationError
from backend.app.message_store import RedisMessageStore


async def test_unread_counts_only_incoming_messages_and_history_does_not_mark_read(users):
    conversation = await services.get_or_create_conversation(users.alice.id, users.bob.id)
    await services.create_message(users.alice.id, conversation["id"], "one")
    await services.create_message(users.bob.id, conversation["id"], "reply")
    await services.create_message(users.alice.id, conversation["id"], "two")
    await services.list_messages(users.bob.id, conversation["id"])

    assert (await services.list_conversations(users.bob.id))[0]["unread_count"] == 2
    assert (await services.list_conversations(users.alice.id))[0]["unread_count"] == 1


async def test_read_cursor_is_monotonic_and_new_messages_remain_unread(users):
    conversation = await services.get_or_create_conversation(users.alice.id, users.bob.id)
    first = await services.create_message(users.alice.id, conversation["id"], "one")
    second = await services.create_message(users.alice.id, conversation["id"], "two")
    await asyncio.gather(
        services.mark_conversation_read(users.bob.id, conversation["id"], second["id"]),
        services.mark_conversation_read(users.bob.id, conversation["id"], first["id"]),
    )
    assert (await services.list_conversations(users.bob.id))[0]["unread_count"] == 0
    await services.create_message(users.alice.id, conversation["id"], "three")
    stale = await services.mark_conversation_read(users.bob.id, conversation["id"], first["id"])
    assert stale["unread_count"] == 1


async def test_expired_unread_messages_disappear_before_cleanup(users, redis_store):
    conversation = await services.get_or_create_conversation(users.alice.id, users.bob.id)
    message = await redis_store.create_message(
        conversation["id"], users.alice.id, "expires",
        expires_at=datetime.now(timezone.utc) + timedelta(milliseconds=60),
    )
    assert (await services.list_conversations(users.bob.id))[0]["unread_count"] == 1
    await asyncio.sleep(0.08)
    assert await redis_store.client.zscore(redis_store.history_key(conversation["id"]), message["id"]) is not None
    assert (await services.list_conversations(users.bob.id))[0]["unread_count"] == 0
    assert (await services.mark_conversation_read(users.bob.id, conversation["id"], message["id"]))["unread_count"] == 0


async def test_read_rejects_nonmembers_unknown_ids_and_other_conversations(users):
    conversation = await services.get_or_create_conversation(users.alice.id, users.bob.id)
    other = await services.get_or_create_conversation(users.alice.id, users.carol.id)
    message = await services.create_message(users.alice.id, conversation["id"], "one")
    other_message = await services.create_message(users.alice.id, other["id"], "elsewhere")
    with pytest.raises(ForbiddenError):
        await services.mark_conversation_read(users.carol.id, conversation["id"], message["id"])
    for invalid in [True, 0, -1, "1", None, 2**31, other_message["id"], other_message["id"] + 100]:
        with pytest.raises(ValidationError):
            await services.mark_conversation_read(users.bob.id, conversation["id"], invalid)


async def test_delayed_message_cannot_land_behind_an_already_read_cursor(users, redis_store, monkeypatch):
    conversation = await services.get_or_create_conversation(users.alice.id, users.bob.id)
    entered, release = asyncio.Event(), asyncio.Event()
    original = redis_store._write_message

    async def delay_first_message(message, **kwargs):
        if message["body"] == "slow":
            entered.set()
            await release.wait()
        await original(message, **kwargs)

    monkeypatch.setattr(redis_store, "_write_message", delay_first_message)
    slow = asyncio.create_task(services.create_message(users.alice.id, conversation["id"], "slow"))
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        fast = await services.create_message(users.alice.id, conversation["id"], "fast")
        history = await services.list_messages(users.bob.id, conversation["id"])
        assert [message["body"] for message in history] == ["fast"]
        await services.mark_conversation_read(users.bob.id, conversation["id"], fast["id"])
    finally:
        release.set()
        await slow
    assert (await services.list_conversations(users.bob.id))[0]["unread_count"] == 1


async def test_peer_read_receipts_are_directional_persistent_and_never_move_backwards(users, redis_store):
    conversation = await services.get_or_create_conversation(users.alice.id, users.bob.id)
    assert conversation["other_last_read_message_id"] is None
    assert await redis_store.last_read_message_id(conversation["id"], users.bob.id) is None
    first = await services.create_message(users.alice.id, conversation["id"], "one")
    reply = await services.create_message(users.bob.id, conversation["id"], "reply")
    latest = await services.create_message(users.alice.id, conversation["id"], "two")

    alice_read = await services.mark_conversation_read(users.alice.id, conversation["id"], reply["id"])
    assert alice_read["other_last_read_message_id"] is None
    assert alice_read["unread_count"] == 0
    bob = (await services.list_conversations(users.bob.id))[0]
    assert bob["other_last_read_message_id"] == reply["id"]
    assert bob["unread_count"] == 2

    bob_read = await services.mark_conversation_read(users.bob.id, conversation["id"], latest["id"])
    assert bob_read["other_last_read_message_id"] == reply["id"]
    await services.mark_conversation_read(users.bob.id, conversation["id"], first["id"])
    alice = (await services.list_conversations(users.alice.id))[0]
    assert alice["other_last_read_message_id"] == latest["id"]
    assert alice["unread_count"] == 0
    reconnected = RedisMessageStore(redis_store.client, redis_store.prefix)
    assert await reconnected.last_read_message_id(conversation["id"], users.bob.id) == latest["id"]
