"""Website examples: claim spans already verified, which the page shows without running a model.

Each number of news items per question a run can choose has its own file,
`exemplos<k>.json`: the same claims, each with what a recorded run of the models on it produced
with that number - the questions, how many news items were retrieved and how many of them were
relevant, the relevant ones, and the articles. `corrida.py` turns a picked example into the run the
page shows; a new claim runs the models.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..schemas import TOP_K_OPCOES
from ..settings import get_settings

logger = logging.getLogger(__name__)

PASTA = Path(__file__).parent


def ficheiro(top_k: int) -> Path:
    """The examples recorded with `top_k` news items per question."""
    return PASTA / f"exemplos{top_k}.json"


def _na_lingua(valor: Any, lingua: str) -> Any:
    """An example, or a part of one, with its `_en` fields in place when `lingua` is `'en'`."""
    if isinstance(valor, list):
        return [_na_lingua(elemento, lingua) for elemento in valor]
    if isinstance(valor, dict):
        ingles = lingua == "en"
        return {
            chave: _na_lingua(
                valor[f"{chave}_en"]
                if ingles and valor.get(f"{chave}_en") is not None
                else conteudo,
                lingua,
            )
            for chave, conteudo in valor.items()
            if not chave.endswith("_en")
        }
    return valor


class ExemploStore:
    def __init__(self, por_top_k: dict[int, dict], top_k_omissao: int) -> None:
        self._dados = por_top_k
        self._por_id = {
            top_k: {exemplo["id"]: exemplo for exemplo in dados.get("exemplos", [])}
            for top_k, dados in por_top_k.items()
        }
        self._omissao = top_k_omissao

    def catalogo(self, lingua: str = "pt") -> list[dict]:
        """The examples without the news text, in the order of the default number of news items
        per question. Each carries its verdict for every number it was recorded with."""
        base = self._omissao if self._omissao in self._dados else next(iter(self._dados), None)
        if base is None:
            return []
        ingles = lingua == "en"
        return [
            {
                "id": exemplo["id"],
                "claim": (
                    exemplo["claim_span_en"]
                    if ingles and exemplo.get("claim_span_en") is not None
                    else exemplo["claim_span"]
                ),
                "claim_date": exemplo["data"],
                "context": (
                    exemplo["contexto_en"]
                    if ingles and exemplo.get("contexto_en") is not None
                    else exemplo["contexto"]
                ),
                # Span-level verdict, shown as a colour; never recomputed here or in the browser.
                "veracity": exemplo["veredito"],
                "veredictos": {
                    str(top_k): exemplos[exemplo["id"]]["veredito"]
                    for top_k, exemplos in sorted(self._por_id.items())
                    if exemplo["id"] in exemplos
                },
            }
            for exemplo in self._dados[base].get("exemplos", [])
        ]

    def get(self, identificador: str, top_k: int, lingua: str = "pt") -> dict | None:
        exemplo = self._por_id.get(top_k, {}).get(identificador)
        return None if exemplo is None else _na_lingua(exemplo, lingua)


@lru_cache
def get_exemplos() -> ExemploStore:
    dados = {}
    for top_k in TOP_K_OPCOES:
        caminho = ficheiro(top_k)
        if caminho.exists():
            dados[top_k] = json.loads(caminho.read_text(encoding="utf-8"))
        else:
            logger.warning("sem exemplos com %d notícias por pergunta: falta %s", top_k, caminho.name)
    return ExemploStore(dados, get_settings().top_k_per_question)
