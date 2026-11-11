from types import SimpleNamespace

import pytest_asyncio


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
