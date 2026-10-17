"""Holistic judge (Gemini): scores Relevance, Comprehensibility and Evidence Presentation in one call per article.

The judge only sees the whitelisted fields built by `entrada_do_juiz`. Requests set only the system prompt
and the response JSON schema (model defaults otherwise, no tools). Replies are validated against the schema
and cached; failed calls are retried with exponential backoff.
"""

import json
import time
from pathlib import Path
from typing import Optional

from . import cache as cache_mod
from . import config, prompts, schemas

CAMPOS_PERMITIDOS = ("claim", "claim_date", "claim_context", "evidence", "expected_conclusion", "article")
CAMPOS_EVIDENCIA = ("id", "relation", "date", "source_title", "text")


def entrada_do_juiz(artigo: dict) -> dict:
    """Judge input: the allowed fields only, and only the allowed fields of each evidence unit."""
    entrada = {c: artigo.get(c) for c in CAMPOS_PERMITIDOS}
    entrada["evidence"] = [{c: e.get(c) for c in CAMPOS_EVIDENCIA} for e in artigo["evidence"]]
    art = artigo["article"]
    entrada["article"] = {"title": art.get("title") or "", "lead": art.get("lead") or "",
                          "seccoes": [{"titulo": s.get("titulo") or "", "paragrafos": list(s.get("paragrafos") or [])}
                                      for s in art.get("seccoes") or [] if isinstance(s, dict)]}
    return entrada


def _pedido(user: str) -> dict:
    return {"model": config.HOLISTIC_JUDGE_MODEL, "system": prompts.sistema_holistico(), "user": user,
            "response_schema": schemas.HOLISTIC_OUTPUT_SCHEMA}


def pedido(artigo: dict) -> dict:
    """Model, messages and schema for one article; the cache key hashes all of them."""
    return _pedido(prompts.utilizador_holistico(entrada_do_juiz(artigo)))


def ler_resposta(bruto: str) -> dict:
    """Parse a reply and check it against the schema; raises ValueError if it does not conform."""
    obj = json.loads(bruto)
    problemas = schemas.erros(obj, schemas.HOLISTIC_OUTPUT_SCHEMA)
    if problemas:
        raise ValueError("resposta fora do schema: " + "; ".join(problemas[:3]))
    return obj


# --------------------------------------------------------------------------- client (created lazily)
def _cliente():
    chave_api = config.credencial("gemini")        # credential first, for a clear error if it is missing
    from google import genai
    return genai.Client(api_key=chave_api)


def campos_da_config(p: dict) -> dict:
    """Request config: system prompt and response schema only; sampling and thinking use model defaults."""
    # Automatic function calling is a client-side SDK feature; it is off because no tools are sent.
    return {"system_instruction": p["system"], "response_mime_type": "application/json",
            "response_json_schema": p["response_schema"], "automatic_function_calling": {"disable": True}}


def _config_geracao(p: dict):
    from google.genai import types
    if "response_json_schema" not in getattr(types.GenerateContentConfig, "model_fields", {}):
        # No silent fallback to `response_schema`: it is the SDK's OpenAPI subset, with different semantics.
        raise ImportError("Esta versão do google-genai não tem `response_json_schema`: atualiza o pacote "
                          "(pip install -U google-genai).")
    campos = campos_da_config(p)
    return types.GenerateContentConfig(**{**campos, "automatic_function_calling":
                                          types.AutomaticFunctionCallingConfig(**campos["automatic_function_calling"])})


def preparar_sdk() -> None:
    """Check that google-genai is installed and supports `response_json_schema`; creates no client."""
    try:
        _config_geracao(_pedido(""))
    except ModuleNotFoundError as e:
        raise ImportError("Falta o pacote google-genai (pip install -r requirements.txt).") from e


class JuizHolistico:
    def __init__(self, cache_path: Optional[Path] = None, retries: int = config.HOLISTIC_RETRIES):
        self.cache = cache_mod.CacheJSONL(cache_path)
        self._cli = None
        self.retries = retries
        self.contagem = {"pedidos": 0, "do_cache": 0, "chamadas": 0, "retries": 0, "erros": 0}

    @staticmethod
    def chave(p: dict) -> str:
        return cache_mod.chave(p["model"], {"system": p["system"], "user": p["user"],
                                            "schema": p["response_schema"]})

    def preparar(self) -> None:
        """Create the client up front, so a missing key or SDK fails at once instead of being retried."""
        if self._cli is None:
            preparar_sdk()
            self._cli = _cliente()

    def _chamar_gemini(self, p: dict) -> str:
        r = self._cli.models.generate_content(model=p["model"], contents=p["user"], config=_config_geracao(p))
        return r.text or ""

    def avaliar(self, artigo: dict) -> dict:
        """Score one article, from the cache or from Gemini with retries; raises if every attempt fails."""
        p = pedido(artigo)
        k = self.chave(p)
        self.contagem["pedidos"] += 1
        if k in self.cache:
            self.contagem["do_cache"] += 1
            return self.cache.get(k)
        self.preparar()
        erro = None
        for tentativa in range(1, self.retries + 1):
            try:
                bruto = self._chamar_gemini(p)
                self.contagem["chamadas"] += 1
                self.cache.put(k, {"scores": ler_resposta(bruto)})
                return self.cache.get(k)
            except (config.CredencialEmFalta, ImportError):
                raise                                   # configuration error, not transient
            except Exception as e:                      # 429/503, timeouts, replies outside the schema
                erro = e
                self.contagem["retries"] += 1
                if tentativa < self.retries:
                    time.sleep(min(config.HOLISTIC_BACKOFF_S * 2 ** (tentativa - 1), config.HOLISTIC_MAX_BACKOFF_S))
        self.contagem["erros"] += 1
        raise RuntimeError(f"{artigo['article_id']}: o juiz holístico falhou {self.retries} vezes: {erro}")
