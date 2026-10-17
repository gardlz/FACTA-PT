"""Computational cost per phase (Table 6.3), summed from the CodeCarbon fields of the records.

Cross-validation: latest record per (task, model) in outputs/resultados.jsonl; final phase: every
*_resultado.json in outputs/final. Unmeasured blocks are left out of the sums.
"""

import argparse
import json
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parents[1]
RESULTADOS = RAIZ / "outputs/resultados.jsonl"
FINAL = RAIZ / "outputs/final"


def somar(registos):
    """Totals of a list of `carbono` blocks (see carbono.Medicao.como_dict)."""
    d = {"n": 0, "s": 0.0, "kwh": 0.0, "kg": 0.0}
    for c in registos:
        d["n"] += 1
        if not c or not c.get("medido"):
            continue
        d["s"] += c["segundos"]
        d["kwh"] += c["energia_kwh"]
        d["kg"] += c["emissoes_kg"]
    return d


def main():
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()

    reg = [json.loads(l) for l in RESULTADOS.read_text(encoding="utf-8").splitlines() if l.strip()]
    ultimo = {}
    for r in reg:
        ultimo[(r["tarefa"], r["modelo"])] = r
    cv = list(ultimo.values())
    finais = [json.loads(f.read_text(encoding="utf-8"))
              for f in sorted(FINAL.glob("*_resultado.json"))]

    fases = {"validação cruzada": somar([r.get("carbono") for r in cv]),
             "treino final + teste": somar([r.get("carbono") for r in finais])}
    total = {k: sum(d[k] for d in fases.values()) for k in ("n", "s", "kwh", "kg")}
    print(f"{len(cv)} combinações modelo-tarefa "
          f"({sum(r['epocas']['n_folds'] for r in cv)} folds), {len(finais)} treinos finais\n")
    print("| fase | execuções | horas | kWh | % energia | kg CO2eq |")
    print("|---|---:|---:|---:|---:|---:|")
    for nome, d in list(fases.items()) + [("total", total)]:
        print(f"| {nome} | {d['n']} | {d['s'] / 3600:.2f} | {d['kwh']:.3f} | "
              f"{100 * d['kwh'] / (total['kwh'] or 1):.2f} | {d['kg']:.3f} |")


if __name__ == "__main__":
    main()
