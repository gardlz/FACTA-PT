#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Figure 4.1: the ±1-sentence context of a claim span inside its article.

Finds the claim span in the prepared CLEVER data, marks the ±1-sentence window the models
receive (the window of `model_utils.claim_context`, from the same sentence splitter) and draws
the article excerpt; with --ner the spaCy entities (PER/ORG/LOC/MISC, pt_core_news_lg) are
coloured and underlined.

    python figuras/fig_contexto.py --claim "<claim span>" --ner
"""
import argparse
import json
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum_qg import achar_raiz, caixa_a_largura   # noqa: E402

RAIZ = achar_raiz(Path(__file__).resolve().parent)
sys.path.insert(0, str(RAIZ / "src"))
from model_utils import split_sentences, _find_span   # noqa: E402

# spaCy labels counted as named entities (PER, ORG, LOC, MISC; Section 4.2.3).
ETIQUETAS = {"PER", "ORG", "LOC", "MISC"}

FICHEIROS = ["data/clever/clever_all.jsonl",
             "data/clever/clever_train_40.jsonl",
             "data/clever/clever_test_100.jsonl"]

CTX_COLOR, CLAIM_COLOR = "#CFE3F5", "#F5C777"
OUT_COLOR, IN_COLOR = "#8A8A8A", "#1A1A1A"
LEGEND = [("Context (±1 sentence window)", CTX_COLOR, "none"),
          ("Claim span", CLAIM_COLOR, "none"),
          ("Rest of the article — not given to the model", "white", "#C8C8C8")]

# One colour and one dash pattern per label, so the marks also survive greyscale printing.
COR_NER = {"PER": "#A6272E", "ORG": "#1B5E9E", "LOC": "#1E7A46", "MISC": "#7B3F9E"}
ESTILO_NER = {"PER": "solid", "ORG": (0, (3.2, 1.2)),
              "LOC": (0, (1.6, 1.2)), "MISC": (0, (0.5, 1.1))}
NOME_NER = {"PER": "PER — person", "ORG": "ORG — organisation",
            "LOC": "LOC — location", "MISC": "MISC — other"}


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--claim", required=True,
                   help="Claim span text. Exact match, or a substring of one.")
    p.add_argument("--output", default="figuras/contexto.pdf",
                   help="Output image (.pdf for LaTeX, .png to preview). Default: %(default)s")
    p.add_argument("--padding", type=int, default=2,
                   help="Sentences shown before AND after the context, to centre it. Default: %(default)s")
    p.add_argument("--width", type=float, default=6.3, help="Figure width in inches (~16 cm).")
    p.add_argument("--fontsize", type=float, default=9.2, help="Body font size in points.")
    p.add_argument("--ner", action="store_true",
                   help="Colour and underline the named entities (spaCy).")
    p.add_argument("--spacy_model", default="pt_core_news_lg",
                   help="NER model. Default: %(default)s")
    return p.parse_args()


def entidades_por_caractere(artigo, modelo):
    """char -> (entity id, label) in article coordinates; NER runs on the whole article."""
    try:
        import spacy
    except ImportError:
        sys.exit("--ner needs spaCy, which is not installed:  pip install spacy")
    try:
        nlp = spacy.load(modelo, disable=["lemmatizer", "textcat"])
    except OSError:
        sys.exit(f"spaCy model {modelo!r} unavailable. "
                 f"Install it with: python -m spacy download {modelo}")
    por_char, spans = {}, []
    for k, ent in enumerate(e for e in nlp(artigo).ents if e.label_ in ETIQUETAS):
        spans.append((ent.start_char, ent.end_char, ent.label_))
        for i in range(ent.start_char, ent.end_char):
            por_char[i] = (k, ent.label_)
    return por_char, spans


def procurar(claim):
    """Find the example whose claim_span matches. Exact match wins over substring."""
    alvo = " ".join(claim.split()).casefold()
    vistos, exatos, parciais = set(), [], []
    for nome in FICHEIROS:
        caminho = RAIZ / nome
        if not caminho.exists():
            continue
        for linha in caminho.read_text(encoding="utf-8").splitlines():
            if not linha.strip():
                continue
            ex = json.loads(linha)
            if ex.get("id") in vistos or not ex.get("claim_span") or not ex.get("context"):
                continue
            vistos.add(ex["id"])
            span = " ".join(ex["claim_span"].split()).casefold()
            if span == alvo:
                exatos.append(ex)
            elif alvo in span or span in alvo:
                parciais.append(ex)
    return exatos or parciais


def main():
    args = parse_args()
    achados = procurar(args.claim)
    if not achados:
        sys.exit(f"No claim span matching {args.claim!r} was found in {', '.join(FICHEIROS)}.")
    if len(achados) > 1:
        print(f"[warning] {len(achados)} matches; using the first:")
        for ex in achados:
            print(f"          {ex['id']}: {ex['claim_span']}")
    ex = achados[0]

    artigo = ex["context"]
    frases = split_sentences(artigo)
    ini, fim = _find_span(artigo, ex["claim_span"])
    toca = [i for i, (a, b) in enumerate(frases) if a < fim and b > ini]
    lo, hi = max(0, toca[0] - 1), min(len(frases) - 1, toca[-1] + 1)     # ±1 sentence
    c0, c1 = frases[lo][0], frases[hi][1]
    # Align the highlight with claim_context, which strips the window.
    while c0 < c1 and artigo[c0].isspace():
        c0 += 1
    while c1 > c0 and artigo[c1 - 1].isspace():
        c1 -= 1

    # Shown excerpt: `padding` sentences on each side of the context.
    v0, v1 = max(0, lo - args.padding), min(len(frases) - 1, hi + args.padding)
    inicio, corte = frases[v0][0], frases[v1][1]
    texto = artigo[inicio:corte]
    antes, depois = v0, len(frases) - 1 - v1

    ner, ents = ({}, [])
    if args.ner:
        ner, ents = entidades_por_caractere(artigo, args.spacy_model)

    def cat(i):
        i += inicio
        return "claim" if ini <= i < fim else ("context" if c0 <= i < c1 else "out")

    def ent(i):
        return ner.get(i + inicio)                    # (id, label) or None

    def chave(i):
        return cat(i), ent(i)

    # Pieces split at category and entity boundaries.
    pecas = []
    for m in re.finditer(r"\S+", texto):
        a, ult = m.start(), m.start()
        for i in range(m.start() + 1, m.end() + 1):
            if i == m.end() or chave(i) != chave(ult):
                pecas.append((texto[a:i], cat(a), ent(a), a, i))
                a = i
            ult = i

    W, FS = args.width, args.fontsize
    h_lin = FS * 1.62 / 72
    fig = plt.figure(figsize=(W, 4), dpi=300)
    rend = fig.canvas.get_renderer()

    def larg(txt, negrito):
        t = fig.text(0, 0, txt, fontsize=FS, family="DejaVu Sans",
                     fontweight="bold" if negrito else "normal")
        w = t.get_window_extent(rend).width / fig.dpi
        t.remove()
        return w

    ESPACO, X0 = larg(" ", False), 0.10
    linhas, linha, x, fim_ant = [], [], X0, None
    for txt, c, e, a, b in pecas:
        w = larg(txt, c == "claim")
        colada = bool(linha) and fim_ant == a       # contiguous in the original text
        if x + (w if colada else w + ESPACO) > W - X0 and linha:
            linhas.append(linha)
            linha, x, colada = [], X0, False
        if linha and not colada:
            x += ESPACO
        linha.append((txt, c, e, x))
        x += w
        fim_ant = b
    linhas.append(linha)
    plt.close(fig)

    # Legend entries only for the labels visible in the drawn excerpt.
    a_vista = {lab for a, b, lab in ents if a < corte and b > inicio}
    legenda = [Patch(fc=f, ec=e, label=l) for l, f, e in LEGEND]
    presentes = [x for x in ("PER", "ORG", "LOC", "MISC") if x in a_vista]
    legenda += [Line2D([0], [0], color=COR_NER[x], lw=1.6, linestyle=ESTILO_NER[x],
                       label=NOME_NER[x]) for x in presentes]

    n_marcas = bool(antes) + bool(depois)
    alt = 0.14 + (len(linhas) + n_marcas) * h_lin + 0.20 + len(legenda) * 0.175 + 0.10
    fig = plt.figure(figsize=(W, alt), dpi=300)
    fig.patch.set_facecolor("white")
    P = lambda pol: pol / alt                                    # noqa: E731

    def elisao(y, n, lado):
        fig.text(X0 / W, P(y), f"[… {n} {'sentence' if n == 1 else 'sentences'} {lado} …]",
                 fontsize=FS - 0.7, color=OUT_COLOR, style="italic",
                 va="baseline", ha="left", family="DejaVu Sans")

    y, desenhadas = alt - 0.14 - h_lin * 0.75, []
    if antes:
        elisao(y, antes, "before, not shown")
        y -= h_lin
    for linha in linhas:
        for txt, c, e, x in linha:
            t = fig.text(x / W, P(y), txt, fontsize=FS, family="DejaVu Sans", zorder=3,
                         color=COR_NER[e[1]] if e is not None else
                         (OUT_COLOR if c == "out" else IN_COLOR),
                         fontweight="bold" if c == "claim" else "normal",
                         va="baseline", ha="left")
            desenhadas.append((t, c, e, y))
        y -= h_lin
    if depois:
        elisao(y, depois, "after, not shown")

    # Highlight rectangles from the measured boxes of the drawn text.
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    inv = fig.transFigure.inverted()

    def corridas_de(chave_de):
        """Merge contiguous boxes on the same line that share a key."""
        saida = []
        for t, c, e, yl in desenhadas:
            k = chave_de(c, e)
            cx = t.get_window_extent(rend)
            x0, x1 = inv.transform((cx.x0, 0))[0], inv.transform((cx.x1, 0))[0]
            if k is not None and saida and saida[-1][0] == k and saida[-1][3] == yl:
                saida[-1][2] = x1
            else:
                saida.append([k, x0, x1, yl])
        return saida

    for c, x0, x1, yl in corridas_de(lambda c, e: c):
        if c == "out":
            continue
        fig.add_artist(Rectangle((x0 - 0.0035, P(yl - h_lin * 0.24)),
                                 (x1 - x0) + 0.007, P(h_lin * 0.90), zorder=1,
                                 fc=CLAIM_COLOR if c == "claim" else CTX_COLOR,
                                 ec="none", transform=fig.transFigure))

    # Entity underline above the background and below the text, keyed by entity id so
    # two adjacent entities with the same label keep separate underlines.
    for k, x0, x1, yl in corridas_de(lambda c, e: e[0] if e else None):
        if k is None:
            continue
        etiqueta = next(e[1] for t, c, e, y in desenhadas if e and e[0] == k)
        fig.add_artist(Line2D([x0, x1], [P(yl - h_lin * 0.20)] * 2, zorder=2,
                              color=COR_NER[etiqueta], linewidth=1.15,
                              linestyle=ESTILO_NER[etiqueta], solid_capstyle="butt",
                              dash_capstyle="butt", transform=fig.transFigure))

    leg = fig.legend(handles=legenda,
                     loc="lower left", bbox_to_anchor=(X0 / W, P(0.10)), frameon=False,
                     fontsize=FS - 1.0, handlelength=1.6, handleheight=1.05,
                     labelspacing=0.5)
    for txt_leg, etq in zip(leg.get_texts()[len(LEGEND):], presentes):
        txt_leg.set_color(COR_NER[etq])

    # Same exact width as the other figures; a PNG is written next to the PDF.
    destino = Path(args.output)
    destino.parent.mkdir(parents=True, exist_ok=True)
    fig.canvas.draw()
    caixa = caixa_a_largura(fig, args.width)
    escritos = [destino]
    fig.savefig(destino, bbox_inches=caixa, facecolor="white")
    if destino.suffix.lower() == ".pdf":
        png = destino.with_suffix(".png")
        fig.savefig(png, bbox_inches=caixa, facecolor="white")
        escritos.append(png)
    for caminho in escritos:
        print(f"written       {caminho}")


if __name__ == "__main__":
    main()
