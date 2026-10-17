"""Question-set metrics: H-ROUGE-L, H-METEOR, H-BERTScore-F1, Cov-BERTScore-F1, CountErr, Q/Ex.

For each claim span, every metric builds its own generated x reference similarity matrix,
takes the Hungarian one-to-one assignment and divides by max(|G|, |R|); Cov-BERT is the
mean over references of the best generated match. Scores are macro-averaged over spans.

    python src/metrics.py --predictions_dir outputs/predictions --metrics_dir outputs/metrics
"""

import argparse
import csv
import json
import math
import re
import warnings
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from io_utils import read_jsonl

SCORE_KEYS = ["rouge_l", "meteor", "h_bert", "cov_bert"]
COUNT_KEYS = ["count_error", "q_per_example", "ref_q_per_example"]


def normalize_questions(value) -> List[str]:
    """JSON list | list | newline-separated text -> list of questions (whitespace collapsed)."""
    if value is None:
        return []
    if isinstance(value, float) and math.isnan(value):
        return []

    if isinstance(value, (list, tuple)):
        items: Sequence = value
    else:
        text = str(value).strip()
        if not text:
            return []
        items = None
        if text[0] in "[(":
            try:
                parsed = json.loads(text)
                items = parsed if isinstance(parsed, list) else [parsed]
            except (json.JSONDecodeError, ValueError):
                items = None
        if items is None:
            items = text.splitlines()

    out: List[str] = []
    for item in items:
        if isinstance(item, dict):
            item = item.get("text") or item.get("question") or ""
        elif isinstance(item, (list, tuple)):
            out.extend(normalize_questions(list(item)))
            continue
        cleaned = re.sub(r"\s+", " ", str(item)).strip()
        if cleaned:
            out.append(cleaned)
    return out


_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def pt_tokenize(text: str) -> List[str]:
    """Lower-cased unicode `\\w+` tokens: keeps accents and cedillas, drops punctuation."""
    return _TOKEN_RE.findall(str(text).lower())


# --------------------------------------------------------------------------- #
# ROUGE-L                                                                      #
# --------------------------------------------------------------------------- #
class _PtTokenizer:
    """`pt_tokenize` behind the rouge-score tokenizer interface (its default splits "eleições")."""

    def tokenize(self, text: str) -> List[str]:
        return pt_tokenize(text)


def _lcs_length(a: Sequence[str], b: Sequence[str]) -> int:
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b):
            cur.append(prev[j] + 1 if x == y else max(cur[j], prev[j + 1]))
        prev = cur
    return prev[-1]


def _lcs_rouge_l(hyp: str, ref: str) -> float:
    """ROUGE-L F1 on `pt_tokenize` tokens (same definition as rouge-score)."""
    h, r = pt_tokenize(hyp), pt_tokenize(ref)
    if not h or not r:
        return 0.0
    lcs = _lcs_length(h, r)
    if lcs == 0:
        return 0.0
    precision, recall = lcs / len(h), lcs / len(r)
    return 2 * precision * recall / (precision + recall) * 100


@lru_cache(maxsize=1)
def _rouge_l_fn() -> Callable[[str, str], float]:
    """rouge-score with the Portuguese tokenizer; the internal LCS if it is unavailable."""
    try:
        from rouge_score import rouge_scorer
        scorer = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=False,
                                          tokenizer=_PtTokenizer())
    except Exception as e:
        warnings.warn(f"rouge-score indisponível ou sem suporte a tokenizer ({e}); "
                      f"a usar a implementação LCS interna (mesma definição).")
        return _lcs_rouge_l
    return lambda hyp, ref: scorer.score(ref, hyp)["rougeL"].fmeasure * 100


def sent_rouge_l(hyp: str, ref: str) -> float:
    return _rouge_l_fn()(hyp, ref)


# --------------------------------------------------------------------------- #
# METEOR for Portuguese: exact match on `pt_tokenize`, Snowball-pt stems and   #
# Open Multilingual Wordnet synonyms with lang="por"; NLTK fragmentation penalty.
# --------------------------------------------------------------------------- #
class _PtLema:
    """Lemma with the minimal interface used by `meteor_score` (`.name()`)."""

    __slots__ = ("_nome",)

    def __init__(self, nome: str):
        self._nome = nome

    def name(self) -> str:
        return self._nome


class _PtSinonimos:
    """Synthetic synset: the stemmed Portuguese synonyms of a word."""

    __slots__ = ("_lemas",)

    def __init__(self, lemas):
        self._lemas = [_PtLema(x) for x in lemas]

    def lemmas(self):
        return self._lemas


