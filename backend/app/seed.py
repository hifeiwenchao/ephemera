from datetime import datetime, timedelta, timezone

from .message_store import get_message_store
from .models import Conversation, User


async def seed_demo_data():
    first_launch = not await User.exists()
    users = {}
    for username, display_name in [("alice", "艾莉丝"), ("bob", "林间"), ("carol", "陈沐"), ("david", "顾远"), ("nina", "宁可")]:
        users[username], _ = await User.get_or_create(
            username_lower=username, defaults={"username": username, "display_name": display_name},
        )
    if not first_launch:
        return
    now = datetime.now(timezone.utc)
    samples = [
        ("bob", [("alice", "周末去海边走走？听说那边新开了一家咖啡馆。"), ("bob", "好呀，想念海风了。我们坐早一点的车吧 ☀️"), ("alice", "那就这么说定了，我来看看车次。")]),
        ("carol", [("carol", "上次说的那本书，我放在工作室的桌上了。"), ("alice", "收到，谢谢你！读完我们再聊。"), ("carol", "不着急，慢慢看。里面有一段写得很美。")]),
        ("david", [("david", "今天路过花店，看到很漂亮的洋甘菊。"), ("alice", "听起来是个不错的下午 🌿")]),
    ]
    for index, (other, messages) in enumerate(samples):
        conversation = await Conversation.create(user_a_id=users["alice"].id, user_b_id=users[other].id)
        latest = now - timedelta(minutes=5 + index * 25)
        for offset, (sender, body) in enumerate(messages):
            await get_message_store().create_message(conversation.id, users[sender].id, body, created_at=latest - timedelta(minutes=len(messages) - offset - 1))
        conversation.updated_at = latest
        await conversation.save(update_fields=["updated_at"])
