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

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
        cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173")
        return cls(
            database_url=os.getenv(
                "DATABASE_URL",
                "mysql://chat:chat_password@127.0.0.1:3307/single_chat",
            ),
            debug=os.getenv("DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"},
            cleanup_interval_seconds=int(os.getenv("CLEANUP_INTERVAL_SECONDS", "60")),
            cors_origins=[origin.strip() for origin in cors_origins.split(",") if origin.strip()],
        )