class _PtWordnet:
    """Portuguese OMW with the interface `meteor_score` expects, indexed by stems.

    NLTK's stem-matching stage hands the synonym stage words that are already stemmed,
    so the OMW is indexed once as stem -> synonym stems.
    """

    def __init__(self, wn, stemmer):
        self._wn = wn
        self._stemmer = stemmer
        self._indice = None

    def _constroi_indice(self) -> dict:
        indice: dict = {}
        for synset in self._wn.all_synsets():
            lemas = [l.name() for l in synset.lemmas(lang="por") if "_" not in l.name()]
            if len(lemas) < 2:
                continue
            radicais = {self._stemmer.stem(x) for x in lemas}
            for radical in radicais:
                indice.setdefault(radical, set()).update(radicais)
        return indice

    def synsets(self, word: str):
        if self._indice is None:
            self._indice = self._constroi_indice()
        sinonimos = self._indice.get(word)
        return [_PtSinonimos(sinonimos)] if sinonimos else []


class _NoWordnet:
    """No synonyms: METEOR falls back to exact + stem matching (never English resources)."""

    def synsets(self, word: str):
        return []


@lru_cache(maxsize=1)
def _meteor_setup() -> Tuple[object, object]:
    """(stemmer, wordnet) of the Portuguese METEOR, loaded once.

    Without the Portuguese OMW the synonym stage is disabled and a loud warning is printed.
    """
    from nltk.stem.snowball import SnowballStemmer

    stemmer = SnowballStemmer("portuguese")
    try:
        from nltk.corpus import wordnet
        if not wordnet.synsets("eleição", lang="por"):
            raise LookupError("OMW carregou mas não devolveu synsets em português")
        return stemmer, _PtWordnet(wordnet, stemmer)
    except Exception as e:
        warnings.warn(
            "\n" + "!" * 78 +
            f"\nMETEOR SEM SINÓNIMOS PORTUGUESES: {e}"
            "\nO nível 3 (OMW pt) não corre; os valores NÃO são o METEOR adaptado ao"
            "\nportuguês e não devem ser comparados com valores calculados com o OMW."
            "\nResolver com:  python -c \"import nltk; nltk.download('omw-2.0');"
            " nltk.download('wordnet')\""
            "\n(em NLTK < 3.9 o pacote chama-se 'omw-1.4')\n" + "!" * 78)
        return stemmer, _NoWordnet()


def sent_meteor(hyp: str, ref: str) -> float:
    from nltk.translate.meteor_score import meteor_score
    h, r = pt_tokenize(hyp), pt_tokenize(ref)
    if not h or not r:
        return 0.0
    stemmer, wn = _meteor_setup()
    return meteor_score([r], h, stemmer=stemmer, wordnet=wn) * 100


def _safe(fn: Callable, *a) -> Optional[float]:
    """fn(*a) as float; None (with a warning) on error."""
    try:
        return float(fn(*a))
    except Exception as e:
        warnings.warn(f"métrica indisponível ({getattr(fn, '__name__', fn)}): {e}")
        return None


def _mean(xs: Iterable[Optional[float]]) -> Optional[float]:
    vals = [x for x in xs if x is not None and not (isinstance(x, float) and math.isnan(x))]
    return sum(vals) / len(vals) if vals else None


def _round(v, nd: int = 4):
    """Round floats at output time only; counts stay integers."""
    if v is None or isinstance(v, bool) or not isinstance(v, (int, float)):
        return v
    if isinstance(v, int):
        return v
    return round(float(v), nd)


def similarity_matrix(gen: List[str], ref: List[str], sim_fn: Callable) -> List[List[float]]:
    return [[_safe(sim_fn, g, r) for r in ref] for g in gen]


def aligned_score(matrix: List[List[float]], n_gen: int, n_ref: int) -> float:
    """Best one-to-one assignment (Hungarian) divided by max(n_gen, n_ref).

    Equivalent to zero-padding the matrix to a square, so both missing references and
    extra generated questions lower the score.
    """
    if n_gen == 0 or n_ref == 0:
        return 0.0
    import numpy as np
    from scipy.optimize import linear_sum_assignment
    scores = np.array([[0.0 if v is None else v for v in row] for row in matrix], dtype=float)
    rows, cols = linear_sum_assignment(-scores)
    return float(scores[rows, cols].sum()) / max(n_gen, n_ref)


# --------------------------------------------------------------------------- #
# BERTScore (all generated x reference pairs in one call)                      #
# --------------------------------------------------------------------------- #
def pick_device(requested: Optional[str] = None) -> Optional[str]:
    """BERTScore device: the requested one, else cuda if available, else cpu."""
    if requested:
        return requested
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return None


