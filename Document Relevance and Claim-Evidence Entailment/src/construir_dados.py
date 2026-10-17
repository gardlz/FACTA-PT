"""Builds the claim span-document pairs read by the experiments, from the CLEVER evidence annotations.

Reads CLEVER at the root of the repository (clever.json and the two partitions, clever_train.json
and clever_test.json) and writes data/pares.jsonl. The train/test split is the one given by the two
partition files.
"""

import argparse
import collections
import json
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DADOS = RAIZ / "data"
CLEVER = RAIZ.parent / "CLEVER"

ROTULOS = {"Supported": "supported", "Refuted": "refuted", "NEI": "nei", None: "nei"}
CLASSES4 = ("supported", "refuted", "nei_relevante", "nei_irrelevante")


def ler_json(caminho):
    caminho = pathlib.Path(caminho)
    if not caminho.exists():
        raise SystemExit(f"falta {caminho}: o CLEVER fica na raiz do repositório (ver o README)")
    return json.loads(caminho.read_text(encoding="utf-8"))


def spans_do_clever(artigos):
    """(article, item, claim span id, claim span) of every claim span; the id is the item id, or
    `<item id>_s<i>` for multi-span items."""
    for artigo in artigos:
        for item in artigo.get("items", []):
            if not item.get("claim"):
                continue
            spans = item["claim_span"] if isinstance(item["claim_span"], list) else [item["claim_span"]]
            for i, span in enumerate(spans):
                yield artigo, item, item["id"] if len(spans) == 1 else f"{item['id']}_s{i}", span


def particao_herdada(clever):
    """{claim span id: "train" | "test"}, read from the two partition files."""
    treino = {sid for _, _, sid, _ in spans_do_clever(ler_json(clever / "clever_train.json"))}
    teste = {sid for _, _, sid, _ in spans_do_clever(ler_json(clever / "clever_test.json"))}
    if treino & teste:
        raise SystemExit(f"{len(treino & teste)} spans nas duas partições do CLEVER")
    return {s: "train" for s in treino} | {s: "test" for s in teste}


def construir(clever):
    """One line per pair, claim spans by id."""
    spans = sorted(spans_do_clever(ler_json(clever / "clever.json")), key=lambda x: x[2])
    particao = particao_herdada(clever)
    if set(particao) != {sid for _, _, sid, _ in spans}:
        raise SystemExit("a partição herdada não cobre os claim spans do clever.json")

    linhas = []
    for artigo, item, sid, span in spans:
        for doc in span["retrieved_documents"]:
            doc_id = str(doc["doc_id"])
            rotulo = ROTULOS[doc["relation"]]
            relevancia = "relevante" if doc.get("relevant") else "irrelevante"
            linhas.append({
                "par_id": f"{sid}::{doc_id}",
                "span_id": sid,
                "doc_id": doc_id,
                "claim_id": item["id"],
                "particao": particao[sid],
                "rotulo4": rotulo if rotulo != "nei" else f"nei_{relevancia}",
                "claim_span": span["text"],
                "claim_documento": artigo["document"],
                "titulo": doc.get("headline"),
                "evidencia_texto": doc["content"],
                # annotated excerpts: used only to build the entailment windows, never as model
                # input
                "_oraculo_excertos": [{"texto": e["text"]} for e in doc["evidence_excerpts"]],
            })
    return linhas


def imprimir_composicao(linhas):
    """Claims, claim spans, pairs per label and annotated excerpts per label, per partition."""
    for nome in ("train", "test", "total"):
        sub = [l for l in linhas if nome == "total" or l["particao"] == nome]
        pares = collections.Counter(l["rotulo4"] for l in sub)
        excertos = collections.Counter(l["rotulo4"] for l in sub for _ in l["_oraculo_excertos"])
        print(f"{nome}: {len({l['claim_id'] for l in sub})} claims · "
              f"{len({l['span_id'] for l in sub})} claim spans · {len(sub)} pares")
        print("   pares:    " + " · ".join(f"{k} {pares.get(k, 0)}" for k in CLASSES4))
        print("   excertos: " + " · ".join(f"{k} {excertos.get(k, 0)}" for k in CLASSES4)
              + f" · total {sum(excertos.values())}")


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--clever", type=pathlib.Path, default=CLEVER,
                   help="CLEVER folder (default: ../CLEVER): clever.json, clever_train.json "
                        "and clever_test.json")
    args = p.parse_args()

    linhas = construir(args.clever)
    DADOS.mkdir(parents=True, exist_ok=True)
    ficheiro = DADOS / "pares.jsonl"
    ficheiro.write_text("".join(json.dumps(l, ensure_ascii=False) + "\n" for l in linhas),
                        encoding="utf-8")
    print(f"{len(linhas)} pares -> {ficheiro}")
    imprimir_composicao(linhas)


if __name__ == "__main__":
    main()
