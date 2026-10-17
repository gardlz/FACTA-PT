"""Readers for configs/protocolo.yaml, configs/modelos.yaml and the cross-validation folds.

One place, so that every script reads the same configuration.
"""

import functools
import json
import pathlib

import yaml

RAIZ = pathlib.Path(__file__).resolve().parents[1]
CONFIGS = RAIZ / "configs"


@functools.lru_cache(maxsize=None)
def _ler(nome):
    return yaml.safe_load((CONFIGS / f"{nome}.yaml").read_text(encoding="utf-8"))


def protocolo():
    return _ler("protocolo")


def modelos():
    return _ler("modelos")


def modelo_de(chave):
    m = modelos()
    if chave not in m:
        raise SystemExit(f"modelo «{chave}» não existe; há: {sorted(m)}")
    return dict(m[chave], chave=chave)


def encoders():
    """The eleven model keys, ordered by pre-training group, then alphabetically."""
    ordem = {"nli_multilingue": 0, "rte_portugues": 1, "pt_sem_nli": 2, "similaridade": 3}
    return sorted(modelos(), key=lambda k: (ordem[modelos()[k]["grupo"]], k))


def config_de_treino(chave, tarefa):
    """Training configuration of one model on one task; the same for every model."""
    p = protocolo()["treino"]
    m = modelo_de(chave)
    return {
        "modelo": m["id"], "chave": chave, "tarefa": tarefa,
        "lr": float(p["lr"]), "batch": int(p["batch"]), "max_len": int(p["max_len"]),
        # memory-saving options declared per model in configs/modelos.yaml (see motor.py)
        "checkpointing": bool(m.get("gradient_checkpointing") or m.get("poupar_memoria")),
        "adamw_cpu": bool(m.get("poupar_memoria")),
        # the 3-way NLI head is reused only in entailment; in relevance the output layer is
        # always new
        "preservar_cabeca": tarefa == "entailment" and m.get("cabeca_original_classes") == 3,
    }


def folds(tarefa):
    caminho = RAIZ / "data" / f"folds_{tarefa}.json"
    if not caminho.exists():
        raise SystemExit(f"não há {caminho}.\nCorrer:  python src/folds.py")
    return json.loads(caminho.read_text(encoding="utf-8"))