@lru_cache(maxsize=2)
def _bertscorer(model_type: str, num_layers: int, batch_size: int, device: Optional[str]):
    """One BERTScorer per run, reused across prediction files."""
    from bert_score import BERTScorer
    print(f"[metrics] BERTScore: {model_type} (camada {num_layers}) em {device or 'cpu'}")
    return BERTScorer(model_type=model_type, num_layers=num_layers, device=device,
                      batch_size=batch_size, lang=None, rescale_with_baseline=False)


def bertscore_f1_matrix(items: List[dict],
                        model_type: str = "FacebookAI/xlm-roberta-large",
                        num_layers: int = 17,
                        batch_size: int = 64,
                        device: Optional[str] = None) -> Optional[Dict[Tuple[int, int, int], float]]:
    """{(example, generated, reference): F1} for every pair, or None if BERTScore fails."""
    cand, refs, keys = [], [], []
    for idx, it in enumerate(items):
        for gi, g in enumerate(it["generated_questions"]):
            for ri, r in enumerate(it["reference_questions"]):
                cand.append(g)
                refs.append(r)
                keys.append((idx, gi, ri))
    if not cand:
        return {}
    try:
        scorer = _bertscorer(model_type, num_layers, batch_size, device)
        _, _, f1 = scorer.score(cand, refs, verbose=False)
        return {k: float(v) for k, v in zip(keys, f1.tolist())}
    except Exception as e:
        warnings.warn(f"BERTScore indisponível: {e}")
        return None


# --------------------------------------------------------------------------- #
# Evaluation                                                                   #
# --------------------------------------------------------------------------- #
def to_item(row: dict) -> dict:
    """Prediction record -> normalised item."""
    return {
        "example_id": row.get("example_id") or row.get("id") or row.get("span_id") or "",
        "model_name": row.get("model_name") or row.get("model_short_name") or "",
        "train_config": row.get("train_config") or row.get("train_setting") or "",
        "regime": row.get("regime", "") or "",
        "architecture": row.get("architecture", "") or "",
        "language_group": row.get("language_group", "") or "",
        "claim_span": str(row.get("claim_span") or ""),
        "context": str(row.get("context") or ""),
        "reference_questions": normalize_questions(row.get("reference_questions")),
        "generated_questions": normalize_questions(row.get("generated_questions")),
    }


def evaluate_items(items: List[dict],
                   bertscore_model: str = "FacebookAI/xlm-roberta-large",
                   num_layers: int = 17,
                   device: Optional[str] = None) -> List[dict]:
    """Per-example metrics of the examples with reference questions (the others are skipped)."""
    usable = [it for it in items if it["reference_questions"]]
    skipped = len(items) - len(usable)
    if skipped:
        warnings.warn(f"{skipped} exemplo(s) sem reference_questions — ignorados "
                      f"(a avaliação exige perguntas de referência).")
    if not usable:
        return []

    bs = bertscore_f1_matrix(usable, bertscore_model, num_layers, device=device)

    records: List[dict] = []
    for idx, it in enumerate(usable):
        gen, ref = it["generated_questions"], it["reference_questions"]
        m, n = len(gen), len(ref)

        if m == 0:
            # Generating nothing scores zero, not a missing value.
            rouge_l = meteor = h_bert = cov_bert = 0.0
        else:
            rouge_l = aligned_score(similarity_matrix(gen, ref, sent_rouge_l), m, n)
            meteor = aligned_score(similarity_matrix(gen, ref, sent_meteor), m, n)
            if bs is None:
                h_bert = cov_bert = None
            else:
                matrix = [[bs.get((idx, gi, ri), 0.0) * 100 for ri in range(n)]
                          for gi in range(m)]
                h_bert = aligned_score(matrix, m, n)
                # Coverage: for each reference, the best of all generated questions.
                cov_bert = sum(max(matrix[gi][ri] for gi in range(m))
                               for ri in range(n)) / n

        records.append({
            "example_id": it["example_id"],
            "model_name": it["model_name"],
            "train_config": it["train_config"],
            "regime": it["regime"],
            "architecture": it["architecture"],
            "language_group": it["language_group"],
            "n_reference_questions": n,
            "n_generated_questions": m,
            "rouge_l": rouge_l,
            "meteor": meteor,
            "h_bert": h_bert,
            "cov_bert": cov_bert,
            "count_error": float(abs(m - n)),
            "q_per_example": float(m),
            "ref_q_per_example": float(n),
        })
    return records


def group_key(rec: dict) -> Tuple[str, str, str]:
    """(model, configuration, regime); zero- and few-shot share train_config "none"."""
    return (rec["model_name"], rec["train_config"], rec["regime"])


