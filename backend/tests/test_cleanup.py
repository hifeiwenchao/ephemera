from datetime import datetime, timedelta, timezone

from backend.app.cleanup import cleanup_expired_messages
from backend.app.models import Conversation


async def test_cleanup_deletes_only_expired_and_broadcasts_ids(users, redis_store):
    conversation = await Conversation.create(user_a_id=users.alice.id, user_b_id=users.bob.id)
    now = datetime.now(timezone.utc)
    expired = await redis_store.create_message(conversation.id, users.alice.id, "到期", expires_at=now - timedelta(seconds=1))
    future = await redis_store.create_message(conversation.id, users.alice.id, "稍后", expires_at=now + timedelta(hours=1))
    permanent = await redis_store.create_message(conversation.id, users.bob.id, "保留")
    events = []

    class Subscriber:
        async def send(self, value):
            import json
            events.append(json.loads(value))

    from backend.app.websocket import events_manager, manager
    socket = Subscriber()
    user_events = []

    class UserSubscriber:
        async def send(self, value):
            import json
            user_events.append(json.loads(value))

    reader = UserSubscriber()
    manager.connect(conversation.id, socket)
    events_manager.connect(users.bob.id, reader)
    try:
        assert await cleanup_expired_messages(now) == 1
        assert await cleanup_expired_messages(now) == 0
        assert {message["id"] for message in await redis_store.list_messages(conversation.id)} == {future["id"], permanent["id"]}
        assert events == [{"type": "message.deleted", "data": {"ids": [expired["id"]]}}]
        assert len(user_events) == 1
        assert user_events[0]["type"] == "conversation.updated"
        assert user_events[0]["data"]["id"] == conversation.id
        assert user_events[0]["data"]["unread_count"] == 1
    finally:
        manager.disconnect(conversation.id, socket)
        events_manager.disconnect(users.bob.id, reader)
