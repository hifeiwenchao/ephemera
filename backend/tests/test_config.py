from backend.app.config import Settings


def test_settings_reads_database_url_and_cleanup_interval(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "mysql://chat:secret@localhost:3306/single_chat")
    monkeypatch.setenv("CLEANUP_INTERVAL_SECONDS", "15")
    settings = Settings.from_env()
    assert settings.database_url.endswith("/single_chat")
    assert settings.cleanup_interval_seconds == 15


def test_settings_reads_auth_test_mode(monkeypatch):
    monkeypatch.setenv("AUTH_TEST_MODE", "true")
    assert Settings.from_env().auth_test_mode is True


def test_settings_reads_redis_connection_and_namespace(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/4")
    monkeypatch.setenv("REDIS_PREFIX", "whisper:isolated:")
    settings = Settings.from_env()
    assert settings.redis_url == "redis://localhost:6379/4"
    assert settings.redis_prefix == "whisper:isolated:"