def summarize(records: List[dict]) -> List[dict]:
    """One row per (model, configuration, regime) with the mean of every metric."""
    groups: Dict[Tuple[str, str, str], List[dict]] = {}
    for rec in records:
        groups.setdefault(group_key(rec), []).append(rec)

    keys = SCORE_KEYS + COUNT_KEYS

    out = []
    for (model, config, regime), recs in groups.items():
        row = {
            "model_name": model,
            "train_config": config,
            "regime": regime,
            "architecture": recs[0]["architecture"],
            "language_group": recs[0]["language_group"],
            "n_examples": len(recs),
        }
        for key in keys:
            vals = [r.get(key) for r in recs]
            row[f"mean_{key}"] = _round(_mean(vals))
        out.append(row)

    return sorted(out, key=lambda r: (
        -(r.get("mean_h_bert") or 0.0),
        -(r.get("mean_cov_bert") or 0.0),
        r.get("mean_count_error") if r.get("mean_count_error") is not None else float("inf"),
        -(r.get("mean_rouge_l") or 0.0),
        -(r.get("mean_meteor") or 0.0)))


def summary_fields(rows: List[dict]) -> List[str]:
    base = ["model_name", "train_config", "regime", "architecture", "language_group",
            "n_examples"]
    rest = [k for k in rows[0] if k not in base] if rows else []
    return base + rest


def write_csv(path: Path, rows: List[dict], fields: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)
    print(f"[metrics] CSV -> {path}  ({len(rows)} linhas)")


def write_outputs(records: List[dict], metrics_dir: Path) -> None:
    summary = summarize(records)
    write_csv(metrics_dir / "summary_metrics.csv", summary, summary_fields(summary))


# --------------------------------------------------------------------------- #
# Prediction files                                                             #
# --------------------------------------------------------------------------- #
def parse_name(stem: str) -> dict:
    """{regime}__{train_setting}__{arch}__{model}__seed{n} -> dict."""
    parts = stem.split("__")
    if len(parts) < 5:
        return {"regime": "", "train_setting": "", "architecture": "",
                "model_short_name": "", "seed": ""}
    return {"regime": parts[0], "train_setting": parts[1], "architecture": parts[2],
            "model_short_name": parts[3], "seed": parts[4].replace("seed", "")}


def run_file(pred_file: Path, args) -> List[dict]:
    """Per-example metrics of one predictions file ([] if none can be evaluated)."""
    rows = read_jsonl(pred_file)
    meta = parse_name(pred_file.stem)

    items = []
    for row in rows:
        item = to_item(row)
        # The file name is the authoritative source of model, configuration and regime.
        item["model_name"] = meta["model_short_name"] or item["model_name"]
        item["train_config"] = meta["train_setting"] or item["train_config"]
        item["regime"] = meta["regime"] or item["regime"]
        item["architecture"] = item["architecture"] or meta["architecture"]
        items.append(item)

    records = evaluate_items(items, args.bertscore_model, args.num_layers,
                             pick_device(args.device))
    if not records:
        warnings.warn(f"{pred_file.name}: sem exemplos avaliáveis.")
        return []

    summary = summarize(records)[0]
    print(f"[metrics] {pred_file.name} -> h_bert={summary.get('mean_h_bert')} "
          f"cov={summary.get('mean_cov_bert')} "
          f"count_err={summary.get('mean_count_error')}")
    return records


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--predictions_file", default=None, help="A single predictions JSONL.")
    p.add_argument("--predictions_dir", default=None, help="Folder of predictions *.jsonl.")
    p.add_argument("--metrics_dir", default="outputs/metrics")
    p.add_argument("--bertscore_model", default="FacebookAI/xlm-roberta-large")
    p.add_argument("--num_layers", type=int, default=17)
    p.add_argument("--device", default=None,
                   help="BERTScore device (cuda/cpu). Default: cuda if available, else cpu.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    metrics_dir = Path(args.metrics_dir)
    metrics_dir.mkdir(parents=True, exist_ok=True)

    if args.predictions_file:
        pred_file = Path(args.predictions_file)
        if not pred_file.exists():
            raise SystemExit(f"Prediction inexistente: {pred_file}")
        records = run_file(pred_file, args)
    elif args.predictions_dir:
        pred_dir = Path(args.predictions_dir)
        if not pred_dir.is_dir():
            raise SystemExit(f"Pasta de predictions inexistente: {pred_dir.resolve()}")
        files = sorted(pred_dir.glob("*.jsonl"))
        if not files:
            raise SystemExit(f"Sem ficheiros *.jsonl em {pred_dir.resolve()}")
        print(f"[metrics] {len(files)} predictions em {pred_dir}")
        records = []
        for f in files:
            records.extend(run_file(f, args))
    else:
        raise SystemExit("É preciso --predictions_dir ou --predictions_file.")

    if not records:
        raise SystemExit("Sem exemplos avaliáveis — nada escrito.")
    write_outputs(records, metrics_dir)


if __name__ == "__main__":
    main()
