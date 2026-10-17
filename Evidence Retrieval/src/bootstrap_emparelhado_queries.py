"""Paired bootstrap, at claim-span level, of the differences between query strategies.

Claim spans are resampled with replacement (10,000 resamples per span set, seed 42) and the
same resample serves both strategies; the 95% interval is the 2.5th-97.5th percentile of the
paired differences. Per-span metrics come from comparar_queries.py.
"""

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

RETRIEVAL = Path(__file__).resolve().parent            # src/
sys.path.insert(0, str(RETRIEVAL))
import comparar_queries as cq  # noqa: E402

SAIDA = RETRIEVAL.parent / "outputs" / "bootstrap"
N_BOOT = 10_000
SEMENTE = 42
ALFA = 0.05

MODELOS = [c for c in cq.NOMES if c.startswith("FT_")]
AMALIA = "FT_amalia_9b"
METRICAS = (("rel_macro", "Relevant Macro Recall"), ("rel_micro", "Relevant Micro Recall"),
            ("dec_macro", "Decisive Macro Recall"), ("dec_micro", "Decisive Micro Recall"),
            ("dcsc", "DCSC"))


def por_span(dados, gold, chave, relacoes):
    """{(condition, configuration): {"rel": (hits, targets), "dec": (hits, targets), "dcsc": covered}}.

    Spans keep the order of `gold` for every condition, which makes the resampling paired.
    DCSC per span follows Eq. 5.7.
    """
    saida = {}
    for leitura, _ in cq.CONFIGURACOES:
        _vr, alvo_span, decidiveis = cq.veracidade(dados, gold, chave, relacoes, leitura)
        for c in cq.NOMES:
            rel = cq.por_span(dados, gold, chave, leitura, c, "relevante")
            dec = cq.por_span(dados, gold, chave, leitura, c, "decisivo")
            cobertos = []
            for s in decidiveis:
                entregues = {chave.get(d, d) for d in cq.entrega(dados, c, s, leitura)}
                cobertos.append(bool(entregues & {chave.get(d, d) for d in gold[s][alvo_span[s]]}))
            saida[c, leitura] = {
                "rel": np.array([x for x in rel if x[1] > 0], dtype=np.int64),
                "dec": np.array([x for x in dec if x[1] > 0], dtype=np.int64),
                "dcsc": np.array(cobertos, dtype=np.int64),
            }
    return saida


def metricas(x, idx=None):
    """The five metrics of a condition, on the full sample (idx=None) or on every resample."""
    rel = x["rel"] if idx is None else x["rel"][idx["rel"]]
    dec = x["dec"] if idx is None else x["dec"][idx["dec"]]
    cob = x["dcsc"] if idx is None else x["dcsc"][idx["dcsc"]]
    return {
        "rel_macro": (rel[..., 0] / rel[..., 1]).mean(axis=-1),
        "rel_micro": rel[..., 0].sum(axis=-1) / rel[..., 1].sum(axis=-1),
        "dec_macro": (dec[..., 0] / dec[..., 1]).mean(axis=-1),
        "dec_micro": dec[..., 0].sum(axis=-1) / dec[..., 1].sum(axis=-1),
        "dcsc": cob.mean(axis=-1),
    }


def comparacoes():
    """(configuration, A, B): the claim span against the claim in every configuration, and
    AMALIA against both under Matched retrieval volume."""
    lista = [(leitura, "claim_span", "claim_frase") for leitura, _ in cq.CONFIGURACOES]
    lista += [("orcamento_igual", AMALIA, b) for b in ("claim_frase", "claim_span")]
    return lista


def inclui_zero(lo, hi, tolerancia=1e-12):
    """Does the closed interval include 0? (tolerance for floating-point summation order)"""
    return bool(lo <= tolerancia and hi >= -tolerancia)


def acima(obs, leitura, referencia, m):
    """How many of the 14 models score above the reference (point estimates)."""
    return sum(1 for c in MODELOS
               if float(obs[c, leitura][m]) - float(obs[referencia, leitura][m]) > 1e-12)


