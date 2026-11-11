import asyncio
from types import SimpleNamespace

import fakeredis.aioredis
import pytest
import pytest_asyncio

from backend.app.errors import UnauthorizedError, ValidationError
from backend.app.models import User


@pytest_asyncio.fixture
async def auth_env(db):
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    mailbox = []

    async def email_sender(email, purpose, code):
        mailbox.append({"email": email, "purpose": purpose, "code": code})

    yield SimpleNamespace(client=client, mailbox=mailbox, sender=email_sender)
    await client.aclose()


def make_service(env, **kwargs):
    from backend.app.auth import AuthService

    sender = kwargs.pop("email_sender", env.sender)
    return AuthService(
        env.client, secret="test-secret-with-at-least-32-characters", email_sender=sender,
        prefix="auth-tests:", **kwargs,
    )


async def register_user(service, env, username="New_User", email="new@example.com"):
    await service.request_email_code(email, "register", ip="127.0.0.1")
    code = env.mailbox[-1]["code"]
    return await service.register(
        username=username, password="correct-password", email=email, code=code,
        display_name="新朋友", ip="127.0.0.1",
    )


async def test_registration_requires_email_verification(auth_env):
    service = make_service(auth_env)
    with pytest.raises(UnauthorizedError):
        await service.register(
            username="new_user", password="correct-password", email="new@example.com", code="123456",
        )
    assert await User.all().count() == 0


async def test_registration_normalizes_email_and_reserves_case_insensitive_names(auth_env):
    service = make_service(auth_env)
    user = await register_user(service, auth_env, email="New@Example.COM")
    assert user.email == "new@example.com" and user.email_verified_at is not None
    assert user.username == "New_User" and user.username_lower == "new_user"
    assert user.password_hash and "correct-password" not in user.password_hash
    await service.request_email_code("other@example.com", "register", ip="127.0.0.2")
    with pytest.raises(ValidationError):
        await service.register(
            username="NEW_USER", password="another-password", email="other@example.com",
            code=auth_env.mailbox[-1]["code"],
        )
    with pytest.raises(UnauthorizedError):
        await service.register(
            username="other_user", password="another-password", email="NEW@example.com", code="000000",
        )
    assert await User.all().count() == 1


@pytest.mark.parametrize("fields", [
    {"username": "ab"}, {"username": "user-name"}, {"username": "中文用户"}, {"username": "a" * 33},
    {"password": "short"}, {"password": "a" * 129}, {"password": 12345678},
    {"display_name": "a" * 81}, {"email": "invalid"}, {"email": ""}, {"code": "１２３４５６"},
])
async def test_registration_validates_identity_fields_before_creating_user(auth_env, fields):
    service = make_service(auth_env)
    data = dict(username="new_user", password="correct-password", email="new@example.com", code="123456")
    data.update(fields)
    with pytest.raises(ValidationError):
        await service.register(**data)
    assert await User.all().count() == 0


async def test_code_is_single_use_and_wrong_attempts_expire_it(auth_env):
    service = make_service(auth_env)
    await service.request_email_code("new@example.com", "register", ip="1.1.1.1")
    for _ in range(5):
        with pytest.raises(UnauthorizedError):
            await service.register(
                username="new_user", password="correct-password", email="new@example.com", code="000000",
            )
    with pytest.raises(UnauthorizedError):
        await service.register(
            username="new_user", password="correct-password", email="new@example.com",
            code=auth_env.mailbox[-1]["code"],
        )


async def test_expired_code_and_replayed_code_are_rejected(auth_env):
    service = make_service(auth_env)
    await service.request_email_code("new@example.com", "register", ip="1.1.1.1")
    key = service._key("otp:register:new@example.com")
    await auth_env.client.expire(key, 1)
    await auth_env.client.expire(service._key("resend:register:new@example.com"), 1)
    await asyncio.sleep(1.05)
    with pytest.raises(UnauthorizedError):
        await service.register(
            username="new_user", password="correct-password", email="new@example.com",
            code=auth_env.mailbox[-1]["code"],
        )
    await service.request_email_code("new@example.com", "register", ip="1.1.1.1")
    await service.register(
        username="new_user", password="correct-password", email="new@example.com",
        code=auth_env.mailbox[-1]["code"],
    )
    with pytest.raises(UnauthorizedError):
        await service.register(
            username="second_user", password="correct-password", email="new@example.com",
            code=auth_env.mailbox[-1]["code"],
        )


async def test_password_login_and_cookie_session_round_trip(auth_env):
    service = make_service(auth_env)
    user = await register_user(service, auth_env)
    assert await service.login_password("NEW_USER", "correct-password", ip="127.0.0.1") == user
    assert await service.login_password("NEW@example.COM", "correct-password", ip="127.0.0.1") == user
    with pytest.raises(UnauthorizedError):
        await service.login_password("new_user", "wrong-password", ip="127.0.0.1")
    token = await service.create_session(user)
    request = SimpleNamespace(cookies={service.cookie_name: token})
    assert await service.authenticate_request(request) == user
    await service.logout(request)
    with pytest.raises(UnauthorizedError):
        await service.authenticate_request(request)


async def test_verified_email_code_login_and_unknown_email_response_are_safe(auth_env):
    service = make_service(auth_env)
    await register_user(service, auth_env)
    result = await service.request_email_code("NEW@example.com", "login", ip="127.0.0.1")
    assert result == {"message": "如果邮箱已注册，验证码将发送到邮箱", "retry_after": 60}
    assert await service.login_email("new@example.com", auth_env.mailbox[-1]["code"])
    result = await service.request_email_code("unknown@example.com", "login", ip="127.0.0.1")
    assert result == {"message": "如果邮箱已注册，验证码将发送到邮箱", "retry_after": 60}
    assert auth_env.mailbox[-1]["email"] == "new@example.com"


async def test_email_sender_failure_does_not_leave_otp(auth_env):
    async def failing_sender(email, purpose, code):
        raise OSError("mailbox unavailable")

    service = make_service(auth_env, email_sender=failing_sender)
    with pytest.raises(OSError):
        await service.request_email_code("new@example.com", "register", ip="1.1.1.1")
    assert await auth_env.client.keys("auth-tests:auth:otp:*") == []
