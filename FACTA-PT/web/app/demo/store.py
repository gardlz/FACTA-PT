"""Stored examples: claim spans already verified, which the page shows without running a model.

They are read from `exemplos.json`, an optional local file that is not distributed. Each example
holds the claim, date and context and a recorded run of the models on it.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

EXEMPLOS = Path(__file__).with_name("exemplos.json")


class ExemploStore:
    def __init__(self, dados: dict) -> None:
        self._dados = dados
        # Only an example holding a recorded run can be replayed.
        self._por_id = {
            exemplo["id"]: exemplo
            for exemplo in dados.get("exemplos", [])
            if exemplo.get("eventos")
        }

    def catalogo(self) -> list[dict]:
        """Examples grouped by topic, without the news text."""
        grupos = []
        for topico in self._dados.get("topicos", []):
            fichas = []
            for identificador in topico["exemplos"]:
                exemplo = self._por_id.get(identificador)
                if exemplo is None:
                    continue
                fichas.append(
                    {
                        "id": exemplo["id"],
                        "claim": exemplo["claim"],
                        "claim_date": exemplo["claim_date"],
                        # Span-level verdict, shown as a colour; never recomputed here or in
                        # the browser.
                        "veracity": exemplo["veracity"],
                        "context": exemplo["context"],
                    }
                )
            if fichas:
                grupos.append({"id": topico["id"], "nome": topico["nome"], "exemplos": fichas})
        return grupos

    def get(self, identificador: str) -> dict | None:
        return self._por_id.get(identificador)


@lru_cache
def get_exemplos() -> ExemploStore:
    # Without the examples file the catalogue is empty and only new claims can be verified.
    if not EXEMPLOS.exists():
        return ExemploStore({})
    return ExemploStore(json.loads(EXEMPLOS.read_text(encoding="utf-8")))
