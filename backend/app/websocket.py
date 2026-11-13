import asyncio
import json
import logging
from collections import defaultdict

from sanic import Blueprint
from tortoise.exceptions import DBConnectionError, OperationalError
from redis.exceptions import RedisError

from .errors import AppError, UnauthorizedError, ValidationError, integer_text
from .models import Conversation
from .schemas import conversation_to_dict
from .services import create_message, require_conversation, require_user

logger = logging.getLogger(__name__)
SEND_TIMEOUT_SECONDS = 5
CLOSE_TIMEOUT_SECONDS = 1


class ConnectionManager:
    def __init__(self):
        self.connections = defaultdict(set)

    def connect(self, conversation_id, websocket):
        self.connections[conversation_id].add(websocket)

    def disconnect(self, conversation_id, websocket):
        connections = self.connections.get(conversation_id)
        if connections is not None:
            connections.discard(websocket)
            if not connections:
                self.connections.pop(conversation_id, None)

    async def broadcast(self, conversation_id, event):
        payload = json.dumps(event, ensure_ascii=False)

        async def send(websocket):
            try:
                await asyncio.wait_for(
                    websocket.send(payload), timeout=SEND_TIMEOUT_SECONDS
                )
            except Exception:
                self.disconnect(conversation_id, websocket)
                # A disconnected transport triggers the client's reconnect/resync.
                # Removing membership alone leaves an open but stale client.
                try:
                    await asyncio.wait_for(
                        websocket.close(code=1013), timeout=CLOSE_TIMEOUT_SECONDS
                    )
                except Exception:
                    logger.warning(
                        "Failed to close a removed socket for conversation %s",
                        conversation_id,
                        exc_info=True,
                    )

        await asyncio.gather(
            *(send(ws) for ws in tuple(self.connections.get(conversation_id, ())))
        )


manager = ConnectionManager()
events_manager = ConnectionManager()
# Keep locks stable across disconnects: an in-flight snapshot can outlive the
# last socket and must stay ordered with notifications after reconnection.
notification_locks = defaultdict(asyncio.Lock)
websocket_api = Blueprint("websocket_api")


async def notify_conversation(conversation_id, user_ids=None):
    """Send fresh, reader-specific snapshots to every connected device."""
    conversation = await Conversation.get_or_none(id=conversation_id)
    if conversation is None:
        return
    recipients = user_ids if user_ids is not None else (conversation.user_a_id, conversation.user_b_id)

    async def notify(user_id):
        if not events_manager.connections.get(user_id):
            return
        # Snapshot creation and sending share a lock so concurrent mutations
        # cannot deliver an older unread count after a newer notification.
        async with notification_locks[user_id]:
            current = await Conversation.get(id=conversation_id)
            data = await conversation_to_dict(current, user_id)
            await events_manager.broadcast(user_id, {"type": "conversation.updated", "data": data})

    await asyncio.gather(*(notify(user_id) for user_id in recipients))


async def socket_user_id(request):
    auth = getattr(request.app.ctx, "auth", None)
    cookie_name = getattr(auth, "cookie_name", "whisper_session")
    if auth is not None and cookie_name in request.cookies:
        return (await auth.authenticate_request(request)).id
    if auth is not None and not getattr(request.app.ctx.settings, "allow_legacy_identity", False):
        raise UnauthorizedError("请先登录")
    try:
        return integer_text(request.args.get("user_id", ""), "user_id")
    except ValidationError as error:
        raise UnauthorizedError("请先登录") from error


async def send_error(websocket, error):
    await websocket.send(
        json.dumps(
            {"type": "error", "code": error.code, "message": error.message},
            ensure_ascii=False,
        )
    )


@websocket_api.websocket("/ws/events")
async def user_events_socket(request, websocket):
    try:
        user_id = await socket_user_id(request)
        await require_user(user_id)
    except AppError as error:
        await send_error(websocket, error)
        await websocket.close(code=1008)
        return
    except (OperationalError, DBConnectionError, RedisError, OSError):
        await websocket.close(code=1013)
        return
    events_manager.connect(user_id, websocket)
    try:
        async for _ in websocket:
            await send_error(websocket, ValidationError("不支持的消息类型"))
    finally:
        events_manager.disconnect(user_id, websocket)


@websocket_api.websocket("/ws/conversations/<conversation_id:int>")
async def conversation_socket(request, websocket, conversation_id):
    try:
        user_id = await socket_user_id(request)
        await require_conversation(user_id, conversation_id)
    except AppError as error:
        await send_error(websocket, error)
        await websocket.close(code=1008)
        return
    except (OperationalError, DBConnectionError, RedisError, OSError):
        await websocket.send(
            json.dumps(
                {
                    "type": "error",
                    "code": "database_unavailable",
                    "message": "数据库暂时不可用，请稍后重试",
                }
            )
        )
        await websocket.close(code=1013)
        return

    connections = request.app.ctx.connections
    connections.connect(conversation_id, websocket)
    try:
        async for raw in websocket:
            try:
                try:
                    event = json.loads(raw)
                except (ValueError, TypeError, UnicodeError) as error:
                    raise ValidationError("消息必须是有效的 JSON") from error
                if not isinstance(event, dict) or event.get("type") != "message.send":
                    raise ValidationError("不支持的消息类型")
                message = await create_message(
                    user_id, conversation_id, event.get("body")
                )
                await connections.broadcast(
                    conversation_id, {"type": "message.created", "data": message}
                )
                await notify_conversation(conversation_id)
            except AppError as error:
                await send_error(websocket, error)
            except (OperationalError, DBConnectionError, RedisError, OSError):
                await websocket.send(
                    json.dumps(
                        {
                            "type": "error",
                            "code": "database_unavailable",
                            "message": "数据库暂时不可用，请稍后重试",
                        }
                    )
                )
    finally:
        connections.disconnect(conversation_id, websocket)
