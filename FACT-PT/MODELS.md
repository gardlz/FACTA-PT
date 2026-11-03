# Models

The two AMALIA models - the question generator and the AMALIA article writer - answer on Modal,
behind one gateway set in `.env` (`MODAL_API_*`), or behind an OpenAI-compatible server of your own
(`QG_API_*`, `AMALIA_API_*`), and the Gemma article writer behind OpenRouter's API
(`ARTICLE_API_*`). Only the two classifiers run here: they are downloaded
from Hugging Face by the inference service the first time it starts, into the Docker volume
`modelos` (`/cache/huggingface` in the container), and read from there afterwards, with the
tokenizers the others count their prompts with. Nothing needs to be fetched by hand, and none of
them needs a Hugging Face token. The revisions are pinned in `docker-compose.yml`.

## Behind the API

### Modal

Both answer on Modal, behind one gateway on one GPU: `MODAL_API_URL` is its address, without a
path, and `MODAL_API_KEY` the key it asks for. The service sends

- **question generation** to `<address>/facta/v1/completions` (`amalia-facta`): the prompt built
  and fitted here, as it is. The gateway reads the base in 4-bit NF4 with the adapter over it, as
  in training and evaluation, and decodes greedily;
- **the AMALIA article** to `<address>/base/v1/chat/completions` (`amalia-base`): the two messages
  and the plan's JSON Schema. The gateway writes it as the writer that recorded the worked examples
  did: the token ids the evaluated run read, the schema compiled by xgrammar with no free
  whitespace, greedy decoding with the repetition penalty asked for.

The GPU is off while nobody asks it anything. The next request switches it on and waits for the
two models to load, about 30 to 50 s, and the GPU stays on for a minute after the last request. A
request still running after 150 s is answered by Modal with a redirect to its result, which the
service follows. The service never asks the gateway for its list of models: that, too, would
switch the GPU on. Whether it is on is estimated from the service's own requests, with the
gateway's idle time in `MODAL_GPU_IDLE_S`, and the page's model status shows it: ready while it is
on, loading while a request switches it on, loads when needed while it is off. A GPU switched on
by anything else, another copy of the site or a test, shows as off until this service asks it
something.

Greedy decoding is not reproducible across GPUs. In the worked example `eleições_016_c7`, the
gateway's questions are the recorded ones, and its article has the recorded plan, sections and
conclusion, worded otherwise.

### A vLLM server of your own

Without `MODAL_API_URL`, `QG_API_URL` and `AMALIA_API_URL` say where each model answers. One vLLM
server serves both, at the revisions below (the evaluation ran vLLM 0.19.1):

```sh
vllm serve amalia-llm/AMALIA-9B-0626-DPO --revision c4614b9b5c7b4fe303fa20902e692fc7dface640 \
    --max-model-len 32768 \
    --structured-outputs-config '{"backend": "xgrammar", "disable_any_whitespace": true}' \
    --enable-lora --max-lora-rank 64 --lora-modules facta-pt-qg=<adapter folder>
```

