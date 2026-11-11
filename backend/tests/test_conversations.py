import asyncio

import pytest

from backend.app.errors import ForbiddenError, NotFoundError, ValidationError
from backend.app.models import Conversation
from backend.app.services import get_or_create_conversation, list_conversations, list_messages, set_conversation_ttl


async def test_conversation_pair_is_idempotent_in_both_directions(users):
    results = await asyncio.gather(*[
        get_or_create_conversation(users.alice.id, users.bob.id),
        get_or_create_conversation(users.bob.id, users.alice.id),
        get_or_create_conversation(users.alice.id, users.bob.id),
    ])
    assert len({result["id"] for result in results}) == 1
    assert await Conversation.all().count() == 1
    assert results[0]["other_user"]["username"] == "bob"
    assert len(await list_conversations(users.alice.id)) == 1
    assert await list_conversations(users.carol.id) == []


async def test_self_and_unknown_recipient_rejected(users):
    with pytest.raises(ValidationError):
        await get_or_create_conversation(users.alice.id, users.alice.id)
    with pytest.raises(NotFoundError):
        await get_or_create_conversation(users.alice.id, 999)


async def test_nonmember_cannot_read_or_change_ttl(users):
    conversation = await get_or_create_conversation(users.alice.id, users.bob.id)
    with pytest.raises(ForbiddenError):
        await list_messages(users.carol.id, conversation["id"])
    with pytest.raises(ForbiddenError):
        await set_conversation_ttl(users.carol.id, conversation["id"], 3600)
