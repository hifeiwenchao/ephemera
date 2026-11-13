import asyncio
import json
import os
import socket
import subprocess
import sys
import time

import httpx
import pytest
from dotenv import dotenv_values
from redis import Redis
from uuid import uuid4
from websockets.asyncio.client import connect


@pytest.fixture
def live_server(tmp_path):
    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        port = port_socket.getsockname()[1]
    private_env = dotenv_values("backend/.env")
    redis_url = os.getenv("TEST_REDIS_URL") or private_env.get("REDIS_URL")
    if not redis_url:
        pytest.skip("TEST_REDIS_URL or backend/.env REDIS_URL is required for live socket tests")
    prefix = f"whisper:test-{uuid4().hex}:"
    env = {**os.environ, "DATABASE_URL": f"sqlite://{tmp_path / 'socket.sqlite3'}", "REDIS_URL": redis_url, "REDIS_PREFIX": prefix, "ALLOW_LEGACY_IDENTITY": "true", "AUTH_TEST_MODE": "true", "PORT": str(port), "DEBUG": "false", "CLEANUP_INTERVAL_SECONDS": "1"}
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
        redis = Redis.from_url(redis_url, decode_responses=True)
        for key in redis.scan_iter(f"{prefix}*"):
            redis.delete(key)
        redis.close()


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


async def test_periodic_cleanup_removes_row_and_notifies_live_sockets(live_server):
    async with httpx.AsyncClient(base_url=live_server) as client:
        users = (await client.get("/api/demo-users")).json()
        alice, bob = users[0]["id"], users[1]["id"]
        conversation = (await client.post("/api/conversations", headers={"X-User-Id": str(alice)}, json={"user_id": bob})).json()
        endpoint = live_server.replace("http://", "ws://") + f"/ws/conversations/{conversation['id']}"
        async with connect(f"{endpoint}?user_id={alice}") as first, connect(f"{endpoint}?user_id={bob}") as second:
            await client.patch(f"/api/conversations/{conversation['id']}/ttl", headers={"X-User-Id": str(alice)}, json={"ttl_seconds": 3600})
            await asyncio.gather(receive(first), receive(second))
            await first.send(json.dumps({"type": "message.send", "body": "测试清理"}))
            event, _ = await asyncio.gather(receive(first), receive(second))
            message_id = event["data"]["id"]
            redis = Redis.from_url(os.getenv("TEST_REDIS_URL") or dotenv_values("backend/.env")["REDIS_URL"], decode_responses=True)
            key = next(key for key in redis.scan_iter(f"whisper:test-*:*message:{message_id}"))
            redis.pexpire(key, 100)
            redis.zadd(
                next(key for key in redis.scan_iter("whisper:test-*:*message_expirations")),
                {f"{conversation['id']}:{message_id}": 1},
            )
            redis.close()
            deleted_a, deleted_b = await asyncio.gather(receive(first), receive(second))
            assert deleted_a == deleted_b == {"type": "message.deleted", "data": {"ids": [message_id]}}
            history = (await client.get(f"/api/conversations/{conversation['id']}/messages", headers={"X-User-Id": str(bob)})).json()
            assert message_id not in [message["id"] for message in history]


async def test_user_events_track_unopened_conversation_and_read_on_other_device(live_server):
    async with httpx.AsyncClient(base_url=live_server) as client:
        users = {user["username"]: user["id"] for user in (await client.get("/api/demo-users")).json()}
        alice, nina = users["alice"], users["nina"]
        ws_base = live_server.replace("http://", "ws://")
        async with connect(f"{ws_base}/ws/events?user_id={alice}") as alice_events, connect(f"{ws_base}/ws/events?user_id={nina}") as nina_events:
            conversation = (await client.post("/api/conversations", headers={"X-User-Id": str(alice)}, json={"user_id": nina})).json()
            first, second = await asyncio.gather(receive(alice_events), receive(nina_events))
            assert first["type"] == second["type"] == "conversation.updated"
            assert second["data"]["id"] == conversation["id"]
            assert second["data"]["unread_count"] == 0
            async with connect(f"{ws_base}/ws/conversations/{conversation['id']}?user_id={alice}") as sender:
                await sender.send(json.dumps({"type": "message.send", "body": "unopened chat"}))
                message = (await receive(sender))["data"]
                first, second = await asyncio.gather(receive(alice_events), receive(nina_events))
                assert first["data"]["unread_count"] == 0
                assert second["data"]["unread_count"] == 1
                assert second["data"]["last_message"]["body"] == "unopened chat"
                response = await client.post(f"/api/conversations/{conversation['id']}/read", headers={"X-User-Id": str(nina)}, json={"last_message_id": message["id"]})
                assert response.status_code == 200
                first, second = await asyncio.gather(receive(alice_events), receive(nina_events))
                assert first["data"]["other_last_read_message_id"] == message["id"]
                assert first["data"]["unread_count"] == 0
                assert second["data"]["unread_count"] == 0
                assert second["data"]["other_last_read_message_id"] is None
                await alice_events.close()
                async with connect(f"{ws_base}/ws/events?user_id={alice}") as reconnected:
                    conversations = (await client.get("/api/conversations", headers={"X-User-Id": str(alice)})).json()
                    persisted = next(item for item in conversations if item["id"] == conversation["id"])
                    assert persisted["other_last_read_message_id"] == message["id"]
                    response = await client.patch(f"/api/conversations/{conversation['id']}/ttl", headers={"X-User-Id": str(nina)}, json={"ttl_seconds": 3600})
                    assert response.status_code == 200
                    first, second = await asyncio.gather(receive(reconnected), receive(nina_events))
                    assert first["data"]["ttl_seconds"] == second["data"]["ttl_seconds"] == 3600
                    assert first["data"]["other_last_read_message_id"] == message["id"]


async def test_user_event_stream_rejects_missing_or_unknown_identity(live_server):
    endpoint = live_server.replace("http://", "ws://") + "/ws/events"
    for suffix in ["", "?user_id=999"]:
        async with connect(endpoint + suffix) as socket:
            assert (await receive(socket))["code"] == "unauthorized"
            await socket.wait_closed()
            assert socket.close_code == 1008


async def test_user_event_stream_uses_login_cookie_and_rejects_invalid_cookie(live_server):
    async with httpx.AsyncClient(base_url=live_server) as client:
        code = await client.post("/api/auth/email-code", json={"email": "reader@example.com", "purpose": "register"})
        assert code.status_code == 200
        registered = await client.post("/api/auth/register", json={
            "username": "reader", "display_name": "读者", "password": "a-good-password",
            "email": "reader@example.com", "code": "666666",
        })
        assert registered.status_code == 200
        endpoint = live_server.replace("http://", "ws://") + "/ws/events"
        cookie = "; ".join(f"{name}={value}" for name, value in client.cookies.items())
        async with connect(endpoint, additional_headers={"Cookie": cookie}) as events:
            users = {user["username"]: user["id"] for user in (await client.get("/api/demo-users")).json()}
            conversation = await client.post("/api/conversations", json={"user_id": users["alice"]})
            assert conversation.status_code == 200
            assert (await receive(events))["data"]["id"] == conversation.json()["id"]
        async with connect(endpoint, additional_headers={"Cookie": "whisper_session=invalid"}) as invalid:
            assert (await receive(invalid))["code"] == "unauthorized"
            await invalid.wait_closed()
            assert invalid.close_code == 1008
