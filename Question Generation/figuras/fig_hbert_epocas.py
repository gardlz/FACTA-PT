#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Figure 4.2: validation H-BERT per epoch (mean and ±1 s.d. over the 4 folds) and the
selected epoch, for four models under Gold91+Silver1073.

    python figuras/fig_hbert_epocas.py
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum_qg import (SERIE_1, TINTA_2, TINTA_FRACA, SUPERFICIE, LARGURA, CONFIG_PRINCIPAL,
                      estilo, arrumar, titulo_painel, ler_agregado,
                      ler_melhores, curva, gravar)   # noqa: E402

MODELOS_POR_OMISSAO = ["ptt5_large", "mt0_large", "gloria_1b3", "mt0_xxl"]
CONFIG_POR_OMISSAO = CONFIG_PRINCIPAL


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--modelos", default=",".join(MODELOS_POR_OMISSAO),
                   help="Comma-separated models. Default: %(default)s")
    p.add_argument("--config", default=CONFIG_POR_OMISSAO,
                   help="Supervision configuration of every panel. Default: %(default)s")
    p.add_argument("--colunas", type=int, default=2, help="Panels per row. Default: %(default)s")
    p.add_argument("--output", default="figuras/hbert_epocas.pdf",
                   help="Output file (.pdf; a .png is written next to it). Default: %(default)s")
    p.add_argument("--width", type=float, default=LARGURA, help="Width in inches.")
    p.add_argument("--altura-painel", type=float, default=1.75, dest="altura_painel",
                   help="Height of each panel, in inches.")
    return p.parse_args()


def combinacoes(args):
    modelos = [m.strip() for m in args.modelos.split(",") if m.strip()]
    return [(m, args.config) for m in modelos]


def painel(ax, g, melhor):
    """One combination: the mean, the across-fold band and the selected epoch."""
    ep = g.epoch.values
    media = g.mean_h_bert.values
    desvio = g.std_h_bert.values

    ax.fill_between(ep, media - desvio, media + desvio, color=SERIE_1, alpha=0.14,
                    linewidth=0, zorder=1)
    ax.plot(ep, media, color=SERIE_1, linewidth=1.5, marker="o", markersize=2.4,
            markeredgecolor=SUPERFICIE, markeredgewidth=0.35, solid_capstyle="round",
            zorder=3)

    escolhida = int(melhor["best_epoch"])
    onde = np.flatnonzero(ep == escolhida)
    if not len(onde):
        sys.exit(f"época {escolhida} não existe no agregado desta combinação (vai até "
                 f"{int(ep.max())}): o best_epochs.csv e o agregado_por_epoca.csv são de "
                 f"execuções diferentes; os dois são escritos pelo aggregate_folds.py.")
    i = int(onde[0])
    ax.axvline(escolhida, color=TINTA_2, linewidth=0.7, linestyle=(0, (3, 2)), zorder=4)
    ax.plot([escolhida], [media[i]], marker="o", markersize=5.0, color=SERIE_1,
            markeredgecolor=SUPERFICIE, markeredgewidth=1.0, zorder=6, clip_on=False)

    # When the selected epoch is not the argmax, draw the tolerance line (max - 0.05).
    argmax = int(ep[int(np.argmax(media))])
    if argmax != escolhida:
        ax.axhline(media.max() - 0.05, color=TINTA_FRACA, linewidth=0.5,
                   linestyle=(0, (1, 2)), zorder=2)

    lo, hi = float(np.min(media - desvio)), float(np.max(media + desvio))
    folga = max(1.0, (hi - lo) * 0.08)
    ax.set_ylim(lo - folga, hi + folga)
    ax.set_xlim(0.4, ep.max() + 0.6)
    ax.set_xticks([1] + list(range(5, int(ep.max()) + 1, 5)))

    # Label beside the dashed line, on the side with more room, pushed into the panel.
    fracao = escolhida / ep.max()
    if fracao > 0.5:
        ha, dx = "right", -3
    else:
        ha, dx = "left", 3
    rotulo = ax.annotate(f"epoch {escolhida} · {media[i]:.1f}",
                         xy=(escolhida, media[i]), xytext=(dx, 8),
                         textcoords="offset points", ha=ha, va="bottom",
                         fontsize=6.4, color=TINTA_2, zorder=7)
    return escolhida, argmax, rotulo


def abrir_folga(fig, rotulos, margem=3.0):
    """Raise each panel's top just enough for its label (two passes, the label moves)."""
    for _ in range(2):
        fig.canvas.draw()
        for ax, rotulo in rotulos:
            caixa_ax = ax.get_window_extent()
            caixa_txt = rotulo.get_window_extent()
            excesso = caixa_txt.y1 + margem - caixa_ax.y1
            if excesso <= 0:
                continue
            base, topo = ax.get_ylim()
            ax.set_ylim(base, topo + excesso * (topo - base) / caixa_ax.height)


def main():
    args = parse_args()
    estilo()
    agregado, melhores = ler_agregado(), ler_melhores()
    pares = combinacoes(args)

    if not pares:
        sys.exit("Nenhum painel a desenhar: --modelos está vazio.")
    if args.colunas < 1:
        sys.exit("--colunas tem de ser >= 1.")

    colunas = min(args.colunas, len(pares))
    linhas = int(np.ceil(len(pares) / colunas))
    fig, eixos = plt.subplots(linhas, colunas, squeeze=False,
                              figsize=(args.width, args.altura_painel * linhas + 0.78))

    com_tolerancia, rotulos = False, []
    for k, (modelo, config) in enumerate(pares):
        ax = eixos[k // colunas][k % colunas]
        arrumar(ax)
        g = curva(agregado, modelo, config)
        if (modelo, config) not in melhores.index:
            sys.exit(f"{modelo}/{config} não está no best_epochs.csv")
        escolhida, argmax, rotulo = painel(ax, g, melhores.loc[(modelo, config)])
        titulo_painel(ax, modelo)
        rotulos.append((ax, rotulo))
        com_tolerancia = com_tolerancia or argmax != escolhida

    for k in range(len(pares), linhas * colunas):     # unused cells of the grid
        eixos[k // colunas][k % colunas].set_visible(False)

    for i in range(linhas):
        eixos[i][0].set_ylabel("Validation H-BERT")
    for j in range(colunas):
        for i in range(linhas):
            if eixos[i][j].get_visible():
                ultimo = i
        eixos[ultimo][j].set_xlabel("Epoch")

    legenda = [
        Line2D([], [], color=SERIE_1, linewidth=1.8, label="Mean over the 4 folds"),
        Patch(facecolor=SERIE_1, alpha=0.14, label="± 1 s.d. across folds"),
        Line2D([], [], color=TINTA_2, linewidth=0.7, linestyle=(0, (3, 2)),
               label="Selected epoch"),
    ]
    # The tolerance line has a legend entry only when some panel draws it.
    if com_tolerancia:
        legenda.append(Line2D([], [], color=TINTA_FRACA, linewidth=0.5,
                              linestyle=(0, (1, 2)),
                              label="Max − 0.05 (selection tolerance)"))
    fig.legend(handles=legenda, loc="lower center", ncol=len(legenda),
               bbox_to_anchor=(0.5, -0.035), frameon=False, handlelength=1.9,
               columnspacing=1.8, numpoints=1)

    fig.tight_layout(h_pad=2.6, w_pad=1.4)
    abrir_folga(fig, rotulos)
    escritos = gravar(fig, args.output, largura=args.width)

    for caminho in escritos:
        print(f"escrito       {caminho}")


if __name__ == "__main__":
    main()
