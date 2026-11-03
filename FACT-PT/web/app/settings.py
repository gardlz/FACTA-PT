"""Application configuration, read from the environment."""

import logging
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .schemas import REDATORES, REDATORES_ANTIGOS, TOP_K_OPCOES

logger = logging.getLogger(__name__)


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
    # The article takes minutes on CPU - about an hour for an attempt that runs to 8192 tokens.
    # The inference service is told this, less a margin, and sends back what it has by then.
    article_timeout: float = 10800.0

    # The article writers this deployment offers (keys of REDATORES, comma-separated), the first
    # one the default: those the inference service does not run are left out of the page.
    article_writers: str = ",".join(REDATORES)

    # Distinct news items kept per question, once reissues are merged, when a run does not
    # choose: one of TOP_K_OPCOES, and the choice the page starts on.
    top_k_per_question: int = 5
    # Guard against a runaway generation: each question is one search.
    max_questions: int = 6

    run_retention: int = 64
    # Finished verifications kept for good, each one a page with an address of its own; once
    # there are more, the oldest go. 0: all are kept.
    saved_retention: int = Field(default=0, ge=0)
    # Shared by the website and the worker: in Docker, a volume both mount.
    run_store_dir: str = "/tmp/facta-pt/execucoes"
    # The accounts and the platform settings, and the reviews of the saved verifications. All of
    # them on the data volume, never directly in `run_store_dir` (the run store prunes `*.json`
    # there). By default: beside the runs, and in a `revisoes/` folder inside them.
    utilizadores_file: str = Field(default="", alias="UTILIZADORES_FILE")
    plataforma_file: str = Field(default="", alias="PLATAFORMA_FILE")

    # The queue of runs that use the models (`fila.py`): where it is, how many may wait, and how
    # long one may take, waiting for the models included, before the worker stops it.
    redis_url: str = "redis://redis:6379/0"
    queue_max: int = Field(default=20, ge=1)
    # Runs one session, and one client address, may have waiting or under way at once; 0, no limit.
    # Behind Docker's port publishing every client may show the same address: the address limit
    # is for a site behind a proxy that passes the client's on.
    runs_per_session: int = Field(default=2, ge=0)
    runs_per_address: int = Field(default=0, ge=0)
    run_timeout: float = 14400.0
    # Seconds a run goes on with nobody reading it - the page lost its connection, and reconnects,
    # or was closed - before it is cancelled.
    run_detached_grace: float = 300.0
    cors_origins: str = ""

    # The password gate (see `acesso.py`). The site refuses to start without a hash and a secret,
    # unless the gate is switched off on purpose (local development only).
    # `ADMIN_PASSWORD_HASH` makes the first administrator when there are no accounts yet;
    # `ACCESS_PASSWORD_HASH` (the old shared password) does the same on a deployment that still
    # has only that, and is not accepted for signing in afterwards.
    access_password_hash: str = Field(default="", alias="ACCESS_PASSWORD_HASH")
    admin_username: str = Field(default="admin", alias="ADMIN_USERNAME")
    admin_password_hash: str = Field(default="", alias="ADMIN_PASSWORD_HASH")
    session_secret: str = Field(default="", alias="SESSION_SECRET")
    access_gate_disabled: bool = Field(default=False, alias="ACCESS_GATE_DISABLED")
    session_hours: int = Field(default=12, ge=1, le=24 * 30)
    # False only over plain HTTP on localhost; behind HTTPS the cookie must be Secure.
    cookie_secure: bool = Field(default=True, alias="COOKIE_SECURE")
    # Wrong passwords tolerated per client address, and over all addresses, in `login_window`
    # seconds. Counted per process: with N workers the real ceiling is N times these.
    login_max_failures: int = 5
    login_max_failures_global: int = 40
    login_window: int = 900

    @field_validator("top_k_per_question")
    @classmethod
    def _top_k_previsto(cls, v: int) -> int:
        if v not in TOP_K_OPCOES:
            raise ValueError(
                f"TOP_K_PER_QUESTION must be one of {', '.join(map(str, TOP_K_OPCOES))}"
            )
        return v

    @field_validator("article_writers")
    @classmethod
    def _redatores_previstos(cls, v: str) -> str:
        escolhidos = [r.strip() for r in v.split(",") if r.strip()]
        # A writer no longer offered, left in an older .env, is dropped rather than refused.
        antigos = [r for r in escolhidos if r in REDATORES_ANTIGOS]
        if antigos:
            logger.warning("ARTICLE_WRITERS: %s já não é oferecido e fica de fora", ", ".join(antigos))
            escolhidos = [r for r in escolhidos if r not in REDATORES_ANTIGOS]
        if not escolhidos or any(r not in REDATORES for r in escolhidos):
            raise ValueError(f"ARTICLE_WRITERS must list some of {', '.join(REDATORES)}")
        return ",".join(escolhidos)

    @property
    def redatores(self) -> list[str]:
        """The article writers offered, the default first."""
        return self.article_writers.split(",")

    @property
    def lusa_configured(self) -> bool:
        return bool(self.lusa_api_url and self.lusa_user and self.lusa_password)

    @property
    def pasta_dados(self):
        """Where the site keeps what must outlive a restart: beside the runs' folder."""
        from pathlib import Path

        return Path(self.run_store_dir).parent

    @property
    def utilizadores_path(self):
        from pathlib import Path

        return Path(self.utilizadores_file) if self.utilizadores_file \
            else self.pasta_dados / "utilizadores.json"

    @property
    def plataforma_path(self):
        from pathlib import Path

        return Path(self.plataforma_file) if self.plataforma_file \
            else self.pasta_dados / "plataforma.json"

    @property
    def revisoes_dir(self):
        from pathlib import Path

        return Path(self.run_store_dir) / "revisoes"

    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
