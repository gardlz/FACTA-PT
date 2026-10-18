# Reproducing the article-generation experiments

This document supplements the [Article Generation README](../README.md) with the model revisions, input structure, full generation and evaluation commands and the complete result tables (Tables 7.4–7.6, copied from the dissertation with its bold marks) for **Chapter 7** of the dissertation. **Run every command from `Article Generation/`, not from `docs/`.**

## 1. Environments, model weights and access

The stage uses two separate environments; the `python_version` markers in `requirements.txt` install the relevant dependencies for each interpreter.

```bash
# Generation: Python 3.11, CUDA GPU, vLLM
python3.11 -m venv .venv-geracao
source .venv-geracao/bin/activate
pip install -r requirements.txt

# Evaluation: Python 3.14, the NLI judge and the Gemini API
# Deactivate the first environment (or open another shell) before creating/using this one.
python3.14 -m venv .venv-evaluation
source .venv-evaluation/bin/activate
pip install -r requirements.txt
```

The dissertation reports one **NVIDIA A100-SXM4 40 GB** GPU per generation run on the Deucalion supercomputer, **vLLM 0.19.1** and **bfloat16**. CodeCarbon records the energy consumption and estimated emissions of each generation run. The content-plan builder and deduplication audit need only standard Python libraries.

Generation loads pretrained model weights **offline** from the local Hugging Face cache. Some checkpoints require acceptance of their licences and authentication before downloading. The model revisions of the reported runs and the prompt formats they require are:

| Model | Hugging Face repository | Commit / revision | `--formato` |
|---|---|---|---|
| Llama 3.2-3B-Instruct | `meta-llama/Llama-3.2-3B-Instruct` | `0cb88a4f764b7a12671c53f0838cd831a0843b95` | `auto` |
| Gemma 4 E4B IT | `google/gemma-4-E4B-it` | `ee0ef6023621cff504d758262d4e04895a5af4a2` | `auto` |
| Qwen3.5-4B | `Qwen/Qwen3.5-4B` | `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a` | `auto` |
| Llama 3.1-8B-Instruct | `meta-llama/Llama-3.1-8B-Instruct` | `0e9e39f249a16976918f6564b8830bc894c89659` | `auto` |
| Gervásio-8B | `PORTULAN/gervasio-8b-portuguese-ptpt-decoder` | `5d9666efbd3051275e52e71c33393495133a7e27` | `llama3` |
| AMALIA-9B-0626-DPO | `amalia-llm/AMALIA-9B-0626-DPO` | `c4614b9b5c7b4fe303fa20902e692fc7dface640` | `auto` |
| EuroLLM-9B-Instruct-2512 | `utter-project/EuroLLM-9B-Instruct-2512` | `def82454026b0353f12e48a0de081a9ed380d91e` | `chatml` |
| Qwen3.5-9B | `Qwen/Qwen3.5-9B` | `c202236235762e1c871ad0ccb60c8ee5ba337b9a` | `auto` |

The generator loads whichever snapshot a model's **local `main` reference** resolves to. To use the revisions above, download them and point each `refs/main` at them. **This modifies the local Hugging Face cache's `refs/main` pointers**, not the upstream repositories; use an isolated cache if other projects share those checkpoints:

```python
from pathlib import Path
from huggingface_hub import snapshot_download

REVISIONS = {
    "meta-llama/Llama-3.2-3B-Instruct": "0cb88a4f764b7a12671c53f0838cd831a0843b95",
    "google/gemma-4-E4B-it": "ee0ef6023621cff504d758262d4e04895a5af4a2",
    "Qwen/Qwen3.5-4B": "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a",
    "meta-llama/Llama-3.1-8B-Instruct": "0e9e39f249a16976918f6564b8830bc894c89659",
    "PORTULAN/gervasio-8b-portuguese-ptpt-decoder": "5d9666efbd3051275e52e71c33393495133a7e27",
    "amalia-llm/AMALIA-9B-0626-DPO": "c4614b9b5c7b4fe303fa20902e692fc7dface640",
    "utter-project/EuroLLM-9B-Instruct-2512": "def82454026b0353f12e48a0de081a9ed380d91e",
    "Qwen/Qwen3.5-9B": "c202236235762e1c871ad0ccb60c8ee5ba337b9a",
}
for repo, commit in REVISIONS.items():
    snapshot = Path(snapshot_download(repo, revision=commit))
    refs = snapshot.parent.parent / "refs"
    refs.mkdir(exist_ok=True)
    (refs / "main").write_text(commit)
```

