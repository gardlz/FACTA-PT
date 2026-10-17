"""Builds the pipeline inputs from CLEVER, the fixed document-level split and ClaimPT.

CLEVER: one example per claim span, with the full article in `context` (windowed later by
`model_utils.claim_context`), in the order of the split record. ClaimPT silver: the claim spans
of claimpt_train.json and claimpt_test.json with their silver questions, concatenated,
de-duplicated and sampled into nested 25/50/75/100% subsets (seed 42). Prints the counts of
Tables 3.7 and 4.8.

    python src/prepare_data.py
"""

import argparse
import random
import re
from collections import Counter
from pathlib import Path

from clever_claimpt import (CLAIMPT_ARTIGOS, CLAIMPT_JSON, CLEVER_ARTIGOS, CLEVER_JSON, SPLIT,
                            ler_json, unidades_silver)
from io_utils import _clean, as_text_list, dedup, normalize_example, write_jsonl

SRC_DIR = Path(__file__).resolve().parent
ROOT = SRC_DIR.parent

PT_MONTHS = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
             "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}


def normalize_date(value) -> str:
    """'05 mai 2025' / '2023-12-04' -> ISO YYYY-MM-DD (or the original value)."""
    text = _clean(value).lower()
    m = re.match(r"^(\d{1,2})\s+([a-zç]{3})\s+(\d{4})$", text)
    if m and PT_MONTHS.get(m.group(2)):
        return f"{int(m.group(3)):04d}-{PT_MONTHS[m.group(2)]:02d}-{int(m.group(1)):02d}"
    return _clean(value)


def read_article(articles_dir: Path, document: str) -> str:
    path = articles_dir / document
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def flatten_clever(articles: list, articles_dir: Path) -> list:
    """CLEVER articles (article -> items -> claim_span) -> one example per claim span.

    The id is the item id, or `<id>_s<i>` when the item has several spans.
    """
    out, sem_artigo = [], 0
    for article in articles:
        document = article.get("document", "")
        context = read_article(articles_dir, document)
        sem_artigo += 0 if context else 1
        pub = normalize_date(article.get("publication_time"))

        for item in article.get("items", []):
            if not item.get("claim"):
                continue
            spans = item.get("claim_span")
            spans = spans if isinstance(spans, list) else [spans] if spans else []
            claimers = as_text_list(item.get("claimer"))
            objects = as_text_list(item.get("claim_object"))
            claim_time = " / ".join(as_text_list(item.get("time")))

            for i, span in enumerate(spans):
                if not isinstance(span, dict):
                    continue
                text = _clean(span.get("text"))
                if not text:
                    continue
                sid = item.get("id", "")
                out.append({
                    "id": sid if len(spans) == 1 else f"{sid}_s{i}",
                    "claim_span": text,
                    "context": context,
                    "publication_time": pub,
                    "claim_time": claim_time,
                    "claimers": claimers,
                    "claim_objects": objects,
                    "reference_questions": as_text_list(span.get("questions")),
                    "document": document,
                    "source": "clever",
                })
    if sem_artigo:
        raise SystemExit(f"[clever] {sem_artigo} artigos do CLEVER sem ficheiro de texto em "
                         f"{articles_dir}.")
    return out


def prepare_clever(args) -> None:
    """Both sides of the split, in the order of the split record, as JSONL files."""
    registo = ler_json(args.split)
    out_dir = Path(args.clever_output_dir)

    por_id = {e["id"]: e for e in flatten_clever(ler_json(args.clever_json),
                                                 Path(args.clever_articles_dir))}
    em_falta = [i for i in registo["train_ids"] + registo["test_ids"] if i not in por_id]
    if em_falta:
        raise SystemExit(f"[clever] ids do split que não existem no CLEVER: {em_falta[:5]}")
    train = [por_id[i] for i in registo["train_ids"]]
    test = [por_id[i] for i in registo["test_ids"]]

    if len(train) != args.clever_train_size or len(test) != args.clever_test_size:
        raise SystemExit(f"[clever] o split tem {len(train)}/{len(test)} claim spans, "
                         f"esperava {args.clever_train_size}/{args.clever_test_size}.")
    partilhados = {e["document"] for e in train} & {e["document"] for e in test}
    if partilhados:
        raise SystemExit(f"[clever] {len(partilhados)} documentos nos dois lados do split: "
                         f"{sorted(partilhados)[:5]}. O split está errado.")

    # Written in the normalised schema (the `document` field does not survive it).
    write_jsonl(out_dir / "clever_all.jsonl", [normalize_example(e) for e in train + test])
    write_jsonl(out_dir / f"clever_train_{args.clever_train_size}.jsonl",
                [normalize_example(e) for e in train])
    write_jsonl(out_dir / f"clever_test_{args.clever_test_size}.jsonl",
                [normalize_example(e) for e in test])

    print(f"[clever] train={len(train)} test={len(test)} "
          f"({len({e['document'] for e in train})}+{len({e['document'] for e in test})} documentos); "
          f"perguntas gold no treino={sum(len(e['reference_questions']) for e in train)}")