with the adapter's folder from `hf download liaad/facta-pt-qg-amalia-9b-0626-dpo --revision
f8aff451e824fb4800c74385a36fea5f19579cfd --local-dir <adapter folder>`. In `.env`, the server's
address in `QG_API_URL` and `AMALIA_API_URL`, `QG_API_MODEL=facta-pt-qg` and
`AMALIA_API_MODEL=amalia-llm/AMALIA-9B-0626-DPO` (the base's id in `/v1/models`: the model given to
`vllm serve`, or its `--served-model-name`).

- **Question generation**: the adapter over the base. The service builds the prompt and fits it to
  the model window (the adapter's `max_seq_length`, less the 192 new tokens, as evaluated) here, with the base's
  tokenizer and the adapter's `checkpoint_info.json` - the only files of the two it fetches, about
  18 MB -, and asks the completions endpoint for it, greedy, as evaluated. The evaluated run read the
  base in 4-bit NF4: a server that reads it in another precision writes some questions differently.
  A `QG_API_MODEL` that names the writer's model is refused: without the adapter the base writes
  other questions.
- **Article writer**: the base itself, asked through the chat completions endpoint with the token
  ids the evaluated run read and that run's JSON Schema of the plan, which vLLM compiles with
  xgrammar under the `--structured-outputs-config` above, as that run set it; its character class
  is kept off U+D800-U+DFFF, which vLLM's server refuses and no text contains. Free whitespace is
  also refused per request (`guided_whitespace_pattern`, as vLLM 0.8 takes it): a server that
  allows it lets the model write blanks until the ceiling. The window has to hold
  the prompt (`ARTICLE_MAX_PROMPT_TOKENS`, 16384) and 8192 new tokens; a smaller one makes the
  service fit fewer passages. A server that refuses the schema is asked again without it, and the
  article records `formato="livre"`.

## Gemma on OpenRouter

The Gemma writer is [google/gemma-4-31b-it](https://openrouter.ai/google/gemma-4-31b-it) on
[OpenRouter](https://openrouter.ai), prompted as AMALIA is. In `.env`, the account's key in
`ARTICLE_API_KEY`; `ARTICLE_API_MODEL` picks the model (`google/gemma-4-31b-it` by default), and a
change takes `docker compose up -d inference`.

- Whether OpenRouter takes the key is asked of its `/key` when the service starts and every two
  minutes after: it describes the key and writes nothing, so it costs no credits. A key it does not
  take, an expired one, or one whose spending limit, or a budget over it, is spent makes the writer
  unavailable on the page, and available again when that changes. The account's balance is not
  there (only a management key reads it): a request it cannot pay for (402) makes the writer
  unavailable until a run tries it again.

- The service reads the model's entry in OpenRouter's `/models` when it starts, and asks only for
  the parameters it lists. The paid model takes the article's JSON Schema and the repetition
  penalty, and the request is routed only to a provider that honours both (`require_parameters`).
  The `:free` variants run on one provider, Google AI Studio, which takes neither the JSON Schema
  (it lists `response_format` for JSON mode, not `structured_outputs`) nor the penalty: their
  article is written freely (`formato="livre"` in the run's metadata), and their requests are
  rate-limited. When no provider takes every parameter asked, the request goes to any provider.
- Thinking is turned off, as the evaluated chat template left it. The prompt is counted with the
  model's tokenizer (`ARTICLE_API_TOKENIZER`, only its tokenizer files), to fit the passages to
  `ARTICLE_MAX_PROMPT_TOKENS`.
- This is not the evaluated configuration: the evaluated Gemma writer was Gemma 4 E4B, run in
  bfloat16 with xgrammar. A provider enforces the schema with its own engine, and which provider
  wrote an article is recorded in its metadata (`tentativas[].provedor`).

## FACT-PT's models

| Stage | Model | Size | Revision |
|---|---|---|---|
| Question generation | [liaad/facta-pt-qg-amalia-9b-0626-dpo](https://huggingface.co/liaad/facta-pt-qg-amalia-9b-0626-dpo) — QLoRA adapter, served by the API (here only its `checkpoint_info.json`) | 0.8 GB | `f8aff451e824fb4800c74385a36fea5f19579cfd` |
| Document relevance | [liaad/facta-pt-relevance-bertimbau-base](https://huggingface.co/liaad/facta-pt-relevance-bertimbau-base) | 0.4 GB | `8b6df9f96bda2c5ba3ec15d2e19deb8a1dbbce20` |
| Claim–evidence entailment | [liaad/facta-pt-cee-xlm-roberta-large-xnli](https://huggingface.co/liaad/facta-pt-cee-xlm-roberta-large-xnli) | 2.2 GB | `585f4cd2c89fdff1421093f60763a0a67be5174e` |

## Base and writer models

| Use | Model | Size | Revision |
|---|---|---|---|
| Base of the question generator, and the AMALIA article writer, served by the API (here only its tokenizer) | [amalia-llm/AMALIA-9B-0626-DPO](https://huggingface.co/amalia-llm/AMALIA-9B-0626-DPO) | 18.3 GB | `c4614b9b5c7b4fe303fa20902e692fc7dface640` (the one the adapter was trained on) |
| Gemma article writer, on OpenRouter (here only its tokenizer) | [google/gemma-4-31b-it](https://huggingface.co/google/gemma-4-31b-it) | — | latest |

In all, about 3 GB of disk here.

## Downloading ahead of time

To fetch everything before the first start (e.g. on a slow connection), with the image built (on
the GPU machine add `-f docker-compose.yml -f docker-compose.gpu.yml` after `docker compose`):

```sh
docker compose run --rm --no-deps inference hf download liaad/facta-pt-relevance-bertimbau-base --revision 8b6df9f96bda2c5ba3ec15d2e19deb8a1dbbce20
docker compose run --rm --no-deps inference hf download liaad/facta-pt-cee-xlm-roberta-large-xnli --revision 585f4cd2c89fdff1421093f60763a0a67be5174e
docker compose run --rm --no-deps inference hf download liaad/facta-pt-qg-amalia-9b-0626-dpo checkpoint_info.json --revision f8aff451e824fb4800c74385a36fea5f19579cfd
docker compose run --rm --no-deps inference hf download amalia-llm/AMALIA-9B-0626-DPO --revision c4614b9b5c7b4fe303fa20902e692fc7dface640 --include "tokenizer*" "special_tokens_map.json" "config.json" "chat_template*"
docker compose run --rm --no-deps inference hf download google/gemma-4-31b-it --include "tokenizer*" "special_tokens_map.json" "config.json" "chat_template*"
```

## Local checkpoints

On a server, the models can live in a folder of their own instead of being downloaded: no hub at
startup, works offline, and the files can be seen and checked. `docker-compose.yml` mounts
`CHECKPOINTS_DIR` (default `./checkpoints`) read-only at `/checkpoints`; the `modelos` volume
stays, for the Gemma writer's tokenizer, fetched from the hub (the writer needs the internet
anyway).

1. Copy the models out of a machine that already has them in its volume, at the pinned revisions,
   as plain files (about 3 GB):

   ```sh
   scripts/exportar-modelos.sh /path/to/checkpoints
   ```

   and move that folder to the server (`rsync -a`, a USB drive…). It holds
   `facta-pt-relevance-bertimbau-base`, `facta-pt-cee-xlm-roberta-large-xnli`, and, in `AMALIA-9B-0626-DPO` and `facta-pt-qg-amalia-9b-0626-dpo`, the tokenizer and the
   `checkpoint_info.json` the question generator reads.
2. In the server's `.env`, uncomment the block that sets `CHECKPOINTS_DIR` and points each
   `*_PATH` at `/checkpoints/<folder>` (`.env.example`).
3. Start as usual. The inference log names each model's folder as it loads, and `/health` says
   which loaded.

A local folder is used as it is: the `*_REVISION` pins no longer apply, so keep the folders at the
revisions above. Not on Windows with Docker Desktop: a folder mounted from the Windows disk is read
far more slowly than the volume.
