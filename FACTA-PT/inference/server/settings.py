"""Inference service configuration."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Base decoder (local path or Hugging Face id) and the QLoRA adapter trained on it.
    qg_model_path: str = ""
    qg_adapter_path: str = ""

    # Decides whether a LUSA news item has anything to do with the claim.
    relevance_model_path: str = ""
    relevance_batch_size: int = 8

    # Decides the relation between a three-sentence passage and the claim.
    stance_model_path: str = ""
    stance_batch_size: int = 16

    # cuda or cpu; auto takes CUDA when it is available.
    device: str = "auto"

    # Writes the fact-checking article: a Hugging Face id, downloaded once into the cache
    # volume, or a local path; and the revision that was evaluated.
    article_model_path: str = ""
    article_model_revision: str = ""
    # cuda or cpu. auto: CUDA when the GPU can hold the model with the other three moved out to
    # main memory (the four take turns on it, `gpu.py`), else the CPU, in the same precision.
    article_device: str = "auto"
    # Tokens the article's prompt may take; the passages worth least leave until it fits
    # (`artigo/admissao.py`). Reading 16k tokens takes about 0.8 GB, growing with the prompt's
    # length on the GPU (read in pieces) and with its square on the CPU, where it takes minutes.
    article_max_prompt_tokens: int = 16384


@lru_cache
def get_settings() -> Settings:
    return Settings()
