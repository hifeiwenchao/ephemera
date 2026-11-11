from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    database_url: str
    debug: bool
    cleanup_interval_seconds: int
    cors_origins: list[str]
    redis_url: str = "redis://127.0.0.1:6379/0"
    redis_prefix: str = "whisper:"
    auth_secret: str = "development-auth-secret-change-me-32-chars"
    session_cookie_secure: bool = False
    smtp_host: str = "127.0.0.1"
    smtp_port: int = 1025
    smtp_from: str = "no-reply@local.test"
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = False
    allow_legacy_identity: bool = False
    auth_test_mode: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
        cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173")
        return cls(
            database_url=os.getenv(
                "DATABASE_URL",
                "mysql://root@127.0.0.1:3306/single_chat",
            ),
            debug=os.getenv("DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"},
            cleanup_interval_seconds=int(os.getenv("CLEANUP_INTERVAL_SECONDS", "60")),
            cors_origins=[origin.strip() for origin in cors_origins.split(",") if origin.strip()],
            redis_url=os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"),
            redis_prefix=os.getenv("REDIS_PREFIX", "whisper:"),
            auth_secret=os.getenv("AUTH_SECRET", "development-auth-secret-change-me-32-chars"),
            session_cookie_secure=os.getenv("SESSION_COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"},
            smtp_host=os.getenv("SMTP_HOST", "127.0.0.1"),
            smtp_port=int(os.getenv("SMTP_PORT", "1025")),
            smtp_from=os.getenv("SMTP_FROM", "no-reply@local.test"),
            smtp_username=os.getenv("SMTP_USERNAME", ""),
            smtp_password=os.getenv("SMTP_PASSWORD", ""),
            smtp_starttls=os.getenv("SMTP_STARTTLS", "false").strip().lower() in {"1", "true", "yes", "on"},
            allow_legacy_identity=os.getenv("ALLOW_LEGACY_IDENTITY", "false").strip().lower() in {"1", "true", "yes", "on"},
            auth_test_mode=os.getenv("AUTH_TEST_MODE", "false").strip().lower() in {"1", "true", "yes", "on"},
        )