def main():
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    dados, gold, chave = cq.carregar()
    cq.preparar_fundo(dados, chave)
    relacoes = cq.ler_relacoes(cq.DATASET, chave)
    base = por_span(dados, gold, chave, relacoes)
    n = {k: len(base[next(iter(base))][k]) for k in ("rel", "dec", "dcsc")}

    obs = {k: metricas(v) for k, v in base.items()}

    # One set of resamples per span set, shared by every comparison.
    idx = {}
    for k in ("rel", "dec", "dcsc"):
        rng = np.random.default_rng(SEMENTE)
        idx[k] = rng.integers(0, n[k], size=(N_BOOT, n[k]))
    usadas = {(x, leitura) for leitura, a, b in comparacoes() for x in (a, b)}
    boot = {k: metricas(base[k], idx) for k in usadas}

    nome_config = dict(cq.CONFIGURACOES)
    linhas = []
    for leitura, a, b in comparacoes():
        for m, nome_m in METRICAS:
            d = boot[a, leitura][m] - boot[b, leitura][m]
            lo, hi = np.percentile(d, [100 * ALFA / 2, 100 - 100 * ALFA / 2])
            oa, ob = float(obs[a, leitura][m]), float(obs[b, leitura][m])
            linhas.append({
                "configuration": nome_config[leitura],
                "strategy_a": cq.NOMES[a], "strategy_b": cq.NOMES[b], "metric": nome_m,
                "n_claim_spans": n["dcsc" if m == "dcsc" else m[:3]],
                "observed_a": oa, "observed_b": ob, "observed_difference": oa - ob,
                "ci95_low": float(lo), "ci95_high": float(hi),
                "ci_includes_zero": inclui_zero(lo, hi),
            })
    SAIDA.mkdir(parents=True, exist_ok=True)
    with open(SAIDA / "bootstrap_emparelhado.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0]))
        w.writeheader()
        w.writerows(linhas)
    (SAIDA / "BOOTSTRAP_EMPARELHADO.md").write_text("\n".join(relatorio(linhas, n, obs)) + "\n",
                                                     encoding="utf-8")
    print(f"{len(linhas)} comparações; spans: relevante {n['rel']}, decisivo {n['dec']}, DCSC {n['dcsc']}")
    print(f"escrito {SAIDA / 'BOOTSTRAP_EMPARELHADO.md'} e bootstrap_emparelhado.csv")


def fmt(x):
    """3 decimals; 4 when the value would round to ±0.000, to show its sign."""
    if abs(x) < 1e-12:
        return "0"
    return f"{x:+.4f}" if abs(x) < 5e-4 else f"{x:+.3f}"


def tabela(linhas):
    out = ["| Configuration | Strategy A | Strategy B | Metric | Observed A | Observed B | Difference "
           "| 95% CI of the paired difference | CI includes 0? |",
           "|---|---|---|---|---:|---:|---:|---|---|"]
    for x in linhas:
        out.append(f"| {x['configuration']} | {x['strategy_a']} | {x['strategy_b']} | {x['metric']} | "
                   f"{x['observed_a']:.3f} | {x['observed_b']:.3f} | {fmt(x['observed_difference'])} | "
                   f"[{fmt(x['ci95_low'])}, {fmt(x['ci95_high'])}] | "
                   f"{'yes' if x['ci_includes_zero'] else '**no**'} |")
    return out + [""]


def relatorio(linhas, n, obs):
    l = [
        "# Paired bootstrap of the query strategies",
        "",
        "Generated by `src/bootstrap_emparelhado_queries.py`.",
        "",
        f"Claim spans: Relevant evidence n = {n['rel']}, decisive evidence n = {n['dec']}, "
        f"DCSC n = {n['dcsc']}. {N_BOOT:,} paired resamples per span set "
        f"(`numpy.random.default_rng({SEMENTE})`), shared by every comparison; the interval is "
        "the 2.5th-97.5th percentile of the paired differences and is closed.",
        "",
        "## AMALIA-9B-0626-DPO against the declarative baselines",
        "",
    ]
    l += tabela([x for x in linhas if x["strategy_a"] == cq.NOMES[AMALIA]])
    l += ["## Claim span against Claim", ""]
    l += tabela([x for x in linhas if x["strategy_a"] == cq.NOMES["claim_span"]])
    l += ["## Models above each declarative baseline (point estimates)", "",
          "| Configuration | Metric | Models above Claim | Models above Claim span |",
          "|---|---|---:|---:|"]
    for leitura, nome_config in cq.CONFIGURACOES:
        for m, nome_m in METRICAS:
            l.append(f"| {nome_config} | {nome_m} | "
                     f"{acima(obs, leitura, 'claim_frase', m)}/{len(MODELOS)} | "
                     f"{acima(obs, leitura, 'claim_span', m)}/{len(MODELOS)} |")
    return l


if __name__ == "__main__":
    main()
