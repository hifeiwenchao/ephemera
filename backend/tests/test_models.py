import pytest
from tortoise.exceptions import IntegrityError

from backend.app.models import Conversation, User
from backend.app.schemas import parse_ttl_seconds, user_to_dict
from backend.app.seed import seed_demo_data


@pytest.mark.parametrize("value", [None, 3600, 86400, 604800, 2592000])
def test_supported_ttl(value):
    assert parse_ttl_seconds(value) == value


@pytest.mark.parametrize("value", [True, False, 0, 30, "3600", 3600.0, [], {}])
def test_invalid_ttl(value):
    with pytest.raises(ValueError):
        parse_ttl_seconds(value)


async def test_participants_sorted_and_pair_unique(users):
    conversation = await Conversation.create(user_a_id=users.bob.id, user_b_id=users.alice.id)
    assert (conversation.user_a_id, conversation.user_b_id) == (users.alice.id, users.bob.id)
    with pytest.raises(IntegrityError):
        await Conversation.create(user_a_id=users.alice.id, user_b_id=users.bob.id)
    with pytest.raises(ValueError):
        await Conversation.create(user_a_id=users.alice.id, user_b_id=users.alice.id)


async def test_user_normalization_and_public_dto(users):
    with pytest.raises(IntegrityError):
        await User.create(username="ALICE", display_name="重复")
    assert user_to_dict(users.alice) == {
        "id": users.alice.id, "username": "alice", "display_name": "艾莉丝", "avatar_url": None,
    }


async def test_seed_idempotent(db):
    from backend.app.models import Message

    await seed_demo_data()
    count = await Message.all().count()
    assert count > 0
    await seed_demo_data()
    assert await User.all().count() == 5
    assert await Conversation.all().count() == 3
    assert await Message.all().count() == count
