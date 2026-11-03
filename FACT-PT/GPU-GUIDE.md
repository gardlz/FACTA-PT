# Running FACT-PT on the GPU desktop

For the desktop with an **RTX 4060 Ti (8 GB)**, **32 GB of RAM**, **Windows with WSL2** and Docker
already able to use the GPU.

## How the models fit

- **Question generator** (AMALIA-9B + FACT-PT adapter) and **AMALIA writer**: on Modal, behind
  the gateway set in `.env` (`MODAL_API_*`, [MODELS.md](MODELS.md)). Nothing of them runs here.
- **Gemma writer**: Gemma 4 31B on OpenRouter (`ARTICLE_API_KEY`,
  [MODELS.md](MODELS.md#gemma-on-openrouter)). Nothing of it runs here either.
- **Relevance and claim–evidence classifiers**: on the GPU, the only models that run here.
- **Idle models leave the GPU.** A model unused for `GPU_IDLE_TTL_S` seconds (600 by default; 0
  keeps them there) goes back to main memory and returns, in seconds, with the next claim. This
  matters on a card that holds every model, where nothing else ever makes them leave. The page's
  model list says which model is on the GPU. A model unused for `RAM_IDLE_TTL_S` seconds (1800 by
  default; 0 keeps them) leaves main memory too, and the next claim loads it again from disk, in
  seconds. The list then shows it as «carrega quando for preciso». The models behind the APIs are
  not this service's to let go.
- **Runs** wait in a queue and the worker takes them one at a time; the page shows how many are
  ahead.

## 1. Check that Docker sees the GPU

```sh
docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu24.04 nvidia-smi
```

It should print the 4060 Ti. If not, fix Docker's GPU support first.

## 2. Give WSL enough memory

WSL gets half of the machine's memory by default (16 GB), too little for a writer. Create or edit
`%UserProfile%\.wslconfig`:

```ini
[wsl2]
memory=28GB
```

Then, in PowerShell, `wsl --shutdown`, and start Docker again.

## 3. Get the code

Clone the repository and go into the prototype's folder:

```sh
git clone https://github.com/LIAAD/factapt.git
cd factapt/FACT-PT
```

`.gitattributes` keeps Unix line endings even on Windows: the Dockerfiles break with Windows ones.
Later changes: `git pull`, then step 5 again (with no run under way).

## 4. Make `.env`

`.env` is not in git: it holds the LUSA account and the password gate's secrets. Copy it from the
Mac by hand (USB, scp…), or start from `.env.example`. Then, for this machine:

- **fill in** the Modal gateway that serves the AMALIA models: `MODAL_API_URL` and
  `MODAL_API_KEY` (`.env.example`);
- **fill in** `ARTICLE_API_KEY`, the OpenRouter key for the Gemma writer;
- **delete** the `ARTICLE_WRITERS=…` line, so both writers are offered;
- **keep** `COOKIE_SECURE=false` while the site is opened over plain HTTP
  (`http://localhost:8000`). To let others in, over HTTPS and without a domain, Tailscale Funnel
  works with Docker Desktop: remove that line and follow
  [SERVER-GUIDE.md](SERVER-GUIDE.md#without-a-domain-tailscale-funnel) — its reverse proxy step is
  for a Linux server, but step 5, the proxy's address, carries over;
- **make sure** there is no `RUN_STORE_DIR=/tmp/…` line: the website and the worker must share
  the run store's volume;
- the **LUSA API only answers over the VPN**: the VPN must be on on this machine.

## 5. Start

```sh
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

The first start builds the images and downloads the classifiers, about **3 GB** (see
[MODELS.md](MODELS.md)). The site answers at once at http://localhost:8000, with the worked
examples; new claims once the models are loaded.

Always use both `-f` files on this machine, for `up`, `run` and `exec` alike.

## 6. Check

Follow the inference service as it downloads and loads:

```sh
docker compose -f docker-compose.yml -f docker-compose.gpu.yml logs -f inference
```

The question generator and the AMALIA writer should be reported **`disponível`** at the API's
address. When the card is full, the GPU sharing logs a warning that it borrows system memory: that
is expected.

Which models are loaded:

```sh
docker compose -f docker-compose.yml -f docker-compose.gpu.yml exec inference python -c "import urllib.request as u; print(u.urlopen('http://localhost:8100/health').read().decode())"
```

`"status": "ok"`. A model that is not available is listed under `motivos`, with the reason.

## 7. The queue

```sh
docker compose -f docker-compose.yml -f docker-compose.gpu.yml exec worker python -m app.fila
```

lists the runs under way and waiting, with the session and address that asked for each.
`… python -m app.fila cancelar ID [ID …]` cancels some, `… cancelar --todas` all of them.

Do not rebuild or restart the `worker` while a run is under way: the run is lost (its page says
so). Check the queue first.

## If something does not fit

| What you see | What to do |
|---|---|
| The question generator or the AMALIA writer not available | `MODAL_API_URL` or `MODAL_API_KEY` is missing or wrong (with a server of your own: it does not answer at `QG_API_URL` / `AMALIA_API_URL`, or does not serve the model named in `QG_API_MODEL` / `AMALIA_API_MODEL`): `/health` and the inference log say which. |
| A model refused with «não há lugar na GPU» | The driver lending memory was not detected: add `GPU_LENDS_MEMORY=true` to `.env` and restart the inference service. |
| The Gemma writer not available | `ARTICLE_API_KEY` is missing or wrong, its spending limit is spent, the account ran out of credits, or OpenRouter does not list `ARTICLE_API_MODEL`: `/health` and the inference log say which. |
| «CUDA driver error: device not ready» loading a model | `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` stops the driver lending memory. `docker-compose.gpu.yml` empties it; check that file is used (`-f` twice). |
| «Error in input stream» in the browser | The page reconnects by itself; if it keeps failing, reload with Ctrl+Shift+R. |

## Not yet tested on this machine

The GPU image build itself. Watch the inference logs on the first start.
