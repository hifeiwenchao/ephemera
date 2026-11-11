from backend.app.config import Settings


def test_settings_reads_database_url_and_cleanup_interval(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "mysql://chat:secret@localhost:3306/single_chat")
    monkeypatch.setenv("CLEANUP_INTERVAL_SECONDS", "15")
    settings = Settings.from_env()
    assert settings.database_url.endswith("/single_chat")
    assert settings.cleanup_interval_seconds == 15
