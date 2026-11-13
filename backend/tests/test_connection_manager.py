import asyncio
import json
from collections import defaultdict
from types import SimpleNamespace

import pytest

from backend.app import websocket


@pytest.mark.parametrize("send_mode", ["failed", "blocked"])
@pytest.mark.parametrize("close_mode", ["normal", "failed", "blocked"])
async def test_failed_broadcast_closes_socket_and_preserves_healthy_peer(
    monkeypatch, caplog, send_mode, close_mode
):
    monkeypatch.setattr(websocket, "SEND_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(websocket, "CLOSE_TIMEOUT_SECONDS", 0.01)
    manager = websocket.ConnectionManager()

    class UnhealthySocket:
        close_code = None

        async def send(self, payload):
            if send_mode == "failed":
                raise OSError("transport unavailable")
            await asyncio.Event().wait()

        async def close(self, *, code):
            self.close_code = code
            if close_mode == "failed":
                raise OSError("close unavailable")
            if close_mode == "blocked":
                await asyncio.Event().wait()

    class HealthySocket:
        def __init__(self):
            self.received = []

        async def send(self, payload):
            self.received.append(json.loads(payload))

    unhealthy, healthy = UnhealthySocket(), HealthySocket()
    manager.connect(7, unhealthy)
    manager.connect(7, healthy)
    event = {"type": "message.created", "data": {"id": 42}}

    await asyncio.wait_for(manager.broadcast(7, event), timeout=0.5)

    assert unhealthy.close_code == 1013
    assert manager.connections[7] == {healthy}
    assert healthy.received == [event]
    if close_mode != "normal":
        assert "Failed to close" in caplog.text

    await manager.broadcast(7, event)
    assert healthy.received == [event, event]


async def test_reconnect_cannot_deliver_old_unread_snapshot_after_newer_update(monkeypatch):
    events_manager = websocket.ConnectionManager()
    monkeypatch.setattr(websocket, "events_manager", events_manager)
    monkeypatch.setattr(websocket, "notification_locks", defaultdict(asyncio.Lock))
    snapshot_started, release_snapshot, second_requested = asyncio.Event(), asyncio.Event(), asyncio.Event()
    conversation = SimpleNamespace(id=7, user_a_id=1, user_b_id=2)
    requests = 0

    class Conversations:
        @staticmethod
        async def get_or_none(**kwargs):
            nonlocal requests
            requests += 1
            if requests == 2:
                second_requested.set()
            return conversation

        @staticmethod
        async def get(**kwargs):
            return conversation

    snapshots = 0

    async def conversation_snapshot(*args):
        nonlocal snapshots
        snapshots += 1
        if snapshots == 1:
            snapshot_started.set()
            await release_snapshot.wait()
            return {"id": 7, "unread_count": 1}
        return {"id": 7, "unread_count": 0}

    async def user_id(*args):
        return 1

    monkeypatch.setattr(websocket, "Conversation", Conversations)
    monkeypatch.setattr(websocket, "conversation_to_dict", conversation_snapshot)
    monkeypatch.setattr(websocket, "socket_user_id", user_id)
    monkeypatch.setattr(websocket, "require_user", user_id)

    class Socket:
        def __init__(self):
            self.started, self.stop = asyncio.Event(), asyncio.Event()
            self.received = []

        def __aiter__(self):
            return self

        async def __anext__(self):
            self.started.set()
            await self.stop.wait()
            raise StopAsyncIteration

        async def send(self, payload):
            self.received.append(json.loads(payload))

    original, reconnected = Socket(), Socket()
    tasks = []
    try:
        original_task = asyncio.create_task(websocket.user_events_socket(SimpleNamespace(), original))
        tasks.append(original_task)
        await original.started.wait()
        first = asyncio.create_task(websocket.notify_conversation(7, [1]))
        tasks.append(first)
        await snapshot_started.wait()
        original.stop.set()
        await original_task
        replacement_task = asyncio.create_task(websocket.user_events_socket(SimpleNamespace(), reconnected))
        tasks.append(replacement_task)
        await reconnected.started.wait()
        second = asyncio.create_task(websocket.notify_conversation(7, [1]))
        tasks.append(second)
        await second_requested.wait()
        # Let the newer notification attempt its lock while the old DTO is held.
        await asyncio.sleep(0)
        release_snapshot.set()
        await asyncio.gather(first, second)
        assert [event["data"]["unread_count"] for event in reconnected.received] == [1, 0]
    finally:
        release_snapshot.set()
        original.stop.set()
        reconnected.stop.set()
        await asyncio.gather(*tasks, return_exceptions=True)
