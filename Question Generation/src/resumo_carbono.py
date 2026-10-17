"""Aggregates the codecarbon summaries written by `carbon.py` (Table 4.7).

Writes the totals per regime to `carbono_por_regime.csv` and prints runs, GPU-hours, kWh and
kg CO2eq per regime. Each process uses one GPU, so process hours are GPU-hours.

    python src/resumo_carbono.py --pastas outputs/carbon qg_kfold/runs/v3/carbon
"""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def le_resumos(pastas) -> list:
    linhas = []
    for pasta in pastas:
        p = Path(pasta)
        if not p.exists():
            print(f"[carbono] pasta inexistente (ignorada): {p}")
            continue
        for ficheiro in sorted(p.glob("*.json")):
            try:
                linhas.append(json.loads(ficheiro.read_text(encoding="utf-8")))
            except Exception as e:                              # noqa: BLE001
                print(f"[carbono] {ficheiro}: ilegível ({type(e).__name__}: {e})")
    return linhas


def escreve_csv(caminho: Path, linhas: list, campos: list) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(linhas)
    print(f"[carbono] {len(linhas)} linhas -> {caminho}")


def soma(linhas: list, chaves: tuple) -> list:
    grupos = defaultdict(lambda: {"n_corridas": 0, "duration": 0.0, "energy_consumed": 0.0,
                                  "emissoes_kg_co2eq": 0.0})
    for l in linhas:
        chave = tuple(l.get(k) or "" for k in chaves)
        g = grupos[chave]
        g["n_corridas"] += 1
        for campo in ("duration", "energy_consumed", "emissoes_kg_co2eq"):
            valor = l.get(campo)
            if isinstance(valor, (int, float)):
                g[campo] += valor
    saida = []
    for chave, g in sorted(grupos.items()):
        linha = dict(zip(chaves, chave))
        linha.update({k: (round(v, 6) if isinstance(v, float) else v) for k, v in g.items()})
        linha["horas"] = round(g["duration"] / 3600, 3)
        saida.append(linha)
    return saida


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--pastas", nargs="+", default=["outputs/carbon", "qg_kfold/runs/v3/carbon"])
    p.add_argument("--saida", default="outputs/metrics")
    args = p.parse_args()

    linhas = le_resumos(args.pastas)
    if not linhas:
        raise SystemExit(
            "Sem medições de carbono nas pastas indicadas. São escritas pelas experiências "
            "(--carbon_dir), com o codecarbon instalado.")

    destino = Path(args.saida)
    por_regime = soma(linhas, ("regime",))
    escreve_csv(destino / "carbono_por_regime.csv", por_regime,
                ["regime", "n_corridas", "horas", "energy_consumed", "emissoes_kg_co2eq"])

    print(f"\n{'regime':22} {'corridas':>8} {'horas':>9} {'kWh':>10} {'kg CO2eq':>10}")
    for l in por_regime:
        print(f"{l['regime'] or '(sem regime)':22} {l['n_corridas']:8} {l['horas']:9.2f} "
              f"{l['energy_consumed']:10.4f} {l['emissoes_kg_co2eq']:10.5f}")
    total_kwh = sum(l["energy_consumed"] for l in por_regime)
    total_kg = sum(l["emissoes_kg_co2eq"] for l in por_regime)
    total_h = sum(l["horas"] for l in por_regime)
    print(f"{'TOTAL':22} {sum(l['n_corridas'] for l in por_regime):8} {total_h:9.2f} "
          f"{total_kwh:10.4f} {total_kg:10.5f}")


if __name__ == "__main__":
    main()
