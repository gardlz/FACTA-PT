"""Coverage of the annotated training excerpts by windows of 1, 2 and 3 consecutive sentences.

Windows slide with stride 1. An excerpt counts as covered when some window contains it whole;
this is the measurement behind the three-sentence passage size.
"""

import argparse

import conjuntos as cj
import entradas as ent


def _norm(t):
    return " ".join((t or "").split())


def por_frases(texto, k, passo):
    """Windows of k consecutive sentences with stride `passo`; one window if there are fewer."""
    fr = ent.frases_do(texto)
    return [" ".join(fr[i:i + k]) for i in range(0, max(1, len(fr) - k + 1), passo)]


REGRAS = [
    ("1 frase", lambda t: por_frases(t, 1, 1)),
    ("2 frases, passo 1", lambda t: por_frases(t, 2, 1)),
    ("3 frases, passo 1", lambda t: por_frases(t, 3, 1)),
]


def main():
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()

    pares = [x for x in cj.pares("train")
             if x["rotulo4"] != "nei_irrelevante" and (x.get("_oraculo_excertos") or [])]
    alvos = [(_norm(e["texto"]), par)
             for par in pares for e in (par.get("_oraculo_excertos") or [])]
    print(f"=== train: {len(alvos)} excertos anotados em {len(pares)} pares ===\n")

    print(f"{'regra de divisão':26} {'cobertura':>18}")
    print("-" * 46)
    for nome, fn in REGRAS:
        janelas_por_par, cobertos = {}, 0
        for texto, par in alvos:
            pid = par["par_id"]
            if pid not in janelas_por_par:
                janelas_por_par[pid] = [_norm(j) for j in fn(par["evidencia_texto"]) if j.strip()]
            if any(texto in j for j in janelas_por_par[pid]):
                cobertos += 1
        print(f"{nome:26} {cobertos:>6}/{len(alvos)} {100 * cobertos / len(alvos):6.1f}%")


if __name__ == "__main__":
    main()
