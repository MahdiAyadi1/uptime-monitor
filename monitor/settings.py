from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = (
        "postgresql+psycopg://uptime_monitor:change-me@localhost:5432/uptime_monitor"
    )
    api_key: str = "dev-api-key"
    alert_webhook_url: str = ""
    failure_threshold: int = 3
    max_concurrent_probes: int = 20
    due_tolerance_seconds: int = 5
    max_redirects: int = 0
    response_bytes_limit: int = 1_048_576
    retention_days: int = 90
    probe_user_agent: str = "uptime-monitor-portfolio/1.0"
    log_level: str = "INFO"
