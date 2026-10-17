# Deploying and reproducing FACTA-PT

This document complements the [FACTA-PT README](../README.md) with model revisions, deployment configuration and the inference rules of the integrated prototype. It covers the implementation presented in **Chapter 8 and Appendix A.7** of the dissertation, rather than the separate training/evaluation protocols in Chapters 4–7.

**Run all shell commands from `FACTA-PT/`, not from `docs/`.**

## 1. Prerequisites and access

The deployment uses a **FastAPI web service** (with a static browser interface) and a separate **inference service** with the four selected models. Docker and Docker Compose are required, together with approximately **80 GB of disk space**.

The deployment shares one NVIDIA GPU between the models, which take turns on it rather than staying in GPU memory simultaneously: a model moves to the GPU when it is called, and the least recently used ones go back to main memory when there is not enough room for it. With a GPU, the deployment requires an NVIDIA driver compatible with **CUDA 12.8**, approximately **12 GB of GPU memory**, and at least **24 GB of system RAM**.

A CPU-only Compose configuration is available, but inference is much slower: on the CPU, the inference service loads the question generator and the article model only when the free memory is at least 1.15 times the size of their weights, about **21 GB** for the question generator and about **18 GB** for the article model, and article generation takes minutes.

**Important access restriction:** creating a new verification requires an account for the **LUSA search API**, which is reachable only via its institutional VPN. Neither access credentials nor the LUSA News Corpus are distributed with the code. The public prototype runs at <https://factapt.inesctec.pt>.

## 2. Model weights and revisions

Three components use task-adapted weights from the dissertation, while **Gemma 4 E4B IT** is the instruction-tuned Writer used without task-specific fine-tuning. Download the weights of the three fine-tuned components, and the question generator's base model, from Hugging Face before starting the containers. Some repositories require accepting a licence and authenticating with `hf auth login`.

