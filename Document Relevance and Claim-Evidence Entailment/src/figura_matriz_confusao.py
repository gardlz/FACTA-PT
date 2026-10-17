"""Confusion matrix of the XLM-R-large-XNLI entailment final run (Figure 6.3 of the dissertation).

Counts in the cells, colour by share of the gold class. Reads the matrix stored in
outputs/final/entailment__xlmr_large_xnli_resultado.json and writes
outputs/figuras/matriz_confusao_entailment_xlmr_large_xnli.png and .pdf.
"""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
FINAL = RAIZ / "outputs/final"
CLASSES = ("supported", "refuted", "nei_relevante")
ROTULOS = ("Supported", "Refuted", "NEI")
MODELO, TITULO = "xlmr_large_xnli", "XLM-R-large-XNLI"


def matriz(modelo, pasta):
    resultado = pasta / f"entailment__{modelo}_resultado.json"
    if not resultado.exists():
        ha = sorted(p.name[len("entailment__"):-len("_resultado.json")]
                    for p in pasta.glob("entailment__*_resultado.json"))
        raise SystemExit(f"não há treino final de {modelo} em {pasta} "
                         f"(há: {', '.join(ha) or 'nenhum'})")
    r = json.loads(resultado.read_text(encoding="utf-8"))
    m = r["matriz_de_confusao"]
    M = np.array([[m[v][p] for p in CLASSES] for v in CLASSES])
    return M, r["resultado"]["macro_f1"]


def desenhar(M, titulo, saida):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "pdf.fonttype": 42, "ps.fonttype": 42})
    fig, eixo = plt.subplots(figsize=(4.7, 3.4), constrained_layout=True)
    prop = M / M.sum(axis=1, keepdims=True)
    imagem = eixo.imshow(prop, cmap="Blues", vmin=0, vmax=1)
    for a in range(3):
        for b in range(3):
            cor = "white" if prop[a, b] > 0.55 else "black"
            eixo.text(b, a - 0.1, str(M[a, b]), ha="center", va="center", color=cor,
                      fontsize=13, fontweight="bold")
            eixo.text(b, a + 0.24, f"{100 * prop[a, b]:.0f}%", ha="center", va="center",
                      color=cor, fontsize=8)
    eixo.set_title(titulo, fontsize=10.5, pad=8)
    eixo.set_xticks(range(3), ROTULOS)
    eixo.set_yticks(range(3), [f"{r} ({t})" for r, t in zip(ROTULOS, M.sum(axis=1))])
    eixo.set_xlabel("Predicted label")
    eixo.set_ylabel("Gold label")
    eixo.tick_params(length=0)
    for lado in eixo.spines.values():
        lado.set_visible(False)
    # interior grid lines only; edge lines would leave a one-pixel column of the matrix outside
    eixo.set_xticks([0.5, 1.5], minor=True)
    eixo.set_yticks([0.5, 1.5], minor=True)
    eixo.grid(which="minor", color="white", linewidth=1.5)
    eixo.tick_params(which="minor", length=0)
    barra = fig.colorbar(imagem, ax=eixo, shrink=0.95, fraction=0.06, pad=0.03)
    barra.set_label("Share of the gold class")
    barra.set_ticks([0, 0.25, 0.5, 0.75, 1], labels=["0%", "25%", "50%", "75%", "100%"])
    # freeze the layout so the PNG and the PDF get the same geometry
    fig.canvas.draw()
    fig.set_layout_engine("none")
    saida.parent.mkdir(parents=True, exist_ok=True)
    for extensao in (".png", ".pdf"):
        fig.savefig(saida.with_suffix(extensao), dpi=300, bbox_inches="tight")


def main():
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    M, macro = matriz(MODELO, FINAL)
    saida = RAIZ / "outputs/figuras" / f"matriz_confusao_entailment_{MODELO}"
    desenhar(M, TITULO, saida)
    print(f"{TITULO}: macro-F1 {macro:.4f} · "
          f"matriz {M.tolist()}\nescrito {saida.relative_to(RAIZ)}.png e .pdf")


if __name__ == "__main__":
    main()
