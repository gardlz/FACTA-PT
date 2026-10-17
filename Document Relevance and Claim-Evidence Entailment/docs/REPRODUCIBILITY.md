# Reproducing document relevance and Claim-Evidence Entailment experiments

This document complements the [stage README](../README.md) with the data requirements, model-selection protocol and commands underlying **Chapter 6** of the dissertation. **Run all commands from `Document Relevance and Claim-Evidence Entailment/`, not from `docs/`.**

## 1. Environment and prerequisites

The experiments were run on the Deucalion supercomputer, on **NVIDIA A100-SXM4 GPUs (40 GB and 80 GB)**, and their resource consumption was recorded with CodeCarbon. The training entry points (`correr.py` and `final.py`) require CUDA; data preparation and analysis scripts run on CPU.

```bash
python -m venv .venv
source .venv/bin/activate
pip install torch==2.10.0 --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements.txt
```

The eleven pretrained encoders are identified in `configs/modelos.yaml` and are downloaded from Hugging Face on first use. If they are already cached, `HF_HUB_OFFLINE=1` can prevent network requests. Check model licences and access requirements before downloading. The experiment implementation uses **float32**.

### Model-loading compatibility

`ruanchaves/mdeberta-v3-base-assin2-entailment` and `ruanchaves/bert-large-portuguese-cased-assin2-entailment` publish a `config.json` whose `id2label` has integer values, which the `transformers` release pinned in `requirements.txt` refuses to load. If loading either checkpoint fails for this reason, rewrite its **local cached** `config.json` once, with string labels and a valid two-class mapping:

```bash
python - <<'PY'
import json
import pathlib
from huggingface_hub import hf_hub_download

for repo in (
    "ruanchaves/mdeberta-v3-base-assin2-entailment",
    "ruanchaves/bert-large-portuguese-cased-assin2-entailment",
):
    path = pathlib.Path(hf_hub_download(repo, "config.json"))
    config = json.loads(path.read_text(encoding="utf-8"))
    config["id2label"] = {"0": "LABEL_0", "1": "LABEL_1"}
    config["label2id"] = {"LABEL_0": 0, "LABEL_1": 1}
    path.unlink()  # Detach the cached snapshot link before writing a local replacement.
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
PY
```

**Do not modify the upstream model repositories.** Both tasks give these two checkpoints new classification heads (Section 6.2.1), so the replacement label names are not used as task labels.

## 2. CLEVER data and fixed partitions

The code expects the following inputs relative to this stage directory:

```text
../CLEVER/clever.json
../CLEVER/clever_train.json
../CLEVER/clever_test.json
```

`python src/construir_dados.py --clever <folder>` reads them from another folder. **CLEVER and LUSA content are not redistributed** in this code repository; obtain them according to the dataset's access conditions and the [root README](../../README.md#data). In `clever.json`, each claim span has its `retrieved_documents`, and each retrieved document has `doc_id`, `headline`, `content`, `relevant`, `relation` and `evidence_excerpts`; the code uses the text of each excerpt.

The **predefined evidence-characterization benchmark split** (Section 3.2.4 and Table 3.5) is distinct from the 40/100 claim-span split used in Question Generation:

| Input unit | Training | Test | Total |
|---|---:|---:|---:|
| CLEVER claim spans | 114 | 26 | 140 |
| Claim span–document pairs | 1,015 | 254 | 1,269 |
| Relevant pairs | 250 | 62 | 312 |
| Irrelevant pairs | 765 | 192 | 957 |
| Deduplicated three-sentence evidence passages | 425 | 82 | 507 |

The partition was constructed to approximate an **80/20** split, grouping source articles that share retrieved LUSA documents so that **no retrieved LUSA document appears in both training and test**. The code reads it from `clever_train.json` and `clever_test.json`.

CLEVER contains **527 manually annotated evidence excerpts**, 444 in training and 83 in test. Passage construction around those excerpts followed by within-pair deduplication removes **20** duplicates, leaving **507** passages (Table 6.4): **145 Supported, 42 Refuted and 238 NEI** in training, and **32 Supported, 9 Refuted and 41 NEI** in test.