| Component | Repository | Revision | Local location |
|---|---|---|---|
| Question generation base | [`amalia-llm/AMALIA-9B-0626-DPO`](https://huggingface.co/amalia-llm/AMALIA-9B-0626-DPO) | `c4614b9b5c7b4fe303fa20902e692fc7dface640` | `checkpoints/qg/` |
| Question generation QLoRA adapter | [`liaad/facta-pt-qg-amalia-9b-0626-dpo`](https://huggingface.co/liaad/facta-pt-qg-amalia-9b-0626-dpo) | Latest | `checkpoints/qg_adapter/` |
| Document relevance | [`liaad/facta-pt-relevance-bertimbau-base`](https://huggingface.co/liaad/facta-pt-relevance-bertimbau-base) | Latest | `checkpoints/relevance/` |
| Claim-Evidence Entailment | [`liaad/facta-pt-cee-xlm-roberta-large-xnli`](https://huggingface.co/liaad/facta-pt-cee-xlm-roberta-large-xnli) | Latest | `checkpoints/stance/` |
| Article Writer | [`google/gemma-4-E4B-it`](https://huggingface.co/google/gemma-4-E4B-it) | `ee0ef6023621cff504d758262d4e04895a5af4a2` | Downloaded on first start |

```bash
hf download amalia-llm/AMALIA-9B-0626-DPO \
  --revision c4614b9b5c7b4fe303fa20902e692fc7dface640 \
  --local-dir checkpoints/qg
hf download liaad/facta-pt-qg-amalia-9b-0626-dpo \
  --local-dir checkpoints/qg_adapter
hf download liaad/facta-pt-relevance-bertimbau-base \
  --local-dir checkpoints/relevance
hf download liaad/facta-pt-cee-xlm-roberta-large-xnli \
  --local-dir checkpoints/stance
```

The question generator loads with **4-bit quantisation on a GPU** (NF4 with double quantisation), consistent with its adaptation and evaluation (Section 4.3.2); without a GPU it loads unquantised, in bfloat16. The classifiers use **float32** and obtain their label order from each checkpoint's `config.json`. The models take turns on the GPU under `inference/server/gpu.py`.

Gemma 4 E4B IT is downloaded on the first start, at the revision above (`ARTICLE_MODEL_REVISION`), into the Hugging Face cache volume of the inference service. `ARTICLE_MODEL_PATH` can point to a local copy under `/checkpoints` instead.

## 3. Configure and start the services

Copy the environment template and fill in the restricted-search credentials:

```bash
cp .env.example .env
```

| Variable | Default | Purpose |
|---|---|---|
| `API_URL_LUSA` | Empty | LUSA search endpoint |
| `USER_LUSA` | Empty | LUSA account name |
| `PASSWORD_LUSA` | Empty | LUSA account password |
| `CHECKPOINTS_DIR` | `./checkpoints` | Host model-weight directory mounted at `/checkpoints` |
| `ARTICLE_DEVICE` | `auto` | Writer device: `cuda`, `cpu` or `auto` |
| `ARTICLE_MAX_PROMPT_TOKENS` | `16384` | Token limit for the article prompt |
| `ARTICLE_TIMEOUT` | `10800` | Maximum website wait in seconds for article generation |
| `TOP_K_PER_QUESTION` | `5` | Number of distinct LUSA news items retained per question |
| `WEB_PORT` | `8000` | Local web-server port |

The other variables in `.env.example` set the LUSA dataset name, the model paths, the Writer revision, the inference-service address and timeout, the number of GPUs reserved, the storage and concurrency of runs, and the allowed origins. **Do not commit `.env`, API credentials or LUSA news content.**

Start the services with an NVIDIA GPU:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

Or use the CPU-only configuration:

```bash
docker compose up -d --build
```

Then open <http://localhost:8000> and check the health endpoint:

```bash
curl -s http://localhost:8000/api/health
```

The health endpoint reports the state of the models and the LUSA API. It is useful for distinguishing model-loading problems from restricted-search access problems. Without working LUSA credentials and VPN connectivity, a new claim stops at evidence retrieval, after its questions are generated.

## 4. End-to-end inference workflow

The web interface accepts three inputs: **claim span**, **publication date** and **local context** (optional). The context supports the interpretation of the claim but is **not treated as external evidence**. The execution follows these steps (Section 8.1):

1. **Question generation.** The fine-tuned AMALIA model receives the claim span and date plus the ±1 sentence window of the given context (Section 4.2.3): the sentence containing the span and the sentences immediately before and after it. If the prompt would not leave the room the answer needs within the model's input length, the window is cut around the claim span.
2. **Retrieval.** Each generated question is submitted independently to the restricted LUSA search API. News items must be published **up to the day before** the claim's date. Reissues of the same LUSA dispatch are grouped, and the first **five distinct** news items per question are retained.
3. **Document relevance.** Fine-tuned BERTimbau-base labels each claim span–document pair **Relevant** or **Irrelevant**. Irrelevant documents are removed from subsequent analysis.
4. **Claim-Evidence Entailment.** Relevant documents are split into overlapping **three-sentence windows**, using a stride of one sentence. XLM-R-large-XNLI assigns **Supported**, **Refuted** or **NEI** to each claim span–passage pair.
5. **Evidence consolidation.** Predicted relations are filtered and combined, as described below. The retained evidence is used to derive the factual conclusion supplied to the Writer.
6. **Article generation.** Gemma 4 E4B IT receives the claim information, prepared evidence, source metadata, predetermined conclusion, verification limitations and content plan. It writes an article with citations such as `[E1]` linking its evidence-based statements to LUSA passages.

The UI exposes selected intermediate outputs (questions, publication dates and relation summaries), together with the final article and source-inspection links. It supports Portuguese and English interface labels, but the generated questions, LUSA content and articles remain in Portuguese.

### Evidence-consolidation rules

The web service (`web/app/pipeline/evidencia.py`) applies the consolidation rules of Sections 6.2.2 and 8.1, followed by a joining step specific to the prototype:

- Retain **every passage predicted Supported or Refuted**.
- If a document contains a decisive (Supported/Refuted) passage, do **not** forward any of that document's NEI passages.
- If **all** passages in a document are predicted NEI, forward **one** NEI passage: the passage whose prediction lies closest to a decisive class (the smallest margin M(w), Equation 6.8).
- Apply the [Article Generation](../../Article%20Generation/) stage's evidence-deduplication procedure **within each factual-relation category** (containment of 5-word shingles, threshold τ = 0.90; Sections 7.2.1 and 7.3.1).
- Join passages from the **same document and relation** when their spans overlap or touch.

## 5. Differences from the article-generation experiments

The article-generation experiments in **Chapter 7** use manually annotated CLEVER evidence to evaluate the Writer independently of upstream retrieval and classification errors. In FACTA-PT, **all input evidence is produced by the preceding automatic stages**. Full Relevant documents are processed through overlapping windows instead of constructing passages around manually annotated excerpt locations.

The article is generated as in the controlled Writer experiments (Section 7.2.3), with these implementation differences:

| Aspect | FACTA-PT deployment | Controlled article-generation experiments |
|---|---|---|
| Decoding backend | Greedy decoding with `transformers`, in bfloat16; output grammar via the `xgrammar` version used by vLLM 0.19.1 | vLLM 0.19.1, in bfloat16, with temperature 0 and top_p = 1 |
| Maximum generated article length | Up to **8192 new tokens** | **4096 new tokens** |
| Evidence input | Automatically retrieved, classified and consolidated; overlapping passages may be joined | Manually annotated CLEVER evidence passages |
| Prompt-size constraint | **16384 tokens** by default, with evidence pruning if needed | Maximum context of 16384 tokens |
| Failure handling | Stuck attempts are stopped, a third attempt uses fewer passages, the article is completed from its content plan if needed, and writing stops at a deadline | A second attempt when the first fails or loops |

The prompt, content plan, factual-verdict rule, fixed texts and grammar are **identical to those of the Article Generation stage**, and so is the retry rule: a repetition penalty of **1.05** on the first attempt and of **1.15** on a second attempt, made only when the first fails or loops. The third attempt, specific to FACTA-PT, also uses **1.15**.

When the article prompt exceeds `ARTICLE_MAX_PROMPT_TOKENS`, the prototype removes passages one at a time from the relation with the most passages: it first removes less-confident decisive passages or NEI passages furthest from a decisive class, but **never the last passage of a relation**. This is intended to preserve the conclusion represented by the retained relations.

If generation becomes stuck in a loop, the attempt is stopped. If neither of the first two attempts produces every section of the content plan, a third attempt removes half of the passages eligible for pruning. If generation still cannot finish, the article is completed from its content plan. The web service gives the inference service a deadline two minutes shorter than `ARTICLE_TIMEOUT`: an attempt starts only when enough time remains to read its prompt and write for at least a minute, and writing stops at that deadline.

FACTA-PT is not itself a component-level evaluation (Chapter 8): the article-generation scores are those of the controlled experiments in **Chapter 7**.

## 6. Stored examples

The optional `web/app/demo/exemplos.json` stores previously executed examples, organised by topic, with stage-by-stage results for claim spans not seen during fine-tuning. These **replay actual end-to-end pipeline outputs** (questions, retrieved documents, predictions, result and article) without running the models; they are **not manually corrected reference verifications**.

This JSON file is **not included** with the released repository because it contains claims and LUSA news text. If it is absent, the example browser is empty, while the form for new verifications remains available subject to restricted API access.

The interface is described in **Section 8.2**, and **Appendix A.7** walks through it, from the input form and stored examples (Figure A.4) to the intermediate results (Figure A.5) and the article and evidence-inspection views (Figures A.6 and A.7).

## 7. Code map

```text
docker-compose.yml               Web and inference containers
docker-compose.gpu.yml           NVIDIA GPU overlay
.env.example                     Environment-variable template

inference/server/main.py         Inference-service HTTP API
inference/server/qg.py           Fine-tuned question generation
inference/server/prompts.py      Question-generation prompt
inference/server/textutils.py    Context window and question parsing
inference/server/relevance.py    Document relevance classification
inference/server/stance.py       Passage-level entailment classification
inference/server/artigo/         Article plan, prompts, verdict, grammar, generation and completion
inference/server/gpu.py          GPU sharing across the four models

web/app/pipeline/                End-to-end orchestration and evidence consolidation
web/app/services/                LUSA API and inference-service clients
web/app/mensagens.py             Portuguese/English interface messages
web/app/static/                  Web interface
web/app/demo/exemplos.json       Optional stored examples (not distributed)
```

Most identifiers and log messages in the code are in Portuguese; the web interface can be switched between Portuguese and English.

## Dissertation and related stages

- **Chapter 8** and **Appendix A.7**: FACTA-PT and the interface walkthrough.
- **Chapters 4–7**: selection and evaluation of the individual pipeline components.
- See the separate stage READMEs for [Question Generation](../../Question%20Generation/), [Evidence Retrieval](../../Evidence%20Retrieval/), [Document Relevance and Claim-Evidence Entailment](../../Document%20Relevance%20and%20Claim-Evidence%20Entailment/) and [Article Generation](../../Article%20Generation/).

For the full dissertation citation, see the [main repository README](../../README.md#citation).
