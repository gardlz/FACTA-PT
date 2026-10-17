# Reproducing the evidence-retrieval experiments

This document complements the [Evidence Retrieval README](../README.md) with the inputs, commands and complete result tables underlying **Chapter 5 (Sections 5.1–5.3)** of the dissertation. Commands are intended to run **from `Evidence Retrieval/`**, not from `docs/`.

## 1. Environment and access

Install the pinned dependencies as shown in the [stage README](../README.md#installation); the scripts run on **CPU**.

The LUSA News Corpus is accessed through a **restricted institutional search API**. Connect to the institution's VPN and create a local `.env` file in `Evidence Retrieval/` with the following names and your authorised values:

```dotenv
API_URL_LUSA=<authorised_api_url>
USER_LUSA=<authorised_username>
PASSWORD_LUSA=<authorised_password>
```

Do **not** commit `.env` or LUSA content to the repository.

The `src/lusa_api.py` client handles API authentication, token renewal, and retries. The retrieval script also consolidates reissued copies of the same LUSA story.

## 2. Inputs and evaluation split

The input collection is the **CLEVER** dataset, read from `../CLEVER/clever.json`. The evaluation uses the fixed **100 test claim spans** of the Question Generation split, which are the claim spans of the stored search results (step 4 below).

The evaluation references are LUSA documents manually annotated for relevance and, when Relevant, for their factual relation to the claim span. The ground-truth subsets are:

| Reference evidence | Claim spans | Annotated claim span–document pairs |
|---|---:|---:|
| Relevant | 83 | 217 |
| Decisive (Supported or Refuted) | 56 | 112 |
| DCSC: unique Supported or Refuted ground-truth status | 54 | - |

The remaining two claim spans with decisive evidence contain both Supported and Refuted evidence and are excluded from DCSC. **CLEVER's manually written verification questions are not themselves compared as retrieval queries**: they were involved in collecting the candidate documents later annotated as ground truth, so evaluating them on those same labels would be circular.

## 3. Search infrastructure and retrieval protocol

All three query types use the **same LUSA search infrastructure**, with a strict temporal cutoff: the returned LUSA article must be **published before** the source claim article.

As documented in the dissertation (Section 5.2.1), this API combines lexical BM25 and semantic search, with internal Reciprocal Rank Fusion (RRF). The dissertation does **not** compare or retrain the retrieval engine. A second RRF step is applied in the **RRF top-5** configuration to merge the rankings obtained from several generated questions; these are separate fusion operations.

The evaluated query sources are:

1. **Claim** - the full sentence or statement containing the target span (`--query frase`; condition `claim_frase` in `evidencias.csv`).
2. **Claim span** - the factual span selected for verification (`--query claim`; condition `claim_span` in `evidencias.csv`).
3. **Generated questions** - outputs of the 14 Chapter 4 models fine-tuned using **Gold91+Silver1073**.

The three retrieval configurations are:

| Configuration | Query/search count | Retained documents |
|---|---|---|
| **Single-search top-5** | One search per condition; the **first question** for question-based conditions | Five highest-ranked documents |
| **RRF top-5** | All generated questions searched independently; question results fused with RRF (constant 60) | Five distinct documents per condition |
| **Matched retrieval volume** | All generated questions searched independently; reissues and duplicates consolidated | All distinct question results; claim and claim-span baselines use a matched claim-span-specific budget, at least five, based on the median question-based volume across 14 models |

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

The three calls obtain rankings for the gold questions (`outputs/lusa_top20/`), claim spans, and complete claims, respectively, and keep the retrieved documents in `outputs/lusa_docs/`. The values `claim` and `frase` of `--query` are code identifiers: `claim` is the **claim span** and `frase` the **complete claim**. Running a command again resumes where it stopped.

The dissertation's question-model comparisons also need the stored results from the **14 generated-question conditions**. These results, the stored rankings and the document cache are expected at:

```text
data/export_evidencias/evidencias.csv    # Top-5 results of every search of every condition
outputs/lusa_top20_claim/<span_id>.json  # Claim-span rankings
outputs/lusa_top20_frase/<span_id>.json  # Complete-claim rankings
outputs/lusa_docs/<doc_id>.json          # Shared source-document cache
```

These paths describe **required inputs**, not downloadable public fixtures. `evidencias.csv` holds, for the 100 test claim spans, the top-5 results of each search of the 14 models' questions, the complete claim, the claim span and the CLEVER gold questions (not an evaluated condition). Under Matched retrieval volume, `comparar_queries.py` extends the stored top-5 of the complete claim and of the claim span with the next documents of their rankings, up to the claim span's budget.

## 5. Compute retrieval measures

Once the fixed stored results and CLEVER annotations are in place:

```bash
python src/comparar_queries.py
```

The script evaluates the three query strategies in each retrieval configuration, producing:

```text
outputs/comparacao_queries.md
```

This report corresponds to the evaluations shown in dissertation **Tables 5.2–5.3**. It gives the values as percentages, with the hit counts, in one table sorted by Decisive Micro Recall within each configuration.

**Definitions used in the dissertation:**

- **Relevant evidence** includes the reference documents annotated Relevant, including those labelled Not Enough Information (NEI).
- **Decisive evidence** is the subset annotated **Supported** or **Refuted**.
- **Macro Recall** averages per-claim-span Recall over claim spans with at least one target reference document; **Micro Recall** pools recovered and available reference documents first.
- **DCSC** is the fraction of the 54 claim spans with a unique decisive reference status for which at least one decisive reference document consistent with that status is recovered.
- **Docs/span** counts the average number of distinct retrieved documents per claim span; it describes retrieved volume, not precision.

## 6. Paired bootstrap analysis

```bash
python src/bootstrap_emparelhado_queries.py
```

The script writes `outputs/bootstrap/BOOTSTRAP_EMPARELHADO.md` and `outputs/bootstrap/bootstrap_emparelhado.csv`: Table 5.4, the claim span against the complete claim in each configuration, and the number of models above each declarative baseline, as cited in Section 5.3. It draws **10,000 paired bootstrap resamples** at claim-span level with **seed 42** and takes the 2.5th and 97.5th percentiles as the **95% confidence interval**, over the 83, 56 or 54 claim spans of each metric.

## Results

The tables below are copied from the dissertation, with its bold marks.

Table 5.2: Retrieval of CLEVER *Relevant* ground-truth evidence under Single-search top-5, RRF top-5, and Matched retrieval volume.

| Query strategy | Single-search top-5 · Macro R | Single-search top-5 · Micro R | RRF top-5 · Macro R | RRF top-5 · Micro R | Matched retrieval volume · Macro R | Matched retrieval volume · Micro R | Matched retrieval volume · Docs/span |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Claim | 0.157 | 0.180 | 0.157 | 0.180 | 0.209 | 0.235 | 9.0 |
| Claim span | 0.200 | 0.253 | 0.200 | 0.253 | 0.241 | 0.309 | 9.0 |
| PTT5 Large | 0.178 | 0.198 | 0.186 | 0.207 | 0.242 | 0.263 | 7.1 |
| PTT5-v2 Large | **0.269** | 0.281 | 0.251 | 0.281 | 0.308 | 0.346 | 8.7 |
| PTT5-v2 3B | 0.235 | 0.272 | 0.241 | 0.276 | 0.320 | 0.359 | 8.0 |
| mT0 Large | 0.217 | 0.249 | 0.217 | 0.240 | 0.259 | 0.281 | 7.3 |
| mT5 XL | 0.106 | 0.138 | 0.166 | 0.207 | 0.266 | 0.300 | 10.8 |
| mT0 XXL | 0.243 | 0.286 | 0.224 | 0.281 | 0.285 | 0.346 | 8.1 |
| Tucano-1b1-Instruct | 0.189 | 0.226 | 0.193 | 0.244 | 0.304 | 0.355 | 8.9 |
| Llama 3.2-1B-Instruct | 0.251 | 0.263 | 0.245 | 0.276 | 0.302 | 0.336 | 9.0 |
| GlórIA-1.3B | 0.178 | 0.217 | 0.166 | 0.203 | 0.239 | 0.290 | 9.5 |
| Bode-7B-Alpaca | 0.255 | **0.295** | 0.258 | 0.300 | 0.315 | 0.355 | 9.0 |
| Llama 3.1-8B-Instruct | 0.239 | 0.253 | 0.237 | 0.267 | 0.321 | 0.364 | 8.7 |
| Gervásio-8B PT-PT | 0.250 | 0.267 | 0.245 | 0.300 | 0.351 | 0.382 | 9.0 |
| AMALIA-9B-0626-DPO | **0.269** | 0.290 | 0.202 | 0.253 | **0.370** | **0.387** | 8.9 |
| Mistral NeMo-12B-Instruct | 0.234 | 0.258 | **0.278** | **0.304** | 0.335 | 0.369 | 9.0 |

Table 5.3: Retrieval of decisive CLEVER ground-truth evidence and claim-span coverage under Single-search top-5, RRF top-5, and Matched retrieval volume.

| Query strategy | Single-search top-5 · Macro R | Single-search top-5 · Micro R | Single-search top-5 · Coverage | RRF top-5 · Macro R | RRF top-5 · Micro R | RRF top-5 · Coverage | Matched retrieval volume · Macro R | Matched retrieval volume · Micro R | Matched retrieval volume · Coverage |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Claim | 0.204 | 0.232 | 0.296 | 0.204 | 0.232 | 0.296 | 0.255 | 0.286 | 0.352 |
| Claim span | 0.245 | 0.330 | 0.352 | 0.245 | **0.330** | 0.352 | 0.314 | 0.402 | 0.407 |
| PTT5 Large | 0.185 | 0.241 | 0.278 | 0.197 | 0.241 | 0.278 | 0.252 | 0.295 | 0.333 |
| PTT5-v2 Large | 0.283 | 0.330 | 0.389 | 0.259 | 0.295 | 0.389 | 0.344 | 0.375 | 0.444 |
| PTT5-v2 3B | 0.294 | 0.330 | **0.444** | 0.260 | 0.286 | 0.389 | 0.363 | 0.393 | 0.500 |
| mT0 Large | 0.268 | 0.304 | 0.352 | 0.276 | 0.295 | 0.389 | 0.340 | 0.357 | 0.444 |
| mT5 XL | 0.161 | 0.170 | 0.259 | 0.212 | 0.250 | 0.333 | 0.349 | 0.375 | 0.463 |
| mT0 XXL | 0.276 | 0.321 | 0.407 | 0.279 | **0.330** | 0.407 | 0.350 | 0.393 | 0.463 |
| Tucano-1b1-Instruct | 0.146 | 0.196 | 0.241 | 0.196 | 0.241 | 0.333 | 0.283 | 0.339 | 0.389 |
| Llama 3.2-1B-Instruct | 0.244 | 0.268 | 0.296 | 0.272 | 0.304 | 0.352 | 0.331 | 0.357 | 0.407 |
| GlórIA-1.3B | 0.199 | 0.259 | 0.296 | 0.178 | 0.223 | 0.296 | 0.295 | 0.348 | 0.370 |
| Bode-7B-Alpaca | 0.297 | 0.339 | 0.426 | 0.277 | 0.312 | 0.407 | 0.372 | 0.384 | 0.500 |
| Llama 3.1-8B-Instruct | 0.250 | 0.312 | 0.352 | 0.224 | 0.295 | 0.333 | 0.322 | 0.393 | 0.444 |
| Gervásio-8B PT-PT | 0.290 | 0.304 | 0.370 | **0.302** | **0.330** | 0.407 | 0.415 | 0.420 | 0.519 |
| AMALIA-9B-0626-DPO | **0.316** | **0.348** | **0.444** | 0.280 | 0.312 | 0.426 | **0.445** | **0.464** | **0.593** |
| Mistral NeMo-12B-Instruct | 0.259 | 0.321 | 0.389 | 0.290 | **0.330** | **0.444** | 0.354 | 0.393 | 0.500 |

Table 5.4: Paired bootstrap differences (95% CI) between AMALIA-9B-0626-DPO and the declarative baselines under Matched retrieval volume.

| Baseline | Metric | Difference | 95% CI |
|---|---|---:|---:|
| Claim | Relevant Macro R | +0.161 | [0.078, 0.247] |
| Claim | Relevant Micro R | +0.152 | [0.072, 0.237] |
| Claim | Decisive Macro R | +0.190 | [0.077, 0.304] |
| Claim | Decisive Micro R | +0.179 | [0.083, 0.278] |
| Claim | DCSC | +0.241 | [0.111, 0.389] |
| Claim span | Relevant Macro R | +0.129 | [0.044, 0.219] |
| Claim span | Relevant Micro R | +0.078 | [0.000, 0.164] |
| Claim span | Decisive Macro R | +0.131 | [0.011, 0.253] |
| Claim span | Decisive Micro R | +0.062 | [-0.036, 0.167] |
| Claim span | DCSC | +0.185 | [0.056, 0.315] |

## Dissertation reference

For the complete experimental methodology, uncertainty estimates, and the scientific discussion, see **Chapter 5, Sections 5.1–5.4 and Tables 5.1–5.4**. For the overall project and citation, see the [repository README](../../README.md).
