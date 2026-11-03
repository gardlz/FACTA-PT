# FACT-PT

> An end-to-end, question-driven fact-checking prototype for European Portuguese, from a claim span to an evidence-grounded article with traceable citations.

**Live prototype:** <https://factpt.inesctec.pt>

FACT-PT integrates the components selected in the [Question Generation](../Question%20Generation/), [Evidence Retrieval](../Evidence%20Retrieval/), [Document Relevance and Claim-Evidence Entailment](../Document%20Relevance%20and%20Claim-Evidence%20Entailment/) and [Article Generation](../Article%20Generation/) stages; the [main repository README](../README.md) describes how the stages connect. The prototype is intended to **support human fact-checkers**, not to replace editorial judgement.

## How it works

A user provides a **claim span**, its **publication date** and, optionally, its **context**, and chooses how many news items each question keeps and which model writes the article. FACT-PT then:

1. Generates verification questions with **AMALIA-9B-0626-DPO** and its fine-tuned question-generation adapter.
2. Searches the **LUSA News Corpus** with each question, restricted to news published **before** the claim date, and keeps the first **5, 10 or 15** distinct news items per question, with the reissues of the same story merged.
3. Classifies each retrieved news item as **Relevant** or **Irrelevant** with **BERTimbau-base**.
4. Classifies overlapping three-sentence passages of the Relevant news items as **Supported**, **Refuted** or **Not Enough Information (NEI)** with **XLM-R-large-XNLI**.
5. Derives the verdict from the passage relations: **Supported** if a passage supports the claim span and none refutes it, **Refuted** if a passage refutes it and none supports it, and **NEI** otherwise, including conflicting evidence and runs without decisive evidence.
6. Writes a structured article with **Gemma 4 31B IT** (the default) or **AMALIA-9B-0626-DPO**, from the consolidated evidence and the predetermined verdict. The Writer does not search for further evidence or reassess the verdict.

