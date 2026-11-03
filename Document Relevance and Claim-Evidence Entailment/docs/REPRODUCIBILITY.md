# Reproducing document relevance and Claim-Evidence Entailment experiments

This document complements the [stage README](../README.md) with the data requirements, configuration-selection protocol, commands and the complete results of this code for the two evidence-characterization tasks. **Run all commands from `Document Relevance and Claim-Evidence Entailment/`, not from `docs/`.**

## 1. Environment and prerequisites

The reported runs used one **NVIDIA GeForce RTX 5070 (12 GB)**, with torch 2.10.0 (CUDA 12.8 build) and transformers 5.6.2 as pinned in `requirements.txt`, and their resource consumption was recorded with CodeCarbon. `configs/modelos.yaml` declares, per model, the memory-saving options implemented in `src/motor.py`: gradient checkpointing and, for Albertina-900M, AdamW with its master weights and moments on the CPU. The training entry points (`correr.py` and `final.py`) require CUDA; data preparation and analysis scripts run on CPU.

```bash
python -m venv .venv
source .venv/bin/activate
pip install torch==2.10.0 --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements.txt
python -m nltk.downloader punkt_tab   # Punkt data for the sentence split of the entailment passages
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

Only three-class natural language inference (NLI) heads are reused, and only for Claim-Evidence Entailment, so both tasks give these two checkpoints new classification heads and the replacement label names are not used as task labels.

## 2. CLEVER data and fixed partitions

The code expects the following inputs relative to this stage directory:

```text
../CLEVER/clever.json
../CLEVER/clever_train.json
../CLEVER/clever_test.json
```

`python src/construir_dados.py --clever <folder>` reads them from another folder. **CLEVER and LUSA content are not redistributed** in this code repository; obtain them according to the dataset's access conditions and the [root README](../../README.md#data). In `clever.json`, each claim span has its `retrieved_documents`, and the code reads `lusa_doc_id`, `headline`, `content`, `relevant`, `relation` and `evidence_excerpts` from each retrieved document, using the `text` of each excerpt.

The **predefined evidence-characterization benchmark split** is distinct from the 40/100 claim-span split used in Question Generation:

| Input unit | Training | Test | Total |
|---|---:|---:|---:|
| CLEVER claim spans | 114 | 26 | 140 |
| Claim span–document pairs | 1,015 | 254 | 1,269 |
| Relevant pairs | 250 | 62 | 312 |
| Irrelevant pairs | 765 | 192 | 957 |
| Deduplicated three-sentence evidence passages | 426 | 82 | 508 |
| Claim spans with evidence passages | 90 | 23 | 113 |

The partition was constructed to approximate an **80/20** split, grouping source articles that share retrieved LUSA documents so that **no retrieved LUSA document appears in both training and test**. The code reads it from `clever_train.json` and `clever_test.json`.

CLEVER contains **527 manually annotated evidence excerpts**, 444 in training and 83 in test. Passage construction around those excerpts followed by within-pair deduplication removes **19** duplicates (18 in training, 1 in test), leaving **508** passages: **145 Supported, 42 Refuted and 239 NEI** in training, and **32 Supported, 9 Refuted and 41 NEI** in test.

## 3. Prepare the data

```bash
python src/construir_dados.py      # claim span–document pairs of both partitions
python src/folds.py                # task examples and grouped folds (3 seeds × 5 folds)
python src/diagnostico_janelas.py  # coverage of the training excerpts by sentence windows
python src/inventario.py           # model table of the eleven encoders, with parameter counts
```

Main generated files:

```text
data/pares.jsonl                # Claim span–document classification pairs, with their partition
data/folds_relevance.json       # Grouped relevance-selection folds
data/folds_entailment.json      # Grouped entailment-selection folds
```

`construir_dados.py` prints, for each partition, the number of claims, claim spans, pairs per label and annotated excerpts per label. `folds.py` builds the examples of both tasks from the training partition (every pair for relevance; for entailment, one three-sentence window per annotated excerpt, deduplicated within each pair), assigns whole source-article groups to five folds for each seed, balancing fold size and class counts, and prints the size and class counts of every fold. `diagnostico_janelas.py` prints how many of the 444 training excerpts are contained in some window of one, two and three consecutive sentences: 372 (83.8%), 430 (96.8%) and 443 (99.8%). The remaining excerpt spans three sentences, and Punkt splits it between a question mark and the closing quotation mark that follows it; the window joins those sentences with one space, so it differs from the excerpt only by that space. `inventario.py` counts the parameters of each checkpoint, loaded on the CPU, and takes the other columns from `configs/modelos.yaml`; every checkpoint must load, including the two ASSIN2 checkpoints (see [Model-loading compatibility](#model-loading-compatibility)).

## 4. Tasks and passage construction

**Document relevance** is binary classification of `(claim span, retrieved LUSA document)` into `Relevant` or `Irrelevant`. A Relevant document is pertinent to the factual situation, but need not support or refute the claim. An Irrelevant document does not address that situation, which is what separates it from NEI evidence: pertinent, but insufficient to support or refute the claim. The premise is the news headline followed by the first 380 words of the body.

**Claim-Evidence Entailment** is three-class classification of `(passage, claim span)` into `Supported`, `Refuted` or `NEI`. The passage is the **premise** and the claim span the **hypothesis**. The news text is split into sentences with NLTK's Punkt model for Portuguese (`sent_tokenize(text, language="portuguese")`, `nltk==3.10.0`), and a passage is three consecutive sentences, each with its whitespace collapsed, joined by one space, without the news headline. In the supervised experiments, each annotated excerpt determines the location of its passage and gives it its label: the window holds the sentences the excerpt touches, centred on them where possible and shifted inward at document boundaries, and a document of three sentences or fewer gives a single passage with all of them. Duplicate windows from the same pair are removed. Three sentences is the smallest window that holds the sentences of every annotated training excerpt: 372 of the 444 excerpts lie within one sentence, 430 within two consecutive sentences and all 444 within three. Every test excerpt also touches at most three sentences. Both tasks give the encoder the pair `(premise, claim span)`, truncated to 512 tokens.

Without manually identified excerpt locations, as in the FACT-PT prototype, the classifier is instead applied to every three-sentence passage of each document predicted Relevant, with a stride of one sentence; these passages must be built from the same Punkt sentence split as the training passages. The subsequent consolidation retains the passages predicted Supported or Refuted; if all passages of a document are predicted NEI, it retains the one whose NEI logit exceeds the larger of its Supported and Refuted logits by the smallest margin, after the logit adjustment of [section 5](#5-model-configuration-selection). This consolidation is implemented in [`FACT-PT/`](../../FACT-PT/).

## 5. Model configuration selection

The eleven model keys from `configs/modelos.yaml` are:

```text
mdeberta_xnli         minilm_xnli        xlmr_large_xnli
xlmr_large_xnli_anli  assin2_mdeberta    assin2_bertimbau
albertina_100m        albertina_900m     bertimbau_base
bertimbau_large       serafim_335m
```

`mdeberta_xnli`, `minilm_xnli`, `xlmr_large_xnli` and `xlmr_large_xnli_anli` are multilingual checkpoints fine-tuned for three-class NLI; `assin2_mdeberta` and `assin2_bertimbau` were fine-tuned for binary textual inference on the Portuguese ASSIN2 dataset; the other five are Portuguese encoders without prior inference specialization, `serafim_335m` being a sentence encoder trained for semantic similarity. Document relevance gives every encoder a new two-class output layer. Claim-Evidence Entailment keeps the output layer of the four NLI checkpoints, with entailment, contradiction and neutral mapped to Supported, Refuted and NEI, and gives the other encoders a new three-class layer. In both tasks the whole encoder is fine-tuned.

For **each model and each task**:

1. Create **five grouped folds** for each of **seeds 42, 43 and 44** (15 configuration-selection runs). Groups are based on the CLEVER source article of the claim.
2. In each run, one fold is the **internal development set** and the other four folds are the training set, so every fold is the development set once per seed. Each run therefore trains on about 80% of the training partition (805 to 818 pairs for relevance, 335 to 344 passages for entailment) and uses the remaining 20% for development. The purpose is configuration selection, **not estimation of held-out generalization**: the development Macro-F1 is measured on the same fold that chooses the epoch and τ.
3. Fine-tune the encoder and evaluate **development Macro-F1 after each epoch**. Early stopping uses patience 5, with a maximum of 20 epochs; the earliest epoch wins ties.
4. At the selected checkpoint, test the post-hoc logit adjustment `z'_c = z_c - τ log π_c`, where `π_c` is the proportion of class `c` in the training folds of the run, on the internal development set for **τ ∈ {0, 0.25, 0.5, 0.75, 1.0}**. Choose the best development Macro-F1 (lower τ wins ties).
5. Consolidate the 15 runs into the **median chosen epoch** and the **mode chosen τ** (lower value breaks mode ties). Fresh final fine-tuning then uses the **full training split** and **seed 42**, without early stopping, with the class proportions of the full training split; the resulting model is evaluated on the held-out test partition.