## 3. Prepare the data

```bash
python src/construir_dados.py      # claim span–document pairs of both partitions
python src/folds.py                # task examples and grouped folds (3 seeds × 5 folds)
python src/diagnostico_janelas.py  # coverage of the training excerpts by sentence windows
python src/inventario.py           # model table of the eleven encoders (Table 6.1)
```

Main generated files:

```text
data/pares.jsonl                # Claim span–document classification pairs, with their partition
data/folds_relevance.json       # Grouped relevance-selection partitions
data/folds_entailment.json      # Grouped entailment-selection partitions
```

`construir_dados.py` prints, for each partition, the number of claims, claim spans, pairs per label and annotated excerpts per label (Section 3.2.4). `folds.py` builds the examples of both tasks from the training partition, every pair for relevance and one three-sentence window per annotated excerpt for entailment, and assigns whole source-article groups to five folds for each seed. `diagnostico_janelas.py` prints the share of the 444 training excerpts contained in a window of one, two and three consecutive sentences (84.7%, 97.3% and 100%; Section 6.2.3). `inventario.py` counts the parameters of each checkpoint, loaded on the CPU, and takes the other columns from `configs/modelos.yaml`; every checkpoint must load, including the two ASSIN2 checkpoints (see [Model-loading compatibility](#model-loading-compatibility)).

## 4. Tasks and passage construction

**Document relevance** is binary classification of `(claim span, retrieved LUSA document)` into `Relevant` or `Irrelevant`. A Relevant document is pertinent to the factual situation, but need not support or refute the claim. An Irrelevant document does not address that situation, which is what separates it from NEI evidence: pertinent, but insufficient to support or refute the claim (Section 6.1).

**Claim-Evidence Entailment** is three-class classification of `(passage, claim span)` into `Supported`, `Refuted` or `NEI`. The passage is the **premise** and the claim span the **hypothesis**. A **three-sentence window** is the smallest fixed sentence window that contains every annotated training excerpt (Section 6.2.3). In the supervised experiments, each annotated excerpt determines the location of its passage and gives it its label; duplicate windows from the same pair are removed.

Without manually identified excerpt locations, as in the FACTA-PT prototype, the classifier is instead applied to every three-sentence passage of each document predicted Relevant, with a stride of one sentence (Section 6.1). The subsequent consolidation retains the predicted decisive passages; if all passages of a document are predicted NEI, it retains one representative NEI passage using an adjusted-logit margin heuristic (Section 6.2.2). This consolidation is implemented in [`FACTA-PT/`](../../FACTA-PT/).

## 5. Model configuration selection

The eleven model keys from `configs/modelos.yaml` are:

```text
mdeberta_xnli         minilm_xnli        xlmr_large_xnli
xlmr_large_xnli_anli  assin2_mdeberta    assin2_bertimbau
albertina_100m        albertina_900m     bertimbau_base
bertimbau_large       serafim_335m
```

For **each model and each task** (Section 6.2.2):

1. Create **five grouped partitions** for each of **seeds 42, 43 and 44** (15 configuration-selection runs). Groups are based on the CLEVER source article.
2. In each run, one fold is excluded to change the remaining group composition. A **20% internal development subset** is formed from the remaining groups; the excluded fold is **not used as an outer evaluation set**. The purpose is configuration selection, **not estimation of held-out generalization**.
3. Fine-tune the encoder and evaluate **development Macro-F1 after each epoch**. Early stopping uses patience 5, with a maximum of 20 epochs; the earliest epoch wins ties.
4. At the selected checkpoint, test the post-hoc logit adjustment `z'_c = z_c - τ log π_c`, where `π_c` is the proportion of class `c` in the training portion of the run, on the internal development set for **τ ∈ {0, 0.25, 0.5, 0.75, 1.0}**. Choose the best development Macro-F1 (lower τ wins ties).
5. Consolidate the 15 runs into the **median chosen epoch** and the **mode chosen τ** (lower value breaks mode ties). Fresh final fine-tuning then uses the **full training split** and **seed 42**, without early stopping, with the class proportions of the full training split; the resulting model is evaluated on the held-out test partition.

The shared configuration (Table **6.2**) is **AdamW**, learning rate **2e-5**, weight decay **0.01**, batch size **8**, maximum sequence length **512**, warm-up ratio **0.1**, linear learning-rate scheduler, cross-entropy loss, float32, and gradient clipping at norm **1.0**. For final training, the scheduler keeps a **20-epoch theoretical horizon**, even if fewer epochs are executed.

Run configuration selection for a single model/task pair, followed by final fine-tuning and test evaluation:

```bash
python src/correr.py --tarefa relevance --modelo bertimbau_base
python src/final.py --tarefa relevance --modelo bertimbau_base --guardar-checkpoint checkpoints

python src/correr.py --tarefa entailment --modelo xlmr_large_xnli
python src/final.py --tarefa entailment --modelo xlmr_large_xnli --guardar-checkpoint checkpoints
```

To reproduce the **full comparison**, repeat **both** commands for every key above and for **both** values of `--tarefa`: `relevance` and `entailment`. This corresponds to **22 model–task combinations**, each with 15 configuration-selection runs, i.e. **330 configuration-selection training runs**, plus **22 final runs**. `correr.py` saves each fold as it closes, so an interrupted run resumes from the folds already saved.

The runs write:

```text
outputs/resultados.jsonl                       # correr.py: one record per task and model, with the 15 selected epochs and τ values
outputs/parciais/<task>__<model>.jsonl         # correr.py: the folds closed so far, deleted once the record is written
outputs/final/<task>__<model>_resultado.json   # final.py: test results, confusion matrix and measured cost
checkpoints/<task>_<model>/                    # final.py --guardar-checkpoint: weights, tokenizer, configuration and COMO_USAR.json
```

`final.py` takes the epochs and τ from the `correr.py` record of the same task and model, and does nothing if its result file already exists (delete it to run again).

## 6. Metrics, figures and execution cost

**Macro-F1** is the primary task comparison metric, because the labels are imbalanced. The relevance task also reports `F1 Relevant`, `F1 Irrelevant`, `Relevant Recall`, and **decisive-evidence Recall** (the share of test pairs annotated Supported or Refuted that are predicted Relevant). The entailment task reports the three per-class F1 values.

For Macro-F1 uncertainty, the dissertation uses **400 grouped bootstrap samples at claim-span level**, with **95% percentile confidence intervals**; the intervals are reported for Claim-Evidence Entailment (Table 6.6).

After the final runs, generate the entailment confusion matrix and the resource report:

```bash
python src/figura_matriz_confusao.py
python src/resumo_carbono.py
```

`figura_matriz_confusao.py` draws **Figure 6.3** from the matrix stored in `outputs/final/entailment__xlmr_large_xnli_resultado.json` and writes `outputs/figuras/matriz_confusao_entailment_xlmr_large_xnli.png` and `.pdf`. `resumo_carbono.py` sums the CodeCarbon measurements stored in `outputs/resultados.jsonl` and `outputs/final/*_resultado.json` for each phase (configuration selection, and final training + test), as in the computational-cost analysis of **Table 6.3**. The dissertation reports **27.68 total execution hours**, **12.416 kWh** and an estimated **2.056 kg CO2 eq** for the experimental campaign of the 22 model–task combinations. CodeCarbon also writes one row per measured block to `outputs/emissoes/emissions.csv`. Figures **6.1 and 6.2** illustrate passage construction and the characterization pipeline and are not generated by the code.

## 7. Results

The tables are copied from the dissertation, with its bold values. In Table 6.5, F1 Rel. and F1 Irr. are the F1 of the Relevant and Irrelevant classes, R Rel. the Recall of the Relevant class and Decisive R the decisive-evidence Recall; in Table 6.6, F1 S, F1 R and F1 NEI are the F1 of Supported, Refuted and NEI.

### Document relevance (Section 6.3.1)

Table 6.5: Final results for document relevance classification.

| Model | Macro-F1 | F1 Rel. | F1 Irr. | R Rel. | Decisive R |
|---|:---:|:---:|:---:|:---:|:---:|
| *Three-class NLI* | | | | | |
| mDeBERTa-v3-XNLI | 0.6253 | 0.414 | 0.836 | 0.371 | 0.382 |
| MiniLM-v2-XNLI | 0.5436 | 0.247 | 0.840 | 0.177 | 0.147 |
| XLM-R-large-XNLI | 0.5753 | 0.304 | 0.846 | 0.226 | 0.206 |
| XLM-R-large-XNLI-ANLI | 0.5864 | 0.309 | 0.863 | 0.210 | 0.147 |
| *Binary textual inference* | | | | | |
| BERTimbau-large-ASSIN2 | 0.6254 | 0.382 | 0.869 | 0.274 | 0.176 |
| mDeBERTa-v3-ASSIN2 | 0.5707 | 0.327 | 0.814 | 0.290 | 0.265 |
| *Without prior inference specialization* | | | | | |
| Albertina-100M | 0.5549 | 0.259 | 0.851 | 0.177 | 0.147 |
| Albertina-900M | 0.5548 | 0.325 | 0.784 | 0.323 | 0.324 |
| BERTimbau-base | **0.7098** | **0.549** | 0.871 | **0.500** | **0.500** |
| BERTimbau-large | 0.6907 | 0.495 | **0.887** | 0.371 | 0.324 |
| Serafim-335M-ptpt | 0.7016 | 0.524 | 0.879 | 0.435 | 0.294 |

### Passage-level Claim-Evidence Entailment (Section 6.3.2)

Table 6.6: Final results for Claim-Evidence Entailment on the three-sentence passages constructed from the annotated CLEVER evidence excerpts. The 95% confidence intervals for Macro-F1 are estimated by grouped bootstrap at claim-span level.

| Model | Macro-F1 | 95% CI | F1 S | F1 R | F1 NEI |
|---|:---:|:---:|:---:|:---:|:---:|
| *Three-class NLI* | | | | | |
| mDeBERTa-v3-XNLI | 0.4741 | [0.3093, 0.6285] | 0.448 | 0.364 | 0.611 |
| MiniLM-v2-XNLI | 0.3787 | [0.2225, 0.5718] | 0.400 | 0.118 | 0.619 |
| XLM-R-large-XNLI | **0.5212** | [**0.3160**, **0.6637**] | 0.462 | 0.429 | **0.673** |
| XLM-R-large-XNLI-ANLI | 0.4217 | [0.2758, 0.5628] | 0.449 | 0.143 | **0.673** |
| *Binary textual inference* | | | | | |
| BERTimbau-large-ASSIN2 | 0.3492 | [0.2298, 0.4616] | 0.393 | 0.083 | 0.571 |
| mDeBERTa-v3-ASSIN2 | 0.3439 | [0.2618, 0.4287] | **0.492** | 0.000 | 0.539 |
| *Without prior inference specialization* | | | | | |
| Albertina-100M | 0.4180 | [0.1890, 0.5526] | 0.295 | **0.471** | 0.488 |
| Albertina-900M | 0.3808 | [0.2520, 0.5211] | 0.441 | 0.133 | 0.568 |
| BERTimbau-base | 0.3434 | [0.2235, 0.4887] | 0.441 | 0.000 | 0.589 |
| BERTimbau-large | 0.2534 | [0.1778, 0.3331] | 0.437 | 0.000 | 0.324 |
| Serafim-335M-ptpt | 0.3567 | [0.2273, 0.4945] | **0.492** | 0.000 | 0.578 |

## Dissertation reference

For the training protocol, passage-construction examples and discussion, see **Chapter 6**, particularly **Sections 6.1–6.4**, **Tables 6.1–6.6** and **Figures 6.1–6.3**. The CLEVER evidence benchmark is described in **Sections 3.2.2–3.2.4**. See the [main repository README](../../README.md#citation) for citation details.
