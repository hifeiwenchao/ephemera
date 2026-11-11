"""Password, email-code, and cookie-session authentication services."""

import asyncio
import base64
import hashlib
import hmac
import os
import re
import secrets
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Awaitable, Callable

from redis.exceptions import WatchError
from tortoise.exceptions import IntegrityError
from tortoise.expressions import Q

from .errors import UnauthorizedError, ValidationError
from .models import User

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,32}$")
CODE_RE = re.compile(r"^[0-9]{6}$")
SESSION_TTL = 7 * 24 * 60 * 60
OTP_TTL = 5 * 60
RESEND_TTL = 60
MAX_OTP_ATTEMPTS = 5


async def _derive_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)

    def derive():
        digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
        return digest

    digest = await asyncio.to_thread(derive)
    return "scrypt$16384$8$1${}${}".format(
        base64.urlsafe_b64encode(salt).decode().rstrip("="),
        base64.urlsafe_b64encode(digest).decode().rstrip("="),
    )


async def _check_password(password: str, encoded: str | None) -> bool:
    if not encoded or not encoded.startswith("scrypt$"):
        return False
    try:
        _, n, r, p, salt_text, digest_text = encoded.split("$", 5)
        padding = "=" * (-len(salt_text) % 4)
        salt = base64.urlsafe_b64decode((salt_text + padding).encode())
        expected = base64.urlsafe_b64decode((digest_text + "=" * (-len(digest_text) % 4)).encode())
        actual_encoded = await _derive_password(password, salt)
        actual = base64.urlsafe_b64decode((actual_encoded.rsplit("$", 1)[1] + "=" * (-len(actual_encoded.rsplit("$", 1)[1]) % 4)).encode())
        return hmac.compare_digest(actual, expected) and n == "16384" and r == "8" and p == "1"
    except (ValueError, TypeError):
        return False


def normalize_email(email: str) -> str:
    if not isinstance(email, str):
        raise ValidationError("邮箱格式不正确")
    value = email.strip().lower()
    if len(value) > 254 or not EMAIL_RE.fullmatch(value):
        raise ValidationError("邮箱格式不正确")
    return value


def validate_registration(username, password, display_name, email, code):
    if not isinstance(username, str) or not USERNAME_RE.fullmatch(username):
        raise ValidationError("用户名必须是 3–32 位 ASCII 字母、数字或下划线")
    if not isinstance(password, str) or not 8 <= len(password) <= 128:
        raise ValidationError("密码长度必须为 8–128 个字符")
    if display_name is not None and (not isinstance(display_name, str) or len(display_name) > 80):
        raise ValidationError("显示名称最多 80 个字符")
    if not isinstance(code, str) or not CODE_RE.fullmatch(code):
        raise ValidationError("验证码必须是 6 位数字")
    return normalize_email(email)


class SMTPEmailSender:
    def __init__(self, host: str, port: int, from_address: str, username: str = "", password: str = "", starttls: bool = False):
        self.host, self.port, self.from_address = host, int(port), from_address
        self.username, self.password, self.starttls = username, password, starttls

    def _send(self, to_email: str, purpose: str, code: str):
        message = EmailMessage()
        message["Subject"] = "Ephemera 验证码"
        message["From"] = self.from_address
        message["To"] = to_email
        message.set_content(f"你的 Ephemera{('注册' if purpose == 'register' else '登录')}验证码是：{code}\n验证码 5 分钟内有效。")
        with smtplib.SMTP(self.host, self.port, timeout=10) as smtp:
            if self.starttls:
                smtp.starttls()
            if self.username:
                smtp.login(self.username, self.password)
            smtp.send_message(message)

    async def __call__(self, to_email: str, purpose: str, code: str):
        await asyncio.to_thread(self._send, to_email, purpose, code)


