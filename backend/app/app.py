import asyncio
import os
from contextlib import suppress
from uuid import uuid4

from sanic import Sanic, response
from sanic.exceptions import SanicException
from tortoise.exceptions import DBConnectionError, OperationalError
from redis.exceptions import RedisError

from .cleanup import cleanup_loop
from .config import Settings
from .db import close_db, init_db
from .message_store import close_message_store, init_message_store
from .auth import AuthService, SMTPEmailSender
from .auth_api import auth_api
from .errors import AppError
from .http_api import api
from .seed import seed_demo_data
from .websocket import manager, websocket_api


def create_app(settings=None) -> Sanic:
    settings = settings or Settings.from_env()
    app = Sanic(f"single_chat_{uuid4().hex}")
    app.ctx.settings = settings
    app.ctx.connections = manager
    app.config.REQUEST_MAX_SIZE = 64 * 1024
    app.config.WEBSOCKET_MAX_SIZE = 64 * 1024
    app.blueprint(api)
    app.blueprint(auth_api)
    app.blueprint(websocket_api)

    @app.exception(AppError)
    async def app_error(request, error):
        return response.json({"error": {"code": error.code, "message": error.message}}, status=error.status)

    @app.exception(OperationalError, DBConnectionError, OSError)
    async def database_error(request, error):
        return response.json({"error": {"code": "database_unavailable", "message": "数据库暂时不可用，请稍后重试"}}, status=503)

    @app.exception(RedisError, RuntimeError)
    async def redis_error(request, error):
        return response.json({"error": {"code": "redis_unavailable", "message": "消息存储暂时不可用，请稍后重试"}}, status=503)

    @app.exception(SanicException)
    async def request_error(request, error):
        return response.json({"error": {"code": "bad_request" if error.status_code == 400 else "request_error", "message": str(error)}}, status=error.status_code)

    @app.middleware("response")
    async def cors(request, result):
        origin = request.headers.get("Origin")
        if origin in settings.cors_origins:
            result.headers["Access-Control-Allow-Origin"] = origin
            result.headers["Vary"] = "Origin"
            result.headers["Access-Control-Allow-Headers"] = "Content-Type, X-User-Id"
            result.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, OPTIONS"
            result.headers["Access-Control-Allow-Credentials"] = "true"

    @app.before_server_start
    async def startup(app):
        await init_db(settings.database_url, generate_schemas=True)
        store = await init_message_store(settings.redis_url, settings.redis_prefix)
        app.ctx.auth = AuthService(
            store.client,
            secret=settings.auth_secret,
            email_sender=SMTPEmailSender(
                settings.smtp_host,
                settings.smtp_port,
                settings.smtp_from,
                settings.smtp_username,
                settings.smtp_password,
                settings.smtp_starttls,
            ),
            prefix=store.prefix,
            cookie_secure=settings.session_cookie_secure,
            test_mode=settings.auth_test_mode,
        )
        await seed_demo_data()
        app.ctx.cleanup_task = asyncio.create_task(cleanup_loop(app))

    @app.before_server_stop
    async def stop_cleanup(app):
        task = getattr(app.ctx, "cleanup_task", None)
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    @app.after_server_stop
    async def shutdown(app):
        await close_message_store()
        await close_db()

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8001")), debug=application.ctx.settings.debug, single_process=True, auto_reload=False, access_log=False)
