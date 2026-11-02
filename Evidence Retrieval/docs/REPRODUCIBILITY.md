# Reproducing the evidence-retrieval experiments

This document complements the [Evidence Retrieval README](../README.md), which explains the evaluation and gives all its results, with the inputs, search protocol and commands of the evidence-retrieval experiments. Commands are intended to run **from `Evidence Retrieval/`**, not from `docs/`.

## 1. Environment and access

Install the pinned dependencies as shown in the [stage README](../README.md#installation); the scripts run on **CPU**.

The LUSA News Corpus is accessed through a **restricted institutional search API**. Connect to the institution's VPN and create a local `.env` file in `Evidence Retrieval/` with the following names and the authorised values:

```dotenv
API_URL_LUSA=<authorised_api_url>
USER_LUSA=<authorised_username>
PASSWORD_LUSA=<authorised_password>
```

Do **not** commit `.env` or LUSA content to the repository.

The `src/lusa_api.py` client handles API authentication, token renewal, and retries. The retrieval script also consolidates reissued copies of the same LUSA story.

## 2. Inputs and evaluation split

The input collection is the **CLEVER** dataset, read from `../CLEVER/clever.json`. The evaluation uses the fixed **100 test claim spans** of the Question Generation split, which are the claim spans of the stored search results (step 4 below).

The evaluation references are LUSA documents manually annotated for relevance and, when Relevant, for their factual relation to the claim span. Decisive evidence is the subset annotated Supported or Refuted. The composition of this reference evidence, and the reason why CLEVER's manually written verification questions are not compared as queries, are given in the [README](../README.md#reference-evidence).

## 3. Search infrastructure and retrieval protocol

The searched collection is the **LUSA News Corpus**: 1,346,032 documents (about 1.3M) published by Agência Lusa between 1 January 2016 and 20 April 2026. Its main statistics are:

| Property | Value |
|---|---:|
| Total number of documents | 1,346,032 |
| Date of the earliest document | 2016-01-01 |
| Date of the most recent document | 2026-04-20 |
| Average words per document | 406.4 |
| Distinct journalistic genres | 20 |
| Distinct topics | 682 |
| Average topics per document | 6.35 |
| Distinct countries | 236 |
| Distinct cities | 5,027 |
| Distinct regions | 887 |

All three query types use the **same LUSA search infrastructure**, with a strict temporal cutoff: the returned LUSA article must be **published before** the source claim article.

The API implements hybrid retrieval, combining a lexical and a semantic ranking:

- **Lexical:** BM25 over the headline and content fields, with the headline weighted three times the content, k1 = 1.2 and b = 0.75.
- **Semantic:** normalized 1024-dimensional embeddings produced by `intfloat/multilingual-e5-large`, with approximate nearest-neighbor search through an HNSW index implemented in FAISS.
- **Fusion:** internal Reciprocal Rank Fusion (RRF) with constant 60: each candidate document scores the sum of 1/(60 + rank) over the two rankings, and candidates are ordered by this score.

The experiments do **not** compare or retrain the retrieval engine. A second RRF step, with the same constant, is applied in the **RRF top-5** configuration to merge the rankings obtained from several generated questions; these are separate fusion operations.

The evaluated query sources are:

1. **Complete claim** - the full sentence or statement containing the target span (`--query frase`; condition `claim_frase` in `evidencias.csv`, shown as `Claim` in the reports of `comparar_queries.py` and `bootstrap_emparelhado_queries.py`).
2. **Claim span** - the factual span selected for verification (`--query claim`; condition `claim_span` in `evidencias.csv`).
3. **Generated questions** - outputs of the 14 models of the [Question Generation](../../Question%20Generation/) stage, fine-tuned using **Gold91+Silver1073** (91 manually written CLEVER questions and 1,073 synthetic ClaimPT questions).

The three retrieval configurations are:

| Configuration | Query/search count | Retained documents |
|---|---|---|
| **Single-search top-5** | One search per condition; the **first question** for question-based conditions | Five highest-ranked documents |
| **RRF top-5** | All generated questions searched independently; question results fused with RRF (constant 60) | Five distinct documents per condition |
| **Matched retrieval volume** | All generated questions searched independently; reissues and duplicates consolidated | All distinct question results; complete-claim and claim-span baselines use a matched claim-span-specific budget, at least five, based on the median question-based volume across 14 models |

The first configuration controls for the number of searches; the second controls the final number of documents but permits multiple questions; the third retains potentially complementary evidence across searches. The **matched-volume budgets** vary across claim spans.

## 4. Prepare query inputs and retrieve LUSA results

First, construct CLEVER gold-question units with the associated claim spans and complete claims:

```bash
python src/build_gold_questions.py
```

This writes `outputs/gold_questions.jsonl`, one unit per gold question, for all 140 CLEVER claim spans (307 questions).

Next, run the API retrieval commands, one per search mode of `src/retrieve_lusa.py`:

```bash
python src/retrieve_lusa.py
python src/retrieve_lusa.py --query claim --output-dir outputs/lusa_top20_claim
python src/retrieve_lusa.py --query frase --output-dir outputs/lusa_top20_frase
```

The three calls write one ranking file per search, each with up to 20 distinct news items: one per gold question in `outputs/lusa_top20/<question_id>.json`, and one per claim span in `outputs/lusa_top20_claim/<span_id>.json` (claim-span query) and `outputs/lusa_top20_frase/<span_id>.json` (complete-claim query). The retrieved documents are cached in `outputs/lusa_docs/<doc_id>.json`. The CLEVER reference documents were collected from the gold-question searches, so the gold questions are not an evaluated condition. The values `claim` and `frase` of `--query` are code identifiers: `claim` is the **claim span** and `frase` the **complete claim**. Running a command again resumes where it stopped.

The comparison of the question-generation models also needs the stored search results of the **14 generated-question conditions**. These results, the stored rankings and the document cache are expected at:

```text
data/export_evidencias/evidencias.csv    # Top-5 results of every search of every condition
outputs/lusa_top20_claim/<span_id>.json  # Claim-span rankings
outputs/lusa_top20_frase/<span_id>.json  # Complete-claim rankings
outputs/lusa_docs/<doc_id>.json          # Shared source-document cache
```

These paths describe **required inputs**, not downloadable public fixtures. `evidencias.csv` holds, for the 100 test claim spans, the top-5 results of each search of the 14 models' questions, the complete claim, the claim span and the CLEVER gold questions (not an evaluated condition). Under Matched retrieval volume, `comparar_queries.py` extends the stored top-5 of the complete claim and of the claim span with the next documents of their rankings, up to the claim span's budget.

A claim span is identified by its claim's `id` in CLEVER, followed by `_s<i>` (its position, from 0) when the claim has several spans, for example `clever_004_c1` and `clever_006_c7_s0`. Documents are identified by their LUSA identifier: `doc_id` in the API and in `evidencias.csv`, `lusa_doc_id` in CLEVER.

## 5. Compute retrieval measures

Once the fixed stored results and CLEVER annotations are in place:

```bash
python src/comparar_queries.py
```

The script evaluates the three query strategies in each retrieval configuration, producing:

```text
outputs/comparacao_queries.md
```

The report gives the size of each ground-truth subset and the values of the [Relevant evidence](../README.md#relevant-evidence) and [decisive evidence](../README.md#decisive-evidence-and-claim-span-coverage) result tables as percentages, with the hit counts, in one table sorted by Decisive Micro Recall within each configuration. The metrics are defined in the [README](../README.md#metrics).

## 6. Paired bootstrap analysis

```bash
python src/bootstrap_emparelhado_queries.py
```

The script writes the paired comparisons to `outputs/bootstrap/bootstrap_emparelhado.csv` and a report, `outputs/bootstrap/BOOTSTRAP_EMPARELHADO.md`, with three tables, all given in the [README results](../README.md#results): AMALIA-9B-0626-DPO against the two declarative baselines under Matched retrieval volume, the claim span against the complete claim in each configuration, and the number of the 14 models above each declarative baseline. It draws **10,000 paired bootstrap resamples** at claim-span level with **seed 42** and takes the 2.5th and 97.5th percentiles as the **95% confidence interval**, over the 83, 56 or 54 claim spans of each metric.
