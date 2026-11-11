import asyncio
import json
import logging
from collections import defaultdict

from sanic import Blueprint
from tortoise.exceptions import DBConnectionError, OperationalError

from .errors import AppError, UnauthorizedError, ValidationError, integer_text
from .services import create_message, require_conversation

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
websocket_api = Blueprint("websocket_api")


async def send_error(websocket, error):
    await websocket.send(
        json.dumps(
            {"type": "error", "code": error.code, "message": error.message},
            ensure_ascii=False,
        )
    )


@websocket_api.websocket("/ws/conversations/<conversation_id:int>")
async def conversation_socket(request, websocket, conversation_id):
    try:
        value = request.args.get("user_id", "")
        try:
            user_id = integer_text(value, "user_id")
        except ValidationError as error:
            raise UnauthorizedError("请选择有效的演示用户") from error
        await require_conversation(user_id, conversation_id)
    except AppError as error:
        await send_error(websocket, error)
        await websocket.close(code=1008)
        return
    except (OperationalError, DBConnectionError, OSError):
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
            except AppError as error:
                await send_error(websocket, error)
            except (OperationalError, DBConnectionError, OSError):
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
