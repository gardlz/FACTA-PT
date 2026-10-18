"""Document-level train/test split of CLEVER (40 / 100 claim spans, seed 0).

Draws the split and writes it to `split/clever_split_ids_seed0.json`: the documents and the
claim spans of each side. Every article goes whole to one side; the articles with claims are
drawn so that the training side has exactly 40 claim spans, and the articles without claims
are drawn per article, in the same proportion.

    python split_por_documento.py
"""

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from clever_claimpt import CLEVER_JSON, SPLIT, ler_json, spans_clever  # noqa: E402

# The split seed is not the training seed (42).
SEED = 0

# The claim spans of each side are listed in the order of the two files of the original CLEVER
# release (its training file, then its test file), which is the order of the prepared examples
# in data/clever/. clever.json keeps every article in one file, and clever_train.json and
# clever_test.json hold the benchmark partition instead, so the articles with claims of the
# release's test file are listed here.
ARTIGOS_DO_TESTE_ORIGINAL = {
    "clever_014.txt", "clever_016.txt", "clever_036.txt", "clever_086.txt",
    "clever_093.txt", "clever_104.txt", "clever_112.txt", "clever_121.txt",
    "clever_122.txt", "clever_135.txt", "clever_136.txt", "clever_141.txt",
    "clever_146.txt", "clever_156.txt", "clever_168.txt", "clever_178.txt",
}


def claim_spans(artigo: dict) -> list:
    """Claim span ids of an article: `<item id>`, or `<item id>_s<i>` for multi-span items."""
    return [span_id for item in artigo.get("items", []) if item.get("claim")
            for span_id, _ in spans_clever(item)]


def sortear(tamanho_por_documento: dict, alvo: int, seed: int) -> set:
    """Uniformly sample a set of documents whose sizes sum exactly to `alvo`.

    `combinacoes[i][t]` counts the subsets of documents i.. that sum to t; each document
    is then taken with probability equal to the share of the remaining solutions that
    include it, so every valid partition is equally likely.
    """
    documentos = sorted(tamanho_por_documento)
    tamanhos = [tamanho_por_documento[d] for d in documentos]
    n = len(documentos)

    combinacoes = [[0] * (alvo + 1) for _ in range(n + 1)]
    combinacoes[n][0] = 1
    for i in range(n - 1, -1, -1):
        for t in range(alvo + 1):
            dentro = combinacoes[i + 1][t - tamanhos[i]] if t >= tamanhos[i] else 0
            combinacoes[i][t] = combinacoes[i + 1][t] + dentro

    if combinacoes[0][alvo] == 0:
        raise SystemExit(f"Nenhum conjunto de documentos soma {alvo}.")

    rng = random.Random(seed)
    escolhidos, falta = set(), alvo
    for i in range(n):
        dentro = combinacoes[i + 1][falta - tamanhos[i]] if falta >= tamanhos[i] else 0
        if rng.randrange(combinacoes[i][falta]) < dentro:
            escolhidos.add(documentos[i])
            falta -= tamanhos[i]
    return escolhidos


def ids_por_ordem(artigos: list) -> list:
    """Claim span ids in the order of the original CLEVER release (training file, then test file)."""
    primeiro = [a for a in artigos if a["document"] not in ARTIGOS_DO_TESTE_ORIGINAL]
    segundo = [a for a in artigos if a["document"] in ARTIGOS_DO_TESTE_ORIGINAL]
    return [i for a in primeiro + segundo for i in claim_spans(a)]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--clever-json", default=CLEVER_JSON, help="CLEVER (default: ../CLEVER/clever.json).")
    p.add_argument("--output", default=SPLIT,
                   help="Split record to write (default: split/clever_split_ids_seed0.json).")
    p.add_argument("--seed", type=int, default=SEED)
    p.add_argument("--n-train", type=int, default=40, help="Training claim spans (default: 40).")
    p.add_argument("--n-test", type=int, default=100, help="Test claim spans (default: 100).")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    artigos = ler_json(args.clever_json)
    total = sum(len(claim_spans(a)) for a in artigos)
    if total != args.n_train + args.n_test:
        raise SystemExit(f"Há {total} claim spans, mas o split pedido soma "
                         f"{args.n_train + args.n_test}: --n-train e --n-test têm de somar {total}.")

    # Articles with claims are drawn to the exact number of claim spans; articles without
    # claims are drawn per article, in the same proportion.
    com, sem = {}, {}
    for artigo in artigos:
        n = len(claim_spans(artigo))
        (com if n else sem)[artigo["document"]] = n or 1
    alvo_sem = round(len(sem) * args.n_train / (args.n_train + args.n_test))

    docs_treino = sortear(com, args.n_train, args.seed) | sortear(sem, alvo_sem, args.seed)
    treino = [a for a in artigos if a["document"] in docs_treino]
    teste = [a for a in artigos if a["document"] not in docs_treino]
    train_ids, test_ids = ids_por_ordem(treino), ids_por_ordem(teste)

    registo = {
        "seed": args.seed,
        "split_unit": "document",
        "regra": (f"sorteio uniforme por documento sobre os {len(artigos)} artigos do CLEVER: um "
                  f"artigo vai inteiro para um dos lados. Os artigos com claims aterram em "
                  f"{args.n_train}/{args.n_test} claim spans exatos; os sem claims são "
                  f"repartidos na mesma proporção, por artigo."),
        "frozen_test": True,
        "n_artigos": len(artigos),
        "n_claim_spans": total,
        "train_size": len(train_ids),
        "test_size": len(test_ids),
        "n_artigos_train": len(treino),
        "n_artigos_test": len(teste),
        "train_documents": sorted(a["document"] for a in treino),
        "test_documents": sorted(a["document"] for a in teste),
        "train_ids": train_ids,
        "test_ids": test_ids,
        "nota": ("O teste é held-out: não usar para escolher modelos, prompts nem "
                 "hiperparâmetros. train_ids e test_ids estão pela ordem dos exemplos de "
                 "data/clever/."),
    }
    destino = Path(args.output)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(registo, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Seed: {args.seed}")
    print(f"CLEVER: {len(artigos)} artigos ({len(com)} com claims, {len(sem)} sem), "
          f"{total} claim spans")
    print(f"Treino: {len(train_ids)} claim spans de {len(com)} artigos com claims, "
          f"mais {alvo_sem} de {len(sem)} sem claims; teste: {len(test_ids)} claim spans")
    print(f"[split] escrito -> {destino}")


if __name__ == "__main__":
    main()
