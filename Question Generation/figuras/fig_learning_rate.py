#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Figure 4.3: the linear learning-rate schedule (warm-up 0.1) for 20, 30 and 40-epoch horizons.

The 20 and 30-epoch curves are read from the per-step logs of a combination whose
cross-validation was rerun with a 30-epoch horizon; the 40-epoch curve is computed with the
same formula, which must first reproduce the two measured curves exactly.

    python figuras/fig_learning_rate.py
"""
import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, MultipleLocator

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum_qg import (SERIE_1, SERIE_2, TINTA_2, TINTA_FRACA, SUPERFICIE,
                      LARGURA, CONFIGS, estilo, arrumar, manifesto,
                      RESULTADOS, gravar)   # noqa: E402

HORIZONTES_MEDIDOS = (20, 30)
HORIZONTE_CALCULADO = 40
WARMUP = 0.1


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--modelo", default=None,
                   help="Model to draw, with --config. Default: the first configuration (in "
                        "the order of Table 4.8) and, within it, the first model of "
                        "models_manifest.json with per-step logs for both measured horizons "
                        "in --fold.")
    p.add_argument("--config", default=None, help="Supervision configuration to draw.")
    p.add_argument("--fold", type=int, default=1, help="Fold to read. Default: %(default)s")
    p.add_argument("--output", default="figuras/learning_rate.pdf",
                   help="Output file (.pdf; a .png is written next to it). Default: %(default)s")
    p.add_argument("--width", type=float, default=LARGURA,
                   help="Final width of the file, in inches. Default: %(default)s")
    p.add_argument("--largura-painel", type=float, default=5.8, dest="largura_painel",
                   help="Width of the drawing, in inches; the rest up to --width is margin. "
                        "Default: %(default)s")
    p.add_argument("--altura", type=float, default=2.8, help="Height in inches.")
    return p.parse_args()


def arquitetura_de(modelo, metas):
    return "encdec" if metas[modelo]["arquitetura"] == "encoder_decoder" else "decoder"


def caminho_lr(modelo, config, fold, horizonte, metas):
    """Per-step learning-rate log of one fold run (written by kfold_eval.py)."""
    arq = arquitetura_de(modelo, metas)
    return RESULTADOS / f"{config}__{arq}__{modelo}__fold{fold}__h{horizonte}__lr_por_step.jsonl"


def com_dois_horizontes(fold, metas):
    """First (configuration, then manifest model order) with logs for both measured horizons."""
    for config in CONFIGS:
        for modelo in metas:
            if all(caminho_lr(modelo, config, fold, h, metas).exists()
                   for h in HORIZONTES_MEDIDOS):
                return modelo, config
    raise SystemExit(f"Nenhuma combinação tem registos por passo dos horizontes "
                     f"{HORIZONTES_MEDIDOS} no fold {fold}, em {RESULTADOS}.")


def ler_lr(modelo, config, fold, horizonte, metas):
    """(step, epoch, learning_rate) arrays from one per-step log."""
    caminho = caminho_lr(modelo, config, fold, horizonte, metas)
    if not caminho.exists():
        disponiveis = sorted(p.name for p in RESULTADOS.glob(f"*{modelo}*lr_por_step.jsonl"))
        raise SystemExit(f"Falta {caminho.name}.\n"
                         + (f"Há {len(disponiveis)} para {modelo}; ex.: {disponiveis[:3]}"
                            if disponiveis else
                            "Estes ficheiros são escritos pelos scripts de treino."))
    linhas = [json.loads(l) for l in caminho.read_text(encoding="utf-8").splitlines() if l.strip()]
    return (np.array([x["step"] for x in linhas]),
            np.array([x["epoch"] for x in linhas]),
            np.array([x["learning_rate"] for x in linhas]))


def passos_por_epoca(passo, epoca):
    """Optimisation steps per epoch (independent of the horizon)."""
    return float(passo.max()) / float(epoca.max())


def prever_lr(passos_epoca, pico, horizonte, warmup=WARMUP):
    """Linear schedule with warm-up for a horizon that was not run (same formula as training)."""
    total = int(round(horizonte * passos_epoca))
    aquece = math.ceil(warmup * total)          # as TrainingArguments.get_warmup_steps
    passo = np.arange(1, total + 1, dtype=float)
    subida = passo / max(aquece, 1)
    descida = (total - passo) / max(total - aquece, 1)
    lr = np.where(passo < aquece, subida, np.maximum(descida, 0.0)) * pico
    return passo / passos_epoca, lr


def conferir_previsao(medidas, passos_epoca, pico, tolerancia=1e-12):
    """Recompute the measured horizons with the formula; stop if any differs."""
    erros = {}
    for horizonte, (_passo, _epoca, lr) in sorted(medidas.items()):
        _ep, prevista = prever_lr(passos_epoca, pico, horizonte)
        if len(prevista) != len(lr):
            raise SystemExit(
                f"A fórmula dá {len(prevista)} passos para o horizonte {horizonte} e o "
                f"registo tem {len(lr)}. Com os passos por época a mudarem com o "
                f"horizonte, a curva calculada de {HORIZONTE_CALCULADO} épocas não se "
                "sustenta.")
        erros[horizonte] = float(np.abs(prevista - lr).max())
    pior = max(erros.values())
    if pior > tolerancia:
        detalhe = ", ".join(f"h{h}: {e:.2e}" for h, e in erros.items())
        raise SystemExit(
            f"A fórmula do scheduler não reproduz os horizontes medidos ({detalhe}); "
            f"a curva calculada de {HORIZONTE_CALCULADO} épocas não seria fiável.")


def pontos_em_dados(ax, dx_pt=0.0, dy_pt=0.0):
    """An offset in typographic points expressed in data units."""
    inv = ax.transData.inverted()
    px = ax.figure.dpi / 72.0
    (x0, y0), (x1, y1) = inv.transform([[0, 0], [dx_pt * px, dy_pt * px]])
    return x1 - x0, y1 - y0


def arrumar_rotulo(ax, texto, curvas, h_alvo, folga_pt=2.4):
    """Place a label in the free band above its own curve and below the next one (measured)."""
    fig = ax.figure
    fig.canvas.draw()
    caixa = texto.get_window_extent(fig.canvas.get_renderer())
    inv = ax.transData.inverted()
    (x0, baixo), (x1, cima) = inv.transform([[caixa.x0, caixa.y0], [caixa.x1, caixa.y1]])
    altura = cima - baixo
    _dx, folga = pontos_em_dados(ax, 0.0, folga_pt)

    troco = np.linspace(x0, x1, 48)
    chao = float(np.interp(troco, *curvas[h_alvo]).max())
    tecto = min((float(np.interp(troco, *curvas[h]).min()) for h in curvas if h > h_alvo),
                default=float(ax.get_ylim()[1]))

    y = chao + folga
    if y + altura > tecto - folga:
        y = max(chao + folga * 0.4, tecto - folga - altura)
    texto.set_position((texto.get_position()[0], y))
    texto.set_verticalalignment("bottom")


def painel_horizontes(ax, modelo, config, fold, metas):
    """The three horizons against the epoch: three different runs, not one stretched."""
    medidas = {h: ler_lr(modelo, config, fold, h, metas) for h in HORIZONTES_MEDIDOS}
    passo, epoca, _lr = medidas[min(HORIZONTES_MEDIDOS)]
    por_epoca = passos_por_epoca(passo, epoca)
    pico = max(float(lr.max()) for _p, _e, lr in medidas.values())
    conferir_previsao(medidas, por_epoca, pico)

    curvas = {h: (e, lr) for h, (_p, e, lr) in medidas.items()}
    curvas[HORIZONTE_CALCULADO] = prever_lr(por_epoca, pico, HORIZONTE_CALCULADO)

    # The computed horizon is drawn in neutral ink: colour means "measured".
    tracos = {20: dict(color=SERIE_1, linestyle="solid", linewidth=1.6),
              30: dict(color=SERIE_2, linestyle=(0, (4, 1.6)), linewidth=1.6),
              40: dict(color=TINTA_2, linestyle=(0, (1.1, 1.7)), linewidth=1.25)}

    for h in sorted(curvas):
        ep, lr = curvas[h]
        ax.plot(ep, lr, solid_capstyle="round", dash_capstyle="round", zorder=3,
                **tracos[h])

    ultima = max(float(ep.max()) for ep, _lr in curvas.values())
    ax.set_xlim(-ultima * 0.02, ultima * 1.035)
    ax.set_ylim(0, pico * 1.30)
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Learning rate")

    # Where each run ends, mark the learning rate the longer runs still have.
    marcas = []
    for acabado in sorted(curvas)[:-1]:
        fim = float(curvas[acabado][0].max())
        vivos = sorted(h for h in curvas if h > acabado)
        alto = max(float(np.interp(fim, *curvas[h])) for h in vivos)
        ax.plot([fim, fim], [0, alto], color=TINTA_FRACA, linewidth=0.6,
                linestyle=(0, (2, 2.2)), zorder=2)
        for h in vivos:
            resto = float(np.interp(fim, *curvas[h]))
            ax.plot([fim], [resto], marker="o", markersize=3.2, color=tracos[h]["color"],
                    markeredgecolor=SUPERFICIE, markeredgewidth=0.6, zorder=5)
            marcas.append(dict(acabado=acabado, horizonte=h, epoca=fim, lr=resto,
                               fracao=resto / pico))

    dx, dy = pontos_em_dados(ax, 4.2, 3.4)
    dizer_unidade = max(marcas, key=lambda m: m["lr"])
    for marca in marcas:
        rotulo = f"{100 * marca['fracao']:.0f}%"
        if marca is dizer_unidade:
            rotulo += " of peak"
        texto = ax.text(marca["epoca"] + dx, marca["lr"] + dy, rotulo,
                        ha="left", va="bottom", fontsize=6.2, color=TINTA_2, zorder=6)
        arrumar_rotulo(ax, texto, curvas, marca["horizonte"])

    return marcas, por_epoca


def main():
    args = parse_args()
    estilo()
    metas = manifesto()

    alvo = (args.modelo, args.config)
    if not all(alvo):
        alvo = com_dois_horizontes(args.fold, metas)
    h_modelo, h_config = alvo

    # One panel, narrower than --width; gravar() pads the file to the common width.
    fig, dta = plt.subplots(figsize=(args.largura_painel, args.altura))
    arrumar(dta)
    # Integer multiples of 1e-5 written in full (e.g. 3×10⁻⁵).
    dta.yaxis.set_major_locator(MultipleLocator(1e-5))
    dta.yaxis.set_major_formatter(FuncFormatter(
        lambda v, _p: "0" if v == 0 else f"{v * 1e5:g}×10⁻⁵"))

    marcas, por_epoca = painel_horizontes(dta, h_modelo, h_config, args.fold, metas)

    dta.set_title("Extending the horizon is a new run", pad=6.0)
    dta.legend(handles=[Line2D([], [], color=SERIE_1, linewidth=1.6, label="20-epoch horizon"),
                        Line2D([], [], color=SERIE_2, linewidth=1.6,
                               linestyle=(0, (4, 1.6)), label="30-epoch horizon"),
                        Line2D([], [], color=TINTA_2, linewidth=1.25,
                               linestyle=(0, (1.1, 1.7)),
                               label="40-epoch horizon (not run)")],
               loc="upper right", frameon=False, handlelength=1.5,
               labelspacing=0.32, borderaxespad=0.2)

    fig.tight_layout(w_pad=0)
    escritos = gravar(fig, args.output, largura=args.width)

    print(f"painel        {h_modelo}/{h_config} · fold {args.fold} · "
          f"{por_epoca:.0f} passos por época")
    for marca in marcas:
        print(f"  no fim do h{marca['acabado']} (época {marca['epoca']:.0f}): "
              f"h{marca['horizonte']} = {marca['lr']:.2e} "
              f"({100 * marca['fracao']:.0f}% do pico)")
    for caminho in escritos:
        print(f"escrito       {caminho}")


if __name__ == "__main__":
    main()
