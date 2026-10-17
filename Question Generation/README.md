# Question Generation

This directory contains the code used to generate **verification questions from claim spans in European Portuguese**. It covers the creation and manual evaluation of silver-standard questions for ClaimPT and the evaluation of 14 language models on CLEVER using zero-shot, 3-shot and supervised fine-tuning approaches.

The experiments address **RQ1 and RQ2** of the dissertation: the effect of gold and synthetic supervision, and the comparison of European Portuguese, other Portuguese and multilingual models. This stage provides the questions subsequently used for [evidence retrieval](../Evidence%20Retrieval/).

**Released model:** [AMALIA-9B-0626-DPO fine-tuned on Gold91+Silver1073](https://huggingface.co/liaad/facta-pt-qg-amalia-9b-0626-dpo), used by the [FACTA-PT prototype](https://factapt.inesctec.pt). Its selection also considers downstream evidence-retrieval performance (Section 5.3.3).

## Experimental overview

| Component | Description |
|---|---|
| Silver question generation | Gemini generates 1,073 verification questions for 522 ClaimPT claim spans. A fixed sample of 104 questions from 50 claim spans is manually evaluated in two dimensions: general question quality and adherence to the CLEVER question-formulation guidelines. |
| Zero-shot and 3-shot | Fourteen models (6 encoder-decoder and 8 decoder-only) generate questions for the same CLEVER test set. |
| Supervised fine-tuning | Models are adapted using 91 manually written CLEVER questions (Gold91), 1,073 synthetic ClaimPT questions (Silver1073), or combinations of both. |
| Model selection and evaluation | A fixed document-level CLEVER split (40 training/development and 100 test claim spans), four-fold cross-validation for the learning rate and the number of epochs, and question-generation metrics on the held-out test set. |

The main comparison uses **Gold91+Silver1073**. Training details, all experiment commands, output locations and the complete result tables are in [Reproducing the experiments](docs/REPRODUCIBILITY.md).

## Repository structure

```text
configs/                 Configurations of the 14 models
src/                     Data preparation, prompts, inference, evaluation and energy summary
qg_kfold/                Cross-validation, learning-rate and epoch selection, and final fine-tuning
silver_generation/       Synthetic question generation and manual evaluation (avaliacao/: the ratings)
split/                   Fixed CLEVER document-level split
split_por_documento.py   Procedure that draws the split
figuras/                 Scripts for dissertation Figures 4.1–4.3
docs/                    Reproduction commands and complete result tables
requirements.txt         Python dependencies
```

The main entry points are `src/prepare_data.py`, `src/run_inference.py`, `src/metrics.py`, `qg_kfold/scripts/train_final.py` and `silver_generation/generate_questions.py`.

## Data

**Datasets are not included in this repository.** Download CLEVER and ClaimPT according to the [main repository instructions](../README.md#data) and their respective access conditions. This stage expects the following files relative to its own directory:

```text
../CLEVER/clever.json
../CLEVER/clean_files/<document>.txt
../ClaimPT/claimpt_train.json
../ClaimPT/claimpt_test.json
../ClaimPT/annotated_clean_txt/<document>.txt
```

The fixed question-generation split is stored in `split/clever_split_ids_seed0.json`. The ClaimPT JSON files contain the silver questions used in the dissertation; regenerating them is optional, and a new run can produce different questions.

## Installation

Run the commands from the `Question Generation/` directory:

```bash
python -m venv .venv
source .venv/bin/activate
pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements.txt
python -c "import nltk; nltk.download('wordnet'); nltk.download('omw-2.0')"
```

The experiments of the dissertation ran on the Deucalion supercomputer with NVIDIA A100-SXM4 80 GB GPUs, using Python 3.11.5, PyTorch 2.10.0 with CUDA 12.8, Transformers 5.6.2, PEFT 0.19.1, Accelerate 1.13.0 and bitsandbytes 0.49.2 (Section 4.3.2). See also [Environment and model access](docs/REPRODUCIBILITY.md#environment-and-model-access).

The model scripts are run with `--offline`: model weights must already be present in the Hugging Face cache, and some models require acceptance of their licences. Model identifiers are defined in `configs/models_encdec.yaml` and `configs/models_decoder.yaml`.

## Quick start

With the datasets in place and the selected model cached, prepare the data and run **one** zero-shot model:

```bash
python src/prepare_data.py

python src/run_inference.py \
    --config configs/models_decoder.yaml \
    --only amalia_9b --regime zero_shot --seed 42 --bf16 --offline

python src/metrics.py \
    --predictions_dir outputs/predictions \
    --metrics_dir outputs/metrics
```

To run the 3-shot variant, change `--regime zero_shot` to `--regime few_shot`. The evaluation summary is written to `outputs/metrics/summary_metrics.csv`.

To generate a **new** silver-question file, set `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) in a `.env` file in this directory, then run:

```bash
python silver_generation/generate_questions.py \
    --input ../ClaimPT/claimpt_train.json \
    --output silver_generation/outputs/claimpt_train_silver_questions.jsonl
```

Do not commit `.env` or API credentials. This command writes a new output file and does **not** replace the silver questions stored in ClaimPT. For manual evaluation, cross-validation, final fine-tuning, figure generation and the complete 14-model runs, see [Reproducing the experiments](docs/REPRODUCIBILITY.md).

## Main results

### Synthetic question quality

On the manually evaluated sample of **104 questions from 50 ClaimPT claim spans**, relevance and clarity/searchability both reached **96.2%** compliance; faithfulness reached **93.3%** (dissertation Table 3.8). Among the criteria of the CLEVER question-formulation guidelines, the general-specific structure was satisfied for **68.0%** of the 50 claim spans, the lowest rate (Table 3.9).

### Question generation on CLEVER

H-BERT scores on the held-out set of 100 claim spans (higher is better) for four of the 14 models; bold marks the best value of the 14 models in each regime (dissertation Tables 4.4, 4.5 and 4.10):

| Model | Zero-shot | 3-shot | Fine-tuned (Gold91+Silver1073) |
|---|---:|---:|---:|
| Mistral NeMo-12B-Instruct | **75.52** | **75.88** | 75.11 |
| AMALIA-9B-0626-DPO | 70.25 | 72.13 | **76.31** |
| Gervásio-8B PT-PT | 43.50 | 50.10 | 75.78 |
| GlórIA-1.3B | 44.13 | 40.28 | 74.12 |

Fine-tuning generally yielded more consistent performance across the evaluated models than prompting alone: on Gold91+Silver1073, H-BERT ranges from 63.94 to 76.31 across the 14 models, against 37.35–75.52 in zero-shot and 32.63–75.88 in 3-shot. The unweighted mean H-BERT of the 14 models is **65.00** with Gold91, **72.90** with Gold91+Silver1073 and **73.77** with Silver1073 (Table 4.9).

The complete Tables 3.8, 3.9, 4.4, 4.5, 4.9 and 4.10, with all 14 models, the other metrics and the six supervision configurations, are copied in [Reproducing the experiments](docs/REPRODUCIBILITY.md#results), which also gives the commands that compute them.

## Dissertation reference

- **Section 3.3:** ClaimPT and silver-standard question generation.
- **Chapter 4:** Automatic question generation and experimental results.
- **Appendix A.1:** CLEVER question-formulation criteria, the reference for the manual evaluation.
- **Appendix A.3:** Prompt used to generate silver questions for ClaimPT.
- **Appendix A.5:** Input templates for question generation.

For how the stages connect, see the [main repository README](../README.md#how-the-stages-connect); for the dissertation citation, see its [Citation](../README.md#citation) section.