def enrich_claimpt(records: list, articles_dir: Path) -> list:
    """Attach the article and normalise the silver records (questions -> silver_questions)."""
    out = []
    for r in records:
        document = r.get("document", "")
        out.append({
            "id": r.get("id", ""),
            "claim_span": _clean(r.get("claim_span")),
            "context": read_article(articles_dir, document),
            "publication_time": normalize_date(r.get("publication_time")),
            "claim_time": _clean(r.get("claim_time")),
            "claimers": as_text_list(r.get("claimers")),
            "claim_objects": as_text_list(r.get("claim_objects")),
            "silver_questions": as_text_list(r.get("silver_questions") or r.get("questions")),
            "document": document,
            "source": "claimpt_silver",
        })
    return out


def prepare_claimpt(args) -> None:
    """Nested subsets (25 ⊆ 50 ⊆ 75 ⊆ 100) of the de-duplicated silver set."""
    articles = Path(args.claimpt_articles_dir)
    out_dir = Path(args.processed_output_dir)

    examples = [normalize_example(e) for e in
                enrich_claimpt(unidades_silver((args.claimpt_train, args.claimpt_test)), articles)]
    if not examples:
        raise SystemExit("[claimpt] Sem exemplos silver nos ficheiros indicados.")

    n_before = len(examples)
    examples, _, n_after = dedup(examples)

    # One shuffle after concatenation and de-duplication; the subsets are its prefixes.
    shuffled = examples[:]
    random.Random(args.seed).shuffle(shuffled)
    total = len(shuffled)
    sizes = {p: (total * p) // 100 for p in (25, 50, 75, 100)}
    sizes[100] = total
    samples = {p: shuffled[:sizes[p]] for p in (25, 50, 75, 100)}

    for p in (25, 50, 75, 100):
        write_jsonl(out_dir / f"claimpt_silver_{p}.jsonl", samples[p])

    print(f"[claimpt] {n_before} brutos -> {n_after} após dedup; nested sizes={sizes}")

    # Question counts of the silver set and of its nested subsets (Tables 3.7 and 4.8).
    perguntas = {p: sum(len(e["questions"]) for e in samples[p]) for p in (25, 50, 75, 100)}
    por_span = Counter(len(e["questions"]) for e in samples[100])
    distribuicao = {n: por_span[n] for n in range(1, max(por_span) + 1)}
    print(f"[claimpt] perguntas silver por subconjunto={perguntas}; claim spans por número de "
          f"perguntas={distribuicao}; média por claim span={perguntas[100] / total:.2f}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--clever_json", default=CLEVER_JSON)
    p.add_argument("--split", default=SPLIT, help="Split record (default: split/clever_split_ids_seed0.json).")
    p.add_argument("--clever_articles_dir", default=CLEVER_ARTIGOS)
    p.add_argument("--clever_output_dir", default=ROOT / "data" / "clever")
    p.add_argument("--clever_train_size", type=int, default=40)
    p.add_argument("--clever_test_size", type=int, default=100)
    p.add_argument("--claimpt_train", default=CLAIMPT_JSON["train"])
    p.add_argument("--claimpt_test", default=CLAIMPT_JSON["test"])
    p.add_argument("--claimpt_articles_dir", default=CLAIMPT_ARTIGOS)
    p.add_argument("--processed_output_dir", default=ROOT / "data" / "processed")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    prepare_clever(args)
    prepare_claimpt(args)
    print("[prepare_data] concluído.")


if __name__ == "__main__":
    main()