The page shows the generated questions, how many news items were retrieved and how many were considered relevant, a timeline of the news items that support or refute the claim, the verdict and the article, whose numbered citations open the cited LUSA passages. Saved verifications can be edited by an editor (see [Editorial review](#editorial-review)). The interface is in **Portuguese and English**; verification content is in Portuguese.

| Step | Model | Where it runs |
|---|---|---|
| Verification questions | [AMALIA-9B-0626-DPO](https://huggingface.co/amalia-llm/AMALIA-9B-0626-DPO) with the adapter [liaad/facta-pt-qg-amalia-9b-0626-dpo](https://huggingface.co/liaad/facta-pt-qg-amalia-9b-0626-dpo) | OpenAI-compatible API |
| Document relevance | [liaad/facta-pt-relevance-bertimbau-base](https://huggingface.co/liaad/facta-pt-relevance-bertimbau-base) | Inference service |
| Claim-Evidence Entailment | [liaad/facta-pt-cee-xlm-roberta-large-xnli](https://huggingface.co/liaad/facta-pt-cee-xlm-roberta-large-xnli) | Inference service |
| Article (default) | [google/gemma-4-31b-it](https://huggingface.co/google/gemma-4-31b-it) | OpenRouter API |
| Article (alternative) | [AMALIA-9B-0626-DPO](https://huggingface.co/amalia-llm/AMALIA-9B-0626-DPO), without the adapter | OpenAI-compatible API |

The Article Generation experiments evaluated Gemma 4 E4B IT; the prototype uses the larger Gemma 4 31B IT through OpenRouter. Revisions, sizes and serving details are in [MODELS.md](MODELS.md).

## Repository structure

```text
docker-compose.yml            Website, worker, Redis and inference services
docker-compose.gpu.yml        NVIDIA GPU configuration of the inference service
.env.example                  Configuration template, copied to .env
web/app/                      Website and API (FastAPI): accounts, queue of runs, saved verifications and editorial review
  pipeline/                   Questions, LUSA retrieval, reissue merging, passages, evidence consolidation and article
  services/                   Clients of the LUSA API and of the inference service
  demo/                       Playback of stored examples (not distributed)
web/frontend/                 Web interface (React), in Portuguese and English
web/inference/server/         Inference service: the two classifiers and the clients of the question generator and the Writers
  artigo/                     Article plan, prompt, JSON Schema and verdict
web/tests/                    Tests
scripts/exportar-modelos.sh   Copy the downloaded models to a folder of local checkpoints
MODELS.md                     The models: revisions, sizes and how each one is served
SERVER-GUIDE.md               Deployment on a server, behind HTTPS
GPU-GUIDE.md                  Running on the 8 GB GPU desktop (RTX 4060 Ti, Windows + WSL)
```

Some file names and identifiers are in Portuguese.

## Data and access

**No news content is included in this repository.** New verifications search the LUSA News Corpus through its **restricted search API**, which answers only over the institution's **VPN** and requires authorised credentials. Without them, a new claim stops after its questions are generated.

The live prototype also offers **stored examples**, recorded runs kept in `web/app/demo/exemplos5.json`, `exemplos10.json` and `exemplos15.json`. They are **not redistributed** because they contain news text; without them, the page starts with the input form.

Accounts, platform settings, finished runs and editorial reviews are kept in `dados/`, next to `docker-compose.yml` (`RUNS_DIR` in `.env` moves it).

## Requirements

- **Docker** with **Docker Compose**, and about **3 GB of disk** for the classifiers and tokenizers, plus the images.
- The two classifiers run in the inference service, on the **CPU** or on an **NVIDIA GPU** with a CUDA 12.8-compatible driver and the NVIDIA Container Toolkit.
- An **OpenAI-compatible server** for the two AMALIA models, the question generator (the base model with the adapter) and the AMALIA Writer (the base model), for example [one vLLM server](MODELS.md#a-vllm-server-of-your-own) on a GPU with room for the base model's **18.3 GB** of weights and its context window. The live prototype serves them through a gateway on Modal (`MODAL_API_URL`, `MODAL_API_KEY`), which is not part of this repository.
- An **OpenRouter** API key for the Gemma Writer, which is paid per request.
- **LUSA API** credentials and VPN access (see [Data and access](#data-and-access)).

## Installation

Get the code and create `.env` from the template:

```bash
git clone https://github.com/LIAAD/factapt.git
cd factapt/FACT-PT
cp .env.example .env
```

In `.env`, set:

- the LUSA account: `API_URL_LUSA`, `USER_LUSA` and `PASSWORD_LUSA`;
- the AMALIA models: `QG_API_URL`, `QG_API_MODEL`, `AMALIA_API_URL` and `AMALIA_API_MODEL` for a server of your own ([MODELS.md](MODELS.md#a-vllm-server-of-your-own)), or `MODAL_API_URL` and `MODAL_API_KEY` for a Modal gateway;
- the Gemma Writer: `ARTICLE_API_KEY`, the OpenRouter key;
- the first administrator and the session secret, `ADMIN_PASSWORD_HASH` and `SESSION_SECRET`, generated with the commands below, which print the two lines to paste into `.env`;
- `COOKIE_SECURE=false`, to sign in over plain HTTP at `http://localhost:8000`.

```bash
docker build -t facta-pt-web:1.6.0 web
docker run --rm -it facta-pt-web:1.6.0 python -m app.acesso
```

Never commit `.env`. On a Linux host, the data folder must belong to the containers' user before the first start:

```bash
mkdir -p dados/execucoes
sudo chown -R 100:101 dados
```

## Running

With an NVIDIA GPU:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

Without one:

```bash
docker compose up -d --build
```

On a GPU host, use both `-f` files in every `docker compose` command. The first start downloads the two classifiers and the tokenizers, about 3 GB. The inference service reports which models are ready:

```bash
docker compose exec inference python -c "import urllib.request as u; print(u.urlopen('http://localhost:8100/health').read().decode())"
```

Then open <http://localhost:8000> and sign in as the first administrator (`admin`, unless `ADMIN_USERNAME` sets another name). Runs that use the models wait in a queue, and a worker takes them one at a time; `docker compose up -d --scale worker=2` runs two at once.

## Accounts and roles

Everyone signs in with their own account; there is no shared password. An administrator makes the
others in **Administração**, which also holds what each role may do and the platform's defaults.

- **Jornalista**: verifies, reads and edits results, and takes part in the editorial review. The
  administrator may take any of those away. A journalist's verification also runs in the background
  (`segundo_plano`): it has its address from the start, goes on when its page is left or closed,
  and is listed on its own page, *Verificações*, under the account, for a day, to be opened again
  from any session. A run that stopped without a verification (cancelled, failed or lost) can be
  restarted from there.
- **Administrador**: everything, including the accounts and the platform settings. At least one
  active administrator always remains.

Permissions are read on every request, so a change of role applies at once. Deactivating or deleting
an account, or changing its password, ends that person's sessions; nobody can deactivate, demote or
delete themselves. Deleting cannot be undone, but the revisions the account signed keep its name.

## Editorial review

A saved verification is a **draft** an editor can change where it is shown: which news items count,
what each passage says (or a stretch of a news item highlighted as supporting, refuting or
undecided), the verdict, from the verdict band, and the article's text. One undo and one redo
(Ctrl+Z, Ctrl+Shift+Z) cover every kind of edit, and nothing is kept until the editor saves
(`Guardar versão`, Ctrl+S): each save is one version, with its author, time and the fields it
changed. A draft not yet saved survives a reload in the same browser.

The automated result is never changed: it is version 0. The history opens any version on the page
to be read as it was, and saving it brings it back as a new version. The article can also be
written again from the saved evidence, with the run's writer or another; the rewrite is a version
of its own.

## On a server

Behind HTTPS, with a reverse proxy, the port kept off the network and the proxy's address trusted:
see [SERVER-GUIDE.md](SERVER-GUIDE.md). With no domain of your own, Tailscale Funnel serves the same
site over HTTPS at a `*.ts.net` address:
[Without a domain: Tailscale Funnel](SERVER-GUIDE.md#without-a-domain-tailscale-funnel).

## The 8 GB GPU desktop

The RTX 4060 Ti desktop (32 GB, Windows + WSL): see [GPU-GUIDE.md](GPU-GUIDE.md).
