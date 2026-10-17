# Article Generation

This directory contains the code for **evidence-grounded fact-checking article generation in European Portuguese**. It addresses **RQ5** of the dissertation by studying how classified evidence can be organised into a readable article with traceable citations.

The **Writer** receives a claim span, its context and publication date, evidence passages already labelled **Supported**, **Refuted** or **Not Enough Information (NEI)**, and a **predetermined factual conclusion**. It does **not** retrieve new evidence or decide the claim's veracity. Evidence-based factual statements are linked to their source passages using local citations such as `[E1]` and `[E2]`.

The selected Writer is **Gemma 4 E4B IT**, also used by the [FACTA-PT prototype](https://factapt.inesctec.pt). It is an existing instruction-tuned model, **not a model fine-tuned or released by this repository**.

## Experimental overview

| Component | Description |
|---|---|
| Evaluation data | **140 CLEVER claim spans** with manually annotated LUSA evidence; articles are generated for all 140, while the quantitative model comparison uses the **113** claim spans with at least one evidence passage. |
| Writer comparison | **Eight open-weight models**, evaluated under the same generation protocol without task-specific fine-tuning. |
| Generation strategy | Conservative evidence **deduplication**, a deterministic **content plan**, and a plan-dependent **JSON grammar** for structural control. |
| Ablation study | With Gemma 4 E4B IT: full strategy, without deduplication, without grammar, without plan, and direct generation. |
| Evaluation | **Citation Recall, Citation Precision and Evidence Coverage** using an NLI judge; **Relevance, Comprehensibility and Evidence Presentation** using a Gemini judge. |

The experiments intentionally use **reference evidence annotations** to evaluate the Writer separately from errors of the preceding relevance and factual-relation classifiers. In the end-to-end prototype, evidence is produced by the preceding pipeline stages instead. See [Reproducing the experiments](docs/REPRODUCIBILITY.md) for the full protocol and commands.

## Repository structure

```text
geracao/                     Evidence preparation, planning, prompts and generation
  construir_planos.py        Build deterministic content plans
  gerar_artigos.py           Generate articles with vLLM
  carbono.py                 Generate articles with CodeCarbon monitoring
  auditoria_dedup.py         Audit evidence-deduplication thresholds
  plano.py                   Assemble evidence passages and content plans
  esquema.py                 Build a JSON grammar from each plan
evaluation/                  NLI/Gemini judging, citation metrics and aggregation
  evaluate_articles.py       Run judges and assemble cached evaluations
  aggregate_results.py       Aggregate article-level metrics
docs/REPRODUCIBILITY.md      Commands in run order and the complete Tables 7.4–7.6
requirements.txt             Dependencies for both Python environments
```

Additional generation and evaluation modules implement citation markers, conclusion templates, prompts and cached judge decisions. Some script names and command-line options are in Portuguese; prompts and article text are in European Portuguese.

## Data

**CLEVER annotations and LUSA news content are not included in this repository.** Obtain the data according to the [main repository instructions](../README.md#data) and the applicable access conditions. The paths below are relative to `Article Generation/`:

```text
../CLEVER/clever.json                  # Claim spans and annotated retrieved evidence
../CLEVER/clean_files/<document>.txt   # Source articles used to recover claim context
```

The code uses **Relevant** documents and their annotated excerpts, relations, publication dates and source identifiers. The manual labels used to choose the deduplication threshold are not included; they are needed only to recompute the removal precision of Table 7.4, not to generate articles with the selected threshold. Generated plans, articles, judge caches and evaluations are written under `dados/` and `evaluation/outputs/`.

## Installation

Generation and evaluation require **separate Python environments**, with version-specific packages selected by markers in `requirements.txt`:

```bash
# Generation: Python 3.11 and a CUDA GPU
python3.11 -m venv .venv-geracao
source .venv-geracao/bin/activate
pip install -r requirements.txt

# Evaluation: Python 3.14, the NLI judge and the Gemini API
# Run in a separate shell or deactivate the generation environment first.
python3.14 -m venv .venv-evaluation
source .venv-evaluation/bin/activate
pip install -r requirements.txt
```

The reported generation runs used **vLLM 0.19.1**, **bfloat16** and one **NVIDIA A100-SXM4 40 GB** GPU per run on the Deucalion supercomputer. Writer checkpoints must be cached before offline generation; some require accepting model licences. The Gemini evaluator requires `GEMINI38_FLASH_KEY` in an uncommitted `.env` file in this directory or in the environment. See the [reproduction notes](docs/REPRODUCIBILITY.md#1-environments-model-weights-and-access) for exact checkpoint revisions and setup details.

## Quick start

Run the following commands **from `Article Generation/`**, after obtaining CLEVER and preparing the generation environment and the selected model checkpoint:

```bash
# 1. Construct the content plans (no GPU required)
python geracao/construir_planos.py --todas

# 2. Generate articles with the selected Writer (CUDA GPU)
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false VLLM_WORKER_MULTIPROC_METHOD=spawn
python geracao/carbono.py --modelo google/gemma-4-E4B-it --condicao full
```

To **evaluate** the generated articles, activate `.venv-evaluation`, unset the two offline variables (the NLI judge may need to download), and configure `GEMINI38_FLASH_KEY` for the holistic judge. The detailed evaluation commands, eight-model comparison and ablations are provided in [Reproducing the experiments](docs/REPRODUCIBILITY.md#4-evaluate-the-generated-articles).

## Main results

**Writer comparison** - selected models on the **113 evidence-bearing claim spans** (dissertation **Table 7.5**):

| Model | Citation Recall ↑ | Citation Precision ↑ | Evidence Coverage ↑ | Comprehensibility ↑ | Evidence Presentation ↑ |
|---|---:|---:|---:|---:|---:|
| **Gemma 4 E4B IT** | **0.644** | 0.677 | 0.885 | **4.94** | **4.01** |
| Qwen3.5-9B | 0.590 | **0.753** | **0.902** | 4.77 | 3.56 |
| Qwen3.5-4B | 0.494 | 0.706 | 0.817 | 4.62 | 3.81 |

**Ablation with Gemma 4 E4B IT** - selected metrics (dissertation **Table 7.6**):

| Condition | Citation Recall ↑ | Evidence Coverage ↑ | Evidence Presentation ↑ |
|---|---:|---:|---:|
| **Full** | **0.644** | **0.885** | 4.01 |
| Without deduplication | 0.626 | 0.876 | **4.21** |
| Without grammar | **0.644** | 0.833 | 3.92 |
| Without plan | 0.395 | 0.537 | 2.49 |
| Direct generation | 0.461 | 0.644 | 2.01 |

The **content plan** has the clearest observed contribution to evidence grounding and integration. Gemma was selected for its **overall balance**, not because it leads every metric: Qwen3.5-9B achieves higher Citation Precision and Evidence Coverage. Grounding scores range from **0 to 1**, while article-quality scores range from **1 to 5**. **Citation Precision is calculated only for articles containing citations**, so its number of observations can vary by model.

Complete eight-model results, deduplication calibration, all six metrics and reproduction details are in **Chapter 7, Tables 7.4–7.6** and [Reproducing the experiments](docs/REPRODUCIBILITY.md).

## Dissertation reference

- **Chapter 7:** Evidence-grounded article generation: experimental setup, results and ablation study.
- **Appendix A.6:** Generation prompt, content plan, generated article structure and Article Quality evaluation prompt.
- **Chapter 8:** Integration of the selected Writer into FACTA-PT.

For the dissertation citation and the full pipeline, see the [main repository README](../README.md#citation).
