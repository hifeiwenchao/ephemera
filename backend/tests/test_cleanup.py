from datetime import datetime, timedelta, timezone

from backend.app.cleanup import cleanup_expired_messages
from backend.app.models import Conversation, Message


async def test_cleanup_deletes_only_expired_and_broadcasts_ids(users):
    conversation = await Conversation.create(user_a_id=users.alice.id, user_b_id=users.bob.id)
    now = datetime.now(timezone.utc)
    expired = await Message.create(conversation=conversation, sender=users.alice, body="到期", expires_at=now)
    future = await Message.create(conversation=conversation, sender=users.alice, body="稍后", expires_at=now + timedelta(hours=1))
    permanent = await Message.create(conversation=conversation, sender=users.bob, body="保留")
    events = []

    class Subscriber:
        async def send(self, value):
            import json
            events.append(json.loads(value))

    from backend.app.websocket import manager
    socket = Subscriber()
    manager.connect(conversation.id, socket)
    try:
        assert await cleanup_expired_messages(now) == 1
        assert await cleanup_expired_messages(now) == 0
        assert set(await Message.all().values_list("id", flat=True)) == {future.id, permanent.id}
        assert events == [{"type": "message.deleted", "data": {"ids": [expired.id]}}]
    finally:
        manager.disconnect(conversation.id, socket)
