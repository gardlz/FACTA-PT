# FACTA-PT

> An end-to-end, question-driven fact-checking prototype for European Portuguese, from a claim span to an evidence-grounded article with traceable citations.

**Live prototype:** <https://factapt.inesctec.pt>

FACTA-PT integrates the components selected in the dissertation's [Question Generation](../Question%20Generation/), [Evidence Retrieval](../Evidence%20Retrieval/), [Document Relevance and Claim-Evidence Entailment](../Document%20Relevance%20and%20Claim-Evidence%20Entailment/) and [Article Generation](../Article%20Generation/) stages. This directory contains two services: a **FastAPI web service** with a static user interface and an **inference service** running the four models.

The prototype is intended to **support human fact-checkers**, not replace editorial judgement. FACTA-PT is described in **Chapter 8 and Appendix A.7** of the dissertation.

<p align="center">
  <img src="../docs/overall_pipeline.png"
       alt="Overview of the question-driven fact-checking architecture"
       width="100%">
</p>

<p align="center"><em>Overview of the question-driven fact-checking architecture. Figure created by the author with the assistance of generative AI.</em></p>

## What the prototype does

A user provides a **claim span**, its **publication date** and its **surrounding context**. FACTA-PT then:

1. Generates verification questions with a fine-tuned **AMALIA-9B-0626-DPO** model.
2. Searches the **LUSA News Corpus** for each question, restricting results to news published **before** the claim date.
3. Classifies retrieved documents as **Relevant** or **Irrelevant** with **BERTimbau-base**.
4. Classifies overlapping three-sentence passages from Relevant documents as **Supported**, **Refuted** or **Not Enough Information (NEI)** with **XLM-R-large-XNLI**.
5. Consolidates the predicted evidence and derives a factual conclusion from the retained relations.
6. Generates a structured article with **Gemma 4 E4B IT**, using the prepared evidence and the **predetermined conclusion**. The Writer does not search for additional evidence or reassess that conclusion.

The web interface presents the generated questions, publication dates of retrieved evidence, a summary of the predicted relations and the final article. Local citations (`[E1]`, `[E2]`, ... in the Writer's output) link factual statements to the corresponding LUSA passages: selecting one opens the news item with its passage highlighted. The interface is available in **Portuguese and English**; verification content remains in Portuguese.

## Models

| Component | Model | Checkpoint |
|---|---|---|
| Verification questions | AMALIA-9B-0626-DPO + QLoRA adapter | [Fine-tuned adapter](https://huggingface.co/liaad/facta-pt-qg-amalia-9b-0626-dpo) |
| Document relevance | BERTimbau-base | [Fine-tuned classifier](https://huggingface.co/liaad/facta-pt-relevance-bertimbau-base) |
| Claim-Evidence Entailment | XLM-R-large-XNLI | [Fine-tuned classifier](https://huggingface.co/liaad/facta-pt-cee-xlm-roberta-large-xnli) |
| Article generation | Gemma 4 E4B IT | [Original instruction-tuned model](https://huggingface.co/google/gemma-4-E4B-it) |

AMALIA requires its **base model** as well as the adapter. Gemma is used as the Writer without additional task-specific fine-tuning. Exact model revisions and local checkpoint paths are listed in [Deployment and reproducibility](docs/REPRODUCIBILITY.md).

## Requirements

- **Docker** with **Docker Compose** and approximately **80 GB of disk space**.
- **Recommended:** an NVIDIA GPU with a CUDA 12.8-compatible driver. The four models take turns on one GPU, which needs approximately **12 GB of GPU memory**, together with at least **24 GB of system RAM**. CPU-only operation is possible but considerably slower and memory-intensive.
- **For new verifications:** credentials for the **restricted LUSA search API** and access through its institutional **VPN**. The news corpus and credentials are **not distributed** with this repository.

See the [deployment notes](docs/REPRODUCIBILITY.md#1-prerequisites-and-access) for CPU and GPU details.

## Quick start

Run these commands from `FACTA-PT/`. Some Hugging Face repositories require acceptance of their licences and `hf auth login` before downloading.

```bash
# 1. Download the three trained components and the question generator's base weights
hf download amalia-llm/AMALIA-9B-0626-DPO \
  --revision c4614b9b5c7b4fe303fa20902e692fc7dface640 --local-dir checkpoints/qg
hf download liaad/facta-pt-qg-amalia-9b-0626-dpo --local-dir checkpoints/qg_adapter
hf download liaad/facta-pt-relevance-bertimbau-base --local-dir checkpoints/relevance
hf download liaad/facta-pt-cee-xlm-roberta-large-xnli --local-dir checkpoints/stance

# 2. Configure the LUSA API credentials in .env
cp .env.example .env

# 3. Start with an NVIDIA GPU
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build

# Alternatively, start without a GPU:
# docker compose up -d --build
```

Open <http://localhost:8000> and inspect service status with:

```bash
curl -s http://localhost:8000/api/health
```

Set `API_URL_LUSA`, `USER_LUSA` and `PASSWORD_LUSA` in `.env` **before starting the services**, which read them at start-up; new verifications need them. Never commit credentials or `.env` files. Gemma is downloaded on first start, so that start also needs network access to Hugging Face and disk space for its weights.

## Repository structure

```text
docker-compose.yml             Web and inference services
docker-compose.gpu.yml         NVIDIA GPU configuration
.env.example                   Environment-variable template
checkpoints/                   Locally downloaded model weights (not distributed)
inference/server/              Model inference API, classifiers and article generation
web/app/pipeline/              Retrieval, evidence analysis and article workflow
web/app/services/              LUSA and inference-service clients
web/app/static/                Bilingual web interface
web/app/demo/                  Optional stored-example playback
docs/REPRODUCIBILITY.md        Deployment details and operational differences
```

## Access and stored examples

**New claim verification is not fully self-contained:** it depends on the restricted LUSA API, a VPN connection and model weights downloaded separately. The optional `web/app/demo/exemplos.json` contains previously recorded end-to-end executions, but is **not redistributed** because it includes claims and news text. Without that file, the stored-example list is empty.

Unlike the controlled article-generation experiments, the prototype uses **automatically retrieved and classified evidence**, so upstream errors can affect the final article. The [deployment and reproducibility notes](docs/REPRODUCIBILITY.md) explain the evidence-consolidation rules, article-generation safeguards and differences from the research experiments.

## Dissertation reference

- **Chapter 8:** FACTA-PT workflow, evidence consolidation (Section 6.2.2) and user interaction.
- **Appendix A.7:** Interface walkthrough, from the input form and stored examples to the article and evidence inspection.
- **Chapters 4–7:** Experiments used to select the individual components.

For the full project overview and dissertation citation, see the [repository README](../README.md#citation).
