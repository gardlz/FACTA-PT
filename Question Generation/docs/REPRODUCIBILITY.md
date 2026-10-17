# Reproducing the question-generation experiments

This document provides the longer command sequences supporting the [Question Generation README](../README.md), and the complete result tables of the stage. All commands are intended to be run **from `Question Generation/`**, not from this `docs/` directory.

## Environment and model access

- Install the dependencies as indicated in the [stage README](../README.md#installation).
- The experiments of the dissertation ran on the Deucalion supercomputer with NVIDIA A100-SXM4 80 GB GPUs, using Python 3.11.5, PyTorch 2.10.0 with CUDA 12.8, Transformers 5.6.2, PEFT 0.19.1, Accelerate 1.13.0 and bitsandbytes 0.49.2 (Section 4.3.2). Each training job used four GPUs, with one training process assigned to each GPU.
- Run each GPU-bound process on one GPU, selected with `CUDA_VISIBLE_DEVICES` (e.g. `CUDA_VISIBLE_DEVICES=0`): CodeCarbon then measures each run on its own GPU, and process hours are GPU-hours.
- The model commands use `--offline`, so obtain the model files and accept the required licences beforehand.
- `GEMINI_API_KEY` or `GOOGLE_API_KEY` must be set in a `.env` file in `Question Generation/` for silver-question generation. Do not commit it.

The model configurations are in `configs/models_encdec.yaml`, `configs/models_decoder.yaml` and `qg_kfold/configs/models_manifest.json`.

## 1. Silver questions for ClaimPT

### Optional: regenerate silver questions

The dissertation's **fixed** silver supervision is already stored in the ClaimPT JSON files. The following calls generate **new** files; outputs can differ even when the same generation settings are used.

```bash
python silver_generation/generate_questions.py \
    --input ../ClaimPT/claimpt_train.json \
    --output silver_generation/outputs/claimpt_train_silver_questions.jsonl

python silver_generation/generate_questions.py \
    --input ../ClaimPT/claimpt_test.json \
    --output silver_generation/outputs/claimpt_test_silver_questions.jsonl
```

The script uses the settings of Section 3.3.2: gemini-3.5-flash with temperature 0.0 (its defaults), output constrained to the JSON format `{"questions": [...]}`, and one request per ClaimPT claim span. The prompt is reproduced in Appendix A.3. Each output line holds one claim span (`id`, `document`, `publication_time`, `claim_time`, `claim_span`, `span_begin`, `span_end`, `claimers`, `claim_objects`) and its `questions`. Claim spans that still fail after the retries are written to `<output>_failed.jsonl`; running the same command again skips the claim spans already in the output and retries the others. These commands write output files without modifying the input datasets.

### Manual evaluation

For the **fixed sample of 50 claim spans (104 questions; seed 42)**, the manual-evaluation interface and the script that prints Tables 3.8 and 3.9 are:

```bash
streamlit run silver_generation/app.py
python silver_generation/tabelas_avaliacao.py
```

The interface reads and writes the evaluation files `ratings.json` and `ratings_clever.json` in `silver_generation/avaliacao/`, which holds the evaluation reported in the dissertation. Its evaluation form covers the two evaluation dimensions of Section 3.3.2: general question quality ([`CRITERIOS.md`](../silver_generation/CRITERIOS.md)) and adherence to the CLEVER question-formulation guidelines ([`CRITERIOS_CLEVER.md`](../silver_generation/CRITERIOS_CLEVER.md); the guidelines are in Appendix A.1). `tabelas_avaliacao.py` reads the same files and prints the compliance rates of [Tables 3.8 and 3.9](#results).

## 2. Fixed CLEVER split and data preparation

The question-generation split differs from the benchmark split used for the document-relevance and entailment experiments. It holds out **100 of 140 claim spans** and reserves **40 claim spans** for training/development, grouped by source document (Section 4.2.1).

```bash
python split_por_documento.py   # optional: draws the split again
python src/prepare_data.py
```

The split is stored in `split/clever_split_ids_seed0.json`, which `prepare_data.py` reads. `split_por_documento.py` is the procedure that draws it; with the published CLEVER it rewrites that file unchanged (`--output` writes it elsewhere). `prepare_data.py` writes the CLEVER examples to `data/clever/` (`clever_train_40.jsonl`, `clever_test_100.jsonl`, `clever_all.jsonl`) and the nested silver subsets to `data/processed/` (`claimpt_silver_{25,50,75,100}.jsonl`), and prints the counts of Tables 3.7 and 4.8.

## 3. Zero-shot and 3-shot inference (14 models)

```bash
for m in ptt5_large ptt5v2_large mt0_large ptt5v2_3b mt5_xl mt0_xxl; do
  for r in zero_shot few_shot; do
    python src/run_inference.py --config configs/models_encdec.yaml --only "$m" \
      --regime "$r" --seed 42 --bf16 --offline
  done
done

for m in tucano_1b1 llama32_1b gloria_1b3 bode_7b llama_8b gervasio_8b amalia_9b mistral_nemo; do
  for r in zero_shot few_shot; do
    python src/run_inference.py --config configs/models_decoder.yaml --only "$m" \
      --regime "$r" --seed 42 --bf16 --offline
  done
done

python src/metrics.py \
  --predictions_dir outputs/predictions \
  --metrics_dir outputs/metrics
```

Every model receives the complete prompt of Appendix A.5; in the 3-shot regime, the three fixed demonstrations are CLEVER training claim spans with one, two and three reference questions. A prompt that does not fit a model's input window stops that model with an error, and `run_inference.py` moves on to the next model. Predictions are written to `outputs/predictions/` and the energy measurements to `outputs/carbon/`. The summary `outputs/metrics/summary_metrics.csv` holds the values of [Tables 4.4 and 4.5](#results). These commands generate the full prompting evaluation and can require substantial compute and local model storage.

## 4. Prepare four-fold cross-validation

```bash
python qg_kfold/scripts/build_folds.py
python qg_kfold/scripts/build_fold_data.py
```

The four folds (`qg_kfold/folds/fold1.json` to `fold4.json`) contain 10 training/development claim spans each and keep each source document in a single fold. Training and validation files are written to `qg_kfold/data/fold{1..4}/` and final training files to `qg_kfold/data/final/`.

The six configurations and their command-line identifiers are:

| Supervision | `--train_setting` |
|---|---|
| Gold91 | `human40` |
| Gold91+Silver266 | `human40_silver25` |
| Gold91+Silver535 | `human40_silver50` |
| Gold91+Silver802 | `human40_silver75` |
| Gold91+Silver1073 | `human40_silver100` |
| Silver1073 | `silver100` |

## 5. Train one cross-validation fold

The following is a **command template**, not a directly runnable command. Replace every angle-bracket placeholder with the value specified by `qg_kfold/configs/models_manifest.json` or by the training protocol. In particular, `<script>`, `<yaml>`, `<family>` and `<batch>` correspond to `script`, `config_yaml`, `familia_adaptacao` and `physical_batch_size` in the manifest.

```bash
python qg_kfold/scripts/<script> --config configs/<yaml> --only <model> \
    --train_file qg_kfold/data/fold<k>/train_<configuration>.jsonl \
    --dev_file qg_kfold/data/fold<k>/dev_gold.jsonl \
    --train_setting <configuration> --fold <k> --familia_adaptacao <family> \
    --epochs <H> --scheduler_horizon_epochs <H> --learning_rate <lr> \
    --warmup_ratio 0.10 --batch_size <batch> --effective_batch_size 8 \
    --results_dir <results> --carbon_dir <run>/carbon \
    --metrics_device cpu --seed 42 --offline
```

The trainer computes the validation H-BERT on the gold validation fold after each epoch and appends one line per epoch to `<results>/<configuration>__<encdec|decoder>__<model>__fold<k>__por_epoca.jsonl`; it also logs the learning rate of every optimisation step to `<results>/<configuration>__<encdec|decoder>__<model>__fold<k>__h<H>__lr_por_step.jsonl`. The per-epoch files are append-only: remove the appropriate file before repeating a model/configuration/fold run from scratch to avoid mixing results.

## 6. Select learning rates and epochs

**Learning-rate selection.** For each adaptation family, run the learning-rate-selection models listed under `lr_calibration_models` in the manifest (both full fine-tuning models, and three pre-specified models for each of LoRA and QLoRA) with each candidate learning rate of their family in `hyperparameter_protocol.lr_candidates`. Use `human40_silver100`, folds 1–4 and an initial horizon of 20 epochs, with `<run>` = `qg_kfold/runs/v3/lr_ablation` and `<results>` = `qg_kfold/runs/v3/lr_ablation/results/<family>/<lr>` (`<family>`: `full_fine_tuning`, `lora` or `qlora`; `<lr>`: `2e-5`, `3e-5`, `1e-4` or `2e-4`).

```bash
python qg_kfold/scripts/select_learning_rates.py
python qg_kfold/scripts/promote_selected_lr_results.py
```

`select_learning_rates.py` keeps, for each family, the candidate with the highest mean cross-validated H-BERT over its models, and writes `qg_kfold/runs/v3/selected_learning_rates.json`: 3 × 10⁻⁵ for full fine-tuning and 1 × 10⁻⁴ for LoRA and QLoRA (Table 4.6). `promote_selected_lr_results.py` copies the cross-validation results of these models at the selected rates into `qg_kfold/runs/v3/results/`, so their `human40_silver100` runs are not repeated in the next step.

**Epoch selection.** With the selected rate for each family, run each model and supervision configuration on all four folds with an initial horizon of 20 epochs, with `<run>` = `qg_kfold/runs/v3` and `<results>` = `qg_kfold/runs/v3/results` (the trainers' defaults).

```bash
python qg_kfold/scripts/aggregate_folds.py
```

`aggregate_folds.py` averages the four folds per epoch (`qg_kfold/runs/v3/results/agregado_por_epoca.csv`) and selects, for each model and configuration, the earliest epoch whose mean validation H-BERT lies within 0.05 points of the maximum (`qg_kfold/runs/v3/results/best_epochs.csv` and `best_epochs.json`).

If the scripts report pending extensions, repeat the affected runs **from scratch** on the four folds (after removing their per-epoch files), with `--epochs` and `--scheduler_horizon_epochs` set to the prescribed `prolongar_ate` horizon (30 or, if necessary, 40 epochs), and rerun the selection/aggregation script until nothing is pending. The pending runs are listed in:

- `qg_kfold/runs/v3/lr_ablation/extensions_pending.csv` (learning-rate selection; all candidate rates of the listed model are rerun)
- `qg_kfold/runs/v3/reports/extensoes_pendentes.csv` (epoch selection)

A restart is necessary because the linear learning-rate schedule is defined over the complete training horizon: changing the horizon changes the learning-rate trajectory from the beginning of training (Figure 4.3).

## 7. Final training and evaluation

For each combination marked `terminado` in `best_epochs.json`, substitute the selected hyperparameters into this **template**:

```bash
python qg_kfold/scripts/train_final.py --config configs/<yaml> --only <model> \
    --train_setting <configuration> --familia_adaptacao <family> \
    --epochs <best_epoch> --scheduler_horizon_epochs <scheduler_horizon_epochs> \
    --learning_rate <selected_lr> --warmup_ratio 0.10 \
    --batch_size <batch> --effective_batch_size 8 \
    --protocol_tag qg_v3 --seed 42 --offline
```

`train_final.py` trains on `qg_kfold/data/final/train_<configuration>.jsonl` up to the selected epoch, with the learning-rate schedule of the cross-validation horizon, and generates the questions for the 100 test claim spans in `qg_kfold/runs/v3/results/final/predictions/`. The learning rate must be the one in `selected_learning_rates.json`.

Compute the test metrics from the final predictions:

```bash
python src/metrics.py \
    --predictions_dir qg_kfold/runs/v3/results/final/predictions \
    --metrics_dir qg_kfold/runs/v3/results/final/metrics
```

The summary holds the values of [Tables 4.9 and 4.10](#results); the Mean row of Table 4.9 is the unweighted mean of the 14 models.

## 8. Energy measurements and figures

```bash
python src/resumo_carbono.py --pastas outputs/carbon qg_kfold/runs/v3/carbon
```

Each run writes its CodeCarbon measurement to `<carbon_dir>/<name>.json`. `resumo_carbono.py` adds them up per regime, prints the runs, hours, kWh and kg CO₂eq of each regime and writes them to `outputs/metrics/carbono_por_regime.csv`. With these two folders, which are also its defaults, it gives the runs, GPU-hours, kWh and kg CO₂eq of the computational-cost summary in **Table 4.7**.

The figure scripts produce **Figures 4.1–4.3**, as PDF and PNG files in `figuras/`. Figure 4.1, with the named entities, additionally requires:

```bash
python -m spacy download pt_core_news_lg
```

Figure 4.1 shows the context of the claim span used as the example in Sections 4.1 and 4.2.3, whose text the first command reads from the prepared CLEVER data; Figures 4.2 and 4.3 read the cross-validation results in `qg_kfold/runs/v3/results/`:

```bash
CLAIM=$(python -c "import json; print(next(e['claim_span'] for e in map(json.loads, open('data/clever/clever_train_40.jsonl', encoding='utf-8')) if e['id'] == 'eleições_016_c7'))")
python figuras/fig_contexto.py --claim "$CLAIM" --ner
python figuras/fig_hbert_epocas.py
python figuras/fig_learning_rate.py
```

## Results

The tables below are copied from the dissertation, with its bold marks.

### Silver questions for ClaimPT (Section 3.3.2)

Table 3.8: Manual evaluation of the general quality of 104 synthetic questions associated with 50 claim spans from ClaimPT.

| Criterion | Compliance | Rate |
|---|:---:|:---:|
| Relevance | 100/104 | 96.2% |
| Faithfulness | 97/104 | 93.3% |
| Clarity and searchability | 100/104 | 96.2% |
| Temporal and local anchor | 103/104 | 99.0% |

Table 3.9: Manual evaluation of adherence to the CLEVER question-formulation guidelines in the sample of 50 claim spans from ClaimPT.

| Criterion | Compliance | Rate | Unit |
|---|:---:|:---:|:---:|
| General-specific structure | 34/50 | 68.0% | Claim span |
| Claim-object adherence | 92/104 | 88.5% | Question |
| Neutrality and factual focus | 103/104 | 99.0% | Question |
| Special-case compliance | 26/30 | 86.7% | Claim span |

### Question generation on CLEVER (Chapter 4)

Table 4.4: Zero-shot results on the CLEVER test set. Reported values are macro-averaged over claim spans. Enc.-Dec. denotes encoder-decoder and Dec.-only denotes decoder-only.

| Model | Architecture | Language | H-BERT ↑ | Cov-BERT ↑ | H-ROUGE-L ↑ | H-METEOR ↑ | CountErr ↓ | Q/Ex. (Ref.=2.16) |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| PTT5 Large | Enc.-Dec. | PT-BR | 43.22 | 82.10 | 3.20 | 6.18 | 1.16 | 1.00 |
| PTT5-v2 Large | Enc.-Dec. | PT (general) | 46.78 | 84.49 | 7.57 | 9.97 | 1.30 | 1.88 |
| PTT5-v2 3B | Enc.-Dec. | PT (general) | 52.39 | 84.65 | 9.95 | 12.27 | 0.92 | 1.34 |
| mT0 Large | Enc.-Dec. | Multilingual | 44.64 | 84.62 | 5.81 | 3.10 | 1.16 | 1.00 |
| mT5 XL | Enc.-Dec. | Multilingual | 41.01 | 77.88 | 3.22 | 6.11 | 1.16 | 1.00 |
| mT0 XXL | Enc.-Dec. | Multilingual | 37.35 | 72.57 | 2.10 | 2.30 | 1.21 | 1.01 |
| Tucano-1b1-Instruct | Dec.-only | PT-BR | 40.11 | 86.30 | 7.16 | 7.59 | 3.63 | 5.39 |
| Bode-7B-Alpaca | Dec.-only | PT-BR | 55.32 | 89.26 | 14.85 | 13.81 | 1.94 | 3.68 |
| Llama 3.2-1B-Instruct | Dec.-only | Multilingual | 50.64 | 89.45 | 14.73 | 15.15 | 2.32 | 4.30 |
| Llama 3.1-8B-Instruct | Dec.-only | Multilingual | 50.24 | 90.57 | 17.62 | 19.22 | 2.03 | 4.17 |
| Mistral NeMo-12B-Instruct | Dec.-only | Multilingual | **75.52** | **90.74** | **26.71** | **28.64** | **0.45** | 2.03 |
| Gervásio-8B PT-PT | Dec.-only | PT-PT | 43.50 | **90.74** | 16.05 | 16.68 | 2.72 | 4.84 |
| AMALIA-9B-0626-DPO | Dec.-only | PT-PT | 70.25 | 89.72 | 22.20 | 27.36 | 0.72 | 2.50 |
| GlórIA-1.3B | Dec.-only | PT-PT | 44.13 | 76.60 | 7.68 | 9.17 | 1.48 | 2.16 |

Table 4.5: Few-shot results on the CLEVER test set in the 3-shot setting. Reported values are macro-averaged over claim spans. Enc.-Dec. denotes encoder-decoder and Dec.-only denotes decoder-only.

| Model | Architecture | Language | H-BERT ↑ | Cov-BERT ↑ | H-ROUGE-L ↑ | H-METEOR ↑ | CountErr ↓ | Q/Ex. (Ref.=2.16) |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| PTT5 Large | Enc.-Dec. | PT-BR | 43.22 | 82.10 | 3.20 | 6.18 | 1.16 | 1.00 |
| PTT5-v2 Large | Enc.-Dec. | PT (general) | 52.46 | 84.53 | 5.96 | 6.62 | 1.10 | 2.00 |
| PTT5-v2 3B | Enc.-Dec. | PT (general) | 48.60 | 82.18 | 5.75 | 4.63 | 1.23 | 2.13 |
| mT0 Large | Enc.-Dec. | Multilingual | 44.55 | 84.58 | 3.92 | 2.55 | 1.16 | 1.00 |
| mT5 XL | Enc.-Dec. | Multilingual | 41.34 | 79.46 | 1.65 | 2.13 | 1.62 | 1.50 |
| mT0 XXL | Enc.-Dec. | Multilingual | 45.53 | 86.37 | 6.91 | 4.96 | 1.16 | 1.00 |
| Tucano-1b1-Instruct | Dec.-only | PT-BR | 32.63 | 88.70 | 9.38 | 9.63 | 3.90 | 6.04 |
| Bode-7B-Alpaca | Dec.-only | PT-BR | 56.74 | 90.71 | 21.46 | 22.35 | 1.43 | 3.15 |
| Llama 3.2-1B-Instruct | Dec.-only | Multilingual | 34.23 | 88.52 | 8.06 | 8.05 | 3.79 | 5.51 |
| Llama 3.1-8B-Instruct | Dec.-only | Multilingual | 48.65 | 90.92 | 19.99 | 21.56 | 2.78 | 4.84 |
| Mistral NeMo-12B-Instruct | Dec.-only | Multilingual | **75.88** | 91.50 | **31.85** | **35.24** | **0.46** | 1.98 |
| Gervásio-8B PT-PT | Dec.-only | PT-PT | 50.10 | **91.83** | 21.79 | 23.43 | 2.53 | 4.57 |
| AMALIA-9B-0626-DPO | Dec.-only | PT-PT | 72.13 | 90.73 | 28.00 | 32.55 | 0.54 | 1.80 |
| GlórIA-1.3B | Dec.-only | PT-PT | 40.28 | 77.05 | 3.32 | 2.02 | 1.99 | 3.09 |

Table 4.9: H-BERT on the CLEVER test set under the six supervision configurations.

| Model | Gold91 | Gold91+Silver266 | Gold91+Silver535 | Gold91+Silver802 | Gold91+Silver1073 | Silver1073 |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| PTT5 Large | 43.22 | 64.69 | 65.11 | 63.44 | 63.94 | **70.45** |
| PTT5-v2 Large | 70.94 | 75.84 | 75.94 | **76.01** | 71.81 | 75.43 |
| PTT5-v2 3B | 52.88 | 64.43 | 68.42 | 72.79 | 73.64 | **75.57** |
| mT0 Large | 51.67 | 64.96 | 62.25 | 63.64 | 65.42 | **67.02** |
| mT5 XL | 53.38 | 59.13 | 63.08 | 63.04 | **69.24** | 66.18 |
| mT0 XXL | 74.12 | 68.15 | 73.97 | 72.80 | 73.58 | **75.69** |
| Tucano-1b1-Instruct | 74.07 | 75.03 | 74.31 | **75.75** | 75.06 | 75.02 |
| Bode-7B-Alpaca | 73.74 | **76.10** | 75.42 | 75.40 | 75.63 | 75.59 |
| Llama 3.2-1B-Instruct | 66.35 | 74.17 | 74.51 | 74.69 | 75.14 | **75.17** |
| Llama 3.1-8B-Instruct | 72.29 | 75.24 | **76.96** | 75.62 | 75.81 | 75.63 |
| Mistral NeMo-12B-Instruct | 73.25 | 75.47 | **76.04** | 75.82 | 75.11 | 75.47 |
| Gervásio-8B PT-PT | 72.84 | 75.41 | 74.83 | 73.64 | 75.78 | **75.89** |
| AMALIA-9B-0626-DPO | 71.65 | 75.78 | 72.35 | 76.23 | **76.31** | 75.24 |
| GlórIA-1.3B | 59.61 | 71.64 | 72.02 | 72.16 | 74.12 | **74.36** |
| **Mean** | 65.00 | 71.15 | 71.80 | 72.22 | 72.90 | **73.77** |

Table 4.10: Comparison of the models in the main training configuration, Gold91+Silver1073, on the CLEVER test set. Reported values are macro-averaged over claim spans. Enc.-Dec. denotes encoder-decoder and Dec.-only denotes decoder-only.

| Model | Architecture | Language | H-BERT ↑ | Cov-BERT ↑ | H-ROUGE-L ↑ | H-METEOR ↑ | CountErr ↓ | Q/Ex. (Ref.=2.16) |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| PTT5 Large | Enc.-Dec. | PT-BR | 63.94 | 91.07 | 28.17 | 30.59 | 0.75 | 1.61 |
| PTT5-v2 Large | Enc.-Dec. | PT (general) | 71.81 | **91.42** | 30.69 | 32.67 | 0.57 | 2.01 |
| PTT5-v2 3B | Enc.-Dec. | PT (general) | 73.64 | 91.14 | 29.47 | 33.92 | 0.51 | 1.89 |
| mT0 Large | Enc.-Dec. | Multilingual | 65.42 | 91.13 | 28.15 | 30.28 | 0.72 | 1.64 |
| mT5 XL | Enc.-Dec. | Multilingual | 69.24 | 90.06 | 28.89 | 29.08 | 0.74 | 2.60 |
| mT0 XXL | Enc.-Dec. | Multilingual | 73.58 | 91.38 | 30.16 | 33.86 | 0.51 | 1.91 |
| Tucano-1b1-Instruct | Dec.-only | PT-BR | 75.06 | 90.58 | 27.35 | 30.13 | 0.48 | 2.04 |
| Bode-7B-Alpaca | Dec.-only | PT-BR | 75.63 | 91.24 | 30.62 | 35.08 | 0.47 | 2.07 |
| Llama 3.2-1B-Instruct | Dec.-only | Multilingual | 75.14 | 91.10 | 29.47 | 34.12 | 0.48 | 2.04 |
| Llama 3.1-8B-Instruct | Dec.-only | Multilingual | 75.81 | 90.73 | 29.37 | 32.60 | 0.46 | 2.10 |
| Mistral NeMo-12B-Instruct | Dec.-only | Multilingual | 75.11 | 91.34 | 30.90 | 35.47 | 0.48 | 2.02 |
| Gervásio-8B PT-PT | Dec.-only | PT-PT | 75.78 | 91.29 | **31.09** | **36.14** | 0.47 | 2.05 |
| AMALIA-9B-0626-DPO | Dec.-only | PT-PT | **76.31** | 91.22 | 31.06 | 35.47 | **0.44** | 2.02 |
| GlórIA-1.3B | Dec.-only | PT-PT | 74.12 | 90.29 | 25.71 | 28.34 | 0.49 | 2.05 |

## Dissertation sections

For the complete methodological description, definitions and detailed results, consult **Section 3.3, Chapter 4 and Appendices A.1, A.3 and A.5** of the dissertation. This technical guide complements rather than replaces that record. For the citation, see the [repository README](../../README.md#citation).