Run the snapshot download **before** enabling offline mode. Generation then runs offline:

```bash
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false VLLM_WORKER_MULTIPROC_METHOD=spawn
```

The holistic judge (`gemini-3.8-flash`) is called through the **Gemini API**, with the `GEMINI38_FLASH_KEY` credential read from a local `.env` file in this folder or from the process environment. **Do not commit API keys or `.env` files.** The NLI judge (`MoritzLaurer/bge-m3-zeroshot-v2.0`, pinned in `evaluation/config.py` to revision `9abf1c8aaeb82a2447809c20753ed0b106b76652`) downloads its weights on first use; unset the offline variables first.

## 2. CLEVER data and evidence preparation

**The dataset and third-party LUSA news content are not redistributed in this repository.** Consult the [root README](../../README.md#data) for access conditions. This stage requires:

```text
../CLEVER/clever.json
../CLEVER/clean_files/<document>.txt
```

`clever.json` lists the source articles (`document`, `publication_time`) with their claim items; each claim span has its `text` and its `retrieved_documents`, and the text of its source article is read from `clean_files/<document>`. Only documents with `relevant: true` supply evidence; from each, the code reads `lusa_doc_id` (the LUSA identifier, which names the evidence), `headline`, `published_at`, `content`, `relation`, and `evidence_excerpts` with `text`, `begin` and `end` offsets. The claim span must occur verbatim in its source article so the surrounding context can be constructed.

The experimental **Writer input** includes: claim span, **±1-sentence context**, publication date, three-sentence evidence passages with their `Supported`/`Refuted`/`NEI` relations and source metadata, plus a **predetermined conclusion**. The Writer does **not** infer a verdict or retrieve further material. Local citation labels `[E1]`, `[E2]`, ... link evidence-grounded factual statements to the passages given to the Writer.

The verdict aggregation in the dissertation is: **Supported** if Supported evidence exists without Refuted evidence; **Refuted** if Refuted evidence exists without Supported evidence; **NEI** if evidence is only NEI, no Relevant evidence exists, or Supported and Refuted evidence coexist. This decision precedes article generation.

Across **140 claim spans**, CLEVER provides **527 annotated evidence excerpts**, each represented by one three-sentence passage. Deduplication compares **5-word shingles** within the same claim span **and the same evidence-relation class**, and removes the shorter of two passages when its containment in the longer one is at least **0.90**. This removes **27** redundant passages, leaving **500** for article generation.

The threshold was selected by manually labelling the candidate removals (Table 7.4). The audit lists every pair of passages of the same claim span and relation with containment of at least 0.80 and, for each threshold, the candidate removals and the removal precision:

```bash
python geracao/auditoria_dedup.py
```

The script labels the 23 identical pairs as redundant and reads the other labels from `dados/dedup/anotacao_dedup.json`, which maps `<claim_span_id>|<shorter passage id>|<longer passage id>` to a `rotulo` of `REDUNDANT` or `NON_REDUNDANT`. These manual labels are not included in this repository. Without them, the script still lists the 27, 31 and 33 candidate removals at 0.90, 0.85 and 0.80, but **cannot compute the removal precision**.

Table 7.4: Manual validation of candidate evidence-passage removals under the evaluated containment thresholds.

| Threshold | Candidate removals | Redundant | Non-redundant | Removal precision |
|---|---:|---:|---:|---:|
| **0.90** | 27 | 27 | 0 | **1.00** |
| 0.85 | 31 | 30 | 1 | 0.97 |
| 0.80 | 33 | 32 | 1 | 0.97 |

Of the 140 instances, **27 have no Relevant evidence passage**. The code generates an article for all 140, including no-evidence cases, but the **quantitative model comparison uses only the 113 evidence-bearing instances** (79 with at least one decisive passage and 34 with exclusively NEI evidence). Citation Precision additionally requires the generated article to contain at least one citation.

## 3. Generation: full model comparison and ablations

The full configuration combines **deduplicated evidence**, a **deterministic content plan** and a **plan-dependent JSON Schema grammar**. The plan organises the factual information to communicate, while the grammar constrains output structure, section order and limits without supplying additional facts. Generation uses temperature **0**, `top_p=1`, context limit **16,384 tokens**, output limit **4,096 tokens**, and repetition penalty **1.05** (increased to **1.15** only if the first attempt fails or repeats); these are the defaults of `geracao/gerar_artigos.py`. There is **no task-specific fine-tuning** of the Writers in this experiment.

With the generation environment active, construct plans first:

```bash
python geracao/construir_planos.py --todas
```

The builder writes one `dados/planos/<condition>/<claim_span_id>.json` per claim span for each of the four plan conditions (`full`, `sem_dedup`, `sem_plano`, `direct`). For each condition it prints the number of plans and evidence passages (500 with deduplication, 527 without), the passages removed by deduplication (27 in `full` and `sem_plano`) and the number of claim spans in each plan case, including 27 `no_evidence` and 34 `non_decisive`. Before loading the model, `gerar_artigos.py` checks that every prompt leaves the full `--max_tokens` within `--max_model_len`; it skips claim spans whose article already exists in the output folder.

Then generate the **eight-model comparison** in the `full` condition. Each line starts a separate monitored generation run:

```bash
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false VLLM_WORKER_MULTIPROC_METHOD=spawn

python geracao/carbono.py --modelo meta-llama/Llama-3.2-3B-Instruct --condicao full
python geracao/carbono.py --modelo google/gemma-4-E4B-it --condicao full
python geracao/carbono.py --modelo Qwen/Qwen3.5-4B --condicao full
python geracao/carbono.py --modelo meta-llama/Llama-3.1-8B-Instruct --condicao full
python geracao/carbono.py --modelo PORTULAN/gervasio-8b-portuguese-ptpt-decoder --condicao full --formato llama3
python geracao/carbono.py --modelo amalia-llm/AMALIA-9B-0626-DPO --condicao full
python geracao/carbono.py --modelo utter-project/EuroLLM-9B-Instruct-2512 --condicao full --formato chatml
python geracao/carbono.py --modelo Qwen/Qwen3.5-9B --condicao full
```

For the **ablation study**, retain the selected Writer (Gemma) and change only the indicated components. The existing Gemma `full` run is reused:

```bash
python geracao/carbono.py --modelo google/gemma-4-E4B-it --condicao sem_dedup
python geracao/carbono.py --modelo google/gemma-4-E4B-it --condicao sem_plano
python geracao/carbono.py --modelo google/gemma-4-E4B-it --condicao full --sem_gramatica
python geracao/carbono.py --modelo google/gemma-4-E4B-it --condicao direct --sem_gramatica
```

The five ablation conditions are: `full`; without deduplication (`--condicao sem_dedup`); without grammar (`--condicao full --sem_gramatica`); without plan (`--condicao sem_plano`); and direct generation (`--condicao direct --sem_gramatica`: without plan **and** grammar, with non-deduplicated evidence). Other input information, including the predetermined conclusion, remains available. `geracao/carbono.py` invokes `geracao/gerar_artigos.py` while monitoring energy and emissions; `geracao/gerar_artigos.py` can be used directly without that monitoring.

Articles are written to `dados/artigos/<condition>/<model>/<claim_span_id>.json`, where `<model>` is the short model name (for example `gemma4_e4b`), with the suffix `_sem_gramatica` for runs without the grammar. Each `carbono.py` run appends one row to `dados/carbono/emissoes.csv`; Table 7.2 of the dissertation reports the energy and emissions of the twelve runs.

## 4. Evaluate the generated articles

Activate **`.venv-evaluation`** and disable the offline flags before using judges that may need remote resources:

```bash
unset HF_HUB_OFFLINE TRANSFORMERS_OFFLINE
```

The **NLI judge** (`MoritzLaurer/bge-m3-zeroshot-v2.0`) evaluates evidence support for **Citation Recall**, **Citation Precision**, and **Evidence Coverage**. **`gemini-3.8-flash`** evaluates **Relevance**, **Comprehensibility**, and **Evidence Presentation** on a **1–5** scale. The grounding metrics use **0–1**. Articles without input evidence are left out, so each model and condition is evaluated on the 113 evidence-bearing claim spans.

Evaluate the **eight-model comparison**. `--executar` runs the judges (`--componentes citacoes` is the NLI judge and `holistico` the Gemini judge; both by default), and `--montar` assembles their cached results:

```bash
python -m evaluation.evaluate_articles --condicoes full --executar --componentes citacoes --saida evaluation/outputs/full
python -m evaluation.evaluate_articles --condicoes full --executar --componentes holistico --saida evaluation/outputs/full
python -m evaluation.evaluate_articles --condicoes full --montar --saida evaluation/outputs/full
python -m evaluation.aggregate_results --resultados evaluation/outputs/full/resultados.jsonl --saida evaluation/outputs/full/agregado
```

Evaluate the **Gemma ablation**, reusing cached judge decisions from the `full` comparison to avoid unnecessary API/model calls. `--modelos` takes the short model name, and the runs without the grammar have the conditions `full+sem_gramatica` and `direct+sem_gramatica`:

```bash
mkdir -p evaluation/outputs/ablacao
cp -n evaluation/outputs/full/cache_*.jsonl evaluation/outputs/ablacao/
python -m evaluation.evaluate_articles --modelos gemma4_e4b --condicoes full sem_dedup sem_plano full+sem_gramatica direct+sem_gramatica --executar --saida evaluation/outputs/ablacao
python -m evaluation.evaluate_articles --modelos gemma4_e4b --condicoes full sem_dedup sem_plano full+sem_gramatica direct+sem_gramatica --montar --saida evaluation/outputs/ablacao
python -m evaluation.aggregate_results --resultados evaluation/outputs/ablacao/resultados.jsonl --saida evaluation/outputs/ablacao/agregado
```

The judge runs are cached as JSONL files and can resume after interruption. Output plans, generated articles and CodeCarbon records are written under `dados/`; judge caches, article-level scores and aggregated reports are written under `evaluation/outputs/`. Each `--saida` folder holds the two judge caches (`cache_citacoes.jsonl` and `cache_holistico_gemini-3.8-flash.jsonl`), `resultados.jsonl` with the six metrics of each article, and `agregado.csv`/`agregado.json` with one row per model, condition and metric: `n_articles`, `n` (articles with a value), `n_null`, `mean` and `null_status` (the reason for each missing value). An article without citations has no Citation Precision and is counted under `null_status` as `no_citations`.

### Model comparison results

Table 7.5: Article-generation results for the eight evaluated models.

| Model | Citation Recall | Citation Precision | Evidence Coverage | Relevance | Comprehensibility | Evidence Presentation |
|---|---:|---:|---:|---:|---:|---:|
| Gemma 4 E4B IT | **0.644** | 0.677 | 0.885 | 4.96 | **4.94** | **4.01** |
| Qwen3.5-9B | 0.590 | **0.753** | **0.902** | **4.97** | 4.77 | 3.56 |
| Qwen3.5-4B | 0.494 | 0.706 | 0.817 | 4.88 | 4.62 | 3.81 |
| Llama 3.1-8B-Instruct | 0.366 | 0.701 | 0.652 | 4.71 | 4.44 | 2.81 |
| Gervásio-8B | 0.331 | 0.723 | 0.613 | 4.52 | 4.00 | 2.29 |
| AMALIA-9B-0626-DPO | 0.248 | 0.509 | 0.478 | 4.69 | 4.42 | 3.37 |
| EuroLLM-9B-Instruct-2512 | 0.077 | 0.348 | 0.247 | 3.97 | 3.33 | 2.87 |
| Llama 3.2-3B-Instruct | 0.049 | 0.408 | 0.118 | 2.45 | 1.80 | 1.35 |

Citation Precision is **conditional on an article containing a citation**, so the number of observations varies by model. The other metrics are averaged over the 113 evidence-bearing claim spans.

### Ablation results

Table 7.6: Results of the ablation study with Gemma 4 E4B IT.

| Condition | Citation Recall | Citation Precision | Evidence Coverage | Relevance | Comprehensibility | Evidence Presentation |
|---|---:|---:|---:|---:|---:|---:|
| Full | **0.644** | **0.677** | **0.885** | **4.96** | **4.94** | 4.01 |
| Without deduplication | 0.626 | 0.653 | 0.876 | **4.96** | **4.94** | **4.21** |
| Without grammar | **0.644** | 0.663 | 0.833 | 4.80 | 4.58 | 3.92 |
| Without plan | 0.395 | 0.435 | 0.537 | 4.87 | 4.65 | 2.49 |
| Direct generation | 0.461 | 0.611 | 0.644 | 4.35 | 4.23 | 2.01 |

## 5. Dissertation reference

See **Chapter 7** for experimental design and interpretation (**Tables 7.1–7.6**), **Appendix A.6** for the generation prompt, content plan, article structure and Article Quality evaluation prompt, and **Chapter 8** for FACTA-PT integration. For citation details, consult the [root README](../../README.md#citation).