class AuthService:
    def __init__(self, client, *, secret: str, email_sender: Callable[[str, str, str], Awaitable[None]], prefix: str = "whisper:", cookie_name: str = "whisper_session", cookie_secure: bool = False):
        if not secret or len(secret) < 32:
            raise ValueError("auth secret must be at least 32 characters")
        self.client = client
        self.secret = secret.encode()
        self.email_sender = email_sender
        self.prefix = prefix if prefix.endswith(":") else prefix + ":"
        self.cookie_name = cookie_name
        self.cookie_secure = cookie_secure

    def _key(self, suffix: str) -> str:
        return f"{self.prefix}auth:{suffix}"

    def _digest(self, value: str) -> str:
        return hmac.new(self.secret, value.encode(), hashlib.sha256).hexdigest()

    async def _limited(self, key: str, limit: int, ttl: int) -> bool:
        count = await self.client.incr(key)
        if count == 1:
            await self.client.expire(key, ttl)
        return count <= limit

    async def request_email_code(self, email: str, purpose: str, *, ip: str = "") -> dict:
        email = normalize_email(email)
        if purpose not in {"register", "login"}:
            raise ValidationError("验证码用途不正确")
        if not await self._limited(self._key(f"email-rate:{email}"), 5, 3600):
            raise ValidationError("验证码请求过于频繁，请稍后重试")
        if ip and not await self._limited(self._key(f"ip-rate:{ip}"), 30, 3600):
            raise ValidationError("请求过于频繁，请稍后重试")
        cooldown = self._key(f"resend:{purpose}:{email}")
        existing = await User.get_or_none(email=email)
        if purpose == "register" and existing:
            raise ValidationError("邮箱已注册")
        if purpose == "login" and (not existing or not existing.email_verified_at):
            return {"message": "如果邮箱已注册，验证码将发送到邮箱", "retry_after": RESEND_TTL}
        if not await self.client.set(cooldown, "1", ex=RESEND_TTL, nx=True):
            raise ValidationError("请稍后再获取验证码")
        code = f"{secrets.randbelow(1_000_000):06d}"
        code_key = self._key(f"otp:{purpose}:{email}")
        await self.client.set(code_key, self._digest(code), ex=OTP_TTL)
        try:
            await self.email_sender(email, purpose, code)
        except Exception:
            await self.client.delete(code_key, cooldown)
            raise
        if purpose == "login":
            return {"message": "如果邮箱已注册，验证码将发送到邮箱", "retry_after": RESEND_TTL}
        return {"message": "验证码已发送", "retry_after": RESEND_TTL}

    async def _consume_code(self, email: str, purpose: str, code: str):
        key = self._key(f"otp:{purpose}:{email}")
        attempts_key = self._key(f"otp-attempts:{purpose}:{email}")
        expected_digest = self._digest(code)
        while True:
            pipe = self.client.pipeline()
            try:
                await pipe.watch(key, attempts_key)
                expected = await pipe.get(key)
                if not expected:
                    await pipe.reset()
                    raise UnauthorizedError("验证码无效或已过期")
                if isinstance(expected, bytes):
                    expected = expected.decode("ascii", "ignore")
                if not hmac.compare_digest(str(expected), expected_digest):
                    attempts = int(await pipe.get(attempts_key) or 0) + 1
                    pipe.multi()
                    pipe.set(attempts_key, attempts, ex=OTP_TTL)
                    if attempts >= MAX_OTP_ATTEMPTS:
                        pipe.delete(key, attempts_key)
                    await pipe.execute()
                    raise UnauthorizedError("验证码无效或已过期")
                pipe.multi()
                pipe.delete(key, attempts_key)
                await pipe.execute()
                return
            except WatchError:
                continue
            finally:
                await pipe.reset()

    async def register(self, *, username, password, email, code, display_name=None, ip: str = "") -> User:
        email = validate_registration(username, password, display_name, email, code)
        await self._consume_code(email, "register", code)
        if await User.get_or_none(username_lower=username.lower()):
            raise ValidationError("用户名已存在")
        if await User.get_or_none(email=email):
            raise ValidationError("邮箱已注册")
        password_hash = await _derive_password(password)
        try:
            return await User.create(username=username, display_name=display_name or username, email=email, email_verified_at=datetime.now(timezone.utc), password_hash=password_hash)
        except IntegrityError as exc:
            raise ValidationError("用户名或邮箱已存在") from exc

    async def login_password(self, username: str, password: str, *, ip: str = "") -> User:
        if not isinstance(username, str) or not isinstance(password, str):
            raise UnauthorizedError("用户名或密码错误")
        identifier = username.strip().lower()
        if ip and not await self._limited(self._key(f"login:{ip}:{identifier}"), 10, 300):
            raise UnauthorizedError("登录尝试过于频繁，请稍后重试")
        user = await User.filter(Q(username_lower=identifier) | Q(email=identifier)).first()
        if not user or not user.email_verified_at or not await _check_password(password, user.password_hash):
            raise UnauthorizedError("用户名或密码错误")
        return user

    async def login_email(self, email: str, code: str) -> User:
        email = normalize_email(email)
        if not isinstance(code, str) or not CODE_RE.fullmatch(code):
            raise UnauthorizedError("验证码无效或已过期")
        await self._consume_code(email, "login", code)
        user = await User.get_or_none(email=email, email_verified_at__isnull=False)
        if not user:
            raise UnauthorizedError("验证码无效或已过期")
        return user

    async def create_session(self, user: User) -> str:
        token = secrets.token_urlsafe(32)
        await self.client.set(self._key(f"session:{self._digest(token)}"), str(user.id), ex=SESSION_TTL)
        return token

    async def authenticate_request(self, request) -> User:
        token = request.cookies.get(self.cookie_name)
        if not token or len(token) > 256:
            raise UnauthorizedError("请先登录")
        user_id = await self.client.get(self._key(f"session:{self._digest(token)}"))
        if not user_id:
            raise UnauthorizedError("请先登录")
        user = await User.get_or_none(id=int(user_id))
        if not user or not user.email_verified_at or not user.password_hash:
            raise UnauthorizedError("请先登录")
        return user

    async def logout(self, request):
        token = request.cookies.get(self.cookie_name)
        if token:
            await self.client.delete(self._key(f"session:{self._digest(token)}"))

    def set_cookie(self, result, token: str):
        result.add_cookie(self.cookie_name, token, path="/", secure=self.cookie_secure, httponly=True, samesite="Lax", max_age=SESSION_TTL)


async def authenticate_request(request) -> User:
    """Authenticate using only the HttpOnly cookie configured on the app."""
    return await request.app.ctx.auth.authenticate_request(request)
