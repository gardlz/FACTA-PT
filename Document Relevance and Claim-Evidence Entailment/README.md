# Document Relevance and Claim-Evidence Entailment

This directory contains the code for **evidence characterization** in European Portuguese fact-checking. After [evidence retrieval](../Evidence%20Retrieval/), two tasks are evaluated independently:

1. **Document relevance:** classify a claim span–document pair as **Relevant** or **Irrelevant**.
2. **Claim-Evidence Entailment:** classify a three-sentence passage from a Relevant document as **Supported**, **Refuted**, or **Not Enough Information (NEI)** with respect to the claim span. The passage is the premise and the claim span is the hypothesis.

The experiments compare **11 pretrained encoders** with and without prior specialization in textual inference: four multilingual checkpoints fine-tuned for three-class natural language inference (NLI), two fine-tuned for binary textual inference on the Portuguese ASSIN2 dataset, and five Portuguese encoders without prior inference specialization. Both tasks use CLEVER annotations, but each model is fine-tuned separately for each task.

**Released models**, also used by [FACT-PT](https://factpt.inesctec.pt):
- **Document relevance:** [BERTimbau-base](https://huggingface.co/liaad/facta-pt-relevance-bertimbau-base)
- **Claim-Evidence Entailment:** [XLM-R-large-XNLI](https://huggingface.co/liaad/facta-pt-cee-xlm-roberta-large-xnli)

## Experimental overview

| Component | Description |
|---|---|
| Dataset | CLEVER: **1,269** annotated claim span–document pairs (**312 Relevant**, **957 Irrelevant**), with **527** manually annotated evidence excerpts in Relevant documents. |
| Fixed evaluation split | **114 training / 26 test claim spans**, grouped to prevent retrieved LUSA documents from appearing in both partitions. This is **different from the 40/100 split** used for question generation. |
| Document relevance | Binary classification of claim span–document pairs: **1,015 training pairs** from 114 claim spans and **254 test pairs** from 26 claim spans. |
| Claim-Evidence Entailment | Three-class classification on deduplicated **three-sentence passages** anchored to manually annotated excerpts, with sentences split by NLTK's Punkt model for Portuguese: **426 training passages** from 90 claim spans and **82 test passages** from 23 claim spans. |
| Model selection | For each model and task: **3 seeds × 5 grouped folds**. Each fold is in turn the development set, which selects the number of training epochs and a post-hoc logit-adjustment strength, while the other four folds train. The final model is trained on the whole training partition and evaluated on the held-out test partition. |
| Baselines | Majority class and stratified random prediction for document relevance; XLM-R-large-XNLI without fine-tuning and stratified random prediction for Claim-Evidence Entailment. |
| Metrics | **Macro-F1** (primary), class-wise F1, Relevant Recall and decisive-evidence Recall; 95% confidence intervals for Macro-F1 by grouped bootstrap over the test claim spans (10,000 resamples). |

Decisive-evidence Recall is the share of test pairs annotated Supported or Refuted that are predicted Relevant.

The entailment **test results use passages constructed around known reference evidence locations**. In the FACT-PT pipeline, where these locations are unknown, the classifier operates on overlapping three-sentence windows of documents predicted Relevant.

The complete selection protocol, commands and required inputs are in [Reproducing the experiments](docs/REPRODUCIBILITY.md).

## Repository structure

```text
configs/               Model definitions and experimental protocol
src/                   Data preparation, folds, model training and evaluation
  construir_dados.py    Build claim span–document pairs and read fixed partitions
  folds.py              Prepare grouped folds and entailment passages
  diagnostico_janelas.py  Coverage of the training excerpts by sentence windows
  inventario.py         Model table of the eleven encoders, with parameter counts
  correr.py             Select epochs and logit adjustment for one model/task
  final.py              Final fine-tuning and held-out test evaluation
  baselines.py          Majority-class, stratified-random and unfine-tuned baselines
  metricas.py           Evaluation metrics and grouped bootstrap
  figura_matriz_confusao.py  Create the entailment confusion matrix
  resumo_carbono.py     Summarise execution cost and emissions
  motor.py              Model, classification head and one configuration-selection run
  entradas.py           Premise and hypothesis texts, and the NLTK sentence split
  conjuntos.py          Read the pairs of a partition
  grelhas.py            Read the configuration files and the folds
  carbono.py            CodeCarbon measurement
docs/REPRODUCIBILITY.md  Data, protocol, commands in run order and the complete result tables
requirements.txt        Pinned Python dependencies
```

The model keys, checkpoints, adaptation settings and training configuration are listed in `configs/modelos.yaml` and `configs/protocolo.yaml`. Some identifiers and command-line options are in Portuguese.

## Data

**Datasets and LUSA news content are not included in this repository.** Obtain CLEVER in accordance with the [main repository instructions](../README.md#data) and its access conditions. Paths below are relative to `Document Relevance and Claim-Evidence Entailment/`:

```text
../CLEVER/clever.json                # Claim spans, retrieved documents and annotations
../CLEVER/clever_train.json          # Fixed training partition
../CLEVER/clever_test.json           # Fixed test partition
```

Running the data-preparation scripts creates `data/pares.jsonl`, `data/folds_relevance.json` and `data/folds_entailment.json`. The code **reads the predefined train/test partition** from `clever_train.json` and `clever_test.json`.

## Installation

Run from `Document Relevance and Claim-Evidence Entailment/`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install torch==2.10.0 --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements.txt
python -m nltk.downloader punkt_tab
```

The last command downloads the Punkt data that splits the news text into sentences for the entailment passages. Training (`correr.py` and `final.py`) requires a CUDA GPU; the other scripts run on CPU. The reported runs used one **NVIDIA GeForce RTX 5070 (12 GB)**, with the memory-saving options that `configs/modelos.yaml` declares per model and `src/motor.py` implements. Model checkpoints are loaded from Hugging Face (see `configs/modelos.yaml`); offline execution requires them to be cached first. Two ASSIN2 checkpoints need a one-off fix of their cached `config.json` to load with the `transformers` release pinned in `requirements.txt`; the procedure is in [Reproducing the experiments](docs/REPRODUCIBILITY.md#model-loading-compatibility).

## Quick start

With the CLEVER data available, prepare the inputs:

```bash
python src/construir_dados.py
python src/folds.py
```

Select the training configuration and evaluate **one model for each task**:

```bash
# Document relevance
python src/correr.py --tarefa relevance --modelo bertimbau_base
python src/final.py --tarefa relevance --modelo bertimbau_base --guardar-checkpoint checkpoints

# Passage-level Claim-Evidence Entailment
python src/correr.py --tarefa entailment --modelo xlmr_large_xnli
python src/final.py --tarefa entailment --modelo xlmr_large_xnli --guardar-checkpoint checkpoints
```

Each `final.py` run writes the test results to `outputs/final/<task>__<model>_resultado.json` and one line per test example to `outputs/final/<task>__<model>_previsoes.jsonl`; with `--guardar-checkpoint`, it also saves the model under `checkpoints/<task>_<model>/`. With both final runs done, compute the baselines of the two tasks:

```bash
python src/baselines.py
```

For all 11 encoders, configuration-selection details, the baselines, figure generation and resource accounting, see [Reproducing the experiments](docs/REPRODUCIBILITY.md).

## Main results

Test results of the two fine-tuned models used by FACT-PT, next to the baselines of each task. Stratified random prediction assigns each class at random with its proportion in the training partition; its value is the expected Macro-F1.

**Document relevance**, on the **254 test pairs** (62 Relevant, 192 Irrelevant):

| Model | Macro-F1 ↑ |
|---|---:|
| BERTimbau-base, fine-tuned | **0.684** |
| Majority class | 0.431 |
| Stratified random | 0.500 |

The fine-tuned BERTimbau-base identifies 32 of the 62 Relevant test pairs.

**Passage-level Claim-Evidence Entailment**, on the **82 test passages** (32 Supported, 9 Refuted, 41 NEI):

| Model | Macro-F1 ↑ |
|---|---:|
| XLM-R-large-XNLI, fine-tuned | **0.482** |
| XLM-R-large-XNLI, without fine-tuning | 0.478 |
| Stratified random | 0.330 |

The Macro-F1 of the fine-tuned XLM-R-large-XNLI has a 95% confidence interval of [0.318, 0.602], and its Macro-F1 difference with stratified random prediction has a 95% confidence interval of [-0.004, 0.277], which includes zero. It identifies 3 of the 9 Refuted test passages.

The confidence intervals come from a grouped bootstrap over the test claim spans. The complete tables, with the 11 encoders of each task, and the baselines with four decimals are in [Reproducing the experiments](docs/REPRODUCIBILITY.md#7-results).

For the full FACT-PT workflow, see the [main repository README](../README.md).
