import asyncio
import json

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
