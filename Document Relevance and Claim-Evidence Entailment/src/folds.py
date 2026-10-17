"""Example sets of both tasks and the cross-validation folds (3 seeds x 5 folds).

Relevance uses every claim span-document pair, entailment the annotated excerpts widened to
three-sentence windows. Folds group examples by the source article of the claim, one partition
per task.
"""

import argparse
import collections
import json
import pathlib
import random

import conjuntos as cj
import entradas as ent

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DADOS = RAIZ / "data"
SEMENTES = (42, 43, 44)
K = 5


# --------------------------------------------------------------------------------------------- #
# Examples of each task
# --------------------------------------------------------------------------------------------- #

def exemplos_relevancia(pares):
    """Relevance: every (claim span, document) pair of the partition."""
    return [dict(p, id=p["par_id"]) for p in pares]


FRASES_POR_EXCERTO = 3


def _frases_com_posicao(texto):
    """[(sentence, start, end)] over the whitespace-normalised text, plus that text.

    The normalised text is the normalised sentences joined by single spaces, so each sentence
    is found right after the previous one.
    """
    doc = " ".join((texto or "").split())
    saida, pos = [], 0
    for f in ent.frases_do(texto):
        f = " ".join(f.split())
        i = doc.find(f, pos)
        saida.append((f, i, i + len(f)))
        pos = i + len(f)
    return saida, doc


def _frases_do_excerto(excerto, frases, doc):
    """Indices of the document sentences that the annotated excerpt touches (literal search).

    Every annotated excerpt is a literal stretch of its document and touches at most three
    sentences; an excerpt that is not found or touches more stops the run.
    """
    e = " ".join((excerto or "").split())
    i = doc.find(e)
    idx = [k for k, (_, a, b) in enumerate(frases) if i >= 0 and a < i + len(e) and b > i]
    if not idx or idx[-1] - idx[0] >= FRASES_POR_EXCERTO:
        raise SystemExit(f"excerto anotado que não se localiza no documento ou que ocupa mais de "
                         f"{FRASES_POR_EXCERTO} frases: «{e[:80]}»")
    return idx


def _janela(n_frases, bloco, k=FRASES_POR_EXCERTO):
    """[start, end) of k consecutive sentences containing `bloco`, centred where possible."""
    if n_frases <= k:
        return 0, n_frases
    a, b = min(bloco), max(bloco) + 1
    if b - a >= k:
        return a, a + k
    inicio = a - (k - (b - a)) // 2
    inicio = max(0, min(inicio, n_frases - k))
    return inicio, inicio + k


def exemplos_entailment(pares):
    """Entailment: one three-sentence window per annotated excerpt, deduplicated within each
    pair."""
    saida = []
    for par in pares:
        if par["rotulo4"] == "nei_irrelevante":
            continue
        frases, doc = _frases_com_posicao(par.get("evidencia_texto") or "")
        vistos = set()
        for e in (par.get("_oraculo_excertos") or []):
            i, j = _janela(len(frases), _frases_do_excerto(e["texto"], frases, doc))
            janela = " ".join(f for f, _, _ in frases[i:j])
            if janela in vistos:
                continue
            vistos.add(janela)
            saida.append(dict(par, id=f"{par['par_id']}#j{len(vistos) - 1}",
                              evidencia_texto=janela, _oraculo_excertos=None))
    return saida


TAREFAS = {"relevance": exemplos_relevancia, "entailment": exemplos_entailment}
CLASSES_RARAS = {"relevance": ("relevante", "irrelevante"),
                 "entailment": ("refuted", "supported", "nei_relevante")}


def rotulo(exemplo, tarefa):
    if tarefa == "relevance":
        return "irrelevante" if exemplo["rotulo4"] == "nei_irrelevante" else "relevante"
    return exemplo["rotulo4"]


def por_artigo(pares):
    """Group of each claim span: the source article of its claim."""
    return {p["span_id"]: p["claim_documento"] for p in pares}


# --------------------------------------------------------------------------------------------- #
# Fold assignment
# --------------------------------------------------------------------------------------------- #

