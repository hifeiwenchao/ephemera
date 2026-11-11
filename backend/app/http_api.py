from sanic import Blueprint, response

from .errors import UnauthorizedError, ValidationError, integer_text
from .models import User
from .schemas import user_to_dict
from .services import get_or_create_conversation, list_conversations, list_messages, require_user, search_users, set_conversation_ttl

api = Blueprint("api", url_prefix="/api")


def require_user_id(request):
    value = request.headers.get("X-User-Id", "")
    try:
        return integer_text(value, "X-User-Id")
    except ValidationError as error:
        raise UnauthorizedError("请通过 X-User-Id 选择演示用户") from error


def object_body(request):
    body = request.json
    if not isinstance(body, dict):
        raise ValidationError("请求体必须是 JSON 对象")
    return body


def query_integer(request, name, default=None):
    value = request.args.get(name)
    if value is None:
        return default
    return integer_text(value, name)


@api.get("/health")
async def health(request):
    await User.all().limit(1)
    return response.json({"status": "ok"})


@api.get("/demo-users")
async def demo_users(request):
    return response.json([user_to_dict(user) for user in await User.all().order_by("id")])


@api.get("/me")
async def me(request):
    return response.json(user_to_dict(await require_user(require_user_id(request))))


@api.get("/users/search")
async def users_search(request):
    return response.json(await search_users(require_user_id(request), request.args.get("q", "")))


@api.get("/conversations")
async def conversations(request):
    return response.json(await list_conversations(require_user_id(request)))


@api.post("/conversations")
async def conversations_create(request):
    user_id = require_user_id(request)
    body = object_body(request)
    return response.json(await get_or_create_conversation(user_id, body.get("user_id")))


@api.get("/conversations/<conversation_id:int>/messages")
async def messages(request, conversation_id):
    return response.json(await list_messages(
        require_user_id(request), conversation_id,
        limit=query_integer(request, "limit", 50), before_id=query_integer(request, "before"),
    ))


@api.patch("/conversations/<conversation_id:int>/ttl")
async def conversation_ttl(request, conversation_id):
    user_id = require_user_id(request)
    body = object_body(request)
    if "ttl_seconds" not in body:
        raise ValidationError("缺少 ttl_seconds")
    conversation = await set_conversation_ttl(user_id, conversation_id, body["ttl_seconds"])
    await request.app.ctx.connections.broadcast(conversation_id, {
        "type": "conversation.updated", "data": {"id": conversation_id, "ttl_seconds": conversation["ttl_seconds"]},
    })
    return response.json(conversation)


@api.options("/health", name="health_options")
@api.options("/demo-users", name="demo_users_options")
@api.options("/me", name="me_options")
@api.options("/users/search", name="search_options")
@api.options("/conversations", name="conversations_options")
@api.options("/conversations/<conversation_id:int>/messages", name="messages_options")
@api.options("/conversations/<conversation_id:int>/ttl", name="ttl_options")
async def preflight(request, conversation_id=None):
    return response.empty()
