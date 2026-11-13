from sanic import Blueprint, response
from redis.exceptions import RedisError

from .errors import UnauthorizedError, ValidationError, integer_text
from .models import User
from .schemas import user_to_dict
from .services import get_or_create_conversation, list_conversations, list_messages, mark_conversation_read, require_user, search_users, set_conversation_ttl
from .message_store import get_message_store
from .websocket import notify_conversation

api = Blueprint("api", url_prefix="/api")


async def require_user_id(request):
    auth = getattr(request.app.ctx, "auth", None)
    if auth is not None:
        cookie_name = getattr(auth, "cookie_name", "whisper_session")
        if cookie_name in request.cookies:
            return (await auth.authenticate_request(request)).id
        if not getattr(request.app.ctx.settings, "allow_legacy_identity", False):
            raise UnauthorizedError("请先登录")
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
    try:
        await get_message_store().client.ping()
    except RedisError as error:
        raise RuntimeError("Redis unavailable") from error
    return response.json({"status": "ok"})


@api.get("/demo-users")
async def demo_users(request):
    if not getattr(request.app.ctx.settings, "allow_legacy_identity", False):
        raise UnauthorizedError("请先登录")
    return response.json([user_to_dict(user) for user in await User.all().order_by("id")])


@api.get("/me")
async def me(request):
    user = await require_user(await require_user_id(request))
    result = user_to_dict(user)
    if getattr(request.app.ctx, "auth", None) is not None:
        result["email"] = user.email
        result["email_verified"] = bool(user.email_verified_at)
    return response.json(result)


@api.get("/users/search")
async def users_search(request):
    return response.json(await search_users(await require_user_id(request), request.args.get("q", "")))


@api.get("/conversations")
async def conversations(request):
    return response.json(await list_conversations(await require_user_id(request)))


@api.post("/conversations")
async def conversations_create(request):
    user_id = await require_user_id(request)
    body = object_body(request)
    conversation = await get_or_create_conversation(user_id, body.get("user_id"))
    await notify_conversation(conversation["id"])
    return response.json(conversation)


@api.get("/conversations/<conversation_id:int>/messages")
async def messages(request, conversation_id):
    return response.json(await list_messages(
        await require_user_id(request), conversation_id,
        limit=query_integer(request, "limit", 50), before_id=query_integer(request, "before"),
    ))


@api.post("/conversations/<conversation_id:int>/read")
async def conversation_read(request, conversation_id):
    user_id = await require_user_id(request)
    body = object_body(request)
    conversation = await mark_conversation_read(user_id, conversation_id, body.get("last_message_id"))
    await notify_conversation(conversation_id)
    return response.json(conversation)


@api.patch("/conversations/<conversation_id:int>/ttl")
async def conversation_ttl(request, conversation_id):
    user_id = await require_user_id(request)
    body = object_body(request)
    if "ttl_seconds" not in body:
        raise ValidationError("缺少 ttl_seconds")
    conversation = await set_conversation_ttl(user_id, conversation_id, body["ttl_seconds"])
    await request.app.ctx.connections.broadcast(conversation_id, {
        "type": "conversation.updated", "data": {"id": conversation_id, "ttl_seconds": conversation["ttl_seconds"]},
    })
    await notify_conversation(conversation_id)
    return response.json(conversation)


@api.options("/health", name="health_options")
@api.options("/demo-users", name="demo_users_options")
@api.options("/me", name="me_options")
@api.options("/users/search", name="search_options")
@api.options("/conversations", name="conversations_options")
@api.options("/conversations/<conversation_id:int>/messages", name="messages_options")
@api.options("/conversations/<conversation_id:int>/read", name="read_options")
@api.options("/conversations/<conversation_id:int>/ttl", name="ttl_options")
async def preflight(request, conversation_id=None):
    return response.empty()
