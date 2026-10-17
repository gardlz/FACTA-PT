"""JSONL cache of the judges' decisions, keyed by the sha256 of {model, full input}.

Records are appended and flushed one line at a time, so an interrupted run resumes without asking
for the same decision twice. Also holds the JSONL reader and CSV writer used by the other modules.
"""

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def ler_jsonl(caminho, ignorar_partidas: bool = False) -> List[dict]:
    """Read a JSONL file, skipping blank lines; with `ignorar_partidas`, also skip lines cut off mid-write."""
    saida = []
    for linha in Path(caminho).read_text(encoding="utf-8").splitlines():
        if not linha.strip():
            continue
        try:
            saida.append(json.loads(linha))
        except json.JSONDecodeError:
            if not ignorar_partidas:
                raise
    return saida


def escrever_csv(caminho: Path, linhas: List[dict]) -> None:
    """Write `linhas` to a CSV whose columns are every row key, in first-seen order."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(dict.fromkeys(k for l in linhas for k in l)))
        w.writeheader()
        w.writerows(linhas)


def chave(modelo: str, entrada: Any) -> str:
    corpo = json.dumps({"modelo": modelo, "entrada": entrada}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(corpo.encode("utf-8")).hexdigest()


class CacheJSONL:
    def __init__(self, caminho: Optional[Path]):
        self.caminho = Path(caminho) if caminho else None
        self.dados: Dict[str, dict] = {}
        if self.caminho and self.caminho.exists():
            for registo in ler_jsonl(self.caminho, ignorar_partidas=True):
                self.dados[registo["chave"]] = registo      # a repeated key keeps its last record

    def __contains__(self, k: str) -> bool:
        return k in self.dados

    def get(self, k: str) -> Optional[dict]:
        return self.dados.get(k)

    def put(self, k: str, registo: dict) -> None:
        registo = {"chave": k, **registo}
        self.dados[k] = registo
        if self.caminho:
            self.caminho.parent.mkdir(parents=True, exist_ok=True)
            with self.caminho.open("a", encoding="utf-8") as f:
                f.write(json.dumps(registo, ensure_ascii=False) + "\n")
                f.flush()
