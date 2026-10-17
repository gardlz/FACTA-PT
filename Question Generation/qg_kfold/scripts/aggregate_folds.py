"""Aggregates the four folds and selects the number of epochs: the earliest whose 4-fold mean
dev H-BERT is within 0.05 of the maximum. A selected epoch that is the last of its horizon marks
the combination for a rerun from scratch with the next horizon (20 -> 30 -> 40). Writes
agregado_por_epoca.csv, best_epochs.csv/.json and reports/extensoes_pendentes.csv.
"""

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
KFOLD = RAIZ / "qg_kfold"

ESCADA = {20: 30, 30: 40}
TETO_ABSOLUTO = 40

METRICAS = ["mean_h_bert"]


def le_registos(pasta: Path) -> list:
    registos = []
    for f in sorted(pasta.glob("*__por_epoca.jsonl")):
        for linha in f.read_text(encoding="utf-8").splitlines():
            if linha.strip():
                registos.append(json.loads(linha))
    return registos


def media_desvio(valores: list) -> tuple:
    """(mean, population std) rounded to 4 decimals; std 0.0 for a single value."""
    validos = [v for v in valores if isinstance(v, (int, float))]
    if not validos:
        return None, None
    return (
        round(statistics.fmean(validos), 4),
        round(statistics.pstdev(validos), 4) if len(validos) > 1 else 0.0,
    )


def agrega(registos: list) -> list:
    """One row per (model, configuration, epoch) with the across-fold mean and std."""
    grupos = defaultdict(list)
    for r in registos:
        grupos[(r["modelo"], r["config"], r["epoch"])].append(r)
    linhas = []
    for (modelo, config, epoca), rs in sorted(grupos.items()):
        linha = {
            "modelo": modelo,
            "config": config,
            "epoch": epoca,
            "n_folds": len(rs),
            "epochs_max": rs[0].get("epochs_max"),
            "learning_rate": rs[0].get("learning_rate"),
            "warmup_ratio": rs[0].get("warmup_ratio"),
            "effective_batch_size": rs[0].get("effective_batch_size"),
            "scheduler_horizon_epochs": rs[0].get("scheduler_horizon_epochs"),
        }
        for m in METRICAS:
            media, desvio = media_desvio([r.get(m) for r in rs])
            linha[m] = media
            linha[f"std_{m.removeprefix('mean_')}"] = desvio
        linhas.append(linha)
    return linhas


def escolhe_epocas(linhas: list, tolerancia: float, n_folds_exigidos: int) -> list:
    por_combinacao = defaultdict(list)
    for l in linhas:
        por_combinacao[(l["modelo"], l["config"])].append(l)

    escolhas = []
    for (modelo, config), candidatas in sorted(por_combinacao.items()):
        completas = [
            c for c in candidatas
            if c["n_folds"] >= n_folds_exigidos and c["mean_h_bert"] is not None
        ]
        if not completas:
            escolhas.append({
                "modelo": modelo, "config": config, "best_epoch": None,
                "estado": "incompleto",
                "detalhe": f"nenhuma época com {n_folds_exigidos} folds e h_bert",
            })
            continue

        # A combination must cover every epoch of one declared horizon; an interrupted run
        # would otherwise look like a completed search ending at its last epoch.
        horizontes = {int(c.get("scheduler_horizon_epochs") or c.get("epochs_max") or 0) for c in completas}
        if len(horizontes) != 1:
            escolhas.append({
                "modelo": modelo, "config": config, "best_epoch": None,
                "estado": "incompleto",
                "detalhe": f"scheduler horizons inconsistentes: {sorted(horizontes)}",
            })
            continue
        horizonte = horizontes.pop()
        epocas_completas = {int(c["epoch"]) for c in completas}
        if horizonte <= 0 or epocas_completas != set(range(1, horizonte + 1)):
            faltam = sorted(set(range(1, max(horizonte, 0) + 1)) - epocas_completas)
            escolhas.append({
                "modelo": modelo, "config": config, "best_epoch": None,
                "estado": "incompleto",
                "detalhe": f"trajetória incompleta para horizonte {horizonte}; épocas em falta={faltam[:10]}",
            })
            continue

        melhor = max(c["mean_h_bert"] for c in completas)
        empatadas = [c for c in completas if melhor - c["mean_h_bert"] <= tolerancia]
        escolhida = min(empatadas, key=lambda c: c["epoch"])
        teto = horizonte

        # The horizon is extended only when the SELECTED epoch is the last one.
        if escolhida["epoch"] < teto:
            estado, proximo = "terminado", None
        elif teto in ESCADA:
            estado, proximo = "prolongar", ESCADA[teto]
        elif teto >= TETO_ABSOLUTO:
            estado, proximo = "limite_atingido", None
        else:
            estado, proximo = "prolongar", TETO_ABSOLUTO

        escolhas.append({
            "modelo": modelo,
            "config": config,
            "best_epoch": escolhida["epoch"],
            "epocas_avaliadas": teto,
            "scheduler_horizon_epochs": teto,
            "learning_rate": escolhida.get("learning_rate"),
            "warmup_ratio": escolhida.get("warmup_ratio"),
            "effective_batch_size": escolhida.get("effective_batch_size"),
            "mean_h_bert": escolhida["mean_h_bert"],
            "std_h_bert": escolhida["std_h_bert"],
            "estado": estado,
            "prolongar_ate": proximo,
        })
    return escolhas


