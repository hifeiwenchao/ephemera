"""Redis message bodies, history indexes and absolute message expiry.

MySQL owns users and conversation metadata. This module never flushes Redis;
every key is scoped to the configured prefix.
"""

import json
import math
from datetime import datetime, timezone

from redis.asyncio import Redis
from redis.exceptions import WatchError


def utcnow():
    return datetime.now(timezone.utc)


def timestamp(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def iso_time(value):
    return timestamp(value).isoformat().replace("+00:00", "Z")


class RedisMessageStore:
    def __init__(self, client, prefix="whisper:"):
        self.client = client
        self.prefix = prefix if prefix.endswith(":") else prefix + ":"

    @property
    def sequence_key(self):
        return f"{self.prefix}message_sequence"

    @property
    def expirations_key(self):
        return f"{self.prefix}message_expirations"

    def message_key(self, message_id):
        return f"{self.prefix}message:{message_id}"

    def history_key(self, conversation_id):
        return f"{self.prefix}conversation:{conversation_id}:messages"

    def read_cursor_key(self, conversation_id, user_id):
        return f"{self.prefix}conversation:{conversation_id}:read:{user_id}"

    async def last_read_message_id(self, conversation_id, user_id):
        value = await self.client.get(self.read_cursor_key(conversation_id, user_id))
        return int(value) if value is not None else None

    async def mark_read(self, conversation_id, user_id, message_id):
        """Advance this reader only; a delayed request must never move backward."""
        if await self.client.zscore(self.history_key(conversation_id), message_id) is None:
            return False
        key = self.read_cursor_key(conversation_id, user_id)
        while True:
            async with self.client.pipeline(transaction=True) as pipeline:
                try:
                    await pipeline.watch(key)
                    current = int(await pipeline.get(key) or 0)
                    if current >= message_id:
                        await pipeline.unwatch()
                        return True
                    pipeline.multi()
                    pipeline.set(key, message_id)
                    await pipeline.execute()
                    return True
                except WatchError:
                    continue

    async def unread_count(self, conversation_id, user_id):
        cursor = await self.last_read_message_id(conversation_id, user_id) or 0
        minimum = f"({cursor}"
        count = 0
        now = utcnow()
        while True:
            ids = await self.client.zrangebyscore(
                self.history_key(conversation_id), minimum, "+inf", start=0, num=100
            )
            if not ids:
                return count
            values = await self.client.mget([self.message_key(int(message_id)) for message_id in ids])
            for raw in values:
                if raw is None:
                    continue
                message = json.loads(raw)
                if message["sender_id"] == user_id:
                    continue
                if message.get("expires_at") and timestamp(message["expires_at"]) <= now:
                    continue
                count += 1
            minimum = f"({int(ids[-1])}"

    async def reserve_sequence(self, minimum):
        """Atomically raise the global sequence, never lowering active IDs."""
        while True:
            async with self.client.pipeline(transaction=True) as pipeline:
                try:
                    await pipeline.watch(self.sequence_key)
                    current = int(await pipeline.get(self.sequence_key) or 0)
                    if current >= minimum:
                        await pipeline.unwatch()
                        return current
                    pipeline.multi()
                    pipeline.set(self.sequence_key, minimum)
                    await pipeline.execute()
                    return minimum
                except WatchError:
                    continue

    def _queue_message(self, pipeline, message):
        message_id = message["id"]
        conversation_id = message["conversation_id"]
        expiration = message.get("expires_at")
        # Floor to ensure Redis never retains a body past the advertised expiry.
        expiry_ms = math.floor(timestamp(expiration).timestamp() * 1000) if expiration else None
        member = f"{conversation_id}:{message_id}"
        pipeline.set(
            self.message_key(message_id),
            json.dumps(message, ensure_ascii=False),
            pxat=expiry_ms,
        )
        pipeline.zadd(self.history_key(conversation_id), {str(message_id): message_id})
        if expiry_ms is not None:
            pipeline.zadd(self.expirations_key, {member: expiry_ms})
        else:
            pipeline.zrem(self.expirations_key, member)

    async def _write_message(self, message, *, pipeline=None):
        if pipeline is not None:
            self._queue_message(pipeline, message)
            return
        async with self.client.pipeline(transaction=True) as transaction:
            self._queue_message(transaction, message)
            await transaction.execute()

    async def create_message(self, conversation_id, sender_id, body, *, created_at=None, expires_at=None):
        content = {
            "conversation_id": conversation_id,
            "sender_id": sender_id,
            "body": body,
            "created_at": iso_time(created_at or utcnow()),
            "expires_at": iso_time(expires_at) if expires_at else None,
        }
        # Publish the ID and message together: reserving an ID in a separate
        # command could let a late lower ID fall behind a reader's cursor.
        while True:
            async with self.client.pipeline(transaction=True) as pipeline:
                try:
                    await pipeline.watch(self.sequence_key)
                    message_id = int(await pipeline.get(self.sequence_key) or 0) + 1
                    message = {"id": message_id, **content}
                    pipeline.multi()
                    pipeline.set(self.sequence_key, message_id)
                    await self._write_message(message, pipeline=pipeline)
                    await pipeline.execute()
                    return message
                except WatchError:
                    continue

    async def import_message(self, message):
        """Import an existing public DTO, retaining IDs/timestamps and expiry.

        Call with complete Message DTO dictionaries. Expired bodies are skipped,
        while their IDs still reserve sequence space. Safe to repeat imports.
        """
        await self.reserve_sequence(message["id"])
        if message.get("expires_at") and timestamp(message["expires_at"]) <= utcnow():
            return False
        await self._write_message(dict(message))
        return True

    async def get_message(self, message_id, *, now=None):
        raw = await self.client.get(self.message_key(message_id))
        if raw is None:
            return None
        message = json.loads(raw)
        if message.get("expires_at") and timestamp(message["expires_at"]) <= (now or utcnow()):
            return None
        return message

    async def list_messages(self, conversation_id, limit=50, before_id=None):
        messages = []
        maximum = f"({before_id}" if before_id is not None else "+inf"
        now = utcnow()
        batch_size = max(100, limit * 2)
        while len(messages) < limit:
            ids = await self.client.zrevrangebyscore(
                self.history_key(conversation_id), maximum, "-inf", start=0, num=batch_size
            )
            if not ids:
                break
            values = await self.client.mget([self.message_key(int(message_id)) for message_id in ids])
            for raw in values:
                if raw is None:
                    continue
                message = json.loads(raw)
                if message.get("expires_at") and timestamp(message["expires_at"]) <= now:
                    continue
                messages.append(message)
                if len(messages) == limit:
                    break
            maximum = f"({int(ids[-1])}"
        return list(reversed(messages))

    async def last_message(self, conversation_id):
        messages = await self.list_messages(conversation_id, limit=1)
        return messages[0] if messages else None

    async def cleanup_expired(self, now=None):
        """Remove expired history references and return IDs for deletion events."""
        cutoff = math.floor((now or utcnow()).timestamp() * 1000)
        deleted = {}
        while True:
            members = await self.client.zrangebyscore(self.expirations_key, "-inf", cutoff, start=0, num=1000)
            if not members:
                break
            async with self.client.pipeline(transaction=True) as pipeline:
                for member in members:
                    if isinstance(member, bytes):
                        member = member.decode()
                    conversation_id, message_id = map(int, member.split(":"))
                    pipeline.delete(self.message_key(message_id))
                    pipeline.zrem(self.history_key(conversation_id), message_id)
                    pipeline.zrem(self.expirations_key, member)
                    deleted.setdefault(conversation_id, []).append(message_id)
                await pipeline.execute()
        return deleted


_message_store = None


async def init_message_store(redis_url, prefix="whisper:", *, client=None):
    global _message_store
    client = client or Redis.from_url(
        redis_url, decode_responses=True, socket_connect_timeout=3, socket_timeout=3
    )
    try:
        await client.ping()
    except Exception:
        await client.aclose()
        raise
    _message_store = RedisMessageStore(client, prefix)
    return _message_store


def get_message_store():
    if _message_store is None:
        raise RuntimeError("Redis message store has not been initialized")
    return _message_store


async def close_message_store():
    global _message_store
    if _message_store is not None:
        await _message_store.client.aclose()
        _message_store = None
