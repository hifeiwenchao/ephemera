from sanic import Blueprint, response

from .errors import ValidationError
from .schemas import user_to_dict

auth_api = Blueprint("auth_api", url_prefix="/api/auth")


def _body(request):
    body = request.json
    if not isinstance(body, dict):
        raise ValidationError("请求体必须是 JSON 对象")
    return body


def _ip(request):
    return getattr(request, "remote_addr", None) or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()


def _auth_user(user):
    result = user_to_dict(user)
    result["email"] = user.email
    result["email_verified"] = bool(user.email_verified_at)
    return result


@auth_api.post("/email-code")
async def email_code(request):
    body = _body(request)
    result = await request.app.ctx.auth.request_email_code(body.get("email"), body.get("purpose"), ip=_ip(request))
    return response.json(result)


@auth_api.post("/register")
async def register(request):
    body = _body(request)
    service = request.app.ctx.auth
    user = await service.register(
        username=body.get("username"), display_name=body.get("display_name"),
        password=body.get("password"), email=body.get("email"), code=body.get("code"), ip=_ip(request),
    )
    token = await service.create_session(user)
    result = response.json({"user": _auth_user(user)})
    service.set_cookie(result, token)
    return result


@auth_api.post("/login/password")
async def login_password(request):
    body = _body(request)
    service = request.app.ctx.auth
    user = await service.login_password(body.get("username"), body.get("password"), ip=_ip(request))
    token = await service.create_session(user)
    result = response.json({"user": _auth_user(user)})
    service.set_cookie(result, token)
    return result


@auth_api.post("/login/email")
async def login_email(request):
    body = _body(request)
    service = request.app.ctx.auth
    user = await service.login_email(body.get("email"), body.get("code"))
    token = await service.create_session(user)
    result = response.json({"user": _auth_user(user)})
    service.set_cookie(result, token)
    return result


@auth_api.post("/logout")
async def logout(request):
    service = request.app.ctx.auth
    await service.logout(request)
    result = response.json({})
    result.delete_cookie(service.cookie_name, path="/")
    return result


@auth_api.options("/email-code", name="auth_email_code_options")
@auth_api.options("/register", name="auth_register_options")
@auth_api.options("/login/password", name="auth_password_options")
@auth_api.options("/login/email", name="auth_email_options")
@auth_api.options("/logout", name="auth_logout_options")
async def auth_preflight(request):
    return response.empty()
