# Document Relevance and Claim-Evidence Entailment

This directory contains the code for **evidence characterization** in European Portuguese fact-checking. After [evidence retrieval](../Evidence%20Retrieval/), two tasks are evaluated independently:

1. **Document relevance:** classify a claim span–document pair as **Relevant** or **Irrelevant**.
2. **Claim-Evidence Entailment:** classify a three-sentence passage from a Relevant document as **Supported**, **Refuted**, or **Not Enough Information (NEI)** with respect to the claim span. The passage is the premise and the claim span is the hypothesis.

The experiments address **RQ4** of the dissertation, comparing **11 pretrained encoders** with and without prior specialization in textual inference. Both tasks use CLEVER annotations, but each model is fine-tuned separately for each task.

**Released models**, also used by [FACTA-PT](https://factapt.inesctec.pt):
- **Document relevance:** [BERTimbau-base](https://huggingface.co/liaad/facta-pt-relevance-bertimbau-base)
- **Claim-Evidence Entailment:** [XLM-R-large-XNLI](https://huggingface.co/liaad/facta-pt-cee-xlm-roberta-large-xnli)

## Experimental overview

| Component | Description |
|---|---|
| Dataset | CLEVER: **1,269** annotated claim span–document pairs (**312 Relevant**, **957 Irrelevant**), with **527** manually annotated evidence excerpts in Relevant documents. |
| Fixed evaluation split | **114 training / 26 test claim spans**, grouped to prevent retrieved LUSA documents from appearing in both partitions. This is **different from the 40/100 split** used for question generation. |
| Document relevance | Binary classification of claim span–document pairs; the test partition contains **254 pairs**. |
| Claim-Evidence Entailment | Three-class classification on deduplicated **three-sentence passages** anchored to manually annotated excerpts; **425 training / 82 test** passages. |
| Model selection | For each model and task: **3 seeds × 5 grouped partitions** for selecting training epochs and a post-hoc logit-adjustment strength; final evaluation on the held-out test partition. |
| Metrics | **Macro-F1** (primary), class-wise F1, Relevant Recall and decisive-evidence Recall; grouped-bootstrap confidence intervals for Macro-F1. |

The entailment **test results use passages constructed around known reference evidence locations**. In the FACTA-PT pipeline, where these locations are unknown, the classifier operates on overlapping three-sentence windows of documents predicted Relevant.

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
  metricas.py           Evaluation metrics and grouped bootstrap
  figura_matriz_confusao.py  Create the entailment confusion matrix
  resumo_carbono.py     Summarise execution cost and emissions
  motor.py              Model, classification head and one configuration-selection run
  entradas.py           Premise and hypothesis texts
  conjuntos.py          Read the pairs of a partition
  grelhas.py            Read the configuration files and the folds
  carbono.py            CodeCarbon measurement
docs/REPRODUCIBILITY.md  Data, protocol, commands in run order and the complete Tables 6.5–6.6
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

Running the data-preparation scripts creates `data/pares.jsonl`, `data/folds_relevance.json` and `data/folds_entailment.json`. The code **reads the predefined train/test partition** (Section 3.2.4) from `clever_train.json` and `clever_test.json`.

## Installation

Run from `Document Relevance and Claim-Evidence Entailment/`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install torch==2.10.0 --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements.txt
```

Training (`correr.py` and `final.py`) requires a CUDA GPU; the other scripts run on CPU. The experiments were run on the Deucalion supercomputer, on NVIDIA A100-SXM4 GPUs with **40 GB and 80 GB** of memory. Model checkpoints are loaded from Hugging Face (see `configs/modelos.yaml`); offline execution requires them to be cached first. Two ASSIN2 checkpoints need a one-off fix of their cached `config.json` to load with the `transformers` release pinned in `requirements.txt`; the procedure is in [Reproducing the experiments](docs/REPRODUCIBILITY.md#model-loading-compatibility).

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

Each `final.py` run writes `outputs/final/<task>__<model>_resultado.json` and, with `--guardar-checkpoint`, saves the model under `checkpoints/<task>_<model>/`. For all 11 encoders, configuration-selection details, figure generation and resource accounting, see [Reproducing the experiments](docs/REPRODUCIBILITY.md).

## Main results

**Document relevance** - selected comparisons on the test partition (dissertation **Table 6.5**):

| Model | Macro-F1 ↑ | F1 Relevant ↑ | Relevant Recall ↑ | Decisive Recall ↑ |
|---|---:|---:|---:|---:|
| BERTimbau-base | **0.7098** | **0.549** | **0.500** | **0.500** |
| Serafim-335M-ptpt | 0.7016 | 0.524 | 0.435 | 0.294 |
| BERTimbau-large | 0.6907 | 0.495 | 0.371 | 0.324 |
| mDeBERTa-v3-XNLI | 0.6253 | 0.414 | 0.371 | 0.382 |

**Passage-level Claim-Evidence Entailment** - selected comparisons on **82 test passages** (dissertation **Table 6.6**):

| Model | Macro-F1 ↑ | 95% CI | F1 Supported ↑ | F1 Refuted ↑ | F1 NEI ↑ |
|---|---:|---|---:|---:|---:|
| XLM-R-large-XNLI | **0.5212** | [**0.3160**, **0.6637**] | 0.462 | 0.429 | **0.673** |
| mDeBERTa-v3-XNLI | 0.4741 | [0.3093, 0.6285] | 0.448 | 0.364 | 0.611 |
| Albertina-100M | 0.4180 | [0.1890, 0.5526] | 0.295 | **0.471** | 0.488 |
| BERTimbau-base | 0.3434 | [0.2235, 0.4887] | 0.441 | 0.000 | 0.589 |

Bold values are those marked in the dissertation tables. BERTimbau-base and XLM-R-large-XNLI obtain the **highest observed test Macro-F1** in their respective tasks and were retained for FACTA-PT.

The complete Tables 6.5 and 6.6, with all 11 encoders, are in [Reproducing the experiments](docs/REPRODUCIBILITY.md#7-results).

## Dissertation reference

- **Sections 3.2.2–3.2.4:** CLEVER evidence annotations and fixed benchmark split.
- **Chapter 6:** Task formulation, experimental protocol, results and discussion.
- **Figures 6.1–6.3:** Passage construction, pipeline and entailment confusion matrix.

For the dissertation citation and the full FACTA-PT workflow, see the [main repository README](../README.md#citation).
