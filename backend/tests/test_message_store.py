import asyncio
from datetime import datetime, timedelta, timezone

import fakeredis.aioredis
import pytest_asyncio

from backend.app.message_store import RedisMessageStore


@pytest_asyncio.fixture
async def store():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield RedisMessageStore(client, "whisper:test:")
    await client.aclose()


async def test_native_ttl_expires_body_before_index_cleanup(store):
    now = datetime.now(timezone.utc)
    message = await store.create_message(7, 1, "你好 🌿", created_at=now, expires_at=now + timedelta(milliseconds=70))
    key = store.message_key(message["id"])
    assert 0 < await store.client.pttl(key) <= 70
    await asyncio.sleep(0.1)
    assert await store.client.get(key) is None
    assert await store.list_messages(7) == []
    assert await store.client.zcard(store.history_key(7)) == 1
    assert await store.cleanup_expired() == {7: [message["id"]]}
    assert await store.client.zcard(store.history_key(7)) == 0
    assert await store.cleanup_expired() == {}


async def test_permanent_messages_have_no_ttl_and_pagination_skips_missing(store):
    first = await store.create_message(7, 1, "one")
    missing = await store.create_message(7, 2, "removed")
    third = await store.create_message(7, 1, "three")
    fourth = await store.create_message(7, 2, "four")
    await store.client.delete(store.message_key(missing["id"]))
    assert await store.client.pttl(store.message_key(first["id"])) == -1
    assert [message["id"] for message in await store.list_messages(7, limit=3)] == [first["id"], third["id"], fourth["id"]]
    assert [message["id"] for message in await store.list_messages(7, before_id=third["id"])] == [first["id"]]
    assert await store.last_message(7) == fourth


async def test_import_preserves_dto_expiry_and_advances_global_ids(store):
    now = datetime.now(timezone.utc)
    payload = {"id": 500, "conversation_id": 7, "sender_id": 2, "body": "历史消息", "created_at": "2026-01-01T00:00:00Z", "expires_at": (now + timedelta(hours=1)).isoformat()}
    assert await store.import_message(payload) is True
    assert await store.import_message(payload) is True
    assert await store.get_message(500) == payload
    assert 3_590_000 < await store.client.pttl(store.message_key(500)) <= 3_600_000
    created = await store.create_message(8, 1, "新消息")
    assert created["id"] == 501
    assert len(await store.list_messages(7)) == 1


async def test_expired_import_is_skipped_and_sequence_still_preserved(store):
    payload = {"id": 900, "conversation_id": 7, "sender_id": 1, "body": "过期", "created_at": "2000-01-01T00:00:00Z", "expires_at": "2000-01-02T00:00:00Z"}
    assert await store.import_message(payload) is False
    assert await store.get_message(900) is None
    assert await store.client.zcard(store.history_key(7)) == 0
    assert (await store.create_message(7, 1, "新消息"))["id"] == 901


async def test_parallel_messages_use_global_unique_ids_and_isolated_prefix(store):
    await store.client.set("unrelated:key", "keep")
    messages = await asyncio.gather(*(store.create_message(7 + index % 2, 1, str(index)) for index in range(20)))
    assert sorted(message["id"] for message in messages) == list(range(1, 21))
    assert len(await store.list_messages(7)) == 10
    assert len(await store.list_messages(8)) == 10
    assert await store.client.get("unrelated:key") == "keep"