The shared training configuration is **AdamW**, learning rate **2e-5**, weight decay **0.01**, batch size **8**, maximum sequence length **512**, warm-up ratio **0.1**, linear learning-rate scheduler, cross-entropy loss, float32, and gradient clipping at norm **1.0**. For final training, the scheduler keeps a **20-epoch theoretical horizon**, even if fewer epochs are executed.

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
outputs/final/<task>__<model>_previsoes.jsonl  # final.py: one line per test example, with its gold label, predicted label and logits
checkpoints/<task>_<model>/                    # final.py --guardar-checkpoint: weights, tokenizer, configuration and COMO_USAR.json
```

`final.py` takes the epochs and τ from the `correr.py` record of the same task and model, and does nothing if its result file already exists (delete it to run again).

## 6. Metrics, baselines, figures and execution cost

**Macro-F1**, the unweighted mean of the per-class F1 values, is the primary task comparison metric, because the labels are imbalanced. The relevance task also reports `F1 Relevant`, `F1 Irrelevant`, `Relevant Recall`, and **decisive-evidence Recall** (the share of test pairs annotated Supported or Refuted that are predicted Relevant). The entailment task reports the three per-class F1 values.

For Macro-F1 uncertainty, `final.py` stores a **95% percentile confidence interval** computed with `scipy.stats.bootstrap`: **10,000 resamples** of the test claim spans with replacement (seed 42), each drawn claim span contributing all its test examples. The [results](#7-results) report it for both tasks.

The [baselines](#baselines) need the final runs of BERTimbau-base for relevance and XLM-R-large-XNLI for entailment:

```bash
python src/baselines.py
```

`baselines.py` reads the test predictions of these two models and writes `outputs/baselines.json`. Document relevance is compared with the majority class of the training partition (Irrelevant) and with stratified random prediction. Claim-Evidence Entailment is compared with the `joeddav/xlm-roberta-large-xnli` checkpoint without fine-tuning, which keeps its own NLI head (entailment → Supported, contradiction → Refuted, neutral → NEI) and receives the same premises, hypotheses and tokenization as the fine-tuned model, and with stratified random prediction. Stratified random prediction assigns each class at random with its proportion in the training partition (Relevant: 250 of 1,015 pairs; Supported, Refuted and NEI: 145, 42 and 239 of 426 passages), and its Macro-F1 is the exact expected value over such predictions. Every system uses the same bootstrap resamples, so the confidence interval of the Macro-F1 difference between the fine-tuned XLM-R-large-XNLI and stratified random prediction is paired. The checkpoint without fine-tuning runs on the GPU when one is available.

After the final runs, generate the entailment confusion matrix and the resource report:

```bash
python src/figura_matriz_confusao.py
python src/resumo_carbono.py
```

`figura_matriz_confusao.py` draws the confusion matrix of the XLM-R-large-XNLI entailment test predictions, stored in `outputs/final/entailment__xlmr_large_xnli_resultado.json`, and writes `outputs/figuras/matriz_confusao_entailment_xlmr_large_xnli.png` and `.pdf`. `resumo_carbono.py` sums the CodeCarbon measurements stored in `outputs/resultados.jsonl` and `outputs/final/*_resultado.json` for each phase: configuration selection, and final training + test. CodeCarbon runs in offline mode with the carbon intensity of Portugal and also writes one row per measured block to `outputs/emissoes/emissions.csv`. For the 22 model–task combinations of the [results](#7-results), on the GPU of [section 1](#1-environment-and-prerequisites):

| Phase | Training runs | Execution hours | kWh | % energy | kg CO2eq |
|---|---:|---:|---:|---:|---:|
| Configuration selection | 330 | 56.61 | 13.643 | 96.42 | 2.259 |
| Final training + test | 22 | 2.13 | 0.506 | 3.58 | 0.084 |
| Total | 352 | 58.74 | 14.150 | 100.00 | 2.343 |

The table printed by `resumo_carbono.py` counts records rather than training runs: one per model–task combination in each phase (22, 22 and 44 in all), each configuration-selection record covering its 15 training runs.

## 7. Results

Test results of the final model of each encoder and task, configured with the protocol of [section 5](#5-model-configuration-selection). The 95% confidence intervals for Macro-F1 are estimated by grouped bootstrap at claim-span level ([section 6](#6-metrics-baselines-figures-and-execution-cost)). In each metric column, bold marks the best value over the 11 encoders (ties: all); the confidence intervals are not marked. F1 Rel. and F1 Irr. are the F1 of the Relevant and Irrelevant classes, R Rel. the Recall of the Relevant class and Decisive R the decisive-evidence Recall; F1 S, F1 R and F1 NEI are the F1 of Supported, Refuted and NEI.

### Document relevance

Test partition: 254 claim span–document pairs from 26 claim spans, 62 of them Relevant.

| Model | Macro-F1 | 95% CI | F1 Rel. | F1 Irr. | R Rel. | Decisive R |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| *Three-class NLI* | | | | | | |
| mDeBERTa-v3-XNLI | 0.6042 | [0.5280, 0.6742] | 0.369 | 0.840 | 0.306 | 0.324 |
| MiniLM-v2-XNLI | 0.6034 | [0.5138, 0.6803] | 0.374 | 0.833 | 0.323 | 0.353 |
| XLM-R-large-XNLI | 0.5978 | [0.5310, 0.6608] | 0.362 | 0.834 | 0.306 | 0.324 |
| XLM-R-large-XNLI-ANLI | 0.4829 | [0.4183, 0.5531] | 0.127 | 0.839 | 0.081 | 0.088 |
| *Binary textual inference* | | | | | | |
| BERTimbau-large-ASSIN2 | 0.7060 | [0.5959, 0.8091] | 0.541 | 0.872 | 0.484 | 0.471 |
| mDeBERTa-v3-ASSIN2 | 0.4698 | [0.4121, 0.5407] | 0.086 | 0.854 | 0.048 | 0.059 |
| *Without prior inference specialization* | | | | | | |
| Albertina-100M | 0.6213 | [0.5282, 0.6931] | 0.359 | 0.884 | 0.226 | 0.265 |
| Albertina-900M | 0.4458 | [0.4006, 0.5040] | 0.031 | 0.860 | 0.016 | 0.029 |
| BERTimbau-base | 0.6835 | [0.5856, 0.7649] | 0.520 | 0.847 | **0.516** | **0.529** |
| BERTimbau-large | **0.7174** | [0.6322, 0.7853] | **0.542** | **0.893** | 0.419 | 0.441 |
| Serafim-335M-ptpt | 0.6569 | [0.5882, 0.7244] | 0.442 | 0.872 | 0.339 | 0.353 |

The final Albertina-900M model predicts Irrelevant for 252 of the 254 test pairs: in 5 of its 15 configuration-selection runs the development Macro-F1 never rose above that of predicting Irrelevant for every pair, and its 2 selected epochs (the median of the 15 best epochs) end with the warm-up, so the final model trains only while the learning rate is still rising.

### Passage-level Claim-Evidence Entailment

Test partition: 82 three-sentence passages from 23 claim spans (32 Supported, 9 Refuted, 41 NEI).

| Model | Macro-F1 | 95% CI | F1 S | F1 R | F1 NEI |
|---|:---:|:---:|:---:|:---:|:---:|
| *Three-class NLI* | | | | | |
| mDeBERTa-v3-XNLI | 0.4550 | [0.3040, 0.5947] | 0.421 | 0.333 | 0.611 |
| MiniLM-v2-XNLI | 0.3258 | [0.2043, 0.4487] | 0.400 | 0.000 | 0.577 |
| XLM-R-large-XNLI | **0.4815** | [0.3179, 0.6021] | 0.451 | **0.500** | 0.494 |
| XLM-R-large-XNLI-ANLI | 0.4748 | [0.3320, 0.6062] | 0.462 | 0.444 | 0.519 |
| *Binary textual inference* | | | | | |
| BERTimbau-large-ASSIN2 | 0.3183 | [0.1965, 0.4404] | 0.353 | 0.000 | 0.602 |
| mDeBERTa-v3-ASSIN2 | 0.3223 | [0.1788, 0.4584] | 0.491 | 0.000 | 0.476 |
| *Without prior inference specialization* | | | | | |
| Albertina-100M | 0.3026 | [0.1997, 0.4016] | 0.444 | 0.000 | 0.463 |
| Albertina-900M | 0.3469 | [0.2223, 0.4533] | 0.466 | 0.000 | 0.575 |
| BERTimbau-base | 0.3208 | [0.1750, 0.4213] | **0.596** | 0.000 | 0.367 |
| BERTimbau-large | 0.3641 | [0.2263, 0.5093] | 0.426 | 0.000 | 0.667 |
| Serafim-335M-ptpt | 0.3934 | [0.2175, 0.5525] | 0.326 | 0.182 | **0.673** |

Every selected configuration has τ = 0, so no final model adjusts its logits; the selected numbers of epochs range from 2 to 9 for relevance and from 3 to 6 for entailment. GPU training is not bit-for-bit reproducible, so a rerun with the same seed and configuration can give different test scores.

### Baselines

Results of `baselines.py` ([section 6](#6-metrics-baselines-figures-and-execution-cost)) on the same test partitions; the rows of the fine-tuned models repeat the tables above.

| Task | Model | Macro-F1 | 95% CI |
|---|---|:---:|:---:|
| Document relevance | BERTimbau-base, fine-tuned | 0.6835 | [0.5856, 0.7649] |
| | Majority class | 0.4305 | [0.3975, 0.4555] |
| | Stratified random | 0.4995 | [0.4928, 0.4995] |
| Claim-Evidence Entailment | XLM-R-large-XNLI, fine-tuned | 0.4815 | [0.3179, 0.6021] |
| | XLM-R-large-XNLI, without fine-tuning | 0.4784 | [0.3210, 0.6311] |
| | Stratified random | 0.3300 | [0.3070, 0.3311] |

The Macro-F1 difference between the fine-tuned XLM-R-large-XNLI and stratified random prediction is 0.1516, with a paired 95% confidence interval of [-0.0042, 0.2774]. For stratified random prediction, each resample recomputes the expected Macro-F1 on the resampled claim spans. That expected value is highest when the class proportions of the test examples equal those of the training partition, so the resamples raise it at most slightly and its value lies near the upper end of its interval.
