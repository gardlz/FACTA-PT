#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared data loading, model names and style for the question-generation figures.

The curves come from the files written by the training scripts (`agregado_por_epoca.csv`,
`best_epochs.csv`, `*lr_por_step.jsonl`) and the model metadata from models_manifest.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def achar_raiz(inicio: Path) -> Path:
    """The repository folder (the first ancestor that contains `qg_kfold/`)."""
    for base in [inicio, *inicio.parents]:
        if (base / "qg_kfold").is_dir():
            return base
    raise SystemExit(
        f"Pasta `qg_kfold` inexistente acima de {inicio}.\n"
        f"As figuras leem os resultados de lá e correm a partir do repositório.")


QG = achar_raiz(Path(__file__).resolve().parent)
RESULTADOS = QG / "qg_kfold" / "runs" / "v3" / "results"
AGREGADO = RESULTADOS / "agregado_por_epoca.csv"
MELHORES = RESULTADOS / "best_epochs.csv"
MANIFESTO = QG / "qg_kfold" / "configs" / "models_manifest.json"

# Palette: two categorical series colours and neutral inks for annotations.
SERIE_1 = "#2a78d6"
SERIE_2 = "#eb6834"

TINTA = "#0b0b0b"
TINTA_2 = "#52514e"
TINTA_FRACA = "#898781"
GRELHA = "#e1e0d9"
EIXO = "#c3c2b7"
SUPERFICIE = "#ffffff"

LARGURA = 6.3            # inches, the text width of the dissertation

# Display names (the manifest short names are file identifiers).
NOMES = {
    "ptt5_large": "PTT5 Large",
    "ptt5v2_large": "PTT5-v2 Large",
    "tucano_1b1": "Tucano-1b1-Instruct",
    "llama32_1b": "Llama 3.2-1B-Instruct",
    "mt0_large": "mT0 Large",
    "gloria_1b3": "GlórIA-1.3B",
    "ptt5v2_3b": "PTT5-v2 3B",
    "mt5_xl": "mT5 XL",
    "bode_7b": "Bode-7B-Alpaca",
    "gervasio_8b": "Gervásio-8B PT-PT",
    "llama_8b": "Llama 3.1-8B-Instruct",
    "amalia_9b": "AMALIA-9B-0626-DPO",
    "mistral_nemo": "Mistral NeMo-12B",
    "mt0_xxl": "mT0 XXL",
}

# Supervision configurations, in the order of the dissertation, and their names there.
CONFIGS = {
    "human40":           "Gold91",
    "human40_silver25":  "Gold91+Silver266",
    "human40_silver50":  "Gold91+Silver535",
    "human40_silver75":  "Gold91+Silver802",
    "human40_silver100": "Gold91+Silver1073",
    "silver100":         "Silver1073",
}

CONFIG_PRINCIPAL = "human40_silver100"


def estilo():
    """Common rcParams; call before creating the figure."""
    plt.rcParams.update({
        "figure.dpi": 300,
        "savefig.dpi": 300,
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 7.2,
        "axes.titlesize": 7.6,
        "axes.labelsize": 7.4,
        "xtick.labelsize": 6.6,
        "ytick.labelsize": 6.6,
        "legend.fontsize": 6.9,
        "axes.edgecolor": EIXO,
        "axes.linewidth": 0.6,
        "axes.labelcolor": TINTA_2,
        "axes.titlecolor": TINTA,
        "text.color": TINTA,
        "xtick.color": TINTA_FRACA,
        "ytick.color": TINTA_FRACA,
        "xtick.labelcolor": TINTA_2,
        "ytick.labelcolor": TINTA_2,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "xtick.major.size": 2.4,
        "ytick.major.size": 2.4,
        "grid.color": GRELHA,
        "grid.linewidth": 0.5,
        "legend.frameon": False,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.facecolor": SUPERFICIE,
        "axes.facecolor": SUPERFICIE,
        "pdf.fonttype": 42,      # TrueType: searchable text in the PDF
        "ps.fonttype": 42,
    })


def arrumar(ax, grelha="y"):
    """Light grid and clean spines."""
    ax.set_axisbelow(True)
    if grelha:
        ax.grid(axis=grelha, color=GRELHA, linewidth=0.5, zorder=0)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(EIXO)


def manifesto():
    """{short_name: metadata} from models_manifest.json."""
    dados = json.loads(MANIFESTO.read_text(encoding="utf-8"))
    return {m["short_name"]: m for m in dados["modelos"]}


def titulo_painel(ax, short_name):
    """Panel title: the model's display name."""
    ax.set_title(NOMES.get(short_name, short_name), pad=6.0)


def ler_agregado():
    """Per-epoch curves averaged over the 4 folds (written by aggregate_folds.py)."""
    import pandas as pd
    if not AGREGADO.exists():
        raise SystemExit(
            f"Falta {AGREGADO}.\nEste ficheiro é produzido pelo "
            f"qg_kfold/scripts/aggregate_folds.py.")
    return pd.read_csv(AGREGADO)


def ler_melhores():
    """Selected epoch per combination, indexed by (model, configuration)."""
    import pandas as pd
    if not MELHORES.exists():
        raise SystemExit(f"Falta {MELHORES}. Ver a nota em ler_agregado().")
    return pd.read_csv(MELHORES).set_index(["modelo", "config"])


def curva(agregado, modelo, config):
    """Epochs of one combination, sorted; a clear error if it does not exist."""
    g = agregado[(agregado.modelo == modelo) & (agregado.config == config)]
    if g.empty:
        combos = sorted(set(zip(agregado.modelo, agregado.config)))
        raise SystemExit(f"Sem curva para {modelo}/{config}. "
                         f"Há {len(combos)} combinações; ex.: {combos[:3]}")
    return g.sort_values("epoch")


def caixa_a_largura(fig, largura=LARGURA):
    """Tight bounding box widened to an exact width, so every figure scales alike in LaTeX."""
    from matplotlib.transforms import Bbox
    caixa = fig.get_tightbbox(fig.canvas.get_renderer()).padded(0.02)
    se_falta = (largura - caixa.width) / 2.0
    if se_falta <= 0:
        return caixa
    return Bbox([[caixa.x0 - se_falta, caixa.y0], [caixa.x1 + se_falta, caixa.y1]])


def gravar(fig, destino, tambem_png=True, largura=LARGURA):
    """Write the PDF and, next to it, a PNG preview."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    fig.canvas.draw()
    caixa = caixa_a_largura(fig, largura)
    escritos = [destino]
    fig.savefig(destino, bbox_inches=caixa, facecolor=SUPERFICIE)
    if tambem_png and destino.suffix.lower() == ".pdf":
        png = destino.with_suffix(".png")
        fig.savefig(png, bbox_inches=caixa, facecolor=SUPERFICIE)
        escritos.append(png)
    return escritos
