"""Stored examples: claim spans already verified, which the page shows without running a model.

Each number of news items per question a run can choose has its own optional local file,
`exemplos<k>.json`, which is not distributed: the same claims, each with what a recorded run of
the models on it produced with that number (the questions, how many news items were retrieved and
how many of them were relevant, the relevant ones, and the article of each writer). `corrida.py`
turns a picked example into the run the page shows. Without the files the catalogue is empty and
only new claims can be verified.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ..schemas import TOP_K_OPCOES
from ..settings import get_settings

PASTA = Path(__file__).parent


def ficheiro(top_k: int) -> Path:
    """The examples recorded with `top_k` news items per question."""
    return PASTA / f"exemplos{top_k}.json"


class ExemploStore:
    def __init__(self, por_top_k: dict[int, dict], top_k_omissao: int) -> None:
        self._dados = por_top_k
        self._por_id = {
            top_k: {exemplo["id"]: exemplo for exemplo in dados.get("exemplos", [])}
            for top_k, dados in por_top_k.items()
        }
        self._omissao = top_k_omissao

    def catalogo(self) -> list[dict]:
        """The examples without the news text, in the order of the file of the default number of
        news items per question. Each carries its verdict for every number it was recorded with."""
        base = self._omissao if self._omissao in self._dados else next(iter(self._dados), None)
        if base is None:
            return []
        return [
            {
                "id": exemplo["id"],
                "claim": exemplo["claim_span"],
                "claim_date": exemplo["data"],
                "context": exemplo["contexto"],
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

    def get(self, identificador: str, top_k: int) -> dict | None:
        return self._por_id.get(top_k, {}).get(identificador)


@lru_cache
def get_exemplos() -> ExemploStore:
    dados = {
        top_k: json.loads(ficheiro(top_k).read_text(encoding="utf-8"))
        for top_k in TOP_K_OPCOES
        if ficheiro(top_k).exists()
    }
    return ExemploStore(dados, get_settings().top_k_per_question)
