from types import SimpleNamespace

import pytest_asyncio
import fakeredis
import fakeredis.aioredis


@pytest_asyncio.fixture(autouse=True)
async def redis_store(monkeypatch):
    from backend.app import message_store

    server = fakeredis.FakeServer()

    def fake_client(*args, **kwargs):
        return fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)

    monkeypatch.setattr(message_store.Redis, "from_url", fake_client)
    store = await message_store.init_message_store("redis://unused")
    yield store
    await message_store.close_message_store()


@pytest_asyncio.fixture
async def db():
    from backend.app.db import close_db, init_db

    await init_db("sqlite://:memory:", generate_schemas=True)
    yield
    await close_db()


@pytest_asyncio.fixture
async def users(db):
    from backend.app.models import User

    result = {}
    for username, display_name in [("alice", "艾莉丝"), ("bob", "林间"), ("carol", "陈沐")]:
        result[username] = await User.create(username=username, display_name=display_name)
    return SimpleNamespace(**result)
