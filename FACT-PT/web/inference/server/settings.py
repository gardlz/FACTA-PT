"""Inference service configuration."""

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # An empty variable is one left unset: docker-compose.yml passes every one, set or not.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore",
                                      env_ignore_empty=True)

    # Each checkpoint is a local path or a Hugging Face id (downloaded once into the cache
    # volume), with the revision to take from the hub; empty, the latest.

    # The question generator - AMALIA with the QLoRA adapter trained on it - answers behind an
    # OpenAI-compatible API: its address, with or without `/v1`, the name it serves the model
    # under, and the API's key, when it asks for one. With `modal_api_url`, Modal's gateway.
    qg_api_url: str = ""
    qg_api_model: str = ""
    qg_api_key: str = ""
    # Base decoder and adapter, of which only the tokenizer and the adapter's checkpoint_info.json
    # are read: the prompt is built and fitted with them. An empty base revision
    # takes the one the adapter records in its checkpoint_info.json, when the base is the model it
    # names.
    qg_model_path: str = ""
    qg_model_revision: str = ""
    qg_adapter_path: str = ""
    qg_adapter_revision: str = ""

    # Decides whether a LUSA news item has anything to do with the claim.
    relevance_model_path: str = ""
    relevance_model_revision: str = ""
    relevance_batch_size: int = 8

    # Decides the relation between a three-sentence passage and the claim.
    stance_model_path: str = ""
    stance_model_revision: str = ""
    stance_batch_size: int = 16

    # cuda, mps or cpu; auto takes the first one available.
    device: str = "auto"
    # Whether the GPU driver lends system memory when the GPU's own runs out (Windows, WSL, Docker
    # Desktop): models larger than the card then run on it, the rest over the bus. Unset, guessed
    # from the kernel (`gpu.driver_empresta`).
    gpu_lends_memory: bool | None = None
    # Seconds a model may sit on the GPU unused before it leaves it for main memory, so that a card
    # that holds every model does not keep them there when nobody is verifying anything. The next
    # call brings it back in seconds. 0 keeps them where they are until another model needs the room.
    gpu_idle_ttl_s: float = Field(default=600.0, ge=0)
    # Seconds a model may sit unused before it is let go of main memory as well, and the memory
    # goes back to the machine. The next call loads the classifier again from disk, in seconds, so
    # this is longer than the GPU's. Without a GPU it is the only one. 0 keeps them loaded.
    ram_idle_ttl_s: float = Field(default=1800.0, ge=0)

    # The article writers, each behind an OpenAI-compatible API (`artigo/redator_api.py`).
    # Gemma, on OpenRouter: its address, the model's name there (a `:free` variant takes only some
    # of the article's parameters: `artigo/redator_api.py`), the account's key, and the checkpoint
    # whose tokenizer counts the prompt (only its tokenizer files are read).
    article_api_url: str = "https://openrouter.ai/api/v1"
    article_api_model: str = "google/gemma-4-31b-it"
    article_api_key: str = ""
    article_api_tokenizer: str = "google/gemma-4-31b-it"
    # AMALIA-9B-0626-DPO, prompted as Gemma is, behind an OpenAI-compatible API: its address, with
    # or without `/v1`, the model's name there, and the API's key, when it asks for one. With
    # `modal_api_url`, Modal's gateway.
    amalia_api_url: str = ""
    amalia_api_model: str = ""
    amalia_api_key: str = ""
    # The two AMALIA models on Modal, behind one gateway (MODELS.md): its address and its key. Set,
    # the question generator answers at `<address>/facta`, as `amalia-facta`, and the writer at
    # `<address>/base`, as `amalia-base`, whatever the two models' own variables say.
    modal_api_url: str = ""
    modal_api_key: str = ""
    # Seconds the gateway's GPU stays on after its last request (its `scaledown_window`): the
    # models there are shown as ready for that long after this service last heard from it.
    modal_gpu_idle_s: float = Field(default=60.0, ge=0)
    # Seconds a request to any API may take; an article's, at most what its deadline leaves.
    api_timeout_s: float = 3600.0
    # Tokens the article's prompt may take, at most what the model's window leaves for the article;
    # the passages worth least to the article are left out until it fits (`artigo/admissao.py`).
    article_max_prompt_tokens: int = 16384

    @model_validator(mode="after")
    def _no_modal(self) -> "Settings":
        """With Modal's gateway set, the two AMALIA models answer there."""
        base = self.modal_api_url.rstrip("/")
        if base:
            self.qg_api_url, self.qg_api_model = f"{base}/facta", "amalia-facta"
            self.amalia_api_url, self.amalia_api_model = f"{base}/base", "amalia-base"
            self.qg_api_key = self.amalia_api_key = self.modal_api_key
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
