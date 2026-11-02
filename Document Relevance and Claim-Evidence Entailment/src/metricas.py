"""Macro-F1, per-class precision/recall/F1, confusion matrix and grouped-bootstrap CI.

The 95% CI of Macro-F1 resamples whole claim spans with replacement, because examples of the
same claim span are not independent. It is scipy.stats.bootstrap's percentile interval: the units
resampled are the claim spans, and the statistic is computed on the examples of the claim spans
drawn.
"""

import collections

import numpy as np
from scipy import stats


def matriz(verdade, previsto, classes):
    """Confusion matrix as {gold: {predicted: count}}."""
    m = collections.Counter(zip(verdade, previsto))
    return {v: {p: m.get((v, p), 0) for p in classes} for v in classes}


def f1_por_classe(verdade, previsto, classes):
    saida = {}
    for c in classes:
        vp = sum(1 for v, p in zip(verdade, previsto) if v == c and p == c)
        fp = sum(1 for v, p in zip(verdade, previsto) if v != c and p == c)
        fn = sum(1 for v, p in zip(verdade, previsto) if v == c and p != c)
        prec = vp / (vp + fp) if vp + fp else 0.0
        rec = vp / (vp + fn) if vp + fn else 0.0
        saida[c] = {
            "f1": 2 * prec * rec / (prec + rec) if prec + rec else 0.0,
            "precisao": prec, "revocacao": rec, "n": vp + fn,
        }
    return saida


def grupos(spans):
    """The example indices of each claim span, in order of first appearance."""
    por_span = collections.defaultdict(list)
    for i, s in enumerate(spans):
        por_span[s].append(i)
    return list(por_span.values())


def bootstrap_agrupado(spans, estatistica, n_boot, seed=42):
    """scipy.stats.bootstrap (percentile) of `estatistica`, resampling whole claim spans with
    replacement; returns scipy's BootstrapResult. `estatistica(escolha)` gets the indices of the
    examples of the claim spans drawn and returns a number, or a list of numbers. The resamples
    depend only on the claim spans (in their order of first appearance), `n_boot` and `seed`:
    statistics computed with the same three are paired."""
    lista = grupos(spans)

    def nos_exemplos(sorteadas):
        return np.asarray(estatistica([i for k in sorteadas for i in lista[k]]), dtype=float)

    return stats.bootstrap((np.arange(len(lista)),), nos_exemplos, n_resamples=n_boot, vectorized=False,
                           method="percentile", rng=np.random.default_rng(seed))


def ic95_agrupado(spans, estatistica, n_boot, seed=42):
    """The percentile 95% CI of `bootstrap_agrupado`: a pair, or a list of pairs when `estatistica`
    returns a list (one interval each)."""
    r = bootstrap_agrupado(spans, estatistica, n_boot, seed)
    baixo, alto = np.atleast_1d(r.confidence_interval.low), np.atleast_1d(r.confidence_interval.high)
    pares = [(float(a), float(b)) for a, b in zip(baixo, alto)]
    return pares if np.ndim(r.confidence_interval.low) else pares[0]


def macro_f1_em(verdade, previsto, classes, escolha):
    """Macro-F1 over the examples `escolha` (with repetitions)."""
    pc = f1_por_classe([verdade[i] for i in escolha], [previsto[i] for i in escolha], classes)
    return sum(pc[c]["f1"] for c in classes) / len(classes)


def avaliar(verdade, previsto, spans, classes, n_boot, seed=42):
    """Macro-F1 with its grouped-bootstrap 95% CI, per-class figures and the confusion matrix."""
    por_classe = f1_por_classe(verdade, previsto, classes)
    macro = sum(por_classe[c]["f1"] for c in classes) / len(classes)
    baixo, alto = ic95_agrupado(spans, lambda escolha: macro_f1_em(verdade, previsto, classes, escolha),
                                n_boot, seed)
    return {
        "macro_f1": round(macro, 4),
        "macro_f1_ic95": (round(baixo, 4), round(alto, 4)),
        "n": len(verdade),
        "por_classe": {c: {**{k: round(v, 4) for k, v in por_classe[c].items() if k != "n"},
                           "n": por_classe[c]["n"]}
                       for c in classes},
        "matriz": matriz(verdade, previsto, classes),
    }


def imprimir(nome, r, classes):
    lo, hi = r["macro_f1_ic95"]
    print(f"\n{nome}")
    print(f"  macro-F1 {r['macro_f1']:.3f}  IC95% [{lo:.3f}, {hi:.3f}]   n={r['n']}")
    for c in classes:
        x = r["por_classe"][c]
        print(f"    {c:12} F1 {x['f1']:.3f}  "
              f"P {x['precisao']:.3f}  R {x['revocacao']:.3f}  n={x['n']}")
    print("    matriz (linha = verdade):")
    print("      " + " " * 12 + "".join(f"{c[:6]:>8}" for c in classes))
    for v in classes:
        print(f"      {v:12}" + "".join(f"{r['matriz'][v][p]:>8}" for p in classes))
