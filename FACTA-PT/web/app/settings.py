"""Application configuration, read from the environment."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "FACTA-PT"

    lusa_api_url: str = Field(default="", alias="API_URL_LUSA")
    lusa_user: str = Field(default="", alias="USER_LUSA")
    lusa_password: str = Field(default="", alias="PASSWORD_LUSA")
    lusa_dataset: str = "LUSA"
    lusa_timeout: float = 120.0
    lusa_login_timeout: float = 60.0
    lusa_retries: int = 4
    lusa_concurrency: int = 4

    inference_url: str = "http://inference:8100"
    inference_timeout: float = 900.0
    # Long because the article is slow on CPU. The inference service gets this deadline, less
    # a margin, and sends back what it has written by then.
    article_timeout: float = 10800.0

    # Distinct news items kept per question, once reissues are merged.
    top_k_per_question: int = 5
    # Cap on the questions used, since each one is a search.
    max_questions: int = 6

    run_retention: int = 64
    run_store_dir: str = "/tmp/facta-pt/execucoes"
    max_concurrent_runs: int = 4
    run_queue_timeout: float = 20.0
    cors_origins: str = ""

    @property
    def lusa_configured(self) -> bool:
        return bool(self.lusa_api_url and self.lusa_user and self.lusa_password)

    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