def repartir(grupos, tarefa, k, seed):
    """Assigns whole groups to k folds, greedily balancing fold size and class counts."""
    import statistics
    classes = CLASSES_RARAS[tarefa]
    conta_grupo = {gid: collections.Counter(rotulo(x, tarefa) for x in itens)
                   for gid, itens in grupos.items()}
    total = collections.Counter()
    for c in conta_grupo.values():
        total.update(c)
    alvo = {cl: max(1e-9, total[cl] / k) for cl in classes}

    rnd = random.Random(seed)
    gids = sorted(grupos)
    rnd.shuffle(gids)
    gids.sort(key=lambda g: (-statistics.pstdev([conta_grupo[g][cl] for cl in classes]),
                             -sum(conta_grupo[g].values())))

    folds = [[] for _ in range(k)]
    conta = [collections.Counter() for _ in range(k)]

    def desvio(j, c):
        """Mean over classes of the std across folds of the target-normalised counts."""
        soma = 0.0
        for cl in classes:
            valores = [conta[i][cl] / alvo[cl] for i in range(k)]
            valores[j] += c[cl] / alvo[cl]
            soma += statistics.pstdev(valores)
        return soma / len(classes)

    TOLERANCIA = 1.02
    for gid in gids:
        c = conta_grupo[gid]
        pontos = [(desvio(j, c), sum(conta[j].values()), j) for j in range(k)]
        melhor = min(p[0] for p in pontos)
        candidatas = [p for p in pontos if p[0] <= melhor * TOLERANCIA] or [min(pontos)]
        # among near-ties, the emptiest fold; the seed decides between equally empty ones
        menor = min(p[1] for p in candidatas)
        candidatas = [p for p in candidatas if p[1] == menor]
        i = rnd.choice(candidatas)[2]
        folds[i].append(gid)
        conta[i].update(c)

    # the rarest class must be in every fold: move the smallest group holding it from a fold
    # that has two or more
    rara = min(classes, key=lambda cl: total[cl])
    for _ in range(k):
        vazias = [j for j in range(k) if conta[j][rara] == 0]
        if not vazias:
            break
        j = vazias[0]
        doadoras = [(conta[i][rara], i) for i in range(k) if conta[i][rara] >= 2]
        if not doadoras:
            print(f"  AVISO: só há {sum(1 for i in range(k) if conta[i][rara])} folds com "
                  f"`{rara}` e não há como as espalhar por {k} sem esvaziar outra.")
            break
        _, doadora = max(doadoras)
        cand = [g for g in folds[doadora] if conta_grupo[g][rara] > 0]
        g = min(cand, key=lambda g: sum(conta_grupo[g].values()))
        folds[doadora].remove(g)
        conta[doadora].subtract(conta_grupo[g])
        folds[j].append(g)
        conta[j].update(conta_grupo[g])
    return [sorted(f) for f in folds]


def construir(exemplos, grupo_de, tarefa, k=K, sementes=SEMENTES):
    grupos = collections.defaultdict(list)
    for x in exemplos:
        grupos[grupo_de[x["span_id"]]].append(x)
    particoes, retratos = [], []
    for s in sementes:
        p = repartir(grupos, tarefa, k, s)
        particoes.append(p)
        retrato = []
        for j, gids in enumerate(p):
            itens = [x for gid in gids for x in grupos[gid]]
            c = collections.Counter(rotulo(x, tarefa) for x in itens)
            retrato.append({"fold": j, "n_grupos": len(gids),
                            "n_spans": len({x["span_id"] for x in itens}),
                            "n_exemplos": len(itens),
                            "classes": {cl: c.get(cl, 0) for cl in CLASSES_RARAS[tarefa]}})
        retratos.append(retrato)
    return {"tarefa": tarefa, "k": k, "sementes": list(sementes),
            "n_grupos": len(grupos), "n_exemplos": len(exemplos),
            "n_spans": len({x["span_id"] for x in exemplos}),
            "grupo_de": {s: g for s, g in sorted(grupo_de.items())},
            "particoes": particoes, "retratos": retratos}


def main():
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()

    pares = cj.pares("train")
    itens = {t: fn(pares) for t, fn in TAREFAS.items()}
    grupo_de = por_artigo(pares)
    for tarefa, lista in itens.items():
        d = construir(lista, grupo_de, tarefa)
        caminho = DADOS / f"folds_{tarefa}.json"
        caminho.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n{tarefa} -> {caminho.name}  ({d['n_grupos']} grupos · {d['n_exemplos']} "
              f"exemplos · {d['n_spans']} spans · {len(d['particoes'])}x{d['k']} folds)")
        for s, retrato in zip(SEMENTES, d["retratos"]):
            print(f"  semente {s}: " + " | ".join(
                f"f{r['fold']} {r['n_exemplos']:>4} ex "
                + " ".join(f"{k[:3]}={v}" for k, v in r["classes"].items())
                for r in retrato))


if __name__ == "__main__":
    main()
