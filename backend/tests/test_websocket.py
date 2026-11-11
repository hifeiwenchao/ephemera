import asyncio
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time

import httpx
import pytest
from websockets.asyncio.client import connect


@pytest.fixture
def live_server(tmp_path):
    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        port = port_socket.getsockname()[1]
    env = {**os.environ, "DATABASE_URL": f"sqlite://{tmp_path / 'socket.sqlite3'}", "PORT": str(port), "DEBUG": "false", "CLEANUP_INTERVAL_SECONDS": "1"}
    log = (tmp_path / "server.log").open("w+")
    process = subprocess.Popen([sys.executable, "-m", "backend.app.app"], env=env, stdout=log, stderr=log)
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"{base}/api/health", timeout=0.2).status_code == 200:
                    break
            except httpx.RequestError:
                pass
            if process.poll() is not None:
                break
            time.sleep(0.1)
        else:
            log.seek(0)
            pytest.fail(f"Server did not start: {log.read()[-6000:]}")
        if process.poll() is not None:
            log.seek(0)
            pytest.fail(log.read())
        yield base
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
        log.close()


async def receive(ws):
    return json.loads(await asyncio.wait_for(ws.recv(), timeout=3))


async def test_two_real_sockets_broadcast_validate_and_ttl_notification(live_server):
    async with httpx.AsyncClient(base_url=live_server) as client:
        users = {user["username"]: user for user in (await client.get("/api/demo-users")).json()}
        alice, bob = users["alice"]["id"], users["bob"]["id"]
        conversation = (await client.post("/api/conversations", headers={"X-User-Id": str(alice)}, json={"user_id": bob})).json()
        endpoint = live_server.replace("http://", "ws://") + f"/ws/conversations/{conversation['id']}"
        async with connect(f"{endpoint}?user_id={alice}") as first, connect(f"{endpoint}?user_id={bob}") as second:
            await first.send(json.dumps({"type": "message.send", "body": "实时消息 🌿"}))
            one, two = await asyncio.gather(receive(first), receive(second))
            assert one == two
            assert one["type"] == "message.created" and one["data"]["body"] == "实时消息 🌿"
            for invalid in ["not-json", "[]", "true", '{"type":"message.send","body":true}', '{"type":"unknown"}']:
                await first.send(invalid)
                assert (await receive(first))["type"] == "error"
            response = await client.patch(f"/api/conversations/{conversation['id']}/ttl", headers={"X-User-Id": str(alice)}, json={"ttl_seconds": 3600})
            assert response.status_code == 200
            one, two = await asyncio.gather(receive(first), receive(second))
            assert one == two == {"type": "conversation.updated", "data": {"id": conversation["id"], "ttl_seconds": 3600}}
            await second.send(json.dumps({"type": "message.send", "body": "仍然在线"}))
            one, two = await asyncio.gather(receive(first), receive(second))
            assert one == two and one["data"]["expires_at"] is not None
        async with connect(f"{endpoint}?user_id={users['carol']['id']}") as unauthorized:
            assert (await receive(unauthorized))["code"] == "forbidden"


async def test_periodic_cleanup_removes_row_and_notifies_live_sockets(live_server, tmp_path):
    async with httpx.AsyncClient(base_url=live_server) as client:
        users = (await client.get("/api/demo-users")).json()
        alice, bob = users[0]["id"], users[1]["id"]
        conversation = (await client.post("/api/conversations", headers={"X-User-Id": str(alice)}, json={"user_id": bob})).json()
        endpoint = live_server.replace("http://", "ws://") + f"/ws/conversations/{conversation['id']}"
        async with connect(f"{endpoint}?user_id={alice}") as first, connect(f"{endpoint}?user_id={bob}") as second:
            await first.send(json.dumps({"type": "message.send", "body": "测试清理"}))
            event, _ = await asyncio.gather(receive(first), receive(second))
            message_id = event["data"]["id"]
            with sqlite3.connect(tmp_path / "socket.sqlite3") as connection:
                connection.execute("UPDATE message SET expires_at = '2000-01-01 00:00:00+00:00' WHERE id = ?", (message_id,))
            deleted_a, deleted_b = await asyncio.gather(receive(first), receive(second))
            assert deleted_a == deleted_b == {"type": "message.deleted", "data": {"ids": [message_id]}}
            history = (await client.get(f"/api/conversations/{conversation['id']}/messages", headers={"X-User-Id": str(bob)})).json()
            assert message_id not in [message["id"] for message in history]
            with sqlite3.connect(tmp_path / "socket.sqlite3") as connection:
                assert connection.execute("SELECT COUNT(*) FROM message WHERE id = ?", (message_id,)).fetchone()[0] == 0
