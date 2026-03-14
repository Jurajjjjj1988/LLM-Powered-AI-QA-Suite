import re
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_API_KEY_RE = re.compile(r"^sk-ant-api\d{2}-[A-Za-z0-9_\-]{90,}$")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Anthropic
    anthropic_api_key: str
    claude_model: str = "claude-opus-4-6"
    claude_max_tokens: int = 4096
    claude_timeout_seconds: int = 60

    # Retry
    retry_max_attempts: int = 3
    retry_wait_min_seconds: float = 1.0
    retry_wait_max_seconds: float = 10.0

    # Database
    db_path: Path = Path("~/ai-qa-projects/qa_suite.db").expanduser()

    # Generator
    generator_default_framework: str = "playwright"
    generator_output_dir: Path = Path("./generated")

    # Analyzer
    analyzer_flaky_threshold_percent: float = 20.0

    # Dashboard
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 8000

    # Logging
    log_level: str = "INFO"
    log_json: bool = True

    @field_validator("anthropic_api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        if not _API_KEY_RE.match(v):
            raise ValueError(
                "ANTHROPIC_API_KEY must match pattern sk-ant-api##-<90+ chars>"
            )
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
