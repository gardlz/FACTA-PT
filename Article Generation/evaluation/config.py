"""Configuration for the automatic evaluation of the generated articles.

Paths, the two judges (NLI citation judge and holistic Gemini judge) and, for each service, the name
of the `.env` variable that holds its credential. Credential values are never printed or logged.
"""

import os
from pathlib import Path
from typing import Dict, Optional

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent                          # this stage's folder
ENV_FILE = RAIZ / ".env"
SAIDAS = AQUI / "outputs"

# ----------------------------------------------------------------------------- credentials
# Name of the .env variable that holds each service's credential (not the value).
CREDENCIAIS: Dict[str, str] = {
    "gemini": "GEMINI38_FLASH_KEY",
}


class CredencialEmFalta(RuntimeError):
    """A service's credential is set neither in .env nor in the environment."""


def _valor_da_variavel(nome: str) -> Optional[str]:
    """Read one variable from .env without exporting the file to os.environ; fall back to os.environ."""
    try:
        from dotenv import dotenv_values
        valor = dotenv_values(ENV_FILE).get(nome) if ENV_FILE.exists() else None
    except ImportError:
        valor = None
    return valor or os.environ.get(nome)


def credencial(servico: str) -> str:
    """Return the credential for `servico`, failing with a clear message that never shows the value."""
    nome = CREDENCIAIS[servico]
    valor = _valor_da_variavel(nome)
    if not valor:
        raise CredencialEmFalta(f"A variável «{nome}» (serviço «{servico}») não existe em "
                                f"{ENV_FILE} nem no ambiente.")
    return valor


# ----------------------------------------------------------------------------- judges
# Citation support judge: a binary NLI classifier (entailment / not_entailment), used without a prompt
# and pinned to a revision.
CITATION_SUPPORT_JUDGE: Dict[str, str] = {
    "model_id": "MoritzLaurer/bge-m3-zeroshot-v2.0",
    "revision": "9abf1c8aaeb82a2447809c20753ed0b106b76652",
}

CITATION_JUDGE_BATCH = 16
# Fallback token limit, used only until the checkpoint is loaded; the real one comes from the model
# config (`citation_judge.limite_real`).
NLI_MAX_LENGTH = 8192

# Holistic judge: scores Relevance, Comprehensibility and Evidence Presentation in one call per article,
# with the model's default generation settings and no tools.
HOLISTIC_JUDGE_MODEL = "gemini-3.8-flash"
HOLISTIC_RETRIES = 5
HOLISTIC_BACKOFF_S = 2.0
HOLISTIC_MAX_BACKOFF_S = 60.0

# ----------------------------------------------------------------------------- data
# Generated articles and their plans (with the evidence units given to the Writer).
# An article id is "<condition>/<model>/<span>".
DADOS = RAIZ / "dados"
ARTIGOS = DADOS / "artigos"                 # <condition>/<model>/<span>.json
PLANOS = DADOS / "planos"                   # <condition>/<span>.json
