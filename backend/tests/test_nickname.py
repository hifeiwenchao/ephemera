import pytest

from backend.app.auth import normalize_display_name, validate_registration
from backend.app.errors import ValidationError
from backend.app.models import User
from backend.app.services import search_users


def test_display_name_accepts_chinese_ascii_and_allowed_symbols():
    for value in ["小明", "Alice123", "A!@#$%^&*()"]:
        assert normalize_display_name(value) == value


@pytest.mark.parametrize("value", [None, "", " ", "名字_", "名字/", "名字🙂", "a" * 13])
def test_display_name_is_required_and_rejects_disallowed_or_long_values(value):
    with pytest.raises(ValidationError):
        normalize_display_name(value)


async def test_registration_requires_display_name_and_search_matches_username_or_display_name(users):
    with pytest.raises(ValidationError):
        validate_registration("newuser", "password123", None, "new@example.com", "123456")
    nickname_user = await User.create(username="nickname", display_name="山海Alice")
    username_user = await User.create(username="mountain", display_name="普通昵称")
    assert [item["username"] for item in await search_users(users.alice.id, "山海")] == ["nickname"]
    assert [item["username"] for item in await search_users(users.alice.id, "alice")] == ["nickname"]
    assert [item["username"] for item in await search_users(users.alice.id, "mount")] == ["mountain"]
    assert nickname_user.id != username_user.id


async def test_display_name_unique_at_database_layer(users):
    from tortoise.exceptions import IntegrityError

    with pytest.raises(IntegrityError):
        await User.create(username="another", display_name=users.alice.display_name)
