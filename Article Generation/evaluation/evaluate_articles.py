"""Score the generated articles on the six metrics in `metricas.py`.

Evidence grounding (component `citacoes`) relies on a local NLI classifier, article quality (`holistico`)
on one Gemini call per article; articles with no input evidence are left out. Judge decisions are cached
under `--saida` and `resultados.jsonl` is always rebuilt from them, so `--montar` calls no model.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Tuple

if __package__ in (None, ""):                       # also allow `python evaluation/evaluate_articles.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "evaluation"

from . import article_parser as ap                  # noqa: E402
from . import citation_judge as cj                  # noqa: E402
from . import citation_metrics as cm                # noqa: E402
from . import config, holistic_judge as hj, metricas   # noqa: E402

LOTE_ARTIGOS = 50                   # articles per chunk; a chunk's NLI pairs go to the judge together


class DecisaoEmFalta(RuntimeError):
    pass


class BackendSoCache:
    """Cache-only NLI backend: never loads the model, but keeps the real identity used in the cache keys."""
    def __init__(self, backend_real):
        self.model_id, self.revision = backend_real.model_id, backend_real.revision
        self.identidade = dict(backend_real.identidade)

    def n_tokens(self, premissa, hipotese):
        # JuizNLI.decidir calls this first for each cache miss, so any missing decision raises here.
        raise DecisaoEmFalta("decisão em falta no cache")


def _caminhos(saida: Path) -> dict:
    # Cache keys hash the judge identity and its full input.
    return {"cache_citacoes": saida / "cache_citacoes.jsonl",
            "cache_holistico": saida / f"cache_holistico_{config.HOLISTIC_JUDGE_MODEL}.jsonl",
            "resultados": saida / "resultados.jsonl"}


# --------------------------------------------------------------------------- execution
def correr_citacoes(artigos: List[dict], juiz: cj.JuizNLI) -> None:
    """Fill the NLI decision cache, chunk by chunk; the results are built from it later, by `montar`."""
    for a in range(0, len(artigos), LOTE_ARTIGOS):
        cm.avaliar(artigos[a:a + LOTE_ARTIGOS], juiz)
        print(f"  citações: {min(a + LOTE_ARTIGOS, len(artigos))}/{len(artigos)} artigos | {juiz.contagem}", flush=True)


def correr_holistico(artigos: List[dict], juiz: hj.JuizHolistico) -> None:
    """One Gemini call per uncached article; an article that fails every retry is reported and skipped."""
    for i, a in enumerate(artigos, 1):
        try:
            juiz.avaliar(a)
        except RuntimeError as e:
            print(f"  [erro] {e}", flush=True)
        if i % 25 == 0 or i == len(artigos):
            print(f"  holístico: {i}/{len(artigos)} | {juiz.contagem}", flush=True)


def montar(artigos: List[dict], cam: dict) -> List[dict]:
    """Build the per-article results from the caches alone; a missing decision leaves its metrics null, with a reason."""
    real = cj._backend_de(config.CITATION_SUPPORT_JUDGE)
    juiz_cache = cj.JuizNLI(BackendSoCache(real), cam["cache_citacoes"])
    cache_h = hj.JuizHolistico(cam["cache_holistico"]).cache
    resultados = []
    for a in artigos:
        try:
            cit = cm.avaliar([a], juiz_cache)[a["article_id"]]
        except DecisaoEmFalta:
            cit = cm.calcular(cm._planear(a), False, "missing_decisions", "decisões do juiz em falta no cache")
        reg_h = cache_h.get(hj.JuizHolistico.chave(hj.pedido(a)))
        qualidade = {d: {"score": reg_h["scores"][d]["score"] if reg_h else None,
                         "justification": reg_h["scores"][d]["justification"] if reg_h else None}
                     for d in metricas.QUALIDADE}
        qualidade["status"] = "ok" if reg_h else "missing"
        resultados.append({"article_id": a["article_id"], "claim_id": a["claim_id"],
                           "generator_model": a["generator_model"], "condition": a["condition"],
                           "evidence_grounding": cit, "article_quality": qualidade})
    return resultados


def _escrever_jsonl(caminho: Path, linhas: List[dict]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8") as f:
        for linha in linhas:
            f.write(json.dumps(linha, ensure_ascii=False) + "\n")


def com_evidencia(artigos: List[dict]) -> Tuple[List[dict], List[str]]:
    """Split off the articles with no input evidence: (articles kept, ids of those left out)."""
    return [a for a in artigos if a["evidence"]], [a["article_id"] for a in artigos if not a["evidence"]]


def _validar_argumentos(p: argparse.ArgumentParser, args) -> None:
    """Fail on any argument or configuration problem before the local NLI judge starts."""
    if not (args.executar or args.montar):
        p.error("indica --executar (corre os juízes e monta) ou --montar (só monta, a partir dos caches)")
    args.componentes_efetivos = {c.strip() for c in args.componentes.split(",") if c.strip()}
    desconhecidos = args.componentes_efetivos - {"citacoes", "holistico"}
    if desconhecidos:
        p.error(f"componentes desconhecidos: {sorted(desconhecidos)} (válidos: citacoes, holistico)")
    if not args.executar:
        return
    # Check the Gemini credential and SDK now, not after a long NLI pass.
    try:
        if "holistico" in args.componentes_efetivos:
            config.credencial("gemini")
            hj.preparar_sdk()
    except (config.CredencialEmFalta, ImportError) as e:
        p.exit(2, f"erro de configuração: {e}\n")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--modelos", nargs="*", default=None, help="generator_model (ex.: gemma4_e4b)")
    p.add_argument("--condicoes", nargs="*", default=None, help="ex.: full sem_plano full+sem_gramatica")
    p.add_argument("--componentes", default="citacoes,holistico",
                   help="citacoes, holistico (vírgulas). Por omissão os dois")
    p.add_argument("--batch-size", type=int, default=config.CITATION_JUDGE_BATCH)
    p.add_argument("--saida", type=Path, default=config.SAIDAS)
    p.add_argument("--executar", action="store_true", help="corre os juízes e monta os resultados")
    p.add_argument("--montar", action="store_true", help="só monta resultados.jsonl a partir dos caches")
    args = p.parse_args()
    _validar_argumentos(p, args)

    artigos = list(ap.carregar_artigos(args.modelos, args.condicoes))
    claims = {a["claim_id"] for a in artigos}
    artigos, sem_evidencia = com_evidencia(artigos)
    cam = _caminhos(args.saida)
    args.saida.mkdir(parents=True, exist_ok=True)
    print(f"{len(artigos)} artigos de {len(claims)} claims ({len(sem_evidencia)} sem evidências "
          f"ficam de fora) | saída {args.saida}")

    comp = args.componentes_efetivos if args.executar else set()
    if "citacoes" in comp:
        correr_citacoes(artigos, cj.juiz_configurado(cam["cache_citacoes"], args.batch_size))
    if "holistico" in comp:
        correr_holistico(artigos, hj.JuizHolistico(cam["cache_holistico"]))

    resultados = montar(artigos, cam)
    _escrever_jsonl(cam["resultados"], resultados)
    print(f"{len(resultados)} resultados -> {cam['resultados']}")


if __name__ == "__main__":
    main()
