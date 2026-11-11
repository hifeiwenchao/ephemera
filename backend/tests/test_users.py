import pytest

from backend.app.errors import UnauthorizedError
from backend.app.services import search_users


async def test_search_normalizes_case_at_sign_and_excludes_self(users):
    assert [user["username"] for user in await search_users(users.alice.id, " @BO ")] == ["bob"]
    assert await search_users(users.alice.id, "ALICE") == []
    assert await search_users(users.alice.id, "b") == []


async def test_search_unknown_user_is_unauthorized(db):
    with pytest.raises(UnauthorizedError):
        await search_users(999, "bob")
