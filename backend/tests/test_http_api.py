import pytest

from backend.app.app import create_app
from backend.app.config import Settings


@pytest.fixture
def api(tmp_path):
    app = create_app(Settings(f"sqlite://{tmp_path / 'api.sqlite3'}", False, 60, ["http://localhost:5173"]))
    return app.asgi_client


async def identities(api):
    _, response = await api.get("/api/demo-users")
    assert response.status == 200
    return {user["username"]: {"X-User-Id": str(user["id"])} for user in response.json}


async def test_http_auth_search_conversation_and_history(api):
    headers = await identities(api)
    _, response = await api.get("/api/me")
    assert response.status == 401 and response.json["error"]["code"] == "unauthorized"
    _, response = await api.get("/api/me", headers={"X-User-Id": "999"})
    assert response.status == 401
    _, response = await api.get("/api/users/search?q=@BO", headers=headers["alice"])
    assert [user["username"] for user in response.json] == ["bob"]
    bob = response.json[0]
    _, response = await api.post("/api/conversations", headers=headers["alice"], json={"user_id": bob["id"]})
    assert response.status == 200
    conversation = response.json
    assert conversation["other_user"]["username"] == "bob"
    _, response = await api.get(f"/api/conversations/{conversation['id']}/messages", headers=headers["alice"])
    assert response.status == 200 and len(response.json) > 0
    assert set(response.json[0]) == {"id", "conversation_id", "sender_id", "body", "created_at", "expires_at"}
    _, response = await api.get(f"/api/conversations/{conversation['id']}/messages", headers=headers["carol"])
    assert response.status == 403
    _, response = await api.patch(f"/api/conversations/{conversation['id']}/ttl", headers=headers["bob"], json={"ttl_seconds": 3600})
    assert response.status == 200 and response.json["ttl_seconds"] == 3600


@pytest.mark.parametrize("payload", [True, 42, [], "text", {"user_id": True}, {"user_id": "2"}, {}])
async def test_http_create_rejects_nonobject_and_invalid_id(api, payload):
    headers = await identities(api)
    _, response = await api.post("/api/conversations", headers=headers["alice"], json=payload)
    assert response.status == 400 and "error" in response.json


@pytest.mark.parametrize("payload", [[], True, {}, {"ttl_seconds": True}, {"ttl_seconds": 3600.0}, {"ttl_seconds": 30}])
async def test_http_ttl_rejects_missing_and_invalid_values(api, payload):
    headers = await identities(api)
    _, response = await api.get("/api/conversations", headers=headers["alice"])
    conversation_id = response.json[0]["id"]
    _, response = await api.patch(f"/api/conversations/{conversation_id}/ttl", headers=headers["alice"], json=payload)
    assert response.status == 400


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "limit=true", "before=-1", "before=1.5", "before=999999999999999999999999"])
async def test_http_history_rejects_invalid_pagination(api, query):
    headers = await identities(api)
    _, response = await api.get("/api/conversations", headers=headers["alice"])
    _, response = await api.get(f"/api/conversations/{response.json[0]['id']}/messages?{query}", headers=headers["alice"])
    assert response.status == 400


async def test_cors_preflight_and_health(api):
    _, response = await api.options("/api/conversations", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
    assert response.status in (200, 204)
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert "X-User-Id" in response.headers["Access-Control-Allow-Headers"]
    _, response = await api.get("/api/health")
    assert response.json == {"status": "ok"}


async def test_invalid_json_and_large_ids_remain_structured_errors(api):
    headers = await identities(api)
    _, response = await api.post("/api/conversations", headers={**headers["alice"], "Content-Type": "application/json"}, content="{bad")
    assert response.status == 400 and "error" in response.json
    _, response = await api.post("/api/conversations", headers=headers["alice"], json={"user_id": 10**50})
    assert response.status == 400
    _, response = await api.get("/api/me", headers={"X-User-Id": "9" * 5000})
    assert response.status == 401 and "error" in response.json


async def test_operational_db_error_returns_503(api, monkeypatch):
    from backend.app import http_api
    from tortoise.exceptions import OperationalError

    async def unavailable(*args):
        raise OperationalError("Connection lost")

    monkeypatch.setattr(http_api, "search_users", unavailable)
    _, response = await api.get("/api/users/search?q=bob", headers={"X-User-Id": "1"})
    assert response.status == 503 and response.json["error"]["code"] == "database_unavailable"
