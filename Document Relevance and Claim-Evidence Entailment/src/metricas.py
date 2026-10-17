"""Macro-F1, per-class precision/recall/F1, confusion matrix and grouped-bootstrap CI.

The 95% CI of Macro-F1 resamples whole claim spans with replacement, because examples of the
same claim span are not independent.
"""

import collections
import random


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


def avaliar(verdade, previsto, spans, classes, n_boot, seed=42):
    """Macro-F1 with its grouped-bootstrap 95% CI, per-class figures and the confusion matrix."""
    por_classe = f1_por_classe(verdade, previsto, classes)
    macro = sum(por_classe[c]["f1"] for c in classes) / len(classes)

    indices_por_span = collections.defaultdict(list)
    for i, s in enumerate(spans):
        indices_por_span[s].append(i)
    lista = list(indices_por_span.values())
    rnd = random.Random(seed)
    macros = []
    for _ in range(n_boot):
        escolha = [i for _ in lista for i in rnd.choice(lista)]
        v = [verdade[i] for i in escolha]
        p = [previsto[i] for i in escolha]
        pc = f1_por_classe(v, p, classes)
        macros.append(sum(pc[c]["f1"] for c in classes) / len(classes))

    def ic(valores):
        v = sorted(valores)
        return round(v[int(0.025 * len(v))], 4), round(v[int(0.975 * len(v))], 4)

    return {
        "macro_f1": round(macro, 4),
        "macro_f1_ic95": ic(macros),
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