def escreve_csv(caminho: Path, linhas: list) -> None:
    if not linhas:
        return
    caminho.parent.mkdir(parents=True, exist_ok=True)
    campos = list(linhas[0].keys())
    with open(caminho, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=campos)
        w.writeheader()
        w.writerows(linhas)
    print(f"[agregado] {len(linhas)} linhas -> {caminho}")


CAMPOS_EXTENSOES = ["modelo", "config", "prolongar_ate"]


def escreve_extensoes_pendentes(caminho: Path, prolongar: list) -> None:
    """Pending horizon extensions; always rewritten (header only when there are none)."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS_EXTENSOES, extrasaction="ignore")
        w.writeheader()
        w.writerows(prolongar)
    print(f"[agregado] {len(prolongar)} extensoes pendentes -> {caminho}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--results_dir", default=str(KFOLD / "runs/v3/results"))
    p.add_argument("--reports_dir", default=str(KFOLD / "runs/v3/reports"))
    p.add_argument("--tolerancia", type=float, default=0.05)
    p.add_argument("--n_folds", type=int, default=4)
    args = p.parse_args()

    registos = le_registos(Path(args.results_dir))
    if not registos:
        raise SystemExit(f"Sem ficheiros *__por_epoca.jsonl em {args.results_dir}")

    linhas = agrega(registos)
    escolhas = escolhe_epocas(linhas, args.tolerancia, args.n_folds)

    destino = Path(args.results_dir)
    escreve_csv(destino / "agregado_por_epoca.csv", linhas)
    escreve_csv(destino / "best_epochs.csv", escolhas)
    (destino / "best_epochs.json").write_text(
        json.dumps(escolhas, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    reports = Path(args.reports_dir)
    reports.mkdir(parents=True, exist_ok=True)
    prolongar = [e for e in escolhas if e["estado"] == "prolongar"]
    escreve_extensoes_pendentes(reports / "extensoes_pendentes.csv", prolongar)

    limites = [e for e in escolhas if e["estado"] == "limite_atingido"]
    if limites:
        escreve_csv(reports / "limite_atingido.csv", limites)

    print(f"\n{'modelo':15} {'config':20} {'best':>5} {'de':>4} {'h_bert':>8} {'±':>6} {'estado':>16}")
    for e in escolhas:
        h = "—" if e.get("mean_h_bert") is None else f"{e['mean_h_bert']:8.2f}"
        s = "—" if e.get("std_h_bert") is None else f"{e['std_h_bert']:6.2f}"
        print(
            f"{e['modelo']:15} {e['config']:20} {str(e['best_epoch']):>5} "
            f"{str(e.get('epocas_avaliadas')):>4} {h} {s} {e['estado']:>16}"
            + (f" -> {e['prolongar_ate']}" if e.get("prolongar_ate") else "")
        )


if __name__ == "__main__":
    main()
